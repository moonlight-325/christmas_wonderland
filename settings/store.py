"""Qt 와 무관한 설정 저장소 (검증·원자적 저장·백업·복구).

SettingsManager(Qt 래퍼)가 이 클래스를 감싼다. 순수 Python 이라 단독 테스트가 가능하다.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from core.logger import get_logger
from weather import spec as aw_spec
from .defaults import CHOICES, DEFAULTS, RANGES

log = get_logger("settings")
MAX_ROTATING_BACKUPS = 5


def _type_ok(default, value) -> bool:
    if default is None:
        return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, str):
        return isinstance(value, str)
    if isinstance(default, list):
        return isinstance(value, list)
    return True


def _merge(defaults: dict, loaded) -> dict:
    out = {}
    src = loaded if isinstance(loaded, dict) else {}
    for key, dv in defaults.items():
        if isinstance(dv, dict):
            out[key] = _merge(dv, src.get(key))
        else:
            lv = src.get(key, dv)
            out[key] = lv if _type_ok(dv, lv) else copy.deepcopy(dv)
    return out


def clamp_value(key: str, value):
    if key in RANGES:
        lo, hi = RANGES[key]
        value = max(lo, min(hi, value))
        if isinstance(DEFAULTS_LOOKUP(key), int):
            value = int(round(value))
    if key in CHOICES and value not in CHOICES[key]:
        value = CHOICES[key][0]
    return value


def DEFAULTS_LOOKUP(key: str):
    d = DEFAULTS
    for part in key.split("."):
        d = d[part]
    return d


def sanitize(data) -> dict:
    merged = _merge(DEFAULTS, data)
    for section, body in merged.items():
        if not isinstance(body, dict):
            continue
        for k in list(body.keys()):
            body[k] = clamp_value(f"{section}.{k}", body[k])
    # 표시 진입점이 모두 꺼져 프로그램을 다시 열기 어려워지는 상태를 방지한다.
    if not merged["app"].get("show_tray", True) and not merged["app"].get("show_taskbar", True):
        merged["app"]["show_tray"] = True
    merged["autoweather"] = aw_spec.clean_section(merged["autoweather"])
    merged["decor"]["items"] = clean_decor_items(merged["decor"].get("items"))
    merged["snowman"]["state"] = clean_snowman_state(merged["snowman"].get("state"))
    return merged


def clean_snowman_state(state) -> dict:
    """저장된 눈사람 상태에서 손상된 항목을 걸러낸다 (dynamic / decorative 유형 구분 유지)."""
    from snowman import model as sm
    state = state if isinstance(state, dict) else {}
    return {"items": sm.clean_items(state.get("items")), "balls": sm.clean_balls(state.get("balls")),
            "props": sm.clean_props(state.get("props"))}


def clean_decor_items(items) -> list:
    """저장된 장식 목록에서 손상된 항목을 걸러낸다."""
    out, seen = [], set()
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        try:
            iid = str(it["id"])
            kind = str(it["kind"])
            x, y = int(it.get("x", 100)), int(it.get("y", 100))
            scale = max(1, min(14, int(it.get("scale", 4))))
        except (KeyError, TypeError, ValueError):
            continue
        if iid in seen or len(out) >= 60:
            continue
        seen.add(iid)
        out.append({"id": iid, "kind": kind, "x": x, "y": y, "scale": scale,
                    "visible": bool(it.get("visible", True))})
    return out


class SettingsStore:
    def __init__(self, directory: Path, filename: str = "settings.json"):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / filename
        self.bak = self.dir / (filename + ".bak")
        self.tmp = self.dir / (filename + ".tmp")
        self.backup_dir = self.dir / "backups"
        self.data: dict = copy.deepcopy(DEFAULTS)
        self.dirty = False
        self.recovered_from: str | None = None

    # ---------- 읽기/복구 ----------
    @staticmethod
    def _read(path: Path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    def _rotating_backups(self):
        if not self.backup_dir.exists():
            return []
        return sorted(self.backup_dir.glob("settings_*.json"), reverse=True)

    def load(self) -> str:
        """설정을 읽는다. 반환: 'primary' | 'recovered' | 'defaults'."""
        self.recovered_from = None
        data = self._read(self.path) if self.path.exists() else None
        if data is not None:
            self.data = sanitize(data)
            self.dirty = False
            self.snapshot_backup()          # 정상 로드된 상태를 세션 시작 백업으로 보관
            return "primary"

        if self.path.exists():              # 손상 파일은 보존
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                shutil.move(str(self.path), str(self.dir / f"settings.corrupt-{stamp}.json"))
            except OSError:
                pass
            log.warning("settings.json 손상 - 백업에서 복구 시도")

        for cand in [self.bak, *self._rotating_backups()]:
            if cand.exists():
                data = self._read(cand)
                if data is not None:
                    self.data = sanitize(data)
                    self.recovered_from = cand.name
                    self.dirty = True
                    log.warning("백업에서 복구: %s", cand.name)
                    return "recovered"

        self.data = copy.deepcopy(DEFAULTS)
        self.dirty = self.path.exists() is False
        return "defaults"

    # ---------- 접근 ----------
    def get(self, key: str):
        d = self.data
        for part in key.split("."):
            d = d[part]
        return copy.deepcopy(d)

    def set(self, key: str, value) -> bool:
        """값이 바뀌면 True."""
        parts = key.split(".")
        d = self.data
        for part in parts[:-1]:
            d = d[part]
        leaf = parts[-1]
        if leaf not in d:
            raise KeyError(key)
        value = clamp_value(key, value)
        if d[leaf] == value:
            return False
        d[leaf] = copy.deepcopy(value)
        self.dirty = True
        return True

    def replace_all(self, data) -> None:
        self.data = sanitize(data)
        self.dirty = True

    def reset(self) -> None:
        self.data = copy.deepcopy(DEFAULTS)
        self.dirty = True

    # ---------- 저장/백업 ----------
    def save(self, manual: bool = False) -> bool:
        try:
            self.data["app"]["last_saved"] = datetime.now().isoformat(timespec="seconds")
            text = json.dumps(self.data, ensure_ascii=False, indent=2)
            with open(self.tmp, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            if self.path.exists() and self._read(self.path) is not None:
                shutil.copy2(self.path, self.bak)        # 직전 정상본 보관
            os.replace(self.tmp, self.path)              # 원자적 교체
            self.dirty = False
            if manual:
                self.snapshot_backup()
            return True
        except OSError as exc:
            log.error("설정 저장 실패: %s", exc)
            return False

    def snapshot_backup(self) -> Path | None:
        try:
            if not self.path.exists():
                return None
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = self.backup_dir / f"settings_{stamp}.json"
            shutil.copy2(self.path, dest)
            for old in self._rotating_backups()[MAX_ROTATING_BACKUPS:]:
                try:
                    old.unlink()
                except OSError:
                    pass
            return dest
        except OSError as exc:
            log.error("백업 실패: %s", exc)
            return None

    def import_from(self, path: Path) -> bool:
        data = self._read(Path(path))
        if data is None:
            return False
        self.replace_all(data)
        return True
