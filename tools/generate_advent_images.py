"""어드벤트 기본 선물 이미지(96x54 픽셀아트) 생성기.  python tools/generate_advent_images.py
UI 에서는 정수 배(×4)로 최근접 확대해 표시한다. 직접 그린 이미지이므로 저작권 문제가 없다."""
import random
from pathlib import Path

from PIL import Image, ImageDraw

W, H = 96, 54
OUT = Path(__file__).resolve().parent.parent / "assets" / "advent" / "images"
MAP = {1: "snowflake", 2: "star", 3: "tree", 4: "candle", 5: "snowman", 6: "gift", 7: "cabin", 8: "bell",
       9: "stocking", 10: "wreath", 11: "ginger", 12: "candycane", 13: "snowflake", 14: "star", 15: "wreath",
       16: "candle", 17: "snowman", 18: "gift", 19: "cabin", 20: "bell", 21: "star", 22: "stocking", 23: "cabin", 24: "tree"}
SKIES = [((11, 29, 58), (36, 70, 120)), ((38, 24, 70), (120, 66, 130)), ((12, 52, 56), (40, 120, 104)),
         ((20, 30, 66), (80, 110, 170)), ((52, 22, 40), (150, 70, 90)), ((16, 40, 30), (60, 110, 70))]
WHITE, ICE, SNOW2 = (255, 255, 255), (220, 236, 248), (176, 208, 235)
GOLD, GOLD2, RED, RED2 = (243, 201, 74), (184, 134, 42), (214, 58, 58), (143, 31, 42)
GREEN, GREEN2, GREEN3 = (47, 143, 78), (29, 94, 58), (98, 200, 115)
BROWN, BROWN2, CREAM, BLUE = (122, 74, 43), (74, 44, 24), (245, 234, 208), (61, 111, 168)


def sky(d, top, bot, rng):
    bands = 7
    for b in range(bands):
        t = b / (bands - 1)
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        y0, y1 = b * 40 // bands, (b + 1) * 40 // bands
        d.rectangle([0, y0, W, y1], fill=c)
        if b:                                           # 띠 경계 디더링
            for x in range(0, W, 2):
                d.point((x + (b % 2), y0), fill=tuple(int(top[i] + (bot[i] - top[i]) * (b - 1) / (bands - 1)) for i in range(3)))
    for _ in range(26):
        d.point((rng.randrange(W), rng.randrange(0, 30)), fill=rng.choice([WHITE, ICE, GOLD]))


def ground(d, rng):
    d.rectangle([0, 42, W, H], fill=WHITE)
    for x in range(W):
        h = 40 + int(1.6 * ((x * 7) % 5 == 0) + 1.2 * ((x * 3) % 7 == 0))
        d.line([(x, h), (x, 42)], fill=WHITE)
    d.rectangle([0, 47, W, H], fill=ICE)
    for _ in range(30):
        d.point((rng.randrange(W), rng.randrange(44, H)), fill=SNOW2)


def snowfall(d, rng, n=30):
    for _ in range(n):
        d.point((rng.randrange(W), rng.randrange(0, 44)), fill=WHITE)


def tri(d, cx, top, h, hw, c1, c2):
    d.polygon([(cx, top), (cx - hw, top + h), (cx + hw, top + h)], fill=c1)
    d.line([(cx - hw, top + h), (cx + hw, top + h)], fill=c2)


def m_tree(d, rng, cx=48):
    d.rectangle([cx - 2, 38, cx + 2, 44], fill=BROWN)
    for i, (top, h, hw) in enumerate([(22, 12, 11), (14, 13, 9), (6, 12, 7)]):
        tri(d, cx, top, h, hw, GREEN, GREEN2)
    d.polygon([(cx, 1), (cx - 2, 5), (cx + 2, 5)], fill=GOLD)
    d.rectangle([cx - 1, 4, cx + 1, 6], fill=GOLD)
    for x, y, c in [(-4, 16, RED), (3, 20, GOLD), (-6, 29, BLUE), (5, 31, RED), (-1, 36, GOLD), (8, 38, BLUE), (-9, 38, RED)]:
        d.rectangle([cx + x, y, cx + x + 1, y + 1], fill=c)


