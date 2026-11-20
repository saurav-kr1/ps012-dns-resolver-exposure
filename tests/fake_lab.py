"""Tiny pretend DNS servers on 127.0.0.1, so the tool can be tested WITHOUT Docker.

Behaviours:
  open     answers any name under the probe zone, RA=1          -> recursive
  refused  answers REFUSED to everything                        -> refused
  auth     AA=1 SOA for its own zone, REFUSED for other names   -> authoritative-only
  silent   never replies                                        -> inconclusive
  servfail SERVFAIL with RA=1                                   -> inconclusive
  flaky    like open, but drops the first packet per name       -> recursive (needs a retry)

Run by hand:  python -m tests.fake_lab     (Ctrl+C to stop)
"""
from __future__ import annotations

import socket
import threading

import dns.flags
import dns.message
import dns.rcode
import dns.rrset


class FakeServer(threading.Thread):
    def __init__(self, behaviour: str, own_zone: str | None = None, port: int = 0,
                 txt: str = "aiori-probe-ok", probe_zone: str = "probe.lab.test"):
        super().__init__(daemon=True)
        self.behaviour, self.own_zone, self.txt, self.probe_zone = behaviour, own_zone, txt, probe_zone
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", port))
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self._halt = threading.Event()
        self._seen = set()

    def stop(self):
        self._halt.set()
        self.join(timeout=2)
        self.sock.close()

    def run(self):
        while not self._halt.is_set():
            try:
                data, addr = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                q = dns.message.from_wire(data)
            except Exception:
                continue
            reply = self._answer(q)
            if reply is not None:
                self.sock.sendto(reply.to_wire(), addr)

    def _answer(self, q):
        qname = str(q.question[0].name).rstrip(".").lower()
        resp = dns.message.make_response(q)
        b = self.behaviour
        if b == "silent":
            return None
        if b == "flaky":
            if qname not in self._seen:
                self._seen.add(qname)
                return None
            b = "open"
        if b == "refused":
            resp.set_rcode(dns.rcode.REFUSED)
        elif b == "servfail":
            resp.flags |= dns.flags.RA
            resp.set_rcode(dns.rcode.SERVFAIL)
        elif b == "auth":
            if self.own_zone and qname == self.own_zone:
                resp.flags |= dns.flags.AA
                resp.answer.append(dns.rrset.from_text(
                    q.question[0].name, 60, "IN", "SOA", "ns1.x. admin.x. 1 3600 600 86400 60"))
            else:
                resp.set_rcode(dns.rcode.REFUSED)
        elif b == "open":
            resp.flags |= dns.flags.RA
            if qname.endswith(self.probe_zone):
                resp.answer.append(dns.rrset.from_text(q.question[0].name, 60, "IN", "TXT", f'"{self.txt}"'))
            else:
                resp.set_rcode(dns.rcode.NXDOMAIN)
        return resp


def start_lab(specs):
    """specs: list of (id, behaviour, own_zone, expected). Returns (servers, ports)."""
    servers = {}
    for sid, behaviour, own_zone, _ in specs:
        s = FakeServer(behaviour, own_zone)
        s.start()
        servers[sid] = s
    return servers


if __name__ == "__main__":
    import time
    fixed = [("f01", "open", None, 15301), ("f02", "refused", None, 15302),
             ("f03", "auth", "example-lab.test", 15303), ("f04", "silent", None, 15304),
             ("f05", "servfail", None, 15305), ("f06", "flaky", None, 15306)]
    live = []
    for sid, beh, zone, port in fixed:
        s = FakeServer(beh, zone, port)
        s.start()
        live.append(s)
        print(f"{sid}: {beh:<8} on 127.0.0.1:{port}")
    print("Fake lab running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for s in live:
            s.stop()
