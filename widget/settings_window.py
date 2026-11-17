"""픽셀 스타일 설정 화면 (13개 카테고리): 위젯 / 눈 효과 / 날씨 / 바람 / 음악 / 사운드 / 시계 / 전구 / 장식 / 화면 및 창 / 일반."""
from __future__ import annotations
from core.i18n import LANGUAGES, tr


from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QMessageBox, QStackedWidget, QVBoxLayout)

from PySide6.QtWidgets import QScrollArea, QWidget as _QW
from audio.sfx import SOUNDS
from core import autostart
from core.logviewer import LogViewerError, open_log_console
from clockface import render as clock_render
from clockface.window import ClockPreview
from decor.lights import ANIM_NAMES, PALETTE_NAMES
from decor.sprites import DECOR_KINDS, KIND_NAME
from .music_panel import MusicPanel
from .pixel_extra import PixelChoice, PixelSwatches
from .pixel_ui import PAL, PX, WrapLabel, PixelButton, PixelCheck, PixelPanel, PixelSection, PixelSlider, PixelTabs, \
    PixelWindow, body_font
from .wind_panel import WindPanel
from .auto_weather_page import AutoWeatherPage
from weather import spec as aw_spec

LABEL_W = 150

DEFAULT_W = 488 * PX      # 설정 창 기본 너비 (이전 432 * PX)
DEFAULT_H = 352 * PX


