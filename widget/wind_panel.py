"""바람 조절 패널(다이얼 + 수치 + 무풍 버튼)과 이것만 들어 있는 작은 독립 창."""
from __future__ import annotations
from core.i18n import tr


from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .pixel_ui import PAL, PX, PixelButton, PixelWindow, body_font
from .wind_dial import WindDial, direction_name


class WindPanel(QWidget):
    """설정 탭과 작은 바람 창이 같은 모양으로 공유한다. 값은 settings 와 항상 동기화된다."""

    def __init__(self, settings, compact: bool = False, parent=None):
        super().__init__(parent)
        self.s = settings
        self.dial = WindDial(unit=3, crop=3) if compact else WindDial(unit=4)   # 작은 창: 다이얼 바깥 빈 여백만 잘라 높이 확보
        self.dial.changed.connect(self._dial_changed)
        self.dial.released.connect(lambda: self.s.save_now())        # 바람 설정 자동 저장

        self.lbl_dir = QLabel()
        self.lbl_spd = QLabel()
        for lb, col in ((self.lbl_dir, PAL["gold"]), (self.lbl_spd, PAL["sky"])):
            lb.setFont(body_font())
            lb.setStyleSheet(f"color:{col};")
        if compact:                      # 창 크기는 그대로, 글자 줄이 눌려 잘리지 않도록 줄 높이를 고정
            lh = max(QFontMetrics(body_font()).height(), 13 * PX) + PX
            for lb in (self.lbl_dir, self.lbl_spd):
                lb.setFixedHeight(lh)
                lb.setAlignment(Qt.AlignCenter)
        calm = PixelButton(tr("무풍"), "wind")
        calm.clicked.connect(self._calm)

        if compact:
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(PX)
            lay.addWidget(self.dial, 0, Qt.AlignHCenter)
            lay.addWidget(self.lbl_dir, 0, Qt.AlignHCenter)
            lay.addWidget(self.lbl_spd, 0, Qt.AlignHCenter)
            lay.addWidget(calm, 0, Qt.AlignHCenter)
        else:
            lay = QHBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6 * PX)
            lay.addWidget(self.dial)
            col = QVBoxLayout()
            col.setSpacing(4 * PX)
            col.addWidget(self.lbl_dir)
            col.addWidget(self.lbl_spd)
            hint = QLabel(tr("화살표 끝을 끌어서\n방향을 돌리고\n길이로 풍속을\n정합니다.\n\n0도 북쪽, 90도 동쪽\n180도 남쪽, 270도 서쪽"))
            hint.setFont(body_font())
            hint.setStyleSheet(f"color:{PAL['dim']};")
            col.addWidget(hint)
            col.addWidget(calm)
            col.addStretch(1)
            lay.addLayout(col, 1)

        settings.changed.connect(self._on_setting)
        if getattr(settings, "auto", None) is not None:
            settings.auto.state_changed.connect(self.refresh)     # 자동 날씨가 바람을 조정 중이면 다이얼도 따라 움직임
        self.refresh()

    def _dial_changed(self, angle: int, pct: int):
        self.s.set("wind.direction", angle)
        self.s.set("wind.strength", pct)
        self._labels(angle, pct)

    def _calm(self):
        self.s.set("wind.strength", 0, save=True)

    def _labels(self, angle, pct):
        self.lbl_dir.setText(tr("방향 {0}도 ({1})").format(angle, direction_name(angle)))
        self.lbl_spd.setText(tr("풍속 0% (무풍)") if pct == 0 else tr("풍속 {0}%").format(pct))

    def _on_setting(self, key: str):
        if key in ("*", "wind.direction", "wind.strength"):
            self.refresh()

    def refresh(self):
        angle, pct = int(self.s.effective("wind.direction")), int(self.s.effective("wind.strength"))
        if not self.dial._down:
            self.dial.set_wind(angle, pct)
        self._labels(angle, pct)


class WindWindow(PixelWindow):
    """바람 방향/세기만 조절하는 작은 창. 다른 창 위에 떠 있어 눈을 보면서 바로 조절할 수 있다."""

    def __init__(self, settings, parent=None):
        super().__init__(tr("바람"), "wind", parent)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setFixedSize(CANVAS_W, CANVAS_H)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(4 * PX, PX, 4 * PX, PX)
        self.panel = WindPanel(settings, compact=True)
        lay.addWidget(self.panel)


CANVAS_W = 250
CANVAS_H = 365
