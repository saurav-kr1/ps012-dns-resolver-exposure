# PS-012: Authorised DNS Resolver Exposure Assessment

A small, safe tool that checks whether DNS servers **in our own lab** answer recursive
queries from an outside client, and sorts each server into
**recursive / authoritative-only / refused / inconclusive**, then scores itself against a known answer key.

Team: Saurav Kumar (264101047), Tanay Umesh Hambire (264101057)
Reference: RFC 5358 (BCP 140). Read `SCOPE.md` first: it lists what this tool must never do.

---

## What is in this folder

| Path | What it is |
|---|---|
| `probe/` | The tool (Python). `classify.py` is the decision tree, `ratelimit.py` the rate control |
| `config/probe.yaml` | Settings: rate limits, retries, budget. Change numbers here, not in code |
| `config/targets.yaml` | The allowlist AND the answer key (what each lab server really is) |
| `lab/` | Configuration of the pretend-Internet servers (Unbound, dnsmasq, BIND) |
| `docker-compose.yml` | Starts the whole lab with one command |
| `tests/` | Automatic tests, plus a pretend lab that needs no Docker |
| `results/` | Reports appear here, one folder per run |

---

## Part A: Practice run WITHOUT Docker (works today)

Open PowerShell in this folder.

**1. Install the two Python libraries (once):**
```bash
python -m pip install dnspython pyyaml
```

**2. Run the automatic tests (should say `OK`):**
```bash
python -m unittest discover -s tests -t .
```

**3. Start the pretend DNS servers.** Leave this window open:
```bash
python -m tests.fake_lab
```

**4. In a SECOND PowerShell window, check the plan without sending anything:**
```bash
python -m probe.main --config config/probe.local.yaml --targets config/targets.local.yaml --dry-run
```

**5. Run it for real:**
```bash
python -m probe.main --config config/probe.local.yaml --targets config/targets.local.yaml
```
Open `results/<newest folder>/report.md` to see the report.

**6. Stop the pretend servers** with Ctrl+C in the first window.

---

## Part B: The real lab with Docker

**1. Start Docker Desktop** (Start menu) and wait until it says "Engine running".

**2. Build the images (first time only, needs Internet, takes a few minutes):**
```bash
docker compose build
docker compose --profile tools build
```

**3. Start the lab (9 small containers: the test-zone server plus 8 targets t01-t08):**
```bash
docker compose up -d
docker compose ps
```

**4. Look at one server by hand with `dig`** (a manual DNS question). `+norecurse` means "don't look it up for me":
```bash
docker compose run --rm dig -c "dig @172.31.0.11 hello1.probe.lab.test TXT"
docker compose run --rm dig -c "dig @172.31.0.13 hello2.probe.lab.test TXT"
docker compose run --rm dig -c "dig @172.31.0.14 example-lab.test SOA +norecurse"
```
Expected: t01 answers `"aiori-probe-ok"`; t03 says `REFUSED`; t04 shows the `aa` flag.
(Note: t02, the dnsmasq forwarder, also shows `aa` on its forwarded answers. That is why the tool
confirms recursion with the test-zone log instead of trusting the flag alone.)

What each lab target is, and the label we expect (the "answer key" in `config/targets.yaml`):

| Target | What it is | Expected |
|---|---|---|
| t01 | Open Unbound resolver | recursive |
| t02 | Open dnsmasq forwarder | recursive |
| t03 | Unbound restricted to the lab network (ACL) | refused |
| t04 | BIND, recursion off, hosts `example-lab.test` | authoritative-only |
| t05 | Unbound listening only on its lab-side address | inconclusive (no reply) |
| t06 | Nothing listening on port 53 | inconclusive |
| t07 | Open resolver with a broken upstream | inconclusive |
| t08 | Open resolver behind 20% packet loss | recursive |

**5. Check the plan, then run the tool from inside the lab:**
```bash
docker compose run --rm probe python -m probe.main --dry-run
docker compose run --rm probe
```

**6. Read the report:** `results/<newest folder>/report.md`.

**7. Reproducibility: run it 3 times and compare:**
```bash
docker compose run --rm probe
docker compose run --rm probe
docker compose run --rm probe
python -m probe.compare results/<run1> results/<run2> results/<run3>
```

**8. See the proof that t01 really recursed** (the test zone logged who asked):
```bash
docker compose exec testzone sh -c "tail -n 5 /logs/query.log"
```

**9. Stop everything:**
```bash
docker compose down
```

---

## Part C: Demo, experiments and reports

| What | Where |
|---|---|
| One-command live demo (11 steps, with talking points) | `powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Pause` |
| Presenter guide and likely mentor questions | `docs/DEMO_SCRIPT.md` |
| Pseudocode snippet for the mentor | `docs/pseudocode.txt` |
| Experiment A: no test-zone log (dnsmasq becomes inconclusive) | `docker compose run --rm probe python -m probe.main --config config/probe.nolog.yaml --out results/nolog` |
| Experiment B: packet loss vs retries on t08 | `docker compose run --rm probe python -m probe.experiments lossy --runs 40` |
| **Project report** (problem, objectives, design, work completed, limitations, challenges, conclusions) | `docs/PS-012_Project_Report.pdf` (editable Word version: `docs/PS-012_Project_Report.docx`) |
| **Presentation** (15 slides, speaker notes with timings) | `docs/PS-012_Presentation.pptx` |
| 2-page project proposal | `docs/PS-012_Project_Proposal_2page.pdf` (editable Word version: `docs/PS-012_Project_Proposal_2page.docx`) |
| Final exposure assessment report (with false/inconclusive analysis) | `docs/PS-012_Final_Exposure_Report.pdf` |
| Technical submission in the hackathon structure | `docs/PS-012_Technical_Submission.pdf` |
| Sample report from one real run | `docs/sample_run/report.md` |
| Raw data used in the final report | `docs/final_report_data/` |

---

## How the tool decides (the heart of the project)

For each target, three times (then majority vote):

1. **P1, recursion probe:** ask `<random>.probe.lab.test` TXT with "please recurse" on.
   The name is brand new, so only a server that really looked it up can answer `aiori-probe-ok`.
2. **P2, authority probe:** if the target owns a zone, ask for it with recursion off.

Then, first match wins:

1. No valid reply -> `inconclusive`
2. P1 answered correctly with RA=1 -> `recursive`
   (if the AA flag is also set, the test-zone log must confirm the target itself asked upstream,
   otherwise -> `inconclusive`, reason `aa_set_unconfirmed`)
3. P2 has AA=1 -> `authoritative-only`
4. REFUSED -> `refused`
5. anything else -> `inconclusive` (with a reason such as `servfail`)

## Safety summary

Only allowlisted private lab addresses (public IPs are rejected), at most 20 targets,
real source address only (no spoofing), small plain queries (no ANY, no big EDNS),
global + per-target rate limits, and a hard query budget.
