# DNS resolver exposure assessment report

- Run: `20261118-071214`  |  Date: 2026-11-18T07:12:38
- Config fingerprint: `3e7e861561b3`  |  Targets: 8

## 1. Safety and rate-control evidence

- Queries sent: **39** (budget 500)
- Peak queries in any 1-second window: **5** (global limit 5/s)
- Duration of sending: 22.0 s
- Only allowlisted lab targets, real source address, small plain queries, no spoofing, no amplification testing.

## 2. Results per target

| ID | Name | Expected | Predicted | Match | Reason | Evidence |
|---|---|---|---|---|---|---|
| t01 | open-unbound | recursive | recursive | yes | resolved+log_confirmed | P1 rcode=NOERROR, RA=1 AA=0 |
| t02 | open-dnsmasq | recursive | recursive | yes | resolved+log_confirmed | P1 rcode=NOERROR, RA=1 AA=1 |
| t03 | acl-unbound | refused | refused | yes | rcode_refused | P1 rcode=REFUSED, RA=0 AA=0 |
| t04 | auth-bind | authoritative-only | authoritative-only | yes | aa_on_own_zone | P1 rcode=REFUSED, RA=0 AA=0 |
| t05 | iface-unbound | inconclusive | inconclusive | yes | no_response | P1 rcode=timeout |
| t06 | dead | inconclusive | inconclusive | yes | no_response | P1 rcode=timeout |
| t07 | servfail-unbound | inconclusive | inconclusive | yes | servfail | P1 rcode=SERVFAIL, RA=1 AA=0 |
| t08 | lossy-unbound | recursive | recursive | yes | resolved+log_confirmed | P1 rcode=NOERROR, RA=1 AA=0 |

## 3. Accuracy against ground truth

Accuracy: **8/8 = 100%**

Confusion matrix (rows = expected, columns = predicted):

| expected \ predicted | recursive | authoritative-only | refused | inconclusive |
|---|---|---|---|---|
| **recursive** | 3 | 0 | 0 | 0 |
| **authoritative-only** | 0 | 1 | 0 | 0 |
| **refused** | 0 | 0 | 1 | 0 |
| **inconclusive** | 0 | 0 | 0 | 3 |

| Class | Support | Precision | Recall |
|---|---|---|---|
| recursive | 3 | 1.00 | 1.00 |
| authoritative-only | 1 | 1.00 | 1.00 |
| refused | 1 | 1.00 | 1.00 |
| inconclusive | 3 | 1.00 | 1.00 |

## 4. False and inconclusive result analysis

- **t05** (iface-unbound): expected `inconclusive`, predicted `inconclusive`, reason `no_response` - inconclusive (as expected). No valid reply to any probe (firewalled, not listening on the probed address, or heavy packet loss). Votes: {'inconclusive': 3}
- **t06** (dead): expected `inconclusive`, predicted `inconclusive`, reason `no_response` - inconclusive (as expected). No valid reply to any probe (firewalled, not listening on the probed address, or heavy packet loss). Votes: {'inconclusive': 3}
- **t07** (servfail-unbound): expected `inconclusive`, predicted `inconclusive`, reason `servfail` - inconclusive (as expected). The server answered SERVFAIL: it probably tried to recurse and failed upstream. It may be a resolver with a broken upstream, not proof either way. Votes: {'inconclusive': 3}

## 5. Findings and RFC 5358 recommendations

- **t01** `recursive`: Open resolver. Apply RFC 5358 Section 4: restrict recursion to intended clients (ACL, incoming interface, TSIG, VPN) and deploy ingress filtering (BCP 38).
- **t02** `recursive`: Open resolver. Apply RFC 5358 Section 4: restrict recursion to intended clients (ACL, incoming interface, TSIG, VPN) and deploy ingress filtering (BCP 38).
- **t03** `refused`: Correct for a restricted resolver: outsiders are refused (RFC 5358, Section 4).
- **t04** `authoritative-only`: Correct for an authoritative-only server: recursion is off (RFC 5358, Section 4).
- **t05** `inconclusive`: Could not be classified from this vantage point; see the reason code.
- **t06** `inconclusive`: Could not be classified from this vantage point; see the reason code.
- **t07** `inconclusive`: Could not be classified from this vantage point; see the reason code.
- **t08** `recursive`: Open resolver. Apply RFC 5358 Section 4: restrict recursion to intended clients (ACL, incoming interface, TSIG, VPN) and deploy ingress filtering (BCP 38).

## 6. Limitations

- The lab models real networks; results come from a single vantage point.
- A server that is open only to some source networks may look refused from here.
- Only recursion exposure is tested.
