"""스노우볼 창: 새 아이소메트릭 스노우볼 시스템의 관리 / 꾸미기 / 눈 설정 UI.

기존 HTML(QtWebEngine) 스노우볼을 대체한다. 창과 열기 동작(open_snowglobe)은 그대로 유지한다.
 - 왼쪽: 스노우볼 목록 + 추가 / 복제 / 삭제
 - 가운데: 선택한 스노우볼 미리보기 (클릭 = 흔들기, 끌기 = 직접 흔들기, 꾸미기 탭에서는 장식 배치 / 이동)
 - 오른쪽: [기본] 외형 · 배경 · 크기  [꾸미기] 장식  [눈 설정] 비율 · 양 · 크기 · 속도  [흔들기] 방식 · 힘 · 자동 흔들기
"""
from __future__ import annotations
from core.i18n import tr


from PySide6.QtCore import QElapsedTimer, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLayout, QSizePolicy, QVBoxLayout, QWidget)

from snowglobe import catalog as C
from snowglobe import model as M
from snowglobe.manager import GlobeManager
from snowglobe.store import MAX_GLOBES

from .pixel_extra import PixelChoice, PixelTile
from .pixel_ui import (PX, ConfirmButton, PixelButton, PixelCheck, PixelPanel, PixelSection, PixelSlider, PixelWindow,
                       WrapLabel, body_font)


def _thumb_state(g: dict | None = None, **over) -> dict:
    """그림 타일용 정지 장면(눈송이 없음). g 가 있으면 그 스노우볼 그대로, 없으면 기본 장면에 over 만 바꾼다."""
    if g is not None:
        return g
    st = {"background": next(iter(C.BACKGROUNDS)), "design": "classic", "decor": [], "snow": {"size": 1.0}}
    st.update(over)
    return st

S = 3                                   # 미리보기 확대 배율


