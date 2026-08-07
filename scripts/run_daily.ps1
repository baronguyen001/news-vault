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
    [switch]$DryRunNotify,
    # Build only the newest day, the way this script used to. Kept for a quick manual run;
    # the nightly job must NOT use it - see the comment on $buildArgs below.
    [switch]$TodayOnly
)

$ErrorActionPreference = "Stop"

function Write-Log([string]$message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $message
    Write-Output $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

# Read one key from .env. Values never reach the log or the console - the bot token lives
# here and this repo is public.
function Get-EnvValue([string]$name) {
    $fromProcess = [Environment]::GetEnvironmentVariable($name)
    if ($fromProcess) { return $fromProcess }
    if (-not (Test-Path $envFile)) { return $null }
    $match = Select-String -Path $envFile -Pattern ("^{0}=(.*)$" -f [regex]::Escape($name))
    if (-not $match) { return $null }
    return $match.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
}

function Format-RunMessage {
    param(
        [Parameter(Mandatory)][ValidateSet("published", "nochange", "buildfail", "pushfail")]
        [string]$Outcome,
        [string]$Summary = "",
        [string]$NewestDay = "",
        [int]$NewestCount = 0,
        [string]$SiteUrl = "",
        [int]$ExitCode = 0,
        [string]$Stamp = "",
        [string]$Mode = ""
    )

    $lines = @()
    switch ($Outcome) {
        "published" {
            $lines += "📰 Kho tin đã cập nhật"
            if ($NewestDay) {
                $pretty = ([datetime]::ParseExact($NewestDay, "yyyy-MM-dd", $null)).ToString("dd/MM/yyyy")
                $lines += "Mới nhất: {0} — {1} tin" -f $pretty, $NewestCount
            }
            if ($Summary) { $lines += $Summary }
            if ($NewestDay) { $lines += "$($SiteUrl.TrimEnd('/'))/d/$NewestDay/" }
            else { $lines += "$($SiteUrl.TrimEnd('/'))/" }
        }
        "nochange" {
            $lines += "✅ Kho tin: chạy xong, không có tin mới"
            if ($Summary) { $lines += $Summary }
        }
        "buildfail" {
            $lines += "❌ Kho tin: BUILD HỎNG (exit $ExitCode)"
        }
        "pushfail" {
            $lines += "❌ Kho tin: dựng xong nhưng PUSH HỎNG (exit $ExitCode)"
        }
    }

    if ($Stamp -or $Mode) {
        $lines += "🕒 $Stamp · $Mode"
    }

    return ($lines -join "`n")
}

function Send-Telegram([string]$text) {
    if ($DryRunNotify) {
        Write-Log ("TELEGRAM (dry-run):`n{0}" -f $text)
        return
    }
    if (-not $tgToken -or -not $tgChat) {
        Write-Log "telegram: chua cau hinh, bo qua"
        return
    }
    try {
        # JSON as raw UTF-8 bytes: a hashtable body gets form-encoded with the system
        # codepage and Vietnamese arrives as mojibake on the phone.
        $payload = @{ chat_id = $tgChat; text = $text; disable_web_page_preview = $false }
        $json = $payload | ConvertTo-Json -Compress
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
        $uri = "https://api.telegram.org/bot$tgToken/sendMessage"
        Invoke-RestMethod -Method Post -Uri $uri -Body $bytes `
            -ContentType 'application/json; charset=utf-8' -TimeoutSec 30 | Out-Null
        Write-Log "telegram: da gui"
    }
    catch {
        # Never let the notification take down a build that already succeeded. The message
        # is the point of the run only for the reader; the published site is the product.
        Write-Log ("telegram: gui that bai - {0}" -f $_.Exception.Message)
    }
}

if (-not $env:NEWSVAULT_SOURCING_ONLY) {
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

    $envFile = Join-Path $RepoPath ".env"

    # Telegram. Silent no-op when the keys are absent, so a checkout without them still builds.
    $tgToken = Get-EnvValue "NEWSVAULT_TELEGRAM_TOKEN"
    $tgChat = Get-EnvValue "NEWSVAULT_TELEGRAM_CHAT"

    $runStamp = Get-Date -Format "HH:mm"
    $runMode = "đầy đủ"
    if ($TodayOnly) { $runMode = "chỉ hôm nay" }

    Write-Log "build start (todayOnly=$TodayOnly)"

    # Every day, not just the newest one. A video is filed under the day it was UPLOADED, so a
    # clip summarised tonight can belong to last Tuesday - and a build of the newest day alone
    # would never write that page, leaving the video invisible forever. The build hashes each
    # day's content and skips what has not changed, so the full pass costs ~10s for 119 days.
    $buildArgs = @("-m", "newsvault.cli", "build")
    if (-not $TodayOnly) { $buildArgs += "--backfill" }

    # Keep the build's own summary line - it is what the Telegram message reports.
    $buildSummary = ""
    # $ErrorActionPreference = "Stop" plus `2>&1` on a NATIVE command is a trap: PowerShell
    # wraps each stderr line in an ErrorRecord and throws NativeCommandError, so a Python
    # traceback killed this script AT this line - past the log, past the failure alert, past
    # everything. The build then failed in total silence, which is the one thing the alert
    # below exists to prevent. Verified by pointing NEWSVAULT_DB at a missing file.
    $previousEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $python @buildArgs 2>&1 | ForEach-Object {
        Write-Log $_
        if ($_ -match "ngày dựng") { $buildSummary = "$_".Trim() }
    }
    $buildExit = $LASTEXITCODE
    $ErrorActionPreference = $previousEAP
    if ($buildExit -ne 0) {
        Write-Log "BUILD FAILED exit=$buildExit"
        # A nightly job that dies quietly is how this task once sat dead for a week.
        Send-Telegram (Format-RunMessage -Outcome "buildfail" -ExitCode $buildExit `
            -Stamp $runStamp -Mode $runMode)
        exit $buildExit
    }

    # The build only ever writes; it has no code path that removes anything. So when a row
    # leaves the source database - a video the summariser flags as junk, say - the day drops out
    # of the build's targets and its already-published page just stays live, still serving the
    # old payload with the pulled item inside it. Most archived days hold only videos and some
    # hold exactly one, so a single removed row can leave a whole day stranded. This deletes
    # what the fresh manifest no longer lists. It runs after the build, before the commit, so
    # the deletions travel in the same push as the rest of the day's changes.
    $previousEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $python (Join-Path $RepoPath "scripts\prune_orphans.py") "--apply" 2>&1 |
        ForEach-Object { Write-Log $_ }
    $pruneExit = $LASTEXITCODE
    $ErrorActionPreference = $previousEAP
    # A failed prune is not a reason to withhold a good build: the site stays correct, it just
    # keeps a stale page a while longer. Log it and carry on.
    if ($pruneExit -ne 0) { Write-Log "PRUNE FAILED exit=$pruneExit (tiep tuc xuat ban)" }

    # Refuse to publish a site that still carries the plaintext password anywhere.
    $password = Get-EnvValue "NEWSVAULT_PASSWORD"
    if ($password) {
        $leak = Get-ChildItem -Path (Join-Path $RepoPath "docs") -Recurse -File |
            Select-String -SimpleMatch -Pattern $password -List
        if ($leak) {
            Write-Log "ABORT: mat khau xuat hien trong docs/: $($leak.Path)"
            # Deliberately does not name the file: the alert itself must not leak anything.
            Send-Telegram ("🚨 Kho tin: DỪNG XUẤT BẢN - mật khẩu lọt vào docs/. Chưa push gì cả.`n🕒 {0} · {1}" -f $runStamp, $runMode)
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
        Send-Telegram (Format-RunMessage -Outcome "nochange" -Summary $buildSummary `
            -Stamp $runStamp -Mode $runMode)
        exit 0
    }

    git add -- docs
    git -c user.name="baronguyen001" -c user.email="265752715+baronguyen001@users.noreply.github.com" `
        commit -m "docs: nhat bao $stamp" | ForEach-Object { Write-Log $_ }
    git push origin main | ForEach-Object { Write-Log $_ }
    if ($LASTEXITCODE -ne 0) {
        Write-Log "PUSH FAILED exit=$LASTEXITCODE"
        Send-Telegram (Format-RunMessage -Outcome "pushfail" -ExitCode $LASTEXITCODE `
            -Stamp $runStamp -Mode $runMode)
        exit $LASTEXITCODE
    }
    Write-Log "published"

    # What actually landed. The manifest is the built site's own record, so this reports the
    # published state rather than what the script hoped it published.
    $newestDay = $null
    $newestCount = 0
    $manifestPath = Join-Path $RepoPath "docs\manifest.json"
    if (Test-Path $manifestPath) {
        try {
            $manifest = Get-Content -Path $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
            $last = $manifest.days[-1]
            $newestDay = $last.d
            $newestCount = $last.n
        }
        catch {
            Write-Log ("khong doc duoc manifest: {0}" -f $_.Exception.Message)
        }
    }

    $siteUrl = (Get-EnvValue "NEWSVAULT_SITE_URL")
    if (-not $siteUrl) { $siteUrl = "https://baronguyen001.github.io/news-vault" }
    $siteUrl = $siteUrl.TrimEnd("/")

    Send-Telegram (Format-RunMessage -Outcome "published" -Summary $buildSummary `
        -NewestDay $newestDay -NewestCount $newestCount -SiteUrl $siteUrl `
        -Stamp $runStamp -Mode $runMode)
}
