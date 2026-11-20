"""Second, independent proof of recursion: did the test-zone server see the nonce?

If a target really recursed, the test zone server logs a line like
    client @0x... 172.30.0.11#40913 (k39xq7.probe.lab.test): query: ...
so we look for the random name (nonce) and the target's lab address in that log.
"""
from __future__ import annotations

import os
import time
from typing import Optional


def _scan(path: str, nonce: str, from_ip: Optional[str]) -> bool:
    needle = nonce.lower()
    marker = f"{from_ip}#" if from_ip else None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            low = line.lower()
            if needle in low and (marker is None or marker in line):
                return True
    return False


def nonce_seen(path: Optional[str], nonce: str, from_ip: Optional[str],
               wait_s: float = 1.0, poll_s: float = 0.2) -> Optional[bool]:
    """True = seen, False = not seen, None = no log available to check."""
    if not path or not os.path.exists(path):
        return None
    deadline = time.monotonic() + wait_s
    while True:
        if _scan(path, nonce, from_ip):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_s)
