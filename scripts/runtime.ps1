param([ValidateSet('prepare','fetch','model')][string]$Action='prepare', [Parameter(Mandatory)][string]$AppPath)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
# Jenkins may inherit PSModulePath from a PowerShell 7 launcher. Windows
# PowerShell 5.1 must discover its own Utility, CimCmdlets and NetTCPIP modules.
if ($PSVersionTable.PSEdition -eq 'Desktop') {
    $env:PSModulePath="$PSHOME\Modules;$env:ProgramFiles\WindowsPowerShell\Modules;$env:USERPROFILE\Documents\WindowsPowerShell\Modules"
    Import-Module Microsoft.PowerShell.Utility -Force
}
$AppPath=(Resolve-Path -LiteralPath $AppPath).Path
$RuntimeHome=if ($env:NYC311_HOME) { [IO.Path]::GetFullPath($env:NYC311_HOME) } else { Join-Path $env:LOCALAPPDATA 'nyc311' }
$env:MONGO_URI='mongodb://127.0.0.1:27017'
if (!$env:MONGO_DB_NAME) { $env:MONGO_DB_NAME='nyc311_forecasting' }
if ($env:MONGO_DB_NAME -notmatch '^nyc311_[A-Za-z0-9_]+$') { throw 'Expected an explicitly named NYC311 database' }
$env:MODEL_ARTIFACT_DIR=Join-Path $RuntimeHome 'models'
$env:RUN_ARTIFACT_DIR=Join-Path $RuntimeHome 'runs'
$env:PYTHONUNBUFFERED='1'
if (!$env:CONFIG_PATH) { $env:CONFIG_PATH='config/production.json' }
$configFile=[IO.Path]::GetFullPath((Join-Path $AppPath $env:CONFIG_PATH))
if (!$configFile.StartsWith($AppPath+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Config must be inside the application checkout' }
if (!(Test-Path -LiteralPath $configFile -PathType Leaf)) { throw 'Missing application configuration' }
$dependencyHash=(Get-FileHash -LiteralPath (Join-Path $AppPath 'requirements.lock') -Algorithm SHA256).Hash.ToLower()
$venv=Join-Path $RuntimeHome "runtime\py312-$($dependencyHash.Substring(0,16))"
$RuntimePython=Join-Path $venv 'Scripts\python.exe'
$mutex=[Threading.Mutex]::new($false,'Local\NYC311-PythonRuntime')
$acquired=$false
try {
    try { $acquired=$mutex.WaitOne(600000) } catch [Threading.AbandonedMutexException] { $acquired=$true }
    if (!$acquired) { throw 'Timed out waiting for Python runtime setup' }
    $ready=Join-Path $venv '.ready'
    if (!(Test-Path -LiteralPath $ready)) {
        New-Item -ItemType Directory -Force -Path $venv | Out-Null
        $basePython=$env:PYTHON_BIN
        if (!$basePython) { $basePython=Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe' }
        if (Test-Path -LiteralPath $basePython) { & $basePython -m venv $venv }
        else { & py -3.12 -m venv $venv }
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 venv creation failed' }
        & $RuntimePython -m pip install --disable-pip-version-check -r (Join-Path $AppPath 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
        [IO.File]::WriteAllText($ready,$dependencyHash)
    }
} finally { if ($acquired) { $mutex.ReleaseMutex() }; $mutex.Dispose() }
if ($Action -ne 'prepare') {
    Push-Location -LiteralPath $AppPath
    try {
        $arguments=@('main_refresh.py',$Action,'--config',$env:CONFIG_PATH,'--output',"artifacts/refresh-$Action.json")
        if ($Action -eq 'model') {
            if ($env:TRAINING_POLICY) { $arguments+=@('--training-policy',$env:TRAINING_POLICY) }
            if ($env:RUN_ID) { $arguments+=@('--run-id',$env:RUN_ID) }
        }
        & $RuntimePython @arguments
        if ($LASTEXITCODE -ne 0) { throw "Application $Action failed with exit code $LASTEXITCODE" }
    } finally { Pop-Location }
}
