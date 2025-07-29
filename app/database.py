import aiosqlite
import os
import asyncio
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from functools import wraps

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
DATABASE_PATH = DATABASE_URL.replace("sqlite:///", "")

logger = logging.getLogger(__name__)
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
                    if (
                        "database is locked" in str(e).lower()
                        or "database disk image is malformed" in str(e).lower()
                    ):
                        if attempt < max_retries - 1:
                            await asyncio.sleep(
                                delay * (2**attempt)
                            )  # Exponential backoff
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
            isolation_level=None,  # Enable autocommit mode
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
                energy INTEGER DEFAULT 100,
                energy_recharge_rate INTEGER DEFAULT 1,
                last_energy_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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

        # Message energy costs table (configurable costs for different message types per user)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_message_energy_costs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_type VARCHAR(50) NOT NULL,
                energy_cost INTEGER NOT NULL DEFAULT 1,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, message_type)
            )
        """)

        await db.commit()

    # Run energy system migration for existing databases
    await migrate_db_for_energy()

    # Initialize default energy costs
    await init_default_energy_costs()


async def migrate_db_for_energy():
    """Add energy columns to existing users table if they don't exist."""
    async with get_db_connection() as db:
        # Check if energy column exists
        cursor = await db.execute("PRAGMA table_info(users)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "energy" not in column_names:
            logger.info("Adding energy column to users table...")
            await db.execute("ALTER TABLE users ADD COLUMN energy INTEGER DEFAULT 100")

        if "energy_recharge_rate" not in column_names:
            logger.info("Adding energy_recharge_rate column to users table...")
            await db.execute(
                "ALTER TABLE users ADD COLUMN energy_recharge_rate INTEGER DEFAULT 1"
            )

        if "last_energy_update" not in column_names:
            logger.info("Adding last_energy_update column to users table...")
            # SQLite doesn't support CURRENT_TIMESTAMP in ALTER TABLE with DEFAULT
            # So we add without default and then update existing rows
            await db.execute(
                "ALTER TABLE users ADD COLUMN last_energy_update TIMESTAMP"
            )
            # Update existing users to have current timestamp
            await db.execute(
                "UPDATE users SET last_energy_update = datetime('now') WHERE last_energy_update IS NULL"
            )

        await db.commit()
        logger.info("Energy system database migration completed")


async def get_db():
    """Get database connection for FastAPI dependency injection."""
    async with get_db_connection() as db:
        yield db


async def init_default_energy_costs():
    """Initialize default energy costs for message types."""
    default_costs = [
        ("text", 1, "Regular text messages"),
        ("sticker", 2, "Sticker messages"),
        ("photo", 2, "Photo messages"),
        ("video", 4, "Video messages"),
        ("gif", 4, "GIF/animation messages"),
        ("audio", 3, "Audio messages"),
        ("voice", 3, "Voice messages"),
        ("document", 3, "Document/file messages"),
        ("location", 2, "Location sharing"),
        ("contact", 2, "Contact sharing"),
        ("poll", 3, "Poll messages"),
        ("game", 3, "Game messages"),
        ("venue", 2, "Venue sharing"),
        ("web_page", 2, "Messages with web page preview"),
        ("media_group", 5, "Media group (multiple photos/videos)"),
    ]

    async with get_db_connection() as db:
        # Check if we have any users
        cursor = await db.execute("SELECT id FROM users")
        users = await cursor.fetchall()

        for user in users:
            user_id = user[0]

            # Check if this user already has energy costs configured
            cursor = await db.execute(
                "SELECT COUNT(*) FROM user_message_energy_costs WHERE user_id = ?",
                (user_id,),
            )
            count = await cursor.fetchone()

            if count[0] == 0:  # No energy costs configured for this user
                # Insert default costs for this user
                for message_type, energy_cost, description in default_costs:
                    await db.execute(
                        """
                        INSERT OR IGNORE INTO user_message_energy_costs 
                        (user_id, message_type, energy_cost, description)
                        VALUES (?, ?, ?, ?)
                    """,
                        (user_id, message_type, energy_cost, description),
                    )

                logger.info(f"Initialized default energy costs for user {user_id}")

        await db.commit()


async def init_user_energy_costs(user_id: int):
    """Initialize default energy costs for a new user."""
    default_costs = [
        ("text", 1, "Regular text messages"),
        ("sticker", 2, "Sticker messages"),
        ("photo", 2, "Photo messages"),
        ("video", 4, "Video messages"),
        ("gif", 4, "GIF/animation messages"),
        ("audio", 3, "Audio messages"),
        ("voice", 3, "Voice messages"),
        ("document", 3, "Document/file messages"),
        ("location", 2, "Location sharing"),
        ("contact", 2, "Contact sharing"),
        ("poll", 3, "Poll messages"),
        ("game", 3, "Game messages"),
        ("venue", 2, "Venue sharing"),
        ("web_page", 2, "Messages with web page preview"),
        ("media_group", 5, "Media group (multiple photos/videos)"),
    ]

    async with get_db_connection() as db:
        # Insert default costs for this user
        for message_type, energy_cost, description in default_costs:
            await db.execute(
                """
                INSERT OR IGNORE INTO user_message_energy_costs 
                (user_id, message_type, energy_cost, description)
                VALUES (?, ?, ?, ?)
            """,
                (user_id, message_type, energy_cost, description),
            )

        await db.commit()
        logger.info(f"Initialized default energy costs for new user {user_id}")
