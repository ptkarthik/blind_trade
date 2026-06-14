#!/bin/bash
echo "🚀 Starting Deployment..."

# 1. Pull latest code from GitHub
echo "📥 Pulling latest code from main branch..."
git fetch origin
git reset --hard origin/main
git pull origin main

# 2. Update Python Dependencies
echo "📦 Updating Python Dependencies..."
cd backend
if [ -d "venv" ]; then
    source venv/bin/activate
    pip install -r requirements.txt
else
    pip3 install -r requirements.txt
fi
cd ..

# 3. Restart PM2 Backend Workers
echo "🔄 Restarting Python Backend (PM2)..."
sudo pm2 restart fastapi
sudo pm2 restart worker

# 3. Rebuild Frontend Container
echo "🏗️ Rebuilding React Frontend..."
sudo docker-compose down
sudo docker-compose up -d --build --remove-orphans frontend

echo "✅ Deployment complete! Server is running the latest code."
