# PS-012 demo guide (about 10 minutes)

Presenters: Saurav Kumar (264101047), Tanay Umesh Hambire (264101057)

## Before you start (5 minutes earlier)

- [ ] Start **Docker Desktop** and wait for "Engine running".
- [ ] Open PowerShell in `ps012-dns-probe` and run once: `docker compose up -d` (the demo script also does this).
- [ ] Open these tabs: the GitHub repository, `docs/PS-012_Technical_Submission.pdf`, `docs/pseudocode.txt`.
- [ ] Close other heavy programs (the lab runs 9 small containers).
- [ ] Do one full dry rehearsal: `powershell -ExecutionPolicy Bypass -File scripts\demo.ps1`

Run the live demo with pauses so you can talk between steps:

```bash
powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Pause
```

If you are short on time add `-SkipRepro` (skips the two extra runs, saves about 1.5 minutes).

## The 30-second opening (say this first)

> Open recursive DNS resolvers answer anyone, so attackers use them as reflectors in DDoS amplification attacks (RFC 5358).
> We built a safe tool that checks, from an outside client, whether lab DNS servers really behave the way RFC 5358 asks,
> sorts each one into recursive, authoritative-only, refused or inconclusive, and scores itself against an answer key.
> Everything runs only against servers we built, at a strictly limited rate.

## Step by step

| Step | What the script shows | What to say | What the audience should see |
|---|---|---|---|
| 1 | Starts the lab | "Two isolated Docker networks, no Internet. Test-zone server plus 8 targets t01 to t08." | 9 containers, all `Up` |
| 2 | The answer key | "I know what each server is, because I configured it. The tool never reads this while probing." | ids, names and expected labels |
| 3 | Manual `dig` of t01 and t03 | "Same question, different behaviour. t01 answers with our marker text, t03 refuses outsiders." | t01: `NOERROR`, `ra`, `aiori-probe-ok`. t03: `REFUSED` |
| 4 | Dry run | "It prints the plan and worst-case query count. It refuses to start for public IPs or more than 20 targets." | 8 targets, worst case 144 queries |
| 5 | Real run | "Fresh random name per query, three attempts, majority vote, rate-limited to 5 per second." | 8 labels, **8/8 = 100%**, 39 to 45 queries, peak 5 per second |
| 6 | The report | "Generated automatically: results, accuracy, confusion matrix, false and inconclusive analysis." | table with `resolved+log_confirmed` for t01, t02, t08 |
| 7 | Test-zone log | "Independent proof: the open resolvers appear as the source of our random names." | lines with `172.30.0.11`, `.12`, `.18` |
| 8 | Two more runs and compare | "Every random name is different, yet all three runs give identical labels." | `IDENTICAL: all 3 runs ...` |
| 9 | Safety check | "Point it at 8.8.8.8 and it refuses. That is our guarantee against scanning outside the lab." | `REFUSING TO RUN: ... public address` |
| 10 | Unit tests | "23 tests, including a pretend DNS lab that needs no Docker." | `Ran 23 tests ... OK` |
| 11 | Pseudocode | "The whole decision logic fits on one screen." | open `docs/pseudocode.txt` |

## Key points to make sure the mentor hears

1. **Fresh random names** defeat caching, so a correct answer proves a real lookup.
2. **Two kinds of evidence:** the reply itself and the test-zone log.
3. **Authority probe before "refused"**, because a closed resolver and an authoritative-only server both answer REFUSED.
4. **Inconclusive is a real answer.** Silent, broken or ambiguous servers are reported honestly, with a reason code.
5. **Safe by design:** allowlist, private IPs only, at most 20 targets, rate limits, query budget, isolated networks, no spoofing, no amplification testing.
6. **We found and fixed real problems** by running the real lab (see section 5.4 of the technical PDF and the final report).

## Likely questions and good answers

**Why does a forwarder like dnsmasq set the AA flag?**
It copies the upstream server's flags into its reply. So AA alone cannot tell a forwarder from a server that hosts the zone. We require the test-zone log to confirm; without it the tool says `inconclusive` (`aa_set_unconfirmed`) instead of guessing. We measured this: with the log disabled, t02 became inconclusive and accuracy fell to 7/8.

**What happens on a lossy network?**
Packets can be dropped, so the tool retries and takes a majority vote. In our experiment on the lossy resolver (20% loss), more retries sharply reduced how often a real open resolver was mislabelled. The numbers are in the final report.

**How do you know the tool will not be used for attacks?**
It only sends small, plain, rate-limited UDP queries from its real address. No spoofing, no ANY queries, no large buffers. It reads only allowlisted private addresses and stops at the query budget. An open resolver is found, never exploited.

**Why is the same result `servfail` in one run and `no_response` in another for t07?**
Unbound answers SERVFAIL close to our 2-second timeout. The label is `inconclusive` every time; only the reason text varies. It is documented as expected variation.

**Did the tool ever give a wrong answer?**
Yes, once, and we report it openly (final report, Section 5.5). In 15 further runs after the three documented ones, 14 were fully correct. In one run the lossy open resolver t08 was labelled `inconclusive` instead of `recursive` (attempts 2 and 3 got no reply although the test-zone log shows t08 did resolve the names). We could not reproduce it and have not established the cause. The important point is that it failed in the safe direction: it said "inconclusive", never "not exposed". If it happens live, say exactly that and re-run.

**Can a server look refused to you but be open to others?**
Yes. The result is only for our vantage point. A second client network would test source-dependent restrictions. This is listed as a limitation and a future extension.

**Why did you choose these four classes?**
They come from the problem statement and map to RFC 5358: recursive is the problem, authoritative-only and refused are the two correct fixes, and inconclusive keeps the results honest.

**How is it reproducible?**
All settings are in `config/probe.yaml` and its fingerprint is written to every report. Random names change, but labels are identical across runs (`python -m probe.compare`).

**What would you do with 20 servers?**
Add them to `config/targets.yaml` with their expected labels. The lab and tool already support up to 20.

## If something goes wrong

| Problem | Fix |
|---|---|
| "Docker is not running" | Start Docker Desktop, wait for Engine running, re-run |
| A container shows `Exited` | `docker compose up -d` again; check `docker compose logs <name>` |
| t08 label comes out `inconclusive` (7/8) | Rare (1 run in about 19 with final settings). It fails safe. Say so, re-run, and point to report Section 5.5 |
| Demo script blocked by PowerShell policy | Use `powershell -ExecutionPolicy Bypass -File scripts\demo.ps1` |
| Need to stop everything | `docker compose down` |
