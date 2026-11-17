"""혼합형 자동 날씨 알고리즘 (Qt 무관 순수 파이썬 - 단독 테스트 가능).

작동 순서
 1) 사용자가 켠 날씨 목록 확인 -> 2) 가중치 랜덤으로 날씨 선택 -> 3) 날씨별 변수 성향 적용
 -> 4) 변수별 사용자 범위[min,max] 확인 -> 5) 자동 변수만 목표값 랜덤 결정
 -> 6) 현재값에서 목표값까지 부드럽게(지수 접근 + 초당 변화량 제한) 이동 -> 7) 지속시간 동안 유지 후 반복

핵심 약속
 - 자동 변수의 적용값은 항상 사용자 범위 안 (매 스텝 마지막에 clamp)
 - 수동 변수는 applied 에 아예 들어오지 않는다 (자동 날씨가 건드리지 않음)
 - 날씨 전환은 period 경계에서 한 번만 일어난다 (중복 전환 없음)
"""
from __future__ import annotations
from core.i18n import tr


import math
import random

from . import spec

MAX_DT = 1.0                 # 한 스텝에서 처리하는 최대 시간(초): 창이 멈췄다 돌아와도 값이 튀지 않게
RELEASE_TAU = 3.0            # 자동 날씨를 끌 때 수동값으로 돌아가는 시간 상수(초)
RELEASE_MAX = 10.0           # 위 전환이 끝나야 하는 최대 시간(초)


def reflect01(x: float) -> float:
    """실수를 0~1 구간에 거울 반사로 접어 넣는다 (범위 끝에 값이 몰리지 않게)."""
    x = abs(x) % 2.0
    return 2.0 - x if x > 1.0 else x


def tau_for(change_speed: int) -> float:
    """변수 변화 속도 0~100 -> 시간 상수(초). 0 = 30초(느림), 100 = 2초(빠름)."""
    return 30.0 * (2.0 / 30.0) ** (max(0, min(100, change_speed)) / 100.0)


def slew_fraction(change_speed: int) -> float:
    """초당 최대 변화량 (변수 전체 한계 폭에 대한 비율). 물리 엔진 충격 방지용."""
    return 0.003 + 0.06 * max(0, min(100, change_speed)) / 100.0


