import unittest

from config import HISTORY_KEEP_DAYS, TENORS


class TenorConfigTest(unittest.TestCase):
    def test_includes_9m_tenor_without_extending_retention(self):
        self.assertIn({"label": "9M", "days": 270}, TENORS)
        self.assertEqual(HISTORY_KEEP_DAYS, 180)


if __name__ == "__main__":
    unittest.main()
