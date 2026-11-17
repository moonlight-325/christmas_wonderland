"""데스크톱 눈 엔진: 시뮬레이션 + 창 추적 + 모니터별 오버레이를 묶어 관리한다. 위젯 UI 와 독립적으로 동작."""
from __future__ import annotations

import time

from PySide6.QtCore import QElapsedTimer, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication

from core.logger import get_logger
from . import winapi
from .overlay import SnowOverlay
from .diag import FrameDiag
from .matter import is_ground
from .physics import Rect, SnowSim
from .surfaces import compute_surfaces, visible_decor_rects

log = get_logger("snow")

TRACK_INTERVAL_MS = 80
DECOR_OCC_EVERY = 4      # 장식 창을 가리는 창 목록은 이 프레임 수마다 다시 구한다 (사각형 자체는 매 프레임)
DECOR_OCC_IDLE_EVERY = 24    # 창 구성에 변화가 없을 때의 안전 확인 간격(프레임): 변화가 감지되면 곧바로 DECOR_OCC_EVERY 로 돌아간다
DECOR_OCC_BURST = 3          # 변화가 감지된 뒤 가림 목록을 연달아 다시 구하는 횟수 (깜빡임 방지용 2회 연속 확인 포함)
MISS_CONFIRM_MS = 30          # 창이 사라진 것을 처음 본 뒤, 같은 결과를 한 번 더 확인하기까지의 시간 (이 뒤에 눈이 떨어진다)
TRACK_FULL_EVERY = 6         # 창 구성이 그대로여도 이 틱 수마다 표면/바닥/가림을 한 번은 전부 다시 계산하는 안전망
KEEPER_INTERVAL_MS = 500      # 바닥 오버레이/작업표시줄 사각형 안전망. 전경 창이 바뀔 때는 아래 FG_BURST_MS 로 바로 확인한다
FG_BURST_MS = (0, 40, 150, 400)   # 전경 창 변경 뒤 셸이 Z-order 를 다 바꿀 때까지 몇 번 확인 (새 알림이 오면 이전 예약은 취소)
DISPLAY_SETTLE_MS = 300       # 화면 구성/해상도/작업 영역 변경이 연달아 올 때 한 번으로 합치는 시간
MAX_ERRORS = 8
LAG_LOG_GAP = 3.0        # 렉 진단 로그는 이 시간(초)에 한 번만 남긴다


