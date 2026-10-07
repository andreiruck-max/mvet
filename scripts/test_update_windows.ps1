# Simulate command boundaries without a Docker daemon or production database.
$ErrorActionPreference = 'Stop'
$updater = Join-Path $PSScriptRoot 'update_windows.ps1'
$originalDirectory = Get-Location
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('mvet-update-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $testRoot | Out-Null
Set-Content -LiteralPath (Join-Path $testRoot '.env') -Value '# fixture, no secrets'
$script:calls = [Collections.Generic.List[string]]::new()
$script:failRestore = $false
function git {
    $global:LASTEXITCODE = 0
    $script:calls.Add('git ' + ($args -join ' '))
    if (($args -join ' ') -eq 'branch --show-current') { 'main' }
}
function docker {
    $global:LASTEXITCODE = 0
    $line = $args -join ' '
    $script:calls.Add('docker ' + $line)
    if ($line -like 'compose cp *') { [IO.File]::WriteAllText($args[-1], 'isolated backup fixture') }
    if ($script:failRestore -and $line -match 'pg_restore') { $global:LASTEXITCODE = 1 }
}
try {
    & $updater -ProjectPath $testRoot -BackupPath (Join-Path $testRoot 'backups')
    $restore = $script:calls.FindIndex({ param($line) $line -match 'pg_restore' })
    $migration = $script:calls.FindIndex({ param($line) $line -match 'manage.py migrate' })
    if ($restore -lt 0 -or $migration -le $restore) { throw 'Migration ran before backup verification.' }
    if (!$script:calls.Exists({ param($line) $line -match '127.0.0.1:8000/entrar/' })) { throw 'Missing startup verification.' }
    $script:calls.Clear();$script:failRestore = $true;$failed = $false
    try { & $updater -ProjectPath $testRoot -BackupPath (Join-Path $testRoot 'backups') } catch { $failed = $true }
    if (!$failed) { throw 'Failed restore must stop the update.' }
    if ($script:calls.Exists({ param($line) $line -match 'manage.py migrate' })) { throw 'Migration ran after failed backup.' }
    if (!$script:calls.Contains('docker compose start web')) { throw 'Previous container was not restarted.' }
    if (!$script:calls.Exists({ param($line) $line -match 'dropdb' })) { throw 'Test database was not cleaned up.' }
    Write-Host 'Update workflow: successful backup and failed restore paths passed.'
} finally {
    Set-Location $originalDirectory
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}
