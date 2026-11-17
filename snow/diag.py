"""프레임 진단 수집기 (순수 Python, Qt 불필요).

일정 시간(기본 5초)마다 '[프레임 요약]' 블록 하나로 정리해 로그에 남긴다.
눈 엔진 틱 / 오버레이 paint / 창 추적 / GC / CPU 사용을 한 표에서 비교해 '시간이 어디로 가는지' 한눈에 보이게 한다.
"""
from __future__ import annotations

import gc
import time

REPORT_EVERY = 5.0       # 요약 로그 간격(초)


def _pct(vals: list, q: float) -> float:
    if not vals:
        return 0.0
    v = sorted(vals)
    return v[min(len(v) - 1, int(q * len(v)))]


def _avg(vals: list) -> float:
    return sum(vals) / len(vals) if vals else 0.0


class FrameDiag:
    def __init__(self, want_ms: float = 33.3):
        self.want_ms = want_ms
        self._gc_t = 0.0
        self._gc_on = False
        self.reset()

    # ------------------------------------------------------------------ 수집
    def reset(self):
        self.t0 = time.perf_counter()
        self.cpu0 = time.process_time()
        self.gaps: list = []            # 틱 간격(ms)
        self.late: list = []            # 타이머가 예정보다 늦은 정도(ms)
        self.inner: list = []           # 틱 함수 안에서 쓴 시간(ms)
        self.parts = {"계산": [], "장식 영역": [], "그리기 요청": []}
        self.track: list = []           # 창 추적 한 번의 GUI 처리(ms)
        self.tparts = {"창 수집": [], "표면 계산": [], "시뮬 반영": [], "바닥/전체화면": []}
        self.track_full = 0             # 안전망/변경으로 표면을 다시 계산한 횟수
        self.track_same = 0             # 그 중 결과가 그대로여서 반영을 건너뛴 횟수
        self.gc_ms = 0.0
        self.gc_n = [0, 0, 0]
        self.gc_max = 0.0

    def start_gc(self):
        if not self._gc_on:
            gc.callbacks.append(self._gc_cb)
            self._gc_on = True

    def stop_gc(self):
        if self._gc_on:
            try:
                gc.callbacks.remove(self._gc_cb)
            except ValueError:
                pass
            self._gc_on = False

    def _gc_cb(self, phase, info):
        if phase == "start":
            self._gc_t = time.perf_counter()
        else:
            dt = (time.perf_counter() - self._gc_t) * 1000.0
            self.gc_ms += dt
            self.gc_max = max(self.gc_max, dt)
            gen = int(info.get("generation", 0))
            if 0 <= gen <= 2:
                self.gc_n[gen] += 1

    def on_tick(self, gap_ms: float, interval_ms: float, inner_ms: float, calc_ms: float, decor_ms: float, update_ms: float):
        self.gaps.append(gap_ms)
        self.late.append(max(0.0, gap_ms - interval_ms))
        self.inner.append(inner_ms)
        self.parts["계산"].append(calc_ms)
        self.parts["장식 영역"].append(decor_ms)
        self.parts["그리기 요청"].append(update_ms)

    def on_track(self, total_ms: float, collect_ms: float, surf_ms: float, push_ms: float, misc_ms: float,
                 full: bool, same: bool):
        self.track.append(total_ms)
        self.tparts["창 수집"].append(collect_ms)
        if full:
            self.track_full += 1
            self.track_same += 1 if same else 0
            self.tparts["표면 계산"].append(surf_ms)
            self.tparts["시뮬 반영"].append(push_ms)
        self.tparts["바닥/전체화면"].append(misc_ms)

    # ------------------------------------------------------------------ 보고
    def due(self, now: float | None = None) -> bool:
        now = time.perf_counter() if now is None else now
        return now - self.t0 >= REPORT_EVERY and len(self.gaps) >= 3

    def build(self, overlays: list, sim, extra: dict | None = None) -> str:
        """overlays: [(라벨, stat dict)] / sim: 개수 표시용. 호출 후 reset() 한다."""
        wall = max(1e-6, time.perf_counter() - self.t0)
        cpu = time.process_time() - self.cpu0
        g = self.gaps
        n = len(g)
        fps = n / wall
        want = self.want_ms
        over = lambda lim: 100.0 * sum(1 for x in g if x > lim) / max(1, n)
        L = []
        L.append("[프레임 요약] %.1f초 동안 틱 %d회 → 실제 %.1ffps (목표 %.0ffps)" % (wall, n, fps, 1000.0 / want))
        L.append("  ├ 프레임 간격   평균 %6.1f │ 최소 %6.1f │ p50 %6.1f │ p95 %6.1f │ 최대 %6.1f ms"
                 % (_avg(g), min(g), _pct(g, 0.5), _pct(g, 0.95), max(g)))
        L.append("  │               목표(%.0fms) 초과 %3.0f%% │ 2배(%.0fms) 초과 %3.0f%% │ 3배(%.0fms) 초과 %3.0f%%"
                 % (want, over(want * 1.15), want * 2, over(want * 2), want * 3, over(want * 3)))
        L.append("  ├ 타이머 지연   평균 %6.1f │ 최대 %6.1f ms   (예정 시각보다 늦게 불린 정도: 클수록 메인 스레드가 딴 일로 바쁨)"
                 % (_avg(self.late), max(self.late)))
        pm = self.parts
        L.append("  ├ 틱 안쪽       평균 %6.1f ms = 계산 %.1f + 장식영역 %.1f + 그리기요청 %.1f   (최대 %.1f)"
                 % (_avg(self.inner), _avg(pm["계산"]), _avg(pm["장식 영역"]), _avg(pm["그리기 요청"]), max(self.inner)))
        busy = _avg(self.inner)
        L.append("  ├ CPU / GC      프로세스 CPU %3.0f%% (전체 스레드 합, 벽시계 대비) │ GC 정지 합계 %.1fms (최대 %.1f, gen0/1/2 = %d/%d/%d)"
                 % (100.0 * cpu / wall, self.gc_ms, self.gc_max, *self.gc_n))
        L.append("  ├ 오버레이      %-8s %5s %8s %8s %9s %10s %10s %7s  %s"
                 % ("이름", "paint", "평균ms", "최대ms", "paint간격", "요청→그림", "최대지연", "눈송이", "창 크기(물리px)"))
        tot_paint = 0.0
        for label, st in overlays:
            k = st.get("n", 0)
            if not k:
                L.append("  │               %-8s %5d   (그려지지 않음)" % (label, 0))
                continue
            tot_paint += st["sum_ms"] / max(1, n)       # 틱 1회당 이 창들이 paint 에 쓴 시간
            L.append("  │               %-8s %5d %8.1f %8.1f %9.1f %10.1f %10.1f %7.0f  %s"
                     % (label, k, st["sum_ms"] / k, st["max_ms"], st["sum_int"] / max(1, st["n_int"]),
                        st["sum_wait"] / k, st["max_wait"], st["flakes"] / k, st.get("size", "?")))
        tk = self.track
        if tk:
            tp = self.tparts
            L.append("  ├ 창 추적       %d회 │ GUI 처리 평균 %.1f / 최대 %.1f ms │ 수집 %.1f │ 표면계산 %.1f │ 시뮬반영 %.1f │ 바닥·전체화면 %.1f"
                     % (len(tk), _avg(tk), max(tk), _avg(tp["창 수집"]), _avg(tp["표면 계산"]), _avg(tp["시뮬 반영"]),
                        _avg(tp["바닥/전체화면"])))
            L.append("  │               표면을 다시 계산한 %d회 중 결과가 그대로라 시뮬 반영을 건너뛴 것 %d회" % (self.track_full, self.track_same))
        if sim is not None:
            hits = sum(st.get("hits", 0) for _l, st in overlays)
            builds = sum(st.get("builds", 0) for _l, st in overlays)
            L.append("  ├ 눈 상태       눈송이 %d │ 눈덩어리 %d │ 눈더미 %d (셀 합계 %d) │ 눈더미 캐시 적중 %d / 재생성 %d"
                     % (len(sim.flakes), len(sim.parcels), len(sim.piles),
                        sum(len(p.cells) for p in sim.piles.values()), hits, builds))
        if extra:
            L.append("  ├ 환경          " + " │ ".join("%s %s" % (k, v) for k, v in extra.items()))
        L.append("  └ 판정          " + self._verdict(busy, tot_paint, cpu / wall, n, g))
        self.reset()
        return "\n".join(L)

    def _verdict(self, busy_ms: float, paint_ms: float, cpu_ratio: float, n: int, g: list) -> str:
        avg = _avg(g)
        if avg <= self.want_ms * 1.15:
            return "정상: 목표 프레임 유지 중"
        known = busy_ms + paint_ms + (_avg(self.track) / 80.0 * avg if self.track else 0.0)
        unknown = avg - known
        tips = []
        if self.gc_ms / max(1, n) > 3.0:
            tips.append("GC 정지가 프레임당 %.1fms (메모리 할당 줄이기 필요)" % (self.gc_ms / max(1, n)))
        if busy_ms > avg * 0.4:
            tips.append("틱 계산이 무거움 (평균 %.1fms)" % busy_ms)
        if paint_ms > avg * 0.4:
            tips.append("paintEvent 가 무거움 (프레임당 %.1fms)" % paint_ms)
        if _avg(self.track) > 8.0:
            tips.append("창 추적 GUI 처리가 무거움 (평균 %.1fms)" % _avg(self.track))
        if unknown > avg * 0.5:
            where = "CPU 는 한가함 → 창 합성/복사(UpdateLayeredWindow·DWM)나 다른 창 대기" if cpu_ratio < 0.5 \
                else "CPU 도 바쁨 → 파이썬 밖(Qt/다른 스레드/오디오)에서 시간을 씀"
            tips.append("측정되지 않은 시간이 평균 %.1fms (%s)" % (unknown, where))
        return "느림: " + (" · ".join(tips) if tips else "뚜렷한 한 곳이 아니라 여러 곳이 조금씩 느림")
