# out.ps1
# One command per line in $CommandBlock.
# Writes everything to out.txt and also prints to terminal.
# Designed for Windows PowerShell 5.1+.

$OutputFile = Join-Path $PSScriptRoot "out.txt"

function Write-Log {
    param(
        [AllowNull()]
        [object] $Value = ""
    )

    $Text = if ($null -eq $Value) { "" } else { [string]$Value }

    Write-Host $Text
    Add-Content -Path $OutputFile -Value $Text -Encoding UTF8
}

# Recreate file in one encoding.
Set-Content -Path $OutputFile -Value "" -Encoding UTF8

Write-Log "Run started: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")"
Write-Log "Repo: $PWD"
Write-Log "============================================================"
Write-Log ""

function Run-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string] $CommandLine
    )

    Write-Log ""
    Write-Log ""
    Write-Log "============================================================"
    Write-Log $CommandLine
    Write-Log "============================================================"

    $global:LASTEXITCODE = $null

    try {
        Invoke-Expression "$CommandLine 2>&1" | ForEach-Object {
            Write-Log $_
        }

        if ($null -ne $LASTEXITCODE) {
            Write-Log "Exit code: $LASTEXITCODE"
        }
    }
    catch {
        Write-Log "PowerShell error: $_"
    }
}

# =========================
# EDIT THIS MIDDLE SECTION
# One command per line.
# Blank lines and lines starting with # are ignored.
# =========================

$CommandBlock = @'
git diff --stat
py -m pytest tests/test_best_matches_parse.py tests/test_lead_review.py tests/test_lead_discard_tags.py
'@

# =========================
# END EDITABLE SECTION
# =========================

$Commands = $CommandBlock -split "`r?`n" |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and -not $_.StartsWith("#") }

foreach ($CommandLine in $Commands) {
    Run-Step $CommandLine
}

Write-Log ""
Write-Log ""
Write-Log "============================================================"
Write-Log "Run finished: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")"
Write-Log "Output written to: $OutputFile"