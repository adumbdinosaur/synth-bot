# Telegram UserBot Web Application

A secure web application built with FastAPI and Jinja2 templates that allows users to connect their personal Telegram account via userbot interface and monitor outgoing messages in real-time.

## Features

### 🔐 Security & Authentication
- **Secure user registration and login** with bcrypt password hashing
- **JWT token-based authentication** with HTTP-only cookies
- **Session-based security** with configurable token expiration
- **2FA support** for Telegram authentication

### 📱 Telegram Integration
- **Userbot connection** via phone number verification
- **Real-time message monitoring** of outgoing messages
- **2FA password support** for accounts with two-factor authentication
- **Secure session management** with encrypted storage

### 💾 Data Management
- **SQLite database** for efficient local storage
- **Message logging** with chat information and timestamps
- **User management** with connection status tracking
- **Persistent session storage** for Telegram connections

### 🐳 Deployment
- **Fully containerized** with Docker and Docker Compose
- **Production-ready** with health checks and restart policies
- **Environment-based configuration** for easy deployment
- **Volume mounting** for data persistence

## Quick Start

### Prerequisites
- Python 3.11+
- Docker and Docker Compose (for containerized deployment)
- Telegram API credentials (from https://my.telegram.org)

### 1. Get Telegram API Credentials
1. Visit https://my.telegram.org
2. Log in with your phone number
3. Go to "API development tools"
4. Create a new application to get your `api_id` and `api_hash`

### 2. Environment Setup

#### For Nix Users ❄️
```bash
# Enter the development environment (auto-creates venv and installs deps)
nix-shell

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

#### For Non-Nix Users
```bash
# Clone or create the project directory
cd /path/to/your/project

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

Update the `.env` file with your values:
```env
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here
SECRET_KEY=your-super-secret-key-change-this-in-production
```

### 3. Development Setup

#### Option A: Nix Shell (Recommended for Nix users) ❄️
```bash
# Using nix-shell (automatically manages everything)
nix-shell

# The environment will automatically:
# - Create virtual environment if needed
# - Activate virtual environment
# - Install/update Python dependencies
# - Set up all necessary paths and variables

# Just start the application
python main.py

# Or run the setup script for configuration
./setup.sh
```

#### Option B: Docker Deployment (Cross-platform)
```bash
# Build and start the application
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the application
docker-compose down
```

#### Option C: Local Development (Without Nix)
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

## Usage

### 1. Register an Account
- Visit `http://localhost:8000`
- Click "Register" and create your account
- Provide username, email, and secure password

### 2. Connect Telegram
- Log in to your account
- Navigate to Dashboard
- Click "Connect Telegram"
- Enter your phone number with country code
- Enter the verification code sent via SMS
- If you have 2FA enabled, enter your cloud password

### 3. Monitor Messages
- Once connected, the dashboard will show your connection status
- All outgoing messages will be automatically logged
- View recent messages in the dashboard table
- Messages auto-refresh every 30 seconds

## API Endpoints

### Authentication
- `GET /` - Home page
- `GET /register` - Registration form
- `POST /register` - Create new account
- `GET /login` - Login form
- `POST /login` - Authenticate user
- `POST /logout` - Logout user

### Dashboard
- `GET /dashboard` - User dashboard (protected)

### Telegram Integration
- `GET /telegram/connect` - Telegram connection form (protected)
- `POST /telegram/connect` - Send verification code (protected)
- `POST /telegram/verify` - Verify and connect account (protected)
- `POST /telegram/disconnect` - Disconnect Telegram (protected)

### System
- `GET /health` - Health check endpoint

## Database Schema

### Users Table
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    telegram_connected BOOLEAN DEFAULT FALSE,
    phone_number VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Telegram Messages Table
```sql
CREATE TABLE telegram_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    message_id INTEGER,
    content TEXT,
    chat_id INTEGER,
    chat_title TEXT,
    chat_type TEXT,
    sent_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id)
);
```

## Configuration

### Environment Variables
- `TELEGRAM_API_ID` - Your Telegram API ID
- `TELEGRAM_API_HASH` - Your Telegram API Hash
- `SECRET_KEY` - JWT secret key for token signing
- `ALGORITHM` - JWT algorithm (default: HS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Token expiration time (default: 1440)
- `DATABASE_URL` - Database connection string
- `DEBUG` - Enable debug mode (default: True)
- `HOST` - Server host (default: 0.0.0.0)
- `PORT` - Server port (default: 8000)

## Security Considerations

### Production Deployment
1. **Change the SECRET_KEY** to a strong, unique value
2. **Use HTTPS** in production (set secure cookies)
3. **Set DEBUG=False** in production
4. **Use a reverse proxy** (nginx, traefik) for SSL termination
5. **Regular backups** of the SQLite database
6. **Monitor logs** for suspicious activity

### Telegram Session Security
- Session files are stored in the `sessions/` directory
- Each user has a separate session file
- Sessions are automatically managed by Telethon
- Disconnecting removes the session file

## Project Structure
```
telegram-userbot/
├── app/
│   ├── __init__.py
│   ├── auth.py          # Authentication logic
│   ├── database.py      # Database connection and setup
│   ├── models.py        # Pydantic models
│   ├── telegram_client.py # Telegram userbot client
│   └── utils.py         # Utility functions
├── templates/
│   ├── base.html        # Base template
│   ├── index.html       # Home page
│   ├── login.html       # Login form
│   ├── register.html    # Registration form
│   ├── dashboard.html   # User dashboard
│   ├── telegram_connect.html # Telegram connection
│   └── telegram_verify.html  # Verification form
├── static/
│   └── style.css        # Custom styles
├── sessions/            # Telegram session files (created automatically)
├── main.py              # FastAPI application
├── requirements.txt     # Python dependencies
├── Dockerfile          # Docker configuration
├── docker-compose.yml  # Docker Compose setup
├── .env.example        # Environment variables template
└── README.md           # This file
```

## Troubleshooting

### Common Issues

1. **"Invalid API ID/Hash"**
   - Verify your API credentials at https://my.telegram.org
   - Ensure no extra spaces in the .env file

2. **"Phone code invalid"**
   - Make sure you're entering the exact code from SMS
   - Check if the code has expired (codes expire after a few minutes)

3. **"Session password needed"**
   - Your account has 2FA enabled
   - Enter your cloud password in the password field

4. **Database errors**
   - Ensure the database directory is writable
   - Check if SQLite is properly installed

5. **Connection issues**
   - Verify your internet connection
   - Check if Telegram is accessible from your server
   - Ensure firewall allows outbound connections

### Logs and Debugging
```bash
# View application logs (Docker)
docker-compose logs -f telegram-userbot

# View real-time logs (local)
python main.py  # Will show logs in console

# Check health status
curl http://localhost:8000/health
```

## Future Enhancements

- [ ] **Message filtering** by keywords or chat types
- [ ] **Export functionality** for message history
- [ ] **Admin panel** for user management
- [ ] **Webhook support** for external integrations
- [ ] **Advanced analytics** and reporting
- [ ] **Multi-language support**
- [ ] **Redis support** for session storage
- [ ] **PostgreSQL support** for larger deployments

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is for educational purposes. Please ensure compliance with Telegram's Terms of Service when using userbot functionality.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review application logs
3. Ensure all prerequisites are met
4. Verify environment configuration
