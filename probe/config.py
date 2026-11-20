"""Load and validate the two YAML files: the probe settings and the target list.

The target list doubles as the ALLOWLIST: the tool only ever talks to servers
written in it, and refuses to start if the list breaks a safety rule.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
from dataclasses import dataclass, field, asdict
from typing import Optional

import yaml

# The four categories every target is sorted into.
RECURSIVE = "recursive"
AUTH_ONLY = "authoritative-only"
REFUSED = "refused"
INCONCLUSIVE = "inconclusive"
LABELS = (RECURSIVE, AUTH_ONLY, REFUSED, INCONCLUSIVE)


class ConfigError(Exception):
    """Raised when the config or the target list breaks a rule."""


@dataclass
class RateConfig:
    global_qps: float = 5.0          # max queries per second, all targets together
    per_target_qps: float = 1.0      # max queries per second to any single target
    max_concurrency: int = 4         # how many targets are tested at the same time
    timeout_s: float = 2.0           # how long to wait for one reply
    retries: int = 1                 # extra tries after a timeout
    backoff_s: float = 0.5           # pause before a retry
    attempts_per_probe: int = 3      # repeat each test this many times (majority vote)
    max_total_queries: int = 500     # hard stop: never send more than this in a run


@dataclass
class Config:
    zone: str = "probe.lab.test"             # probes ask for <random>.<zone>
    expected_txt: str = "aiori-probe-ok"     # what the test zone answers with
    testzone_log: Optional[str] = None       # path to the test-zone query log, or None
    rate: RateConfig = field(default_factory=RateConfig)
    max_targets: int = 20
    require_private_ips: bool = True         # refuse any target that is a public IP

    def fingerprint(self) -> str:
        """Short hash of the settings, written into reports (reproducibility)."""
        blob = json.dumps(asdict(self), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:12]


@dataclass
class Target:
    id: str
    ip: str                                  # address the probe client sends to
    port: int = 53
    lab_ip: Optional[str] = None             # address the test zone sees when this target recurses
    own_zone: Optional[str] = None           # a zone this target should be authoritative for
    expected: Optional[str] = None           # ground truth label
    name: str = ""
    description: str = ""


def _positive(value, name):
    if not isinstance(value, (int, float)) or value <= 0:
        raise ConfigError(f"{name} must be a positive number, got {value!r}")


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    rate_raw = raw.get("rate_control", {}) or {}
    safety = raw.get("safety", {}) or {}
    rate = RateConfig(**{k: v for k, v in rate_raw.items() if k in RateConfig.__dataclass_fields__})
    for name in ("global_qps", "per_target_qps", "timeout_s", "max_total_queries", "attempts_per_probe", "max_concurrency"):
        _positive(getattr(rate, name), name)
    if rate.retries < 0 or rate.backoff_s < 0:
        raise ConfigError("retries and backoff_s cannot be negative")
    cfg = Config(
        zone=raw.get("zone", "probe.lab.test").strip(".").lower(),
        expected_txt=raw.get("expected_txt", "aiori-probe-ok"),
        testzone_log=raw.get("testzone_log"),
        rate=rate,
        max_targets=int(safety.get("max_targets", 20)),
        require_private_ips=bool(safety.get("require_private_ips", True)),
    )
    if cfg.max_targets > 20:
        raise ConfigError("max_targets cannot be above 20 (project limit)")
    return cfg


def load_targets(path: str, cfg: Config) -> list[Target]:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    items = raw.get("targets") or []
    if not items:
        raise ConfigError("the target list is empty")
    if len(items) > cfg.max_targets:
        raise ConfigError(f"{len(items)} targets listed but the limit is {cfg.max_targets}")
    targets, seen = [], set()
    for item in items:
        try:
            t = Target(**{k: v for k, v in item.items() if k in Target.__dataclass_fields__})
        except TypeError as e:
            raise ConfigError(f"bad target entry {item!r}: {e}")
        if not t.id or t.id in seen:
            raise ConfigError(f"target id missing or duplicated: {t.id!r}")
        seen.add(t.id)
        try:
            addr = ipaddress.ip_address(t.ip)
        except ValueError:
            raise ConfigError(f"{t.id}: {t.ip!r} is not an IP address")
        if cfg.require_private_ips and not addr.is_private:
            raise ConfigError(f"{t.id}: {t.ip} is a public address; only private lab addresses are allowed")
        if not (1 <= int(t.port) <= 65535):
            raise ConfigError(f"{t.id}: bad port {t.port}")
        if t.expected is not None and t.expected not in LABELS:
            raise ConfigError(f"{t.id}: expected must be one of {LABELS}, got {t.expected!r}")
        if t.own_zone:
            t.own_zone = t.own_zone.strip(".").lower()
        targets.append(t)
    return targets
