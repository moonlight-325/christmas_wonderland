"""선물 콘텐츠 설정 창: 콘텐츠 JSON 파일 선택/편집/다시 불러오기, 애니메이션·이벤트 사용 여부."""
from __future__ import annotations
from core.i18n import tr


from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout

from widget.pixel_ui import PAL, PX, PixelButton, PixelCheck, PixelSection, PixelWindow


class ContentSettingsWindow(PixelWindow):
    changed = Signal()            # 콘텐츠 파일/옵션이 바뀌어 다시 불러와야 할 때

    def __init__(self, store, get_content, parent=None):
        super().__init__(tr("선물 콘텐츠 설정"), "gear", parent)
        self.store = store
        self.get_content = get_content          # () -> ContentSet (현재 로드된 콘텐츠)
        self.setFixedSize(330 * PX, 215 * PX)
        v = QVBoxLayout(self.body)
        v.setContentsMargins(5 * PX, 4 * PX, 5 * PX, 4 * PX)
        v.setSpacing(3 * PX)

        v.addWidget(PixelSection(tr("콘텐츠 파일")))
        self.lbl_src = QLabel()
        self.lbl_src.setWordWrap(True)
        self.lbl_src.setStyleSheet(f"color:{PAL['dim']};")
        v.addWidget(self.lbl_src)
        row = QHBoxLayout()
        row.setSpacing(3 * PX)
        b_edit = PixelButton(tr("JSON 편집"), "folder")
        b_edit.clicked.connect(self._open_json)
        b_pick = PixelButton(tr("파일 선택"), "folder")
        b_pick.clicked.connect(self._pick)
        b_default = PixelButton(tr("기본 파일로"), "reset")
        b_default.clicked.connect(self._use_default)
        for b in (b_edit, b_pick, b_default):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)

        v.addWidget(PixelSection(tr("표시")))
        self.chk_anim = PixelCheck(tr("개봉·공개 애니메이션 사용"))
        self.chk_anim.toggled.connect(lambda on: self._set("animations", on))
        self.chk_events = PixelCheck(tr("선물 속 작은 이벤트 사용"))
        self.chk_events.toggled.connect(lambda on: self._set("events", on))
        v.addWidget(self.chk_anim)
        v.addWidget(self.chk_events)

        self.lbl_warn = QLabel()
        self.lbl_warn.setWordWrap(True)
        v.addWidget(self.lbl_warn)
        v.addStretch(1)
        row2 = QHBoxLayout()
        b_reload = PixelButton(tr("다시 불러오기"), "reset", kind="accent")
        b_reload.clicked.connect(self.changed.emit)
        row2.addWidget(b_reload)
        row2.addStretch(1)
        v.addLayout(row2)
        self.refresh()

    def refresh(self):
        cs = self.get_content()
        self.lbl_src.setText(tr("사용 중: {0}").format(cs.source))
        for chk, key in ((self.chk_anim, "animations"), (self.chk_events, "events")):
            chk.blockSignals(True)
            chk.setChecked(bool(self.store.get_setting(key)))
            chk.blockSignals(False)
        if cs.warnings:
            shown = " / ".join(cs.warnings[:2])
            more = tr(" 외 {0}건").format(len(cs.warnings) - 2) if len(cs.warnings) > 2 else ""
            self.lbl_warn.setStyleSheet("color:#ff7a6e;")
            self.lbl_warn.setText(tr("확인 필요 {0}건: {1}{2}").format(len(cs.warnings), shown, more))
        else:
            self.lbl_warn.setStyleSheet(f"color:{PAL['green']};")
            self.lbl_warn.setText(tr("24개 선물 콘텐츠를 모두 정상적으로 불러왔습니다."))

    def _set(self, key: str, on: bool):
        self.store.set_setting(key, on)
        self.changed.emit()

    def _open_json(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.get_content().source)))

    def _pick(self):
        start = str(self.get_content().source.parent)
        path, _ = QFileDialog.getOpenFileName(self, tr("콘텐츠 JSON 선택"), start, "JSON (*.json)")
        if path:
            self.store.set_setting("content_path", path)
            self.changed.emit()

    def _use_default(self):
        self.store.set_setting("content_path", "")
        self.changed.emit()
