# Scope, ethics and rules

## In scope
- Up to 20 **authorised** DNS servers that we build and own in an isolated lab
- Recursion exposure only
- A controlled test zone (`lab.test`) and a separate client network (`172.31.0.0/24`)

## Out of scope (never do these)
- Scanning the Internet or any server not listed in `config/targets.yaml`
- **Spoofed traffic**: every query leaves with the probe client's real address
- **Amplification or stress testing**: no flooding, no `ANY` queries, no large EDNS buffers
- Testing anything other than recursion exposure

## How the tool enforces this
- The target list is the allowlist; the tool refuses to start if it has more than 20 entries,
  duplicate ids, or any **public** IP address.
- Global and per-target rate limits (token bucket) and a hard `max_total_queries` budget.
- The lab networks are `internal`, so lab recursion cannot reach the real Internet.
- `--dry-run` shows the full plan and worst-case query count without sending anything.
