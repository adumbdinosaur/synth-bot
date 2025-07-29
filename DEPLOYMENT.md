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

2. **Set environment variables:**
   ```bash
   export TELEGRAM_API_ID=your_api_id
   export TELEGRAM_API_HASH=your_api_hash
   export SECRET_KEY=your_secret_key_for_jwt
   # Optional: Set other variables with defaults
   export DEBUG=False
   export LOG_LEVEL=INFO
   ```

3. **Create required directories (if using bind mounts):**
   ```bash
   mkdir -p sessions data logs temp
   ```

4. **Run with Docker Compose:**
   ```bash
   docker-compose up -d
   ```

### Development Deployment

To run the development version with bind mounts:
```bash
docker-compose -f docker-compose.local.yml up -d
```

### Environment Variables

Required environment variables for production:
```env
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
SECRET_KEY=your_secret_key_for_jwt
```

Optional environment variables with defaults:
```env
DATABASE_URL=sqlite:///./data/app.db
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
DEBUG=False
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
```

### Monitoring

- Health check endpoint: `http://localhost:8000/health`
- Logs: `docker-compose logs -f telegram-userbot`
- Container stats: `docker stats telegram-userbot-app`

### Volume Management

The production deployment uses Docker volumes for data persistence:
- `telegram_sessions` - Telegram session files
- `telegram_data` - Database and profile photos  
- `telegram_logs` - Application logs
- `telegram_temp` - Temporary files

To backup volumes:
```bash
# Create backup directory
mkdir -p backups/$(date +%Y%m%d_%H%M%S)

# Backup each volume
docker run --rm -v telegram_sessions:/data -v $(pwd)/backups/$(date +%Y%m%d_%H%M%S):/backup alpine tar czf /backup/sessions.tar.gz -C /data .
docker run --rm -v telegram_data:/data -v $(pwd)/backups/$(date +%Y%m%d_%H%M%S):/backup alpine tar czf /backup/data.tar.gz -C /data .
docker run --rm -v telegram_logs:/data -v $(pwd)/backups/$(date +%Y%m%d_%H%M%S):/backup alpine tar czf /backup/logs.tar.gz -C /data .
```

To restore volumes:
```bash
# Restore from backup (replace BACKUP_DATE with actual date)
docker run --rm -v telegram_sessions:/data -v $(pwd)/backups/BACKUP_DATE:/backup alpine tar xzf /backup/sessions.tar.gz -C /data
docker run --rm -v telegram_data:/data -v $(pwd)/backups/BACKUP_DATE:/backup alpine tar xzf /backup/data.tar.gz -C /data
```

### Backup

Important data to backup:
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

### Autocorrect Feature

The application includes an optional autocorrect feature powered by OpenAI that:
- Automatically corrects spelling errors in messages to American English
- Applies configurable energy penalties for each correction
- Can be enabled/disabled per user
- Uses conservative correction to avoid changing intended text

To enable autocorrect:
1. Set the `OPENAI_API_KEY` environment variable with your OpenAI API key
2. Configure autocorrect settings in the web interface for each user
3. Users can set energy penalty per correction (1-50 points)

**Note:** Autocorrect requires an OpenAI API key and will incur API costs based on usage.
