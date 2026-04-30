# Safe local cleanup for Automat generated/manual helper files.
# Run from the repository root. This does NOT delete the SQLite DB or your latest working artifacts.

$ErrorActionPreference = "Stop"

Write-Host "Repo root:" (Get-Location)

# Remove temporary patch/helper scripts created during manual patching.
$rootTempFiles = @(
  "manual_patch_dump_prospects.patch",
  "apply_manual_dump_prospects_patch.py",
  "fix_dump_prospects_parser.py"
)

foreach ($file in $rootTempFiles) {
  if (Test-Path $file) {
    Remove-Item $file
    Write-Host "Removed $file"
  }
}

# Remove local pytest scratch dir if present.
if (Test-Path "pytest_tmp") {
  Remove-Item "pytest_tmp" -Recurse -Force
  Write-Host "Removed pytest_tmp"
}

# Keep these by default:
# - data/automat.sqlite3
# - data/debug/upwork_raw_hydrated_latest.json
# - data/debug/dry_run_latest.json
# - data/manual/enrichment_queue.csv
# - data/manual/prospects_dump.txt
# - timestamped remaining enrichment CSVs
Write-Host "Kept DB/debug/manual artifacts."
Write-Host "Done."
