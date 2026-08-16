.PHONY: help install backend frontend run-backend run-frontend docker-up docker-down clean test lint format

help:
	@echo "Available commands:"
	@echo "  make install        - Install dependencies for both backend and frontend"
	@echo "  make backend        - Setup backend only"
	@echo "  make frontend       - Setup frontend only"
	@echo "  make run-backend    - Run backend server"
	@echo "  make run-frontend   - Run frontend server"
	@echo "  make run            - Run both backend and frontend (requires 2 terminals)"
	@echo "  make docker-up      - Start all services with Docker Compose"
	@echo "  make docker-down    - Stop all Docker services"
	@echo "  make test           - Run all tests"
	@echo "  make lint           - Run linters"
	@echo "  make format         - Format code"
	@echo "  make clean          - Clean up generated files"
	@echo "  make db-migrate     - Run database migrations"

install: backend frontend
	@echo "✅ Installation complete!"

backend:
	@echo "📦 Setting up backend..."
	cd backend && \
	python -m venv venv && \
	. venv/bin/activate 2>/dev/null || venv\Scripts\activate && \
	pip install -r requirements.txt && \
	cp .env.example .env
	@echo "✅ Backend setup complete!"

frontend:
	@echo "📦 Setting up frontend..."
	cd frontend && \
	npm install && \
	cp .env.example .env
	@echo "✅ Frontend setup complete!"

run-backend:
	@echo "🚀 Starting backend server..."
	cd backend && python main.py

run-frontend:
	@echo "🚀 Starting frontend server..."
	cd frontend && npm start

run:
	@echo "🚀 Starting both servers... (Please open another terminal for the other server)"
	@echo "Starting backend..."
	cd backend && python main.py &
	@echo "Starting frontend..."
	cd frontend && npm start

docker-up:
	@echo "🐳 Starting Docker services..."
	docker-compose up -d
	@echo "✅ Services started!"
	@echo "   Frontend: http://localhost:3000"
	@echo "   Backend:  http://localhost:5000"
	@echo "   Database: localhost:5432"

docker-down:
	@echo "🐳 Stopping Docker services..."
	docker-compose down

docker-logs:
	@echo "📊 Docker service logs..."
	docker-compose logs -f

test:
	@echo "🧪 Running tests..."
	cd backend && pytest -v --cov=app tests/

lint:
	@echo "🔍 Running linters..."
	cd backend && pylint app/ --fail-under=8.0 || true
	cd frontend && npm run lint || true

format:
	@echo "✨ Formatting code..."
	cd backend && black app/ config/ && isort app/ config/ || true
	cd frontend && npx prettier --write "src/**/*.{js,jsx,css}" || true

clean:
	@echo "🧹 Cleaning up..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf backend/venv 2>/dev/null || true
	rm -rf frontend/node_modules 2>/dev/null || true
	rm -rf frontend/build 2>/dev/null || true

db-migrate:
	@echo "🗄️ Running database migrations..."
	cd backend && python -c "from app import create_app; app = create_app(); app.app_context().push()" || true

db-seed:
	@echo "🌱 Seeding database..."
	cd backend && python scripts/seed_db.py || true

requirements-update:
	@echo "📦 Updating backend requirements..."
	cd backend && pip freeze > requirements.txt

git-init:
	@echo "🔧 Initializing git repository..."
	git init
	git add .
	git commit -m "Initial commit: Full-stack auth application"
	@echo "✅ Git repository initialized!"
