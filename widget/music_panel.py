from __future__ import annotations
from core.i18n import tr


from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QSizePolicy, QVBoxLayout, QWidget)

from .pixel_ui import PX, PAL, PixelButton, PixelCheck, PixelPanel, PixelSlider, body_font

REPEAT_LABEL = {"all": tr("전체 반복"), "one": tr("한 곡 반복"), "off": tr("반복 안 함")}
REPEAT_TIP = {"all": tr("목록 전체를 끝나면 처음부터 다시 재생해요"), "one": tr("지금 곡만 계속 반복해요"), "off": tr("마지막 곡이 끝나면 멈춰요")}


def now_text(index: int, total: int, title: str, playing: bool) -> str:
    """'재생 중인 곡' 표시 문구: 곡 번호/전체와 재생 상태. 곡이 없으면 안내 문구."""
    if not title or index < 0 or total <= 0:
        return tr("재생 중인 곡 없음")
    return f"{index + 1}/{total}  {title}  ({tr('재생 중') if playing else tr('일시정지')})"


def list_text(title: str, tag: str, current: bool) -> str:
    return f"{'> ' if current else '  '}{title}  [{tag}]"


def fmt_ms(ms: int) -> str:
    s = max(0, int(ms // 1000))
    return f"{s // 60}:{s % 60:02d}"


class TimeSlider(PixelSlider):
    def format(self, v: float) -> str:
        return fmt_ms(int(v))


class ElideLabel(QLabel):
    """한 줄 고정 라벨: 글이 길면 줄바꿈하지 않고 끝을 …으로 줄인다 (창 크기가 글 길이에 따라 변하지 않는다)."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = ""
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setFixedHeight(self.fontMetrics().height() + 2 * PX)
        self.setText(text)

    def setText(self, text):
        self._full = str(text)
        self._elide()

    def _elide(self):
        w = max(0, self.width())
        shown = self.fontMetrics().elidedText(self._full, Qt.ElideRight, w) if w > 8 else self._full
        if shown != QLabel.text(self):
            QLabel.setText(self, shown)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def minimumSizeHint(self):
        return QSize(0, self.height())


class MarqueeLabel(ElideLabel):
    """한 줄 고정 라벨: 글이 길어 안 들어가면 제목 전체가 옆으로 천천히 흘러가며 보인다 (짧으면 그대로 정지)."""

    STEP_PX = 1            # 한 번에 움직이는 거리 (px)
    TICK_MS = 33
    PAUSE_TICKS = 45       # 시작/끝에서 잠깐 멈추는 시간
    GAP_PX = 36            # 한 바퀴 돌 때 글 사이 간격

    def __init__(self, text="", parent=None):
        self._off = 0.0
        self._pause = self.PAUSE_TICKS
        self._scroll = False
        self._timer = None
        self.color = None                    # 흐르는 글자색 (None 이면 라벨 기본색)
        super().__init__(text, parent)
        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._elide()

    def _elide(self):
        if self._timer is None:
            return
        w = max(0, self.width())
        need = self.fontMetrics().horizontalAdvance(self._full) > w > 8
        if need != self._scroll:
            self._scroll = need
            self._off = 0.0
            self._pause = self.PAUSE_TICKS
        if need:
            QLabel.setText(self, "")
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            QLabel.setText(self, self._full)
        self.update()

    def _tick(self):
        if not self.isVisible():
            return
        if self._pause > 0:
            self._pause -= 1
            return
        self._off += self.STEP_PX
        if self._off >= self.fontMetrics().horizontalAdvance(self._full) + self.GAP_PX:
            self._off = 0.0
            self._pause = self.PAUSE_TICKS
        self.update()

    def hideEvent(self, e):
        self._off, self._pause = 0.0, self.PAUSE_TICKS
        super().hideEvent(e)

    def paintEvent(self, e):
        if not self._scroll:
            return super().paintEvent(e)
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(QColor(self.color) if self.color else self.palette().windowText().color())
        fm = self.fontMetrics()
        tw = fm.horizontalAdvance(self._full)
        y = (self.height() + fm.ascent() - fm.descent()) // 2
        x = -int(self._off)
        p.drawText(x, y, self._full)
        p.drawText(x + tw + self.GAP_PX, y, self._full)       # 끝이 지나가면 처음이 이어서 나타난다
        p.end()


class MusicPanel(QWidget):
    def __init__(self, audio, settings, parent=None):
        super().__init__(parent)
        self.audio = audio
        self.settings = settings
        self.setFont(body_font())
        self._build()
        self._connect()
        self.refresh_all()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4 * PX)

        now = PixelPanel(self)
        nl = QVBoxLayout(now)
        nl.setContentsMargins(6 * PX, 5 * PX, 6 * PX, 5 * PX)
        self.lbl_title = MarqueeLabel(tr("재생 중인 곡 없음"))
        self.lbl_title.setStyleSheet(f"color:{PAL['gold']};")
        self.lbl_title.color = PAL["gold"]
        nl.addWidget(self.lbl_title)
        self.seek = TimeSlider(0, 0, 1000, value_width=70)
        nl.addWidget(self.seek)
        self.lbl_pos = QLabel("")
        v.addWidget(now)

        ctl = QHBoxLayout()
        ctl.setSpacing(3 * PX)
        self.btn_prev = PixelButton("", "prev")
        self.btn_play = PixelButton("", "play", kind="accent")
        self.btn_next = PixelButton("", "next")
        for b in (self.btn_prev, self.btn_play, self.btn_next):
            b.setFixedWidth(26 * PX)
            ctl.addWidget(b)
        self.btn_repeat = PixelButton("", "repeat")
        ctl.addWidget(self.btn_repeat)
        ctl.addStretch(1)
        v.addLayout(ctl)

        vr = QHBoxLayout()
        vr.addWidget(PixelButton(tr("음량"), "speaker", kind="flat"))
        self.vol = PixelSlider(0, 100, 1, "%", value_width=56)
        vr.addWidget(self.vol, 1)
        v.addLayout(vr)

        self.list = QListWidget()
        self.list.setFont(body_font())
        self.list.setMinimumHeight(48 * PX)
        self.list.setTextElideMode(Qt.ElideRight)                      # 긴 곡 이름은 …으로 줄이고 가로로 늘어나지 않게
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        v.addWidget(self.list, 1)

        row2 = QHBoxLayout()
        row2.setSpacing(3 * PX)
        self.btn_add = PixelButton(tr("파일 추가"), "note")
        self.btn_folder = PixelButton(tr("폴더 선택"), "folder")
        self.btn_remove = PixelButton(tr("곡 제거"), "trash")
        for b in (self.btn_add, self.btn_folder, self.btn_remove):
            row2.addWidget(b)
        v.addLayout(row2)

        self.lbl_folder = QLabel()
        self.lbl_folder.setWordWrap(True)
        self.lbl_folder.setStyleSheet(f"color:{PAL['dim']};")
        v.addWidget(self.lbl_folder)
        self.chk_default = PixelCheck(tr("기본 크리스마스 음악 포함"))
        self.chk_auto = PixelCheck(tr("프로그램 시작 시 자동 재생"))
        v.addWidget(self.chk_default)
        v.addWidget(self.chk_auto)
        self.lbl_msg = QLabel("")
        self.lbl_msg.setWordWrap(True)
        self.lbl_msg.setStyleSheet(f"color:{PAL['red']};")
        v.addWidget(self.lbl_msg)

    def _connect(self):
        a = self.audio
        self.btn_play.clicked.connect(a.toggle)
        self.btn_prev.clicked.connect(a.prev)
        self.btn_next.clicked.connect(a.next)
        self.btn_repeat.clicked.connect(self.audio.cycle_repeat)
        self.vol.valueChanged.connect(lambda x: self.audio.set_volume(x / 100.0))
        self.vol.released.connect(lambda: self.settings.save_now())
        self.seek.valueChanged.connect(lambda x: a.seek(int(x)))
        self.list.itemDoubleClicked.connect(lambda it: a.play_index(self.list.row(it)))
        self.btn_add.clicked.connect(self._add_files)
        self.btn_folder.clicked.connect(self._pick_folder)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.chk_default.toggled.connect(a.set_use_default)
        self.chk_auto.toggled.connect(lambda on: self.settings.set("music.autoplay", on, save=True))
        a.playlistChanged.connect(self._fill_list)
        a.trackChanged.connect(self._on_track)
        a.playingChanged.connect(self._on_playing)
        a.positionChanged.connect(self._on_pos)
        a.durationChanged.connect(self._on_dur)
        a.message.connect(self.lbl_msg.setText)
        self.settings.changed.connect(self._on_setting)

    # ---- 동기화
    def refresh_all(self):
        self._fill_list()
        self._on_playing(self.audio.is_playing)
        self._on_setting("*")
        self._on_track(self.audio.index, self.audio.current_title())
        # 플레이어 창은 처음 열 때 만들어지므로, 이미 재생 중인 곡의 길이/위치 신호는 놓친 뒤다 -> 지금 값을 직접 가져온다
        self._sync_time()

    def _sync_time(self):
        pl = self.audio.player
        self._on_dur(pl.duration())
        self._on_pos(pl.position())

    def _on_setting(self, key):
        if key in ("*", "music.volume"):
            self.vol.setValue(round(float(self.settings.get("music.volume")) * 100))
        if key in ("*", "music.repeat"):
            mode = self.settings.get("music.repeat")
            self.btn_repeat.setText(REPEAT_LABEL.get(mode, "반복"))
            self.btn_repeat._kind = "normal" if mode == "off" else "accent"      # 반복이 켜져 있으면 강조색
            self.btn_repeat.update()
        if key in ("*", "music.folder"):
            f = self.settings.get("music.folder")
            self.lbl_folder.setText(tr("음악 폴더: {0}").format(f) if f else tr("음악 폴더: (선택 안 함)"))
        for chk, k in ((self.chk_default, "music.use_default"), (self.chk_auto, "music.autoplay")):
            if key in ("*", k):
                chk.blockSignals(True)
                chk.setChecked(bool(self.settings.get(k)))
                chk.blockSignals(False)

    _TAG = {"default": tr("기본"), "folder": tr("폴더"), "user": tr("추가")}

    def _fill_list(self):
        self.list.clear()
        cur = self.audio.index
        for i, t in enumerate(self.audio.tracks):
            item = QListWidgetItem(list_text(t.title, self._TAG.get(t.source, ""), i == cur))
            item.setData(Qt.UserRole, t.path)
            self.list.addItem(item)
        if 0 <= cur < self.list.count():
            self.list.setCurrentRow(cur)
        self._update_now()

    def _mark_current(self, index: int):
        """목록에서 지금 곡 앞에만 '>' 표시 (목록 전체를 다시 만들지 않는다)."""
        for i, t in enumerate(self.audio.tracks[:self.list.count()]):
            item = self.list.item(i)
            if item is not None:
                item.setText(list_text(t.title, self._TAG.get(t.source, ""), i == index))

    def _update_now(self):
        a = self.audio
        self.lbl_title.setText(now_text(a.index, len(a.tracks), a.current_title(), bool(a.is_playing)))

    def _on_track(self, index, title):
        self._mark_current(index)
        if 0 <= index < self.list.count():
            self.list.setCurrentRow(index)
        self._update_now()
        self.lbl_msg.setText("")

    def _on_playing(self, playing):
        self.btn_play.set_icon("pause" if playing else "play")
        self._update_now()

    def _on_pos(self, ms):
        if int(ms) > self.seek.hi:                 # 길이를 아직 못 받았으면(또는 0이면) 재생바가 멈추지 않게 범위를 넓힌다
            self.seek.setRange(0, max(int(ms), int(self.audio.player.duration())))
        if not self.seek.isDown():
            self.seek.blockSignals(True)
            self.seek.setValue(int(ms))
            self.seek.blockSignals(False)

    def _on_dur(self, ms):
        self.seek.setRange(0, max(0, int(ms)))

    # ---- 동작
    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("음악 파일 추가"), self.settings.get("music.folder") or str(Path.home()),
            tr("오디오 파일 (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.wma *.opus);;모든 파일 (*.*)"))
        if files:
            self.audio.add_files(files)
            self.settings.save_now()

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, tr("음악 폴더 선택"), self.settings.get("music.folder") or str(Path.home()))
        if folder:
            self.audio.set_folder(folder)

    def _remove_selected(self):
        item = self.list.currentItem()
        if not item:
            return
        path = item.data(Qt.UserRole)
        if path in self.settings.get("music.user_files"):
            self.audio.remove_user_file(path)
        else:
            self.lbl_msg.setText(tr("추가한 파일만 제거할 수 있습니다. (기본 음악은 옵션, 폴더는 폴더 선택으로 변경)"))
