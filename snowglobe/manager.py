"""스노우볼 매니저: 여러 스노우볼을 각각 독립된 상태 / 물리 / 위젯으로 관리하고, 저장 · 복원한다.

- 스노우볼마다 GlobePhysics 가 따로 있어 한 개를 흔들어도 다른 것에는 영향이 없다.
- 물리(step)와 렌더링(render)은 분리: 움직임이 있는 스노우볼만 계산·그린다. 숨김/화면 밖/모두 가라앉은 것은 건너뜀.
- 데스크톱 전체 눈 엔진(snow/)과는 코드도 입자도 공유하지 않는다.
"""
from __future__ import annotations

import random

from PySide6.QtCore import QElapsedTimer, QObject, QRect, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from core.logger import get_logger
from decor.layer import show_layered

from . import catalog as C
from . import model as M
from .physics import GlobePhysics
from .render import GlobeRenderer
from .store import MAX_GLOBES, SnowGlobeStore
from .widget import GlobeWidget

log = get_logger("snowglobe")
TOP_KEYS = ("name", "design", "background", "size", "shake_mode", "shake_strength", "position_locked", "auto_shake", "auto_shake_sec", "visible", "x", "y")
SNOW_KEYS = ("normal", "big", "sparkle", "amount", "size", "speed")


def _screens_union() -> QRect:
    r = QRect()
    for sc in QGuiApplication.screens():
        r = r.united(sc.availableGeometry())
    return r if not r.isNull() else QRect(0, 0, 1280, 720)


