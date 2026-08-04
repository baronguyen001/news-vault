# run_daily.ps1 - build today's pages and publish them.
#
# Runs AFTER the news-hunter daily job, so the database already holds today's articles.
# Register with Task Scheduler and QUOTE the executable path: an unquoted path with a space
# fails as 0x800700C1 and the task then dies silently every night.
#
#   schtasks /Create /TN "NewsVault\Daily" /SC DAILY /ST 18:30 ^
#     /TR "\"C:\Program Files\PowerShell\7\pwsh.exe\" -NoProfile -File \"E:\news-vault\scripts\run_daily.ps1\""

[CmdletBinding()]
param(
    # A pipeline expression is not legal in a parameter default - it is a parse error,
    # which would kill this script every night before it printed anything. Resolve below.
    [string]$RepoPath,
    [switch]$NoPush,
    [switch]$Backfill
)

$ErrorActionPreference = "Stop"
if (-not $RepoPath) { $RepoPath = Split-Path -Parent $PSScriptRoot }
Set-Location $RepoPath

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

Write-Log "build start (backfill=$Backfill)"

$buildArgs = @("-m", "newsvault.cli", "build")
if ($Backfill) { $buildArgs += "--backfill" }

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
