"""설정 > '자동 날씨' 탭: 제어 / 프리셋 / 날씨 종류 가중치 / 변수별 자동·수동·범위 / 변화 설정."""
from __future__ import annotations
from core.i18n import tr


from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QDoubleSpinBox, QHBoxLayout, QInputDialog, QLabel, QListWidget, QMessageBox,
                               QScrollArea, QVBoxLayout, QWidget)

from weather import spec
from .pixel_ui import PAL, PX, PixelButton, PixelCheck, PixelSection, PixelSlider, body_font

AUTO_BG, MANUAL_BG = "#1b5a43", "#5d4521"
AUTO_BAR, MANUAL_BAR = "#4fb66b", "#f39a3a"
LABEL_W = 170
BUILTIN_TAG = tr("[기본] ")


def _disp(presets, name):
    """기본 제공 프리셋만 현재 언어로 표시한다 (저장되는 이름은 그대로 한국어 원문)."""
    return tr(name) if name and presets.is_builtin(name) else name


def _fmt_time(sec: float) -> str:
    sec = int(max(0, sec))
    return tr("{0}분 {1:02d}초").format(sec // 60, sec % 60) if sec >= 60 else tr("{0}초").format(sec)


class VarRow(QWidget):
    """변수 한 줄. 왼쪽 색 막대/배경이 자동(초록) / 수동(주황)을 보여 준다."""

    def __init__(self, vid: str, auto_ctl, parent=None):
        super().__init__(parent)
        self.vid = vid
        self.ctl = auto_ctl
        self._auto = True
        self._refreshing = False
        self.setFixedHeight(22 * PX)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8 * PX, 1 * PX, 3 * PX, 1 * PX)
        lay.setSpacing(2 * PX)
        label = spec.KIND_LABEL if vid == spec.KIND_VAR else spec.VARS_BY_ID[vid]["label"]
        short = label.split(" (")[0]               # 긴 보충 설명은 툴팁으로 (줄 폭 초과로 잘리는 것 방지)
        self.chk = PixelCheck(short)
        self.chk.setFixedWidth(max(LABEL_W * PX // 2 + 40, self.chk.sizeHint().width() + 2 * PX))
        self.chk.setToolTip(label if short != label else "")      # 긴 보충 설명이 잘린 항목만 이름 전체를 보여 줌
        self.chk.toggled.connect(self._toggled)
        lay.addWidget(self.chk)
        self.tag = QLabel()
        self.tag.setFont(body_font())
        self.tag.setFixedWidth(24 * PX)
        lay.addWidget(self.tag)

        self.sp_min = self.sp_max = self.sp_fix = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self._commit_range)
        if vid != spec.KIND_VAR:
            v = spec.VARS_BY_ID[vid]
            self.sp_min = self._spin(v)
            lay.addWidget(self.sp_min)
            sep = QLabel("~")
            sep.setFont(body_font())
            lay.addWidget(sep)
            self.sp_max = self._spin(v)
            lay.addWidget(self.sp_max)
            if vid == spec.DURATION_VAR:
                self.sp_fix = self._spin(v, ranged=False)
                self.sp_fix.valueChanged.connect(self._fix_changed)
                lay.addWidget(self.sp_fix)
        self.lbl_val = QLabel()
        self.lbl_val.setFont(body_font())
        self.lbl_val.setMinimumWidth(52 * PX)
        self.lbl_val.setStyleSheet(f"color:{PAL['gold']};")
        lay.addWidget(self.lbl_val, 1)
        self.btn_reset = None
        if vid != spec.KIND_VAR:
            self.btn_reset = PixelButton("", "reset")
            self.btn_reset.setToolTip(tr("초기화"))
            self.btn_reset.clicked.connect(lambda: self.ctl.reset_var_range(self.vid))
            lay.addWidget(self.btn_reset)

    def _spin(self, v, ranged: bool = True) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sc = v["scale"]
        sp.setDecimals(v["dec"])
        sp.setRange(v["lo"] * sc, v["hi"] * sc)
        sp.setSingleStep(max(1.0, round((v["hi"] - v["lo"]) * sc / 100)))
        sp.setSuffix(v["suffix"].rstrip() if v["suffix"].strip() in ("%",) else "")
        sp.setKeyboardTracking(False)
        sp.setFixedWidth(46 * PX)
        sp.setFont(body_font())
        if ranged:
            sp.valueChanged.connect(lambda _x: None if self._refreshing else self._timer.start())
        return sp

    # ---- 사용자 동작
    def _toggled(self, on: bool):
        if not self._refreshing:
            self.ctl.set_var_auto(self.vid, on)

    def _commit_range(self):
        if self.sp_min is None:
            return
        sc = spec.VARS_BY_ID[self.vid]["scale"]
        ok, _msg = self.ctl.set_var_range(self.vid, self.sp_min.value() / sc, self.sp_max.value() / sc)
        if not ok:                                   # 거부되면 저장돼 있던 값으로 되돌림
            self.refresh(force=True)

    def _fix_changed(self, x: float):
        if not self._refreshing:
            ok, _ = self.ctl.set_duration_manual(x)
            if not ok:
                self.refresh(force=True)

    # ---- 표시 갱신
    def refresh(self, force: bool = False):
        cfg = self.ctl.config()["vars"][self.vid]
        self._refreshing = True
        try:
            self._auto = bool(cfg["auto"])
            self.chk.setChecked(self._auto)
            self.tag.setText(tr("자동") if self._auto else tr("수동"))
            self.tag.setStyleSheet(f"color:{AUTO_BAR if self._auto else MANUAL_BAR};")
            if self.sp_min is not None:
                sc = spec.VARS_BY_ID[self.vid]["scale"]
                for sp, key in ((self.sp_min, "min"), (self.sp_max, "max")):
                    if force or not sp.hasFocus():
                        sp.setValue(cfg[key] * sc)
                if self.sp_fix is not None:
                    if force or not self.sp_fix.hasFocus():
                        self.sp_fix.setValue(cfg["manual"])
                    self.sp_fix.setVisible(not self._auto)
                    self.sp_min.setVisible(self._auto)
                    self.sp_max.setVisible(self._auto)
                    self.layout().itemAt(3).widget().setVisible(self._auto)       # '~'
            self.lbl_val.setText(self.ctl.applied_text(self.vid))        # 자동/수동은 왼쪽 표시가 이미 알려 줌
            self.lbl_val.setStyleSheet(f"color:{PAL['gold'] if self._auto else MANUAL_BAR};")
        finally:
            self._refreshing = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(AUTO_BG if self._auto else MANUAL_BG))
        p.fillRect(0, 0, 4 * PX, self.height(), QColor(AUTO_BAR if self._auto else MANUAL_BAR))
        p.setPen(QColor(PAL["panel_lo"]))
        p.drawRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1))
        p.end()


