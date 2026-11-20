# PS-012 live demo: runs the whole story step by step.
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1            (runs straight through)
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1 -Pause     (waits for Enter before each step)
#   add -SkipRepro to skip the two extra runs (saves about 1.5 minutes)
param([switch]$Pause, [switch]$SkipRepro)

Set-Location (Split-Path $PSScriptRoot -Parent)

function Step($n, $title, $say) {
    Write-Host ""
    Write-Host "=== STEP ${n}: $title ===" -ForegroundColor Cyan
    Write-Host "SAY: $say" -ForegroundColor DarkGray
    if ($Pause) { Read-Host "Press Enter to run this step" | Out-Null }
}

function Latest-Run {
    Get-ChildItem results -Directory | Where-Object { $_.Name -match '^\d{8}-\d{6}$' } | Sort-Object Name | Select-Object -Last 1
}

docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Host "Docker is not running. Start Docker Desktop, wait for 'Engine running', then re-run." -ForegroundColor Red; exit 1 }

Step 1 "Start the lab" "This is our pretend Internet: a test-zone server and 8 DNS servers I configured on purpose. Two isolated networks, no Internet access."
docker compose up -d 2>&1 | Select-Object -Last 3
Start-Sleep 5
docker compose ps --format "table {{.Name}}\t{{.Status}}"
# quiet warm-up (precaution): one throw-away question to the lossy server so its first real lookup is not cold
docker compose run --rm -T dig -c "dig @172.31.0.18 warmup.probe.lab.test TXT +time=3 +tries=2 > /dev/null 2>&1" *> $null

Step 2 "The answer key (ground truth)" "I know what each server really is because I configured it. The tool never sees this file while probing; it is only used to score the result."
Get-Content config\targets.yaml | Select-String -Pattern "^\s+(id|name|expected):" | ForEach-Object { $_.Line.Trim() }

Step 3 "Ask two servers by hand" "Before the tool, a manual check. t01 is an open resolver, t03 is restricted to the lab network. Same question, different behaviour."
Write-Host "--- t01 (open Unbound)" -ForegroundColor Yellow
docker compose run --rm -T dig -c "dig @172.31.0.11 demo1.probe.lab.test TXT +noall +comments +answer +time=3 +tries=1 | grep -E 'status:|flags:|aiori'" 2>&1 | Where-Object { $_ -notmatch "Container ps012" }
Write-Host "--- t03 (ACL Unbound)" -ForegroundColor Yellow
docker compose run --rm -T dig -c "dig @172.31.0.13 demo3.probe.lab.test TXT +noall +comments +answer +time=3 +tries=1 | grep -E 'status:|flags:|aiori'" 2>&1 | Where-Object { $_ -notmatch "Container ps012" }

Step 4 "Dry run: check the plan, send nothing" "The tool shows exactly what it would do and the worst-case number of queries. It refuses to start if a target is public or there are more than 20."
docker compose run --rm -T probe python -m probe.main --dry-run 2>&1 | Where-Object { $_ -notmatch "Container ps012" }

Step 5 "Real assessment" "Each target gets fresh random names, retried and voted on three times, under a global limit of 5 queries per second and a hard budget of 500."
docker compose run --rm -T probe 2>&1 | Where-Object { $_ -notmatch "Container ps012" }

Step 6 "The report" "This is generated automatically: results table, accuracy, confusion matrix, and the false and inconclusive analysis."
$run = Latest-Run
Get-Content (Join-Path $run.FullName "report.md") | Select-Object -First 36

Step 7 "Independent proof of recursion" "The test-zone server logs who asked. The open resolvers t01, t02 and t08 appear as the source of the random names, so the answer was not a cache trick."
docker compose exec -T testzone sh -c "tail -n 5 /logs/query.log" 2>&1

if (-not $SkipRepro) {
    Step 8 "Reproducibility" "I run it two more times and compare. The labels must be identical even though every random name is different."
    docker compose run --rm -T probe 2>&1 | Select-String -Pattern "Accuracy|Reports written"
    docker compose run --rm -T probe 2>&1 | Select-String -Pattern "Accuracy|Reports written"
    $runs = Get-ChildItem results -Directory | Where-Object { $_.Name -match '^\d{8}-\d{6}$' } | Sort-Object Name | Select-Object -Last 3 | ForEach-Object { $_.FullName }
    python -m probe.compare @runs
}

Step 9 "Safety check" "If someone points the tool at a public address, it refuses to run. This is how we guarantee no scanning outside the lab."
$bad = Join-Path $env:TEMP "ps012_public_target.yaml"
Set-Content -Path $bad -Value "targets:`n  - {id: x1, ip: 8.8.8.8, expected: recursive}" -Encoding ascii
python -m probe.main --targets $bad
Remove-Item $bad -Force

Step 10 "Automatic tests" "23 tests, including a pretend DNS lab that needs no Docker."
python -m unittest discover -s tests -t . 2>&1 | Select-Object -Last 4

Step 11 "The pseudocode" "This is the whole decision logic in one screen."
Get-Content docs\pseudocode.txt

Write-Host ""
Write-Host "Demo finished. Stop the lab afterwards with:  docker compose down" -ForegroundColor Green
