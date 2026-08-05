# run_daily.ps1 - build every changed day and publish it.
#
# Task \NewsVault\Daily fires this TWICE a day, both times Asia/Ho_Chi_Minh:
#
#   14:00 - after news-hunter's 13:00 digest, so the day's articles are readable by early
#           afternoon instead of waiting for the evening.
#   21:15 - after the 20:00 YouTube summariser, which is the run that picks up the videos.
#
# Two runs are cheap: the build hashes each day and skips what has not changed, and the
# publish step exits early when `git status -- docs` is empty, so an afternoon with no new
# articles costs about ten seconds and produces no commit.
#
# Register with Task Scheduler and QUOTE the executable path: an unquoted path with a space
# fails as 0x800700C1 and the task then dies silently every night.
#
#   $a = New-ScheduledTaskTrigger -Daily -At '14:00'
#   $b = New-ScheduledTaskTrigger -Daily -At '21:15'
#   Set-ScheduledTask -TaskPath '\NewsVault\' -TaskName 'Daily' -Trigger @($a, $b)

[CmdletBinding()]
param(
    # A pipeline expression is not legal in a parameter default - it is a parse error,
    # which would kill this script every night before it printed anything. Resolve below.
    [string]$RepoPath,
    [switch]$NoPush,
    # Build only the newest day, the way this script used to. Kept for a quick manual run;
    # the nightly job must NOT use it - see the comment on $buildArgs below.
    [switch]$TodayOnly
)

$ErrorActionPreference = "Stop"
if (-not $RepoPath) { $RepoPath = Split-Path -Parent $PSScriptRoot }
Set-Location $RepoPath

# The build reports in Vietnamese. Without these the log reads "1 ng├áy dß╗▒ng": Python writes
# the console codepage and PowerShell decodes it as something else. This log is the only
# record of what happened when the job runs unattended, so it has to be readable.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$python = Join-Path $RepoPath ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$logDir = Join-Path $RepoPath "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$stamp = Get-Date -Format "yyyy-MM-dd"
$log = Join-Path $logDir "build-$stamp.log"

function Write-Log([string]$message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $message
    Write-Output $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

Write-Log "build start (todayOnly=$TodayOnly)"

# Every day, not just the newest one. A video is filed under the day it was UPLOADED, so a
# clip summarised tonight can belong to last Tuesday - and a build of the newest day alone
# would never write that page, leaving the video invisible forever. The build hashes each
# day's content and skips what has not changed, so the full pass costs ~10s for 119 days.
$buildArgs = @("-m", "newsvault.cli", "build")
if (-not $TodayOnly) { $buildArgs += "--backfill" }

& $python @buildArgs 2>&1 | ForEach-Object { Write-Log $_ }
if ($LASTEXITCODE -ne 0) {
    Write-Log "BUILD FAILED exit=$LASTEXITCODE"
    exit $LASTEXITCODE
}

# Refuse to publish a site that still carries the plaintext password anywhere.
$password = $env:NEWSVAULT_PASSWORD
if (-not $password) {
    $envFile = Join-Path $RepoPath ".env"
    if (Test-Path $envFile) {
        $match = Select-String -Path $envFile -Pattern '^NEWSVAULT_PASSWORD=(.*)$'
        if ($match) { $password = $match.Matches[0].Groups[1].Value.Trim('"').Trim("'") }
    }
}
if ($password) {
    $leak = Get-ChildItem -Path (Join-Path $RepoPath "docs") -Recurse -File |
        Select-String -SimpleMatch -Pattern $password -List
    if ($leak) {
        Write-Log "ABORT: mat khau xuat hien trong docs/: $($leak.Path)"
        exit 2
    }
}

if ($NoPush) {
    Write-Log "done (push skipped)"
    exit 0
}

$changes = git status --porcelain -- docs
if (-not $changes) {
    Write-Log "no changes to publish"
    exit 0
}

git add -- docs
git -c user.name="baronguyen001" -c user.email="265752715+baronguyen001@users.noreply.github.com" `
    commit -m "docs: nhat bao $stamp" | ForEach-Object { Write-Log $_ }
git push origin main | ForEach-Object { Write-Log $_ }
Write-Log "published"
