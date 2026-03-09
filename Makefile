.PHONY: generate generate-types generate-http test format format-check typecheck install clean help changeset changeset-status changeset-version changeset-changelog build prepare-release

help:
	@echo "Available commands:"
	@echo "  make generate            - Generate all code (types + HTTP client)"
	@echo "  make generate-types      - Generate type definitions"
	@echo "  make generate-http       - Generate HTTP client"
	@echo "  make test               - Run tests"
	@echo "  make format             - Format all Python files with ruff"
	@echo "  make typecheck          - Run mypy type checking"
	@echo "  make install            - Install all packages in dev mode"
	@echo "  make build              - Build all packages for distribution"
	@echo "  make clean              - Remove generated files and caches"
	@echo ""
	@echo "Changeset commands:"
	@echo "  make changeset          - Create a new changeset file"
	@echo "  make changeset-status   - Show pending changesets"
	@echo "  make changeset-version  - Apply version bumps from changesets"
	@echo "  make changeset-changelog - Generate changelogs from applied changesets"
	@echo "  make prepare-release     - Run version bump, changelog generation, and build for release preparation"

generate: generate-types generate-http

generate-types:
	@echo "🔧 Generating types..."
	@python codegen/types/generate_types.py

generate-http:
	@echo "🔧 Generating HTTP client..."
	@python codegen/http/generate_http.py

test:
	@echo "🧪 Running tests..."
	@pytest packages/*/tests/ -v

format:
	@echo "🎨 Formatting code..."
	@ruff format .

format-check:
	@echo "🔍 Checking code format..."
	@ruff format --check .
	@echo "✅ Code format is correct"

typecheck:
	@echo "🔍 Running type checks..."
	@mypy packages/
	@echo "✅ Type checking complete"

install:
	@echo "📦 Installing packages in dev mode..."
	@pip install -e .[dev]
	@pip install -e ./packages/sdk-types[dev]
	@pip install -e ./packages/api-key-stamper[dev]
	@pip install -e ./packages/http[dev]
	@echo "✅ All packages installed"

build:
	@echo "📦 Building packages for distribution..."
	@pip install build
	@for pkg in packages/*/; do \
		if [ -f "$$pkg/pyproject.toml" ]; then \
			echo "Building $$pkg..."; \
			python -m build "$$pkg"; \
		fi \
	done
	@echo "✅ All packages built"

clean:
	@echo "🧹 Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleanup complete"

# Changeset management
changeset:
	@python changesets/manage.py new

changeset-status:
	@python changesets/manage.py status

changeset-version:
	@python changesets/manage.py version

changeset-changelog:
	@python changesets/manage.py changelog

prepare-release: changeset-version changeset-changelog build
	@echo "✅ Release preparation complete"

