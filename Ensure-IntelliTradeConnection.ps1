$ErrorActionPreference = 'Stop'
try {
    $health = Invoke-RestMethod 'http://127.0.0.1:8100/api/health' -TimeoutSec 5
    if ($health.app -ne 'IntelliTrade') { throw 'Unexpected backend identity.' }
    $account = Invoke-RestMethod 'http://127.0.0.1:8100/api/account/info' -TimeoutSec 5
    if ($account.active_account -ne 'DEMO' -or $account.allow_live -ne $false) {
        throw 'Automatic launcher recovery requires DEMO mode with live trading disabled.'
    }
    if (-not $health.mt5.connected) {
        Write-Host 'Backend is running but MT5 is disconnected. Reconnecting configured DEMO terminal...'
        $result = Invoke-RestMethod 'http://127.0.0.1:8100/api/account/switch' -Method Post -ContentType 'application/json' -Body '{"target":"DEMO"}' -TimeoutSec 110
        if (-not $result.ok) { throw 'MT5 reconnect failed. Check the configured terminal login and backend log.' }
    }
    $health = Invoke-RestMethod 'http://127.0.0.1:8100/api/health' -TimeoutSec 5
    if (-not $health.mt5.connected -or $health.mt5.verified_type -ne 'DEMO') {
        throw 'Backend is available, but MT5 DEMO connection is not verified.'
    }
    Write-Host 'Backend and MT5 DEMO connection verified.'
    exit 0
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message)
    exit 1
}
