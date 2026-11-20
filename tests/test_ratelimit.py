import unittest

from probe.ratelimit import BudgetExceeded, RateLimiter, TokenBucket


class FakeTime:
    """A clock we control, so the test needs no real waiting."""
    def __init__(self):
        self.t = 0.0

    def clock(self):
        return self.t

    def sleep(self, s):
        self.t += s


class RateTests(unittest.TestCase):
    def test_bucket_spaces_requests(self):
        ft = FakeTime()
        b = TokenBucket(rate=2, burst=1, clock=ft.clock, sleep=ft.sleep)
        for _ in range(5):
            b.acquire()
        self.assertAlmostEqual(ft.t, 2.0, places=6)   # first free, then 4 x 0.5 s

    def test_global_limit_is_respected(self):
        ft = FakeTime()
        rl = RateLimiter(global_qps=5, per_target_qps=100, max_total_queries=1000, clock=ft.clock, sleep=ft.sleep)
        for i in range(50):
            rl.acquire(f"t{i % 7}")
        self.assertLessEqual(rl.peak_qps(), 5)

    def test_per_target_limit_is_respected(self):
        ft = FakeTime()
        rl = RateLimiter(global_qps=1000, per_target_qps=1, max_total_queries=1000, clock=ft.clock, sleep=ft.sleep)
        for _ in range(5):
            rl.acquire("only")
        self.assertGreaterEqual(ft.t, 4.0)            # 5 queries at 1/s need at least 4 s

    def test_budget_stops_the_run(self):
        ft = FakeTime()
        rl = RateLimiter(100, 100, max_total_queries=3, clock=ft.clock, sleep=ft.sleep)
        for _ in range(3):
            rl.acquire("t")
        with self.assertRaises(BudgetExceeded):
            rl.acquire("t")
        self.assertEqual(rl.sent, 3)


if __name__ == "__main__":
    unittest.main()