class AutoWeatherCore:
    def __init__(self, cfg: dict | None = None, seed=None):
        self.cfg = spec.clean_config(cfg or spec.default_config())
        self.rng = random.Random(seed)
        self.phase = "idle"                  # idle | run | release
        self.paused = False
        self.kind = "custom"                 # 현재 날씨 id (custom = 직접 설정한 종류)
        self.next_kind = "custom"            # 다음 날씨 예측
        self.period_len = 0.0                # 현재 날씨 총 지속시간(초)
        self.period_t = 0.0                  # 현재 날씨 경과시간(초)
        self.applied: dict[str, float] = {}  # 자동 변수 id -> 현재 적용값
        self.targets: dict[str, float] = {}
        self._release: dict[str, float] = {}
        self._release_t = 0.0
        self._manual_kind_seen: str | None = None
        self.transitions = 0                 # 날씨 전환 횟수 (테스트/진단용)

    # ------------------------------------------------------------------ 조회
    @property
    def active(self) -> bool:
        return self.phase in ("run", "release")

    def auto_numeric(self) -> list:
        return [v for v in spec.SETTING_VARS if self.cfg["vars"][v]["auto"]]

    def is_auto(self, vid: str) -> bool:
        return bool(self.cfg["vars"][vid]["auto"])

    def values(self) -> dict:
        """엔진이 쓸 현재 적용값 (자동 변수만, 타입 정리됨)."""
        return {vid: spec.clamp_var_value(vid, x) for vid, x in self.applied.items()}

    def remaining(self) -> float:
        return max(0.0, self.period_len - self.period_t)

    # ------------------------------------------------------------------ 설정
    def set_config(self, cfg: dict) -> None:
        """실행 중 설정 변경: 범위가 줄면 적용값/목표값을 즉시 새 범위로 맞춘다 (범위 절대 준수)."""
        self.cfg = spec.clean_config(cfg)
        if self.phase != "run":
            return
        self._clamp_all()
        if self.next_kind not in spec.KIND_IDS and self.cfg["vars"][spec.KIND_VAR]["auto"]:
            self.next_kind = self._pick_kind()
        elif self.cfg["vars"][spec.KIND_VAR]["auto"] and not self.cfg["kinds"].get(self.next_kind, {"on": False})["on"]:
            self.next_kind = self._pick_kind()

    def _clamp_all(self):
        for vid in list(self.applied):
            if not self.is_auto(vid):
                self.applied.pop(vid, None)
                self.targets.pop(vid, None)
                continue
            d = self.cfg["vars"][vid]
            self.applied[vid] = max(d["min"], min(d["max"], self.applied[vid]))
            if vid in self.targets:
                self.targets[vid] = max(d["min"], min(d["max"], self.targets[vid]))

    # ------------------------------------------------------------------ 선택/샘플링
    def _pick_kind(self) -> str:
        on = spec.enabled_kinds(self.cfg)
        if not on:
            return self.kind if self.kind in spec.KIND_IDS else "custom"
        if len(on) == 1:
            return on[0]
        weights = [self.cfg["kinds"][k]["weight"] for k in on]
        if sum(weights) <= 0:
            return self.rng.choice(on)
        return self.rng.choices(on, weights=weights, k=1)[0]

    def _profile(self, kind: str, vid: str):
        return spec.PROFILES.get(kind, {}).get(vid, spec.NEUTRAL_PROFILE)

    def _sample(self, vid: str, kind: str) -> float:
        d = self.cfg["vars"][vid]
        lo, hi = d["min"], d["max"]
        if hi <= lo:
            return float(lo)
        center, spread = self._profile(kind, vid)
        link = self.cfg["link"] / 100.0
        rnd = self.cfg["randomness"] / 100.0
        if self.rng.random() < link:                       # 날씨 연동: 종류별 성향으로 치우친 값
            u = reflect01(self.rng.gauss(center, spread * (0.4 + 1.6 * rnd)))
        else:                                              # 연동 없음: 사용자 범위 전체에서 균등
            u = self.rng.random()
        return lo + (hi - lo) * u

    def _pick_duration(self) -> float:
        d = self.cfg["vars"][spec.DURATION_VAR]
        if not d["auto"]:
            return float(spec.clamp_var_value(spec.DURATION_VAR, d["manual"]))
        lo, hi = d["min"], d["max"]
        p = 2.0 ** ((self.cfg["change_freq"] - 50) / 25.0)      # 빈도 높음 -> 짧은 쪽으로 치우침 (범위 안)
        return lo + (hi - lo) * (self.rng.random() ** p)

    def _roll_targets(self, only=None):
        for vid in (only or self.auto_numeric()):
            if self.is_auto(vid):
                self.targets[vid] = self._sample(vid, self.kind)

    # ------------------------------------------------------------------ 시작 / 정지
    def start(self, manual: dict, manual_kind: str | None = None) -> str | None:
        """시작. 켜진 날씨가 없으면 사유 문자열을 돌려주고 시작하지 않는다."""
        if not spec.enabled_kinds(self.cfg):
            return tr("켜진 날씨가 하나도 없어서 자동 날씨를 시작할 수 없어요. 날씨 종류를 하나 이상 켜 주세요.")
        errs = spec.validate_ranges(self.cfg)
        if errs:
            return errs[0][1]
        self.phase, self.paused = "run", False
        self.applied, self.targets = {}, {}
        self.transitions = 0
        for vid in self.auto_numeric():                    # 현재 수동값에서 출발 -> 시작 순간에 튀지 않음
            d = self.cfg["vars"][vid]
            self.applied[vid] = max(d["min"], min(d["max"], float(manual[vid])))
        self._begin_period(first=True, manual_kind=manual_kind)
        return None

    def pause(self):
        if self.phase == "run":
            self.paused = True

    def resume(self):
        if self.phase == "run":
            self.paused = False

    def stop(self, immediate: bool = False):
        """끄기. 기본은 수동값으로 부드럽게 복귀(release) 후 idle."""
        if self.phase != "run" or immediate or not self.applied:
            self.phase, self.paused = "idle", False
            self.applied, self.targets = {}, {}
            return
        self.phase, self.paused = "release", False
        self._release_t = 0.0

    # ------------------------------------------------------------------ 기간(날씨) 시작
    def _begin_period(self, first: bool = False, manual_kind: str | None = None):
        kind_auto = self.cfg["vars"][spec.KIND_VAR]["auto"]
        if kind_auto:
            self.kind = self._pick_kind() if first else (
                self.next_kind if self.cfg["kinds"].get(self.next_kind, {"on": False})["on"] else self._pick_kind())
            self.next_kind = self._pick_kind()
        else:
            self.kind = manual_kind or "custom"
            self.next_kind = self.kind
        self._manual_kind_seen = manual_kind if not kind_auto else None
        self.period_len = self._pick_duration()
        self.period_t = 0.0
        self._roll_targets()
        self.transitions += 1

    # ------------------------------------------------------------------ 한 스텝
    def step(self, dt: float, manual: dict, manual_kind: str | None = None) -> bool:
        """시간 dt(초) 진행. 적용값이 바뀌었으면 True."""
        if self.phase == "idle":
            return False
        dt = max(0.0, min(MAX_DT, dt))
        if self.phase == "release":
            return self._step_release(dt, manual)
        if self.paused or dt <= 0.0:
            return False
        before = dict(self.applied)
        self._sync_vars(manual, manual_kind)
        self.period_t += dt
        if self.period_t >= self.period_len:                # 날씨 전환: 경계에서 정확히 한 번
            self._begin_period(manual_kind=manual_kind)
        tau = tau_for(self.cfg["change_speed"])
        frac = slew_fraction(self.cfg["change_speed"])
        k = 1.0 - math.exp(-dt / tau)
        for vid, cur in self.applied.items():
            d = self.cfg["vars"][vid]
            v = spec.VARS_BY_ID[vid]
            diff = self.targets.get(vid, cur) - cur
            step = diff * k
            cap = (v["hi"] - v["lo"]) * frac * dt            # 물리 충격 방지: 초당 변화량 제한
            step = max(-cap, min(cap, step))
            new = cur + step
            self.applied[vid] = max(d["min"], min(d["max"], new))   # 범위 절대 준수
        return before != self.applied

    def _sync_vars(self, manual: dict, manual_kind: str | None):
        """실행 중에 자동/수동이 바뀐 변수 반영 + 수동 날씨 종류 변경 반영."""
        for vid in spec.SETTING_VARS:
            auto = self.is_auto(vid)
            if auto and vid not in self.applied:             # 수동 -> 자동 재개: 현재 수동값에서 이어서 조정
                d = self.cfg["vars"][vid]
                self.applied[vid] = max(d["min"], min(d["max"], float(manual[vid])))
                self.targets[vid] = self._sample(vid, self.kind)
            elif not auto and vid in self.applied:            # 자동 -> 수동: 즉시 자동 제어에서 제외
                self.applied.pop(vid)
                self.targets.pop(vid, None)
        kind_auto = self.cfg["vars"][spec.KIND_VAR]["auto"]
        if not kind_auto:
            mk = manual_kind or "custom"
            if mk != self.kind or self._manual_kind_seen != manual_kind:
                self.kind, self.next_kind = mk, mk
                self._manual_kind_seen = manual_kind
                self._roll_targets()                          # 사용자가 고른 종류로 즉시 새 목표
        elif self._manual_kind_seen is not None:              # 종류 수동 -> 자동: 다음 날씨부터 자동 선택
            self._manual_kind_seen = None
            self.next_kind = self._pick_kind()

    def _step_release(self, dt: float, manual: dict) -> bool:
        """자동 날씨를 끈 뒤: 자동 적용값 -> 수동값으로 부드럽게 복귀, 끝나면 idle (이후엔 설정값을 직접 사용)."""
        before = dict(self.applied)
        self._release_t += dt
        k = 1.0 - math.exp(-dt / RELEASE_TAU)
        all_home = True
        for vid in list(self.applied):
            v = spec.VARS_BY_ID[vid]
            span = v["hi"] - v["lo"]
            goal = max(v["lo"], min(v["hi"], float(manual[vid])))
            cap = span * slew_fraction(100) * dt
            diff = goal - self.applied[vid]
            self.applied[vid] += max(-cap, min(cap, diff * k))
            if abs(goal - self.applied[vid]) <= span * 0.004:
                self.applied[vid] = goal
            else:
                all_home = False
        if all_home or self._release_t >= RELEASE_MAX:
            self.phase = "idle"
            self.applied, self.targets = {}, {}
            return True
        return before != self.applied