class AutoWeatherPage(QScrollArea):
    def __init__(self, settings, auto, parent=None):
        super().__init__(parent)
        self.s = settings
        self.auto = auto
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)
        self.setStyleSheet("QScrollArea{background:transparent;}")
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        self.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(5 * PX, 4 * PX, 5 * PX, 4 * PX)
        lay.setSpacing(3 * PX)
        self._refreshing = False
        self.rows: dict[str, VarRow] = {}
        self.kind_chk: dict[str, PixelCheck] = {}
        self.kind_sl: dict[str, PixelSlider] = {}
        self.param_sl: dict[str, PixelSlider] = {}

        self._build_control(lay)
        self._build_presets(lay)
        self._build_kinds(lay)
        self._build_vars(lay)
        self._build_params(lay)
        lay.addStretch(1)

        self._msg_timer = QTimer(self)
        self._msg_timer.setSingleShot(True)
        self._msg_timer.timeout.connect(lambda: self.lbl_msg.setText(""))
        auto.notice.connect(self.show_message)
        auto.state_changed.connect(self.refresh)
        settings.changed.connect(lambda _k: self.refresh())
        self.refresh()

    # ---------------------------------------------------------------- 구성
    def _label(self, text="", dim=False, wrap=True) -> QLabel:
        lb = QLabel(text)
        lb.setFont(body_font())
        lb.setWordWrap(wrap)
        if dim:
            lb.setStyleSheet(f"color:{PAL['dim']};")
        return lb

    def _build_control(self, lay):
        lay.addWidget(PixelSection(tr("자동 날씨 제어")))
        self.lbl_state = self._label()
        self.lbl_state.setStyleSheet(f"color:{PAL['sky']};")
        lay.addWidget(self.lbl_state)
        row = QHBoxLayout()
        row.setSpacing(3 * PX)
        self.btn_start = PixelButton(tr("시작"), "play", kind="accent")
        self.btn_pause = PixelButton(tr("일시정지"), "pause")
        self.btn_stop = PixelButton(tr("중지"), "close")
        self.btn_start.clicked.connect(self._start)
        self.btn_pause.clicked.connect(self._pause_resume)
        self.btn_stop.clicked.connect(self.auto.stop)
        for b in (self.btn_start, self.btn_pause, self.btn_stop):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        row2.setSpacing(3 * PX)
        b_auto = PixelButton(tr("모든 변수 자동"), "repeat")
        b_man = PixelButton(tr("모든 변수 수동"), "lock")
        b_def = PixelButton(tr("기본 설정 복원"), "reset")
        b_auto.clicked.connect(lambda: self.auto.set_all_auto(True))
        b_man.clicked.connect(lambda: self.auto.set_all_auto(False))
        b_def.clicked.connect(self._restore_defaults)
        for b in (b_auto, b_man, b_def):
            row2.addWidget(b)
        row2.addStretch(1)
        lay.addLayout(row2)
        self.lbl_msg = self._label()
        self.lbl_msg.setStyleSheet(f"color:{PAL['gold']};")
        lay.addWidget(self.lbl_msg)

    def _build_presets(self, lay):
        lay.addWidget(PixelSection(tr("프리셋")))
        self.lst = QListWidget()
        self.lst.setFont(body_font())
        self.lst.setFixedHeight(74 * PX)
        self.lst.itemDoubleClicked.connect(lambda _i: self._load_preset())
        lay.addWidget(self.lst)
        row = QHBoxLayout()
        row.setSpacing(3 * PX)
        for text, icon, fn in ((tr("불러오기"), "folder", self._load_preset), (tr("현재 설정 저장"), "save", self._save_preset),
                               (tr("이름 변경"), "gear", self._rename_preset), (tr("삭제"), "trash", self._delete_preset)):
            b = PixelButton(text, icon, kind="danger" if text == "삭제" else "normal")
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.lbl_preset = self._label(dim=True)
        lay.addWidget(self.lbl_preset)

    def _build_kinds(self, lay):
        lay.addWidget(PixelSection(tr("날씨 종류: 사용 여부와 선택 가중치")))
        for kid, name in spec.KINDS:
            row = QHBoxLayout()
            row.setSpacing(3 * PX)
            c = PixelCheck(name)
            c.setFixedWidth(70 * PX)
            c.toggled.connect(lambda v, k=kid: None if self._refreshing else self.auto.set_kind_on(k, v))
            sl = PixelSlider(0, 100, 5, "", value_width=24 * PX)
            sl.valueChanged.connect(lambda v, k=kid: self.auto.set_kind_weight(k, v))
            sl.released.connect(self.auto.save_now)
            row.addWidget(c)
            row.addWidget(sl, 1)
            lay.addLayout(row)
            self.kind_chk[kid], self.kind_sl[kid] = c, sl
        self.lbl_kinds = self._label(dim=True)
        lay.addWidget(self.lbl_kinds)

    def _build_vars(self, lay):
        for title, ids in spec.GROUPS:
            lay.addWidget(PixelSection(tr("변수 자동 조정 - {0}").format(title)))
            if title == "날씨":
                hint = self._label(tr("초록 = 자동 조정 중, 주황 = 수동 고정. 체크를 끄면 현재 값으로 고정되고, 최솟값/최댓값은 숫자를 직접 입력하거나 화살표로 바꿔요."), dim=True)
                lay.addWidget(hint)
            for vid in ids:
                row = VarRow(vid, self.auto)
                self.rows[vid] = row
                lay.addWidget(row)

    def _build_params(self, lay):
        lay.addWidget(PixelSection(tr("변화 방식")))
        for name, (label, _dv) in spec.PARAMS.items():
            row = QHBoxLayout()
            lb = self._label(label, wrap=False)
            lb.setFixedWidth(LABEL_W * PX // 2 + 30)
            sl = PixelSlider(0, 100, 5, "%", value_width=58 * PX // 2 + 12)
            sl.valueChanged.connect(lambda v, n=name: self.auto.set_param(n, v))
            sl.released.connect(self.auto.save_now)
            row.addWidget(lb)
            row.addWidget(sl, 1)
            lay.addLayout(row)
            self.param_sl[name] = sl

    # ---------------------------------------------------------------- 동작
    def show_message(self, text: str):
        self.lbl_msg.setText(text)
        self._msg_timer.start(9000)

    def _start(self):
        ok, msg = self.auto.start()
        if not ok:
            self.show_message(msg)

    def _pause_resume(self):
        if self.auto.core.paused:
            self.auto.resume()
        else:
            self.auto.pause()

    def _restore_defaults(self):
        if QMessageBox.question(self, tr("기본 설정 복원"), tr("자동 날씨 설정(날씨 종류, 범위, 가중치, 변화 방식)을 기본값으로 되돌릴까요?\n"
                                "눈 효과/바람의 수동 설정값과 프리셋은 바뀌지 않아요.")) == QMessageBox.StandardButton.Yes:
            self.auto.reset_defaults()

    def _selected(self):
        it = self.lst.currentItem()
        if it is None:
            return None, False
        name = it.data(Qt.UserRole)
        return name, self.auto.presets.is_builtin(name)

    def _load_preset(self):
        name, _b = self._selected()
        if not name:
            self.show_message(tr("불러올 프리셋을 목록에서 선택해 주세요."))
            return
        ok, msg = self.auto.load_preset(name)
        self.show_message(tr("'{0}' 프리셋을 불러왔어요.").format(_disp(self.auto.presets, name)) if ok else msg)

    def _save_preset(self):
        cur = self.s.get("autoweather.preset")
        name, ok = QInputDialog.getText(self, tr("프리셋 저장"), tr("프리셋 이름:"), text=cur if cur and not self.auto.presets.is_builtin(cur) else "")
        if not ok:
            return
        name = name.strip()
        if self.auto.presets.exists(name) and not self.auto.presets.is_builtin(name):
            if QMessageBox.question(self, tr("프리셋 덮어쓰기"), tr("'{0}' 프리셋이 이미 있어요. 덮어쓸까요?").format(name)) != QMessageBox.StandardButton.Yes:
                return
            ok, msg = self.auto.save_preset(name, overwrite=True)
        else:
            ok, msg = self.auto.save_preset(name)
        self.show_message(tr("'{0}' 프리셋으로 저장했어요.").format(name) if ok else msg)

    def _rename_preset(self):
        name, builtin = self._selected()
        if not name:
            self.show_message(tr("이름을 바꿀 프리셋을 선택해 주세요."))
            return
        if builtin:
            self.show_message(tr("기본 제공 프리셋은 이름을 바꿀 수 없어요."))
            return
        new, ok = QInputDialog.getText(self, tr("프리셋 이름 변경"), tr("새 이름:"), text=name)
        if ok:
            ok2, msg = self.auto.rename_preset(name, new)
            self.show_message(tr("이름을 바꿨어요.") if ok2 else msg)

    def _delete_preset(self):
        name, builtin = self._selected()
        if not name:
            self.show_message(tr("삭제할 프리셋을 선택해 주세요."))
            return
        if builtin:
            self.show_message(tr("기본 제공 프리셋은 삭제할 수 없어요."))
            return
        if QMessageBox.question(self, tr("프리셋 삭제"), tr("'{0}' 프리셋을 삭제할까요?").format(name)) == QMessageBox.StandardButton.Yes:
            ok, msg = self.auto.delete_preset(name)
            self.show_message(tr("삭제했어요.") if ok else msg)

    # ---------------------------------------------------------------- 갱신
    def refresh(self):
        if self._refreshing:
            return
        self._refreshing = True
        try:
            st = self.auto.status()
            cfg = self.auto.config()
            if st["active"] and st["paused"]:
                head = tr("상태: 일시정지 (현재 값 유지 중)")
            elif st["active"]:
                head = tr("상태: 실행 중")
            elif st["phase"] == "release":
                head = tr("상태: 수동 설정으로 돌아가는 중…")
            else:
                head = tr("상태: 꺼짐 (눈 효과/날씨/바람 탭의 수동 설정 사용 중)")
            if st["active"]:
                nm = spec.KIND_NAME.get(st["kind"], "직접 설정")
                nx = spec.KIND_NAME.get(st["next_kind"], "직접 설정")
                head += tr("\n현재 날씨: {0} (남은 시간 {1} / 총 {2})").format(nm, _fmt_time(st['remaining']), _fmt_time(st['period']))
                head += tr("\n다음 날씨 예상: {0}").format(nx)
            self.lbl_state.setText(head)
            self.btn_start.setEnabled(not st["active"])
            self.btn_pause.setEnabled(st["active"])
            self.btn_pause.setText(tr("재개") if st["paused"] else tr("일시정지"))
            self.btn_pause._icon = "play" if st["paused"] else "pause"
            self.btn_pause.update()
            self.btn_stop.setEnabled(st["active"])

            names = [(n, True) for n in self.auto.presets.builtin_names()] + [(n, False) for n in self.auto.presets.user_names()]
            sel = self.lst.currentItem().data(Qt.UserRole) if self.lst.currentItem() else self.s.get("autoweather.preset")
            if [self.lst.item(i).data(Qt.UserRole) for i in range(self.lst.count())] != [n for n, _ in names]:
                self.lst.clear()
                for n, b in names:
                    from PySide6.QtWidgets import QListWidgetItem
                    it = QListWidgetItem((BUILTIN_TAG if b else "") + (tr(n) if b else n))
                    it.setData(Qt.UserRole, n)
                    self.lst.addItem(it)
                    if n == sel:
                        self.lst.setCurrentItem(it)
            last = self.s.get("autoweather.preset")
            self.lbl_preset.setText(tr("마지막으로 불러온/저장한 프리셋: {0}").format(_disp(self.auto.presets, last)) if last else tr("프리셋: 직접 설정한 값"))

            for kid in spec.KIND_IDS:
                c, sl = self.kind_chk[kid], self.kind_sl[kid]
                c.blockSignals(True)
                c.setChecked(cfg["kinds"][kid]["on"])
                c.blockSignals(False)
                if not sl.isDown():
                    sl.setValue(cfg["kinds"][kid]["weight"])
                sl.setEnabled(cfg["kinds"][kid]["on"])
            n_on = len(spec.enabled_kinds(cfg))
            self.lbl_kinds.setText(tr("켜진 날씨가 없어서 자동 날씨를 시작할 수 없어요. 하나 이상 켜 주세요.") if n_on == 0 else
                                   tr("켜진 날씨가 하나뿐이라 그 날씨만 유지돼요.") if n_on == 1 else "")
            self.lbl_kinds.setStyleSheet(f"color:{PAL['gold'] if n_on == 0 else PAL['dim']};")
            for name, sl in self.param_sl.items():
                if not sl.isDown():
                    sl.setValue(cfg[name])
            for row in self.rows.values():
                row.refresh()
        finally:
            self._refreshing = False