def m_snowman(d, rng, cx=48):
    for cy, r in [(38, 9), (27, 7), (18, 5)]:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE, outline=SNOW2)
    d.rectangle([cx - 4, 10, cx + 4, 13], fill=(30, 30, 40)); d.rectangle([cx - 6, 13, cx + 6, 13], fill=(30, 30, 40))
    d.point((cx - 2, 17), fill=(20, 20, 30)); d.point((cx + 2, 17), fill=(20, 20, 30))
    d.rectangle([cx, 19, cx + 4, 19], fill=(240, 138, 60))
    d.rectangle([cx - 5, 23, cx + 5, 24], fill=RED); d.rectangle([cx + 3, 24, cx + 5, 29], fill=RED)
    for y in (27, 31, 35): d.point((cx, y), fill=(30, 30, 40))
    d.line([(cx - 8, 26), (cx - 15, 21)], fill=BROWN2); d.line([(cx + 8, 26), (cx + 15, 21)], fill=BROWN2)


def m_star(d, rng, cx=48, cy=24):
    for r, c in [(20, (255, 255, 255, 0)), ]:
        pass
    for r, a in [(18, 1), (14, 2)]:
        for ang in range(0, 360, 30):
            import math
            x = cx + int(r * math.cos(math.radians(ang))); y = cy + int(r * math.sin(math.radians(ang)))
            d.point((x, y), fill=GOLD if a == 2 else (255, 236, 160))
    import math
    pts = []
    for i in range(10):
        r = 12 if i % 2 == 0 else 5
        a = math.radians(-90 + i * 36)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=GOLD, outline=GOLD2)
    d.polygon([(cx, cy - 8), (cx - 2, cy - 2), (cx + 2, cy - 2)], fill=(255, 241, 168))


