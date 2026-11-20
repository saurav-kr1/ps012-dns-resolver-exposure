"""Whole-tool test against the pretend servers (no Docker needed)."""
import os
import tempfile
import unittest

from probe.config import Config, RateConfig, Target, ConfigError, load_config, load_targets
from probe.evaluate import evaluate
from probe.ratelimit import RateLimiter
from probe.report import write_reports
from probe.runner import run_assessment
from tests.fake_lab import FakeServer

SPECS = [  # id, behaviour, own_zone, expected
    ("f01", "open", None, "recursive"),
    ("f02", "refused", None, "refused"),
    ("f03", "auth", "example-lab.test", "authoritative-only"),
    ("f04", "silent", None, "inconclusive"),
    ("f05", "servfail", None, "inconclusive"),
    ("f06", "flaky", None, "recursive"),
]


def fast_cfg():
    rate = RateConfig(global_qps=500, per_target_qps=500, max_concurrency=4, timeout_s=0.4,
                      retries=1, backoff_s=0.02, attempts_per_probe=3, max_total_queries=500)
    return Config(rate=rate)


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.servers = []
        self.targets = []
        for sid, beh, zone, exp in SPECS:
            s = FakeServer(beh, zone)
            s.start()
            self.servers.append(s)
            self.targets.append(Target(id=sid, ip="127.0.0.1", port=s.port, own_zone=zone, expected=exp, name=beh))

    def tearDown(self):
        for s in self.servers:
            s.stop()

    def test_all_six_targets_are_classified_correctly(self):
        outcomes, limiter = run_assessment(fast_cfg(), self.targets, log=lambda m: None)
        rows = [{"id": o.target.id, "expected": o.target.expected, "label": o.label} for o in outcomes]
        ev = evaluate(rows)
        self.assertEqual(ev["accuracy"], 1.0, ev["mismatches"])

    def test_reports_are_written(self):
        outcomes, limiter = run_assessment(fast_cfg(), self.targets, log=lambda m: None)
        with tempfile.TemporaryDirectory() as d:
            meta = {"run_id": "t", "timestamp": "now", "config_fingerprint": "x"}
            write_reports(d, fast_cfg(), outcomes, limiter, meta)
            for name in ("results.json", "results.csv", "report.md"):
                self.assertTrue(os.path.exists(os.path.join(d, name)), name)

    def test_budget_exhaustion_is_reported_not_crashed(self):
        cfg = fast_cfg()
        cfg.rate.max_total_queries = 5
        limiter = RateLimiter(500, 500, 5)
        outcomes, limiter = run_assessment(cfg, self.targets, limiter=limiter, log=lambda m: None)
        self.assertLessEqual(limiter.sent, 5)
        self.assertTrue(any(o.reason == "budget_exhausted" for o in outcomes))


class SafetyRules(unittest.TestCase):
    def _write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_more_than_20_targets_refused(self):
        body = "targets:\n" + "".join(f"  - {{id: t{i}, ip: 10.0.0.{i + 1}}}\n" for i in range(21))
        with self.assertRaises(ConfigError):
            load_targets(self._write(body), Config())

    def test_public_ip_refused(self):
        with self.assertRaises(ConfigError):
            load_targets(self._write("targets:\n  - {id: a, ip: 8.8.8.8}\n"), Config())

    def test_bad_expected_label_refused(self):
        with self.assertRaises(ConfigError):
            load_targets(self._write("targets:\n  - {id: a, ip: 10.0.0.1, expected: banana}\n"), Config())

    def test_duplicate_ids_refused(self):
        body = "targets:\n  - {id: a, ip: 10.0.0.1}\n  - {id: a, ip: 10.0.0.2}\n"
        with self.assertRaises(ConfigError):
            load_targets(self._write(body), Config())


if __name__ == "__main__":
    unittest.main()