class SnowEngine(QObject):
    gust = Signal(float, float)          # 돌풍 발생 (세기 0~1, 방향 도) - 사운드 시스템 연동용

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.sim = SnowSim()
        self.sim.gust_listeners.append(lambda amp, deg: self.gust.emit(amp, deg))
        self.overlays: list[SnowOverlay] = []
        self.top_overlays: list[SnowOverlay] = []      # 장식 창 위에만 눈을 덧그리는 오버레이 (모니터마다 하나, Windows 전용)
        self._decor_pend: dict = {}                    # 가리는 창 목록 변화 확인 대기 (깜빡임 방지)
        self._decor_occ: dict = {}                     # 장식 창 hwnd -> 그 위에 있는 다른 프로그램 창 사각형
        self._decor_n = 0
        self._cut_rects: list = []                     # 작업표시줄 창 사각형 (눈을 그리지 않는다)
        self._monitor_rects: list = []
        self._paused_monitors: set = set()
        self._errors = 0
        self._running = False
        self.world = None                # snowman.world.SnowmanWorld (SnowmanManager 가 attach_world 로 연결)
        self._win_surfaces: list = []    # 창/작업표시줄 표면 (눈사람 머리 표면은 따로 합친다)
        self._world_seen = -1
        self._wsurf_t = 0.0
        self._lag_t = 0.0
        self._tick_t = 0.0
        self._miss_timer_set = False
        self._diag = FrameDiag()             # 5초마다 [프레임 요약] 로그를 남기는 진단 수집기
        self._track_ms = 0.0                 # 렉 진단용: 창 추적 한 번의 GUI 처리 전체(ms)
        self._collect_ms = 0.0               # 렉 진단용: 그 중 Windows 창 목록 수집(ms)
        self._decor_ms = 0.0                 # 렉 진단용: 장식 영역 계산(ms)
        self._update_ms = 0.0                # 렉 진단용: 오버레이 그리기 요청(update 호출)(ms)
        self._calc_parts: dict = {}          # 렉 진단용: 틱 계산의 부분별 시간(ms)
        self._track_sig = None               # 직전 창 추적 결과의 요약 (같으면 표면 재계산을 건너뛴다)
        self._track_n = 0
        self._decor_dirty = DECOR_OCC_BURST  # 장식 창을 가리는 창 목록을 서둘러 다시 구해야 하는 남은 횟수
        self._decor_vis: dict = {}           # 장식 창 hwnd -> (창 사각형, 가림 목록, 보이는 사각형들)
        self._fg_gen = 0                     # 전경 창 변경 알림 세대 (이전 예약 확인 취소용)
        self._hooked_screens: set = set()    # 화면 변경 신호를 이미 연결한 QScreen

        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._track = QTimer(self)
        self._track.setInterval(TRACK_INTERVAL_MS)
        self._track.timeout.connect(self._track_tick)
        self._keeper = QTimer(self)
        self._keeper.setInterval(KEEPER_INTERVAL_MS)
        self._keeper.timeout.connect(self._keep_tick)

        self._disp_timer = QTimer(self)
        self._disp_timer.setSingleShot(True)
        self._disp_timer.setInterval(DISPLAY_SETTLE_MS)
        self._disp_timer.timeout.connect(self._after_display_change)

        app = QGuiApplication.instance()
        app.screenAdded.connect(lambda _s: self.rebuild_overlays())
        app.screenRemoved.connect(lambda _s: self.rebuild_overlays())
        app.primaryScreenChanged.connect(self._on_display_changed)
        settings.changed.connect(self._on_setting)

    # ------------------------------------------------------------------ 시작/종료
    def start(self):
        self._sync_settings()
        self.rebuild_overlays()
        self._apply_enabled()

    def shutdown(self):
        self._diag.stop_gc()
        self._timer.stop()
        self._track.stop()
        self._keeper.stop()
        self._disp_timer.stop()
        for o in self.overlays + self.top_overlays:
            try:
                o.hide()
                o.deleteLater()
            except Exception:
                pass
        self.overlays.clear()
        self.top_overlays.clear()
        self._running = False

    # ------------------------------------------------------------------ 눈덩이/눈사람 월드
    def attach_world(self, world):
        """눈사람 월드를 눈 시뮬레이션에 연결한다 (sim.bodies). 틱마다 월드를 한 걸음 진행하고 오버레이가 그린다."""
        self.world = world
        self.sim.bodies = world
        self._world_seen = -1
        self._track_sig = None               # 새 월드에도 창 장애물을 바로 전달한다

    def _push_surfaces(self):
        extra = self.world.surfaces() if (self.world is not None and getattr(self.world, "visible", True)) else []
        self.sim.set_surfaces(list(self._win_surfaces) + extra)

    def _step_world(self, dt: float):
        w = self.world
        if w is None or not bool(self.settings.get("snowman.enabled")):
            return
        if not (w.balls or w.snowmen or w.props):
            return
        down = winapi.left_button_down() if winapi.IS_WINDOWS else bool(
            QGuiApplication.mouseButtons() & Qt.LeftButton)
        w.step(dt, self._cursor_phys(), down)
        # 장식용 눈사람 머리 표면: 월드가 바뀌었거나(이동/삭제) 0.5초마다 눈 표면 목록 갱신
        self._wsurf_t += dt
        if w.counter != self._world_seen or self._wsurf_t >= 0.5:
            self._world_seen = w.counter
            self._wsurf_t = 0.0
            self._push_surfaces()

    # ------------------------------------------------------------------ 설정 반영
    def _on_setting(self, key: str):
        if key == "autoweather" or key.startswith("autoweather."):
            self._sync_settings()           # 자동 날씨 설정/상태 변경: 값만 다시 반영
            return
        if key == "*" or key.split(".")[0] in ("snow", "wind", "performance", "weather", "physics"):
            self._sync_settings()
            self._apply_enabled()

    def _sync_settings(self):
        """모든 값은 settings.effective() 를 거친다: 자동 날씨가 조정 중인 변수는 자동 적용값, 나머지는 수동 설정값."""
        s = self.settings
        eff = s.effective
        self.sim.configure(
            enabled=bool(s.get("snow.enabled")),
            amount=int(eff("snow.amount")),
            speed=float(eff("snow.speed")),
            size=float(eff("snow.size")),
            accumulate=int(eff("snow.accumulate")),
            accumulate_rate=int(eff("snow.accumulate_rate")),
            max_height=int(s.get("snow.max_height")),
            wind_dir=int(eff("wind.direction")),
            wind_strength=int(eff("wind.strength")),
            max_particles=int(s.get("performance.max_particles")),
            blizzard=(int(s.get("weather.blizzard")) / 100.0 if s.get("weather.blizzard_on") else 0.0),
            gust_on=bool(s.get("weather.gust_on")),
            gust_strength=int(eff("weather.gust_strength")) / 100.0,
            gust_interval=float(eff("weather.gust_interval")),
            temperature=float(eff("weather.temperature")),
            cursor_on=bool(s.get("weather.cursor_on")),
            cursor_strength=int(s.get("weather.cursor_strength")) / 100.0,
            cursor_radius=float(s.get("weather.cursor_radius")),
            cursor_gain=int(s.get("physics.cursor_gain")) / 100.0,
            flake_react=int(s.get("physics.flake_react")) / 100.0,
            pile_react=int(s.get("physics.pile_react")) / 100.0,
            wrap=bool(s.get("physics.wrap")),
            inertia=int(s.get("physics.inertia")) / 100.0,
            friction=int(s.get("physics.friction")) / 100.0,
            collision=int(s.get("physics.collision")) / 100.0,
            swirl=int(s.get("physics.swirl")) / 100.0,
            chain=int(s.get("physics.chain")) / 100.0,
            spread=int(s.get("physics.spread")) / 100.0,
            win_slip=int(s.get("physics.win_slip")) / 100.0,
            win_fall=int(s.get("physics.win_fall")) / 100.0,
        )
        self._timer.setInterval(max(8, int(1000 / int(s.get("performance.fps")))))
        self._diag.want_ms = 1000.0 / max(1, int(s.get("performance.fps")))

    def on_auto_applied(self):
        """자동 날씨 적용값이 바뀔 때마다 (약 10Hz) 시뮬레이션에 반영."""
        try:
            self._sync_settings()
        except Exception:
            self._fail("자동 날씨 반영")

    def _apply_enabled(self):
        want = bool(self.settings.get("snow.enabled")) and self._errors < MAX_ERRORS
        if want and not self._running:
            self._running = True
            for o in self.overlays:
                self._show_overlay(o)
            self._clock.start()
            self._timer.start()
            self._keeper.start()
            self._diag.reset()
            self._diag.start_gc()
            winapi.install_foreground_hook(self._on_foreground)
        elif not want and self._running:
            self._running = False
            self._timer.stop()
            self._keeper.stop()
            self._diag.stop_gc()
            for o in self.overlays + self.top_overlays:
                o.hide()
            for o in self.top_overlays:
                o.set_decor_rects([])
        if self._running and self.settings.get("performance.track_windows") and winapi.IS_WINDOWS:
            if not self._track.isActive():
                self._track.start()
        else:
            self._track.stop()
            self._track_sig = None
            self._win_surfaces = []
            if self.sim.surfaces:
                self._push_surfaces()
            if self.world is not None:
                self.world.set_obstacles([])
        if self._running:
            self._track_tick()

    def _show_overlay(self, o: SnowOverlay):
        try:
            o.present()
        except Exception:
            log.exception("오버레이 표시 실패")

    # ------------------------------------------------------------------ 모니터 / 오버레이
    def rebuild_overlays(self):
        for o in self.overlays + self.top_overlays:
            o.hide()
            o.deleteLater()
        self.overlays.clear()
        self.top_overlays.clear()
        self._decor_occ.clear()
        self._decor_pend.clear()
        screens = QGuiApplication.screens()
        native = winapi.get_monitors()
        rects = []
        for sc in screens:
            r = native.get(sc.name())
            if r is None:
                g = sc.geometry()
                dpr = sc.devicePixelRatio()
                r = (round(g.x() * dpr), round(g.y() * dpr),
                     round((g.x() + g.width()) * dpr), round((g.y() + g.height()) * dpr))
            rects.append(r)
            ov = SnowOverlay(sc, self.sim)
            ov.label = "일반#%d" % len(self.overlays)
            ov.native_rect = r if winapi.IS_WINDOWS else None   # 아래 _fit_overlays 가 작업표시줄 윗선까지로 줄인다
            self.overlays.append(ov)
            if winapi.IS_WINDOWS:
                tv = SnowOverlay(sc, self.sim, top=True)
                tv.label = "장식#%d" % len(self.top_overlays)
                tv.native_rect = r
                self.top_overlays.append(tv)
        self._monitor_rects = rects
        self._hook_screens(screens)
        if rects:
            self.sim.cell = max(2, round(3 * max(s.devicePixelRatio() for s in screens)))
            self.sim.set_bounds(Rect(min(r[0] for r in rects), min(r[1] for r in rects),
                                     max(r[2] for r in rects), max(r[3] for r in rects)))
            self.sim.set_monitors(rects, self._floors_for(screens, rects))   # 바닥 = 작업표시줄 윗선(없으면 모니터 아래 가장자리)
            self._fit_overlays()
        self._paused_monitors = set()
        if self._running:
            for o in self.overlays:
                self._show_overlay(o)
        log.info("눈 오버레이 %d개 준비 (모니터 %d개)", len(self.overlays), len(rects))

    def _fit_overlays(self):
        """오버레이 창을 모니터 맨 위 ~ 작업표시줄 윗선까지로 맞춘다: 작업표시줄 아래는 창 자체가 없어 눈이 그려지지 않는다."""
        if not winapi.IS_WINDOWS:
            return
        for lst in (self.overlays, self.top_overlays):
            for i, o in enumerate(lst):
                if i >= len(self._monitor_rects) or i >= len(self.sim.floors):
                    continue
                l, t, r, b = self._monitor_rects[i]
                fl = int(self.sim.floors[i])
                nr = (l, t, r, fl if t + 200 < fl < b else b)
                if o.native_rect != nr:
                    o.native_rect = nr
                    if o.top:                          # 장식 오버레이: 한계 영역이 바뀌었으니 창 크기를 다시 정한다
                        o._fit = None
                        o._mask_sig = None
                    if o.isVisible():
                        o.fix_native()

    def _floors_for(self, screens, rects) -> list:
        """모니터별 바닥 y. 1순위: 사각형으로 짝지은 작업표시줄 윗선, 2순위: 장치 이름으로 구한 값, 3순위: 모니터 아래 가장자리."""
        by_rect = winapi.floors_for_rects(list(rects))
        native = winapi.get_floors()
        out = []
        for sc, r, fr in zip(screens, rects, by_rect):
            fl = fr if (fr is not None and r[1] < fr < r[3]) else native.get(sc.name())
            out.append(float(fl) if fl is not None and r[1] < fl <= r[3] else float(r[3]))
        return out

    # ------------------------------------------------------------------ 타이머
    def _tick(self):
        try:
            dt = self._clock.restart() / 1000.0
            t0 = time.perf_counter()
            parts = self._calc_parts
            if len(self._paused_monitors) < len(self.overlays):
                self.sim.set_cursor(self._cursor_phys() if self.sim.cursor_on else None, dt)
                t1 = time.perf_counter()
                self.sim.step(dt)
                t2 = time.perf_counter()
                self._step_world(dt)
                t3 = time.perf_counter()
                parts["커서"], parts["눈"], parts["눈사람"] = (t1 - t0) * 1000.0, (t2 - t1) * 1000.0, (t3 - t2) * 1000.0
            step_ms = (time.perf_counter() - t0) * 1000.0
            self._decor_tick()
            t4 = time.perf_counter()
            for i, o in enumerate(self.overlays):
                if i not in self._paused_monitors and o.isVisible():
                    o.request_paint()
            for i, o in enumerate(self.top_overlays):
                if i not in self._paused_monitors and o.isVisible():
                    o.request_paint()          # 장식 위 오버레이는 보이는 영역만 다시 그린다
            self._update_ms = (time.perf_counter() - t4) * 1000.0
            self._tick_t = t0
            inner_ms = (time.perf_counter() - t0) * 1000.0
            self._diag.on_tick(dt * 1000.0, self._timer.interval(), inner_ms, step_ms, self._decor_ms, self._update_ms)
            self._lag_check(dt * 1000.0, step_ms)
            self._diag_report()
        except Exception:
            self._fail("틱")

    def _diag_report(self):
        """5초마다 한 번: 틱/paint/창 추적/GC/CPU 를 한 표로 정리해 로그에 남긴다 (읽기 쉬운 [프레임 요약])."""
        d = self._diag
        if not d.due():
            return
        try:
            ovs = [(o.label, o.stat) for o in self.overlays + self.top_overlays]
            s = self.settings
            screens = QGuiApplication.screens()
            extra = {
                "모니터": "%d개 (배율 %s)" % (len(screens), "/".join("%.2g" % sc.devicePixelRatio() for sc in screens)),
                "fps 설정": s.get("performance.fps"),
                "눈 양": s.get("snow.amount"),
                "최대 입자": s.get("performance.max_particles"),
                "창 추적": "켜짐" if self._track.isActive() else "꺼짐",
                "일시정지 모니터": len(self._paused_monitors),
            }
            log.info("%s", d.build(ovs, self.sim, extra))
            for o in self.overlays + self.top_overlays:
                o.reset_stat()
        except Exception:
            log.exception("프레임 요약 실패")
            d.reset()

    def _decor_tick(self):
        """장식 창(전구·장식·시계·스노우볼)이 보이는 부분을 구해 top 오버레이에 알린다 -> 눈이 모든 장식 위에 그려진다.
        다른 프로그램 창이 장식 위를 덮은 부분은 제외한다.
        가림 목록(Z-order 를 훑는 비싼 작업)은 창 구성이 바뀐 것이 감지됐을 때만 서둘러 다시 구하고, 평소에는 드문드문 안전 확인만 한다."""
        t0 = time.perf_counter()
        if not self.top_overlays:
            self._decor_ms = 0.0
            return
        try:
            from decor.layer import decor_windows
            wins = decor_windows() if self._running else []
            n = self._decor_n
            self._decor_n += 1
            if self._track.isActive():
                # 창 추적이 창 구성 변화를 알려 준다: 변화가 있을 때만 자주, 없으면 드물게 확인
                refresh = (n % DECOR_OCC_EVERY == 0) and (self._decor_dirty > 0 or n % DECOR_OCC_IDLE_EVERY == 0)
            else:
                refresh = (n % DECOR_OCC_EVERY == 0)            # 창 추적이 꺼져 있으면 예전과 같은 주기
            if refresh and self._decor_dirty > 0:
                self._decor_dirty -= 1
            alive = set()
            rects: list = []
            for w in wins:
                try:
                    hwnd = int(w.winId())
                except Exception:
                    continue
                r = winapi.window_rect(hwnd)
                if r is None:
                    continue
                alive.add(hwnd)
                if hwnd not in self._decor_occ:
                    occ = winapi.occluders_above(hwnd)
                    self._decor_occ[hwnd] = occ
                    self._decor_pend[hwnd] = (None, 0)
                elif refresh:
                    # 깜빡임 방지: 가리는 창 목록이 바뀌어도 두 번 연속 같은 결과일 때만 반영한다 (잠깐 나타났다 사라지는 보조 창 무시)
                    occ = winapi.occluders_above(hwnd)
                    if occ != self._decor_occ[hwnd]:
                        last, cnt = self._decor_pend.get(hwnd, (None, 0))
                        cnt = cnt + 1 if last == occ else 1
                        if cnt >= 2:
                            self._decor_occ[hwnd] = occ
                            self._decor_pend[hwnd] = (None, 0)
                        else:
                            self._decor_pend[hwnd] = (occ, cnt)
                            self._decor_dirty = max(self._decor_dirty, 1)    # 확인 중이면 다음 확인까지 서둔다
                    else:
                        self._decor_pend[hwnd] = (None, 0)
                occ_now = self._decor_occ[hwnd]
                hit = self._decor_vis.get(hwnd)
                if hit is not None and hit[0] == r and hit[1] is occ_now:
                    vis = hit[2]                              # 창 위치도 가림 목록도 그대로: 계산 결과 재사용
                else:
                    vis = visible_decor_rects(r, occ_now)
                    self._decor_vis[hwnd] = (r, occ_now, vis)
                rects.extend(vis)
            for k in [k for k in self._decor_occ if k not in alive]:
                del self._decor_occ[k]
                self._decor_pend.pop(k, None)
                self._decor_vis.pop(k, None)
            for i, o in enumerate(self.top_overlays):
                if i in self._paused_monitors or not rects:
                    o.set_decor_rects([])
                    continue
                ml, mt, mr, mb = self._monitor_rects[i]
                mine = []
                for (l, t, rr, b) in rects:
                    l2, t2, r2, b2 = max(l, ml), max(t, mt), min(rr, mr), min(b, mb)
                    if r2 > l2 and b2 > t2:
                        mine.append((l2, t2, r2, b2))
                o.cut_rects = self._cut_rects
                o.set_decor_rects(mine)                # 오버레이가 새로 나타날 때만 Z-order 를 맞춘다 (프레임마다 순서를 검사하지 않는다)
        except Exception:
            self._fail("장식 위 눈")
        finally:
            self._decor_ms = (time.perf_counter() - t0) * 1000.0

    def _lag_check(self, gap_ms: float, step_ms: float):
        """프레임이 눈에 띄게 늦거나 한 부분이 오래 걸리면 어디가 느린지 로그에 남긴다 (3초에 한 번)."""
        want = 1000.0 / max(1, int(self.settings.get("performance.fps")))
        paint = sum(getattr(o, "last_paint_ms", 0.0) for o in self.overlays)
        paint_top = sum(getattr(o, "last_paint_ms", 0.0) for o in self.top_overlays)
        if (gap_ms < want * 2.2 and step_ms < 20.0 and paint < 25.0 and paint_top < 25.0
                and self._track_ms < 15.0 and self._decor_ms < 10.0 and self._update_ms < 10.0):
            return
        now = time.monotonic()
        if now - self._lag_t < LAG_LOG_GAP:
            return
        self._lag_t = now
        sim = self.sim
        hits = sum(o.cache_hits for o in self.overlays + self.top_overlays)
        builds = sum(o.cache_builds for o in self.overlays + self.top_overlays)
        for o in self.overlays + self.top_overlays:
            o.cache_hits = o.cache_builds = 0
        fmt = lambda d: " / ".join("%s %.1f" % (k, v) for k, v in d.items())
        log.warning("[렉 진단] 프레임 간격 %.1fms (목표 %.1fms)\n"
                    "계산        %6.1fms : %s\n"
                    "장식 영역   %6.1fms\n"
                    "그리기 요청 %6.1fms\n"
                    "일반 오버레이 %6.1fms (paint 합계)\n"
                    "장식 오버레이 %6.1fms (paint 합계)\n"
                    "창 추적     %6.1fms (GUI 처리) / 수집 %6.1fms\n"
                    "개수        : 눈송이 %d · 눈덩어리 %d · 눈더미 %d · 창 표면 %d · 오버레이 일반 %d/장식 %d\n"
                    "눈 구간     : %s\n"
                    "셀          : 합계 %d (최대 %d), 표면 구간 %d\n"
                    "눈더미 캐시 : 적중 %d · 재생성 %d",
                    gap_ms, want, step_ms, fmt(self._calc_parts), self._decor_ms, self._update_ms, paint, paint_top,
                    self._track_ms, self._collect_ms,
                    len(sim.flakes), len(sim.parcels), len(sim.piles), len(self._win_surfaces),
                    len(self.overlays), len(self.top_overlays),
                    fmt(sim.perf), sum(len(p.cells) for p in sim.piles.values()),
                    max((len(p.cells) for p in sim.piles.values()), default=0),
                    sum(len(p.segments) for p in sim.piles.values()), hits, builds)
        known = step_ms + self._decor_ms + self._update_ms + paint + paint_top + self._track_ms
        if gap_ms - known > 20.0:                        # 측정된 구간으로 설명되지 않는 시간: 창 합성/복사, 다른 창 그리기, 이벤트 처리 등
            ends = [getattr(o, "last_paint_end", 0.0) for o in self.overlays + self.top_overlays]
            after = (getattr(self, "_tick_t", 0.0) - max(ends)) * 1000.0 if ends and max(ends) else -1.0
            log.warning("[프레임 진단] 설명되지 않는 시간 %.1fms (간격 %.1fms - 측정합 %.1fms) · 마지막 그리기 끝~이번 틱 %.1fms",
                        gap_ms - known, gap_ms, known, after)
        if sim.perf.get("parcels", 0.0) >= 8.0:          # 덩어리 구간이 느릴 때만: 안쪽 어디가 느린지 (ms / 개수)
            log.warning("[덩어리 진단] %s | 보관함 %d", fmt(sim.pstat), len(sim._reservoir))

    def _cursor_phys(self):
        """커서의 물리 픽셀 좌표. Windows 는 GetCursorPos, 그 외에는 Qt 좌표 x 배율."""
        pos = winapi.cursor_pos()
        if pos is not None:
            return pos
        p = QCursor.pos()
        sc = QGuiApplication.screenAt(p)
        dpr = sc.devicePixelRatio() if sc else 1.0
        return p.x() * dpr, p.y() * dpr

    def trigger_gust(self, strength: float | None = None, direction: float | None = None):
        """돌풍을 즉시 일으킨다 (설정창/트레이 버튼)."""
        self.sim.trigger_gust(strength, direction)

    def _track_tick(self):
        try:
            t0 = time.perf_counter()
            entries = winapi.snapshot_windows()
            self._collect_ms = (time.perf_counter() - t0) * 1000.0
            surf_ms = push_ms = 0.0
            full = same = False
            sig = (tuple((e.key, e.left, e.top, e.right, e.bottom, e.surface, e.taskbar, e.own) for e in entries),
                   tuple(self.sim.floors), tuple(self._monitor_rects))
            self._track_n += 1
            changed = sig != self._track_sig or self._track_n % TRACK_FULL_EVERY == 0 or self._miss_pending()
            if changed:
                # 창 위치/크기/Z-order/작업표시줄이 바뀌었을 때(와 안전망으로 가끔)만 표면·바닥·가림을 다시 계산한다
                sig_changed = sig != self._track_sig
                if sig_changed:
                    self._decor_dirty = DECOR_OCC_BURST          # 장식 창을 가리는 창 목록도 서둘러 다시 확인
                self._track_sig = sig
                full = True
                ts = time.perf_counter()
                new_surf = compute_surfaces(entries, self._monitor_rects, self.sim.floors)
                surf_ms = (time.perf_counter() - ts) * 1000.0
                same = (not sig_changed) and new_surf == self._win_surfaces
                self._win_surfaces = new_surf
                self._cut_rects = [(e.left, e.top, e.right, e.bottom) for e in entries if e.taskbar]
                for o in self.overlays:
                    o.cut_rects = self._cut_rects
                if not same or self._miss_pending():   # 안전망 재계산 결과가 그대로면 시뮬레이션에 다시 밀어 넣지 않는다 (프레임 끊김 방지). 사라진 창의 눈은 확인이 끝날 때까지 계속 반영
                    tp = time.perf_counter()
                    self._push_surfaces()
                    push_ms = (time.perf_counter() - tp) * 1000.0
                    if self._miss_pending():
                        self._confirm_miss_soon()
                if winapi.IS_WINDOWS and self._monitor_rects:      # 작업표시줄 크기/위치/자동 숨김 변경 반영
                    if self.sim.set_floors(self._floors_for(QGuiApplication.screens(), self._monitor_rects)):
                        log.debug("바닥 기준선 변경: %s", self.sim.floors)
                        self._fit_overlays()
                if self.world is not None and not same:    # 창이 덮은 곳은 클릭이 창으로 가므로 눈덩이 잡기/밀기에서 제외
                    self.world.set_obstacles([(e.left, e.top, e.right, e.bottom) for e in entries])
            self._check_fullscreen()                   # 전경 창이 전체화면인지는 매번 확인 (가벼움)
            self._track_ms = (time.perf_counter() - t0) * 1000.0
            misc_ms = self._track_ms - self._collect_ms - surf_ms - push_ms
            self._diag.on_track(self._track_ms, self._collect_ms, surf_ms, push_ms, max(0.0, misc_ms), full, same)
        except Exception:
            self._fail("창 추적")

    def _miss_pending(self) -> bool:
        """창이 목록에서 빠져 '사라짐 확인 중'인 눈더미가 있는가 (최소화/닫힘 직후). 있으면 확인이 끝날 때까지 매번 반영해야 눈이 떨어진다."""
        return any(p.miss > 0 for p in self.sim.piles.values())

    def _confirm_miss_soon(self):
        """사라진 창의 눈이 바로 떨어지도록, 다음 80ms 창 추적을 기다리지 않고 곧 한 번 더 확인한다."""
        if self._miss_timer_set or not self._running:
            return
        self._miss_timer_set = True

        def run():
            self._miss_timer_set = False
            if self._running:
                self._track_tick()
        QTimer.singleShot(MISS_CONFIRM_MS, run)

    def _check_fullscreen(self):
        if not self.settings.get("performance.pause_fullscreen"):
            new = set()
        else:
            new = winapi.fullscreen_monitors(self._monitor_rects)
        if new != self._paused_monitors:
            self._paused_monitors = new
            for i, o in enumerate(self.overlays):
                o.setVisible(i not in new) if self._running else None
            for i, o in enumerate(self.top_overlays):
                if i in new:
                    o.set_decor_rects([])

    def _on_foreground(self):
        """활성 창이 바뀜(바탕화면/작업표시줄 클릭 등): 셸이 Z-order 를 다 바꾼 뒤에 몇 번 확인한다.
        알림이 연달아 와도 이전 알림의 남은 예약은 취소하므로 확인이 겹쳐 쌓이지 않는다."""
        if not self._running:
            return
        self._fg_gen += 1
        self._decor_dirty = DECOR_OCC_BURST
        gen = self._fg_gen
        for ms in FG_BURST_MS:
            QTimer.singleShot(ms, lambda g=gen: self._keep_tick() if g == self._fg_gen else None)

    # ------------------------------------------------------------------ 화면 구성 / 해상도 / 작업 영역 변경
    def _hook_screens(self, screens):
        self._hooked_screens &= set(screens)
        for sc in screens:
            if sc in self._hooked_screens:
                continue
            self._hooked_screens.add(sc)
            sc.geometryChanged.connect(self._on_display_changed)            # 해상도 변경
            sc.availableGeometryChanged.connect(self._on_display_changed)   # 작업표시줄 위치/자동 숨김 변경 (작업 영역이 바뀜)

    def _on_display_changed(self, *_args):
        if self._running:
            self._disp_timer.start()                  # 연달아 오는 알림은 한 번으로 합친다

    def _after_display_change(self):
        if not self._running:
            return
        try:
            from decor.layer import request_settle          # 눈 오버레이가 장식 위인지 다시 확인
            request_settle("display-change")
        except Exception:
            self._fail("화면 변경 후 Z-order 확인")
        self._keep_tick()

    def _keep_tick(self):
        """안전망 + 전경 창 변경 직후 확인: 작업표시줄 사각형 갱신, 바닥 오버레이의 Z-order 유지.
        항상 위 층(top 오버레이·장식)의 Z-order 는 decor.layer 가 이벤트로 점검한다."""
        try:
            if winapi.IS_WINDOWS:                              # 작업표시줄 사각형은 창 추적 설정과 무관하게 항상 갱신
                tb = winapi.taskbar_rects()
                if tb != self._cut_rects:
                    self._cut_rects = tb
                    for o in self.overlays + self.top_overlays:
                        o.cut_rects = tb
            for i, o in enumerate(self.overlays):
                if i not in self._paused_monitors and o.isVisible():
                    o.fix_native()
        except Exception:
            self._fail("Z-order 유지")

    def _fail(self, what: str):
        self._errors += 1
        log.exception("눈 엔진 오류 (%s) %d/%d", what, self._errors, MAX_ERRORS)
        if self._errors >= MAX_ERRORS:
            log.error("오류가 반복되어 눈 엔진을 중지합니다 (프로그램은 계속 실행됩니다)")
            self._apply_enabled()

    # ------------------------------------------------------------------ 사용자 동작
    def clear_piles(self):
        self.sim.clear_piles()

    def reset(self):
        self.sim.reset()
        self._errors = 0
        self._apply_enabled()
