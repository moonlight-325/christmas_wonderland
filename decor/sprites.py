"""장식용 픽셀 스프라이트 (문자 격자). widget.sprites 의 SPRITES / ICONS 에 등록해 기존 스프라이트 시스템을 그대로 쓴다."""
from __future__ import annotations
from core.i18n import tr


from widget.sprites import ICONS, SPRITES


def _pad(rows: list[str]) -> list[str]:
    w = max(len(r) for r in rows)
    return [r.ljust(w, ".") for r in rows]


def _star() -> list[str]:
    return _pad([
        "......Y......",
        ".....YWY.....",
        ".....YYY.....",
        "....YYYYY....",
        "YYYYYYWYYYYYY",
        ".YYYYYYYYYYY.",
        "..YYYYYYYYY..",
        "...YYYYYYY...",
        "...YYYYYYy...",
        "..YYYYYYyyy..",
        "..YYYy.yYYY..",
        ".YYY.....YYy.",
        ".YY.......yy.",
    ])


def _snowman() -> list[str]:
    return _pad([
        "....kkkkk....",
        "....kkRkk....",
        "..kkkkkkkkk..",
        "...WWWWWWw...",
        "..WWSWWWSWw..",
        "..WWWWOOOOO..",
        "..WWSWSWSWw..",
        "...WWWWWWw...",
        "..RRRRRRRRR..",
        "...RRWWWwRr..",
        "..WWWWWWWWw..",
        ".WWWWWWWWWWw.",
        ".WWWWSWWWWWw.",
        ".WWWWWWWWWWw.",
        ".WWWWSWWWWWw.",
        ".WWWWWWWWWWw.",
        "WWWWWWWWWWWWw",
        "WWWWWWSWWWWWw",
        "WWWWWWWWWWWWw",
        ".WWWWWWWWWWw.",
        "..wwwwwwwww..",
    ])


def _wreath() -> list[str]:
    n = 17
    c = (n - 1) / 2
    rows = [["."] * n for _ in range(n)]
    greens = "GLGgLG"
    for y in range(n):
        for x in range(n):
            d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5
            if 4.6 <= d <= 8.2:
                rows[y][x] = greens[(x * 3 + y * 5) % len(greens)]
    for (x, y) in ((3, 4), (13, 5), (2, 10), (14, 11), (5, 14), (11, 14), (8, 1), (6, 2)):
        if rows[y][x] != ".":
            rows[y][x] = "R"
    # 아래쪽 빨간 리본
    bow = ["R...R", "RR.RR", ".RRR.", "R.R.R", "R...R"]
    for dy, line in enumerate(bow):
        for dx, ch in enumerate(line):
            if ch != ".":
                rows[11 + dy][6 + dx] = ch if dy != 2 else "r"
    rows[13][8] = "Y"
    return ["".join(r) for r in rows]


def _candy() -> list[str]:
    mask = [
        "..####..",
        ".######.",
        "###..###",
        "##....##",
        "##....##",
        "##......",
        "##......",
        "##......",
        "##......",
        "##......",
        "##......",
        "##......",
        "##......",
    ]
    out = []
    for y, line in enumerate(mask):
        out.append("".join(("R" if ((x + y) // 2) % 2 == 0 else "W") if ch == "#" else "."
                           for x, ch in enumerate(line)))
    return out


def _bell() -> list[str]:
    return _pad([
        ".....RRR.....",
        "....RR.RR....",
        ".....yyy.....",
        "....yYYYy....",
        "...yYYWYYy...",
        "..yYYWYYYYy..",
        "..yYWYYYYYy..",
        "..yYYYYYYYy..",
        ".yYYYYYYYYYy.",
        ".yYYYYYYYYYy.",
        "yYYYYYYYYYYYy",
        "yyyyyyyyyyyyy",
        ".....yYy.....",
        "......y......",
    ])


def _stocking() -> list[str]:
    return _pad([
        ".WWWWWWWWW..",
        "wWWWWWWWWw..",
        ".RRRRRRRR...",
        ".RRRRRRRR...",
        ".RRRRRRRR...",
        ".RRRRRRRR...",
        ".RRRRRRRR...",
        ".RRRRRRRR...",
        ".RRRRRRRRRR.",
        "RRRRRRRRRRRR",
        "RRRRRRRRRRRR",
        "RRRRRRRRRRRr",
        ".rrrrrrrrrr.",
    ])


SPRITES["star_big"] = _star()
SPRITES["snowman"] = _snowman()
SPRITES["wreath"] = _wreath()
SPRITES["candy_cane"] = _candy()
SPRITES["bell_gold"] = _bell()
SPRITES["stocking"] = _stocking()

ICONS["bulb"] = ["..###..", ".#####.", "#######", "#######", ".#####.", "..###..", "...+...", "..+++.."]
ICONS["thermo"] = ["..###..", "..#.#..", "..#.#..", "..#+#..", "..#+#..", ".#####.", "###+###", ".#####."]
ICONS["tree_small"] = ["...#...", "..###..", ".#####.", "..###..", ".#####.", "#######", "...+...", "...+..."]

# (키, 표시 이름, 스프라이트 이름)
DECOR_KINDS = [
    ("tree", tr("트리"), "tree"),
    ("star", tr("별"), "star_big"),
    ("gift_red", tr("빨간 선물"), "gift_red"),
    ("gift_blue", tr("파란 선물"), "gift_blue"),
    ("snowman", tr("눈사람"), "snowman"),
    ("wreath", tr("리스"), "wreath"),
    ("candy", tr("지팡이 사탕"), "candy_cane"),
    ("bell", tr("종"), "bell_gold"),
    ("stocking", tr("양말"), "stocking"),
]
KIND_SPRITE = {k: s for k, _n, s in DECOR_KINDS}
KIND_NAME = {k: n for k, n, _s in DECOR_KINDS}
