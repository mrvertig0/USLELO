# Run the USL2 Elo data pipeline locally and push the results to GitHub.
#
# This exists because Sofascore's API blocks GitHub Actions' IP ranges,
# so the fetch has to happen from a normal residential connection --
# i.e. this computer -- instead of in the cloud. Run this manually
# whenever you want fresh ratings, or schedule it with Windows Task
# Scheduler (see README.md) to run automatically once a day.
#
# Usage (from the repo root, in PowerShell):
#   .\scripts\run_update.ps1

$ErrorActionPreference = "Stop"

# Move to the repo root (parent of this script's folder), regardless of
# where this was launched from -- important for Task Scheduler, which
# often runs with an unexpected working directory.
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "== USL2 Elo update: $(Get-Date) =="

Write-Host "-- Pulling latest repo state --"
git pull --ff-only

Write-Host "-- Fetching match data --"
python scripts\fetch_data.py

Write-Host "-- Computing Elo ratings --"
python scripts\compute_elo.py

Write-Host "-- Checking for changes --"
git add data docs\data
$changes = git status --porcelain -- data docs\data

if ([string]::IsNullOrWhiteSpace($changes)) {
    Write-Host "No changes -- ratings are already up to date."
} else {
    git commit -m "Update ratings [local]"
    Write-Host "-- Pushing to GitHub --"
    git push
    Write-Host "Done -- GitHub Pages will republish automatically."
}
