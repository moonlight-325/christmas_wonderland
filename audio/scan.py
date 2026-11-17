"""음악 폴더 탐색 (Qt 무관, 테스트 가능). 파일 수 상한에 도달하면 하위 폴더 순회도 즉시 멈춘다."""
from __future__ import annotations

import os
from pathlib import Path

AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus"}
MAX_FOLDER_FILES = 500


def scan_folder(folder, limit: int = MAX_FOLDER_FILES) -> list:
    """folder 아래의 오디오 파일을 최대 limit 개까지 반환한다. 읽을 수 없는 폴더는 건너뛴다."""
    out: list = []
    if limit <= 0:
        return out
    for root, _dirs, files in os.walk(folder, onerror=lambda _e: None):
        for name in sorted(files):
            p = Path(root) / name
            if p.suffix.lower() in AUDIO_EXTS:
                out.append(p)
                if len(out) >= limit:
                    return out
    return out
