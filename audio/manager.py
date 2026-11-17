from __future__ import annotations
from core.i18n import tr


import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from core.logger import get_logger
from core.paths import resource_path

from .scan import AUDIO_EXTS, MAX_FOLDER_FILES, scan_folder  # noqa: F401  (다른 모듈이 manager 에서 가져다 씀)

log = get_logger("audio")


@dataclass
class Track:
    path: str
    title: str
    source: str  # default | folder | user


def _title_from(path: Path) -> str:
    stem = path.stem
    parts = stem.split("_", 1)
    if len(parts) == 2 and parts[0].isdigit():
        stem = parts[1]
    return stem.replace("_", " ").strip().title() if path.parent.name == "music" else stem


class AudioManager(QObject):
    playlistChanged = Signal()
    trackChanged = Signal(int, str)       # index, title
    playingChanged = Signal(bool)
    positionChanged = Signal("qlonglong")
    durationChanged = Signal("qlonglong")
    message = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.tracks: list[Track] = []
        self.index = -1
        self._err_streak = 0

        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.player.setAudioOutput(self.output)
        self.apply_volume()

        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.positionChanged.connect(self.positionChanged)
        self.player.durationChanged.connect(self.durationChanged)
        self.player.errorOccurred.connect(self._on_error)

        self.rebuild_playlist()
        last = self.settings.get("music.last_track")
        for i, t in enumerate(self.tracks):
            if t.path == last:
                self.index = i
                self.player.setSource(QUrl.fromLocalFile(t.path))
                self.trackChanged.emit(i, t.title)
                break
        if self.settings.get("music.autoplay"):
            QTimer.singleShot(800, self.play)

    # ---------- 재생목록 ----------
    def rebuild_playlist(self) -> None:
        current = self.tracks[self.index].path if 0 <= self.index < len(self.tracks) else None
        tracks: list[Track] = []
        seen: set[str] = set()

        def add(p: Path, source: str):
            key = os.path.normcase(str(p.resolve()))
            if key in seen or p.suffix.lower() not in AUDIO_EXTS or not p.is_file():
                return
            seen.add(key)
            tracks.append(Track(str(p), _title_from(p), source))

        if self.settings.get("music.use_default"):
            music_dir = resource_path("assets", "music")
            if music_dir.is_dir():
                for p in sorted(music_dir.iterdir()):
                    add(p, "default")

        folder = self.settings.get("music.folder")
        if folder and Path(folder).is_dir():
            for p in scan_folder(folder, MAX_FOLDER_FILES):
                add(p, "folder")

        for f in self.settings.get("music.user_files"):
            add(Path(f), "user")

        self.tracks = tracks
        self.index = next((i for i, t in enumerate(tracks) if t.path == current), -1)
        self.playlistChanged.emit()

    def add_files(self, files: list[str]) -> int:
        cur = list(self.settings.get("music.user_files"))
        added = 0
        for f in files:
            if f not in cur and Path(f).suffix.lower() in AUDIO_EXTS:
                cur.append(f)
                added += 1
        self.settings.set("music.user_files", cur)
        self.rebuild_playlist()
        return added

    def remove_user_file(self, path: str) -> None:
        cur = [f for f in self.settings.get("music.user_files") if f != path]
        self.settings.set("music.user_files", cur)
        self.rebuild_playlist()

    def set_folder(self, folder: str) -> None:
        self.settings.set("music.folder", folder, save=True)
        self.rebuild_playlist()

    def set_use_default(self, on: bool) -> None:
        self.settings.set("music.use_default", on)
        self.rebuild_playlist()

    # ---------- 재생 제어 ----------
    @property
    def is_playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def current_title(self) -> str:
        return self.tracks[self.index].title if 0 <= self.index < len(self.tracks) else ""

    def play_index(self, i: int) -> None:
        if not self.tracks:
            self.message.emit(tr("재생할 음악이 없습니다. 음악 파일이나 폴더를 추가하세요."))
            return
        i %= len(self.tracks)
        self.index = i
        t = self.tracks[i]
        self.player.setSource(QUrl.fromLocalFile(t.path))
        self.player.play()
        self.settings.set("music.last_track", t.path)
        self.trackChanged.emit(i, t.title)

    def play(self) -> None:
        if not self.tracks:
            self.message.emit(tr("재생할 음악이 없습니다. 음악 파일이나 폴더를 추가하세요."))
            return
        if self.index < 0 or self.player.source().isEmpty():
            self.play_index(max(self.index, 0))
        else:
            self.player.play()

    def pause(self) -> None:
        self.player.pause()

    def stop(self) -> None:
        self.player.stop()

    def toggle(self) -> None:
        self.pause() if self.is_playing else self.play()

    def next(self) -> None:
        if self.tracks:
            self.play_index(self.index + 1 if self.index >= 0 else 0)

    def prev(self) -> None:
        if not self.tracks:
            return
        if self.player.position() > 3000:
            self.player.setPosition(0)
        else:
            self.play_index(self.index - 1 if self.index >= 0 else 0)

    def seek(self, ms: int) -> None:
        self.player.setPosition(int(ms))

    # ---------- 음량/반복 ----------
    def apply_volume(self) -> None:
        v = float(self.settings.get("music.volume"))
        self.output.setVolume(v * v)      # 체감 음량에 가깝게 제곱 곡선 사용

    def set_volume(self, v: float) -> None:
        self.settings.set("music.volume", v)
        self.apply_volume()

    def set_repeat(self, mode: str) -> None:
        self.settings.set("music.repeat", mode)

    def cycle_repeat(self) -> str:
        order = ["all", "one", "off"]
        cur = self.settings.get("music.repeat")
        nxt = order[(order.index(cur) + 1) % 3] if cur in order else "all"
        self.set_repeat(nxt)
        return nxt

    # ---------- 이벤트 ----------
    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        if playing:
            self._err_streak = 0
        self.playingChanged.emit(playing)

    def _on_status(self, status) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        mode = self.settings.get("music.repeat")
        if mode == "one":
            self.player.setPosition(0)
            self.player.play()
        elif mode == "all":
            self.next()
        elif self.index + 1 < len(self.tracks):      # off: 마지막 곡 전까지만 이어 재생
            self.next()
        else:
            self.player.stop()

    def _on_error(self, error, text: str = "") -> None:
        log.warning("재생 오류: %s (%s)", text, self.tracks[self.index].path if 0 <= self.index < len(self.tracks) else "-")
        self._err_streak += 1
        self.message.emit(tr("재생할 수 없는 파일입니다: {0}").format(self.current_title()))
        if self._err_streak < len(self.tracks):
            QTimer.singleShot(0, self.next)          # 깨진 파일은 건너뜀
        else:
            self.player.stop()