class GlobeCanvas(QWidget):
    """선택한 스노우볼의 미리보기. view 모드: 흔들기 / edit 모드: 장식 배치와 이동 (X/Y 2D 좌표만)."""
    selection_changed = Signal(object)      # 선택한 장식 id 또는 None
    place_finished = Signal()
    place_failed = Signal(str)              # 장식을 놓지 못했을 때 이유 ("full")

    def __init__(self, mgr: GlobeManager, parent=None):
        super().__init__(parent)
        self.mgr = mgr
        self.mode = "view"
        self.place_kind: str | None = None
        self.sel_item: str | None = None
        self._hover = None
        self._drag_off = None
        self._down = False
        self._moved = False
        self._press = None
        self._lt = QElapsedTimer()
        self._last = None
        self._vel = (0.0, 0.0)
        self._acc = (0.0, 0.0)
        self.setFixedSize(C.GW * S, C.GH * S)
        self.setFont(body_font())
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)

    def gid(self):
        return self.mgr.selected

    def _logical(self, pos):
        return pos.x() / S, pos.y() / S

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0c1626"))
        gid = self.gid()
        if gid is None or self.mgr.frame(gid) is None:
            p.setPen(QColor("#9fb4d0"))
            p.setFont(self.font())
            p.drawText(self.rect().adjusted(8 * PX, 0, -8 * PX, 0), Qt.AlignCenter | Qt.TextWordWrap,
                       tr("왼쪽의 '스노우볼 추가'를 눌러\n첫 스노우볼을 만들어 보세요"))
            p.end()
            return
        ph = self.mgr.physics(gid)
        jx, jy = (ph.jolt if ph else (0.0, 0.0))
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawImage(QRect(int(jx * S), int(jy * S), C.GW * S, C.GH * S), self.mgr.frame(gid))
        if self.mode == "edit":
            pen = QPen(QColor(255, 216, 74, 150), PX, Qt.DotLine)          # 배치 가능 영역(바닥 타원)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(C.GX * S, C.GY * S), C.GRX * S, C.GRY * S)
            g = self.mgr.get(gid)
            for it in g["decor"]:
                if it["id"] == self.sel_item:
                    x0, x1, y0, y1 = M.item_extent(it["kind"], it["scale"], it["rot"])
                    p.setPen(QPen(QColor("#ffd84a"), PX, Qt.DashLine))
                    p.drawRect(int((it["x"] + x0 - 1) * S), int((it["y"] + y0 - 1) * S),
                               int((x1 - x0 + 2) * S), int((y1 - y0 + 2) * S))
            if self.place_kind and self._hover is not None:               # 놓기 전 미리 보기(반투명)
                hx, hy = M.clamp_to_ground(*self._hover)
                im = self.mgr.renderer.sprite(self.place_kind, 1.0)
                p.setOpacity(0.6)
                p.drawImage(QRect(int((hx - im.width() / 2.0) * S), int((hy - im.height()) * S),
                                  im.width() * S, im.height() * S), im)
                p.setOpacity(1.0)
        p.end()

    # ------------------------------------------------------------ 마우스
    def mouseMoveEvent(self, e):
        lx, ly = self._logical(e.position())
        self._hover = (lx, ly)
        gid = self.gid()
        if gid is None:
            return
        if self._down and self.mode == "edit" and self.sel_item and self._drag_off is not None:
            self.mgr.update_decor(gid, self.sel_item, x=lx - self._drag_off[0], y=ly - self._drag_off[1])
            self._moved = True
        elif self._down and self.mode == "view":
            self._moved = self._moved or (abs(e.position().x() - self._press.x()) + abs(e.position().y() - self._press.y()) > 4)
            self._sample(lx, ly)
        self.update()

    def _sample(self, lx, ly):
        """미리보기에서 끈 마우스 움직임을 가속도로 바꿔 눈에 전달 (직접 흔들기)."""
        if not self._lt.isValid():
            self._lt.start()
            self._last = (lx, ly)
            return
        dt = self._lt.elapsed() / 1000.0
        if dt < 0.016:
            return
        self._lt.restart()
        vx, vy = (lx - self._last[0]) / dt, (ly - self._last[1]) / dt
        ax, ay = (vx - self._vel[0]) / dt, (vy - self._vel[1]) / dt
        self._acc = (self._acc[0] * 0.5 + ax * 0.5, self._acc[1] * 0.5 + ay * 0.5)
        self._vel, self._last = (vx, vy), (lx, ly)
        if abs(self._acc[0]) + abs(self._acc[1]) > 60:
            self.mgr.apply_accel(self.gid(), self._acc[0], self._acc[1])

    def mousePressEvent(self, e):
        gid = self.gid()
        self.setFocus()
        if gid is None:
            return
        lx, ly = self._logical(e.position())
        if e.button() == Qt.RightButton:
            if self.place_kind:
                self.place_kind = None
                self.place_finished.emit()
                self.update()
            return
        if e.button() != Qt.LeftButton:
            return
        self._down, self._moved, self._press = True, False, e.position()
        if self.mode == "edit":
            if self.place_kind:
                iid = self.mgr.add_decor(gid, self.place_kind, lx, ly)      # 클릭한 2D 좌표에 배치
                if iid:
                    self._select(iid)
                elif len(self.mgr.decor_items(gid)) >= C.MAX_DECOR:
                    self.place_failed.emit("full")             # 가득 차서 못 놓았을 때 아무 반응 없이 끝나지 않게 알린다
                if not (e.modifiers() & Qt.ShiftModifier):
                    self.place_kind = None
                    self.place_finished.emit()
                self._down = False
            else:
                hit = self.mgr.hit_decor(gid, lx, ly)
                self._select(hit)
                self._drag_off = None
                if hit:
                    it = next(i for i in self.mgr.decor_items(gid) if i["id"] == hit)
                    self._drag_off = (lx - it["x"], ly - it["y"])
        else:
            self._lt.invalidate()
            self._vel = self._acc = (0.0, 0.0)
            self._last = (lx, ly)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self._down and self.mode == "view" and not self._moved and self.gid():
            self.mgr.click(self.gid())                 # 가볍게 클릭 = 자동 흔들기
        self._down = False
        self._drag_off = None

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def keyPressEvent(self, e):
        gid = self.gid()
        if e.key() == Qt.Key_Escape and self.place_kind:
            self.place_kind = None
            self.place_finished.emit()
            self.update()
        elif e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.mode == "edit" and gid and self.sel_item:
            self.mgr.remove_decor(gid, self.sel_item)
            self._select(None)
        else:
            e.ignore()

    def _select(self, iid):
        if iid != self.sel_item:
            self.sel_item = iid
        self.selection_changed.emit(iid)


