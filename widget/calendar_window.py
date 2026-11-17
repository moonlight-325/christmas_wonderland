from core.i18n import tr

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtGui import QBrush, QColor, QTextCharFormat
from PySide6.QtWidgets import QCalendarWidget, QLabel, QVBoxLayout

from core.dday import next_christmas
from .pixel_ui import PAL, PX, PixelWindow, body_font


class CalendarWindow(PixelWindow):
    def __init__(self, parent=None):
        super().__init__(tr("크리스마스 캘린더"), "calendar", parent)
        self.setFixedSize(300 * PX, 250 * PX)
        v = QVBoxLayout(self.body)
        v.setContentsMargins(2 * PX, 2 * PX, 2 * PX, 2 * PX)
        self.cal = QCalendarWidget()
        self.cal.setFont(body_font())
        self.cal.setGridVisible(False)
        self.cal.setNavigationBarVisible(True)
        v.addWidget(self.cal, 1)
        self.lbl = QLabel()
        self.lbl.setFont(body_font())
        self.lbl.setWordWrap(True)
        v.addWidget(self.lbl)
        self.cal.currentPageChanged.connect(self._mark_christmas)
        self.cal.selectionChanged.connect(self._update_label)
        self._mark_christmas(self.cal.yearShown(), self.cal.monthShown())
        today = date.today()
        self.cal.setSelectedDate(QDate(today.year, today.month, today.day))
        self._update_label()

    def _mark_christmas(self, year, month):
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(QColor(PAL["snow"])))
        fmt.setBackground(QBrush(QColor(PAL["red"])))
        self.cal.setDateTextFormat(QDate(year, 12, 25), fmt)

    def _update_label(self):
        q = self.cal.selectedDate()
        sel = date(q.year(), q.month(), q.day())
        xmas = date(sel.year, 12, 25)
        diff = (xmas - sel).days
        if diff > 0:
            text = tr("크리스마스까지 {0}일 남았습니다.").format(diff)
        elif diff == 0:
            text = tr("메리 크리스마스! 오늘이 크리스마스입니다.")
        else:
            text = tr("올해 크리스마스가 {0}일 지났습니다.").format(-diff)
        today_diff = (next_christmas() - date.today()).days
        self.lbl.setText(tr("{0}\n오늘 기준 D-{1}").format(text, today_diff) if today_diff else text)
