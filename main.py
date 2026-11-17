"""Christmas Wonderland - 픽셀 크리스마스 데스크톱 위젯 + 바탕화면 전체 눈."""

from core.i18n import tr

import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from core.logger import setup_logging
from core.paths import data_dir
from core.version import APP_TITLE, __version__


def main() -> int:
    log = setup_logging()
    from core import i18n
    i18n.init_from_settings_file(data_dir())   # 문구가 들어간 모듈을 import 하기 전에 언어부터 정한다

    def excepthook(exc_type, exc, tb):
        log.error("처리되지 않은 예외", exc_info=(exc_type, exc, tb))
    sys.excepthook = excepthook

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("ChristmasWonderland")
    app.setQuitOnLastWindowClosed(False)      # 트레이/보조 창만 남아도 임의로 종료하지 않음
    log.info("%s v%s 시작", APP_TITLE, __version__)

    from core.fonts import load_fonts           # Qt 앱 생성 후 임포트
    from widget.pixel_ui import app_stylesheet, body_font
    load_fonts()
    app.setFont(body_font())                    # 모든 UI 의 기본 폰트 = 픽셀 폰트
    app.setStyleSheet(app_stylesheet())

    lock = QLockFile(str(data_dir() / "app.lock"))
    if not lock.tryLock(200):
        QMessageBox.information(None, APP_TITLE, tr("이미 실행 중입니다. 트레이 아이콘을 확인하세요."))
        return 0

    from core.app_controller import AppController
    controller = AppController(app)
    controller.start()
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
