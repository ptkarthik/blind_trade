#!/bin/bash
echo "🚀 Starting Deployment..."

# 1. Pull latest code from GitHub
echo "📥 Pulling latest code from main branch..."
git fetch origin
git reset --hard origin/main
git pull origin main

# 2. Restart PM2 Backend Workers
echo "🔄 Restarting Python Backend (PM2)..."
sudo pm2 restart fastapi
sudo pm2 restart worker

# 3. Rebuild Frontend Container
echo "🏗️ Rebuilding React Frontend..."
sudo docker-compose up -d --build frontend

echo "✅ Deployment complete! Server is running the latest code."
