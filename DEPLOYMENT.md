# Deployment Guide

## Docker Deployment

### Prerequisites
- Docker and Docker Compose installed
- GitHub repository with the following secrets configured:
  - `REGISTRY_USERNAME`: Your registry.rptr.dev username
  - `REGISTRY_PASSWORD`: Your registry.rptr.dev password

### Production Deployment

1. **Pull the latest image:**
   ```bash
   docker pull registry.rptr.dev/synth-bot:latest
   ```

2. **Create environment file:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Create required directories:**
   ```bash
   mkdir -p sessions data logs temp
   ```

4. **Run with Docker Compose:**
   ```bash
   docker-compose up -d
   ```

### Development Deployment

To run the development version:
```bash
docker-compose --profile dev up -d telegram-userbot-dev
```

### Environment Variables

Required environment variables in `.env`:
```env
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
SECRET_KEY=your_secret_key_for_jwt
DATABASE_URL=sqlite:///./data/app.db
```

### Monitoring

- Health check endpoint: `http://localhost:8000/health`
- Logs: `docker-compose logs -f telegram-userbot`
- Container stats: `docker stats telegram-userbot-app`

### Backup

Important directories to backup:
- `./sessions/` - Telegram session files
- `./data/` - Database and profile photos
- `./logs/` - Application logs

### Updates

To update to the latest version:
```bash
docker-compose pull
docker-compose up -d
```

## GitHub Actions

The repository includes automated Docker image building and pushing to `registry.rptr.dev/synth-bot:latest` on every push to main branch.

### Required Secrets

Configure these secrets in your GitHub repository settings:
- `REGISTRY_USERNAME`: Username for registry.rptr.dev
- `REGISTRY_PASSWORD`: Password for registry.rptr.dev
