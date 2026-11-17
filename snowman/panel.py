"""눈사람 공방 패널 (픽셀 스타일): 눈덩이 만들기, 장식용 눈사람 선택, 꾸미기, 선택한 눈사람 관리, 조립 상태 표시.

필요할 때만 열리는 작은 창이다 (메인 위젯 메뉴 / 트레이 메뉴에서 연다). 화면의 눈사람 선택은 월드가 마우스 클릭으로 처리하고
(오버레이는 클릭이 통과하므로 버튼 상태를 직접 읽는다), 이 패널은 선택된 대상을 보여주고 조작한다.
"""
from __future__ import annotations
from core.i18n import tr


from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QScrollArea, QStackedWidget,
                               QVBoxLayout, QWidget)

from widget.pixel_ui import (PAL, PX, C, ConfirmButton, PixelButton, PixelCheck, PixelSection, PixelSlider, PixelWindow,
                             body_font, pixel_box)

from . import model as M

PAGES = ((tr("만들기"), "snow"), (tr("꾸미기"), "gift"), (tr("관리"), "gear"))
TYPE_TAG = {M.DYNAMIC: tr("직접 제작"), M.DECORATIVE: tr("장식용"), "ball": tr("눈덩이")}


class _Swatch(QAbstractButton):
    """색상 선택 칸."""

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(13 * PX, 13 * PX)
        self.setToolTip(name)

    def sizeHint(self) -> QSize:
        return QSize(13 * PX, 13 * PX)

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        pixel_box(p, r, M.COLORS[self.name], PAL["gold"] if self.isChecked() else PAL["border_dark"])
        p.end()


