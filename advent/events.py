"""선물 속 작은 이벤트 위젯: quiz(퀴즈) / wish(소원 쓰기) / catch(떨어지는 것 잡기).
결과는 done(dict) 시그널로 알리며, 저장은 AdventWindow 가 한다."""
from __future__ import annotations
from core.i18n import tr


import math

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from core.fonts import pixel_font
from widget.pixel_ui import PAL, PX, PixelButton, draw_ink_centered, pixel_box
from widget.sprites import sprite_pixmap
from .fx import CatchGame

GOLD_LABEL = f"color:{PAL['gold']};"
LINE_STYLE = (f"QLineEdit{{background:{PAL['panel_lo']};color:{PAL['text']};border:{PX}px solid {PAL['border_dark']};"
              f"padding:{3 * PX}px {4 * PX}px;selection-background-color:{PAL['gold']};selection-color:{PAL['shadow']};}}"
              f"QLineEdit:focus{{border-color:{PAL['border']};}}"
              f"QLineEdit:disabled{{color:{PAL['dim']};}}")
LINE_STYLE_ERR = LINE_STYLE + "QLineEdit{border-color:#ff7a6e;}QLineEdit:focus{border-color:#ff7a6e;}"
WISH_MAX = 60
ITEM_SPRITE = {"star": ("star", None), "snowflake": ("snow", "#ffffff"), "candy": ("candy", "#d63a3a"),
               "bell": ("bell", "#f3c94a"), "gift": ("gift", "#f5ead0")}


def _label(text: str, style: str = "", wrap: bool = True) -> QLabel:
    lb = QLabel(text)
    lb.setWordWrap(wrap)
    if style:
        lb.setStyleSheet(style)
    return lb


# ====================================================================== 퀴즈
class QuizEvent(QWidget):
    done = Signal(dict)

    def __init__(self, spec: dict, prev: dict | None, parent=None):
        super().__init__(parent)
        self.spec = spec
        self._answered = False
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3 * PX)
        v.addWidget(_label(tr("퀴즈  ") + spec["question"], GOLD_LABEL))
        grid = QGridLayout()
        grid.setHorizontalSpacing(3 * PX)
        grid.setVerticalSpacing(3 * PX)
        self.buttons: list[PixelButton] = []
        for i, text in enumerate(spec["choices"]):
            b = PixelButton(text)
            b.clicked.connect(lambda _=False, k=i: self._choose(k))
            self.buttons.append(b)
            grid.addWidget(b, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)
        row = QHBoxLayout()
        self.result = _label("", "", wrap=True)
        row.addWidget(self.result, 1)
        self.retry = PixelButton(tr("다시 풀기"), "reset")
        self.retry.clicked.connect(self._reset)
        self.retry.hide()
        row.addWidget(self.retry)
        v.addLayout(row)
        if prev and prev.get("done") and isinstance(prev.get("choice"), int) and prev["choice"] < len(self.buttons):
            self._show(prev["choice"], emit=False)

    def _choose(self, i: int):
        if not self._answered:
            self._show(i, emit=True)

    def _show(self, i: int, emit: bool):
        self._answered = True
        ok = i == self.spec["answer"]
        for k, b in enumerate(self.buttons):
            b._kind = "accent" if k == self.spec["answer"] else ("danger" if k == i else "normal")
            b.update()
        self.result.setStyleSheet(f"color:{PAL['green'] if ok else '#ff7a6e'};")
        self.result.setText(self.spec["success"] if ok else self.spec["fail"])
        self.retry.show()
        if emit:
            self.done.emit({"done": True, "correct": ok, "choice": i})

    def _reset(self):
        self._answered = False
        for b in self.buttons:
            b._kind = "normal"
            b.update()
        self.result.setText("")
        self.retry.hide()


# ====================================================================== 소원
class WishEvent(QWidget):
    done = Signal(dict)
    wishSent = Signal(str)

    def __init__(self, spec: dict, prev: dict | None, parent=None):
        super().__init__(parent)
        self.spec = spec
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3 * PX)
        v.addWidget(_label(tr("소원  ") + spec["prompt"], GOLD_LABEL))
        row = QHBoxLayout()
        row.setSpacing(3 * PX)
        self.edit = QLineEdit()
        self.edit.setMaxLength(WISH_MAX)
        self.edit.setPlaceholderText(tr("여기에 소원을 적어 주세요 (최대 {0}자)").format(WISH_MAX))
        self.edit.setStyleSheet(LINE_STYLE)
        self.edit.returnPressed.connect(self._send)
        row.addWidget(self.edit, 1)
        self.btn = PixelButton(tr("별에게 보내기"), "star", kind="accent")
        self.btn.clicked.connect(self._send)
        row.addWidget(self.btn)
        v.addLayout(row)
        foot = QHBoxLayout()
        foot.setSpacing(3 * PX)
        self.note = _label("", "")
        foot.addWidget(self.note, 1)
        self.count = _label("", f"color:{PAL['dim']};", wrap=False)          # 글자 수 (남은 칸이 적으면 금색)
        foot.addWidget(self.count)
        v.addLayout(foot)
        self.edit.textChanged.connect(self._on_text)
        self._on_text(self.edit.text())
        if prev and prev.get("done") and isinstance(prev.get("text"), str):
            self._lock(prev["text"])

    def _on_text(self, text: str):
        """글자 수 표시. 글자를 쓰기 시작하면 '적어 주세요' 오류 표시를 지운다."""
        n = len(text)
        self.count.setText(f"{n}/{WISH_MAX}")
        self.count.setStyleSheet(f"color:{PAL['gold'] if n >= WISH_MAX - 10 else PAL['dim']};")
        if n and self.edit.styleSheet() == LINE_STYLE_ERR:
            self.edit.setStyleSheet(LINE_STYLE)
            self.note.setText("")

    def _lock(self, text: str):
        self.edit.setStyleSheet(LINE_STYLE)
        self.edit.setText(text)
        self.edit.setEnabled(False)
        self.btn.setText(tr("다시 쓰기"))
        self.btn.set_icon("reset")
        self.btn._kind = "normal"
        self.btn.update()
        self.note.setStyleSheet(f"color:{PAL['green']};")
        self.note.setText(self.spec["success"])
        self._sent = True

    def _send(self):
        if getattr(self, "_sent", False):              # 다시 쓰기
            self._sent = False
            self.edit.setEnabled(True)
            self.edit.setFocus()
            self.edit.selectAll()
            self.btn.setText(tr("별에게 보내기"))
            self.btn.set_icon("star")
            self.btn._kind = "accent"
            self.btn.update()
            self.note.setText("")
            self._on_text(self.edit.text())
            return
        text = self.edit.text().strip()
        if not text:
            self.note.setStyleSheet("color:#ff7a6e;")
            self.note.setText(tr("소원을 한 줄 적어 주세요."))
            self.edit.setStyleSheet(LINE_STYLE_ERR)                  # 빈 칸을 붉은 테두리로 알리고 바로 쓸 수 있게 함
            self.edit.setFocus()
            return
        self._lock(text)
        self.done.emit({"done": True, "text": text})
        self.wishSent.emit(text)


