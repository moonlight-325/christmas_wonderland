"""v2.0.0 snow-globe layering, shake strength, and saved-position settings."""
import unittest

from snowglobe import model as M
from snowglobe.physics import GlobePhysics


class SnowGlobeV200FeatureTests(unittest.TestCase):
    def test_position_lock_and_shake_strength_have_safe_defaults(self):
        globe = M.clean_globe(M.new_globe(with_demo=False))
        self.assertFalse(globe["position_locked"])
        self.assertEqual(globe["shake_strength"], 1.0)

    def test_position_lock_and_shake_strength_survive_cleaning(self):
        globe = M.clean_globe({**M.new_globe(with_demo=False),
                               "position_locked": True, "shake_strength": 1.75})
        self.assertTrue(globe["position_locked"])
        self.assertEqual(globe["shake_strength"], 1.75)

    def test_shake_strength_is_clamped(self):
        globe = M.clean_globe({**M.new_globe(with_demo=False), "shake_strength": 99})
        self.assertEqual(globe["shake_strength"], 2.0)

    def test_higher_shake_strength_increases_air_response(self):
        a = GlobePhysics({**M.DEFAULT_SNOW, "amount": 0}, [])
        b = GlobePhysics({**M.DEFAULT_SNOW, "amount": 0}, [])
        a.shake_strength = 1.0
        b.shake_strength = 2.0
        a.step(1 / 30, 100.0, 0.0)
        b.step(1 / 30, 100.0, 0.0)
        self.assertGreater(abs(b.air_x), abs(a.air_x))


if __name__ == "__main__":
    unittest.main()
