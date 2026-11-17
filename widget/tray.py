from core.i18n import tr

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from core.icons import make_app_icon
from core.logger import get_logger
from weather import spec
from .sprites import sprite_icon

log = get_logger("tray")


class Tray:
    """위젯을 제어하기 위한 트레이 아이콘.

    켜기/끄기 항목은 체크 표시로 현재 상태를 보여 주고, 메뉴를 열 때마다 실제 설정값과 다시 맞춘다.
    """

    def __init__(self, controller):
        self.c = controller
        # 트레이가 없는 환경이면 '항상 아래 창' 모드에서 위젯을 다시 불러낼 방법이 줄어든다. 원인 파악을 위해 기록해 둔다.
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        if not self.available:
            log.warning("시스템 트레이를 사용할 수 없습니다. 트레이 메뉴 없이 실행됩니다.")
        self.icon = QSystemTrayIcon(make_app_icon())
        self._tip = "Christmas Wonderland"
        self.icon.setToolTip(self._tip)
        self._toggles: list[tuple[QAction, str]] = []
        menu = QMenu()

        def act(text, fn, icon=None):
            a = menu.addAction(sprite_icon(icon), text) if icon else menu.addAction(text)
            a.triggered.connect(lambda _checked=False, f=fn: f())
            return a

        def toggle(text, key, fn=None, icon=None):
            a = act(text, fn or (lambda k=key: controller.toggle_setting(k)), icon)
            a.setCheckable(True)
            self._toggles.append((a, key))
            return a

        act(tr("위젯 표시"), controller.widget.show_from_tray)
        group = QActionGroup(menu)
        group.setExclusive(True)
        self._mode_actions = {}
        for mode, text in (("normal", tr("일반 창 모드")), ("bottom", tr("항상 아래 창 모드"))):
            a = act(text, lambda m=mode: controller.settings.set("widget.mode", m, save=True))
            a.setCheckable(True)
            group.addAction(a)
            self._mode_actions[mode] = a
        menu.addSeparator()
        toggle(tr("눈 내리기"), "snow.enabled", controller.toggle_snow, "snow")
        act(tr("바람 조절 창"), controller.show_wind, "wind")
        act(tr("돌풍 일으키기"), controller.snow.trigger_gust, "wind")
        act(tr("눈사람 공방"), controller.show_snowman, "snow")
        self.act_auto = act(tr("자동 날씨 시작"), controller.toggle_auto_weather, "snow")
        toggle(tr("전구 장식"), "lights.enabled")
        toggle(tr("바탕화면 시계"), "clock.enabled")
        toggle(tr("장식 표시"), "decor.enabled")
        menu.addSeparator()
        self.act_music = act(tr("음악 재생"), controller.audio.toggle, "play")
        act(tr("음악 플레이어"), controller.show_music, "note")
        act(tr("스노우볼"), controller.show_snowglobe, "globe")
        act(tr("달력"), controller.show_calendar, "calendar")
        act(tr("어드벤트 캘린더"), controller.show_advent, "gift")
        act(tr("설정"), controller.show_settings, "gear")
        menu.addSeparator()
        act(tr("종료"), controller.quit, "close")
        self.menu = menu
        menu.aboutToShow.connect(self.refresh)
        controller.auto_weather.state_changed.connect(self.update_tip)       # 날씨가 바뀌면 메뉴를 열지 않아도 툴팁이 맞도록
        self.refresh()
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._activated)
        self.update_visibility()

    def update_visibility(self):
        """일반 설정의 트레이 아이콘 표시 여부를 적용한다."""
        visible = bool(self.c.settings.get("app.show_tray"))
        self.icon.setVisible(visible)

    def refresh(self):
        """메뉴에 표시되는 상태(체크, 시작/일시정지/재개, 재생/일시정지)를 현재 값으로 맞춘다."""
        c = self.c
        for a, key in self._toggles:
            a.setChecked(bool(c.settings.get(key)))
        mode = c.settings.get("widget.mode")
        for m, a in self._mode_actions.items():
            a.setChecked(m == mode)
        core = c.auto_weather.core
        self.act_auto.setText(tr("자동 날씨 시작") if core.phase != "run"
                              else tr("자동 날씨 재개") if core.paused else tr("자동 날씨 일시정지"))
        self.act_music.setText(tr("음악 일시정지") if c.audio.is_playing else tr("음악 재생"))
        self.update_tip()

    def update_tip(self):
        """트레이 아이콘 툴팁에 자동 날씨 상태를 덧붙인다 (메뉴 항목은 '다음 동작'만 보여 주기 때문).
        값이 바뀐 경우에만 설정해 트레이 API 를 불필요하게 두드리지 않는다."""
        summary = spec.status_summary(self.c.auto_weather.status())
        tip = "Christmas Wonderland" + (f"\n{summary}" if summary else "")
        if tip != self._tip:
            self._tip = tip
            self.icon.setToolTip(tip)

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.c.widget.show_from_tray()

    def hide(self):
        self.icon.hide()
