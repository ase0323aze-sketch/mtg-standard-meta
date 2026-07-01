# Runs on the 1st and 15th via Task Scheduler.
# Collect -> analyze (emit JSON) -> push docs to GitHub Pages.
# ASCII-only on purpose: PowerShell 5.1 misreads UTF-8-no-BOM scripts, so an
# unattended task with Japanese text could fail to parse. Keep this file ASCII.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $here
$py = Join-Path $here "venv\Scripts\python.exe"

Write-Host "[1/3] collect (MTGTop8 + Moxfield)"
& $py collect_runner.py --source mtgtop8 --limit 40
& $py collect_runner.py --source moxfield --limit 20

Write-Host "[2/4] analyze + emit web JSON"
& $py analyze.py --json

Write-Host "[3/4] generate AI showcase decks (meta-aware)"
& $py build_showcase.py

Write-Host "[4/4] publish to GitHub"
git add docs
if (git diff --cached --quiet) {
    Write-Host "  no changes; skip push"
} else {
    $stamp = Get-Date -Format "yyyy-MM-dd"
    git commit -m "meta update $stamp"
    git push
    Write-Host "  pushed"
}
Write-Host "done"
