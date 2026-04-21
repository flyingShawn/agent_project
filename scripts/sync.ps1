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

        Write-Host "Ensuring qdrant and backend containers are running..." -ForegroundColor Cyan
        & docker compose up -d qdrant backend
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose up -d qdrant backend failed."
        }

        Write-Host "Running sync inside backend container..." -ForegroundColor Cyan
        & docker compose exec backend python scripts/sync_rag.py --target $target --mode $mode
        exit $LASTEXITCODE
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
