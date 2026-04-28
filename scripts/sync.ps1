param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")

$mode = "incremental"
$target = "all"
$runner = "docker"

$modeAliases = @{
    "inc" = "incremental"
    "incremental" = "incremental"
    "full" = "full"
}

$targetAliases = @{
    "all" = "all"
    "docs" = "docs"
    "doc" = "docs"
    "sql" = "sql"
}

$runnerAliases = @{
    "docker" = "docker"
    "local" = "local"
}

function Show-Usage {
    Write-Host "Usage:" -ForegroundColor Cyan
    Write-Host "  .\scripts\sync.cmd" -ForegroundColor Yellow
    Write-Host "  .\scripts\sync.cmd inc" -ForegroundColor Yellow
    Write-Host "  .\scripts\sync.cmd sql full" -ForegroundColor Yellow
    Write-Host "  .\scripts\sync.cmd docs inc local" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Args:" -ForegroundColor Cyan
    Write-Host "  mode: inc | incremental | full"
    Write-Host "  target: all | docs | sql"
    Write-Host "  runner: docker | local"
    Write-Host ""
    Write-Host "Defaults:" -ForegroundColor Cyan
    Write-Host "  mode=incremental, target=all, runner=docker"
    Write-Host ""
    Write-Host "Note:" -ForegroundColor Cyan
    Write-Host "  Docker mode docs sync now uses docling-sync container (supports Office/PDF)."
    Write-Host "  Docker mode sql sync still uses backend container."
}

foreach ($arg in $CliArgs) {
    $normalized = $arg.ToLowerInvariant()
    if ($normalized -in @("help", "-h", "--help", "/?")) {
        Show-Usage
        exit 0
    }
    if ($modeAliases.ContainsKey($normalized)) {
        $mode = $modeAliases[$normalized]
        continue
    }
    if ($targetAliases.ContainsKey($normalized)) {
        $target = $targetAliases[$normalized]
        continue
    }
    if ($runnerAliases.ContainsKey($normalized)) {
        $runner = $runnerAliases[$normalized]
        continue
    }

    Write-Error "Unsupported arg: $arg"
}

Write-Host "target=$target | mode=$mode | runner=$runner" -ForegroundColor Green

Push-Location $projectRoot
try {
    if ($runner -eq "docker") {
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            throw "docker command not found. Install/start Docker Desktop or use local runner."
        }

        # Determine which containers to use based on target
        # docs  -> docling-sync (has docling for Office/PDF parsing)
        # sql   -> backend (no docling needed)
        # all   -> both
        $needsDocling = $target -in @("docs", "all")
        $needsBackend = $target -in @("sql", "all")

        if ($needsDocling) {
            Write-Host "Ensuring qdrant container is running..." -ForegroundColor Cyan
            & docker compose up -d qdrant
            if ($LASTEXITCODE -ne 0) {
                throw "docker compose up -d qdrant failed."
            }

            $previousSyncTarget = $env:SYNC_TARGET
            $previousSyncMode = $env:SYNC_MODE
            $previousRequireDocling = $env:RAG_REQUIRE_DOCLING
            $env:SYNC_TARGET = "docs"
            $env:SYNC_MODE = $mode
            $env:RAG_REQUIRE_DOCLING = "1"

            Write-Host "Building and running docling-sync container for docs sync..." -ForegroundColor Cyan
            try {
                & docker compose --profile docling up docling-sync --build --force-recreate
                if ($LASTEXITCODE -ne 0) {
                    throw "docling-sync failed."
                }

                $doclingExitCode = (& docker inspect agent-docling-sync --format "{{.State.ExitCode}}").Trim()
                if ($doclingExitCode -ne "0") {
                    throw "docling-sync exited with code $doclingExitCode. If docling import failed, rebuild it with: powershell -ExecutionPolicy Bypass -File docker/build-docling-sync.ps1"
                }
            }
            finally {
                if ($null -eq $previousSyncTarget) { Remove-Item Env:SYNC_TARGET -ErrorAction SilentlyContinue } else { $env:SYNC_TARGET = $previousSyncTarget }
                if ($null -eq $previousSyncMode) { Remove-Item Env:SYNC_MODE -ErrorAction SilentlyContinue } else { $env:SYNC_MODE = $previousSyncMode }
                if ($null -eq $previousRequireDocling) { Remove-Item Env:RAG_REQUIRE_DOCLING -ErrorAction SilentlyContinue } else { $env:RAG_REQUIRE_DOCLING = $previousRequireDocling }
            }
        }

        if ($needsBackend) {
            Write-Host "Ensuring qdrant and backend containers are running..." -ForegroundColor Cyan
            & docker compose up -d qdrant backend
            if ($LASTEXITCODE -ne 0) {
                throw "docker compose up -d qdrant backend failed."
            }

            Write-Host "Running SQL sync inside backend container..." -ForegroundColor Cyan
            & docker compose exec backend python scripts/sync_rag.py --target sql --mode $mode
            if ($LASTEXITCODE -ne 0) {
                throw "SQL sync failed."
            }
        }

        exit 0
    }

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "python command not found. Install Python or use docker runner."
    }

    Write-Host "Running sync in local Python environment..." -ForegroundColor Cyan
    & python scripts/sync.py $target $mode
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
