"""영어 번역표(assets/lang/en.json)와 어드벤트 영어 콘텐츠 점검: 누락, 자리표시자 불일치, 한글 잔존. Qt 없이 돈다."""
import ast
import functools
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import i18n

HANGUL = re.compile("[가-힣]")
PLACEHOLDER = re.compile(r"\{\d+[^}]*\}")
SKIP_DIRS = {"tests", "tools", "__pycache__"}
# 번역표 키가 코드에 tr("...") 로 직접 나오지 않는 것: 기본 날씨 프리셋 이름(화면 표시 때 tr 로 변환)
EXTRA_KEYS = {"잔잔한 겨울", "포근한 눈 내리는 날", "폭설", "강한 눈보라", "변화무쌍한 겨울"}


@functools.lru_cache(maxsize=1)
def source_keys() -> frozenset:
    keys = set()
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT).parts
        if rel[0] in SKIP_DIRS or p.name == "i18n.py":
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and getattr(n.func, "id", None) == "tr" and n.args
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
                    and HANGUL.search(n.args[0].value)):
                k = n.args[0].value
                if len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
                    k = f"{n.args[1].value}|{k}"
                keys.add(k)
    return frozenset(keys)


@functools.lru_cache(maxsize=1)
def log_keys() -> frozenset:
    """core/logger 가 로그 메시지를 tr() 로 번역하므로, log.<level>("...") 의 첫 인자도 번역표를 쓰는 항목이다."""
    levels = {"debug", "info", "warning", "error", "exception", "critical"}
    keys = set()
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT).parts
        if rel[0] in SKIP_DIRS or p.name == "i18n.py":
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in levels
                    and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
                    and HANGUL.search(n.args[0].value)):
                keys.add(n.args[0].value)
    return frozenset(keys)


EN = json.loads((ROOT / "assets" / "lang" / "en.json").read_text(encoding="utf-8"))


class EnglishTable(unittest.TestCase):
    def test_every_source_text_is_translated(self):
        missing = sorted(k for k in source_keys() if k not in EN)
        self.assertEqual(missing, [], f"번역 누락 {len(missing)}건")

    def test_extra_keys_present(self):
        self.assertFalse([k for k in EXTRA_KEYS if k not in EN])

    def test_no_unused_entries(self):
        unused = sorted(k for k in EN if k not in source_keys() and k not in log_keys() and k not in EXTRA_KEYS)
        self.assertEqual(unused, [], "코드에서 쓰지 않는 번역 항목")

    def test_placeholders_match(self):
        bad = [k for k, v in EN.items() if sorted(PLACEHOLDER.findall(k.split("|", 1)[-1])) != sorted(PLACEHOLDER.findall(v))]
        self.assertEqual(bad, [])

    def test_no_hangul_left_in_english(self):
        left = [k for k, v in EN.items() if HANGUL.search(v)]
        self.assertEqual(left, [])

    def test_runtime_lookup(self):
        try:
            i18n.set_language("en")
            self.assertEqual(i18n.tr("눈 효과"), "Snow effects")
            self.assertEqual(i18n.tr("눈", "eyes"), "Eyes")
            self.assertEqual(i18n.tr("눈"), "Snow")
            self.assertEqual(i18n.tr("{0}분 {1:02d}초").format(3, 5), "3m 05s")
        finally:
            i18n.set_language("ko")


class AdventEnglish(unittest.TestCase):
    def setUp(self):
        base = ROOT / "assets" / "advent"
        self.ko = json.loads((base / "contents.default.json").read_text(encoding="utf-8"))
        self.en = json.loads((base / "contents.default.en.json").read_text(encoding="utf-8"))

    def test_same_shape(self):
        self.assertEqual(len(self.ko["days"]), len(self.en["days"]))
        for a, b in zip(self.ko["days"], self.en["days"]):
            self.assertEqual(a["day"], b["day"])
            self.assertEqual(a["image"], b["image"])
            self.assertEqual(a["animation"], b["animation"])
            ea, eb = a.get("event") or {}, b.get("event") or {}
            self.assertEqual(ea.get("type"), eb.get("type"))
            if ea.get("type") == "quiz":
                self.assertEqual(ea["answer"], eb["answer"])
                self.assertEqual(len(ea["choices"]), len(eb["choices"]))
            if ea.get("type") == "catch":
                self.assertEqual((ea["item"], ea["target"], ea["seconds"]), (eb["item"], eb["target"], eb["seconds"]))

    def test_no_hangul(self):
        text = json.dumps({k: v for k, v in self.en.items() if k != "_comment"}, ensure_ascii=False)
        self.assertFalse(HANGUL.search(text))

    def test_parses_without_warnings(self):
        from advent import content
        cs = content.load_file(ROOT / "assets" / "advent" / "contents.default.en.json")
        self.assertIsNotNone(cs)
        self.assertEqual(cs.warnings, [])
        self.assertEqual(len(cs.gifts), 24)


if __name__ == "__main__":
    unittest.main()
