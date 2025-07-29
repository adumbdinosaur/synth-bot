#!/bin/bash
# Environment Variables Export Script for Telegram UserBot
# Customize the values and run: source set-env.sh

# Required Variables - MUST BE SET
export TELEGRAM_API_ID="your_telegram_api_id"
export TELEGRAM_API_HASH="your_telegram_api_hash"
export SECRET_KEY="your_very_secure_secret_key_here_change_this"

# Optional Variables (with defaults)
export ALGORITHM="HS256"
export ACCESS_TOKEN_EXPIRE_MINUTES="1440"
export DATABASE_URL="sqlite:///./data/app.db"

# Application Settings
export DEBUG="False"
export HOST="0.0.0.0"
export PORT="8000"
export LOG_LEVEL="INFO"

# Development Mode (uncomment for development)
# export DEVELOPMENT="1"

# Docker Environment Variables
export PYTHONUNBUFFERED="1"

echo "Environment variables set successfully!"
echo "Required variables:"
echo "  TELEGRAM_API_ID: ${TELEGRAM_API_ID}"
echo "  TELEGRAM_API_HASH: ${TELEGRAM_API_HASH:0:8}..."
echo "  SECRET_KEY: ${SECRET_KEY:0:8}..."
