# Simulate command boundaries without a Docker daemon or production database.
$ErrorActionPreference = 'Stop'
$updater = Join-Path $PSScriptRoot 'update_windows.ps1'
$originalDirectory = Get-Location
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('mvet-update-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $testRoot | Out-Null
Set-Content -LiteralPath (Join-Path $testRoot '.env') -Value '# fixture, no secrets'
$global:mvetTestCalls = [Collections.Generic.List[string]]::new()
$global:mvetTestFailRestore = $false
$global:mvetTestProbeCount = 0
$global:mvetTestShell = (Get-Process -Id $PID).Path
function git {
    $global:LASTEXITCODE = 0
    $global:mvetTestCalls.Add('git ' + ($args -join ' '))
    if (($args -join ' ') -eq 'branch --show-current') { 'main' }
}
function docker {
    $global:LASTEXITCODE = 0
    $line = $args -join ' '
    $global:mvetTestCalls.Add('docker ' + $line)
    if ($line -like 'compose cp *') { [IO.File]::WriteAllText($args[-1], 'isolated backup fixture') }
    if ($global:mvetTestFailRestore -and $line -match 'pg_restore') { $global:LASTEXITCODE = 1 }
    if ($line -like 'compose exec -T web python -c *') {
        $global:mvetTestProbeCount++
        if ($global:mvetTestProbeCount -eq 1) {
            & $global:mvetTestShell -NoProfile -Command "[Console]::Error.WriteLine('container starting'); exit 1"
            $global:LASTEXITCODE = 1
        }
    }
}
try {
    & $updater -ProjectPath $testRoot -BackupPath (Join-Path $testRoot 'backups')
    $restore = $global:mvetTestCalls.FindIndex({ param($line) $line -match 'pg_restore' })
    $migration = $global:mvetTestCalls.FindIndex({ param($line) $line -match 'manage.py migrate' })
    if ($restore -lt 0 -or $migration -le $restore) { throw 'Migration ran before backup verification.' }
    if (!$global:mvetTestCalls.Exists({ param($line) $line -match '127.0.0.1:8000/entrar/' })) { throw 'Missing startup verification.' }
    if ($global:mvetTestProbeCount -ne 2) { throw 'Native stderr must trigger a retry, not abort the update.' }
    $global:mvetTestCalls.Clear();$global:mvetTestFailRestore = $true;$failed = $false
    try { & $updater -ProjectPath $testRoot -BackupPath (Join-Path $testRoot 'backups') } catch { $failed = $true }
    if (!$failed) { throw 'Failed restore must stop the update.' }
    if ($global:mvetTestCalls.Exists({ param($line) $line -match 'manage.py migrate' })) { throw 'Migration ran after failed backup.' }
    if (!$global:mvetTestCalls.Contains('docker compose start web')) { throw 'Previous container was not restarted.' }
    if (!$global:mvetTestCalls.Exists({ param($line) $line -match 'dropdb' })) { throw 'Test database was not cleaned up.' }
    Write-Host 'Update workflow: successful backup and failed restore paths passed.'
} finally {
    Set-Location $originalDirectory
    Remove-Item -LiteralPath $testRoot -Recurse -Force
    Remove-Variable -Name mvetTestCalls, mvetTestFailRestore, mvetTestProbeCount, mvetTestShell -Scope Global
}
