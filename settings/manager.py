from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from core.paths import data_dir
from .store import SettingsStore


class SettingsManager(QObject):
    """Qt 시그널/타이머를 붙인 설정 관리자."""

    changed = Signal(str)       # 변경된 dotted key ("*" = 전체 갱신)
    saved = Signal(str)         # 저장 시각 ISO 문자열
    save_failed = Signal()

    def __init__(self, directory: Path | None = None, parent=None):
        super().__init__(parent)
        self.store = SettingsStore(directory or data_dir())
        self.load_result = self.store.load()
        self.auto = None            # 자동 날씨 컨트롤러 (weather.controller.AutoWeather) - 연결되면 값 제어권을 가진다
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._autosave_tick)
        self.apply_autosave_config()

    # ---------- 접근 ----------
    def get(self, key: str):
        return self.store.get(key)

    def effective(self, key: str):
        """실제로 적용되는 값. 자동 날씨가 이 변수를 조정 중이면 자동 적용값, 아니면 설정에 저장된 수동값."""
        if self.auto is not None:
            v = self.auto.effective(key)
            if v is not None:
                return v
        return self.store.get(key)

    def set(self, key: str, value, save: bool = False) -> None:
        if self.auto is not None:
            self.auto.on_user_set(key)      # 자동 조정 중인 변수를 직접 바꾸면 그 변수만 수동 고정
        if self.store.set(key, value):
            self.changed.emit(key)
            if key.startswith("app.autosave"):
                self.apply_autosave_config()
            if save:
                self.save_now()

    @property
    def path(self) -> Path:
        return self.store.path

    @property
    def backup_dir(self) -> Path:
        return self.store.backup_dir

    # ---------- 저장 ----------
    def apply_autosave_config(self) -> None:
        self._timer.stop()
        if self.store.get("app.autosave"):
            self._timer.start(int(self.store.get("app.autosave_interval")) * 1000)

    def _autosave_tick(self) -> None:
        if self.store.dirty:
            self.save_now()

    def save_now(self, manual: bool = False) -> bool:
        ok = self.store.save(manual=manual)
        if ok:
            self.saved.emit(self.store.get("app.last_saved"))
        else:
            self.save_failed.emit()
        return ok

    def reset_defaults(self) -> None:
        self.store.reset()
        self.changed.emit("*")
        self.apply_autosave_config()

    def import_backup(self, path: Path) -> bool:
        if self.store.import_from(path):
            self.changed.emit("*")
            self.apply_autosave_config()
            return True
        return False
