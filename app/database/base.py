"""
Base database manager with connection handling and common utilities.
"""

import asyncio
import logging
from typing import Dict, Any, List, Tuple
from contextlib import asynccontextmanager
import aiosqlite
from functools import wraps

logger = logging.getLogger(__name__)


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
            raise last_exception

        return wrapper

    return decorator


class BaseDatabaseManager:
    """Base database manager with connection handling and common utilities."""

    def __init__(self, database_path: str):
        self.database_path = database_path
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def get_connection(self):
        """Get a database connection with proper locking."""
        async with self._lock:
            async with aiosqlite.connect(
                self.database_path,
                timeout=30.0,
                isolation_level=None,  # Enable autocommit mode
            ) as db:
                db.row_factory = aiosqlite.Row
                # Enable WAL mode for better concurrency
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA synchronous=NORMAL")
                await db.execute("PRAGMA cache_size=1000")
                await db.execute("PRAGMA temp_store=memory")
                await db.execute("PRAGMA busy_timeout=30000")
                yield db

    @retry_db_operation()
    async def execute_query(
        self, query: str, params: Tuple = ()
    ) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results."""
        async with self.get_connection() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    @retry_db_operation()
    async def execute_update(self, query: str, params: Tuple = ()) -> int:
        """Execute an INSERT/UPDATE/DELETE query and return rows affected."""
        async with self.get_connection() as db:
            cursor = await db.execute(query, params)
            await db.commit()
            return cursor.rowcount

    async def initialize_database(self):
        """Initialize the database with all required tables."""
        try:
            async with self.get_connection() as db:
                # Users table
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        hashed_password TEXT NOT NULL,
                        telegram_connected BOOLEAN DEFAULT FALSE,
                        phone_number TEXT,
                        energy INTEGER DEFAULT 100,
                        max_energy INTEGER DEFAULT 100,
                        energy_recharge_rate INTEGER DEFAULT 1,
                        last_energy_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_admin BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                # Telegram sessions table
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telegram_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        session_data TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        session_timer_end TIMESTAMP DEFAULT NULL,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                """
                )

                # Add timer column to existing sessions (migration)
                try:
                    await db.execute(
                        "ALTER TABLE telegram_sessions ADD COLUMN session_timer_end TIMESTAMP DEFAULT NULL"
                    )
                except Exception:
                    pass  # Column already exists

                # Remove old timer_minutes column if it exists
                try:
                    await db.execute("ALTER TABLE telegram_sessions DROP COLUMN session_timer_minutes")
                except Exception:
                    pass  # Column doesn't exist or can't be dropped

                # Messages table
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        message_type TEXT NOT NULL,
                        content TEXT,
                        energy_cost INTEGER DEFAULT 0,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                """
                )

                # Energy costs table
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_energy_costs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        message_type TEXT NOT NULL,
                        energy_cost INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                        UNIQUE(user_id, message_type)
                    )
                """
                )

                # Profile protection table
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_profile_protection (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL UNIQUE,
                        profile_protection_enabled BOOLEAN DEFAULT TRUE,
                        profile_change_penalty INTEGER DEFAULT 10,
                        original_first_name TEXT,
                        original_last_name TEXT,
                        original_bio TEXT,
                        original_profile_photo_id TEXT,
                        profile_locked_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                """
                )

                # Profile revert costs table
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_profile_revert_costs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL UNIQUE,
                        revert_cost INTEGER DEFAULT 15,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                """
                )

                # Badwords table
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_badwords (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        word TEXT NOT NULL,
                        penalty INTEGER DEFAULT 5,
                        case_sensitive BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                        UNIQUE(user_id, word, case_sensitive)
                    )
                """
                )

                # Autocorrect settings table
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_autocorrect_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL UNIQUE,
                        enabled BOOLEAN DEFAULT FALSE,
                        penalty_per_correction INTEGER DEFAULT 5,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                    )
                """
                )

                # Invite codes table
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS invite_codes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code TEXT UNIQUE NOT NULL,
                        max_uses INTEGER,
                        current_uses INTEGER DEFAULT 0,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                # Chat blacklist table - allows users with locked profiles to exempt chats from filtering
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_chat_blacklist (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        chat_title TEXT,
                        chat_type TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                        UNIQUE(user_id, chat_id)
                    )
                """
                )

                # Chat whitelist table - allows users with locked profiles to only apply filtering to specific chats
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_chat_whitelist (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        chat_title TEXT,
                        chat_type TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                        UNIQUE(user_id, chat_id)
                    )
                """
                )

                # Chat list mode settings - determines whether a user uses blacklist or whitelist
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_chat_list_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL UNIQUE,
                        list_mode TEXT NOT NULL DEFAULT 'blacklist',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                        CHECK (list_mode IN ('blacklist', 'whitelist'))
                    )
                """
                )

                await db.commit()
                logger.info("✅ Database initialized successfully")

        except Exception as e:
            logger.error(f"❌ Error initializing database: {e}")
            raise
