# Central Dispatch - Vehicle Transport Automation

Email-to-ClickUp/Central Dispatch pipeline for vehicle transport with ML training support.

## Tech Stack

- **Backend**: Python 3.9+ / FastAPI
- **Frontend**: React 18 / Vite / Tailwind CSS
- **Database**: SQLite
- **E2E Tests**: Playwright
- **Unit Tests**: pytest

## Project Structure

```
├── api/              # FastAPI backend
│   ├── routes/       # API endpoints
│   ├── models/       # Database models
│   └── workers/      # Background workers
├── web/              # React frontend
│   └── src/
│       ├── pages/    # Page components
│       └── components/
├── e2e/              # Playwright E2E tests
├── tests/            # Python unit/integration tests
├── core/             # Core business logic
├── extractors/       # PDF extraction modules
├── services/         # External service integrations
└── schemas/          # Config schemas and mappings
```

## Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+
- npm or pnpm

### Setup

```bash
# Clone and enter directory
git clone <repo-url>
cd CENTRALDISPATCH

# Install Python dependencies
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install frontend dependencies
cd web && npm install && cd ..

# Install E2E test dependencies (optional)
cd e2e && npm install && npx playwright install && cd ..

# Copy environment template
cp .env.example .env
# Edit .env with your configuration
```

### Running the Application

```bash
# Start backend API (port 8000)
uvicorn api.main:app --reload --port 8000

# Start frontend dev server (port 5173)
cd web && npm run dev
```

### Using Make (recommended)

```bash
make setup      # Install all dependencies
make dev        # Start backend + frontend
make lint       # Run all linters
make test       # Run all tests
make build      # Build for production
make check      # Run lint + test
make clean      # Remove build artifacts
```

## Development

### Linting & Formatting

```bash
# Python
ruff check .                    # Lint
ruff check . --fix              # Lint with autofix
ruff format .                   # Format

# Frontend
cd web && npm run lint          # ESLint (if configured)
```

### Testing

```bash
# Python unit/integration tests
pytest                          # Run all tests
pytest -v                       # Verbose output
pytest --cov=api               # With coverage

# E2E tests (requires running app)
cd e2e && npm test             # Run Playwright tests
cd e2e && npm run test:headed  # Run with browser visible
```

### Security Scanning

```bash
# Python dependencies
pip-audit                       # Check for vulnerabilities
bandit -r api/                  # Static security analysis

# Node dependencies
cd web && npm audit
cd e2e && npm audit
```

## API Documentation

When running, API docs are available at:
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## Environment Variables

See `.env.example` for all configuration options including:
- Database paths
- Central Dispatch credentials
- Google Sheets API keys
- Email (IMAP) settings
- ClickUp integration

## License

MIT License - see LICENSE file for details.
