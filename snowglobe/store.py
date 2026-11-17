"""스노우볼 저장소: data/snowglobes.json. 임시 파일에 쓴 뒤 교체(원자적 저장) + 직전 정상본 백업.

- 저장 도중 오류가 나도 기존 파일은 그대로 남는다.
- 본 파일이 손상되면 .bak 에서 복구한다.
- 스노우볼 설정은 프로그램 설정(settings.json)과 분리해 서로 충돌하지 않는다.
- 이전 HTML 스노우볼은 저장 데이터가 없었으므로 이전할 값이 없다 (새로 시작).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from core.logger import get_logger
from core.paths import data_dir

from . import model as M

log = get_logger("snowglobe.store")
VERSION = 1
MAX_GLOBES = 12


def _read(path: Path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def migrate(raw) -> dict | None:
    """저장 형식 정규화. 알 수 없는 형식이면 None. (과거 형식: globes 목록만 있는 리스트도 허용)"""
    if isinstance(raw, list):
        raw = {"version": 0, "globes": raw}
    if not isinstance(raw, dict) or not isinstance(raw.get("globes", []), list):
        return None
    globes, seen = [], set()
    for r in raw.get("globes", [])[:MAX_GLOBES]:
        g = M.clean_globe(r)
        if g is None:
            continue
        if g["id"] in seen:
            g["id"] = M.new_id()
        seen.add(g["id"])
        globes.append(g)
    sel = raw.get("selected")
    return {"version": VERSION, "globes": globes, "selected": sel if sel in seen else (globes[0]["id"] if globes else None)}


class SnowGlobeStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else data_dir() / "snowglobes.json"
        self.bak = self.path.with_suffix(".json.bak")
        self.load_result = "new"        # new | ok | recovered | failed

    def load(self) -> dict:
        """{'globes': [...], 'selected': id|None}. 파일이 없으면 빈 상태, 손상되면 백업에서 복구."""
        empty = {"version": VERSION, "globes": [], "selected": None}
        if not self.path.exists() and not self.bak.exists():
            self.load_result = "new"
            return empty
        for cand, tag in ((self.path, "ok"), (self.bak, "recovered")):
            if not cand.exists():
                continue
            try:
                data = migrate(_read(cand))
            except (OSError, ValueError) as e:
                log.warning("스노우볼 저장 파일을 읽지 못함(%s): %s", cand.name, e)
                continue
            if data is not None:
                self.load_result = tag
                if tag == "recovered":
                    log.warning("스노우볼 데이터를 백업에서 복구했습니다")
                return data
        self.load_result = "failed"
        return empty

    def save(self, globes: list, selected: str | None = None) -> bool:
        """안전 저장. 실패해도 기존 파일을 손상시키지 않고 False 를 돌려준다."""
        payload = {"version": VERSION, "selected": selected,
                   "globes": [M.clean_globe(g) for g in globes if g is not None][:MAX_GLOBES]}
        tmp = self.path.with_suffix(".json.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(payload, ensure_ascii=False, indent=1)
            json.loads(text)                                    # 직렬화 결과 검증
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            if self.path.exists():
                try:
                    _read(self.path)                            # 정상 본일 때만 백업으로 승격
                    os.replace(self.path, self.bak)
                except (OSError, ValueError):
                    pass
            os.replace(tmp, self.path)
            return True
        except (OSError, ValueError, TypeError) as e:
            log.error("스노우볼 저장 실패: %s", e)
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            return False
