"""눈사람 월드 <-> Qt 연결: 눈 엔진 틱/오버레이에 월드를 붙이고, 설정(snowman.*)과 저장/복원을 맡는다.

 - 엔진이 월드를 매 틱 진행시키고(마우스 왼쪽 버튼 읽기, 창 사각형 전달, 장식용 눈사람 머리 표면 등록)
   오버레이가 월드를 그린다. 이 클래스는 그 연결점(attach_world)과 저장만 담당한다.
 - 저장: settings 의 snowman.state (dynamic / decorative 구분 유지). 자동 저장 타이머 + 종료 시 저장.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

from core.logger import get_logger
from .world import SnowmanWorld

log = get_logger("snowman")

SAVE_INTERVAL_MS = 3000


class SnowmanManager(QObject):
    def __init__(self, settings, engine, parent=None):
        super().__init__(parent)
        self.s = settings
        self.engine = engine
        self.world = SnowmanWorld(engine.sim)
        engine.attach_world(self.world)
        self._saved_counter = -1
        self._loading = False
        self._timer = QTimer(self)
        self._timer.setInterval(SAVE_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        settings.changed.connect(self._on_setting)
        self.apply_settings()

    # ------------------------------------------------------------------ 시작/종료
    def start(self):
        """눈 엔진이 시작(화면 경계 확정)된 뒤 호출: 저장된 눈사람을 복원한다."""
        self.load()
        self._timer.start()

    def shutdown(self):
        self._timer.stop()
        self.flush()

    # ------------------------------------------------------------------ 설정
    def apply_settings(self):
        s, w = self.s, self.world
        w.visible = bool(s.get("snowman.enabled"))
        w.mouse_push = bool(s.get("snowman.mouse_push"))
        w.grab_on = bool(s.get("snowman.grab"))
        w.growth = int(s.get("snowman.growth")) / 100.0
        w.push_gain = int(s.get("snowman.push_gain")) / 100.0

    def _on_setting(self, key: str):
        if key == "*":
            self.apply_settings()
            self.load()                      # 설정 초기화/백업 가져오기: 저장된 상태로 다시 구성
        elif key.startswith("snowman.") and key != "snowman.state":
            self.apply_settings()

    # ------------------------------------------------------------------ 저장/복원
    def load(self):
        st = self.s.get("snowman.state") or {}
        self._loading = True
        try:
            self.world.load_state(st.get("items", []), st.get("balls", []), st.get("props", []))
            self._clamp_to_screen()
        except Exception:
            log.exception("눈사람 복원 실패")
        finally:
            self._loading = False
        self._saved_counter = self.world.counter

    def _clamp_to_screen(self):
        """모니터 구성이 바뀌어 화면 밖에 남은 눈사람/눈덩이를 화면 안으로 되돌린다."""
        b = self.engine.sim.bounds
        if b is None or b.width <= 0:
            return
        w = self.world
        for ball in w.balls.values():
            ball.x = min(max(ball.x, b.left + ball.r), b.right - ball.r)
            ball.y = min(max(ball.y, b.top + ball.r), self.engine.sim.floor_at(ball.x) - ball.r)
        for sn in w.snowmen.values():
            if sn.type == "decorative":
                sn.x = min(max(sn.x, b.left), b.right)
                sn.y = min(max(sn.y, b.top + 20), self.engine.sim.floor_at(sn.x) + 10)
        for p in w.props:
            p["x"] = min(max(p["x"], b.left), b.right)
            p["y"] = min(max(p["y"], b.top), self.engine.sim.floor_at(p["x"]))

    def flush(self):
        """월드 상태를 설정에 기록한다 (디스크 저장은 설정의 자동 저장/종료 저장이 처리)."""
        if self._loading:
            return
        try:
            self.s.set("snowman.state", self.world.to_state())
        except Exception:
            log.exception("눈사람 저장 실패")

    def _tick(self):
        w = self.world
        if w._grab is not None:              # 끌고 있는 동안은 쓰지 않는다
            return
        if w.dirty or w.counter != self._saved_counter:
            w.dirty = False
            self._saved_counter = w.counter
            self.flush()
