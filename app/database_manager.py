import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from contextlib import asynccontextmanager
import aiosqlite
import os

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Centralized database manager to handle all database operations."""

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

    # User Management Operations
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        async with self.get_connection() as db:
            cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_user(self, username: str, email: str, hashed_password: str) -> int:
        """Create a new user and return the user ID."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO users (username, email, hashed_password, energy, energy_recharge_rate, last_energy_update) 
                   VALUES (?, ?, ?, 100, 1, ?)""",
                (username, email, hashed_password, datetime.now().isoformat()),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_user_telegram_info(
        self, user_id: int, phone_number: str, connected: bool = True
    ):
        """Update user's Telegram connection info."""
        async with self.get_connection() as db:
            await db.execute(
                "UPDATE users SET telegram_connected = ?, phone_number = ? WHERE id = ?",
                (connected, phone_number, user_id),
            )
            await db.commit()

    # Energy Management Operations
    async def get_user_energy(self, user_id: int) -> Dict[str, Any]:
        """Get current energy level for a user, applying recharge if needed."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """SELECT energy, energy_recharge_rate, last_energy_update 
                   FROM users WHERE id = ?""",
                (user_id,),
            )
            row = await cursor.fetchone()
            if not row:
                logger.error(f"User {user_id} not found when getting energy")
                return {
                    "energy": 0,
                    "recharge_rate": 1,
                    "last_update": datetime.now(),
                    "max_energy": 100,
                }

            current_energy = row[0] or 100
            recharge_rate = row[1] or 1
            last_update = datetime.fromisoformat(row[2]) if row[2] else datetime.now()

            # Calculate recharge
            now = datetime.now()
            time_diff = now - last_update
            minutes_passed = int(time_diff.total_seconds() / 60)

            if minutes_passed > 0:
                energy_to_add = minutes_passed * recharge_rate
                new_energy = min(100, current_energy + energy_to_add)

                await db.execute(
                    """UPDATE users SET energy = ?, last_energy_update = ? WHERE id = ?""",
                    (new_energy, now.isoformat(), user_id),
                )
                await db.commit()

                logger.info(
                    f"User {user_id} energy recharged: {current_energy} -> {new_energy} (+{energy_to_add} from {minutes_passed} minutes)"
                )
                current_energy = new_energy

            return {
                "energy": current_energy,
                "recharge_rate": recharge_rate,
                "last_update": now,
                "max_energy": 100,
            }

    async def consume_user_energy(
        self, user_id: int, amount: int = 1
    ) -> Dict[str, Any]:
        """Consume energy for a user. Returns updated energy info or error."""
        # Get current energy (this will apply recharge)
        energy_info = await self.get_user_energy(user_id)
        current_energy = energy_info["energy"]

        if current_energy < amount:
            logger.warning(
                f"User {user_id} insufficient energy: {current_energy} < {amount}"
            )
            return {
                "success": False,
                "error": "Insufficient energy",
                "current_energy": current_energy,
                "required_energy": amount,
                "max_energy": 100,
            }

        # Consume energy
        new_energy = current_energy - amount
        now = datetime.now()

        async with self.get_connection() as db:
            await db.execute(
                """UPDATE users SET energy = ?, last_energy_update = ? WHERE id = ?""",
                (new_energy, now.isoformat(), user_id),
            )
            await db.commit()

        logger.info(
            f"User {user_id} consumed {amount} energy: {current_energy} -> {new_energy}"
        )

        return {
            "success": True,
            "energy": new_energy,
            "consumed": amount,
            "recharge_rate": energy_info["recharge_rate"],
            "last_update": now,
            "max_energy": 100,
        }

    async def add_user_energy(self, user_id: int, amount: int) -> Dict[str, Any]:
        """Add energy to a user (admin function)."""
        energy_info = await self.get_user_energy(user_id)
        current_energy = energy_info["energy"]
        new_energy = min(100, current_energy + amount)
        now = datetime.now()

        async with self.get_connection() as db:
            await db.execute(
                """UPDATE users SET energy = ?, last_energy_update = ? WHERE id = ?""",
                (new_energy, now.isoformat(), user_id),
            )
            await db.commit()

        logger.info(
            f"User {user_id} gained {amount} energy: {current_energy} -> {new_energy}"
        )

        return {
            "success": True,
            "energy": new_energy,
            "added": amount,
            "recharge_rate": energy_info["recharge_rate"],
            "last_update": now,
            "max_energy": 100,
        }

    # Message Operations
    async def save_telegram_message(
        self,
        user_id: int,
        message_id: int,
        content: str,
        chat_id: int,
        chat_title: str = None,
        chat_type: str = None,
        sent_at: datetime = None,
    ):
        """Save a Telegram message to the database."""
        async with self.get_connection() as db:
            await db.execute(
                """INSERT INTO telegram_messages 
                   (user_id, message_id, content, chat_id, chat_title, chat_type, sent_at) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    message_id,
                    content,
                    chat_id,
                    chat_title,
                    chat_type,
                    sent_at.isoformat() if sent_at else datetime.now().isoformat(),
                ),
            )
            await db.commit()

    async def get_user_messages(
        self, user_id: int, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get messages for a user."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """SELECT * FROM telegram_messages WHERE user_id = ? 
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (user_id, limit, offset),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # Session Operations
    async def save_telegram_session(self, user_id: int, session_data: str):
        """Save Telegram session data."""
        async with self.get_connection() as db:
            # Check if session exists
            cursor = await db.execute(
                "SELECT id FROM telegram_sessions WHERE user_id = ?", (user_id,)
            )
            existing = await cursor.fetchone()

            if existing:
                # Update existing session
                await db.execute(
                    """UPDATE telegram_sessions SET session_data = ?, updated_at = ? 
                       WHERE user_id = ?""",
                    (session_data, datetime.now().isoformat(), user_id),
                )
            else:
                # Insert new session
                await db.execute(
                    """INSERT INTO telegram_sessions (user_id, session_data) 
                       VALUES (?, ?)""",
                    (user_id, session_data),
                )
            await db.commit()

    async def get_telegram_session(self, user_id: int) -> Optional[str]:
        """Get Telegram session data for a user."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                "SELECT session_data FROM telegram_sessions WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def delete_telegram_session(self, user_id: int):
        """Delete Telegram session data for a user."""
        async with self.get_connection() as db:
            await db.execute(
                "DELETE FROM telegram_sessions WHERE user_id = ?", (user_id,)
            )
            await db.commit()

    # Utility Operations
    async def execute_query(
        self, query: str, params: Tuple = ()
    ) -> List[Dict[str, Any]]:
        """Execute a custom query and return results."""
        async with self.get_connection() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def execute_update(self, query: str, params: Tuple = ()) -> int:
        """Execute an update/insert/delete query and return affected rows."""
        async with self.get_connection() as db:
            cursor = await db.execute(query, params)
            await db.commit()
            return cursor.rowcount


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        database_url = os.getenv("DATABASE_URL", "sqlite:///./app.db")
        database_path = database_url.replace("sqlite:///", "")
        _db_manager = DatabaseManager(database_path)
    return _db_manager


async def init_database_manager():
    """Initialize the database manager and create tables."""
    db_manager = get_database_manager()

    async with db_manager.get_connection() as db:
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

        # Telegram sessions table
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

        await db.commit()

    # Run migration for existing databases
    await migrate_energy_columns(db_manager)


async def migrate_energy_columns(db_manager: DatabaseManager):
    """Add energy columns to existing users table if they don't exist."""
    async with db_manager.get_connection() as db:
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
            await db.execute(
                "ALTER TABLE users ADD COLUMN last_energy_update TIMESTAMP"
            )
            # Update existing users to have current timestamp
            await db.execute(
                "UPDATE users SET last_energy_update = datetime('now') WHERE last_energy_update IS NULL"
            )

        await db.commit()
        logger.info("Energy system database migration completed")
