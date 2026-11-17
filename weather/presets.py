"""자동 날씨 프리셋 저장소: 기본 제공 5종 + 사용자 프리셋(data/autoweather_presets.json, 별도 파일).

기본 제공 프리셋은 이름 변경/삭제/앱에서의 덮어쓰기는 안 되지만, JSON 파일에 같은 이름의 항목을 넣으면 그 내용으로 대체된다
(빠진 항목은 기본 제공 값 그대로). 대체 항목을 JSON 에서 지우면 기본 제공 값으로 돌아간다.
파일을 고치면 프리셋을 불러올 때 자동으로 다시 읽는다 (앱을 껐다 켜지 않아도 됨)."""
from __future__ import annotations
from core.i18n import tr


import copy
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from core.logger import get_logger
from . import spec

log = get_logger("autoweather")
FILENAME = "autoweather_presets.json"
MAX_NAME = 24
MAX_PRESETS = 50


class PresetStore:
    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / FILENAME
        self.presets: dict[str, dict] = {}
        self.overrides: dict[str, dict] = {}              # 기본 제공 프리셋 이름 -> JSON 파일의 대체 내용
        self._mtime = None
        self.load()

    # ---------------------------------------------------------------- 읽기 / 쓰기
    def _stat(self):
        try:
            return self.path.stat().st_mtime_ns
        except OSError:
            return None

    def load(self) -> None:
        self.presets = {}
        self.overrides = {}
        self._mtime = self._stat()
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or ("presets" in data and not isinstance(data["presets"], list)):
                raise ValueError("프리셋 파일 구조가 올바르지 않음")
            items = data.get("presets", [])
        except (OSError, ValueError):
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            try:                                                 # 손상 파일은 보존하고 빈 목록으로 계속
                shutil.move(str(self.path), str(self.dir / f"autoweather_presets.corrupt-{stamp}.json"))
            except OSError:
                pass
            log.warning("autoweather_presets.json 손상 - 빈 목록으로 시작")
            return
        for it in items:
            if not isinstance(it, dict) or not isinstance(it.get("name"), str):
                continue
            name = it["name"].strip()
            if name in spec.PRESETS:                         # 기본 제공 이름: 파일 내용으로 대체 (빠진 값은 기본 제공 값)
                self.overrides.setdefault(name, spec.clean_config(it.get("config"), base=copy.deepcopy(spec.PRESETS[name])))
                continue
            if not name or name in self.presets or len(self.presets) >= MAX_PRESETS:
                continue
            self.presets[name] = spec.clean_config(it.get("config"))

    def _write(self) -> tuple[bool, str]:
        try:
            items = [{"name": n, "config": c} for n, c in self.overrides.items()]      # 대체 항목을 잃지 않도록 함께 기록
            items += [{"name": n, "config": c} for n, c in self.presets.items()]
            body = {"version": 1, "presets": items}
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(body, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            self._mtime = self._stat()
            return True, ""
        except OSError as exc:
            log.error("프리셋 저장 실패: %s", exc)
            return False, tr("프리셋 파일을 저장하지 못했어요. 폴더 쓰기 권한을 확인해 주세요.")

    def _commit(self, before: dict) -> tuple[bool, str]:
        """저장에 실패하면 메모리 목록을 이전 상태로 되돌려, 화면과 파일이 어긋나지 않게 한다."""
        ok, msg = self._write()
        if not ok:
            self.presets = before
        return ok, msg

    # ---------------------------------------------------------------- 조회
    def builtin_names(self) -> list:
        return list(spec.PRESET_NAMES)

    def user_names(self) -> list:
        return list(self.presets)

    def is_builtin(self, name: str) -> bool:
        return name in spec.PRESETS

    def exists(self, name: str) -> bool:
        return name in spec.PRESETS or name in self.presets

    def get(self, name: str):
        if self._stat() != self._mtime:                      # 파일을 직접 고쳤으면 다시 읽는다
            self.load()
        src = self.overrides.get(name) or spec.PRESETS.get(name) or self.presets.get(name)
        return copy.deepcopy(src) if src is not None else None

    # ---------------------------------------------------------------- 이름 검사
    def _check_name(self, name: str) -> tuple[bool, str]:
        if not name or not name.strip():
            return False, tr("프리셋 이름을 입력해 주세요.")
        if len(name.strip()) > MAX_NAME:
            return False, tr("프리셋 이름은 {0}자 이하로 입력해 주세요.").format(MAX_NAME)
        return True, ""

    # ---------------------------------------------------------------- 사용자 동작
    def save(self, name: str, cfg: dict, overwrite: bool = False) -> tuple[bool, str]:
        ok, msg = self._check_name(name)
        if not ok:
            return False, msg
        name = name.strip()
        if name in spec.PRESETS:
            return False, tr("기본 제공 프리셋 이름은 사용할 수 없어요. 다른 이름을 입력해 주세요.")
        if name in self.presets and not overwrite:
            return False, tr("같은 이름의 프리셋이 이미 있어요.")
        if name not in self.presets and len(self.presets) >= MAX_PRESETS:
            return False, tr("프리셋은 최대 {0}개까지 저장할 수 있어요.").format(MAX_PRESETS)
        errs = spec.validate_ranges(cfg)
        if errs:
            return False, errs[0][1]
        before = dict(self.presets)
        self.presets[name] = spec.clean_config(cfg)
        return self._commit(before)

    def rename(self, old: str, new: str) -> tuple[bool, str]:
        if old in spec.PRESETS:
            return False, tr("기본 제공 프리셋은 이름을 바꿀 수 없어요.")
        if old not in self.presets:
            return False, tr("이름을 바꿀 프리셋을 찾을 수 없어요.")
        ok, msg = self._check_name(new)
        if not ok:
            return False, msg
        new = new.strip()
        if new == old:
            return True, ""
        if self.exists(new):
            return False, tr("같은 이름의 프리셋이 이미 있어요.")
        before = self.presets
        self.presets = {(new if n == old else n): c for n, c in before.items()}
        return self._commit(before)

    def delete(self, name: str) -> tuple[bool, str]:
        if name in spec.PRESETS:
            return False, tr("기본 제공 프리셋은 삭제할 수 없어요.")
        if name not in self.presets:
            return False, tr("삭제할 프리셋을 찾을 수 없어요.")
        before = dict(self.presets)
        del self.presets[name]
        return self._commit(before)
