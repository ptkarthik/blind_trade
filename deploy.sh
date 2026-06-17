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

# 4. Free up Port 80
echo "🧹 Freeing up port 80 (stopping conflicting services)..."
sudo systemctl stop nginx > /dev/null 2>&1 || true
sudo systemctl stop apache2 > /dev/null 2>&1 || true
sudo docker ps -a | grep frontend | awk '{print $1}' | xargs -r sudo docker rm -f > /dev/null 2>&1 || true
sudo fuser -k 80/tcp > /dev/null 2>&1 || true

# 5. Rebuild Frontend Container
echo "🏗️ Rebuilding React Frontend..."
sudo docker-compose stop frontend > /dev/null 2>&1 || true
sudo docker-compose rm -f frontend > /dev/null 2>&1 || true
sudo docker system prune -f > /dev/null 2>&1 || true
sudo docker-compose up -d --build --remove-orphans frontend

echo "✅ Deployment complete! Server is running the latest code."
