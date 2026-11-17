"""자동 날씨 컨트롤러 (Qt): 코어 알고리즘 + 설정 저장 + 단일 제어권 + 프리셋.

단일 제어권 규칙
 - 자동 날씨는 설정 파일의 수동값을 절대 덮어쓰지 않는다. 자동 적용값은 메모리(core.applied)에만 있고,
   눈 엔진은 settings.effective(key) 로 '자동 적용값 또는 수동값' 중 하나만 읽는다.
 - 자동 조정 중인 변수를 사용자가 직접 바꾸면(settings.set 훅) 그 변수만 즉시 수동으로 전환된다.
"""
from __future__ import annotations
from core.i18n import tr


import copy

from PySide6.QtCore import QElapsedTimer, QObject, QTimer, Signal

from core.logger import get_logger
from core.paths import data_dir
from . import spec
from .core import AutoWeatherCore
from .presets import PresetStore

log = get_logger("autoweather")
TICK_MS = 100
STATE_EVERY = 5          # 틱 5번(0.5초)마다 UI 상태 갱신 신호


class AutoWeather(QObject):
    applied = Signal()           # 자동 적용값이 바뀜 (엔진 반영용, ~10Hz)
    state_changed = Signal()     # 상태/설정/프리셋 변경 (UI 갱신용)
    notice = Signal(str)         # 사용자 안내 메시지

    def __init__(self, settings, presets_dir=None, seed=None, parent=None):
        super().__init__(parent)
        self.s = settings
        self.presets = PresetStore(presets_dir or data_dir())
        self.core = AutoWeatherCore(self._cfg(), seed=seed)
        self._vals: dict = {}
        self._n = 0
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._busy = False                       # 내부 설정 쓰기 중 재진입 방지
        settings.auto = self
        settings.changed.connect(self._on_changed)

    # ------------------------------------------------------------------ 설정 읽기
    def _section(self) -> dict:
        return self.s.get("autoweather")

    def _cfg(self) -> dict:
        return spec.config_of(self._section())

    def config(self) -> dict:
        return self._cfg()

    def _manual_values(self) -> dict:
        return {vid: self.s.store.get(spec.VARS_BY_ID[vid]["key"]) for vid in spec.SETTING_VARS}

    def _manual_kind(self):
        k = self.s.store.get("weather.kind")
        return None if k == "custom" else k

    # ------------------------------------------------------------------ 엔진/설정창이 쓰는 값
    def effective(self, key: str):
        """자동 날씨가 이 설정 키를 조정 중이면 현재 적용값, 아니면 None."""
        if self.core.phase == "idle":
            return None
        if key == "weather.kind":
            if self.core.is_auto(spec.KIND_VAR) and self.core.phase == "run":
                return self.core.kind
            return None
        vid = spec.KEY_TO_VAR.get(key)
        if vid is None or vid not in self._vals:
            return None
        return self._vals[vid]

    def controlled_vars(self) -> list:
        """지금 자동 날씨가 실제로 조정 중인 변수 id 목록."""
        if self.core.phase != "run":
            return []
        out = [v for v in spec.SETTING_VARS if v in self._vals]
        if self.core.is_auto(spec.KIND_VAR):
            out.append(spec.KIND_VAR)
        if self.core.is_auto(spec.DURATION_VAR):
            out.append(spec.DURATION_VAR)
        return out

    def applied_text(self, vid: str) -> str:
        """변수의 현재 적용값을 표시용 문자열로. 수동 변수는 수동값."""
        if vid == spec.KIND_VAR:
            if self.core.phase == "run":
                return spec.KIND_NAME.get(self.core.kind, "직접 설정")
            k = self.s.get("weather.kind")
            return spec.KIND_NAME.get(k, "직접 설정")
        v = spec.VARS_BY_ID[vid]
        if vid == spec.DURATION_VAR:
            if self.core.phase == "run" and self.core.period_len:
                x = self.core.period_len
            elif self.core.cfg["vars"][vid]["auto"]:
                return "-"
            else:
                x = self.core.cfg["vars"][vid]["manual"]
        elif vid in self._vals:
            x = self._vals[vid]
        else:
            x = self.s.get(v["key"])
        return f"{x * v['scale']:.{v['dec']}f}{v['suffix']}"

    def status(self) -> dict:
        c = self.core
        return {
            "phase": c.phase, "paused": c.paused,
            "running": c.phase == "run" and not c.paused,
            "active": c.phase == "run",
            "kind": c.kind if c.phase == "run" else None,
            "next_kind": c.next_kind if c.phase == "run" else None,
            "remaining": c.remaining() if c.phase == "run" else 0.0,
            "period": c.period_len if c.phase == "run" else 0.0,
        }

    # ------------------------------------------------------------------ 사용자 직접 변경 훅
    def on_user_set(self, key: str) -> None:
        """SettingsManager.set 이 호출: 자동 조정 중인 변수를 직접 바꾸면 그 변수만 수동으로 전환."""
        if self._busy or self.core.phase != "run":
            return
        vid = spec.KEY_TO_VAR.get(key) or (spec.KIND_VAR if key == "weather.kind" else None)
        if vid is None:
            return
        if self.core.is_auto(vid):
            self._write_vars_auto(vid, False)
            self.core.set_config(self._cfg())        # 이 변수만 즉시 자동 제어에서 제외
            self._vals = self.core.values()
            self.state_changed.emit()

    # ------------------------------------------------------------------ 설정 쓰기 도우미
    def _write(self, key: str, value, save: bool = False):
        self._busy = True
        try:
            self.s.set(key, value, save=save)
        finally:
            self._busy = False

    def _write_vars_auto(self, vid: str, auto: bool):
        vars_ = self._section()["vars"]
        vars_[vid]["auto"] = bool(auto)
        self._write("autoweather.vars", vars_, save=True)

    def _commit_cfg(self, cfg: dict, preset: str | None = None):
        """검증된 설정을 settings 에 한꺼번에 기록 (프리셋 불러오기/초기화)."""
        for k in ("kinds", "vars"):
            self._write(f"autoweather.{k}", copy.deepcopy(cfg[k]))
        for name in spec.PARAMS:
            self._write(f"autoweather.{name}", cfg[name])
        if preset is not None:
            self._write("autoweather.preset", preset)
        self.s.save_now()

    def _on_changed(self, key: str):
        if self._busy:
            return
        if key == "*":                                # 설정 초기화 / 백업 복원
            sec = self._section()
            self.core.set_config(self._cfg())
            if not sec["enabled"] and self.core.active:
                self.core.stop(immediate=True)
                self._vals = {}
                self._timer.stop()
                self.applied.emit()
            elif sec["enabled"] and not self.core.active:
                self.restore()
            self.state_changed.emit()
        elif key.startswith("autoweather."):
            self.core.set_config(self._cfg())
            self.state_changed.emit()

    # ------------------------------------------------------------------ 시작 / 정지
    def restore(self) -> None:
        """프로그램 시작 시: 저장된 상태가 '시작됨' 이면 이어서 실행."""
        sec = self._section()
        if not sec["enabled"] or self.core.active:
            return
        err = self.core.start(self._manual_values(), self._manual_kind())
        if err:
            log.warning("자동 날씨 복원 실패: %s", err)
            self._write("autoweather.enabled", False, save=True)
            return
        if sec["paused"]:
            self.core.pause()
        self._begin_ticking()

    def _begin_ticking(self):
        self._vals = self.core.values()
        self._clock.start()
        self._n = 0
        self._timer.start()
        self.applied.emit()
        self.state_changed.emit()

    def start(self) -> tuple[bool, str]:
        if self.core.phase == "run":
            return True, ""
        self.core.set_config(self._cfg())
        err = self.core.start(self._manual_values(), self._manual_kind())
        if err:
            self.notice.emit(err)
            return False, err
        self._write("autoweather.enabled", True)
        self._write("autoweather.paused", False, save=True)
        self._begin_ticking()
        return True, ""

    def pause(self):
        if self.core.phase == "run" and not self.core.paused:
            self.core.pause()
            self._write("autoweather.paused", True, save=True)
            self.state_changed.emit()

    def resume(self):
        if self.core.phase == "run" and self.core.paused:
            self.core.resume()
            self._clock.restart()
            self._write("autoweather.paused", False, save=True)
            self.state_changed.emit()

    def stop(self):
        """자동 날씨 끄기: 적용값이 수동값으로 부드럽게 돌아간 뒤 완전히 해제."""
        if self.core.phase != "run":
            return
        self.core.stop()
        self._write("autoweather.enabled", False)
        self._write("autoweather.paused", False, save=True)
        if self.core.phase == "idle":
            self._vals = {}
            self._timer.stop()
            self.applied.emit()
        else:
            self._clock.restart()
        self.state_changed.emit()

    def shutdown(self):
        self._timer.stop()

    # ------------------------------------------------------------------ 틱
    def _tick(self):
        try:
            dt = self._clock.restart() / 1000.0
            was = self.core.phase
            changed = self.core.step(dt, self._manual_values(), self._manual_kind())
            if self.core.phase == "idle":
                self._vals = {}
                self._timer.stop()
                self.applied.emit()
                self.state_changed.emit()
                return
            if changed or was != self.core.phase:
                self._vals = self.core.values()
                self.applied.emit()
            self._n += 1
            if self._n % STATE_EVERY == 0:
                self.state_changed.emit()
        except Exception:
            log.exception("자동 날씨 틱 오류 - 자동 날씨를 중지합니다")
            self.core.stop(immediate=True)
            self._vals = {}
            self._timer.stop()
            self._write("autoweather.enabled", False, save=True)
            self.applied.emit()
            self.state_changed.emit()

    # ------------------------------------------------------------------ 변수 설정 (UI)
    def _freeze_to_manual(self, vid: str):
        """자동 -> 수동 전환 시 현재 적용값을 수동값으로 굳힌다 (값이 튀지 않고 그대로 유지)."""
        if self.core.phase != "run":
            return
        if vid == spec.KIND_VAR:
            if self.core.kind in spec.KIND_IDS:
                self._write("weather.kind", self.core.kind)
        elif vid == spec.DURATION_VAR:
            vars_ = self._section()["vars"]
            vars_[vid]["manual"] = spec.clamp_var_value(vid, self.core.period_len)
            self._write("autoweather.vars", vars_)
        elif vid in self._vals:
            self._write(spec.VARS_BY_ID[vid]["key"], self._vals[vid])

    def set_var_auto(self, vid: str, auto: bool):
        if vid not in spec.ALL_VAR_IDS or bool(self._section()["vars"][vid]["auto"]) == bool(auto):
            return
        if not auto:
            self._freeze_to_manual(vid)
        self._write_vars_auto(vid, auto)
        self.core.set_config(self._cfg())
        self.state_changed.emit()

    def set_all_auto(self, auto: bool):
        vars_ = self._section()["vars"]
        if not auto:
            for vid in spec.ALL_VAR_IDS:
                if vars_[vid]["auto"]:
                    self._freeze_to_manual(vid)
            vars_ = self._section()["vars"]
        for vid in spec.ALL_VAR_IDS:
            vars_[vid]["auto"] = bool(auto)
        self._write("autoweather.vars", vars_, save=True)
        self.core.set_config(self._cfg())
        self.state_changed.emit()

    def set_var_range(self, vid: str, lo, hi) -> tuple[bool, str]:
        """최솟값/최댓값 저장. 최솟값 > 최댓값이거나 허용 범위 밖이면 저장하지 않고 이유를 돌려준다."""
        msg = spec.validate_range(vid, lo, hi)
        if msg:
            self.notice.emit(msg)
            return False, msg
        vars_ = self._section()["vars"]
        vars_[vid]["min"], vars_[vid]["max"] = spec.clamp_var_value(vid, lo), spec.clamp_var_value(vid, hi)
        self._write("autoweather.vars", vars_, save=True)
        self.core.set_config(self._cfg())
        self.state_changed.emit()
        return True, ""

    def reset_var_range(self, vid: str):
        if vid in (spec.KIND_VAR,) or vid not in spec.VARS_BY_ID:
            return
        d = spec.VARS_BY_ID[vid]
        self.set_var_range(vid, d["dmin"], d["dmax"])

    def set_duration_manual(self, seconds) -> tuple[bool, str]:
        v = spec.VARS_BY_ID[spec.DURATION_VAR]
        if not isinstance(seconds, (int, float)) or seconds < v["lo"] or seconds > v["hi"]:
            msg = tr("날씨 지속시간: 허용 범위({0}~{1} 초)를 벗어났어요.").format(v['lo'], v['hi'])
            self.notice.emit(msg)
            return False, msg
        vars_ = self._section()["vars"]
        vars_[spec.DURATION_VAR]["manual"] = int(round(seconds))
        self._write("autoweather.vars", vars_, save=True)
        self.core.set_config(self._cfg())
        self.state_changed.emit()
        return True, ""

    # ------------------------------------------------------------------ 날씨 종류 / 변화 설정
    def set_kind_on(self, kid: str, on: bool) -> tuple[bool, str]:
        kinds = self._section()["kinds"]
        if kid not in kinds:
            return False, ""
        if not on and self.core.phase == "run" and kinds[kid]["on"] and len(spec.enabled_kinds(self._cfg())) <= 1:
            msg = tr("실행 중에는 켜진 날씨를 모두 끌 수 없어요. 먼저 자동 날씨를 중지하거나 다른 날씨를 켜 주세요.")
            self.notice.emit(msg)
            return False, msg
        kinds[kid]["on"] = bool(on)
        self._write("autoweather.kinds", kinds, save=True)
        self.core.set_config(self._cfg())
        self.state_changed.emit()
        return True, ""

    def set_kind_weight(self, kid: str, weight: int):
        kinds = self._section()["kinds"]
        if kid in kinds:
            kinds[kid]["weight"] = int(max(0, min(100, round(weight))))
            self._write("autoweather.kinds", kinds)
            self.core.set_config(self._cfg())

    def set_param(self, name: str, value):
        if name in spec.PARAMS:
            self._write(f"autoweather.{name}", int(max(0, min(100, round(value)))))
            self.core.set_config(self._cfg())

    def save_now(self):
        self.s.save_now()

    # ------------------------------------------------------------------ 복원 / 프리셋
    def reset_defaults(self):
        """기본 설정 복원 (실행 상태는 유지, 설정값만 기본으로)."""
        self._commit_cfg(spec.default_config(), preset="")
        self.core.set_config(self._cfg())
        self.state_changed.emit()

    def load_preset(self, name: str) -> tuple[bool, str]:
        cfg = self.presets.get(name)
        if cfg is None:
            return False, tr("프리셋을 찾을 수 없어요.")
        if self.core.phase == "run" and not spec.enabled_kinds(cfg):
            msg = tr("이 프리셋은 켜진 날씨가 없어서 실행 중에는 불러올 수 없어요.")
            self.notice.emit(msg)
            return False, msg
        self._commit_cfg(cfg, preset=name)
        self.core.set_config(self._cfg())
        self.state_changed.emit()
        return True, ""

    def save_preset(self, name: str, overwrite: bool = False) -> tuple[bool, str]:
        ok, msg = self.presets.save(name, self._cfg(), overwrite=overwrite)
        if ok:
            self._write("autoweather.preset", name.strip(), save=True)
        self.state_changed.emit()
        return ok, msg

    def rename_preset(self, old: str, new: str) -> tuple[bool, str]:
        ok, msg = self.presets.rename(old, new)
        if ok and self._section()["preset"] == old:
            self._write("autoweather.preset", new.strip(), save=True)
        self.state_changed.emit()
        return ok, msg

    def delete_preset(self, name: str) -> tuple[bool, str]:
        ok, msg = self.presets.delete(name)
        if ok and self._section()["preset"] == name:
            self._write("autoweather.preset", "", save=True)
        self.state_changed.emit()
        return ok, msg
