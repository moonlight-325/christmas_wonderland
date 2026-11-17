"""픽셀 스프라이트(문자 격자). 외부 이미지 파일 없이 코드에서 직접 생성하며, 확대는 항상 최근접(Nearest) 방식이다."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap

PALETTE = {
    "W": "#ffffff", "w": "#dcecf8", "B": "#8fd0f5", "b": "#3d6fa8",
    "G": "#2f8f4e", "g": "#1d5e3a", "L": "#62c873", "D": "#0f3b2e",
    "R": "#d63a3a", "r": "#8f1f2a", "Y": "#f3c94a", "y": "#b8862a",
    "C": "#f5ead0", "c": "#c9b88e", "K": "#7a4a2b", "k": "#4a2c18",
    "O": "#f08a3c", "P": "#c767d6", "S": "#0b241d",
}

# 단색 아이콘: '#' 가 주색(기본 크림), '+' 가 보조색
ICONS = {
    "snow": ["W..W..W", ".W.W.W.", "..WWW..", "WWWWWWW", "..WWW..", ".W.W.W.", "W..W..W"],
    "sparkle": ["..Y..", "..Y..", "YYWYY", "..Y..", "..Y.."],
    "star": ["...Y...", "..YYY..", "YYYWYYY", ".YYYYY.", "..YYY..", ".YY.YY.", ".Y...Y."],
    "star_mono": ["...#...", "..###..", "#######", ".#####.", "..###..", ".##.##.", ".#...#."],   # 선택된 탭용: 주색 단색
    "note": ["....#####", "....#...#", "....#...#", "....#...#", "....#...#",
             "..###.###", ".####.###", "..##..##."],
    "gear": ["....#....", ".#.###.#.", "..#####..", ".###.###.", "####.####",
             ".###.###.", "..#####..", ".#.###.#.", "....#...."],
    "clock": ["..#####..", ".#..#..#.", "#...#...#", "#...#...#", "#...###.#",
              "#.......#", ".#.....#.", "..#####.."],
    "calendar": [".#.....#.", "#########", "#.......#", "#.#.#.#.#", "#.......#",
                 "#.#.#.#.#", "#.......#", "#########"],
    "globe": ["..#####..", ".#.....#.", "#.#...#.#", "#...#...#", "#.#...#.#",
              ".#.....#.", "..#####..", ".#######.", ".#######."],
    "lock": ["..#####..", ".#.....#.", ".#.....#.", "#########", "#########",
             "####.####", "####.####", "#########"],
    "wind": ["..#####..", ".......#.", "#######.#", "........#", ".#########",
             ".........", "..####..."],
    "save": ["#######..", "#.....##.", "#.....###", "#########", "#.......#",
             "#.#####.#", "#.......#", "#########"],
    "folder": ["###......", "#.#######", "#.......#", "#.......#", "#.......#",
               "#.......#", "#########"],
    "trash": ["...###...", "#########", ".#.....#.", ".#.#.#.#.", ".#.#.#.#.",
              ".#.#.#.#.", ".#######."],
    "reset": ["..####...", ".#....#..", "#......#.", "#....####", "#.....##.",
              ".#.....#.", "..####..."],
    "speaker": ["....#....", "...##..#.", "#####...#", "#####.#.#", "#####...#",
                "...##..#.", "....#...."],
    "play": ["..#......", "..##.....", "..###....", "..####...", "..#####..",
             "..####...", "..###....", "..##.....", "..#......"],
    "pause": ["..##.##..", "..##.##..", "..##.##..", "..##.##..", "..##.##..",
              "..##.##..", "..##.##..", "..##.##..", "..##.##.."],
    "next": ["#.....#..", "##....##.", "###...###", "####..###", "#####.###",
             "####..###", "###...###", "##....##.", "#.....#.."],
    "prev": ["..#.....#", ".##....##", "###...###", "###..####", "###.#####",
             "###..####", "###...###", ".##....##", "..#.....#"],
    "close": ["#.......#", ".#.....#.", "..#...#..", "...#.#...", "....#....",
              "...#.#...", "..#...#..", ".#.....#.", "#.......#"],
    "minus": [".........", ".........", ".........", ".........", ".#######.",
              ".#######.", ".........", ".........", "........."],
    "menu": [".........", ".#######.", ".........", ".#######.", ".........", ".#######.", "........."],
    "box": ["#########", "#.......#", "#.......#", "#.......#", "#.......#",
            "#.......#", "#.......#", "#.......#", "#########"],
    "gift": ["..Y.Y....", ".Y.Y.Y...", "..YYY....", "#########", "#...#...#", "#...#...#",
             "#########", "#...#...#", "#########"],
    "bell": ["....#....", "...###...", "..#####..", "..#####..", ".#######.", ".#######.",
             "#########", "....+....", "........."],
    "candy": ["...####..", "..#.#.##.", ".#.#.#.#.", ".#..#..#.", "..#..#.#.", "...####.."],
    "repeat": ["..#####..", ".#....##.", "#......#.", "..#....#.", ".#....#..", "..#####.."],
    "grip": ["......#..", ".....#...", "....#..#.", "...#..#..", "..#..#..#"],
}

# 체크 표시 글리프(7x5) - PixelCheck 가 11x11 칸 안쪽(9x9)의 정중앙에 그린다.
CHECK_GLYPH = [".....##",
               "#...##.",
               "##.##..",
               ".###...",
               "..#...."]
_CHECK_SMALL = ["....Y",
                "...YY",
                "Y.YY.",
                ".YY..",
                "..Y.."]


def _boxed(glyph: list[str], n: int) -> list[str]:
    """n x n 테두리 상자 안 정중앙에 글리프를 배치한 스프라이트 격자."""
    rows = [["."] * n for _ in range(n)]
    for i in range(n):
        rows[0][i] = rows[n - 1][i] = rows[i][0] = rows[i][n - 1] = "#"
    gh, gw = len(glyph), len(glyph[0])
    oy, ox = (n - gh) // 2, (n - gw) // 2
    for y, line in enumerate(glyph):
        for x, ch in enumerate(line):
            if ch != ".":
                rows[oy + y][ox + x] = ch
    return ["".join(r) for r in rows]


ICONS["check"] = _boxed(_CHECK_SMALL, 9)      # 메뉴용 체크 아이콘 (체크가 박스 안 정중앙)

SPRITES = {
    "gift_red": [
        "..YYY.YYY..",
        ".Y...Y...Y.",
        ".Y..YYY..Y.",
        "..YYYYYYY..",
        "RRRRRYRRRRR",
        "RRRRRYRRRRR",
        "YYYYYYYYYYY",
        "RRRRRYRRRRR",
        "RRRRRYRRRRR",
        "rrrrrYrrrrr",
        "rrrrrYrrrrr",
    ],
    "gift_blue": [
        "..WWW.WWW..",
        ".W...W...W.",
        ".W..WWW..W.",
        "..WWWWWWW..",
        "bbbbbWbbbbb",
        "bbbbbWbbbbb",
        "WWWWWWWWWWW",
        "bbbbbWbbbbb",
        "bbbbbWbbbbb",
        "SSSSSWSSSSS",
        "SSSSSWSSSSS",
    ],
}


def _tree() -> list[str]:
    """대칭 크리스마스 트리 (17 x 21) 를 절차적으로 생성."""
    W = 17
    rows = []

    def row(w, ch="G"):
        pad = (W - w) // 2
        r = ["."] * W
        for i in range(w):
            r[pad + i] = ch
        r[pad] = "g"
        r[pad + w - 1] = "g"
        return r

    rows.append(list("........Y........"))
    rows.append(list("......YYYYY......"))
    rows.append(list("........Y........"))
    tiers = [(3, 9), (5, 13), (7, 17)]
    for top, bot in tiers:
        h = (bot - top) // 2 + 1
        for i in range(h):
            w = top + 2 * i
            r = row(w)
            for k in range(1, w - 1, 3):          # 밝은 가지
                r[(W - w) // 2 + k] = "L" if (i + k) % 2 == 0 else "G"
            rows.append(r)
    orn = {(5, 7): "R", (6, 10): "Y", (8, 5): "B", (9, 9): "R", (10, 12): "Y",
           (11, 4): "Y", (12, 8): "B", (13, 11): "R", (14, 6): "R", (14, 13): "B"}
    for (y, x), ch in orn.items():
        if y < len(rows) and rows[y][x] in "GL":
            rows[y][x] = ch
    for _ in range(3):
        r = ["."] * W
        for i in range(7, 10):
            r[i] = "K" if i != 7 else "k"
        rows.append(r)
    return ["".join(r) for r in rows]


SPRITES["tree"] = _tree()

_CACHE: dict = {}


def _color(ch: str) -> QColor:
    return QColor(PALETTE[ch])


def sprite_image(name: str, main: str | None = None, accent: str | None = None) -> QImage:
    """스프라이트 -> QImage(1배). 아이콘이면 '#'/'+' 를 main/accent 색으로 치환한다."""
    key = (name, main, accent)
    img = _CACHE.get(key)
    if img is not None:
        return img
    grid = SPRITES.get(name) or ICONS[name]
    h, w = len(grid), max(len(r) for r in grid)
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(0)
    mc = QColor(main or "#f5ead0")
    ac = QColor(accent or main or "#f3c94a")
    for y, line in enumerate(grid):
        for x, ch in enumerate(line):
            if ch == ".":
                continue
            if ch == "#":
                img.setPixelColor(x, y, mc)
            elif ch == "+":
                img.setPixelColor(x, y, ac)
            else:
                img.setPixelColor(x, y, _color(ch))
    _CACHE[key] = img
    return img


def sprite_pixmap(name: str, scale: int = 1, main: str | None = None, accent: str | None = None) -> QPixmap:
    img = sprite_image(name, main, accent)
    if scale != 1:
        img = img.scaled(img.width() * scale, img.height() * scale,
                         Qt.IgnoreAspectRatio, Qt.FastTransformation)       # 최근접
    return QPixmap.fromImage(img)


def sprite_icon(name: str, scale: int = 2, main: str | None = None) -> QIcon:
    return QIcon(sprite_pixmap(name, scale, main))