class SettingsWindow(PixelWindow):
    center_requested = Signal()
    clean_requested = Signal()
    reset_requested = Signal()
    wind_window_requested = Signal()
    gust_requested = Signal()

    def __init__(self, settings, audio, parent=None, sfx=None, decor=None, auto=None, defer=False):
        super().__init__(tr("Christmas Wonderland 설정"), "gear", parent)
        self.s = settings
        self.audio = audio
        self.sfx = sfx
        self.decor = decor
        self.auto = auto
        # 기본 창 크기: 너비 976px (기존 864px). 작은 화면이면 화면 안에 들어오게 한 번만 제한한다.
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.setFixedSize(min(DEFAULT_W, max(640, avail.width() - 40)), min(DEFAULT_H, max(480, avail.height() - 40)))

        root = QVBoxLayout(self.body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        outer = QHBoxLayout()
        outer.setContentsMargins(0, 2 * PX, 0, 0)
        outer.setSpacing(3 * PX)
        root.addLayout(outer, 1)
        self._cur_tab = 0
        self.tabs = PixelTabs([("gear", tr("위젯")), ("snow", tr("눈 효과")), ("snow", tr("눈 물리")), ("thermo", tr("날씨")), ("wind", tr("바람")),
                               ("repeat", tr("자동 날씨")), ("note", tr("음악")), ("speaker", tr("사운드")), ("clock", tr("시계")), ("bulb", tr("전구")),
                               ("star", tr("장식")), ("calendar", tr("화면 및 창")), ("gear", tr("일반", "settings_tab"))])
        outer.addWidget(self.tabs)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self._builders = (self._page_widget, self._page_snow, self._page_physics, self._page_weather, self._page_wind,
                          self._page_auto, self._page_music, self._page_sound, self._page_clock,
                          self._page_lights, self._page_decor, self._page_window, self._page_general)
        self._built = 0
        self._ready = False
        self.tabs.currentChanged.connect(self.stack.setCurrentIndex)
        if defer:
            # 13개 탭을 한 번에 만들면 처음 열 때 화면이 1초 넘게 멈춘다(렉 진단 로그: 프레임 간격 1248ms).
            # 한 틱에 한 페이지씩 나눠 만들고, 다 만들기 전에 열리면 남은 것만 그때 만든다.
            for _ in self._builders:
                self.stack.addWidget(_QW())
            QTimer.singleShot(0, self._build_step)
        else:
            self.finish_build()

    def _build_step(self):
        """한 틱에 한 페이지만 만든다 (프레임 하나 정도의 끊김으로 분산)."""
        if self._ready:
            return
        self._build_page(self._built)
        if self._built >= len(self._builders):
            self._finish()
        else:
            QTimer.singleShot(15, self._build_step)

    def _build_page(self, idx):
        self._cur_labels = []
        self._cur_tab = idx
        page = self._builders[idx]()
        self._fit_labels(self._cur_labels)
        old = self.stack.widget(idx) if idx < self.stack.count() else None
        if old is not None:
            cur = self.stack.currentIndex()
            self.stack.removeWidget(old)
            old.deleteLater()
            self.stack.insertWidget(idx, page)
            self.stack.setCurrentIndex(cur)
        else:
            self.stack.addWidget(page)
        self._built = idx + 1

    def finish_build(self):
        """남은 페이지를 지금 모두 만든다 (설정창이 만들어지는 도중에 열렸을 때 / 테스트)."""
        while self._built < len(self._builders):
            self._build_page(self._built)
        self._finish()

    def _finish(self):
        if self._ready:
            return
        self._ready = True
        self.s.changed.connect(lambda _k: self.refresh())
        self.s.saved.connect(lambda _t: self.refresh())
        if self.auto is not None:
            self.auto.state_changed.connect(self._refresh_values)
        self.refresh()

    # ---------------------------------------------------------------- 도우미
    def _page(self, scroll: bool = True):
        """탭 한 페이지. 내용이 창보다 길면 세로 스크롤이 생긴다 (scroll=False: 자체 스크롤이 있는 페이지용)."""
        panel = PixelPanel(fill="bg")
        if not scroll:
            lay = QVBoxLayout(panel)
            lay.setContentsMargins(5 * PX, 4 * PX, 5 * PX, 4 * PX)
            lay.setSpacing(3 * PX)
            return panel, lay
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(PX, PX, PX, PX)            # 픽셀 테두리 안쪽에 스크롤 영역
        outer.setSpacing(0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)     # 폭이 모자란 내용은 잘리는 대신 가로 스크롤로 볼 수 있게
        sc.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        sc.viewport().setAutoFillBackground(False)
        sc.setStyleSheet("QScrollArea{background:transparent;}")
        body = _QW()
        body.setObjectName("pageBody")
        sc.setWidget(body)
        body.setAutoFillBackground(False)
        body.setStyleSheet("#pageBody{background:transparent;}")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(4 * PX, 3 * PX, 4 * PX, 3 * PX)
        lay.setSpacing(3 * PX)
        outer.addWidget(sc)
        return panel, lay

    def _fit_labels(self, labels):
        """한 페이지 안의 슬라이더 이름 칸 폭을 가장 긴 이름에 맞춘다 (모든 슬라이더가 같은 폭을 써서 줄이 맞음)."""
        if not labels:
            return
        fm = QFontMetrics(body_font())
        need = max(fm.horizontalAdvance(lb.text()) for lb in labels) + 3 * PX
        w = min(max(LABEL_W, need), 300)
        for lb in labels:
            lb.setFixedWidth(w)

    def _row(self, lay, label, control, key=None):
        row = QHBoxLayout()
        row.setSpacing(4 * PX)
        lb = WrapLabel(label)
        lb.setWordWrap(True)
        lb.setFont(body_font())
        lb.setFixedWidth(LABEL_W)
        self._cur_labels.append(lb)
        row.addWidget(lb)
        row.addWidget(control, 1)
        lay.addLayout(row)

    def _check(self, lay, text, key, save=True):
        c = PixelCheck(text)
        c.toggled.connect(lambda v, k=key: self.s.set(k, v, save=save))
        lay.addWidget(c)
        self._checks[key] = c
        return c

    def _slider(self, lay, label, key, lo, hi, step, suffix, scale=1.0, integer=False):
        sl = PixelSlider(lo, hi, step, suffix, value_width=58 * PX // 2 + 12)
        sl.valueChanged.connect(
            lambda v, k=key: self.s.set(k, int(v) if integer else v * scale))
        sl.released.connect(lambda: self.s.save_now())
        self._row(lay, label, sl, key)
        self._sliders[key] = (sl, scale)
        return sl

    def _choice(self, lay, label, key, items):
        ch = PixelChoice(items)
        ch.changed.connect(lambda v, k=key: self.s.set(k, v, save=True))
        self._row(lay, label, ch, key)
        self._choices.setdefault(key, []).append(ch)
        return ch

    def _swatches(self, lay, label, key, colors):
        sw = PixelSwatches(colors)
        sw.changed.connect(lambda v, k=key: self.s.set(k, v, save=True))
        self._row(lay, label, sw, key)
        self._swatch[key] = sw
        return sw

    @property
    def _choices(self):
        if not hasattr(self, "_ch"):
            self._ch = {}
        return self._ch

    @property
    def _swatch(self):
        if not hasattr(self, "_sw"):
            self._sw = {}
        return self._sw

    @property
    def _checks(self):
        if not hasattr(self, "_c"):
            self._c = {}
        return self._c

    @property
    def _sliders(self):
        if not hasattr(self, "_sl"):
            self._sl = {}
        return self._sl

    # ---------------------------------------------------------------- 페이지
    def _page_widget(self):
        w, lay = self._page()
        lay.addWidget(PixelSection(tr("시계와 날짜")))
        self._check(lay, tr("시계 표시"), "widget.show_clock")
        self._check(lay, tr("초 표시"), "widget.show_seconds")
        self._check(lay, tr("24시간제 (끄면 12시간제)"), "widget.clock_24h")
        self._check(lay, tr("날짜와 요일 표시"), "widget.show_date")
        self._check(lay, tr("크리스마스 D-Day 표시"), "widget.show_dday")
        lay.addWidget(PixelSection(tr("장식")))
        self._check(lay, tr("크리스마스 트리"), "widget.show_tree")
        self._check(lay, tr("선물 상자"), "widget.show_gift")
        self._check(lay, tr("별, 반짝임, 작은 눈송이"), "widget.show_sparkle")
        lay.addWidget(PixelSection(tr("투명도")))
        self._slider(lay, tr("위젯 투명도"), "widget.opacity", 20, 100, 5, "%", scale=0.01)
        lay.addStretch(1)
        return w

    def _page_snow(self):
        w, lay = self._page()
        lay.addWidget(PixelSection(tr("바탕화면 전체에 내리는 눈")))
        self._check(lay, tr("눈 효과 사용"), "snow.enabled")
        self._slider(lay, tr("강설량"), "snow.amount", 0, 1000, 10, tr(" 개"), integer=True)
        self._slider(lay, tr("눈송이 크기"), "snow.size", 50, 250, 5, "%", scale=0.01)
        self._slider(lay, tr("낙하 속도"), "snow.speed", 20, 300, 5, "%", scale=0.01)
        lay.addWidget(PixelSection(tr("쌓이는 눈")))
        self._slider(lay, tr("눈 축적량"), "snow.accumulate", 0, 100, 5, "%", integer=True)
        self._slider(lay, tr("눈 축적 속도"), "snow.accumulate_rate", 0, 100, 5, "%", integer=True)
        self._slider(lay, tr("눈 쌓이는 최대 높이"), "snow.max_height", 25, 300, 5, "%", integer=True)
        lay.addWidget(PixelSection(tr("온도 (눈과 눈사람이 녹는 속도를 결정)")))
        self._slider(lay, tr("온도"), "weather.temperature", -20, 30, 1, " ℃", integer=True)
        self.lbl_temp = WrapLabel()
        self.lbl_temp.setWordWrap(True)
        self.lbl_temp.setStyleSheet(f"color:{PAL['dim']};")
        lay.addWidget(self.lbl_temp)
        self.lbl_auto_snow = self._auto_note()
        lay.addWidget(self.lbl_auto_snow)
        lay.addSpacing(2 * PX)
        row = QHBoxLayout()
        b1 = PixelButton(tr("쌓인 눈 청소"), "trash")
        b2 = PixelButton(tr("시뮬레이션 초기화"), "reset")
        b1.clicked.connect(self.clean_requested.emit)
        b2.clicked.connect(self.reset_requested.emit)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    # ---------------------------------------------------------------- 새 페이지: 날씨
    def _page_weather(self):
        w, lay = self._page()
        lay.addWidget(PixelSection(tr("날씨 종류")))
        kinds = list(aw_spec.KINDS)
        self.kind_choices = []
        for chunk in ([("custom", tr("직접 설정"))] + kinds[:3], kinds[3:]):
            ch = PixelChoice(chunk)
            ch.changed.connect(self._manual_kind_picked)
            lay.addWidget(ch)
            self.kind_choices.append(ch)
        self.lbl_auto_weather = self._auto_note()
        lay.addWidget(self.lbl_auto_weather)
        lay.addWidget(PixelSection(tr("눈보라")))
        self._check(lay, tr("눈보라 켜기"), "weather.blizzard_on")
        self._slider(lay, tr("눈보라 강도"), "weather.blizzard", 0, 100, 5, "%", integer=True)
        lay.addWidget(PixelSection(tr("돌풍")))
        self._check(lay, tr("불규칙한 돌풍 자동 발생"), "weather.gust_on")
        self._slider(lay, tr("돌풍 세기"), "weather.gust_strength", 0, 100, 5, "%", integer=True)
        self._slider(lay, tr("평균 발생 간격"), "weather.gust_interval", 5, 180, 5, tr(" 초"), integer=True)
        gb = PixelButton(tr("지금 돌풍 일으키기"), "wind")
        gb.clicked.connect(self.gust_requested.emit)
        lay.addWidget(gb)
        lay.addStretch(1)
        return w

    # ---------------------------------------------------------------- 새 페이지: 사운드
    def _page_sound(self):
        w, lay = self._page()
        lay.addWidget(PixelSection(tr("크리스마스 사운드")))
        self._check(lay, tr("전체 효과음 켜기 / 끄기"), "sfx.enabled")
        self._slider(lay, tr("전체 효과음 음량"), "sfx.master", 0, 100, 5, "%", scale=0.01)
        chk_w = max([116 * PX] + [PixelCheck(t).sizeHint().width() + 4 * PX for _k, t in SOUNDS])
        for key, title in SOUNDS:
            row = QHBoxLayout()
            row.setSpacing(3 * PX)
            c = PixelCheck(title)
            c.setFixedWidth(chk_w)
            c.toggled.connect(lambda v, k=f"sfx.{key}_on": self.s.set(k, v, save=True))
            self._checks[f"sfx.{key}_on"] = c
            row.addWidget(c)
            sl = PixelSlider(0, 100, 5, "%", value_width=58 * PX // 2 + 12)
            sl.valueChanged.connect(lambda v, k=f"sfx.{key}_vol": self.s.set(k, v * 0.01))
            sl.released.connect(lambda: self.s.save_now())
            self._sliders[f"sfx.{key}_vol"] = (sl, 0.01)
            row.addWidget(sl, 1)
            pb = PixelButton("", "play")
            pb.setToolTip(tr("미리 듣기"))
            pb.clicked.connect(lambda _=False, k=key: self.sfx and self.sfx.preview(k))
            fb = PixelButton("", "folder")
            fb.setToolTip(tr("내 음원"))
            fb.clicked.connect(lambda _=False, k=key: self._pick_sfx_file(k))
            row.addWidget(pb)
            row.addWidget(fb)
            self._sfx_file_btn = getattr(self, "_sfx_file_btn", {})
            self._sfx_file_btn[key] = fb
            lay.addLayout(row)
        lay.addWidget(PixelSection(tr("재생 방식")))
        self._check(lay, tr("환경음 반복 재생 (끄면 한 번만)"), "sfx.loop")
        self._check(lay, tr("바람/눈보라/돌풍 상태에 맞춰 소리 연동"), "sfx.follow_weather")
        self._check(lay, tr("음악 재생 중에는 효과음 낮추기"), "sfx.duck")
        self._slider(lay, tr("종소리 간격"), "sfx.bell_interval", 1, 60, 1, tr(" 분"), integer=True)
        self.lbl_sfx = WrapLabel()
        self.lbl_sfx.setWordWrap(True)
        self.lbl_sfx.setStyleSheet(f"color:{PAL['dim']};")
        lay.addWidget(self.lbl_sfx)
        lay.addStretch(1)
        return w

    def _pick_sfx_file(self, key: str):
        cur = self.s.get(f"sfx.{key}_file")
        if cur:                                   # 이미 사용자 음원이면 기본 음원으로 되돌림
            self.s.set(f"sfx.{key}_file", "", save=True)
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("효과음으로 쓸 음원 선택"), "",
                                              tr("오디오 (*.wav *.mp3 *.ogg *.flac *.m4a *.aac *.opus)"))
        if path:
            self.s.set(f"sfx.{key}_file", path, save=True)

    # ---------------------------------------------------------------- 새 페이지: 시계
    def _page_clock(self):
        w, lay = self._page()
        self._check(lay, tr("바탕화면 시계 표시"), "clock.enabled")
        self.clock_preview = ClockPreview(self.s, height=84 * PX)
        lay.addWidget(self.clock_preview)
        self._choice(lay, tr("디지털"), "clock.theme", [(k, v) for k, v in clock_render.THEMES.items() if not k.startswith("analog")])
        self._choice(lay, tr("아날로그"), "clock.theme", [(k, v.replace("아날로그 ", "").replace("Analog ", "")) for k, v in clock_render.THEMES.items() if k.startswith("analog")])
        self._swatches(lay, tr("색상"), "clock.color", {k: v[0] for k, v in clock_render.COLORS.items()})
        self._choice(lay, tr("배경"), "clock.bg", list(clock_render.BGS.items()))
        self._slider(lay, tr("크기"), "clock.scale", 1, 8, 1, "", integer=True)
        self._slider(lay, tr("투명도"), "clock.opacity", 20, 100, 5, "%", integer=True)
        row = QHBoxLayout()
        row.setSpacing(6 * PX)
        for text, key in ((tr("시간"), "clock.show_time"), (tr("날짜"), "clock.show_date"), (tr("요일"), "clock.show_weekday"),
                          ("D-Day", "clock.show_dday")):
            c = PixelCheck(text)
            c.toggled.connect(lambda v, k=key: self.s.set(k, v, save=True))
            self._checks[key] = c
            row.addWidget(c)
        row.addStretch(1)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        row2.setSpacing(6 * PX)
        for text, key in ((tr("초 표시"), "clock.show_seconds"), (tr("24시간제"), "clock.h24"), (tr("이동 잠금"), "clock.locked")):
            c = PixelCheck(text)
            c.toggled.connect(lambda v, k=key: self.s.set(k, v, save=True))
            self._checks[key] = c
            row2.addWidget(c)
        row2.addStretch(1)
        lay.addLayout(row2)
        self._choice(lay, tr("표시 층"), "clock.layer", [("top", tr("항상 위")), ("normal", tr("일반")), ("bottom", tr("항상 아래"))])
        lay.addStretch(1)
        return w

    # ---------------------------------------------------------------- 새 페이지: 전구
    def _page_lights(self):
        w, lay = self._page()
        lay.addWidget(PixelSection(tr("픽셀 전구 장식")))
        self._check(lay, tr("전구 장식 켜기"), "lights.enabled")
        self._choice(lay, tr("위치"), "lights.position",
                     [("top", tr("위")), ("bottom", tr("아래")), ("left", tr("왼쪽")), ("right", tr("오른쪽")), ("custom", tr("직접 배치"))])
        self._check(lay, tr("직접 배치: 이동 잠금 (끄면 마우스로 끌어 이동)"), "lights.locked")
        self._check(lay, tr("직접 배치: 세로 방향"), "lights.custom_vertical")
        self._slider(lay, tr("직접 배치 길이"), "lights.custom_length", 120, 2400, 20, " px", integer=True)
        self._slider(lay, tr("모니터 번호"), "lights.monitor", 0, 3, 1, "", integer=True)
        lay.addWidget(PixelSection(tr("모양과 움직임")))
        self._choice(lay, tr("애니메이션"), "lights.anim", list(ANIM_NAMES.items())[:2])
        self._choice(lay, "", "lights.anim", list(ANIM_NAMES.items())[2:])
        self._choice(lay, tr("색상"), "lights.palette", [(k, v) for k, v in PALETTE_NAMES.items()][:3])
        self._choice(lay, "", "lights.palette", [(k, v) for k, v in PALETTE_NAMES.items()][3:])
        self._slider(lay, tr("밝기"), "lights.brightness", 20, 100, 5, "%", integer=True)
        self._slider(lay, tr("점멸 속도"), "lights.speed", 20, 300, 10, "%", integer=True)
        self._slider(lay, tr("전구 크기"), "lights.size", 2, 6, 1, "", integer=True)
        self._slider(lay, tr("전구 간격"), "lights.spacing", 3, 10, 1, "", integer=True)
        self._choice(lay, tr("표시 층"), "lights.layer", [("top", tr("항상 위")), ("normal", tr("일반")), ("bottom", tr("항상 아래"))])
        lay.addStretch(1)
        return w

    # ---------------------------------------------------------------- 새 페이지: 장식
    DECOR_PER_PAGE = 5

    def _page_decor(self):
        w, lay = self._page()
        lay.addWidget(PixelSection(tr("장식 추가 (누르면 화면 가운데에 놓임)")))
        grid = QHBoxLayout()
        grid.setSpacing(2 * PX)
        row2 = QHBoxLayout()
        row2.setSpacing(2 * PX)
        for n, (key, name, _spr) in enumerate(DECOR_KINDS):
            b = PixelButton(name)
            b.clicked.connect(lambda _=False, k=key: self.decor and self.decor.add(k))
            (grid if n < 5 else row2).addWidget(b)
        grid.addStretch(1)
        row2.addStretch(1)
        lay.addLayout(grid)
        lay.addLayout(row2)
        self._check(lay, tr("장식 표시"), "decor.enabled")
        self._check(lay, tr("이동 / 크기 조절 잠금"), "decor.locked")
        self._choice(lay, tr("표시 층"), "decor.layer", [("normal", tr("일반")), ("top", tr("항상 위")), ("bottom", tr("항상 아래"))])
        lay.addWidget(PixelSection(tr("배치한 장식")))
        self._decor_page = 0
        self.decor_list = QVBoxLayout()
        self.decor_list.setSpacing(2 * PX)
        lay.addLayout(self.decor_list)
        nav = QHBoxLayout()
        self.btn_dprev = PixelButton(tr("이전"), "prev")
        self.btn_dnext = PixelButton(tr("다음"), "next")
        self.lbl_dpage = WrapLabel()
        self.lbl_dpage.setStyleSheet(f"color:{PAL['dim']};")
        self.btn_dprev.clicked.connect(lambda: self._decor_turn(-1))
        self.btn_dnext.clicked.connect(lambda: self._decor_turn(1))
        nav.addWidget(self.btn_dprev)
        nav.addWidget(self.lbl_dpage)
        nav.addWidget(self.btn_dnext)
        nav.addStretch(1)
        clear = PixelButton(tr("모두 삭제"), "trash", kind="danger")
        clear.clicked.connect(lambda: self.decor and self.decor.clear_all())
        nav.addWidget(clear)
        lay.addLayout(nav)
        lay.addStretch(1)
        return w

    def _decor_turn(self, step: int):
        self._decor_page += step
        self._refresh_decor_list()

    def _refresh_decor_list(self):
        items = self.s.get("decor.items")
        per = self.DECOR_PER_PAGE
        pages = max(1, (len(items) + per - 1) // per)
        self._decor_page = max(0, min(self._decor_page, pages - 1))
        while self.decor_list.count():
            it = self.decor_list.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                while it.layout().count():
                    sub = it.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
                it.layout().deleteLater()
        for item in items[self._decor_page * per:(self._decor_page + 1) * per]:
            row = QHBoxLayout()
            row.setSpacing(3 * PX)
            c = PixelCheck(f"{KIND_NAME.get(item['kind'], item['kind'])}  x{item['scale']}")
            c.setChecked(item["visible"])
            c.setFixedWidth(150 * PX)
            c.toggled.connect(lambda v, i=item["id"]: self.decor and self.decor.set_visible(i, v))
            sm = PixelButton("", "minus")
            sm.clicked.connect(lambda _=False, i=item["id"], sc=item["scale"]: self.decor and self.decor.update_item(i, scale=max(1, sc - 1)))
            bg = PixelButton("", "star")
            bg.clicked.connect(lambda _=False, i=item["id"], sc=item["scale"]: self.decor and self.decor.update_item(i, scale=min(14, sc + 1)))
            de = PixelButton("", "trash", kind="danger")
            de.clicked.connect(lambda _=False, i=item["id"]: self.decor and self.decor.remove(i))
            for wdg in (c, sm, bg, de):
                row.addWidget(wdg)
            row.addStretch(1)
            self.decor_list.addLayout(row)
        self.lbl_dpage.setText(tr("{0} / {1}  (총 {2}개)").format(self._decor_page + 1, pages, len(items)))
        self.btn_dprev.setEnabled(self._decor_page > 0)
        self.btn_dnext.setEnabled(self._decor_page < pages - 1)

    def _auto_note(self):
        lb = WrapLabel()
        lb.setWordWrap(True)
        lb.setStyleSheet(f"color:{PAL['gold']};")
        lb.hide()
        return lb

    def _manual_kind_picked(self, kid: str):
        """수동 날씨 종류 선택. 자동 날씨 실행 중이면 날씨 종류만 고정(나머지 변수는 자동 유지),
        꺼져 있으면 그 날씨의 대표값을 수동 설정에 한 번 적용한다."""
        running = self.auto is not None and self.auto.core.phase == "run"
        if not running and kid != "custom":
            for key, val in aw_spec.MANUAL_APPLY[kid].items():
                self.s.set(key, val)
        self.s.set("weather.kind", kid, save=True)

    def _page_auto(self):
        panel, lay = self._page(scroll=False)
        lay.setContentsMargins(0, 0, 0, 0)
        if self.auto is None:
            lay.addWidget(WrapLabel(tr("자동 날씨를 사용할 수 없습니다.")))
        else:
            self.auto_page = AutoWeatherPage(self.s, self.auto)
            lay.addWidget(self.auto_page)
        return panel

    def _page_physics(self):
        """눈 물리 튜닝: 커서 / 눈 물질 / 창 이동. 항목이 많아 스크롤 영역에 담는다."""
        panel, lay = self._page(scroll=False)
        lay.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.viewport().setAutoFillBackground(False)
        sc.setStyleSheet("QScrollArea{background:transparent;}")
        body = _QW()
        body.setStyleSheet("background:transparent;")
        sc.setWidget(body)
        inner = QVBoxLayout(body)
        inner.setContentsMargins(5 * PX, 4 * PX, 5 * PX, 4 * PX)
        inner.setSpacing(3 * PX)

        def sl(label, key):
            self._slider(inner, label, f"physics.{key}", 0, 100, 5, "%", integer=True)

        inner.addWidget(PixelSection(tr("화면 가장자리")))
        self._check(inner, tr("화면 끝으로 나간 눈이 반대편에서 나오기"), "physics.wrap")
        inner.addWidget(PixelSection(tr("마우스 커서")))
        self._check(inner, tr("커서로 눈 휘젓기"), "weather.cursor_on")
        self._slider(inner, tr("휘젓는 세기"), "weather.cursor_strength", 0, 100, 5, "%", integer=True)
        self._slider(inner, tr("영향 반경"), "weather.cursor_radius", 40, 400, 10, " px", integer=True)
        sl(tr("속도에 따른 힘 증가"), "cursor_gain")
        sl(tr("눈송이 반응 강도"), "flake_react")
        sl(tr("회전력"), "swirl")
        inner.addWidget(PixelSection(tr("프로그램 창과 눈")))
        sl(tr("창 이동 시 미끄러짐"), "win_slip")
        sl(tr("창 이동 시 낙하 민감도"), "win_fall")
        inner.addStretch(1)
        lay.addWidget(sc)
        return panel

    def _page_wind(self):
        w, lay = self._page()
        lay.addWidget(PixelSection(tr("바람 컨트롤러")))
        self.wind_panel = WindPanel(self.s)
        self.dial = self.wind_panel.dial
        lay.addWidget(self.wind_panel)
        btn = PixelButton(tr("작은 바람 창으로 열기"), "wind")
        btn.clicked.connect(self.wind_window_requested.emit)
        lay.addWidget(btn)
        self.lbl_auto_wind = self._auto_note()
        lay.addWidget(self.lbl_auto_wind)
        lay.addStretch(1)
        return w

    def _page_music(self):
        w, lay = self._page()
        lay.setContentsMargins(3 * PX, 3 * PX, 3 * PX, 3 * PX)
        self.music = MusicPanel(self.audio, self.s)
        lay.addWidget(self.music)
        return w

    def _page_window(self):
        w, lay = self._page()
        lay.addWidget(PixelSection(tr("창 표시 방식")))
        row = QHBoxLayout()
        self.btn_normal = PixelButton(tr("일반 창"), "calendar")
        self.btn_bottom = PixelButton(tr("항상 아래 창"), "globe")
        for b, mode in ((self.btn_normal, "normal"), (self.btn_bottom, "bottom")):
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, m=mode: self.s.set("widget.mode", m, save=True))
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(PixelSection(tr("위치와 크기")))
        self._check(lay, tr("위젯 잠금 (이동, 크기 조절 방지)"), "widget.locked")
        self._slider(lay, tr("위젯 너비"), "widget.width", 260, 1600, 10, " px", integer=True)
        self._slider(lay, tr("위젯 높이"), "widget.height", 300, 1600, 10, " px", integer=True)
        btn = PixelButton(tr("위젯을 화면 중앙으로"), "star")
        btn.clicked.connect(self.center_requested.emit)
        lay.addWidget(btn)
        lay.addWidget(PixelSection(tr("감지된 모니터")))
        self.lbl_mon = WrapLabel()
        self.lbl_mon.setStyleSheet(f"color:{PAL['dim']};")
        lay.addWidget(self.lbl_mon)
        lay.addStretch(1)
        return w

    def _set_display_option(self, key: str, enabled: bool):
        """트레이/작업표시줄은 최소 하나가 켜져 있도록 보장한다."""
        other_key = "app.show_taskbar" if key == "app.show_tray" else "app.show_tray"
        if not enabled and not self.s.get(other_key):
            target = self.chk_show_tray if key == "app.show_tray" else self.chk_show_taskbar
            target.blockSignals(True)
            target.setChecked(True)
            target.blockSignals(False)
            QMessageBox.information(self, tr("프로그램 표시 방식"), tr("트레이 또는 작업표시줄 중 하나는 표시해야 합니다."))
            return
        self.s.set(key, bool(enabled), save=True)

    def _set_autostart(self, enabled: bool):
        """Windows 현재 사용자 로그인 시작 등록을 적용한다."""
        try:
            autostart.set_enabled(enabled)
        except Exception as exc:
            QMessageBox.warning(self, tr("자동 실행 설정"), tr("자동 실행 설정을 변경하지 못했습니다.\n{0}").format(exc))
            self.chk_autostart.blockSignals(True)
            self.chk_autostart.setChecked(autostart.is_enabled())
            self.chk_autostart.blockSignals(False)

    def _open_log_viewer(self):
        """별도 콘솔 창에서 data/app.log 를 실시간으로 보여 준다. 그 창을 닫아도 프로그램은 종료되지 않는다."""
        proc = getattr(self, "_log_proc", None)
        if proc is not None and proc.poll() is None:          # 이미 열려 있으면 또 열지 않는다
            return
        try:
            self._log_proc = open_log_console()
        except LogViewerError as exc:
            QMessageBox.warning(self, tr("실시간 로그"), str(exc))

    def _page_general(self):
        w, lay = self._page()
        lay.addWidget(PixelSection(tr("언어")))
        lang = self._choice(lay, tr("언어"), "app.language", list(LANGUAGES.items()))
        self.lbl_lang_note = WrapLabel()
        self.lbl_lang_note.setWordWrap(True)
        self.lbl_lang_note.setStyleSheet(f"color:{PAL['dim']};")
        lang.changed.connect(lambda _v: self.lbl_lang_note.setText(tr("다시 시작하면 적용돼요.")))
        lay.addWidget(self.lbl_lang_note)
        lay.addWidget(PixelSection(tr("프로그램 표시 방식")))
        self.chk_show_tray = PixelCheck(tr("시스템 트레이에 표시"))
        self.chk_show_taskbar = PixelCheck(tr("작업표시줄에 표시"))
        self.chk_show_tray.toggled.connect(lambda value: self._set_display_option("app.show_tray", value))
        self.chk_show_taskbar.toggled.connect(lambda value: self._set_display_option("app.show_taskbar", value))
        lay.addWidget(self.chk_show_tray)
        lay.addWidget(self.chk_show_taskbar)
        lay.addWidget(PixelSection(tr("Windows 시작")))
        self.chk_autostart = PixelCheck(tr("컴퓨터 시작 시 자동 실행"))
        self.chk_autostart.toggled.connect(self._set_autostart)
        if __import__("os").name != "nt":
            self.chk_autostart.setEnabled(False)
            self.chk_autostart.setToolTip(tr("Windows에서만 사용할 수 있습니다."))
        lay.addWidget(self.chk_autostart)
        lay.addWidget(PixelSection(tr("눈 렌더링")))
        self._slider(lay, tr("초당 프레임"), "performance.fps", 10, 60, 5, " fps", integer=True)
        self._slider(lay, tr("파티클 상한"), "performance.max_particles", 100, 3000, 100, tr(" 개"), integer=True)
        self._check(lay, tr("창 / 작업표시줄 위에 눈 쌓기"), "performance.track_windows")
        self._check(lay, tr("전체화면 앱 실행 중에는 눈 멈춤"), "performance.pause_fullscreen")
        lay.addWidget(PixelSection(tr("로그")))
        row_log = QHBoxLayout()
        row_log.setSpacing(3 * PX)
        self.btn_log = PixelButton(tr("실시간 로그 보기"), "gear")
        self.btn_log.clicked.connect(self._open_log_viewer)
        if __import__("os").name != "nt":
            self.btn_log.setEnabled(False)
        row_log.addWidget(self.btn_log)
        row_log.addStretch(1)
        lay.addLayout(row_log)
        lay.addWidget(PixelSection(tr("저장과 백업")))
        self._check(lay, tr("자동 저장 사용"), "app.autosave", save=False)
        self._slider(lay, tr("자동 저장 간격"), "app.autosave_interval", 5, 600, 5, tr(" 초"), integer=True)
        self.lbl_path = WrapLabel()
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet(f"color:{PAL['dim']};")
        self.lbl_saved = WrapLabel()
        self.lbl_saved.setStyleSheet(f"color:{PAL['dim']};")
        lay.addWidget(self.lbl_path)
        lay.addWidget(self.lbl_saved)
        row = QHBoxLayout()
        row.setSpacing(3 * PX)
        for text, icon, fn in ((tr("지금 저장"), "save", self._manual_save), (tr("폴더 열기"), "folder", self._open_folder),
                               (tr("백업 복원"), "reset", self._restore), (tr("초기화"), "trash", self._reset)):
            b = PixelButton(text, icon)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    # ---------------------------------------------------------------- 동기화
    def refresh(self):
        if not self._ready:                 # 아직 페이지를 만드는 중: 다 만들어지면 _finish 가 한 번 반영한다
            return
        self._refresh_values()
        self._refresh_decor_list()
        if hasattr(self, "chk_autostart"):
            self.chk_autostart.blockSignals(True)
            self.chk_autostart.setChecked(autostart.is_enabled())
            self.chk_autostart.blockSignals(False)
        for attr, key in (("chk_show_tray", "app.show_tray"), ("chk_show_taskbar", "app.show_taskbar")):
            chk = getattr(self, attr, None)
            if chk is not None:
                chk.blockSignals(True)
                chk.setChecked(bool(self.s.get(key)))
                chk.blockSignals(False)

    def _eff(self, key):
        return self.s.effective(key)

    def _refresh_values(self):
        """슬라이더 등은 '실제 적용값'(자동 날씨 조정 중이면 자동 적용값)을 보여 준다. 가벼워서 자동 날씨 상태 갱신마다 호출."""
        if not self._ready:
            return
        s = self.s
        for key, chk in self._checks.items():
            chk.blockSignals(True)
            chk.setChecked(bool(s.get(key)))
            chk.blockSignals(False)
        for key, (sl, scale) in self._sliders.items():
            v = self._eff(key)
            if not sl.isDown():
                sl.setValue(v / scale if scale != 1.0 else v)
        for key, chs in self._choices.items():
            for ch in chs:
                ch.set_value(s.get(key))
        for key, sw in self._swatch.items():
            sw.set_value(s.get(key))
        T = int(self._eff("weather.temperature"))
        self.lbl_temp.setText(tr("현재 {0}℃ - ").format(T) + (tr("영하 10℃ 이하에서는 눈과 눈사람이 거의 녹지 않아요.") if T <= -10 else
                              tr("0℃ 이하에서는 천천히 녹아요.") if T <= 0 else tr("온도가 높을수록 쌓인 눈과 눈사람이 빨리 녹아내려요.")))
        kind = self._eff("weather.kind")
        for ch in getattr(self, "kind_choices", []):
            ch.set_value(kind)
        ctl = set(self.auto.controlled_vars()) if self.auto is not None else set()
        groups = ((self.lbl_auto_snow, ("snow_amount", "snow_size", "snow_speed", "snow_accumulate", "snow_accum_rate", "temperature")),
                  (self.lbl_auto_weather, ("kind", "gust_strength", "gust_interval")),
                  (self.lbl_auto_wind, ("wind_direction", "wind_strength")))
        for lb, ids in groups:
            names = [aw_spec.KIND_LABEL if i == "kind" else aw_spec.VARS_BY_ID[i]["label"].split(" (")[0] for i in ids if i in ctl]
            lb.setVisible(bool(names))
            if names:
                lb.setText(tr("자동 날씨가 조정 중: ") + ", ".join(names) + tr("\n슬라이더는 현재 적용값을 보여 주며, 직접 바꾸면 그 항목만 수동으로 고정돼요."))
        for key, btn in getattr(self, "_sfx_file_btn", {}).items():
            has = bool(s.get(f"sfx.{key}_file"))
            btn.set_icon("trash" if has else "folder")
            btn.setToolTip(tr("기본 음원") if has else tr("내 음원"))
        self.lbl_sfx.setText(tr("사용자 음원 사용: ") + (", ".join(t for k, t in SOUNDS if s.get(f"sfx.{k}_file")) or tr("없음 (모두 기본 음원)")))
        self.wind_panel.refresh()
        mode = s.get("widget.mode")
        self.btn_normal.setChecked(mode == "normal")
        self.btn_bottom.setChecked(mode == "bottom")
        scr = QGuiApplication.screens()
        self.lbl_mon.setText("\n".join(
            tr("{0}. {1:.0f}x{2:.0f}  배율 {3:.0f}%").format(i + 1, sc.geometry().width() * sc.devicePixelRatio(), sc.geometry().height() * sc.devicePixelRatio(), sc.devicePixelRatio() * 100)
            for i, sc in enumerate(scr)) or tr("(없음)"))
        self.lbl_path.setText(tr("설정 파일: {0}").format(s.path))
        last = s.get("app.last_saved")
        self.lbl_saved.setText(tr("마지막 저장: {0}").format(last.replace('T', ' ') if last else tr('아직 저장 안 됨')))

    # ---------------------------------------------------------------- 동작
    def _manual_save(self):
        if not self.s.save_now(manual=True):
            QMessageBox.warning(self, tr("저장 실패"), tr("설정을 저장하지 못했습니다. 로그(data/app.log)를 확인하세요."))

    def _open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.s.path.parent)))

    def _restore(self):
        start = str(self.s.backup_dir if self.s.backup_dir.exists() else self.s.path.parent)
        path, _ = QFileDialog.getOpenFileName(self, tr("복원할 백업 선택"), start, tr("설정 백업 (*.json *.bak)"))
        if path and not self.s.import_backup(Path(path)):
            QMessageBox.warning(self, tr("복원 실패"), tr("올바른 설정 파일이 아닙니다."))

    def _reset(self):
        if QMessageBox.question(self, tr("초기화"), tr("모든 설정을 기본값으로 되돌릴까요?")) == QMessageBox.StandardButton.Yes:
            self.s.reset_defaults()
            self.s.save_now()
