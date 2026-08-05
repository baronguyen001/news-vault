$env:NEWSVAULT_SOURCING_ONLY = "1"
try {
    . (Join-Path $PSScriptRoot "run_daily.ps1")
}
finally {
    Remove-Item Env:NEWSVAULT_SOURCING_ONLY -ErrorAction SilentlyContinue
}

$passed = 0
$failed = 0

# Report through Write-Host, not Write-Output: whatever a PowerShell function writes to
# the SUCCESS stream becomes part of its return value, so `$passed += Assert-Contains ...`
# was adding an array to an integer and failing with op_Addition.
function Assert-Contains([string]$name, [string]$text, [string]$expected) {
    if ($text.Contains($expected)) {
        Write-Host "PASS $name"
        return 1
    }
    Write-Host "FAIL $name"
    return 0
}

function Assert-NotContains([string]$name, [string]$text, [string]$unexpected) {
    if (-not $text.Contains($unexpected)) {
        Write-Host "PASS $name"
        return 1
    }
    Write-Host "FAIL $name"
    return 0
}

$published = Format-RunMessage -Outcome "published" `
    -Summary "1 ngày dựng: 28 tin" `
    -NewestDay "2026-08-05" `
    -NewestCount 28 `
    -SiteUrl "https://example.test/news-vault" `
    -Stamp "14:00" `
    -Mode "đầy đủ"

$nochange = Format-RunMessage -Outcome "nochange" `
    -Summary "1 ngày dựng: 0 tin" `
    -Stamp "21:15" `
    -Mode "chỉ hôm nay"

$buildfail = Format-RunMessage -Outcome "buildfail" `
    -ExitCode 3 `
    -Stamp "14:00" `
    -Mode "đầy đủ"

$pushfail = Format-RunMessage -Outcome "pushfail" `
    -ExitCode 128 `
    -Stamp "21:15" `
    -Mode "đầy đủ"

$passed += Assert-Contains "published emoji" $published "📰"
$passed += Assert-Contains "published date" $published "05/08/2026"
$passed += Assert-Contains "published count" $published "28 tin"
$passed += Assert-Contains "published summary" $published "1 ngày dựng: 28 tin"
$passed += Assert-Contains "published url" $published "https://example.test/news-vault/d/2026-08-05/"
$passed += Assert-Contains "published stamp" $published "🕒 14:00 · đầy đủ"
$passed += Assert-Contains "nochange emoji" $nochange "✅"
$passed += Assert-Contains "nochange phrase" $nochange "không có tin mới"
$passed += Assert-Contains "nochange summary" $nochange "1 ngày dựng: 0 tin"
$passed += Assert-Contains "nochange stamp" $nochange "🕒 21:15 · chỉ hôm nay"
$passed += Assert-Contains "buildfail marker" $buildfail "❌"
$passed += Assert-Contains "buildfail outcome" $buildfail "BUILD HỎNG"
$passed += Assert-Contains "buildfail exit" $buildfail "exit 3"
$passed += Assert-Contains "pushfail marker" $pushfail "❌"
$passed += Assert-Contains "pushfail outcome" $pushfail "PUSH HỎNG"
$passed += Assert-Contains "pushfail exit" $pushfail "exit 128"
$passed += Assert-NotContains "published is not nochange" $published "không có tin mới"
$passed += Assert-NotContains "nochange has no day link" $nochange "/d/"

$failed = 18 - $passed
if ($failed -gt 0) {
    exit 1
}

# Send-Telegram's dry-run branch, which the message tests above never touch. It shipped
# with "{text}" where -f wants "{0}", so it threw "Input string was not in a correct
# format" and, under ErrorActionPreference=Stop, killed the run AFTER a good build.
$script:capturedLog = @()
function Write-Log([string]$message) { $script:capturedLog += $message }
$DryRunNotify = $true
$tgToken = "unused"
$tgChat = "unused"

Send-Telegram "dòng một`ndòng hai"
$logged = ($script:capturedLog -join "`n")
$passed += Assert-Contains "dry-run logs instead of sending" $logged "TELEGRAM (dry-run):"
$passed += Assert-Contains "dry-run keeps the message body" $logged "dòng hai"

Write-Host ""
Write-Host ("{0} passed, {1} failed" -f $passed, $failed)
if ($failed -gt 0) { exit 1 }
exit 0
