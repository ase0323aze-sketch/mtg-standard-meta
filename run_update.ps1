# 毎月1日・15日にタスクスケジューラから実行される更新スクリプト。
# 収集 → 解析(JSON出力) → docs を GitHub に push して Pages を更新する。
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $here
$py = Join-Path $here "venv\Scripts\python.exe"

Write-Host "[1/3] 収集 (MTGTop8 + Moxfield)"
& $py collect_runner.py --source mtgtop8 --limit 40
& $py collect_runner.py --source moxfield --limit 20

Write-Host "[2/3] 解析 + Web用JSON書き出し"
& $py analyze.py --json

Write-Host "[3/3] GitHub へ公開"
git add docs
if (git diff --cached --quiet) {
    Write-Host "  変更なし。push をスキップ"
} else {
    $stamp = Get-Date -Format "yyyy-MM-dd"
    git commit -m "メタ更新 $stamp"
    git push
    Write-Host "  push 完了"
}
Write-Host "完了"
