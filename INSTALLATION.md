# Complete Installation & Setup Guide

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Setup (Docker)](#quick-setup-docker)
3. [Manual Setup](#manual-setup)
4. [Verification](#verification)
5. [Troubleshooting](#troubleshooting)
6. [Configuration](#configuration)

---

## Prerequisites

### For Docker Setup
- Docker Desktop or Docker Engine
- Docker Compose (included with Docker Desktop)
- 4GB RAM minimum
- Internet connection

### For Manual Setup
- **Backend Requirements:**
  - Python 3.8+
  - PostgreSQL 12+
  - pip (Python package manager)
  - Git

- **Frontend Requirements:**
  - Node.js 16+ (includes npm)
  - Git

### System Requirements
- Disk space: ~2GB
- RAM: 4GB minimum (8GB recommended)
- Port availability: 3000 (frontend), 5000 (backend), 5432 (database)

---

## Quick Setup (Docker)

### Step 1: Install Docker

**Windows/Mac:**
1. Download [Docker Desktop](https://www.docker.com/products/docker-desktop)
2. Install and run

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo usermod -aG docker $USER
# Log out and back in for group changes to take effect
```

### Step 2: Clone Project

```bash
git clone <repository-url> fullstack-auth-app
cd fullstack-auth-app
```

### Step 3: Start Services

```bash
# Start all services (PostgreSQL, Backend, Frontend)
docker-compose up -d

# Wait for services to initialize (~30 seconds)
sleep 30

# Verify all containers are running
docker-compose ps
```

Expected output:
```
CONTAINER ID   IMAGE            STATUS              PORTS
xxxx           auth_backend     Up 2 minutes        0.0.0.0:5000->5000/tcp
xxxx           auth_frontend    Up 2 minutes        0.0.0.0:3000->3000/tcp
xxxx           auth_postgres    Up 2 minutes        0.0.0.0:5432->5432/tcp
```

### Step 4: Access Application

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:5000/api
- **Database:** localhost:5432 (psql -U postgres -d auth_db)

### Step 5: Test

Create a test account:
1. Go to http://localhost:3000/signup
2. Fill in the form with:
   - Username: `testuser`
   - Email: `test@example.com`
   - Password: `TestPass123!`
3. Click Sign Up

### Stop Services

```bash
docker-compose down

# To also remove database volume:
docker-compose down -v
```

---

## Manual Setup

### Backend Setup

#### Step 1: Setup Python Environment

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate

# macOS/Linux:
source venv/bin/activate
```

You should see `(venv)` prefix in terminal.

#### Step 2: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### Step 3: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env (optional for development)
# Default values work for local development
cat .env
```

**Important environment variables:**
```env
FLASK_ENV=development
DATABASE_URL=postgresql://postgres:password@localhost:5432/auth_db
JWT_SECRET_KEY=your-secret-key-change-in-production
CORS_ORIGINS=http://localhost:3000
```

#### Step 4: Setup Database

**Option A: Using PostgreSQL locally**

```bash
# Create database
createdb auth_db

# Verify connection
psql -U postgres -d auth_db

# Type \q to exit
```

**Option B: Using Docker for database only**

```bash
docker run -d \
  --name postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=auth_db \
  -p 5432:5432 \
  postgres:15

# Wait for database to start
sleep 10
```

#### Step 5: Initialize Database

```bash
# The database tables are created automatically when you run the app
# If needed, initialize manually:
python -c "from app import create_app; app = create_app(); app.app_context().push()"
```

#### Step 6: Start Backend Server

```bash
python main.py
```

Expected output:
```
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://0.0.0.0:5000
```

**Backend is ready at:** `http://localhost:5000/api`

---

### Frontend Setup

#### Step 1: Setup Node Environment

```bash
cd frontend

# Verify Node.js installation
node --version  # Should be v16 or higher
npm --version   # Should be v8 or higher
```

#### Step 2: Install Dependencies

```bash
npm install

# Wait for installation to complete (~2-3 minutes)
```

#### Step 3: Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Default configuration works for development
cat .env
```

**Environment variables:**
```env
REACT_APP_API_URL=http://localhost:5000/api
REACT_APP_ENVIRONMENT=development
```

#### Step 4: Start Frontend Server

```bash
npm start
```

Expected output:
```
Compiled successfully!

You can now view auth-app-frontend in the browser.

  Local:            http://localhost:3000
  On Your Network:  http://192.168.x.x:3000
```

**Frontend is ready at:** `http://localhost:3000`

---

## Verification

### Check Backend

```bash
# Test health endpoint
curl http://localhost:5000/api/health

# Expected response:
# {"success": true, "message": "Server is running", "data": {"status": "healthy"}}
```

### Check Frontend

1. Open browser: http://localhost:3000
2. Should see login page
3. No console errors

### Check Database Connection

```bash
# Backend should create tables automatically
# Verify tables exist:
psql -U postgres -d auth_db -c "\dt"

# Should output:
#  public | users               | table
#  public | refresh_token_blacklist | table
```

### Check Network Communication

```bash
# Frontend → Backend
curl -X GET http://localhost:5000/api/auth/me \
  -H "Authorization: Bearer invalid" 2>/dev/null | python -m json.tool

# Should return 401 (unauthorized) - that's correct!
```

---

## Troubleshooting

### Port Already in Use

**Error:** `Address already in use` or `Port 5000 is already in use`

**Solution:**

```bash
# Find process using port
# macOS/Linux:
lsof -i :5000   # Backend
lsof -i :3000   # Frontend
lsof -i :5432   # Database

# Kill process
kill -9 <PID>

# Or change port in code
```

### Database Connection Error

**Error:** `could not translate host name "localhost" to address`

**Solutions:**

```bash
# 1. Check PostgreSQL is running
pg_isready -h localhost -p 5432

# 2. Verify DATABASE_URL in .env
echo $DATABASE_URL

# 3. Test connection
psql -U postgres -d auth_db

# 4. If not installed, install PostgreSQL or use Docker
docker run -d -e POSTGRES_PASSWORD=password -e POSTGRES_DB=auth_db -p 5432:5432 postgres:15
```

### Module/Package Not Found

**Error:** `ModuleNotFoundError: No module named 'flask'`

**Solution (Backend):**

```bash
cd backend
source venv/bin/activate  # Activate venv
pip install -r requirements.txt
```

**Error:** `Cannot find module 'react'`

**Solution (Frontend):**

```bash
cd frontend
npm install
```

### CORS Error in Browser

**Error:** `Access to XMLHttpRequest at 'http://localhost:5000/api/...' blocked by CORS`

**Solution:**

1. Check `CORS_ORIGINS` in backend `.env`:
   ```env
   CORS_ORIGINS=http://localhost:3000
   ```

2. Restart backend:
   ```bash
   # Stop (Ctrl+C)
   # Start again
   python main.py
   ```

### Port 3000 Won't Start (Frontend)

**Error:** `Something is already listening on port 3000`

**Solution:**

```bash
# Option 1: Kill existing process
lsof -i :3000
kill -9 <PID>

# Option 2: Use different port
PORT=3001 npm start

# Update backend CORS_ORIGINS:
# CORS_ORIGINS=http://localhost:3001
```

### Virtual Environment Issues (Python)

**Error:** `python: command not found` or `ModuleNotFoundError`

**Solution:**

```bash
# Use python3 explicitly
python3 -m venv venv
source venv/bin/activate

# For Windows:
python -m venv venv
venv\Scripts\activate
```

### Docker Issues

**Error:** `Cannot connect to Docker daemon`

**Solution:**

```bash
# Start Docker Desktop (GUI) or daemon:

# Linux:
sudo systemctl start docker

# Windows/Mac:
# Open Docker Desktop application
```

**Error:** `Exit code: 1` when running docker-compose

**Solution:**

```bash
# Check logs
docker-compose logs

# Remove containers and rebuild
docker-compose down -v
docker-compose up --build
```

### npm Start Stuck

**Error:** Compilation doesn't finish or webpack errors

**Solution:**

```bash
# Clear cache and reinstall
cd frontend
rm -rf node_modules
npm cache clean --force
npm install
npm start
```

---

## Configuration

### Environment Variables

#### Backend (.env)

```env
# Flask
FLASK_ENV=development              # development or production
FLASK_DEBUG=True                   # Auto-reload on changes

# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/auth_db

# JWT
JWT_SECRET_KEY=change-me-in-production-use-openssl-rand-hex-32
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRES=3600      # 1 hour in seconds
JWT_REFRESH_TOKEN_EXPIRES=2592000  # 30 days in seconds

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# Logging
LOG_LEVEL=DEBUG

# Security (Production)
SESSION_COOKIE_SECURE=True
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE=Lax
```

#### Frontend (.env)

```env
# API
REACT_APP_API_URL=http://localhost:5000/api

# Environment
REACT_APP_ENVIRONMENT=development

# Features
REACT_APP_ENABLE_ANALYTICS=false
```

### Generate JWT Secret

```bash
# macOS/Linux:
openssl rand -hex 32

# Python:
python -c "import secrets; print(secrets.token_hex(32))"

# Windows PowerShell:
$bytes = New-Object byte[] 32; [Security.Cryptography.RNGCryptoServiceProvider]::new().GetBytes($bytes); [Convert]::ToHexString($bytes)
```

### Change Database

To use a different database (e.g., PostgreSQL on a different host):

```env
# Local PostgreSQL (default)
DATABASE_URL=postgresql://postgres:password@localhost:5432/auth_db

# Remote PostgreSQL
DATABASE_URL=postgresql://user:password@host:5432/dbname

# SQLite (development only)
DATABASE_URL=sqlite:///auth.db
```

---

## Production Deployment

### Backend

```bash
# Install production server
pip install gunicorn

# Generate strong JWT secret
openssl rand -hex 32

# Set environment variables for production
export FLASK_ENV=production
export JWT_SECRET_KEY=<generated-secret>
export DATABASE_URL=postgresql://...

# Run with Gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 main:app
```

### Frontend

```bash
# Build optimized version
npm run build

# Serve static files
npx serve -s build -l 3000

# Or deploy to hosting (Vercel, Netlify, etc)
```

### Docker

```bash
# Build custom images
docker build -t myapp-backend:1.0 ./backend
docker build -t myapp-frontend:1.0 ./frontend

# Push to registry
docker push myapp-backend:1.0
docker push myapp-frontend:1.0

# Deploy with docker-compose
docker-compose -f docker-compose.prod.yml up -d
```

---

## Free (~₹0/month) Deployment

This app's AI features run on open-source models (see `ARCHITECTURE.md`'s
"AI Provider Architecture" section) specifically so the whole stack can be
hosted for free, without a paid Anthropic/OpenAI bill on top of hosting
costs. None of these steps cost money at the tiers described, but every
provider can change its free tier at any time - check current terms
before relying on this for something important. **Railway's free usage
is a limited monthly trial credit, not an indefinitely-free tier like
Render's or Vercel's** - fine for a personal/demo project, but worth
knowing going in.

### Option A: Railway, via Docker (both services in one project)

Both `backend/` and `frontend/` have a production `Dockerfile` and a
`railway.json` pinned to `"builder": "DOCKERFILE"` - Railway builds and
runs the actual Docker image rather than guessing at a buildpack, so
what runs in production is exactly what `docker build` produces locally.
This is two Railway **services** inside **one Railway project**, not two
separate projects.

**1. Create the project and the backend service**
- Sign up at [railway.com](https://railway.com) and connect your GitHub account.
- **New Project → Deploy from GitHub repo** → select this repository.
  Railway creates one service from it; treat that as the backend.
- Open that service → **Settings → Root Directory** → set it to `backend`.
  This repo is a monorepo, and the Dockerfile paths in `railway.json` are
  relative to whatever Root Directory you set here.
- Railway will detect `backend/railway.json` and build `backend/Dockerfile`
  automatically on the next deploy.

**2. Add a PostgreSQL database**
- In the same project: **New → Database → PostgreSQL**.
- On the backend service's **Variables** tab, add `DATABASE_URL` and set
  it to `${{Postgres.DATABASE_URL}}` (Railway's cross-service variable
  reference - it resolves to the Postgres plugin's real connection
  string, kept in sync automatically).

**3. Set the backend service's remaining Variables**
- `JWT_SECRET_KEY` - generate with `openssl rand -hex 32`
- `CORS_ORIGINS` - the frontend service's URL (you'll get this in step 5;
  it's fine to come back and fill this in after)
- `AI_PROVIDER=groq`, `GROQ_API_KEY` - see "AI provider" below
- Under **Settings → Networking**, click **Generate Domain** to get a
  public URL for the backend. Copy it - the frontend needs it next.

**4. Add the frontend as a second service in the same project**
- In the same Railway project: **New → GitHub Repo** → select this same
  repository again. This creates a second, independent service.
- Open it → **Settings → Root Directory** → set it to `frontend`.
- **Settings → Build → Build Variables** (not the regular runtime
  Variables tab - Create React App bakes `REACT_APP_*` values into the
  static JS bundle at build time, so it must be visible during the build
  step specifically) → add `REACT_APP_API_URL` set to
  `<your-backend-domain-from-step-3>/api`.
- **Settings → Networking → Generate Domain** for this service too. That
  URL is your live app.
- Go back to the backend service's Variables and set `CORS_ORIGINS` to
  this frontend URL, then redeploy the backend so the CORS change takes
  effect.

**Redeploying after a code change**: push to GitHub - both services are
already connected to this repo and rebuild automatically. There's no
separate "docker push" step; Railway builds the Dockerfile itself on
every deploy.

**If you'd rather keep the frontend off Railway** (its free tier is a
limited trial credit, not indefinite - see the note above), deploy only
the backend service above and host the frontend on
[Vercel](https://vercel.com) or [Netlify](https://netlify.com) instead
(genuinely free, no trial-credit limit, and a better-optimized fit for a
static React build) - point it at `frontend/`, and set the same
`REACT_APP_API_URL` build-time variable there instead of on Railway.

### Option B: Render + Vercel + Neon (each genuinely free, not trial-limited)

**1. Database - [Neon](https://neon.tech) (free Postgres, persists)**
Create a project, copy the connection string, and set it as
`DATABASE_URL` on the backend (step 2) - it already starts with
`postgresql://`, which this app's `SQLALCHEMY_DATABASE_URI` expects as-is.

**2. Backend - [Render](https://render.com) (free web service)**
Create a new Web Service pointed at this repo's `backend/` folder:
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn -w 2 -b 0.0.0.0:$PORT main:app`
- Environment variables: `DATABASE_URL` (from step 1), `JWT_SECRET_KEY`
  (generate with `openssl rand -hex 32`), `CORS_ORIGINS` (your frontend's
  URL from step 3), `AI_PROVIDER=groq`, `GROQ_API_KEY` (step 4).
- Free tier caveat: the service sleeps after ~15 minutes of no traffic and
  takes ~30-60s to wake on the next request - fine for a personal/demo
  app, not for something needing instant uptime.

**3. Frontend - [Vercel](https://vercel.com) or [Netlify](https://netlify.com) (free static hosting)**
Point either at this repo's `frontend/` folder (Create React App preset
works out of the box); set `REACT_APP_API_URL` to your Render backend's
URL from step 2.

### Option C: AWS EC2 (or any self-managed Docker host, including a shared box)

If you already have a Linux server (EC2 or otherwise) - possibly one
already running other projects behind the same nginx - deploy the
backend as a Docker container and the frontend as static files served by
your existing nginx, rather than a second Docker container per service:

**1. Backend**
```bash
git clone https://github.com/<you>/expense-classifier.git
cd expense-classifier/backend
cp .env.example .env
# Edit .env: JWT_SECRET_KEY (openssl rand -hex 32), CORS_ORIGINS (your
# domain), AI_PROVIDER=groq, GROQ_API_KEY.
#
# DATABASE_URL on a memory-constrained box: three options, best to worst
# for a shared/low-RAM host -
#   1. A managed database (e.g. AWS RDS Postgres) in the same VPC as the
#      EC2 instance - offloads the DB process entirely, costs the host
#      zero RAM. Needs: the RDS security group to allow inbound 5432 from
#      the EC2 instance's security group (`aws ec2
#      authorize-security-group-ingress --group-id <rds-sg> --protocol
#      tcp --port 5432 --source-group <ec2-sg>`), and a
#      `postgresql://user:pass@<rds-endpoint>:5432/postgres` URL here.
#   2. SQLite (the default if DATABASE_URL is left unset) - zero extra
#      process, but data lives only on this host's disk.
#   3. A second local Postgres container - avoid on a box already tight
#      on RAM; it's the heaviest of the three options here.
cd ..
docker compose -f docker-compose.prod.yml -p fintech up -d --build
```
`docker-compose.prod.yml` binds the backend to `127.0.0.1:5000` only (not
exposed to the internet directly - only reachable through nginx) and
persists the SQLite file on a named volume (unused if DATABASE_URL points
at an external database instead). On a low-RAM host, the compose file's
`command:` already reduces gunicorn to 1 worker; increase it if the host
has more headroom.

**2. Frontend** - built once and served as static files by your existing
nginx (no second Docker container, no extra Node.js process at runtime):
```bash
cd frontend
echo "REACT_APP_API_URL=https://<your-domain>/api" > .env.production.local
npm install && npm run build
sudo mkdir -p /var/www/fintech && sudo cp -r build/* /var/www/fintech/
```

**3. nginx** - see [deploy/nginx-fintech.conf.example](deploy/nginx-fintech.conf.example)
for a ready-to-adapt server block (static frontend + `/api/` proxied to
the container). **Read the caveat in that file before running certbot**:
if another Docker container on the host already publishes host port 80,
Docker's iptables rule for it silently intercepts *all* external port-80
traffic before nginx ever sees it - for any domain, not just that
container's own - which breaks Let's Encrypt's HTTP-01 challenge with no
obvious error pointing at the real cause. Check
`sudo iptables -t nat -L DOCKER -n` for existing `dpt:80` rules first. If
one exists and you can't remap it, a self-signed certificate
(`openssl req -x509 -nodes -days 825 -newkey rsa:2048 ...`) is the
pragmatic fallback - real encryption, just a one-time browser warning
instead of a trusted cert chain.

### AI provider - [Groq](https://console.groq.com) (free tier)

Needed by any option above. Sign up, create an API key, and set
`GROQ_API_KEY` + `AI_PROVIDER=groq` on the backend service's environment
variables. This is what serves the AI Assistant chat, goal savings
advice, and the CSV/PDF AI-parsing fallback in production - Ollama (used
for local development) cannot be deployed to Railway, Render, Vercel, or
any platform above, since it's a long-running process with multi-GB
model weights on local disk, not a serverless-compatible one.

---

## Next Steps After Installation

1. ✅ [x] Create user account (http://localhost:3000/signup)
2. ✅ [x] Login (http://localhost:3000/login)
3. ✅ [x] View dashboard (http://localhost:3000/dashboard)
4. 📚 Read [API.md](API.md) for endpoint documentation
5. 🔧 Customize styles and components
6. 🧪 Write tests
7. 🚀 Deploy to production

---

## Support & Resources

### Documentation
- [README.md](README.md) - Project overview
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [API.md](API.md) - API documentation
- [FILE_STRUCTURE.md](FILE_STRUCTURE.md) - File reference

### Useful Commands

```bash
# Backend
make run-backend          # Start backend
make test                # Run tests
make lint                # Check code

# Frontend
npm start                # Start dev server
npm build                # Build for production
npm test                 # Run tests

# Both
docker-compose up -d     # Start all services
docker-compose down      # Stop all services
make help               # Show all make commands
```

### Common Ports

| Service | Port | URL |
|---------|------|-----|
| Frontend | 3000 | http://localhost:3000 |
| Backend | 5000 | http://localhost:5000/api |
| Database | 5432 | localhost:5432 |
| PostgreSQL CLI | N/A | `psql -U postgres -d auth_db` |

### Get Help

1. Check the error message
2. Look in [Troubleshooting](#troubleshooting) section
3. Review [FILE_STRUCTURE.md](FILE_STRUCTURE.md) for code reference
4. Check [API.md](API.md) for endpoint issues
5. Open an issue in the repository

---

## Verify Everything Works

### Quick Test

```bash
# 1. Backend health
curl http://localhost:5000/api/health

# 2. Frontend loads (open browser)
http://localhost:3000

# 3. Create account
Sign up at http://localhost:3000/signup

# 4. Login
Login at http://localhost:3000/login

# 5. View dashboard
Should redirect to http://localhost:3000/dashboard

✅ All systems operational!
```

---

## Clean Up

If you need to start fresh:

```bash
# Docker
docker-compose down -v          # Remove everything
docker-compose up -d             # Start fresh

# Manual
cd backend
rm -rf venv                      # Remove virtual environment
cd ../frontend
rm -rf node_modules              # Remove dependencies

# Reinstall
make install
```

---

**Congratulations! Your full-stack authentication application is ready! 🎉**

For questions or issues, refer to the documentation or open an issue in the repository.