def m_gift(d, rng, cx=48):
    for gx, gy, w, h, c, c2, rb in [(cx - 22, 30, 16, 12, BLUE, (30, 60, 110), WHITE), (cx - 4, 22, 24, 20, RED, RED2, GOLD), (cx + 15, 33, 12, 9, GREEN, GREEN2, GOLD)]:
        d.rectangle([gx, gy, gx + w, gy + h], fill=c, outline=c2)
        d.rectangle([gx + w // 2 - 1, gy, gx + w // 2 + 1, gy + h], fill=rb)
        d.rectangle([gx, gy + h // 2 - 1, gx + w, gy + h // 2 + 1], fill=rb)
        d.rectangle([gx + w // 2 - 4, gy - 3, gx + w // 2 - 1, gy], fill=rb); d.rectangle([gx + w // 2 + 1, gy - 3, gx + w // 2 + 4, gy], fill=rb)


def m_bell(d, rng, cx=48):
    d.polygon([(cx - 4, 12), (cx + 4, 12), (cx + 12, 36), (cx - 12, 36)], fill=GOLD, outline=GOLD2)
    d.rectangle([cx - 14, 36, cx + 14, 39], fill=GOLD, outline=GOLD2)
    d.ellipse([cx - 3, 38, cx + 3, 44], fill=GOLD2)
    d.line([(cx - 5, 18), (cx - 8, 32)], fill=(255, 241, 168))
    d.rectangle([cx - 3, 6, cx + 3, 12], fill=GOLD2)
    d.polygon([(cx - 12, 4), (cx - 2, 8), (cx - 12, 12)], fill=RED); d.polygon([(cx + 12, 4), (cx + 2, 8), (cx + 12, 12)], fill=RED)
    d.rectangle([cx - 2, 6, cx + 2, 10], fill=RED2)


def m_candle(d, rng, cx=48):
    d.rectangle([cx - 5, 22, cx + 5, 42], fill=CREAM, outline=(201, 184, 142))
    d.line([(cx - 3, 24), (cx - 3, 40)], fill=WHITE)
    for i, y in enumerate((25, 28, 31)):
        d.point((cx + 3, y + i), fill=(201, 184, 142))
    d.line([(cx, 22), (cx, 19)], fill=(40, 30, 30))
    d.polygon([(cx, 8), (cx - 4, 16), (cx, 20), (cx + 4, 16)], fill=(240, 138, 60))
    d.polygon([(cx, 11), (cx - 2, 16), (cx, 19), (cx + 2, 16)], fill=GOLD)
    for ang in range(8):
        d.point((cx + int(10 * (1 if ang % 2 else -1) * (ang / 8 + 0.3)), 10 + ang), fill=(255, 241, 168))
    for sx in (-1, 1):
        d.polygon([(cx + sx * 6, 41), (cx + sx * 16, 37), (cx + sx * 14, 43)], fill=GREEN, outline=GREEN2)
    d.rectangle([cx - 1, 40, cx + 1, 42], fill=RED); d.rectangle([cx + 3, 41, cx + 4, 42], fill=RED)


def m_stocking(d, rng, cx=48):
    d.rectangle([10, 6, 86, 8], fill=BROWN2)
    d.line([(cx, 8), (cx, 11)], fill=GOLD)
    d.rectangle([cx - 8, 11, cx + 8, 18], fill=WHITE, outline=SNOW2)
    d.rectangle([cx - 7, 19, cx + 6, 34], fill=RED, outline=RED2)
    d.polygon([(cx - 7, 30), (cx + 6, 30), (cx + 15, 38), (cx + 15, 43), (cx - 3, 43), (cx - 7, 36)], fill=RED, outline=RED2)
    d.rectangle([cx + 8, 38, cx + 15, 43], fill=WHITE)
    for x, y, c in [(cx - 4, 23, GOLD), (cx + 1, 27, GREEN), (cx - 3, 31, GOLD)]:
        d.rectangle([x, y, x + 1, y + 1], fill=c)
    d.point((cx - 12, 3), fill=GOLD); d.point((cx + 12, 14), fill=WHITE)


def m_cabin(d, rng, cx=48):
    d.rectangle([cx - 18, 26, cx + 18, 42], fill=BROWN, outline=BROWN2)
    for y in range(28, 42, 4): d.line([(cx - 18, y), (cx + 18, y)], fill=BROWN2)
    d.polygon([(cx - 22, 27), (cx, 12), (cx + 22, 27)], fill=(90, 50, 30), outline=BROWN2)
    d.polygon([(cx - 22, 27), (cx, 12), (cx + 22, 27), (cx + 18, 27), (cx, 15), (cx - 18, 27)], fill=WHITE)
    d.rectangle([cx + 9, 8, cx + 13, 18], fill=(140, 70, 60)); d.rectangle([cx + 8, 7, cx + 14, 8], fill=WHITE)
    d.rectangle([cx - 12, 31, cx - 5, 37], fill=GOLD, outline=BROWN2); d.line([(cx - 8, 31), (cx - 8, 37)], fill=BROWN2)
    d.rectangle([cx + 3, 32, cx + 10, 42], fill=BROWN2)
    d.point((cx + 8, 38), fill=GOLD)
    for y, x in [(5, cx + 12), (2, cx + 15), (0, cx + 18)]:
        d.rectangle([x, y, x + 2, y + 1], fill=(220, 230, 240))
    for x in (cx - 30, cx + 28):
        tri(d, x, 20, 12, 5, GREEN, GREEN2); tri(d, x, 28, 12, 7, GREEN, GREEN2); d.rectangle([x - 1, 40, x + 1, 42], fill=BROWN)


def m_wreath(d, rng, cx=48, cy=26):
    d.ellipse([cx - 19, cy - 19, cx + 19, cy + 19], fill=GREEN2)
    d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=SKIES[0][1])
    d.ellipse([cx - 19, cy - 19, cx + 19, cy + 19], outline=GREEN)
    import math
    for i in range(24):
        a = math.radians(i * 15)
        x, y = cx + 15.5 * math.cos(a), cy + 15.5 * math.sin(a)
        d.rectangle([x - 2, y - 1, x + 1, y + 1], fill=GREEN if i % 2 else GREEN3)
    for i in (1, 4, 8, 11, 15, 19):
        a = math.radians(i * 15 + 7)
        d.rectangle([cx + 15 * math.cos(a) - 1, cy + 15 * math.sin(a) - 1, cx + 15 * math.cos(a), cy + 15 * math.sin(a)], fill=RED)
    d.polygon([(cx, cy + 17), (cx - 9, cy + 13), (cx - 9, cy + 23)], fill=RED); d.polygon([(cx, cy + 17), (cx + 9, cy + 13), (cx + 9, cy + 23)], fill=RED)
    d.rectangle([cx - 2, cy + 15, cx + 2, cy + 19], fill=RED2)


def m_ginger(d, rng, cx=48):
    c = (196, 120, 60)
    d.ellipse([cx - 7, 8, cx + 7, 22], fill=c, outline=BROWN)
    d.rectangle([cx - 9, 22, cx + 9, 34], fill=c, outline=BROWN)
    d.rectangle([cx - 20, 22, cx - 9, 27], fill=c, outline=BROWN); d.rectangle([cx + 9, 22, cx + 20, 27], fill=c, outline=BROWN)
    d.rectangle([cx - 9, 34, cx - 2, 43], fill=c, outline=BROWN); d.rectangle([cx + 2, 34, cx + 9, 43], fill=c, outline=BROWN)
    d.point((cx - 3, 13), fill=BROWN2); d.point((cx + 3, 13), fill=BROWN2); d.line([(cx - 3, 17), (cx + 3, 17)], fill=WHITE)
    for y, col in ((25, RED), (29, GREEN), (33, RED)): d.rectangle([cx - 1, y, cx, y + 1], fill=col)
    d.line([(cx - 19, 24), (cx - 11, 24)], fill=WHITE); d.line([(cx + 11, 24), (cx + 19, 24)], fill=WHITE)
    d.line([(cx - 8, 41), (cx - 3, 41)], fill=WHITE); d.line([(cx + 3, 41), (cx + 8, 41)], fill=WHITE)


def m_candycane(d, rng, cx=48):
    mask = Image.new("L", (W, H), 0); m = ImageDraw.Draw(mask)
    m.rectangle([cx - 14, 20, cx - 8, 44], fill=255)
    m.pieslice([cx - 14, 6, cx + 14, 34], 180, 360, fill=255); m.pieslice([cx - 8, 12, cx + 8, 28], 180, 360, fill=0)
    m.rectangle([cx + 8, 20, cx + 14, 24], fill=255)
    px = mask.load()
    img = CUR[0]
    for y in range(H):
        for x in range(W):
            if px[x, y]:
                img.putpixel((x, y), RED if ((x + y) // 4) % 2 == 0 else WHITE)
    for y in range(H):
        for x in range(W):
            if px[x, y] and (not px[x - 1, y] or not px[x + 1, y] or not px[x, y - 1] or not px[x, y + 1]):
                img.putpixel((x, y), RED2)
    for x, y in [(cx + 20, 14), (cx + 24, 22), (cx - 28, 20)]: d.point((x, y), fill=GOLD)


def m_snowflake(d, rng, cx=48, cy=24):
    import math
    for k in range(6):
        a = math.radians(k * 60 - 90)
        ex, ey = cx + 18 * math.cos(a), cy + 18 * math.sin(a)
        d.line([(cx, cy), (ex, ey)], fill=WHITE)
        for t in (0.45, 0.7):
            bx, by = cx + 18 * t * math.cos(a), cy + 18 * t * math.sin(a)
            for s in (-1, 1):
                b = a + s * math.radians(55)
                d.line([(bx, by), (bx + 6 * math.cos(b), by + 6 * math.sin(b))], fill=ICE)
        d.rectangle([ex - 1, ey - 1, ex, ey], fill=(143, 208, 245))
    d.rectangle([cx - 1, cy - 1, cx + 1, cy + 1], fill=(143, 208, 245))


CUR = [None]
MOTIFS = {k[2:]: v for k, v in globals().items() if k.startswith("m_")}


def make(day: int) -> Image.Image:
    rng = random.Random(day * 977)
    top, bot = SKIES[(day - 1) % len(SKIES)]
    img = Image.new("RGB", (W, H), top)
    d = ImageDraw.Draw(img)
    CUR[0] = img
    sky(d, top, bot, rng)
    ground(d, rng)
    MOTIFS[MAP[day]](d, rng)
    snowfall(d, rng, 22)
    d.rectangle([0, 0, W - 1, H - 1], outline=(245, 234, 208))      # 1px 액자
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for day in range(1, 25):
        make(day).save(OUT / f"day{day:02d}.png")
    print("saved 24 images ->", OUT)
