import aiosqlite
import os
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from functools import wraps

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
DATABASE_PATH = DATABASE_URL.replace("sqlite:///", "")

# Database connection pool
_db_lock = asyncio.Lock()

def retry_db_operation(max_retries=3, delay=0.1):
    """Decorator to retry database operations on failure."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if "database is locked" in str(e).lower() or "database disk image is malformed" in str(e).lower():
                        if attempt < max_retries - 1:
                            await asyncio.sleep(delay * (2 ** attempt))  # Exponential backoff
                            continue
                raise
            raise last_exception
        return wrapper
    return decorator

@asynccontextmanager
async def get_db_connection():
    """Get a database connection with proper locking."""
    async with _db_lock:
        async with aiosqlite.connect(
            DATABASE_PATH,
            timeout=30.0,  # 30 second timeout
            isolation_level=None  # Enable autocommit mode
        ) as db:
            db.row_factory = aiosqlite.Row
            # Enable WAL mode for better concurrency
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute("PRAGMA cache_size=1000")
            await db.execute("PRAGMA temp_store=memory")
            await db.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout
            yield db

async def init_db():
    """Initialize the database with required tables."""
    async with get_db_connection() as db:
        # Users table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                telegram_connected BOOLEAN DEFAULT FALSE,
                phone_number VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Telegram messages table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS telegram_messages (
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
            )
        """)
        
        # Telegram sessions table (for storing session data)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS telegram_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

async def get_db():
    """Get database connection for FastAPI dependency injection."""
    async with get_db_connection() as db:
        yield db
