# Quick Start Guide

Get the application running in 5 minutes!

## Option 1: Using Docker Compose (Easiest)

### Prerequisites
- Docker and Docker Compose installed

### Steps

```bash
# Navigate to project root
cd fullstack-auth-app

# Start all services (PostgreSQL, Backend, Frontend)
docker-compose up -d

# Wait for services to start (30 seconds)
sleep 30

# Access the application
# Frontend: http://localhost:3000
# Backend API: http://localhost:5000/api
# Database: localhost:5432
```

**Credentials:**
- PostgreSQL User: `postgres`
- PostgreSQL Password: `password`
- Database: `auth_db`

**Stop services:**
```bash
docker-compose down
```

## Option 2: Manual Setup

### Backend Setup

```bash
# 1. Navigate to backend
cd backend

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create .env file
cp .env.example .env

# 6. Update DATABASE_URL in .env (if not using default)
# Default: postgresql://postgres:password@localhost:5432/auth_db

# 7. Create database (if using PostgreSQL)
createdb auth_db

# 8. Run backend server
python main.py
```

Backend runs at: **http://localhost:5000**

### Frontend Setup (in another terminal)

```bash
# 1. Navigate to frontend
cd frontend

# 2. Install dependencies
npm install

# 3. Create .env file
cp .env.example .env

# 4. Start development server
npm start
```

Frontend runs at: **http://localhost:3000**

## Test the Application

### Sign Up
1. Navigate to http://localhost:3000/signup
2. Fill in the form with:
   - Username: `testuser`
   - Email: `test@example.com`
   - Password: `TestPass123!`
   - Confirm Password: `TestPass123!`
3. Click Sign Up

### Login
1. Navigate to http://localhost:3000/login
2. Enter email and password from signup
3. Click Sign In

### View Dashboard
1. After login, you'll be redirected to dashboard
2. View and edit your profile

## API Testing (with curl/Postman)

### Sign Up
```bash
curl -X POST http://localhost:5000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "TestPass123!",
    "confirm_password": "TestPass123!"
  }'
```

### Login
```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPass123!"
  }'
```

### Get Current User (use access token from login)
```bash
curl -X GET http://localhost:5000/api/auth/me \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Troubleshooting

### Database Connection Error
```bash
# Check PostgreSQL is running
psql -U postgres

# If not installed, install PostgreSQL or use Docker:
docker run -d \
  --name postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=auth_db \
  -p 5432:5432 \
  postgres:15
```

### Port 5000 or 3000 Already in Use
```bash
# Change port in backend/main.py or frontend/package.json

# Or kill existing process:
# macOS/Linux:
lsof -i :5000
kill -9 PID

# Windows:
netstat -ano | findstr :5000
taskkill /PID PID /F
```

### CORS Errors
1. Ensure backend and frontend URLs match in CORS_ORIGINS in .env
2. Default: `CORS_ORIGINS=http://localhost:3000`

### Module Not Found Errors
```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

## Project Structure Quick Reference

```
Backend
├── main.py              ← Run this to start backend
├── config/              ← Configuration files
├── app/
│   ├── routes/         ← API endpoints
│   ├── models/         ← Database models
│   ├── services/       ← Business logic
│   └── validators/     ← Input validation

Frontend
├── src/
│   ├── pages/          ← Page components (Login, SignUp, Dashboard)
│   ├── components/     ← Reusable components
│   ├── store/          ← Zustand state management
│   └── utils/          ← Helper functions and API client
└── package.json        ← Run 'npm start' to start frontend
```

## Next Steps

1. ✅ Create user account
2. ✅ Login to dashboard
3. ✅ Update profile
4. 📚 Explore API endpoints
5. 🔧 Customize the application
6. 🚀 Deploy to production

## Support

For issues or questions:
1. Check the README.md for detailed documentation
2. Review error messages in console/logs
3. Check API response for validation errors
4. Ensure all environment variables are set correctly

Happy coding! 🎉
