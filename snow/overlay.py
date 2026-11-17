"""모니터별 전체화면 투명 눈 오버레이 창 (마우스 입력 통과)."""
from __future__ import annotations
from core.i18n import tr


import math
import time

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QWidget

from core.logger import get_logger
from . import winapi

log = get_logger("overlay")

ALPHAS = (150, 215, 255)
PILE_BODY = QColor(230, 240, 249)
PILE_TOP = QColor(255, 255, 255)
PILE_BASE = QColor(196, 218, 238)

FIT_ENABLED = True      # False: 예전처럼 장식 오버레이 창을 모니터 전체 크기로 연다 (문제가 생겼을 때 되돌리는 스위치)
FIT_PAD = 48            # top 오버레이 창을 장식 영역보다 이만큼(물리 px) 넉넉하게 연다 (조금 움직일 때마다 창 크기를 바꾸지 않으려고)
FIT_KEEP = 3.0          # 지금 창이 필요한 영역을 덮고 있으면서 면적이 이 배수 이내면 그대로 쓴다

_SPRITES: dict = {}
_SHAPES = {
    (1, 0): [(0, 0)],
    (2, 0): [(0, 0), (1, 0), (0, 1), (1, 1)],
    (3, 0): [(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)],
    (3, 1): [(0, 0), (2, 0), (1, 1), (0, 2), (2, 2)],
    (4, 0): [(2, 0), (2, 1), (0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (2, 3), (2, 4)],
    (4, 1): [(0, 0), (4, 0), (1, 1), (3, 1), (2, 2), (1, 3), (3, 3), (0, 4), (4, 4)],
}
_SIZE = {1: 1, 2: 2, 3: 3, 4: 5}


def flake_pixmap(tier: int, state: int, unit: int, alpha_idx: int) -> QPixmap:
    key = (tier, state, unit, alpha_idx)
    pm = _SPRITES.get(key)
    if pm is None:
        n = _SIZE[tier]
        pm = QPixmap(n * unit, n * unit)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        col = QColor(255, 255, 255, ALPHAS[alpha_idx])
        for (cx, cy) in _SHAPES[(tier, state if tier >= 3 else 0)]:
            p.fillRect(cx * unit, cy * unit, unit, unit, col)
        p.end()
        _SPRITES[key] = pm
    return pm


class SnowOverlay(QWidget):
    """모니터별 눈 오버레이.

    top=False: 일반 창 바로 뒤(바탕화면 위)에 깔리는 기본 오버레이.
    top=True : 장식 창(전구·장식·시계·스노우볼) 위에만 눈을 덧그리는 오버레이. 항상 위에 있지만 보이는 범위(decor_rects)가
               '다른 창에 가려지지 않은 장식 창 부분' 으로 제한되어 일반 창 위에는 눈이 그려지지 않는다.
    cut_rects: 눈을 그리지 않을 물리 픽셀 사각형 (작업표시줄). 모니터 바닥선(작업표시줄 윗선) 아래도 항상 비운다.
    """

    cache_hits = 0       # 렉 진단용: 눈더미 캐시를 그대로 쓴 횟수 / 새로 그린 횟수 (진단 로그를 남길 때마다 0 으로 되돌린다)
    cache_builds = 0
    last_paint_ms = 0.0

    def __init__(self, screen, sim, top: bool = False):
        super().__init__(None)
        self.sim = sim
        self.qscreen = screen
        self.top = bool(top)
        self.native_rect = None          # 물리 픽셀 (l, t, r, b), 엔진이 지정
        self.cut_rects: list = []
        self.decor_rects: list = []      # top=True 일 때: 눈을 그릴 물리 픽셀 사각형들
        self._mask_sig = None
        self._fit = None                 # top 오버레이: 지금 열어 둔 창의 물리 사각형 (장식이 보이는 영역 크기). None 이면 native_rect 전체
        self._mask_region = None         # top 오버레이: 창 모양(mask)과 같은 논리 좌표 영역 (부분 다시 그리기/지우기용)
        self._full_clear = True          # True: 다음 paint 에서 창 전체를 지운다 (처음/크기 변경/보이는 영역 변경 직후 잔상 방지)
        self._clip_sig = None
        self._clip_region = None
        self.label = "top" if self.top else "base"     # 진단 로그에 찍는 이름 (엔진이 모니터 번호를 붙인다)
        self._req_t = None                             # 진단: 다시 그리기를 요청한 시각
        self._last_start = 0.0                         # 진단: 직전 paint 시작 시각
        self._drawn = 0                                # 진단: 이번 paint 에서 그린 눈송이 수
        self.reset_stat()
        flags = (Qt.FramelessWindowHint | Qt.Tool
                 | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        if self.top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowTitle("CW Snow Overlay")
        self.setScreen(screen)
        self.setGeometry(screen.geometry())

    def present(self):
        self.show()
        self.fix_native()

    def hwnd(self) -> int:
        return int(self.winId())

    def fix_native(self):
        """Windows: 클릭 통과·항상 맨 아래 스타일 적용 및 모니터 물리 사각형으로 위치 보정."""
        if not winapi.IS_WINDOWS:
            return
        hwnd = self.hwnd()
        if self.top:
            winapi.make_top_overlay(hwnd)
        else:
            winapi.make_overlay_window(hwnd)
        want = self._target_rect()
        if want:
            cur = winapi.window_rect(hwnd)
            if cur != tuple(want):
                winapi.set_window_rect(hwnd, want, top=self.top)

    def _target_rect(self):
        """창이 실제로 차지해야 할 물리 사각형. top 오버레이는 장식이 보이는 영역 크기, 그 외에는 native_rect."""
        if self.top and self._fit:
            return self._fit
        return self.native_rect

    def _plan_fit(self, rects):
        """장식이 보이는 사각형들을 덮는 최소 창 크기를 정한다 (native_rect 안으로 제한). 지금 창이 충분하면 바꾸지 않는다."""
        lim = self.native_rect
        if not FIT_ENABLED and lim:
            return tuple(lim)
        l = min(r[0] for r in rects)
        t = min(r[1] for r in rects)
        r_ = max(r[2] for r in rects)
        b = max(r[3] for r in rects)
        if lim:
            l, t, r_, b = max(l, lim[0]), max(t, lim[1]), min(r_, lim[2]), min(b, lim[3])
        need = (l, t, r_, b)
        cur = self._fit
        area = lambda q: max(1, q[2] - q[0]) * max(1, q[3] - q[1])
        if cur and cur[0] <= l - 2 and cur[1] <= t - 2 and cur[2] >= r_ + 2 and cur[3] >= b + 2 \
                and area(cur) <= FIT_KEEP * area(need) + 400 * 400:
            return cur
        new = (l - FIT_PAD, t - FIT_PAD, r_ + FIT_PAD, b + FIT_PAD)
        if lim:
            new = (max(new[0], lim[0]), max(new[1], lim[1]), min(new[2], lim[2]), min(new[3], lim[3]))
        return new

    def set_decor_rects(self, rects: list):
        """top 오버레이: 눈을 그릴 물리 픽셀 사각형을 바꾼다. 달라졌을 때만 창 모양(mask)을 갱신하고, 비면 창을 숨긴다."""
        rects = [tuple(r) for r in rects]
        if not rects and self.decor_rects and getattr(self, "_empty_n", 0) < 12:
            self._empty_n = getattr(self, "_empty_n", 0) + 1      # 잠깐 비는 것은 무시 (창이 숨었다 나타날 때 깜빡임 방지)
            return
        self._empty_n = 0
        sig = tuple(rects)
        if sig == self._mask_sig:
            return
        self._mask_sig = sig
        self.decor_rects = rects
        self._full_clear = True
        if not rects:
            self._mask_region = None
            self.clearMask()
            if self.isVisible():
                self.hide()
            return
        fit = self._plan_fit(rects)
        if fit != self._fit:
            self._fit = fit
            if winapi.IS_WINDOWS:
                cur = winapi.window_rect(self.hwnd())
                if cur != tuple(fit):
                    winapi.set_window_rect(self.hwnd(), fit, top=True)      # 창 크기/위치만 바꾼다 (Z-order 는 그대로)
        self._apply_mask()
        if not self.isVisible():
            self.present()

    def _apply_mask(self):
        """창 모양(mask)을 장식이 보이는 부분으로 맞춘다. 창 크기가 아직 Qt 에 반영되기 전이면 건너뛴다 (resizeEvent 가 다시 부른다)."""
        rects = self.decor_rects
        if not rects:
            return
        pl, pt, pr, pb = self.phys_rect()
        pw, ph = max(1, pr - pl), max(1, pb - pt)
        sx, sy = self.width() / pw, self.height() / ph
        dpr = self.devicePixelRatioF() or 1.0
        if winapi.IS_WINDOWS and (abs(self.width() - pw / dpr) > 2.5 or abs(self.height() - ph / dpr) > 2.5):
            return
        region = QRegion()
        for (l, t, r, b) in rects:
            x0, y0 = int((l - pl) * sx) - 1, int((t - pt) * sy) - 1
            x1, y1 = int((r - pl) * sx) + 2, int((b - pt) * sy) + 2
            region = region.united(QRegion(QRect(x0, y0, x1 - x0, y1 - y0)))
        self.setMask(region)
        self._mask_region = region
        self._full_clear = True

    def reset_stat(self):
        """진단 통계를 비운다 (엔진이 요약 로그를 남길 때마다 호출)."""
        self.stat = {"n": 0, "sum_ms": 0.0, "max_ms": 0.0, "sum_wait": 0.0, "max_wait": 0.0,
                     "sum_int": 0.0, "n_int": 0, "flakes": 0, "size": "?", "hits": 0, "builds": 0}

    def _note_paint(self, t0: float, t_end: float, pw: int, ph: int):
        st = self.stat
        ms = (t_end - t0) * 1000.0
        st["n"] += 1
        st["sum_ms"] += ms
        st["max_ms"] = max(st["max_ms"], ms)
        if self._req_t is not None:
            w = (t0 - self._req_t) * 1000.0
            st["sum_wait"] += w
            st["max_wait"] = max(st["max_wait"], w)
            self._req_t = None
        if self._last_start:
            st["sum_int"] += (t0 - self._last_start) * 1000.0
            st["n_int"] += 1
        self._last_start = t0
        st["flakes"] += self._drawn
        st["size"] = "%dx%d" % (pw, ph)

    def request_paint(self):
        """다시 그리기를 요청한다. top 오버레이는 보이는 영역(장식 창 부분)만 더럽혀서 합성/복사 범위를 줄인다."""
        if self._req_t is None:
            self._req_t = time.perf_counter()
        if self.top and self._mask_region is not None and not self._full_clear:
            self.update(self._mask_region)
        else:
            self.update()

    def resizeEvent(self, e):
        self._full_clear = True
        super().resizeEvent(e)
        if self.top and self.decor_rects:
            self._apply_mask()                  # 창 크기가 실제로 바뀐 뒤 mask 를 다시 맞춘다

    def showEvent(self, e):
        self._full_clear = True
        super().showEvent(e)

    def phys_rect(self):
        """이 오버레이가 실제로 덮는 물리 픽셀 사각형."""
        if winapi.IS_WINDOWS:
            r = winapi.window_rect(self.hwnd())
            if r:
                return r
        g = self.geometry()
        dpr = self.devicePixelRatioF()
        return (round(g.x() * dpr), round(g.y() * dpr),
                round((g.x() + g.width()) * dpr), round((g.y() + g.height()) * dpr))

    # ------------------------------------------------------------------ 그리기
    def paintEvent(self, e):
        t0 = time.perf_counter()
        self._drawn = 0
        pw = ph = 0
        p = QPainter(self)
        try:
            pl, pt, pr, pb = self.phys_rect()
            pw, ph = max(1, pr - pl), max(1, pb - pt)
            p.setCompositionMode(QPainter.CompositionMode_Source)
            if self.top and self._mask_region is not None and not self._full_clear:
                p.setClipRegion(self._mask_region)             # 보이는 영역 밖은 어차피 안 보이므로 그 안만 지운다
                p.fillRect(self.rect(), Qt.transparent)
                p.setClipping(False)
            else:
                p.fillRect(self.rect(), Qt.transparent)
                self._full_clear = False
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.scale(self.width() / pw, self.height() / ph)      # 논리 -> 물리 픽셀
            p.translate(-pl, -pt)                               # 전역 물리 좌표 사용
            if self.top:
                if not self.decor_rects:
                    return
                sig = self._mask_sig
                if sig != self._clip_sig or self._clip_region is None:
                    clip = QRegion()
                    for (l, t, r, b) in self.decor_rects:
                        clip = clip.united(QRegion(QRect(l, t, r - l, b - t)))
                    self._clip_sig, self._clip_region = sig, clip
                clip = self._clip_region
                p.setClipRegion(clip)                           # 장식 창이 보이는 부분에만 그린다
            self._paint_piles(p, pl, pt, pr, pb)
            self._paint_bodies(p, pl, pt, pr, pb)
            t1 = time.perf_counter()
            self._paint_flakes(p, pl, pt, pr, pb)
            self._erase_cuts(p, pl, pt, pr, pb)
            self.perf_ms = {"piles+bodies": (t1 - t0) * 1000.0, "flakes": (time.perf_counter() - t1) * 1000.0}
        finally:
            p.end()
            self.last_paint_ms = (time.perf_counter() - t0) * 1000.0
            self.last_paint_end = time.perf_counter()
            self._note_paint(t0, self.last_paint_end, pw, ph)

    def _erase_cuts(self, p, pl, pt, pr, pb):
        """작업표시줄 영역(바닥선 아래 + 작업표시줄 창 사각형)에 그려진 눈을 지운다: 눈은 작업표시줄 위쪽에만 보인다."""
        p.setClipping(False)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        floor = self.sim.floor_at((pl + pr) / 2)
        if floor < pb:
            p.fillRect(pl, int(floor), pr - pl, pb - int(floor) + 1, Qt.transparent)
        lim = int(floor)
        for (l, t, r, b) in self.cut_rects:
            t = max(t, lim)                       # 작업표시줄 창 사각형이 일시적으로 커져도 윗선 위의 눈은 지우지 않는다
            if r > pl and l < pr and b > pt and t < pb and b > t:
                p.fillRect(l, t, r - l, b - t, Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)

    def _paint_bodies(self, p, pl, pt, pr, pb):
        """눈덩이/눈사람 (snowman.world) 을 눈 더미 위, 눈송이 아래에 그린다."""
        world = getattr(self.sim, "bodies", None)
        if world is None or not getattr(world, "visible", True) or not (world.snowmen or world.balls or world.props):
            return
        try:
            from snowman.render import paint_world
            p.save()
            paint_world(p, world, pl, pt, pr, pb)
        except Exception:
            if not getattr(self, "_body_err", False):
                self._body_err = True
                from core.logger import get_logger
                get_logger("snow").exception(tr("눈사람 그리기 오류"))
        finally:
            try:
                p.restore()
            except Exception:
                pass

    def _paint_flakes(self, p, pl, pt, pr, pb):
        sim = self.sim
        unit = max(1, round(sim.cell * sim.size))
        draw = p.drawPixmap
        only = self.decor_rects if self.top else None
        x_lo, x_hi, y_lo, y_hi = pl - 40, pr, pt - 40, pb
        sprites = _SPRITES
        drawn = 0
        for f in sim.flakes:
            x, y = f.x, f.y
            if x < x_lo or x > x_hi or y < y_lo or y > y_hi:
                continue
            if only is not None:
                for (l, t, r, b) in only:
                    if l - 40 <= x <= r and t - 40 <= y <= b:
                        break
                else:
                    continue
            state = 0 if (f.angle % 3.1416) < 1.5708 else 1
            pm = sprites.get((f.tier, state, unit, f.alpha))
            if pm is None:
                pm = flake_pixmap(f.tier, state, unit, f.alpha)
            draw(int(x) // unit * unit, int(y) // unit * unit, pm)     # 픽셀 격자에 정렬
            drawn += 1
        self._drawn = drawn
        # 이동 중인 눈 덩어리 (질량이 보존된 눈): 질량의 제곱근에 비례한 크기의 눈뭉치. 화면 밖의 눈도 지우지 않고 계속 계산만 한다
        cell = sim.cell
        for f in sim.parcels:
            x, y = f.x, f.y
            if x < pl - 60 or x > pr + 60 or y < pt - 400 or y > pb + 40:
                continue
            if only is not None and not any(l - 60 <= x <= r + 60 and t - 400 <= y <= b + 40
                                            for (l, t, r, b) in only):
                continue
            side = max(cell, min(cell * 14, int(math.sqrt(f.carry) * cell)))
            sx = int(x - side / 2) // cell * cell
            sy = int(y - side) // cell * cell
            p.fillRect(sx, sy, side, side, PILE_BODY)
            p.fillRect(sx, sy, side, cell, PILE_TOP)

    # ------------------------------------------------------------------ 눈더미 (v1.5.0 열 단위 픽셀 블록)
    @staticmethod
    def _draw_pile_runs(fill, pile, base_y, pl, pr):
        """눈더미 한 개를 같은 높이가 이어지는 열끼리 사각형으로 묶어 그린다 (화면 밖 열은 건너뜀, 데이터는 그대로).
        몸체(PILE_BODY) + 윗면 한 셀(PILE_TOP) + 아래 한 셀 그림자(PILE_BASE). 곡선/블러/광택 없음."""
        cell = pile.cell
        cells = pile.cells
        left = pile.left
        for (sa, sb) in pile.draw_segments:
            if sb < pl or sa > pr:
                continue
            i0 = max(0, int((sa - left) // cell), int((pl - left) // cell) - 1)
            i1 = min(len(cells), int((sb - left) // cell) + 1, int((pr - left) // cell) + 2)
            i = i0
            while i < i1:
                h = int(cells[i] + 0.5)
                j = i + 1
                while j < i1 and int(cells[j] + 0.5) == h:
                    j += 1
                if h > 0:
                    x0 = int(left + i * cell)
                    x1 = int(left + j * cell)
                    x0, x1 = max(x0, int(sa)), min(x1, int(sb))
                    if x1 > x0:
                        top = base_y - h * cell
                        fill(x0, top, x1 - x0, h * cell, PILE_BODY)
                        fill(x0, top, x1 - x0, cell, PILE_TOP)
                        if h > 1:
                            fill(x0, base_y - cell, x1 - x0, cell, PILE_BASE)
                i = j

    def _pile_signature(self, pile, pl, pr):
        """눈더미 모양이 바뀌었는지 판단하는 값. cells 는 리스트 비교(C 속도)로 확인한다."""
        return (pile.left, pile.top, pile.cell, pl, pr, tuple(pile.draw_segments), tuple(pile.occluders))

    def _pile_entry(self, key, pile, pl, pt, pr, pb):
        """눈더미를 작은 QPixmap 에 한 번 그려 두고, 모양이 그대로인 동안 재사용한다.
        '모양' = 실제로 그려지는 열 높이(반올림) + 위치/가림. 소수점 이하만 변하는 축적/용해로는 다시 그리지 않는다.
        일반 오버레이와 top 오버레이는 같은 눈더미를 같은 모양으로 그리므로 시뮬레이션 단위로 캐시를 함께 쓴다.
        반환: (pixmap, x, y, region|None) 또는 None(그릴 것 없음)."""
        cache = self.sim.__dict__.setdefault("_pile_px_cache", {})
        ckey = (key, pl, pr)
        ent = cache.get(ckey)
        sig = self._pile_signature(pile, pl, pr)
        cells = pile.cells
        if ent is not None and ent[0] == sig:
            if ent[1] == cells:
                self.cache_hits += 1
                self.stat["hits"] += 1
                return ent[3]
            heights = [int(c + 0.5) for c in cells]
            if ent[2] == heights:                      # 눈높이가 반올림 값으로는 그대로: 그림도 그대로
                ent[1] = list(cells)
                self.cache_hits += 1
                self.stat["hits"] += 1
                return ent[3]
        else:
            heights = [int(c + 0.5) for c in cells]
        self.cache_builds += 1
        self.stat["builds"] += 1
        cell = pile.cell
        peak_px = max(heights) * cell
        base_y = int(pile.top)
        reach = int(peak_px) + cell * 2
        x0 = int(max(pile.left, pl - cell * 2))
        x1 = int(min(pile.right, pr + cell * 2)) + 1
        w, h = x1 - x0, reach + cell
        result = None
        if w > 0 and h > 0 and peak_px > 0:
            pm = QPixmap(w, h)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.translate(-x0, -(base_y - reach))
            self._draw_pile_runs(q.fillRect, pile, base_y, pl, pr)
            q.end()
            region = None
            if pile.occluders:
                region = QRegion(QRect(x0, base_y - reach, w, h))
                for (l, t, r, b) in pile.occluders:
                    region = region.subtracted(QRegion(QRect(l, t, r - l, b - t)))
                if region.isEmpty():
                    pm = None
            if pm is not None:
                result = (pm, x0, base_y - reach, region)
        cache[ckey] = [sig, list(cells), heights, result]
        return result

    def _paint_piles(self, p, pl, pt, pr, pb):
        sim = self.sim
        if sim.accumulate <= 0:
            return
        cache = sim.__dict__.setdefault("_pile_px_cache", {})
        if len(cache) > len(sim.piles) * 2 + 4:              # 사라진 표면/바뀐 모니터 범위의 캐시 정리
            for k in [k for k in cache if k[0] not in sim.piles]:
                del cache[k]
            if len(cache) > len(sim.piles) * 4 + 8:
                cache.clear()
        draw = p.drawPixmap
        for key, pile in sim.piles.items():
            cells = pile.cells
            if not cells:
                continue
            peak_px = max(cells) * pile.cell                # 높이 상한 없음: 실제 눈 높이로 화면 포함 여부 판단
            if pile.top - peak_px - pile.cell > pb or pile.top + 8 < pt:
                continue
            ent = self._pile_entry(key, pile, pl, pt, pr, pb)
            if ent is None:
                continue
            pm, x, y, region = ent
            if region is not None:
                # 이 창보다 위(앞)에 있는 창이 덮는 부분은 눈도 가린다 (합성 지연 시 비침 방지)
                p.save()
                p.setClipRegion(region, Qt.IntersectClip)
                draw(x, y, pm)
                p.restore()
            else:
                draw(x, y, pm)
