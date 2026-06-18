# AngaWatch Greenhouse — developer task runner.
# Windows users without `make`: use ./make.ps1 <target> (same targets).
.DEFAULT_GOAL := help
COMPOSE := docker compose

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.PHONY: env
env: ## Create .env from .env.example if missing
	@test -f .env || cp .env.example .env

.PHONY: build
build: ## Build all docker images
	$(COMPOSE) build

.PHONY: up
up: env ## Start the full stack (infra + backend + workers + ingestion + web)
	$(COMPOSE) up -d

.PHONY: dev
dev: env ## Bring the whole stack up (foreground logs)
	$(COMPOSE) up --build

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop the stack and remove volumes (DESTROYS DB DATA)
	$(COMPOSE) down -v

.PHONY: migrate
migrate: ## Run DB migrations
	$(COMPOSE) run --rm migrate

.PHONY: seed
seed: ## Seed demo org/farm/greenhouse/tomato cycle + history
	$(COMPOSE) exec backend python -m app.seed.seed

.PHONY: simulate
simulate: ## Run the device simulator (SIM_SCENARIO from .env)
	$(COMPOSE) --profile sim up simulator

.PHONY: demo
demo: ## Run the full scripted hackathon demo (seed + blight scenario + alert)
	$(COMPOSE) up -d
	$(COMPOSE) exec backend python -m app.seed.seed
	$(COMPOSE) exec backend python -m app.seed.demo

.PHONY: test
test: ## Run backend tests
	$(COMPOSE) run --rm backend pytest -q

.PHONY: test-local
test-local: ## Run backend tests against a local venv (no docker)
	cd backend && pytest -q

.PHONY: lint
lint: ## Ruff + Black check
	cd backend && ruff check . && black --check .

.PHONY: fmt
fmt: ## Auto-format backend
	cd backend && ruff check --fix . && black .

.PHONY: logs
logs: ## Tail all logs
	$(COMPOSE) logs -f --tail=100

.PHONY: psql
psql: ## Open a psql shell
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-angawatch} -d $${POSTGRES_DB:-angawatch}
