"""어드벤트 상태 저장소 (advent_state.json).  Qt 무관, 원자적 저장 + 백업 복구.

예전 버전이 저장한 `test` 항목은 읽을 때 무시하고 다음 저장 때 사라진다.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from core.logger import get_logger
from .logic import DAYS

log = get_logger("advent.state")
SCHEMA = 1
MAX_BACKUPS = 3
MAX_WISH = 200

DEFAULTS = {
    "schema_version": SCHEMA,
    "opened": {},                       # {"2026": [1, 2, 3]}  실제 날짜 기준 개봉 기록
    "events": {},                       # {"2026": {"3": {...}}} 실제 기록의 이벤트 결과
    "last_opened": None,                # {"year":2026,"day":3,"at":"ISO"}
    "settings": {                       # 선물 콘텐츠 설정
        "content_path": "",
        "animations": True,
        "events": True,
    },
}


def _days(value) -> list[int]:
    out = set()
    if isinstance(value, list):
        for v in value:
            if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= DAYS:
                out.add(v)
    return sorted(out)


def _event_result(value):
    if not isinstance(value, dict):
        return None
    r = {}
    if isinstance(value.get("done"), bool):
        r["done"] = value["done"]
    if isinstance(value.get("correct"), bool):
        r["correct"] = value["correct"]
    for k in ("choice", "best"):
        if isinstance(value.get(k), int) and not isinstance(value.get(k), bool):
            r[k] = max(0, min(9999, value[k]))
    if isinstance(value.get("text"), str):
        r["text"] = value["text"][:MAX_WISH]
    return r


def _events(value, nested: bool):
    """nested=True: {year:{day:result}},  False: {day:result}"""
    out = {}
    if not isinstance(value, dict):
        return out
    if nested:
        for y, inner in value.items():
            if str(y).isdigit():
                sub = _events(inner, False)
                if sub:
                    out[str(y)] = sub
    else:
        for d, res in value.items():
            if str(d).isdigit() and 1 <= int(d) <= DAYS:
                r = _event_result(res)
                if r is not None:
                    out[str(int(d))] = r
    return out


def _last(value, with_year: bool):
    if not isinstance(value, dict):
        return None
    d = value.get("day")
    if not (isinstance(d, int) and not isinstance(d, bool) and 1 <= d <= DAYS):
        return None
    out = {"day": d, "at": value.get("at") if isinstance(value.get("at"), str) else ""}
    if with_year:
        y = value.get("year")
        if not (isinstance(y, int) and not isinstance(y, bool) and 1970 <= y <= 9999):
            return None
        out["year"] = y
    return out


def sanitize(data) -> dict:
    src = data if isinstance(data, dict) else {}
    out = copy.deepcopy(DEFAULTS)
    opened = src.get("opened")
    if isinstance(opened, dict):
        for y, days in opened.items():
            if str(y).isdigit():
                ds = _days(days)
                if ds:
                    out["opened"][str(y)] = ds
    out["events"] = _events(src.get("events"), True)
    out["last_opened"] = _last(src.get("last_opened"), True)

    s = src.get("settings") if isinstance(src.get("settings"), dict) else {}
    st = out["settings"]
    if isinstance(s.get("content_path"), str):
        st["content_path"] = s["content_path"][:500]
    for k in ("animations", "events"):
        if isinstance(s.get(k), bool):
            st[k] = s[k]
    return out


class AdventStore:
    def __init__(self, directory: Path, filename: str = "advent_state.json"):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / filename
        self.bak = self.dir / (filename + ".bak")
        self.tmp = self.dir / (filename + ".tmp")
        self.backup_dir = self.dir / "backups"
        self.data = copy.deepcopy(DEFAULTS)
        self.recovered_from: str | None = None
        self.save_failed = False          # 마지막 저장 시도가 실패했는지 (창이 사용자에게 안내)

    # ------------------------------------------------------------ 읽기/복구
    @staticmethod
    def _read(path: Path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else None
        except (OSError, ValueError):
            return None

    def _rotating(self):
        return sorted(self.backup_dir.glob("advent_state_*.json"), reverse=True) if self.backup_dir.exists() else []

    def load(self) -> str:
        self.recovered_from = None
        d = self._read(self.path) if self.path.exists() else None
        if d is not None:
            self.data = sanitize(d)
            self.snapshot()
            return "primary"
        if self.path.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                shutil.move(str(self.path), str(self.dir / f"advent_state.corrupt-{stamp}.json"))
            except OSError:
                pass
            log.warning("advent_state.json 손상 - 백업에서 복구 시도")
        for cand in [self.bak, *self._rotating()]:
            if cand.exists():
                d = self._read(cand)
                if d is not None:
                    self.data = sanitize(d)
                    self.recovered_from = cand.name
                    self.save()
                    return "recovered"
        self.data = copy.deepcopy(DEFAULTS)
        return "defaults"

    # ------------------------------------------------------------ 저장
    def save(self) -> bool:
        try:
            text = json.dumps(self.data, ensure_ascii=False, indent=2)
            with open(self.tmp, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            if self.path.exists() and self._read(self.path) is not None:
                shutil.copy2(self.path, self.bak)
            os.replace(self.tmp, self.path)
            self.save_failed = False
            return True
        except OSError as exc:
            log.error("어드벤트 상태 저장 실패: %s", exc)
            self.save_failed = True
            return False

    def snapshot(self):
        try:
            if not self.path.exists():
                return
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(self.path, self.backup_dir / f"advent_state_{stamp}.json")
            for old in self._rotating()[MAX_BACKUPS:]:
                old.unlink(missing_ok=True)
        except OSError as exc:
            log.error("어드벤트 백업 실패: %s", exc)

    # ------------------------------------------------------------ 개봉 기록
    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def opened_days(self, year: int) -> set[int]:
        return set(self.data["opened"].get(str(year), []))

    def mark_opened(self, year: int, day: int) -> None:
        cur = self.opened_days(year)
        cur.add(day)
        self.data["opened"][str(year)] = sorted(cur)
        self.data["last_opened"] = {"year": year, "day": day, "at": self._now()}
        self.save()

    @property
    def last_opened(self):
        return copy.deepcopy(self.data["last_opened"])

    def years_with_records(self) -> list[int]:
        return sorted(int(y) for y in self.data["opened"])

    # ------------------------------------------------------------ 이벤트 결과
    def get_event(self, year: int, day: int):
        return copy.deepcopy(self.data["events"].get(str(year), {}).get(str(day)))

    def set_event(self, year: int, day: int, result: dict) -> None:
        self.data["events"].setdefault(str(year), {})[str(day)] = _event_result(result) or {}
        self.save()

    # ------------------------------------------------------------ 콘텐츠 설정
    def get_setting(self, key: str):
        return self.data["settings"][key]

    def set_setting(self, key: str, value) -> None:
        if key not in self.data["settings"]:
            raise KeyError(key)
        if isinstance(DEFAULTS["settings"][key], bool):
            value = bool(value)
        else:
            value = str(value)[:500]
        self.data["settings"][key] = value
        self.save()
