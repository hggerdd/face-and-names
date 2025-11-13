import unittest

from src.core.cache import LRUCache


class LRUCacheTests(unittest.TestCase):
    def test_eviction_order(self):
        cache = LRUCache[int, int](maxsize=2)
        cache.set(1, 1)
        cache.set(2, 2)
        self.assertEqual(cache.get(1), 1)
        cache.set(3, 3)
        self.assertIsNone(cache.get(2))
        self.assertEqual(cache.get(1), 1)
        self.assertEqual(cache.get(3), 3)


if __name__ == "__main__":
    unittest.main()
