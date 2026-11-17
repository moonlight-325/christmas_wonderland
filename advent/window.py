"""Advent Calendar 창: 캘린더 화면 <-> 선물 공개 화면 (부드러운 전환), 저장/복구."""
from __future__ import annotations
from core.i18n import tr


from datetime import date
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from core.logger import get_logger
from widget.pixel_ui import PX, PixelButton, PixelWindow
from .anim import FadeStack
from .calendar_page import CalendarCanvas
from .content import load_contents
from .launcher import LaunchError, LaunchTracker
from .logic import AVAILABLE, OPENED, all_statuses, build_context, default_view_year, unlock_message
from .reveal_page import RevealPage
from .settings_window import ContentSettingsWindow
from .state import AdventStore

log = get_logger("advent")


class AdventWindow(PixelWindow):
    def __init__(self, directory: Path, today_fn=date.today, parent=None):
        super().__init__(tr("어드벤트 캘린더"), "gift", parent)
        self.today_fn = today_fn
        self.setFixedSize(420 * PX, 350 * PX)

        self.store = AdventStore(directory)
        self.load_result = self.store.load()
        self.directory = Path(directory)
        self.content = load_contents(self.directory, self.store.get_setting("content_path"))
        self._today = self.today_fn()
        self.year = default_view_year(self._today)
        self._ctx = build_context(self.store, self.year, self._today)
        self._reveal_key = None                  # (year, day) 현재 공개 중인 선물
        self._settings_win = None
        self._launcher = LaunchTracker()          # 실행 중인 선물 프로그램 (날짜별, 중복 실행 방지)
        self._launch_timer = QTimer(self)         # 실행 중인 프로그램이 끝났는지 1초마다 확인(대기하지 않음)
        self._launch_timer.timeout.connect(self._poll_launches)

        root = QVBoxLayout(self.body)
        root.setContentsMargins(2 * PX, 2 * PX, 2 * PX, 2 * PX)
        self.stack = FadeStack()
        root.addWidget(self.stack)
        self.stack.addWidget(self._build_calendar_page())
        self.reveal = RevealPage()
        self.reveal.back.connect(self._back_to_calendar)
        self.reveal.eventResult.connect(self._on_event_result)
        self.reveal.launchRequested.connect(self._on_launch_requested)
        self.stack.addWidget(self.reveal)

        self.canvas.dayClicked.connect(self._on_day_clicked)
        self.canvas.openFinished.connect(self._on_open_finished)
        self.canvas.yearStep.connect(self._step_year)
        self.canvas.hint_fn = self._hint

        self._midnight = QTimer(self)             # 자정이 지나면 새 날짜로 자동 해금
        self._midnight.timeout.connect(self._check_date)
        self._midnight.start(30_000)
        self._apply_animation_setting()
        self.refresh()
        if self.load_result == "recovered":
            log.warning("어드벤트 기록을 백업(%s)에서 복구했습니다", self.store.recovered_from)

    # ------------------------------------------------------------------ 화면 구성
    def _build_calendar_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3 * PX)
        self.canvas = CalendarCanvas()
        v.addWidget(self.canvas, 1)

        row = QHBoxLayout()
        row.setSpacing(3 * PX)
        self.btn_last = PixelButton(tr("마지막 선물"), "gift")
        self.btn_last.clicked.connect(self._open_last)
        self.btn_content = PixelButton(tr("콘텐츠 설정"), "gear")
        self.btn_content.clicked.connect(self._show_settings)
        for b in (self.btn_last, self.btn_content):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        return page

    # ------------------------------------------------------------------ 갱신
    def _year_bounds(self):
        years = self.store.years_with_records() + [self._today.year]
        return min(years), max(years)

    def refresh(self):
        self._today = self.today_fn()
        st = self.store
        self._ctx = build_context(st, self.year, self._today)
        ctx = self._ctx
        lo, hi = self._year_bounds()
        self.canvas.set_view(self.year, all_statuses(ctx), len(ctx.opened), self.year > lo, self.year < hi)
        last = st.last_opened
        self.btn_last.setEnabled(last is not None)
        self.btn_last.setText(tr("마지막 선물 {0}일").format(last['day']) if last else tr("마지막 선물"))

    def _hint(self, day: int) -> str:
        st = self._ctx
        from .logic import box_status
        s = box_status(st, day)
        if s == OPENED:
            return tr("12월 {0}일 선물 · 개봉 완료 · 눌러서 다시 보기").format(day)
        if s == AVAILABLE:
            return tr("12월 {0}일 선물 · 눌러서 열기").format(day)
        return unlock_message(st, day)

    def _check_date(self):
        today = self.today_fn()
        if today != self._today:
            self.year = default_view_year(today)
            self.refresh()

    def showEvent(self, e):
        super().showEvent(e)
        self._check_date()

    def closeEvent(self, e):
        self.store.save()
        super().closeEvent(e)

    # ------------------------------------------------------------------ 연도 이동
    def _step_year(self, k: int):
        lo, hi = self._year_bounds()
        self.year = max(lo, min(hi, self.year + k))
        self.refresh()

    # ------------------------------------------------------------------ 열기 흐름
    def _animations_on(self) -> bool:
        return bool(self.store.get_setting("animations"))

    def _apply_animation_setting(self):
        self.stack.animated = self._animations_on()

    def _on_day_clicked(self, day: int):
        status = all_statuses(self._ctx)[day]
        if status == AVAILABLE:
            self.canvas.play_open(day, animate=self._animations_on())      # 끝나면 _on_open_finished
        elif status == OPENED:
            self._enter_reveal(self.year, day, first=False)

    def _on_open_finished(self, day: int):
        self._enter_reveal(self.year, day, first=True)

    def _enter_reveal(self, year: int, day: int, first: bool):
        if first:
            self.store.mark_opened(year, day)
            self.refresh()
            self._warn_if_save_failed()
        self._reveal_key = (year, day)
        self.reveal.show_gift(self.content.get(day), first=first,
                              prev_event=self.store.get_event(year, day),
                              animations=self._animations_on(), events_enabled=bool(self.store.get_setting("events")),
                              launch_running=self._launcher.is_running(day))
        self.stack.fade_to(1)

    def _warn_if_save_failed(self):
        """개봉/이벤트 기록 저장에 실패하면 연속 실패 중 한 번만 안내한다."""
        if not self.store.save_failed:
            self._save_warned = False
            return
        if getattr(self, "_save_warned", False):
            return
        self._save_warned = True
        QMessageBox.warning(self, tr("저장 실패"), tr("개봉 기록을 저장하지 못했어요.\n"
                            "프로그램을 닫으면 이번 기록이 사라질 수 있어요. 폴더 쓰기 권한과 디스크 공간을 확인해 주세요."))

    def _back_to_calendar(self):
        self.stack.fade_to(0)
        self.refresh()

    def _on_event_result(self, day: int, result: dict):
        if self._reveal_key and self._reveal_key[1] == day:
            self.store.set_event(self._reveal_key[0], day, result)
            self._warn_if_save_failed()

    # ------------------------------------------------------------------ 외부 프로그램 실행
    def _on_launch_requested(self, day: int):
        action = self.content.get(day).action
        if action is None:
            return
        try:
            started = self._launcher.start(day, action)
        except LaunchError as exc:
            log.warning("%d일 선물 실행 실패: %s", day, exc)
            QMessageBox.warning(self, tr("선물을 실행하지 못했어요"), str(exc))
            return
        if started:                                # 성공 시에는 팝업 없이 버튼만 '실행 중'으로 바뀐다
            self.reveal.set_launch_running(True)
            self._launch_timer.start(1000)

    def _poll_launches(self):
        day = self.reveal.current_day
        if day is not None:
            self.reveal.set_launch_running(self._launcher.is_running(day))
        if not self._launcher.any_running():
            self._launch_timer.stop()

    def _open_last(self):
        li = self.store.last_opened
        if not li:
            return
        self.year = li["year"]
        self.refresh()
        self._enter_reveal(self.year, li["day"], first=False)

    # ------------------------------------------------------------------ 콘텐츠 설정
    def _show_settings(self):
        if self._settings_win is None:
            self._settings_win = ContentSettingsWindow(self.store, lambda: self.content)
            self._settings_win.changed.connect(self._reload_content)
        self._settings_win.refresh()
        self._settings_win.show()
        self._settings_win.raise_()
        self._settings_win.activateWindow()

    def _reload_content(self):
        self.content = load_contents(self.directory, self.store.get_setting("content_path"))
        self._apply_animation_setting()
        if self._settings_win is not None:
            self._settings_win.refresh()
        self.refresh()