# ====================================================================== 잡기 게임
class CatchCanvas(QWidget):
    finished = Signal(bool, int)

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.game = CatchGame(600, 100, spec["target"], spec["seconds"])
        self.font = pixel_font(11, 2)
        self.setFixedHeight(54 * PX)
        self.setMinimumWidth(240)
        self.setCursor(Qt.PointingHandCursor)
        self._pops: list[list] = []
        self._msg = tr("시작 버튼을 눌러 주세요")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        name, main = ITEM_SPRITE.get(spec["item"], ("star", None))
        self._pix = sprite_pixmap(name, 3, main=main)

    def start(self):
        self.game.w, self.game.h = max(100, self.width()), self.height()
        self.game.start()
        self._pops.clear()
        self._msg = ""
        self._timer.start(33)

    def _tick(self):
        self.game.step(0.033)
        for p in self._pops:
            p[2] += 0.033
        self._pops = [p for p in self._pops if p[2] < 0.3]
        if self.game.state in ("won", "lost"):
            self._timer.stop()
            self._msg = self.spec["success"] if self.game.state == "won" else self.spec["fail"]
            self.finished.emit(self.game.state == "won", self.game.caught)
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.game.state == "playing":
            pt = e.position()
            if self.game.hit(pt.x(), pt.y()):
                self._pops.append([pt.x(), pt.y(), 0.0])
                self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        pixel_box(p, self.rect(), PAL["panel_lo"], PAL["border_dark"])
        p.setFont(self.font)
        g = self.game
        for it in g.items:
            x = int(it["x"] + math.sin(it["y"] / 18 + it["wob"]) * 6) // PX * PX
            p.drawPixmap(x - self._pix.width() // 2, int(it["y"]) // PX * PX - self._pix.height() // 2, self._pix)
        for x, y, age in self._pops:
            r = int(6 + age * 60) // PX * PX
            p.setPen(QColor(PAL["gold"]))
            p.drawRect(int(x) - r, int(y) - r, 2 * r, 2 * r)
        p.setPen(QColor(PAL["text"]))
        if g.state == "playing":
            p.drawText(QRect(10, 6, self.width() - 20, 28), Qt.AlignLeft | Qt.AlignTop, tr("잡은 수 {0}/{1}").format(g.caught, g.target))
            p.drawText(QRect(10, 6, self.width() - 20, 28), Qt.AlignRight | Qt.AlignTop, tr("{0}초").format(math.ceil(g.time_left)))
        elif self._msg:
            draw_ink_centered(p, self.rect(), f"{self._msg}" + (f"  ({g.caught}/{g.target})" if g.state != "ready" else ""),
                              PAL["gold"], self.font)


class CatchEvent(QWidget):
    done = Signal(dict)

    def __init__(self, spec: dict, prev: dict | None, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.best = prev.get("best", 0) if prev else 0
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3 * PX)
        row = QHBoxLayout()
        row.addWidget(_label(tr("게임  {0}").format(spec['prompt']), GOLD_LABEL), 1)
        self.btn = PixelButton(tr("시작"), "play", kind="accent")
        self.btn.clicked.connect(self._start)
        row.addWidget(self.btn)
        v.addLayout(row)
        self.canvas = CatchCanvas(spec)
        self.canvas.finished.connect(self._finished)
        v.addWidget(self.canvas)
        if prev and prev.get("done"):
            self.canvas._msg = tr("이전 기록: {0}/{1}").format(self.best, spec['target']) + (tr(" 성공") if prev.get("correct") else "")
            self.btn.setText(tr("다시 하기"))

    def _start(self):
        self.btn.setEnabled(False)
        self.canvas.start()

    def _finished(self, won: bool, caught: int):
        self.best = max(self.best, caught)
        self.btn.setEnabled(True)
        self.btn.setText(tr("다시 하기"))
        self.done.emit({"done": True, "correct": won, "best": self.best})


def build_event(spec: dict | None, prev: dict | None, parent=None):
    if not spec:
        return None
    return {"quiz": QuizEvent, "wish": WishEvent, "catch": CatchEvent}[spec["type"]](spec, prev, parent)
