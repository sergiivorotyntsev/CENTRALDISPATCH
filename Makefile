.PHONY: help setup setup-python setup-web setup-e2e dev dev-api dev-web lint lint-python lint-web format test test-python test-e2e build build-web check clean security

# Default target
help:
	@echo "Central Dispatch - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup        - Install all dependencies (Python + Node)"
	@echo "  make setup-python - Install Python dependencies only"
	@echo "  make setup-web    - Install frontend dependencies only"
	@echo "  make setup-e2e    - Install E2E test dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make dev          - Start API server (port 8000)"
	@echo "  make dev-api      - Start API server with reload"
	@echo "  make dev-web      - Start frontend dev server"
	@echo ""
	@echo "Quality:"
	@echo "  make lint         - Run all linters"
	@echo "  make lint-python  - Run Python linters (ruff)"
	@echo "  make format       - Format code (ruff)"
	@echo "  make test         - Run all tests"
	@echo "  make test-python  - Run Python tests (pytest)"
	@echo "  make test-e2e     - Run E2E tests (Playwright)"
	@echo "  make check        - Run lint + test"
	@echo "  make security     - Run security scans"
	@echo ""
	@echo "Build:"
	@echo "  make build        - Build for production"
	@echo "  make build-web    - Build frontend only"
	@echo "  make clean        - Remove build artifacts"

# =============================================================================
# Setup
# =============================================================================

setup: setup-python setup-web
	@echo "✓ Setup complete"

setup-python:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	pip install ruff mypy bandit pip-audit
	@echo "✓ Python dependencies installed"

setup-web:
	@echo "Installing frontend dependencies..."
	cd web && npm install
	@echo "✓ Frontend dependencies installed"

setup-e2e:
	@echo "Installing E2E test dependencies..."
	cd e2e && npm install && npx playwright install --with-deps chromium
	@echo "✓ E2E dependencies installed"

# =============================================================================
# Development
# =============================================================================

dev: dev-api

dev-api:
	uvicorn api.main:app --reload --port 8000

dev-web:
	cd web && npm run dev

# =============================================================================
# Linting & Formatting
# =============================================================================

lint: lint-python
	@echo "✓ All linting passed"

lint-python:
	@echo "Running ruff linter..."
	ruff check . --fix
	@echo "Running ruff formatter check..."
	ruff format --check .

format:
	@echo "Formatting Python code..."
	ruff format .
	ruff check . --fix
	@echo "✓ Code formatted"

# =============================================================================
# Testing
# =============================================================================

test: test-python
	@echo "✓ All tests passed"

test-python:
	@echo "Running Python tests..."
	pytest tests/ -v --tb=short

test-e2e:
	@echo "Running E2E tests..."
	cd e2e && npm test

test-cov:
	@echo "Running tests with coverage..."
	pytest tests/ -v --cov=api --cov-report=term-missing

# =============================================================================
# Security
# =============================================================================

security:
	@echo "Running security scans..."
	@echo "== pip-audit =="
	-pip-audit
	@echo ""
	@echo "== bandit =="
	-bandit -r api/ -ll -q
	@echo ""
	@echo "== npm audit (web) =="
	-cd web && npm audit --audit-level=high
	@echo ""
	@echo "✓ Security scan complete"

# =============================================================================
# Build
# =============================================================================

build: build-web
	@echo "✓ Build complete"

build-web:
	@echo "Building frontend..."
	cd web && npm run build
	@echo "✓ Frontend built"

# =============================================================================
# Quality Gate
# =============================================================================

check: lint test
	@echo "✓ All checks passed"

# =============================================================================
# Cleanup
# =============================================================================

clean:
	@echo "Cleaning build artifacts..."
	rm -rf web/dist
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf .mypy_cache
	rm -rf htmlcov
	rm -rf .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Cleaned"