class _Progress(QWidget):
    """조립 진행 막대 (조립 가능 상태일 때만 채워진다)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.setFixedHeight(8 * PX)

    def set_value(self, v: float):
        if abs(v - self.value) > 0.005:
            self.value = v
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        pixel_box(p, r, PAL["panel"], PAL["border_dark"], lo=PAL["panel_lo"])
        if self.value > 0:
            p.fillRect(QRect(r.x() + PX, r.y() + PX, int((r.width() - 2 * PX) * self.value), r.height() - 2 * PX),
                       C("gold"))
        p.end()


def _clear(layout):
    while layout.count():
        it = layout.takeAt(0)
        w = it.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif it.layout() is not None:
            _clear(it.layout())


def _label(text: str, color: str = "text", wrap: bool = True) -> QLabel:
    lb = QLabel(text)
    lb.setFont(body_font())
    lb.setWordWrap(wrap)
    lb.setStyleSheet(f"color:{PAL.get(color, color)}; background:transparent;")
    return lb


class SnowmanPanel(PixelWindow):
    def __init__(self, manager, parent=None):
        super().__init__(tr("눈사람 공방"), "snow", parent)
        self.m = manager
        self.w = manager.world
        self.s = manager.s
        self._sig = None
        self._ui_dirty = True
        self._sel_decor = None
        self._page_i = 0
        self._note_t = 0.0
        self.w.on_select = self._on_select

        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(4 * PX, 4 * PX, 4 * PX, 4 * PX)
        lay.setSpacing(3 * PX)
        self.status = _label("", "gold")
        self.prog = _Progress()
        self.note = _label("", "snow")
        lay.addWidget(self.status)
        lay.addWidget(self.prog)
        lay.addWidget(self.note)

        nav = QHBoxLayout()
        nav.setSpacing(2 * PX)
        self._nav = []
        for i, (t, icon) in enumerate(PAGES):
            b = PixelButton(t, icon)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, i=i: self.set_page(i))
            nav.addWidget(b)
            self._nav.append(b)
        lay.addLayout(nav)

        self.stack = QStackedWidget()
        self._holders = []
        for _ in PAGES:
            holder = QWidget()
            holder.setStyleSheet("background:transparent;")
            v = QVBoxLayout(holder)
            v.setContentsMargins(0, 2 * PX, 0, 0)
            v.setSpacing(3 * PX)
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setFrameShape(QFrame.NoFrame)
            sc.setStyleSheet("QScrollArea{background:transparent;}")
            sc.setWidget(holder)
            self.stack.addWidget(sc)
            self._holders.append(v)
        lay.addWidget(self.stack, 1)

        self.setFixedSize(290 * PX, 360 * PX)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._refresh)
        self.set_page(0)

    # ------------------------------------------------------------------ 열기/닫기
    def showEvent(self, e):
        super().showEvent(e)
        self._ui_dirty = True
        self._timer.start()
        self._refresh()

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def set_page(self, i: int):
        self._page_i = i
        for k, b in enumerate(self._nav):
            b.setChecked(k == i)
        self.stack.setCurrentIndex(i)
        self._ui_dirty = True
        self._refresh()

    def _on_select(self, eid):
        self._sel_decor = None
        self._ui_dirty = True

    def flash(self, text: str):
        self.note.setText(text)
        self._note_t = 3.0

    # ------------------------------------------------------------------ 갱신
    def _sel(self):
        eid = self.w.selected
        if eid is not None and self.w.kind_of(eid) is None:
            return None
        return eid

    def _sig_now(self):
        eid = self._sel()
        dids = tuple(d["id"] for _o, d in self.w.decor_list(eid)) if eid else ()
        return (self._page_i, eid, tuple(self.w.snowmen), tuple(b for b in self.w.balls if not self.w.balls[b].sid),
                dids, self._sel_decor)

    def _refresh(self):
        w = self.w
        txt = w.status_text()
        self.status.setText(txt)
        prog = max((h[2] for h in w.hints), default=0.0)
        self.prog.set_value(prog)
        if self._note_t > 0:
            self._note_t -= 0.25
            if self._note_t <= 0:
                self.note.setText("")
        sig = self._sig_now()
        if self._ui_dirty or sig != self._sig:
            self._sig = sig
            self._ui_dirty = False
            self._rebuild()

    def _rebuild(self):
        i = self._page_i
        v = self._holders[i]
        _clear(v)
        (self._build_make, self._build_decor, self._build_manage)[i](v)
        v.addStretch(1)

    # ------------------------------------------------------------------ 공통 이름
    def _name(self, eid) -> str:
        k = self.w.kind_of(eid)
        if k is None:
            return ""
        if k == "ball":
            ids = [b for b in self.w.balls if not self.w.balls[b].sid]
        else:
            ids = [i for i, s in self.w.snowmen.items() if s.type == k]
        n = ids.index(eid) + 1 if eid in ids else 0
        return tr("[{0}] {1}번").format(TYPE_TAG[k], n)

    def _setting_check(self, text: str, key: str) -> PixelCheck:
        c = PixelCheck(text)
        c.blockSignals(True)
        c.setChecked(bool(self.s.get(key)))
        c.blockSignals(False)
        c.toggled.connect(lambda on, k=key: self.s.set(k, bool(on), save=True))
        return c

    def _setting_slider(self, label: str, key: str, lo, hi, step) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(_label(label, wrap=False))
        sl = PixelSlider(lo, hi, step, "%", value_width=44)
        sl.setValue(float(self.s.get(key)))
        sl.valueChanged.connect(lambda val, k=key: self.s.set(k, int(val)))
        sl.released.connect(lambda: self.s.save_now())
        h.addWidget(sl, 1)
        return box

    # ------------------------------------------------------------------ 만들기
    def _build_make(self, v):
        v.addWidget(PixelSection(tr("눈덩이 만들기")))
        row = QHBoxLayout()
        row.addWidget(_label(tr("처음 크기"), wrap=False))
        self._size = PixelSlider(8, 34, 1, "", value_width=30)
        self._size.setValue(getattr(self, "_size_v", 16))
        self._size.valueChanged.connect(lambda val: setattr(self, "_size_v", val))
        row.addWidget(self._size, 1)
        v.addLayout(row)
        b = PixelButton(tr("눈덩이 만들기"), "snow", kind="accent")
        b.clicked.connect(self._spawn)
        v.addWidget(b)
        v.addWidget(_label(tr("떨어진 눈덩이를 굴려 키우고, 큰 것부터 쌓아 눈사람을 만들어요."), "dim"))
        v.addWidget(PixelSection(tr("장식용 눈사람 (녹지 않아요)")))
        for key, (name, _decor) in M.PRESETS.items():
            pb = PixelButton(name, "gift")
            pb.clicked.connect(lambda _=False, k=key: self._add_deco(k))
            v.addWidget(pb)
        v.addWidget(PixelSection(tr("설정")))
        v.addWidget(self._setting_check(tr("눈덩이/눈사람 기능 켜기"), "snowman.enabled"))
        v.addWidget(self._setting_check(tr("마우스를 스치면 밀기"), "snowman.mouse_push"))
        v.addWidget(self._setting_check(tr("클릭해서 잡기/선택"), "snowman.grab"))
        v.addWidget(self._setting_slider(tr("성장 속도"), "snowman.growth", 0, 300, 10))
        v.addWidget(self._setting_slider(tr("미는 힘"), "snowman.push_gain", 20, 300, 10))

    def _spawn(self):
        bid = self.w.spawn_ball(radius=float(self._size.value()))
        if not bid:
            self.flash(tr("눈덩이는 최대 {0}개예요").format(M.LIMITS['balls']))
            return
        self.w.select(bid)
        self.flash(tr("눈덩이를 만들었어요"))

    def _add_deco(self, preset: str):
        sid = self.w.add_decorative(preset)
        if not sid:
            self.flash(tr("장식용 눈사람은 최대 20개예요"))
            return
        self.w.select(sid)
        self.flash(tr("장식용 눈사람을 놓았어요"))

    # ------------------------------------------------------------------ 꾸미기
    def _build_decor(self, v):
        eid = self._sel()
        k = self.w.kind_of(eid) if eid else None
        if k not in (M.DYNAMIC, M.DECORATIVE):
            msg = (tr("눈덩이는 먼저 눈사람으로 쌓아야 꾸밀 수 있어요.") if k == "ball"
                   else tr("꾸밀 눈사람을 화면에서 클릭해 선택하세요."))
            v.addWidget(_label(msg, "dim"))
            return
        v.addWidget(_label(tr("선택: {0}").format(self._name(eid)), "gold"))
        v.addWidget(PixelSection(tr("장식 추가")))
        # 2열 배치
        rows = [M.KIND_ORDER[i:i + 2] for i in range(0, len(M.KIND_ORDER), 2)]
        for pair in rows:
            h = QHBoxLayout()
            h.setSpacing(2 * PX)
            for kind in pair:
                b = PixelButton(M.KINDS[kind][0])
                b.clicked.connect(lambda _=False, kd=kind: self._add_decor(kd))
                h.addWidget(b)
            v.addLayout(h)
        decs = self.w.decor_list(eid)
        v.addWidget(PixelSection(tr("붙인 장식 {0}").format(len(decs))))
        if not decs:
            v.addWidget(_label(tr("아직 장식이 없어요."), "dim"))
        for _o, d in decs:
            b = PixelButton(("▶ " if d["id"] == self._sel_decor else "") + M.KINDS[d["kind"]][0], kind="flat")
            b.clicked.connect(lambda _=False, did=d["id"]: self._pick_decor(did))
            v.addWidget(b)
        cur = next((d for _o, d in decs if d["id"] == self._sel_decor), None)
        if cur is not None:
            self._build_editor(v, eid, cur)

    def _add_decor(self, kind: str):
        eid = self._sel()
        did = self.w.add_decor(eid, kind) if eid else ""
        if not did:
            self.flash(tr("장식은 눈사람 하나에 최대 {0}개예요").format(M.LIMITS['decor']))
            return
        self._sel_decor = did
        self._ui_dirty = True
        self.flash(tr("{0}을(를) 붙였어요").format(M.KINDS[kind][0]))

    def _pick_decor(self, did: str):
        self._sel_decor = did
        self._ui_dirty = True

    def _build_editor(self, v, eid, d):
        did = d["id"]
        styles = M.KINDS[d["kind"]][1]
        v.addWidget(PixelSection(tr("{0} 편집").format(M.KINDS[d['kind']][0])))
        names = dict(styles)
        sb = PixelButton(tr("종류: {0}  (눌러서 바꾸기)").format(names.get(d['style'], d['style'])))
        sb.clicked.connect(lambda: self._cycle_style(eid, d))
        v.addWidget(sb)
        sw = QHBoxLayout()
        sw.setSpacing(PX)
        for name in M.COLORS:
            s = _Swatch(name)
            s.setChecked(name == d["color"])
            s.clicked.connect(lambda _=False, n=name: self._set_color(eid, did, n))
            sw.addWidget(s)
        sw.addStretch(1)
        v.addLayout(sw)
        for label, key, lo, hi in ((tr("크기"), "size", 40, 220), (tr("가로"), "dx", -60, 60), (tr("세로"), "dy", -60, 60)):
            h = QHBoxLayout()
            h.addWidget(_label(label, wrap=False))
            sl = PixelSlider(lo, hi, 1, "", value_width=36)
            sl.setValue(float(d[key]))
            sl.valueChanged.connect(lambda val, k=key: self.w.update_decor(eid, did, **{k: int(val)}))
            h.addWidget(sl, 1)
            v.addLayout(h)
        rm = PixelButton(tr("이 장식 제거"), "trash", kind="danger")
        rm.clicked.connect(lambda: self._remove_decor(eid, did))
        v.addWidget(rm)

    def _cycle_style(self, eid, d):
        keys = [k for k, _ in M.KINDS[d["kind"]][1]]
        nxt = keys[(keys.index(d["style"]) + 1) % len(keys)] if d["style"] in keys else keys[0]
        self.w.update_decor(eid, d["id"], style=nxt)
        self._ui_dirty = True

    def _set_color(self, eid, did, name):
        self.w.update_decor(eid, did, color=name)
        self._ui_dirty = True

    def _remove_decor(self, eid, did):
        self.w.remove_decor(eid, did)
        self._sel_decor = None
        self._ui_dirty = True
        self.flash(tr("장식을 제거했어요"))

    # ------------------------------------------------------------------ 관리
    def _build_manage(self, v):
        w = self.w
        eid = self._sel()
        v.addWidget(PixelSection(tr("선택한 대상")))
        if eid is None:
            v.addWidget(_label(tr("화면의 눈덩이/눈사람을 클릭하면 선택돼요."), "dim"))
        else:
            k = w.kind_of(eid)
            v.addWidget(_label(self._name(eid), "gold"))
            note = {M.DYNAMIC: tr("직접 제작: 온도가 높으면 녹아요. 장식은 녹을 때 주변에 남아요."),
                    M.DECORATIVE: tr("장식용: 온도와 상관없이 녹지 않아요."), "ball": tr("눈덩이: 굴리면 눈을 모아 커져요.")}[k]
            v.addWidget(_label(note, "dim"))
            r = QHBoxLayout()
            r.setSpacing(2 * PX)
            dup = PixelButton(tr("복제"), "box")
            dup.clicked.connect(self._duplicate)
            # 눈사람은 되돌릴 수 없으므로 두 번 눌러야 지워진다 (대기 중 선택이 바뀌면 확인으로 치지 않음)
            dele = ConfirmButton(tr("삭제"), "trash", key_fn=self._sel)
            dele.confirmed.connect(self._delete)
            r.addWidget(dup)
            r.addWidget(dele)
            v.addLayout(r)
            if k == M.DYNAMIC:
                ds = PixelButton(tr("분리하기 (다시 조립 가능)"), "reset")
                ds.clicked.connect(self._disassemble)
                v.addWidget(ds)
            if k == M.DECORATIVE:
                sn = w.snowmen[eid]
                for label, lo, hi, step, cur, suffix, fn in (
                        (tr("크기"), 40, 300, 5, sn.scale * 100.0, "%", lambda val: w.set_deco(eid, scale=val / 100.0)),
                        (tr("회전"), -60, 60, 1, sn.rot, "°", lambda val: w.set_deco(eid, rot=val))):
                    h = QHBoxLayout()
                    h.addWidget(_label(label, wrap=False))
                    sl = PixelSlider(lo, hi, step, suffix, value_width=44)
                    sl.setValue(float(cur))
                    sl.valueChanged.connect(fn)
                    h.addWidget(sl, 1)
                    v.addLayout(h)
            un = PixelButton(tr("선택 해제"), kind="flat")
            un.clicked.connect(lambda: w.select(None))
            v.addWidget(un)
        v.addWidget(PixelSection(tr("눈사람 목록 {0}").format(len(w.snowmen))))
        if not w.snowmen:
            v.addWidget(_label(tr("아직 눈사람이 없어요."), "dim"))
        for sid in w.snowmen:
            b = PixelButton(("▶ " if sid == eid else "") + self._name(sid), kind="flat")
            b.clicked.connect(lambda _=False, i=sid: w.select(i))
            v.addWidget(b)
        loose = [b for b in w.balls if not w.balls[b].sid]
        if loose:
            v.addWidget(PixelSection(tr("낱개 눈덩이 {0}").format(len(loose))))
            for bid in loose:
                b = PixelButton(("▶ " if bid == eid else "") + self._name(bid), kind="flat")
                b.clicked.connect(lambda _=False, i=bid: w.select(i))
                v.addWidget(b)
        if w.props:
            cl = PixelButton(tr("남겨진 장식 치우기 ({0})").format(len(w.props)), "trash")
            cl.clicked.connect(self._clear_props)
            v.addWidget(cl)

    def _duplicate(self):
        eid = self._sel()
        nid = self.w.duplicate(eid) if eid else ""
        if nid:
            self.w.select(nid)
            self.flash(tr("복제했어요"))
        else:
            self.flash(tr("더 만들 수 없어요 (최대 개수)"))

    def _delete(self):
        eid = self._sel()
        if eid:
            name = self._name(eid)               # 지우기 전에 이름을 읽어 둔다
            self.w.remove(eid)
            self.flash(tr("{0}을(를) 삭제했어요").format(name))
        self._ui_dirty = True

    def _disassemble(self):
        eid = self._sel()
        if eid:
            self.w.disassemble(eid)
            self.flash(tr("눈덩이로 분리했어요"))
        self._ui_dirty = True

    def _clear_props(self):
        self.w.clear_props()
        self._ui_dirty = True
