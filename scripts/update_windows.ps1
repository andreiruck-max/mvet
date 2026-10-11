param([string]$ProjectPath = 'C:\Mercadovet\mvet', [string]$BackupPath = 'C:\Mercadovet\backups')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Run([string]$Command, [string[]]$Arguments) {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Falha em $Command (codigo $LASTEXITCODE). Atualizacao interrompida." }
}

Set-Location -LiteralPath $ProjectPath
Run docker @('info', '--format', '{{.ServerVersion}}')
$branch = Run git @('branch', '--show-current')
if ($branch -ne 'main') { throw 'O projeto precisa estar na branch main. Nenhuma troca automatica foi feita.' }
if (!(Test-Path -LiteralPath '.env')) { throw 'Arquivo .env nao encontrado.' }
Run git @('fetch', 'origin')
Run git @('merge-base', '--is-ancestor', 'HEAD', 'origin/main')
$changed = @(Run git @('diff', '--name-only', 'HEAD'))
$allowed = @('scripts/backup.sh', 'scripts/test_restore.sh')
if (@($changed | Where-Object { $_ -notin $allowed }).Count -gt 0) {
    throw 'Ha alteracoes locais de codigo. Elas foram preservadas. Envie git status --short para revisao antes de atualizar.'
}
if (@(Run git @('ls-files', '--others', '--exclude-standard')).Count -gt 0) {
    throw 'Ha arquivos locais nao versionados. Foram preservados; revise git status --short antes de atualizar.'
}
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
New-Item -ItemType Directory -Force -Path $BackupPath | Out-Null
$backupFile = Join-Path $BackupPath "mvet_antes_atualizacao_$stamp.dump"
$savedScripts = $null
try {
    if ($changed.Count -gt 0) {
        Run git @('stash', 'push', '-m', "mvet-backup-scripts-$stamp", '--', 'scripts/backup.sh', 'scripts/test_restore.sh')
        $savedScripts = Run git @('rev-parse', 'stash@{0}')
    }
    Run git @('merge', '--ff-only', 'origin/main')
} finally {
    if ($savedScripts) {
        Run git @('stash', 'apply', '--index', $savedScripts)
        Write-Host "Scripts locais restaurados; copia adicional preservada no stash $savedScripts."
    }
}

# Build while the previous container is still serving. Do not recreate the database.
Run docker @('compose', 'build', 'web')
$webStopped = $false
$newWebStarted = $false
try {
    Run docker @('compose', 'stop', 'web')
    $webStopped = $true
    Run docker @('compose', 'exec', '-T', 'db', 'sh', '-c', 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f /tmp/mvet_before_update.dump')
    Run docker @('compose', 'cp', 'db:/tmp/mvet_before_update.dump', $backupFile)
    if ((Get-Item -LiteralPath $backupFile).Length -eq 0) { throw 'Backup vazio. Nenhuma migration executada.' }

    # Restore into an isolated database before touching the application schema.
    $testDb = "mvet_update_test_$stamp"
    $testCreated = $false
    try {
        Run docker @('compose', 'exec', '-T', 'db', 'sh', '-c', 'createdb -U $POSTGRES_USER $1', 'sh', $testDb)
        $testCreated = $true
        Run docker @('compose', 'exec', '-T', 'db', 'sh', '-c', 'pg_restore --exit-on-error --no-owner --no-privileges -U $POSTGRES_USER -d $1 /tmp/mvet_before_update.dump', 'sh', $testDb)
    } finally {
        if ($testCreated) { Run docker @('compose', 'exec', '-T', 'db', 'sh', '-c', 'dropdb -U $POSTGRES_USER $1', 'sh', $testDb) }
    }
    Write-Host "Backup restaurado e conferido: $backupFile"
    Get-FileHash -LiteralPath $backupFile -Algorithm SHA256 | Format-List
    Run docker @('compose', 'run', '--rm', '--no-deps', 'web', 'python', 'manage.py', 'migrate', '--noinput')
    Run docker @('compose', 'run', '--rm', '--no-deps', 'web', 'python', 'manage.py', 'install_mercadovet_chart')
    Run docker @('compose', 'run', '--rm', '--no-deps', 'web', 'python', 'manage.py', 'check')
    Run docker @('compose', 'up', '-d', '--no-deps', 'web')
    $newWebStarted = $true
    $ready = $false
    $probeOutput = @()
    for ($attempt = 0; $attempt -lt 12; $attempt++) {
        $healthCheck = "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/entrar/', timeout=5).read()"
        # Windows PowerShell 5.1 turns native stderr into ErrorRecords. A startup
        # probe may fail normally; only its exit code decides whether to retry.
        $previousPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $probeOutput = @(& docker compose exec -T web python -c $healthCheck 2>&1)
            $probeExitCode = $LASTEXITCODE
        } finally { $ErrorActionPreference = $previousPreference }
        if ($probeExitCode -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 3
    }
    if (!$ready) {
        Write-Warning ($probeOutput -join [Environment]::NewLine)
        throw 'Aplicacao nao respondeu. Confira docker compose logs --tail=60 web; o backup foi preservado.'
    }
    Run docker @('compose', 'ps')
    Write-Host "MVet atualizado. Backup: $backupFile"
    Write-Host 'Abra o endereco habitual do MVet e atualize o navegador com Ctrl+F5.'
} catch {
    if ($webStopped -and !$newWebStarted) {
        & docker compose start web
        Write-Warning 'Tentativa de reiniciar o container existente. Nenhum banco foi restaurado por cima do original.'
    }
    Write-Warning "Atualizacao nao concluida. Backup, se gerado: $backupFile. Envie o erro antes de repetir."
    throw
}
