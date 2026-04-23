param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"

$action = "run"
$runner = "local"
$baseUrl = if ($env:OPS_REPORT_BASE_URL) { $env:OPS_REPORT_BASE_URL.Trim() } else { "http://localhost:8000" }

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")

$actionAliases = @{
    "run" = "run"
    "latest" = "latest"
    "last" = "latest"
    "list" = "list"
}

$runnerAliases = @{
    "local" = "local"
    "docker" = "docker"
}

function Show-Usage {
    Write-Host "Usage:" -ForegroundColor Cyan
    Write-Host "  .\scripts\ops_report.cmd" -ForegroundColor Yellow
    Write-Host "  .\scripts\ops_report.cmd docker" -ForegroundColor Yellow
    Write-Host "  .\scripts\ops_report.cmd latest" -ForegroundColor Yellow
    Write-Host "  .\scripts\ops_report.cmd list" -ForegroundColor Yellow
    Write-Host "  .\scripts\ops_report.cmd run http://192.168.1.149:8000" -ForegroundColor Yellow
    Write-Host "  .\scripts\ops_report_docker.cmd" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Notes:" -ForegroundColor Cyan
    Write-Host "  default action: run"
    Write-Host "  default runner: local"
    Write-Host "  default base url: http://localhost:8000"
    Write-Host "  optional env: OPS_REPORT_BASE_URL"
}

foreach ($arg in $CliArgs) {
    $normalized = $arg.ToLowerInvariant()

    if ($normalized -in @("help", "-h", "--help", "/?")) {
        Show-Usage
        exit 0
    }

    if ($actionAliases.ContainsKey($normalized)) {
        $action = $actionAliases[$normalized]
        continue
    }

    if ($runnerAliases.ContainsKey($normalized)) {
        $runner = $runnerAliases[$normalized]
        continue
    }

    if ($arg -match "^https?://") {
        $baseUrl = $arg.Trim()
        continue
    }

    throw "Unsupported arg: $arg"
}

$baseUrl = $baseUrl.TrimEnd("/")

switch ($action) {
    "run" {
        $method = "POST"
        $path = "/api/v1/ops/reports/run"
    }
    "latest" {
        $method = "GET"
        $path = "/api/v1/ops/reports/latest"
    }
    "list" {
        $method = "GET"
        $path = "/api/v1/ops/reports"
    }
    default {
        throw "Unsupported action: $action"
    }
}

$uri = "$baseUrl$path"

if ($runner -eq "docker") {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "docker command not found. Install/start Docker Desktop first."
    }

    $pythonCode = @"
import json
import urllib.request

url = "http://localhost:8000$path"
data = None
headers = {}
if "$method" == "POST":
    data = b"{}"
    headers["Content-Type"] = "application/json"

request = urllib.request.Request(url, data=data, headers=headers, method="$method")
with urllib.request.urlopen(request) as response:
    print(response.read().decode("utf-8", "replace"))
"@

    Write-Host "$method docker://backend$path" -ForegroundColor Green
    Push-Location $projectRoot
    try {
        Write-Host "Ensuring backend container is running..." -ForegroundColor Cyan
        & docker compose up -d backend
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose up -d backend failed."
        }

        & docker compose exec -T backend python -c $pythonCode
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}

Write-Host "$method $uri" -ForegroundColor Green

try {
    if ($method -eq "POST") {
        $result = Invoke-RestMethod -Method $method -Uri $uri -ContentType "application/json"
    } else {
        $result = Invoke-RestMethod -Method $method -Uri $uri
    }

    if ($null -ne $result) {
        $result | ConvertTo-Json -Depth 10
    }
}
catch {
    $message = $_.Exception.Message
    if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
        $message = $_.ErrorDetails.Message
    }
    Write-Error "Request failed: $message"
    exit 1
}
