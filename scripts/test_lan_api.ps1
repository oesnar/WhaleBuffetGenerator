param(
    [string]$BaseUrl = "http://127.0.0.1:8765",
    [string]$RoomCode = $env:WBG_ROOM_CODE,
    [string]$PlayerName = "Curl Test Player"
)

if ([string]::IsNullOrWhiteSpace($RoomCode)) {
    throw "Pass -RoomCode or set the WBG_ROOM_CODE environment variable."
}

$BaseUrl = $BaseUrl.TrimEnd("/")
$RoomHeader = "X-Room-Code: $RoomCode"

Write-Host "Checking LAN session..."
& curl.exe --silent --show-error --fail-with-body --header $RoomHeader "$BaseUrl/session"
if ($LASTEXITCODE -ne 0) { throw "Session check failed with curl exit code $LASTEXITCODE." }
Write-Host ""

Write-Host "Fetching role choices..."
& curl.exe --silent --show-error --fail-with-body --header $RoomHeader "$BaseUrl/roles"
if ($LASTEXITCODE -ne 0) { throw "Role request failed with curl exit code $LASTEXITCODE." }
Write-Host ""

$Player = @{
    name = $PlayerName
    townsfolk = "Librarian"
    outsider = "Recluse"
    minion = "Baron"
    demon = "Imp"
} | ConvertTo-Json -Compress

Write-Host "Submitting sample player '$PlayerName'..."
$PlayerFile = [System.IO.Path]::GetTempFileName()
try {
    $Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($PlayerFile, $Player, $Utf8NoBom)
    & curl.exe --silent --show-error --fail-with-body `
        --header $RoomHeader `
        --header "Content-Type: application/json" `
        --data-binary "@$PlayerFile" `
        "$BaseUrl/player"
    if ($LASTEXITCODE -ne 0) { throw "Player submission failed with curl exit code $LASTEXITCODE." }
    Write-Host ""
    Write-Host "API smoke test completed. Re-running with the same player name will be rejected as a duplicate."
}
finally {
    Remove-Item -LiteralPath $PlayerFile -Force -ErrorAction SilentlyContinue
}
