param([Parameter(Mandatory)][string]$AppPath)
$ErrorActionPreference='Stop'
. "$PSScriptRoot\runtime.ps1" -Action prepare -AppPath $AppPath
$commit=(& git -C $AppPath rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[a-f0-9]{40}$') { throw 'Cannot determine application revision' }
$frontHome=Join-Path $RuntimeHome 'front'
$release=Join-Path $frontHome "releases\$commit"
$statePath=Join-Path $frontHome 'process.json'
New-Item -ItemType Directory -Force -Path $release | Out-Null
foreach ($relative in (& git -C $AppPath ls-files)) {
    $destination=[IO.Path]::GetFullPath((Join-Path $release $relative))
    if (!$destination.StartsWith($release+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe release path' }
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($destination)) | Out-Null
    Copy-Item -LiteralPath (Join-Path $AppPath $relative) -Destination $destination -Force
}
$scriptPath=Join-Path $release 'presentation\app.py'
$port=30130
function Get-Listener { return ,@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) }
function Assert-Owned($record) {
    $process=Get-CimInstance Win32_Process -Filter "ProcessId=$($record.pid)"
    if (!$process) { return $null }
    if ($process.CreationDate.ToUniversalTime().ToString('o') -ne $record.created_at -or
        $process.ExecutablePath -ne $record.executable -or !$process.CommandLine.Contains($record.script)) {
        throw 'PID ownership changed; refusing to stop an unrelated process'
    }
    return $process
}
$state=$null
if (Test-Path -LiteralPath $statePath) { $state=Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json }
$listener=Get-Listener
$same=$false
if ($listener.Count) {
    if (!$state -or $listener.Count -ne 1 -or $listener[0].OwningProcess -ne $state.listener.pid) {
        throw 'Port 30130 is owned by an unmanaged service; no process was stopped'
    }
    $null=Assert-Owned $state.listener
    $same=$state.commit -eq $commit -and $state.database -eq $env:MONGO_DB_NAME
    if (!$same) {
        foreach ($record in @($state.listener,$state.launcher)) {
            $owned=Assert-Owned $record
            if ($owned) { Stop-Process -Id $owned.ProcessId -ErrorAction Stop }
        }
        for ($i=0; $i -lt 15 -and (Get-Listener).Count; $i++) { Start-Sleep -Seconds 1 }
        if ((Get-Listener).Count) { throw 'Previous frontend did not release its port' }
    }
}
if (!$same) {
    $env:JENKINS_NODE_COOKIE='nyc311-frontend-service'
    $arguments=@(('"'+$scriptPath+'"'),'--config',('"'+(Join-Path $release $env:CONFIG_PATH)+'"'),'--port',"$port")
    $launcher=Start-Process -FilePath $RuntimePython -ArgumentList $arguments -WorkingDirectory $release -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $frontHome 'stdout.log') -RedirectStandardError (Join-Path $frontHome 'stderr.log') -PassThru
    for ($i=0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        $listener=Get-Listener
        if ($listener.Count) { break }
        if ($launcher.HasExited) { throw 'Frontend exited; inspect persistent stderr.log' }
    }
    if ($listener.Count -ne 1 -or $listener[0].LocalAddress -ne '127.0.0.1') { throw 'Expected one loopback frontend listener' }
    function Record-Process([int]$processId) {
        $process=Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
        if (!$process -or !$process.CommandLine.Contains($scriptPath)) { throw 'Unexpected frontend process identity' }
        return @{pid=$processId;created_at=$process.CreationDate.ToUniversalTime().ToString('o');executable=$process.ExecutablePath;script=$scriptPath}
    }
    $state=@{commit=$commit;database=$env:MONGO_DB_NAME;listener=(Record-Process $listener[0].OwningProcess);launcher=(Record-Process $launcher.Id)}
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8
}
$health=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/health" -TimeoutSec 10
if ($health.StatusCode -ne 200) { throw 'Frontend healthcheck failed' }
$query=if ($env:EXPECTED_RUN_ID) { '?run_id='+[Uri]::EscapeDataString($env:EXPECTED_RUN_ID) } else { '?limit=1' }
$results=Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/prediction-results$query" -TimeoutSec 20
if (!$results) { throw 'Expected completed prediction is not visible' }
$result=@($results)[0]
if (!$result.forecasts.Count -or $result.forecasts.Count -ne $result.diagnostics.Count) { throw 'Forecast/diagnostic coverage mismatch' }
$report=@{status='healthy';url="http://127.0.0.1:$port";commit=$commit;run_id=$result.run_id;forecasts=$result.forecasts.Count;diagnostics=$result.diagnostics.Count;already_running=$same;listener_pid=$state.listener.pid}
New-Item -ItemType Directory -Force -Path 'artifacts' | Out-Null
$report | ConvertTo-Json | Set-Content -LiteralPath 'artifacts/frontend.json' -Encoding UTF8
$report | ConvertTo-Json | Write-Output
