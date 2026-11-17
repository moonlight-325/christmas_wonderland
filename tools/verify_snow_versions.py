"""v1.9.6 검증: 쌓인 눈 물리가 v1.4.0 과 같고, 내리는 눈이 v1.9.5 Stage 2 와 같은지 두 원본 폴더와 직접 비교한다.

사용: python tools/verify_snow_versions.py --v140 <v1.4.0 의 christmas_wonderland 폴더> --v195 <v1.9.5 stage2 의 christmas_wonderland 폴더>
(PySide6 불필요. 두 원본 폴더는 배포 ZIP 에 들어 있지 않으므로 직접 지정한다.)
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DT = 1 / 30


def load_pkg(name: str, root: Path):
    """root/snow 를 별도 패키지 이름으로 불러온다 (세 버전의 'snow' 가 서로 섞이지 않게)."""
    pkg_dir = root / "snow"
    spec = importlib.util.spec_from_file_location(f"{name}", pkg_dir / "__init__.py", submodule_search_locations=[str(pkg_dir)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return importlib.import_module(f"{name}.physics")


def make(mod, seed, win=(400, 600, 1200), **cfg):
    sim = mod.SnowSim(seed=seed)
    sim.cell = 3
    sim.set_bounds(mod.Rect(0, 0, 1920, 1080))
    base = dict(amount=0, accumulate=50, temperature=-15, wind_strength=0, cursor_on=False, cursor_strength=1.0, cursor_radius=120.0)
    base.update(cfg)
    sim.configure(**base)
    l, t, r = win
    sim.set_surfaces([mod.SurfaceInfo("w", l, t, r, [(l, r)], [(l, r)])])
    return sim


results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(("통과  " if ok else "실패  ") + name + (f"  [{detail}]" if detail else ""))


def falling_snow(new, ref):
    """내리는 눈: 같은 시드/설정이면 눈송이 위치가 v1.9.5 Stage 2 와 완전히 같아야 한다 (표면 없음 = 착지 없음)."""
    cases = {
        "기본": dict(amount=300),
        "바람 60%": dict(amount=300, wind_strength=60, wind_dir=45),
        "눈보라": dict(amount=300, blizzard=0.8, wind_strength=40),
        "돌풍": dict(amount=300, gust_on=True, gust_strength=0.9, gust_interval=6.0, wind_strength=25),
        "낙하 속도/크기": dict(amount=500, speed=1.7, size=1.4, wind_strength=10),
    }
    for label, cfg in cases.items():
        a = make(new, 7, accumulate=0, **cfg)
        b = make(ref, 7, accumulate=0, **cfg)
        a.set_surfaces([]); b.set_surfaces([])
        for _ in range(30 * 20):
            a.step(DT); b.step(DT)
        same = len(a.flakes) == len(b.flakes) and all(
            (x.x, x.y, x.vx, x.vy, x.tier, x.angle) == (y.x, y.y, y.vx, y.vy, y.tier, y.angle) for x, y in zip(a.flakes, b.flakes))
        check(f"내리는 눈 = v1.9.5 Stage 2 ({label}, {len(a.flakes)}개, 20초)", same)


def pile_rules(new, old):
    """relax / 착지 / 용해 / 마우스 밀기: 같은 입력이면 v1.4.0 과 같은 결과가 나와야 한다."""
    rng = random.Random(5)
    # 1) relax: 무작위 눈더미에 같은 규칙 적용
    ok = True
    for trial in range(200):
        n = rng.randint(5, 80)
        cap = rng.choice([4.0, 9.0, 18.0])
        cells = [rng.uniform(0, 30) if rng.random() < 0.3 else rng.uniform(0, 3) for _ in range(n)]
        po, pn = old.Pile(0, 0, n * 3, 3), new.Pile(0, 0, n * 3, 3)
        po.cells, pn.cells = list(cells), list(cells)
        pn.maxh = cap
        so = po.relax(rng.randrange(n), cap)
        # 같은 시작 열
        pn2 = new.Pile(0, 0, n * 3, 3); pn2.cells = list(cells); pn2.maxh = cap
        start = rng.randrange(n)
        po.cells = list(cells); so = po.relax(start, cap)
        sn = pn2.relax(start)
        ok &= po.cells == pn2.cells and so == sn
    check("relax (경사 1.5 / 최대 높이 / 가장자리 낙하) = v1.4.0, 200개 무작위 더미", ok)
    # 2) 용해: 온도별로 같은 결과
    for temp in (-5.0, 0.0, 6.0, 15.0, 30.0):
        so = make(old, 1, temperature=temp)
        sn = make(new, 1, temperature=temp)
        so.piles["w"].cells = [rng.uniform(0, 9) for _ in so.piles["w"].cells]
        sn.piles["w"].cells = list(so.piles["w"].cells)
        before = sum(sn.piles["w"].cells)
        for _ in range(8):
            so._melt(0.25); sn._melt(0.25)
        check(f"용해 = v1.4.0 ({temp:+.0f}℃, 8틱)", so.piles["w"].cells == sn.piles["w"].cells,
              f"녹은 양 {before - sum(sn.piles['w'].cells):.2f}, 장부 {sn.mass_melted:.2f}")
    # 3) 마우스 밀기: 같은 커서 경로면 같은 더미 모양 (공중 눈송이 없음, 넘침 없는 범위)
    for label, path in (("오른쪽 훑기", lambda t: (500 + t * 420, 600 - 6)), ("왼쪽 훑기", lambda t: (1000 - t * 380, 600 - 4)),
                        ("느린 이동", lambda t: (700 + t * 60, 600 - 9))):
        sn = make(new, 3, cursor_on=True)
        # 최대 높이가 서로 달라(2배) 결과가 갈리지 않도록, v1.4.0 쪽 눈 축적량을 올려 최대 높이(cell)를 같게 맞춘다
        so = make(old, 3, cursor_on=True, accumulate=(sn.max_cells - 2.0) / 14.0 * 100.0)
        assert abs(so.max_cells - sn.max_cells) < 1e-9
        h = [4.0 + 3.0 * math.sin(i / 11.0) ** 2 for i in range(len(so.piles["w"].cells))]
        so.piles["w"].cells = list(h); sn.piles["w"].cells = list(h)
        spawn_same = True
        same = True
        frames = 0
        for k in range(int(3 / DT)):
            t = k * DT
            so.set_cursor(path(t), DT); sn.set_cursor(path(t), DT)
            so._cursor_plow(DT); sn._cursor_plow(DT)          # 쟁기 계산만 직접 비교 (날아간 눈송이의 비행은 내리는 눈 쪽 규칙이라 별도)
            if sn.parcels or sn._reservoir:
                break      # 눈이 더미 밖으로 넘친 순간부터는 v1.4.0(눈송이, 눈 소멸)과 v1.9.6(독립 눈 덩어리, 보존)이 의도적으로 다르다
            spawn_same &= len(so.flakes) == len(sn.flakes)
            same &= so.piles["w"].cells == sn.piles["w"].cells
            frames += 1
            so.flakes.clear(); sn.flakes.clear()
        same &= frames >= 20
        check(f"마우스로 쌓인 눈 밀기 = v1.4.0 ({label}, 첫 넘침 전 {frames}프레임, 흩날린 눈송이 수 포함)", same and spawn_same)
    # 4) 눈 쌓임: 같은 눈송이가 같은 열에 내리면 같은 결과
    so = make(old, 2, amount=0); sn = make(new, 2, amount=0)
    ok = True
    for _ in range(3000):
        c = rng.randrange(len(so.piles["w"].cells))
        fo, fn = so._new_flake(False), sn._new_flake(False)
        fo.amount = fn.amount = rng.choice([0.5, 1.0, 2.0, 3.6]); fo.cols = fn.cols = rng.choice([1, 2, 3, 4])
        so._land(so.piles["w"], c, fo); sn._land(sn.piles["w"], c, fn)
    cap_new = sn.max_cells
    # 최대 높이가 서로 다르므로(2배) 최대 높이 미만인 동안만 비교: 낮은 더미 구간
    so2 = make(old, 2); sn2 = make(new, 2)
    ok = True
    for _ in range(400):
        c = rng.randrange(len(so2.piles["w"].cells))
        fo, fn = so2._new_flake(False), sn2._new_flake(False)
        fo.amount = fn.amount = rng.choice([0.5, 1.0, 2.0]); fo.cols = fn.cols = rng.choice([1, 2, 3])
        so2._land(so2.piles["w"], c, fo); sn2._land(sn2.piles["w"], c, fn)
    check("눈 축적(_land) = v1.4.0 (최대 높이에 닿기 전 400회)", so2.piles["w"].cells == sn2.piles["w"].cells)
    # 5) 최대 높이
    for acc in (0, 25, 50, 100):
        so = old.SnowSim(); sn = new.SnowSim()
        so.configure(accumulate=acc); sn.configure(accumulate=acc)
        check(f"최대 높이 = v1.4.0 x 2 (눈 축적량 {acc}: {so.max_cells:.2f} -> {sn.max_cells:.2f} cell)",
              abs(sn.max_cells - 2 * so.max_cells) < 1e-12)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v140", required=True)
    ap.add_argument("--v195", required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(HERE))
    new = load_pkg("snow_new", HERE)
    old = load_pkg("snow_v140", Path(a.v140))
    ref = load_pkg("snow_v195", Path(a.v195))
    falling_snow(new, ref)
    pile_rules(new, old)
    bad = [n for n, ok in results if not ok]
    print(f"\n통과 {len(results) - len(bad)} / 실패 {len(bad)}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
