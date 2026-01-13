.PHONY: generate generate-types generate-http test format typecheck install clean help

help:
	@echo "Available commands:"
	@echo "  make generate       - Generate all code (types + HTTP client)"
	@echo "  make generate-types - Generate type definitions"
	@echo "  make generate-http  - Generate HTTP client"
	@echo "  make test          - Run tests"
	@echo "  make format        - Format all Python files with ruff"
	@echo "  make typecheck     - Run mypy type checking"
	@echo "  make install       - Install all packages in dev mode"
	@echo "  make clean         - Remove generated files and caches"

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

clean:
	@echo "🧹 Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleanup complete"
