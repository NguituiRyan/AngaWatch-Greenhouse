#!/usr/bin/env pwsh
# Windows-friendly task runner mirroring the Makefile targets.
#   ./make.ps1 dev    ./make.ps1 seed    ./make.ps1 demo    ./make.ps1 test
param([Parameter(Position = 0)][string]$Target = "help")

$ErrorActionPreference = "Stop"
$compose = "docker compose"

function Ensure-Env {
    if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "Created .env from .env.example" }
}

switch ($Target) {
    "help" {
        Write-Host "AngaWatch targets:" -ForegroundColor Cyan
        @(
            "env       Create .env from .env.example",
            "build     Build docker images",
            "up        Start full stack (detached)",
            "dev       Start full stack (foreground)",
            "down      Stop stack",
            "clean     Stop + remove volumes (DESTROYS DATA)",
            "migrate   Run DB migrations",
            "seed      Seed demo data",
            "simulate  Run device simulator",
            "demo      Run scripted demo",
            "test      Run backend tests",
            "lint      Ruff + Black check",
            "logs      Tail logs"
        ) | ForEach-Object { Write-Host "  $_" }
    }
    "env"      { Ensure-Env }
    "build"    { iex "$compose build" }
    "up"       { Ensure-Env; iex "$compose up -d" }
    "dev"      { Ensure-Env; iex "$compose up --build" }
    "down"     { iex "$compose down" }
    "clean"    { iex "$compose down -v" }
    "migrate"  { iex "$compose run --rm migrate" }
    "seed"     { iex "$compose exec backend python -m app.seed.seed" }
    "simulate" { iex "$compose --profile sim up simulator" }
    "demo"     { Ensure-Env; iex "$compose up -d"; iex "$compose exec backend python -m app.seed.seed"; iex "$compose exec backend python -m app.seed.demo" }
    "test"     { iex "$compose run --rm backend pytest -q" }
    "lint"     { Push-Location backend; ruff check .; black --check .; Pop-Location }
    "fmt"      { Push-Location backend; ruff check --fix .; black .; Pop-Location }
    "logs"     { iex "$compose logs -f --tail=100" }
    default    { Write-Host "Unknown target '$Target'. Run ./make.ps1 help" -ForegroundColor Red; exit 1 }
}