class GlobeManager(QObject):
    changed = Signal()              # 목록 / 선택 / 구조 변경
    globe_changed = Signal(str)     # 한 스노우볼의 설정이 바뀜
    frame_ready = Signal(str)       # 새 프레임이 그려짐 (UI 미리보기용)
    open_requested = Signal(str)    # 바탕화면 위젯 메뉴에서 '설정 / 꾸미기' 선택
    save_failed = Signal()          # 저장 실패 (UI 알림용)

    def __init__(self, store: SnowGlobeStore | None = None, parent=None):
        super().__init__(parent)
        self.store = store or SnowGlobeStore()
        self.globes: dict[str, dict] = {}
        self.order: list[str] = []
        self.selected: str | None = None
        self.phys: dict[str, GlobePhysics] = {}
        self.widgets: dict[str, GlobeWidget] = {}
        self.frames: dict = {}
        self.renderer = GlobeRenderer()
        self._preview: set[str] = set()
        self._dirty: set[str] = set()
        self._ext: dict[str, tuple] = {}        # UI 미리보기에서 직접 흔든 가속도(다음 틱에 반영)
        self._clock = QElapsedTimer()
        self._auto_clock: dict[str, float] = {}      # 스노우볼별 다음 자동 흔들기까지 남은 시간(초)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(700)
        self._save_timer.timeout.connect(self.save_now)

    # ------------------------------------------------------------ 수명
    def start(self):
        data = self.store.load()
        for g in data["globes"]:
            self._register(g)
        self.selected = data["selected"] if data["selected"] in self.globes else (self.order[0] if self.order else None)
        for gid in self.order:
            if self.globes[gid]["visible"]:
                self._make_widget(gid)
        self._clock.start()
        self._timer.start()
        self.changed.emit()

    def shutdown(self):
        self._timer.stop()
        self._save_timer.stop()
        self.save_now()
        for w in self.widgets.values():
            w.close()
            w.deleteLater()
        self.widgets.clear()

    def save_now(self) -> bool:
        ok = self.store.save([self.globes[i] for i in self.order], self.selected)
        if not ok:
            log.warning("스노우볼 저장에 실패했습니다 (기존 파일은 보존됨)")
            self.save_failed.emit()
        return ok

    def _schedule_save(self):
        self._save_timer.start()

    # ------------------------------------------------------------ 조회
    def get(self, gid: str) -> dict:
        return self.globes[gid]

    def frame(self, gid: str):
        return self.frames.get(gid)

    def physics(self, gid: str) -> GlobePhysics | None:
        return self.phys.get(gid)

    def count(self) -> int:
        return len(self.order)

    def set_preview(self, gid: str, on: bool):
        """UI 안에서 미리보기 중인 스노우볼은 바탕화면 위젯이 숨겨져도 물리를 돌린다."""
        (self._preview.add if on else self._preview.discard)(gid)
        if on:
            self._dirty.add(gid)

    # ------------------------------------------------------------ 등록 / 위젯
    def _register(self, g: dict):
        self.globes[g["id"]] = g
        self.order.append(g["id"])
        self.phys[g["id"]] = GlobePhysics(g["snow"], g["decor"])
        self.phys[g["id"]].shake_strength = g.get("shake_strength", 1.0)
        self._render(g["id"])

    def _clamp(self, x: int, y: int, w: int, h: int):
        a = _screens_union()
        return (max(a.left() - w + 24, min(a.right() - 24, x)), max(a.top() - h + 24, min(a.bottom() - 24, y)))

    def _make_widget(self, gid: str):
        if gid in self.widgets:
            return
        g = self.globes[gid]
        w = GlobeWidget(self, gid)
        g["x"], g["y"] = self._clamp(g["x"], g["y"], w.width(), w.height())
        w.move(g["x"], g["y"])
        w.selected = gid == self.selected
        self.widgets[gid] = w
        if gid in self.frames:
            w.set_frame(self.frames[gid], self.phys[gid].jolt)
        show_layered(w)

    def _drop_widget(self, gid: str):
        w = self.widgets.pop(gid, None)
        if w is not None:
            w.close()
            w.deleteLater()

    # ------------------------------------------------------------ 스노우볼 관리
    def add_globe(self, design: str | None = None, background: str | None = None) -> str | None:
        if len(self.order) >= MAX_GLOBES:
            return None
        a = _screens_union()
        n = len(self.order)
        g = M.new_globe(a.center().x() - C.GW + (n % 6) * 36, a.center().y() - C.GH + (n % 6) * 30,
                        design if design in C.DESIGNS else C.DEFAULT_DESIGN,
                        background if background in C.BACKGROUNDS else C.DEFAULT_BACKGROUND)
        self._register(g)
        self._make_widget(g["id"])
        self.select(g["id"])
        self._schedule_save()
        self.changed.emit()
        return g["id"]

    def duplicate(self, gid: str) -> str | None:
        if gid not in self.globes or len(self.order) >= MAX_GLOBES:
            return None
        g = M.clone_globe(self.globes[gid])
        self._register(g)
        if g["visible"]:
            self._make_widget(g["id"])
        self.select(g["id"])
        self._schedule_save()
        self.changed.emit()
        return g["id"]

    def remove(self, gid: str):
        if gid not in self.globes:
            return
        self._drop_widget(gid)
        for d in (self.globes, self.phys, self.frames):
            d.pop(gid, None)
        self._preview.discard(gid)
        self._dirty.discard(gid)
        self._ext.pop(gid, None)
        self.order.remove(gid)
        if self.selected == gid:
            self.selected = self.order[-1] if self.order else None
        for i, w in self.widgets.items():
            w.selected = i == self.selected
            w.update()
        self._schedule_save()
        self.changed.emit()

    def select(self, gid: str | None):
        if gid is not None and gid not in self.globes:
            return
        if gid == self.selected:
            return
        self.selected = gid
        for i, w in self.widgets.items():
            w.selected = i == gid
            w.update()
        self._schedule_save()
        self.changed.emit()

    def update(self, gid: str, **kw):
        """외형 / 배경 / 크기 / 이름 / 흔들기 방식 / 표시 / 위치."""
        g = self.globes.get(gid)
        if g is None:
            return
        kw = {k: v for k, v in kw.items() if k in TOP_KEYS}
        new = M.clean_globe({**g, **kw})
        old_vis, old_size = g["visible"], g["size"]
        g.update({k: new[k] for k in TOP_KEYS})
        self.phys[gid].shake_strength = g["shake_strength"]
        w = self.widgets.get(gid)
        if g["visible"] and w is None:
            self._make_widget(gid)
            w = self.widgets.get(gid)
        elif not g["visible"] and w is not None:
            self._drop_widget(gid)
            w = None
        if w is not None:
            if g["size"] != old_size:
                w.apply_size()
                g["x"], g["y"] = self._clamp(g["x"], g["y"], w.width(), w.height())
            if (w.x(), w.y()) != (g["x"], g["y"]):
                w.move(g["x"], g["y"])
        self._dirty.add(gid)
        self._schedule_save()
        self.globe_changed.emit(gid)
        if g["visible"] != old_vis:
            self.changed.emit()

    def resize_step(self, gid: str, step: int):
        g = self.globes.get(gid)
        if g:
            self.update(gid, size=g["size"] + step)

    def moved(self, gid: str, x: int, y: int):
        g = self.globes.get(gid)
        if g:
            g["x"], g["y"] = int(x), int(y)
            self._schedule_save()
            self.globe_changed.emit(gid)

    # ------------------------------------------------------------ 눈 설정 (스노우볼별 독립)
    def set_snow(self, gid: str, **kw):
        g = self.globes.get(gid)
        if g is None:
            return
        snow = dict(g["snow"])
        for k, v in kw.items():
            if k in C.SNOW_KINDS:
                M.set_ratio(snow, k, v)            # 세 비율의 합계는 항상 100
            elif k in SNOW_KEYS:
                snow[k] = v
        g["snow"] = M.clean_snow(snow)
        self.phys[gid].configure(g["snow"])
        self._dirty.add(gid)
        self._schedule_save()
        self.globe_changed.emit(gid)

    # ------------------------------------------------------------ 장식 (2D 좌표만)
    def decor_items(self, gid: str) -> list:
        return self.globes[gid]["decor"]

    def _decor_changed(self, gid: str, save: bool = True):
        self.phys[gid].set_decor(self.globes[gid]["decor"])
        self._dirty.add(gid)
        if save:
            self._schedule_save()
        self.globe_changed.emit(gid)

    def add_decor(self, gid: str, kind: str, x: float = C.GX, y: float = C.GY) -> str | None:
        g = self.globes.get(gid)
        if g is None or kind not in C.DECOR or len(g["decor"]) >= C.MAX_DECOR:
            return None
        it = M.new_item(kind, x, y)
        g["decor"].append(it)
        self._decor_changed(gid)
        return it["id"]

    def update_decor(self, gid: str, iid: str, **kw):
        """x, y, scale, rot 변경. 항상 배치 가능 영역(바닥 타원 + 유리 안쪽)으로 보정된다."""
        g = self.globes.get(gid)
        if g is None:
            return
        for it in g["decor"]:
            if it["id"] == iid:
                for k in ("x", "y", "scale", "rot"):
                    if k in kw:
                        it[k] = kw[k]
                M.fit_item(it)
                self._decor_changed(gid)
                return

    def remove_decor(self, gid: str, iid: str):
        g = self.globes.get(gid)
        if g is None:
            return
        g["decor"] = [it for it in g["decor"] if it["id"] != iid]
        self._decor_changed(gid)

    def duplicate_decor(self, gid: str, iid: str) -> str | None:
        g = self.globes.get(gid)
        if g is None or len(g["decor"]) >= C.MAX_DECOR:
            return None
        for it in g["decor"]:
            if it["id"] == iid:
                c = M.new_item(it["kind"], it["x"] + 5, it["y"] + 2, it["scale"], it["rot"])
                g["decor"].append(c)
                self._decor_changed(gid)
                return c["id"]
        return None

    def hit_decor(self, gid: str, x: float, y: float) -> str | None:
        """논리 좌표 (x, y) 에 있는 장식 id (앞쪽 = Y 가 큰 것 우선)."""
        for it in sorted(self.globes[gid]["decor"], key=lambda i: -i["y"]):
            x0, x1, y0, y1 = M.item_extent(it["kind"], it["scale"], it["rot"])
            if it["x"] + x0 - 1 <= x <= it["x"] + x1 + 1 and it["y"] + y0 - 1 <= y <= it["y"] + y1 + 1:
                return it["id"]
        return None

    # ------------------------------------------------------------ 흔들기
    def shake(self, gid: str) -> bool:
        ph = self.phys.get(gid)
        if ph is None:
            return False
        ok = ph.auto_shake()
        if ok:
            self._dirty.add(gid)
        return ok

    def apply_accel(self, gid: str, ax: float, ay: float):
        """UI 미리보기에서 마우스로 직접 흔들 때의 가속도 (논리 px/s^2). 흔들기 방식이 '클릭만' 이면 무시."""
        if gid in self.globes and self.globes[gid]["shake_mode"] in ("both", "drag"):
            ox, oy = self._ext.get(gid, (0.0, 0.0))
            self._ext[gid] = (ox + ax, oy + ay)

    def click(self, gid: str):
        """가볍게 클릭: 흔들기 방식이 '클릭' 을 허용할 때만 자동 흔들기."""
        if self.globes[gid]["shake_mode"] in ("both", "click"):
            self.shake(gid)

    def _auto_shake_due(self, gid: str, dt: float) -> bool:
        """자동 흔들기 옵션이 켜져 있을 때, 정한 간격마다 흔들 때가 됐는지."""
        g = self.globes[gid]
        if not g.get("auto_shake", True):
            self._auto_clock.pop(gid, None)
            return False
        sec = float(g.get("auto_shake_sec", C.AUTO_SHAKE_DEFAULT_SEC))
        t = self._auto_clock.get(gid)
        if t is None:                                    # 처음엔 스노우볼마다 다른 시점에서 시작
            t = sec * (0.3 + 0.7 * random.random())
        t -= dt
        if t > 0:
            self._auto_clock[gid] = min(t, sec)          # 간격을 줄이면 바로 반영
            return False
        self._auto_clock[gid] = sec
        return True

    # ------------------------------------------------------------ 루프: 물리 -> 렌더링 분리
    def _render(self, gid: str):
        ph = self.phys[gid]
        img = self.renderer.render(self.globes[gid], ph.snapshot())
        self.frames[gid] = img
        w = self.widgets.get(gid)
        if w is not None:
            w.set_frame(img, ph.jolt)
        self.frame_ready.emit(gid)

    def _tick(self):
        dt = min(0.05, self._clock.restart() / 1000.0)
        if dt <= 0:
            return
        area = _screens_union()
        for gid in self.order:
            w = self.widgets.get(gid)
            watched = gid in self._preview
            if not watched and (w is None or not w.isVisible() or not area.intersects(w.frameGeometry())):
                continue                                   # 보이지 않는 스노우볼은 계산하지 않음
            g, ph = self.globes[gid], self.phys[gid]
            ax, ay = self._ext.pop(gid, (0.0, 0.0))
            if self._auto_shake_due(gid, dt) and not (w is not None and w._holding):
                self.shake(gid)
            if w is not None:
                wx, wy = w.sample_accel(dt)
                if g["shake_mode"] != "click":
                    ax, ay = ax + wx, ay + wy
            if ph.idle and ax == 0.0 and ay == 0.0 and gid not in self._dirty:
                continue                                   # 모두 가라앉음: 물리도 렌더링도 생략
            ph.step(dt, ax, ay)
            self._dirty.discard(gid)
            self._render(gid)
