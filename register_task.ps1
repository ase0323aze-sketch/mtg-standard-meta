# Register a Windows task that runs run_update.ps1 on the 1st and 15th at 9:00.
# schtasks supports monthly-on-specific-days (1,15) directly.
$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
$script = Join-Path $here "run_update.ps1"
$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$script`""

# schtasks /SC MONTHLY /D accepts a single day reliably, so register two tasks.
foreach ($day in 1, 15) {
    $tn = "MTG-Meta-Update-$day"
    schtasks /Create /TN $tn /TR $cmd /SC MONTHLY /D $day /ST 09:00 /F
}

Write-Host ""
Write-Host "Registered: MTG-Meta-Update-1 / -15  (monthly, 09:00)"
Write-Host "Query : schtasks /Query /TN MTG-Meta-Update-1"
Write-Host "Run   : schtasks /Run   /TN MTG-Meta-Update-1"
Write-Host "Delete: schtasks /Delete /TN MTG-Meta-Update-1 /F"