class SnowGlobeWindow(PixelWindow):
    def __init__(self, mgr: GlobeManager, parent=None):
        super().__init__(tr("스노우볼"), "globe", parent)
        self.mgr = mgr
        self._busy = False
        self._prev_gid: str | None = None
        self._list_sig = None
        avail = QGuiApplication.primaryScreen().availableGeometry()
        self.setFixedSize(min(520 * PX, max(640, avail.width() - 40)), min(344 * PX, max(480, avail.height() - 40)))
        # 창 크기는 실행 중 절대 바뀌지 않게: 안쪽 내용이 아무리 커져도 창을 키우거나 밀지 않는다
        self._root.setSizeConstraint(QLayout.SetNoConstraint)
        root = QHBoxLayout(self.body)
        root.setContentsMargins(4 * PX, 4 * PX, 4 * PX, 4 * PX)
        root.setSpacing(4 * PX)
        root.addWidget(self._build_list())
        root.addWidget(self._build_center())
        root.addWidget(self._build_right(), 1)
        self._fit_height_once(root)
        mgr.changed.connect(self._on_structure)
        mgr.globe_changed.connect(self._on_globe_changed)
        mgr.frame_ready.connect(self._on_frame)
        self._on_structure()

    def _fit_height_once(self, root):
        """스크롤이 없으므로 가장 높은 칸의 내용이 들어가도록 창 높이를 열 때 한 번만 맞춘다 (화면보다 커지지는 않음).
        그 뒤에는 setFixedSize 그대로라 실행 중 창 크기는 바뀌지 않는다."""
        need = 0
        for i in range(root.count()):
            wd = root.itemAt(i).widget()
            if wd is not None:
                need = max(need, wd.sizeHint().height())
        chrome = self.TITLE_H + PX + 3 * PX + 8 * PX              # 제목줄 + 바깥 여백 + 본문 여백
        avail = QGuiApplication.primaryScreen().availableGeometry()
        h = min(max(self.height(), need + chrome), max(480, avail.height() - 40))
        self.setFixedSize(self.width(), h)

    # ------------------------------------------------------------ 왼쪽: 목록
    def _build_list(self):
        w = QWidget()
        w.setFixedWidth(104 * PX)                       # "스노우볼 추가"(아이콘 포함)와 "정말 삭제?"가 잘리지 않는 폭
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3 * PX)
        v.addWidget(PixelSection(tr("스노우볼")))
        self._list_host = QWidget()                     # 선반: 스크롤 없이 12개가 3열 x 4줄로 모두 들어온다
        self._list_host.setStyleSheet("background:transparent;")
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(0)
        v.addWidget(self._list_host, 1)
        self.lbl_gname = WrapLabel()                    # 선반 캡션 (선택/마우스를 올린 스노우볼 이름)
        self.lbl_gname.setFont(body_font())
        self.lbl_gname.setWordWrap(True)                # 이름이 길어도 잘리지 않고 다음 줄로
        self.lbl_gname.setStyleSheet("color:#f3e6c4;")
        v.addWidget(self.lbl_gname)
        self.lbl_gcount = WrapLabel()                   # "3 / 12" - 가득 차면 금색으로 바뀌어 추가가 막힌 이유를 알려 줌
        self.lbl_gcount.setFont(body_font())
        v.addWidget(self.lbl_gcount)
        self.btn_add = PixelButton(tr("스노우볼 추가"), "globe", kind="accent")
        self.btn_add.clicked.connect(self._add_globe)
        self.btn_dup = PixelButton(tr("복제"), "box")
        self.btn_dup.clicked.connect(self._dup_globe)
        # 스노우볼은 장식·눈 설정까지 함께 사라지므로 두 번 눌러야 지워진다
        self.btn_del = ConfirmButton(tr("삭제"), "trash", key_fn=lambda: self.mgr.selected)
        self.btn_del.confirmed.connect(self._del_globe)
        for b in (self.btn_add, self.btn_dup, self.btn_del):
            v.addWidget(b)
        return w

    def _pick_globe(self, gid: str):
        self.mgr.select(gid)
        self._list_sig = None                # 이미 선택된 항목을 다시 눌러도 체크 표시가 어긋나지 않게 다시 그림
        self._rebuild_list()

    def _rebuild_list(self):
        sig = tuple((gid, self.mgr.get(gid)["name"], self.mgr.get(gid)["design"], self.mgr.get(gid)["background"],
                     self.mgr.get(gid)["visible"], repr(self.mgr.get(gid)["decor"]), gid == self.mgr.selected)
                    for gid in self.mgr.order)
        if sig == self._list_sig:
            return                           # 목록 표시가 같으면 다시 만들지 않음 (장식을 끄는 중 깜빡임 방지)
        self._list_sig = sig
        while self._list_lay.count():
            it = self._list_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        host = QWidget()
        host.setStyleSheet("background:transparent;")
        g = QGridLayout(host)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(2 * PX)
        for i, gid in enumerate(self.mgr.order):
            gl = self.mgr.get(gid)
            name = gl["name"] or C.DESIGNS[gl["design"]]["name"]
            t = PixelTile(self.mgr.renderer.render(gl, []), name + ("" if gl["visible"] else tr(" (숨김)")),
                          26 * PX, 30 * PX, badge=str(i + 1), dim=not gl["visible"])
            t.setChecked(gid == self.mgr.selected)
            t.clicked.connect(lambda _=False, i_=gid: self._pick_globe(i_))
            t.hovered.connect(self._shelf_caption)
            g.addWidget(t, i // 3, i % 3)
        g.setRowStretch(len(self.mgr.order) // 3 + 1, 1)
        self._list_lay.addWidget(host)
        self._list_lay.addStretch(1)
        self._shelf_caption(None)

    def _shelf_caption(self, hovered):
        """선반 아래 한 줄: 마우스를 올린 스노우볼, 없으면 선택한 스노우볼의 이름."""
        gid = self.mgr.selected
        name = hovered
        if name is None and gid is not None:
            gl = self.mgr.get(gid)
            name = gl["name"] or C.DESIGNS[gl["design"]]["name"]
        self.lbl_gname.setText(name or "")

    # ------------------------------------------------------------ 가운데: 미리보기
    def _build_center(self):
        w = QWidget()
        w.setFixedWidth(C.GW * S + 8 * PX)           # 스노우볼을 만들거나 안내 글이 바뀌어도 가운데 칸 폭은 그대로
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3 * PX)
        self.canvas = GlobeCanvas(self.mgr)
        self.canvas.selection_changed.connect(lambda _i: self._refresh_decor())
        self.canvas.place_finished.connect(self._sync_place_buttons)
        self.canvas.place_failed.connect(lambda _why: self._flash(tr("장식은 스노우볼 하나에 최대 {0}개예요").format(C.MAX_DECOR)))
        frame = PixelPanel(fill="shadow")                 # 미리보기 액자
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(4 * PX, 4 * PX, 4 * PX, 4 * PX)
        fl.addWidget(self.canvas, 0, Qt.AlignCenter)
        v.addWidget(frame)
        self.btn_shake = PixelButton(tr("흔들기"), "sparkle", kind="accent")
        self.btn_shake.clicked.connect(lambda: self.mgr.selected and self.mgr.shake(self.mgr.selected))
        v.addWidget(self.btn_shake)
        v.addWidget(PixelSection(tr("바탕화면")))             # 바탕화면에서 보이는 모습: 표시 / 위치 고정 / 크기를 한곳에
        row = QHBoxLayout()
        row.setSpacing(3 * PX)
        self.chk_vis = PixelCheck(tr("표시"))
        self.chk_vis.toggled.connect(self._on_visible)
        self.chk_lock = PixelCheck(tr("위치 고정"))
        self.chk_lock.toggled.connect(lambda v: self._set(position_locked=bool(v)))
        row.addWidget(self.chk_vis)
        row.addWidget(self.chk_lock, 1)
        v.addLayout(row)
        size_labels = []
        self.sl_size = self._slider(v, size_labels, tr("화면 크기"), C.GLOBE_SIZE_MIN, C.GLOBE_SIZE_MAX, 1, tr(" 배"),
                                    lambda x: self._set(size=int(x)))
        self._fit(size_labels)
        self.hint = WrapLabel()
        self.hint.setFont(body_font())
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color:#9fb4d0;")
        v.addWidget(self.hint)
        self.note = WrapLabel()                         # 방금 한 동작의 결과 (3초 뒤 사라짐)
        self.note.setFont(body_font())
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color:#ffd35a;")
        v.addWidget(self.note)
        self._note_timer = QTimer(self)
        self._note_timer.setSingleShot(True)
        self._note_timer.timeout.connect(lambda: self.note.setText(""))
        v.addStretch(1)
        self._update_hint()
        return w

    def _update_hint(self):
        """현재 모드를 글머리로 알린다: 보기(흔들기)와 꾸미기(장식 배치/이동)는 같은 미리보기를 다르게 다룬다."""
        if self.mgr.selected is None:
            self.hint.setText(tr("'스노우볼 추가'로 만들어 보세요."))
        elif self.canvas.mode == "edit":
            self.hint.setText(tr("장식을 고르고 점선 안을 클릭해 놓아요. 끌면 이동, Delete로 삭제."))
        else:
            self.hint.setText(tr("클릭하면 흔들리고, 끌면 직접 흔들어요."))

    def _flash(self, text: str):
        self.note.setText(text)
        self._note_timer.start(3000)

    # ------------------------------------------------------------ 오른쪽: 패널
    def _scroll_page(self):
        """페이지 하나. 이름은 예전 그대로지만 스크롤 영역이 아니다: 내용이 모두 창 안에 들어오도록 짜여 있다."""
        page = QWidget()
        page.setObjectName("sgBody")
        page.setStyleSheet("#sgBody{background:transparent;}")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(4 * PX, 3 * PX, 4 * PX, 3 * PX)
        lay.setSpacing(3 * PX)
        return page, lay

    def _row(self, lay, labels: list, label: str, widget):
        row = QHBoxLayout()
        row.setSpacing(3 * PX)
        lb = WrapLabel(label)
        lb.setFont(body_font())
        labels.append(lb)
        row.addWidget(lb)
        row.addWidget(widget, 1)
        lay.addLayout(row)

    def _fit(self, labels: list):
        fm = QFontMetrics(body_font())
        w = max(fm.horizontalAdvance(lb.text()) for lb in labels) + 3 * PX
        for lb in labels:
            lb.setFixedWidth(w)

    def _slider(self, lay, labels, label, lo, hi, step, suffix, cb):
        sl = PixelSlider(lo, hi, step, suffix)
        sl.valueChanged.connect(lambda v: (not self._busy) and cb(v))
        self._row(lay, labels, label, sl)
        return sl

    def _tiles(self, lay, items, on_pick, image_of, cols, tw, th):
        """그림 타일 격자. items: [(키, 이름)], image_of(키) -> QImage. 아래 한 줄에 마우스를 올린/고른 항목의 이름을 보여 준다."""
        host = QWidget()
        g = QGridLayout(host)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(2 * PX)
        cap = WrapLabel()
        cap.setFont(body_font())
        cap.setStyleSheet("color:#f3e6c4;")
        tiles = {}
        names = dict(items)

        def show(hovered):
            if hovered is not None:
                cap.setText(hovered)
                return
            cur = next((k for k, t in tiles.items() if t.isChecked()), None)
            cap.setText(names.get(cur, ""))
        for i, (key, label) in enumerate(items):
            t = PixelTile(image_of(key), label, tw, th)
            t.clicked.connect(lambda _=False, k=key: (on_pick(k), show(None)))
            t.hovered.connect(show)
            g.addWidget(t, i // cols, i % cols)
            tiles[key] = t
        g.setColumnStretch(cols, 1)
        lay.addWidget(host)
        lay.addWidget(cap)
        cap._show = show
        return tiles, cap

    def _build_right(self):
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)   # 안쪽 내용 크기와 상관없이 남은 폭만 쓴다 (넘치면 스크롤)
        w.setMinimumWidth(0)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3 * PX)
        self.tabs = PixelChoice([("basic", tr("모양")), ("decor", tr("장식")), ("snow", tr("눈")), ("shake", tr("흔들기"))])
        self.tabs.changed.connect(self._on_tab)
        v.addWidget(self.tabs)
        self.panel = PixelPanel(fill="bg")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(PX, PX, PX, PX)
        from PySide6.QtWidgets import QStackedWidget
        self.stack = QStackedWidget()
        pl.addWidget(self.stack)
        v.addWidget(self.panel, 1)
        self.stack.addWidget(self._page_basic())
        self.stack.addWidget(self._page_decor())
        self.stack.addWidget(self._page_snow())
        self.stack.addWidget(self._page_shake())
        self.tabs.set_value("basic")
        return w

    # ---- 모양: 외형 / 내부 배경 (화면 크기는 가운데 "바탕화면" 구획)
    def _page_basic(self):
        sc, lay = self._scroll_page()
        lay.addWidget(PixelSection(tr("외형")))
        R = self.mgr.renderer
        self._design_btns, self._design_cap = self._tiles(
            lay, [(k, d["name"]) for k, d in C.DESIGNS.items()], lambda k: self._set(design=k),
            lambda k: R.render(_thumb_state(design=k), []), 6, 34 * PX, 40 * PX)
        lay.addWidget(PixelSection(tr("내부 배경")))
        self._bg_btns, self._bg_cap = self._tiles(
            lay, [(k, d["name"]) for k, d in C.BACKGROUNDS.items()], lambda k: self._set(background=k),
            lambda k: R.render(_thumb_state(background=k), []), 6, 34 * PX, 40 * PX)
        lay.addStretch(1)
        return sc

    # ---- 꾸미기: 장식 고르기 / 선택한 장식의 위치 · 크기 · 회전 / 복제 / 삭제
    def _page_decor(self):
        sc, lay = self._scroll_page()
        lay.addWidget(PixelSection(tr("장식 고르기")))
        self._decor_btns, self._decor_cap = self._tiles(
            lay, [(k, d["name"]) for k, d in C.DECOR.items()], self._pick_decor,
            lambda k: self.mgr.renderer.sprite(k, 1.0), 6, 34 * PX, 30 * PX)
        self.lbl_count = WrapLabel()
        self.lbl_count.setFont(body_font())
        lay.addWidget(self.lbl_count)
        lay.addWidget(PixelSection(tr("선택한 장식")))
        self.lbl_sel = WrapLabel(tr("(미리보기에서 장식을 클릭해 선택)"))
        self.lbl_sel.setFont(body_font())
        self.lbl_sel.setWordWrap(True)
        lay.addWidget(self.lbl_sel)
        self._decor_ctl = QWidget()                      # 장식을 고르지 않았을 땐 숨겨 자리를 비워 둔다
        self._decor_ctl.setObjectName("sgDecorCtl")
        self._decor_ctl.setStyleSheet("#sgDecorCtl{background:transparent;}")
        cl = QVBoxLayout(self._decor_ctl)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(3 * PX)
        labels = []
        self.sl_x = self._slider(cl, labels, tr("가로 위치"), 15, 81, 1, "", lambda v: self._edit_item(x=v))
        self.sl_y = self._slider(cl, labels, tr("세로 위치"), 58, 86, 1, "", lambda v: self._edit_item(y=v))
        self.sl_scale = self._slider(cl, labels, tr("크기"), int(C.SCALE_MIN * 100), int(C.SCALE_MAX * 100), 5, "%",
                                     lambda v: self._edit_item(scale=v / 100.0))
        self.sl_rot = self._slider(cl, labels, tr("회전"), 0, 345, 15, tr("도"), lambda v: self._edit_item(rot=v))
        self._fit(labels)
        row = QHBoxLayout()
        row.setSpacing(3 * PX)
        self.btn_idup = PixelButton(tr("장식 복제"), "box")
        self.btn_idup.clicked.connect(self._dup_item)
        self.btn_idel = PixelButton(tr("장식 삭제"), "trash", kind="danger")
        self.btn_idel.clicked.connect(self._del_item)
        row.addWidget(self.btn_idup)
        row.addWidget(self.btn_idel)
        row.addStretch(1)
        cl.addLayout(row)
        lay.addWidget(self._decor_ctl)
        lay.addStretch(1)
        return sc

    # ---- 눈 설정: 종류 비율(합계 100) / 양 / 크기 / 속도 / 흔들기 방식
    def _page_snow(self):
        sc, lay = self._scroll_page()
        lay.addWidget(PixelSection(tr("눈 종류 비율 (합계 100%)")))
        labels = []
        self.sl_ratio = {}
        for k in C.SNOW_KINDS:
            self.sl_ratio[k] = self._slider(lay, labels, C.SNOW_NAMES[k], 0, 100, 1, "%",
                                            lambda v, kk=k: self._set_snow(**{kk: int(v)}))
        lay.addWidget(PixelSection(tr("양 / 크기 / 속도")))
        self.sl_amount = self._slider(lay, labels, tr("눈의 양"), M.AMOUNT_RANGE[0], M.AMOUNT_RANGE[1], 10, tr(" 개"),
                                      lambda v: self._set_snow(amount=int(v)))
        self.sl_ssize = self._slider(lay, labels, tr("눈송이 크기"), int(M.SNOW_SIZE_RANGE[0] * 100), int(M.SNOW_SIZE_RANGE[1] * 100),
                                     5, "%", lambda v: self._set_snow(size=v / 100.0))
        self.sl_speed = self._slider(lay, labels, tr("낙하 속도"), int(M.SPEED_RANGE[0] * 100), int(M.SPEED_RANGE[1] * 100),
                                     5, "%", lambda v: self._set_snow(speed=v / 100.0))
        self._fit(labels)
        lay.addStretch(1)
        return sc

    # ---- 흔들기: 방식 / 힘 / 자동 흔들기
    def _page_shake(self):
        sc, lay = self._scroll_page()
        lay.addWidget(PixelSection(tr("흔들기 방식")))
        short = {"both": tr("클릭·끌기"), "drag": tr("끌기만"), "click": tr("클릭만")}       # 긴 이름은 한 줄에 못 들어와 잘린다
        self.shake_choice = PixelChoice([(k, short.get(k, name)) for k, name in C.SHAKE_MODES.items()])
        self.shake_choice.changed.connect(lambda k: self._set(shake_mode=k))
        lay.addWidget(self.shake_choice)
        labels = []
        self.sl_shake_strength = self._slider(
            lay, labels, tr("흔드는 힘"), 50, 200, 5, "%",
            lambda v: self._set(shake_strength=v / 100.0))
        self._fit(labels)
        lay.addWidget(PixelSection(tr("자동 흔들기")))
        self.chk_auto = PixelCheck(tr("일정 시간마다 자동으로 흔들기"))
        self.chk_auto.toggled.connect(lambda v: self._set(auto_shake=bool(v)))
        lay.addWidget(self.chk_auto)
        al = []
        self.sl_auto = self._slider(lay, al, tr("자동 흔들기 간격"), C.AUTO_SHAKE_RANGE[0], C.AUTO_SHAKE_RANGE[1], 5, tr(" 초"),
                                    lambda v: self._set(auto_shake_sec=int(v)))
        self._fit(al)
        lay.addStretch(1)
        return sc

    # ------------------------------------------------------------ 동작
    def _set(self, **kw):
        if self._busy or self.mgr.selected is None:
            return
        self.mgr.update(self.mgr.selected, **kw)

    def _set_snow(self, **kw):
        if self._busy or self.mgr.selected is None:
            return
        self.mgr.set_snow(self.mgr.selected, **kw)

    def _add_globe(self):
        if self.mgr.add_globe():
            self._flash(tr("스노우볼을 추가했어요"))
        else:
            self._flash(tr("스노우볼은 최대 {0}개예요").format(MAX_GLOBES))

    def _dup_globe(self):
        gid = self.mgr.selected
        if gid is None:
            return
        if self.mgr.duplicate(gid):
            self._flash(tr("복제했어요"))
        else:
            self._flash(tr("스노우볼은 최대 {0}개예요").format(MAX_GLOBES))

    def _del_globe(self):
        gid = self.mgr.selected
        if gid is None:
            return
        g = self.mgr.get(gid)
        name = g["name"] or C.DESIGNS[g["design"]]["name"]      # 지우기 전에 이름을 읽어 둔다
        self.mgr.remove(gid)
        self._flash(tr("'{0}'을(를) 삭제했어요").format(name))

    def _on_visible(self, on: bool):
        self._set(visible=bool(on))

    def _on_tab(self, key: str):
        self.stack.setCurrentIndex({"basic": 0, "decor": 1, "snow": 2, "shake": 3}[key])
        self.canvas.mode = "edit" if key == "decor" else "view"
        if key != "decor" and self.canvas.place_kind:
            self.canvas.place_kind = None
            self._sync_place_buttons()
        self._update_hint()
        self.canvas.update()

    def _pick_decor(self, kind: str):
        self.canvas.place_kind = None if self.canvas.place_kind == kind else kind
        self._sync_place_buttons()
        self.canvas.setFocus()
        self.canvas.update()

    def _sync_place_buttons(self):
        for k, b in self._decor_btns.items():
            b.setChecked(k == self.canvas.place_kind)
        self._decor_cap._show(None)

    def _sel_item(self):
        gid = self.mgr.selected
        if gid is None or self.canvas.sel_item is None:
            return None
        return next((i for i in self.mgr.decor_items(gid) if i["id"] == self.canvas.sel_item), None)

    def _edit_item(self, **kw):
        it = self._sel_item()
        if it is not None:
            self.mgr.update_decor(self.mgr.selected, it["id"], **kw)

    def _dup_item(self):
        it = self._sel_item()
        if it is not None:
            nid = self.mgr.duplicate_decor(self.mgr.selected, it["id"])
            if nid:
                self.canvas.sel_item = nid
                self._refresh_decor()
            else:
                self._flash(tr("장식은 스노우볼 하나에 최대 {0}개예요").format(C.MAX_DECOR))

    def _del_item(self):
        it = self._sel_item()
        if it is not None:
            self.mgr.remove_decor(self.mgr.selected, it["id"])
            self.canvas.sel_item = None
            self._refresh_decor()
            self._flash(tr("장식을 삭제했어요"))

    # ------------------------------------------------------------ 동기화
    def _on_structure(self):
        gid = self.mgr.selected
        if gid != self._prev_gid:
            self.btn_del.disarm()                    # 대기 중이던 삭제 확인은 다른 스노우볼에 적용되지 않게 해제
            if self._prev_gid:
                self.mgr.set_preview(self._prev_gid, False)
            self._prev_gid = gid
            self.canvas.sel_item = None
            self.canvas.place_kind = None
            self._sync_place_buttons()
            if gid and self.isVisible():
                self.mgr.set_preview(gid, True)
        self._rebuild_list()
        self._refresh()

    def _on_globe_changed(self, gid: str):
        if gid == self.mgr.selected:
            self._refresh()
        self._rebuild_list()

    def _on_frame(self, gid: str):
        if gid == self.mgr.selected and self.isVisible():
            self.canvas.update()

    def _refresh(self):
        gid = self.mgr.selected
        has = gid is not None
        for wdg in (self.stack, self.tabs, self.btn_shake, self.chk_vis, self.chk_lock, self.sl_size, self.btn_dup, self.btn_del):
            wdg.setEnabled(has)
        full = self.mgr.count() >= MAX_GLOBES
        self.btn_add.setEnabled(not full)
        self.lbl_gcount.setText(f"{self.mgr.count()} / {MAX_GLOBES}")
        self.lbl_gcount.setStyleSheet("color:#ffd35a;" if full else "color:#9fb4d0;")
        self._update_hint()
        self.canvas.update()
        if not has:
            return
        g = self.mgr.get(gid)
        self._busy = True
        try:
            for k, b in self._design_btns.items():
                b.setChecked(k == g["design"])
            for k, b in self._bg_btns.items():
                b.setChecked(k == g["background"])
            self._design_cap._show(None)
            self._bg_cap._show(None)
            self.sl_size.setValue(g["size"])
            self.chk_vis.setChecked(g["visible"])
            self.chk_lock.setChecked(g.get("position_locked", False))
            self.shake_choice.set_value(g["shake_mode"])
            self.sl_shake_strength.setValue(g.get("shake_strength", 1.0) * 100)
            self.chk_auto.setChecked(g["auto_shake"])
            self.sl_auto.setValue(g["auto_shake_sec"])
            self.sl_auto.setEnabled(g["auto_shake"])
            sn = g["snow"]
            for k in C.SNOW_KINDS:
                self.sl_ratio[k].setValue(sn[k])
            self.sl_amount.setValue(sn["amount"])
            self.sl_ssize.setValue(sn["size"] * 100)
            self.sl_speed.setValue(sn["speed"] * 100)
        finally:
            self._busy = False
        self._refresh_decor()

    def _refresh_decor(self):
        gid = self.mgr.selected
        if gid is None:
            return
        g = self.mgr.get(gid)
        self.lbl_count.setText(tr("장식 {0} / {1}").format(len(g['decor']), C.MAX_DECOR))
        it = self._sel_item()
        if it is None and self.canvas.sel_item is not None:
            self.canvas.sel_item = None
        has = it is not None
        for wdg in (self.sl_x, self.sl_y, self.sl_scale, self.sl_rot, self.btn_idup, self.btn_idel):
            wdg.setEnabled(has)
        self._decor_ctl.setVisible(has)
        self.lbl_sel.setText(C.DECOR[it["kind"]]["name"] if has else tr("(미리보기에서 장식을 클릭해 선택)"))
        if has:
            self._busy = True
            try:
                self.sl_x.setValue(it["x"])
                self.sl_y.setValue(it["y"])
                self.sl_scale.setValue(it["scale"] * 100)
                self.sl_rot.setValue(it["rot"])
            finally:
                self._busy = False
        self.canvas.update()

    # ------------------------------------------------------------ 표시 / 숨김
    def showEvent(self, e):
        super().showEvent(e)
        if self.mgr.selected:
            self._prev_gid = self.mgr.selected
            self.mgr.set_preview(self.mgr.selected, True)

    def hideEvent(self, e):
        super().hideEvent(e)
        for gid in list(self.mgr.order):
            self.mgr.set_preview(gid, False)
