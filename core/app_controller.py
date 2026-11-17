from __future__ import annotations
from core.i18n import tr


from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QVBoxLayout

from audio.manager import AudioManager
from audio.sfx import SfxManager
from clockface.window import ClockWindow
from decor.items import DecorManager
from decor.lights import LightsWindow
import decor.sprites  # noqa: F401  (장식 스프라이트 등록)
from core.icons import make_app_icon
from core.logger import get_logger
from advent.window import AdventWindow
from core.paths import data_dir
from core.steps import run_steps
from settings.manager import SettingsManager
from snow.engine import SnowEngine
from snowman.manager import SnowmanManager
from weather.controller import AutoWeather
from widget.calendar_window import CalendarWindow
from widget.main_widget import MainWidget
from widget.music_panel import MusicPanel
from widget.pixel_ui import PX, PixelWindow
from widget.settings_window import SettingsWindow
from snowglobe.manager import GlobeManager
from widget.snowglobe_window import SnowGlobeWindow
from widget.tray import Tray
from widget.wind_panel import WindWindow

log = get_logger("app")


class AppController:
    def __init__(self, app):
        self.app = app
        self._quitting = False
        app.setWindowIcon(make_app_icon())

        self.settings = SettingsManager()
        log.info("설정 로드: %s (%s)", self.settings.load_result, self.settings.path)
        self.audio = AudioManager(self.settings)
        self.widget = MainWidget(self.settings, self.audio)
        self.auto_weather = AutoWeather(self.settings)   # 자동 날씨: 값 제어권(settings.effective)을 가진다
        self.snow = SnowEngine(self.settings)        # 위젯과 독립적으로 동작하는 데스크톱 눈
        self.auto_weather.applied.connect(self.snow.on_auto_applied)
        self.snowman = SnowmanManager(self.settings, self.snow)   # 눈덩이/눈사람 월드 (눈 엔진에 연결)
        self.sfx = SfxManager(self.settings, self.audio, self.snow)
        self.decor = DecorManager(self.settings)
        self.snowglobes = GlobeManager()               # 스노우볼: 내부 물리/저장이 데스크톱 눈 엔진과 완전히 독립
        self.snowglobes.open_requested.connect(self._open_globe)
        self.lights = LightsWindow(self.settings)
        self.clock = ClockWindow(self.settings)
        self.tray = Tray(self)
        self.settings.changed.connect(self._on_app_setting_changed)
        self._last_fail_msg: dict[str, float] = {}
        self.settings.save_failed.connect(lambda: self._notify_save_failed(tr("설정")))
        self.snowglobes.save_failed.connect(lambda: self._notify_save_failed(tr("스노우볼")))

        self._settings_dlg = None
        self._calendar = None
        self._advent = None
        self._snowglobe = None
        self._music_win = None
        self._wind_win = None
        self._snowman_win = None

        w = self.widget
        w.open_settings.connect(self.show_settings)
        w.open_calendar.connect(self.show_calendar)
        w.open_advent.connect(self.show_advent)
        w.open_snowglobe.connect(self.show_snowglobe)
        w.open_music.connect(self.show_music)
        w.open_wind.connect(self.show_wind)
        w.open_snowman.connect(self.show_snowman)
        w.clean_snow.connect(self.snow.clear_piles)
        w.reset_snow.connect(self.snow.reset)
        w.request_quit.connect(self.quit)
        app.aboutToQuit.connect(self._shutdown)

    def _on_app_setting_changed(self, key: str):
        if key in ("app.show_tray", "*"):
            self.tray.update_visibility()

    def start(self):
        self.widget.apply_mode()
        self.auto_weather.restore()                  # 저장된 자동 날씨 상태 복원 (눈 엔진 시작 전)
        self.snow.start()
        self.snowman.start()                         # 저장된 눈사람 복원 (화면 경계 확정 후)
        self.decor.start()
        self.snowglobes.start()                      # 저장된 스노우볼 복원
        self.sfx.start()
        if self.settings.load_result == "recovered":
            self.tray.icon.showMessage("Christmas Wonderland",
                                       tr("설정 파일이 손상되어 백업에서 복구했습니다."))
        # 첫 실행 직후 상태를 디스크에 확정
        QTimer.singleShot(1500, self.settings.save_now)
        # 설정창은 처음 열 때 한꺼번에 만들면 1초 넘게 멈추므로, 시작 직후 한가할 때 한 페이지씩 미리 만들어 둔다
        QTimer.singleShot(4000, lambda: self._build_settings(defer=True))

    # ---- 보조 창
    def _notify_save_failed(self, what: str):
        """저장 실패를 트레이 알림으로 알린다 (자동 저장이 반복 실패해도 종류별로 60초에 한 번만)."""
        import time
        now = time.monotonic()
        if now - self._last_fail_msg.get(what, -1e9) < 60.0:       # 같은 종류는 60초에 한 번만
            return
        self._last_fail_msg[what] = now
        self.tray.icon.showMessage("Christmas Wonderland",
                                   tr("{0} 저장에 실패했어요. 디스크 공간이나 폴더 권한을 확인하세요. (data/app.log 에 기록됨)").format(what))

    def _present(self, win):
        """창 열기: 기존 인스턴스 재사용 -> 숨김/최소화 복원 -> 화면 안으로 위치 보정 -> 앞으로 -> 활성화."""
        from PySide6.QtCore import Qt
        if win.isMinimized():
            win.setWindowState(win.windowState() & ~Qt.WindowMinimized)
            win.showNormal()
        if not win.isVisible():
            win.show()
        self._keep_on_screen(win)
        win.raise_()
        win.activateWindow()
        try:
            from widget import winz
            winz.force_foreground(win)
        except Exception:
            log.exception("창 앞으로 가져오기 실패")

    @staticmethod
    def _keep_on_screen(win):
        """창이 어떤 모니터와도 충분히 겹치지 않으면 (화면 밖에 열린 경우) 가장 가까운 화면 안으로 옮긴다."""
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QGuiApplication
        fr = win.frameGeometry()
        screens = [s.availableGeometry() for s in QGuiApplication.screens()]
        for r in screens:
            i = r.intersected(fr)
            if i.width() >= min(120, fr.width()) and i.height() >= min(60, fr.height()):
                return
        r = QGuiApplication.primaryScreen().availableGeometry()
        x = max(r.left(), min(fr.left(), r.right() - fr.width() + 1))
        y = max(r.top(), min(fr.top(), r.bottom() - fr.height() + 1))
        win.move(QPoint(x, y))

    def show_settings(self):
        if self._settings_dlg is None:
            self._build_settings(defer=False)
        self._settings_dlg.finish_build()         # 미리 만드는 중이었다면 남은 페이지만 지금 마무리
        self._present(self._settings_dlg)

    def _build_settings(self, defer: bool):
        if self._settings_dlg is None:
            self._settings_dlg = SettingsWindow(self.settings, self.audio, sfx=self.sfx, decor=self.decor,
                                                auto=self.auto_weather, defer=defer)
            self._settings_dlg.gust_requested.connect(self.snow.trigger_gust)
            self._settings_dlg.center_requested.connect(self.widget.center_on_screen)
            self._settings_dlg.clean_requested.connect(self.snow.clear_piles)
            self._settings_dlg.reset_requested.connect(self.snow.reset)
            self._settings_dlg.wind_window_requested.connect(self.show_wind)

    def show_calendar(self):
        if self._calendar is None:
            self._calendar = CalendarWindow()
        self._present(self._calendar)

    def show_advent(self):
        if self._advent is None:
            self._advent = AdventWindow(data_dir())
        self._present(self._advent)

    def show_snowglobe(self):
        if self._snowglobe is None:
            self._snowglobe = SnowGlobeWindow(self.snowglobes)
        self._present(self._snowglobe)

    def _open_globe(self, gid: str):
        self.snowglobes.select(gid)
        self.show_snowglobe()

    def show_music(self):
        if self._music_win is None:
            self._music_win = PixelWindow(tr("음악 플레이어"), "note")
            lay = QVBoxLayout(self._music_win.body)
            lay.setContentsMargins(4 * PX, 4 * PX, 4 * PX, 4 * PX)
            lay.addWidget(MusicPanel(self.audio, self.settings))
            self._music_win.setFixedSize(280 * PX, 330 * PX)
        self._present(self._music_win)

    def show_wind(self):
        if self._wind_win is None:
            self._wind_win = WindWindow(self.settings)
            g = self.widget.geometry()
            self._wind_win.move(max(0, g.left() - self._wind_win.width() - 12), g.top())
        self._present(self._wind_win)

    def show_snowman(self):
        if self._snowman_win is None:
            from snowman.panel import SnowmanPanel
            self._snowman_win = SnowmanPanel(self.snowman)
            g = self.widget.geometry()
            scr = self.widget.screen().availableGeometry()
            w = self._snowman_win
            x = g.right() + 12
            if x + w.width() > scr.right():                      # 오른쪽에 자리가 없으면 위젯 왼쪽에 둔다
                x = g.left() - w.width() - 12
            x = max(scr.left(), min(x, scr.right() - w.width() + 1))
            y = max(scr.top(), min(g.top(), scr.bottom() - w.height() + 1))
            w.move(x, y)
        self._present(self._snowman_win)

    def toggle_snow(self):
        self.settings.set("snow.enabled", not self.settings.get("snow.enabled"), save=True)

    def toggle_auto_weather(self):
        """트레이: 꺼져 있으면 시작, 실행 중이면 일시정지, 일시정지 중이면 재개."""
        aw = self.auto_weather
        if aw.core.phase != "run":
            ok, msg = aw.start()
            if not ok:
                self.tray.icon.showMessage("Christmas Wonderland", msg)
        elif aw.core.paused:
            aw.resume()
        else:
            aw.pause()

    def toggle_setting(self, key: str):
        self.settings.set(key, not self.settings.get(key), save=True)

    # ---- 종료
    def quit(self):
        if self._quitting:
            return
        self._quitting = True
        self.app.quit()

    def _shutdown(self):
        """각 시스템을 독립적으로 정리한다: 한 단계가 실패해도 나머지(트레이 아이콘 제거 포함)는 반드시 실행."""
        def save_advent():
            if self._advent is not None:
                self._advent.store.save()

        failed = run_steps([
            (tr("위젯 위치 저장"), self.widget._store_geometry),
            (tr("설정 저장"), self.settings.save_now),
            (tr("어드벤트 저장"), save_advent),
            (tr("눈사람 저장"), self.snowman.shutdown),       # 눈사람 상태를 설정에 기록 (아래 save_now 보다 먼저)
            (tr("설정 최종 저장"), self.settings.save_now),
            (tr("자동 날씨 정리"), self.auto_weather.shutdown),
            (tr("눈 정리"), self.snow.shutdown),              # 오버레이 창과 타이머 정리
            (tr("효과음 정리"), self.sfx.shutdown),
            (tr("스노우볼 저장"), self.snowglobes.shutdown),  # 스노우볼 상태 안전 저장 + 창 정리
            (tr("장식 정리"), self.decor.shutdown),
            (tr("전구 정리"), self.lights.shutdown),
            (tr("시계 정리"), self.clock.shutdown),
            (tr("음악 정지"), self.audio.stop),
            (tr("트레이 제거"), self.tray.hide),
        ], log)
        if failed:
            log.error("종료 중 실패한 단계: %s", ", ".join(failed))
        log.info("종료")
