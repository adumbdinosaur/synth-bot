import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from contextlib import asynccontextmanager
import aiosqlite
import os
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
                raise
            raise last_exception

        return wrapper

    return decorator


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
                """INSERT INTO users (username, email, hashed_password, energy, max_energy, energy_recharge_rate, last_energy_update) 
                   VALUES (?, ?, ?, 100, 100, 1, ?)""",
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
                """SELECT energy, energy_recharge_rate, last_energy_update, max_energy
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

            current_energy = row[0] if row[0] is not None else 100
            recharge_rate = row[1] if row[1] is not None else 1
            last_update = datetime.fromisoformat(row[2]) if row[2] else datetime.now()
            max_energy = row[3] if row[3] is not None else 1000

            # Calculate recharge
            now = datetime.now()
            time_diff = now - last_update
            minutes_passed = int(time_diff.total_seconds() / 60)

            if minutes_passed > 0:
                energy_to_add = minutes_passed * recharge_rate
                new_energy = min(max_energy, current_energy + energy_to_add)

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
                "max_energy": max_energy,
            }

    async def consume_user_energy(
        self, user_id: int, amount: int = 1
    ) -> Dict[str, Any]:
        """Consume energy for a user. Returns updated energy info or error."""
        # Get current energy (this will apply recharge)
        energy_info = await self.get_user_energy(user_id)
        current_energy = energy_info["energy"]
        max_energy = energy_info["max_energy"]

        if current_energy < amount:
            logger.warning(
                f"User {user_id} insufficient energy: {current_energy} < {amount}"
            )
            return {
                "success": False,
                "error": "Insufficient energy",
                "current_energy": current_energy,
                "required_energy": amount,
                "max_energy": max_energy,
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
            "max_energy": max_energy,
        }

    async def add_user_energy(self, user_id: int, amount: int) -> Dict[str, Any]:
        """Add energy to a user (admin function)."""
        energy_info = await self.get_user_energy(user_id)
        current_energy = energy_info["energy"]
        max_energy = energy_info["max_energy"]
        new_energy = min(max_energy, current_energy + amount)
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
            "max_energy": max_energy,
        }

    async def update_user_energy_recharge_rate(
        self, user_id: int, recharge_rate: int
    ) -> Dict[str, Any]:
        """Update the energy recharge rate for a user."""
        if recharge_rate < 0 or recharge_rate > 10:
            return {
                "success": False,
                "error": "Recharge rate must be between 0 and 10 energy per minute",
            }

        async with self.get_connection() as db:
            # First check if user exists
            cursor = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
            if not await cursor.fetchone():
                return {
                    "success": False,
                    "error": "User not found",
                }

            # Update the recharge rate
            await db.execute(
                """UPDATE users SET energy_recharge_rate = ? WHERE id = ?""",
                (recharge_rate, user_id),
            )
            await db.commit()

        logger.info(f"User {user_id} energy recharge rate updated to {recharge_rate}")

        return {
            "success": True,
            "recharge_rate": recharge_rate,
            "message": f"Energy recharge rate updated to {recharge_rate} energy per minute",
        }

    async def update_user_max_energy(
        self, user_id: int, max_energy: int
    ) -> Dict[str, Any]:
        """Update the maximum energy for a user."""
        if max_energy < 10 or max_energy > 1000:
            return {
                "success": False,
                "error": "Maximum energy must be between 10 and 1000",
            }

        async with self.get_connection() as db:
            # First check if user exists
            cursor = await db.execute(
                "SELECT id, energy FROM users WHERE id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return {
                    "success": False,
                    "error": "User not found",
                }

            current_energy = row[1]
            # If current energy exceeds new max, cap it
            new_current_energy = min(current_energy, max_energy)

            # Update the max energy and current energy if needed
            await db.execute(
                """UPDATE users SET max_energy = ?, energy = ?, last_energy_update = ? WHERE id = ?""",
                (max_energy, new_current_energy, datetime.now().isoformat(), user_id),
            )
            await db.commit()

        logger.info(
            f"User {user_id} max energy updated to {max_energy}, current energy adjusted to {new_current_energy}"
        )

        return {
            "success": True,
            "max_energy": max_energy,
            "current_energy": new_current_energy,
            "message": f"Maximum energy updated to {max_energy}",
        }

    async def remove_user_energy(self, user_id: int, amount: int) -> Dict[str, Any]:
        """Remove energy from a user (admin function)."""
        if amount <= 0:
            return {
                "success": False,
                "error": "Amount must be positive",
            }

        energy_info = await self.get_user_energy(user_id)
        current_energy = energy_info["energy"]
        max_energy = energy_info["max_energy"]
        new_energy = max(0, current_energy - amount)
        now = datetime.now()

        async with self.get_connection() as db:
            await db.execute(
                """UPDATE users SET energy = ?, last_energy_update = ? WHERE id = ?""",
                (new_energy, now.isoformat(), user_id),
            )
            await db.commit()

        logger.info(
            f"User {user_id} lost {amount} energy: {current_energy} -> {new_energy}"
        )

        return {
            "success": True,
            "energy": new_energy,
            "removed": amount,
            "recharge_rate": energy_info["recharge_rate"],
            "last_update": now,
            "max_energy": max_energy,
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

    # Energy Costs Operations
    async def get_user_energy_costs(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all energy costs for a user."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """SELECT message_type, energy_cost, description 
                   FROM user_message_energy_costs 
                   WHERE user_id = ? 
                   ORDER BY message_type""",
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_message_energy_cost(self, user_id: int, message_type: str) -> int:
        """Get energy cost for a specific message type for a user."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """SELECT energy_cost FROM user_message_energy_costs 
                   WHERE user_id = ? AND message_type = ?""",
                (user_id, message_type),
            )
            row = await cursor.fetchone()
            # Return configured cost or default to 1 if not found
            return row[0] if row else 1

    async def update_user_energy_cost(
        self, user_id: int, message_type: str, energy_cost: int, description: str = None
    ):
        """Update or insert energy cost for a user and message type."""
        async with self.get_connection() as db:
            await db.execute(
                """INSERT OR REPLACE INTO user_message_energy_costs 
                   (user_id, message_type, energy_cost, description, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    user_id,
                    message_type,
                    energy_cost,
                    description,
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()

    async def init_user_energy_costs(self, user_id: int):
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

        async with self.get_connection() as db:
            # Check if user already has energy costs
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
                        INSERT INTO user_message_energy_costs 
                        (user_id, message_type, energy_cost, description)
                        VALUES (?, ?, ?, ?)
                    """,
                        (user_id, message_type, energy_cost, description),
                    )

                await db.commit()
                logger.info(f"Initialized default energy costs for user {user_id}")

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

    # Profile Protection Operations
    async def init_user_profile_protection(self, user_id: int) -> bool:
        """Initialize default profile protection settings for a new user."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO user_profile_protection 
                    (user_id, profile_change_penalty)
                    VALUES (?, ?)
                """,
                    (user_id, 10),  # Default penalty of 10 energy points
                )
                await db.commit()
                logger.info(
                    f"Initialized default profile protection for new user {user_id}"
                )
                return True
        except Exception as e:
            logger.error(
                f"Error initializing profile protection for user {user_id}: {e}"
            )
            return False

    async def set_profile_change_penalty(self, user_id: int, penalty: int) -> bool:
        """Set the energy penalty for profile changes."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO user_profile_protection 
                    (user_id, profile_change_penalty, updated_at)
                    VALUES (?, ?, datetime('now'))
                    """,
                    (user_id, penalty),
                )
                await db.commit()
                logger.info(
                    f"Set profile change penalty to {penalty} for user {user_id}"
                )
                return True
        except Exception as e:
            logger.error(
                f"Error setting profile change penalty for user {user_id}: {e}"
            )
            return False

    async def get_profile_change_penalty(self, user_id: int) -> int:
        """Get the energy penalty for profile changes. Returns default of 10 if not set."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "SELECT profile_change_penalty FROM user_profile_protection WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()
                return row[0] if row else 10  # Default penalty
        except Exception as e:
            logger.error(
                f"Error getting profile change penalty for user {user_id}: {e}"
            )
            return 10  # Default penalty

    async def get_profile_protection_settings(self, user_id: int) -> Dict[str, Any]:
        """Get profile protection settings for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """SELECT profile_change_penalty, original_first_name, original_last_name, 
                              original_bio, original_profile_photo_id, profile_locked_at
                       FROM user_profile_protection WHERE user_id = ?""",
                    (user_id,),
                )
                row = await cursor.fetchone()
                if row:
                    return {
                        "profile_protection_enabled": True,
                        "profile_change_penalty": row[0],
                        "original_first_name": row[1],
                        "original_last_name": row[2],
                        "original_bio": row[3],
                        "original_profile_photo_id": row[4],
                        "profile_locked_at": row[5],
                    }
                else:
                    return {
                        "profile_protection_enabled": False,
                        "profile_change_penalty": 10,
                    }
        except Exception as e:
            logger.error(
                f"Error getting profile protection settings for user {user_id}: {e}"
            )
            return {
                "profile_protection_enabled": False,
                "profile_change_penalty": 10,
            }

    async def store_original_profile(
        self,
        user_id: int,
        profile_data: Dict[str, Any] = None,
        first_name: str = None,
        last_name: str = None,
        bio: str = None,
        profile_photo_id: str = None,
    ) -> bool:
        """Store the user's original profile data when session starts."""
        try:
            # Handle both calling methods:
            # 1. store_original_profile(user_id, profile_dict)
            # 2. store_original_profile(user_id, first_name=..., last_name=..., ...)
            if profile_data is not None:
                # Called with dictionary
                first_name = profile_data.get("first_name")
                last_name = profile_data.get("last_name")
                bio = profile_data.get("bio")
                profile_photo_id = profile_data.get("profile_photo_id")

            async with self.get_connection() as db:
                # Check if record exists
                cursor = await db.execute(
                    "SELECT id FROM user_profile_protection WHERE user_id = ?",
                    (user_id,),
                )
                exists = await cursor.fetchone()

                if exists:
                    # Update existing record
                    await db.execute(
                        """
                        UPDATE user_profile_protection 
                        SET original_first_name = COALESCE(?, original_first_name),
                            original_last_name = COALESCE(?, original_last_name),
                            original_bio = COALESCE(?, original_bio),
                            original_profile_photo_id = COALESCE(?, original_profile_photo_id),
                            profile_locked_at = datetime('now'),
                            updated_at = datetime('now')
                        WHERE user_id = ?
                        """,
                        (first_name, last_name, bio, profile_photo_id, user_id),
                    )
                else:
                    # Insert new record
                    await db.execute(
                        """
                        INSERT INTO user_profile_protection 
                        (user_id, original_first_name, original_last_name, original_bio, 
                         original_profile_photo_id, profile_locked_at)
                        VALUES (?, ?, ?, ?, ?, datetime('now'))
                        """,
                        (user_id, first_name, last_name, bio, profile_photo_id),
                    )

                await db.commit()
                logger.info(f"Stored original profile data for user {user_id}")
                return True

        except Exception as e:
            logger.error(f"Error storing original profile for user {user_id}: {e}")
            return False

    async def lock_user_profile(self, user_id: int) -> bool:
        """Lock the user's profile for protection."""
        try:
            async with self.get_connection() as db:
                # Update or insert profile protection record with lock timestamp
                cursor = await db.execute(
                    "SELECT id FROM user_profile_protection WHERE user_id = ?",
                    (user_id,),
                )
                exists = await cursor.fetchone()

                if exists:
                    # Update existing record
                    await db.execute(
                        """
                        UPDATE user_profile_protection 
                        SET profile_locked_at = datetime('now'),
                            updated_at = datetime('now')
                        WHERE user_id = ?
                        """,
                        (user_id,),
                    )
                else:
                    # Insert new record
                    await db.execute(
                        """
                        INSERT INTO user_profile_protection 
                        (user_id, profile_locked_at)
                        VALUES (?, datetime('now'))
                        """,
                        (user_id,),
                    )

                await db.commit()
                logger.info(f"Locked profile for user {user_id}")
                return True

        except Exception as e:
            logger.error(f"Error locking profile for user {user_id}: {e}")
            return False

    async def is_profile_locked(self, user_id: int) -> bool:
        """Check if the user's profile is locked for protection."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "SELECT profile_locked_at FROM user_profile_protection WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()
                return row is not None and row[0] is not None
        except Exception as e:
            logger.error(f"Error checking profile lock for user {user_id}: {e}")
            return False

    async def get_original_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get the user's original profile data."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """SELECT original_first_name, original_last_name, original_bio, 
                              original_profile_photo_id, profile_locked_at
                       FROM user_profile_protection WHERE user_id = ?""",
                    (user_id,),
                )
                row = await cursor.fetchone()
                if row:
                    return {
                        "first_name": row[0],
                        "last_name": row[1],
                        "bio": row[2],
                        "profile_photo_id": row[3],
                        "locked_at": row[4],
                    }
                return None
        except Exception as e:
            logger.error(f"Error getting original profile for user {user_id}: {e}")
            return None

    async def clear_profile_lock(self, user_id: int) -> bool:
        """Clear the profile lock for a user."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """
                    UPDATE user_profile_protection 
                    SET profile_locked_at = NULL,
                        updated_at = datetime('now')
                    WHERE user_id = ?
                    """,
                    (user_id,),
                )
                await db.commit()
                logger.info(f"Cleared profile lock for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error clearing profile lock for user {user_id}: {e}")
            return False

    async def update_saved_profile_state(
        self,
        user_id: int,
        first_name: str = None,
        last_name: str = None,
        bio: str = None,
        profile_photo_id: str = None,
    ) -> bool:
        """Update the saved profile state (what the system remembers as 'original')."""
        try:
            async with self.get_connection() as db:
                # Get current profile protection record
                cursor = await db.execute(
                    "SELECT id FROM user_profile_protection WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()

                if row:
                    # Update existing record
                    update_fields = []
                    update_values = []

                    if first_name is not None:
                        update_fields.append("original_first_name = ?")
                        update_values.append(first_name)
                    if last_name is not None:
                        update_fields.append("original_last_name = ?")
                        update_values.append(last_name)
                    if bio is not None:
                        update_fields.append("original_bio = ?")
                        update_values.append(bio)
                    if profile_photo_id is not None:
                        update_fields.append("original_profile_photo_id = ?")
                        update_values.append(profile_photo_id)

                    if update_fields:
                        update_fields.append("updated_at = datetime('now')")
                        update_values.append(user_id)

                        query = f"""
                            UPDATE user_profile_protection 
                            SET {", ".join(update_fields)}
                            WHERE user_id = ?
                        """
                        await db.execute(query, update_values)
                else:
                    # Create new record
                    await db.execute(
                        """INSERT INTO user_profile_protection 
                           (user_id, original_first_name, original_last_name, original_bio, 
                            original_profile_photo_id, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                        (
                            user_id,
                            first_name or "",
                            last_name or "",
                            bio or "",
                            profile_photo_id,
                        ),
                    )

                await db.commit()
                logger.info(f"Updated saved profile state for user {user_id}")
                return True

        except Exception as e:
            logger.error(f"Error updating saved profile state for user {user_id}: {e}")
            return False

    async def get_profile_revert_cost(self, user_id: int) -> int:
        """Get the energy cost for reverting profile changes for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "SELECT profile_change_penalty FROM user_profile_protection WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()
                return row[0] if row and row[0] is not None else 10  # Default cost
        except Exception as e:
            logger.error(f"Error getting profile revert cost for user {user_id}: {e}")
            return 10  # Default cost

    async def set_profile_revert_cost(self, user_id: int, cost: int) -> bool:
        """Set the energy cost for reverting profile changes for a user."""
        try:
            async with self.get_connection() as db:
                # Check if record exists
                cursor = await db.execute(
                    "SELECT id FROM user_profile_protection WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()

                if row:
                    # Update existing record
                    await db.execute(
                        """UPDATE user_profile_protection 
                           SET profile_change_penalty = ?, updated_at = datetime('now')
                           WHERE user_id = ?""",
                        (cost, user_id),
                    )
                else:
                    # Create new record
                    await db.execute(
                        """INSERT INTO user_profile_protection 
                           (user_id, profile_change_penalty, created_at, updated_at)
                           VALUES (?, ?, datetime('now'), datetime('now'))""",
                        (user_id, cost),
                    )

                await db.commit()
                logger.info(f"Set profile revert cost to {cost} for user {user_id}")
                return True

        except Exception as e:
            logger.error(f"Error setting profile revert cost for user {user_id}: {e}")
            return False

    # Badwords Operations
    async def get_user_badwords(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all badwords for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """SELECT id, word, penalty, case_sensitive, created_at 
                       FROM user_badwords WHERE user_id = ? ORDER BY word""",
                    (user_id,),
                )
                rows = await cursor.fetchall()
                return [
                    {
                        "id": row[0],
                        "word": row[1],
                        "penalty": row[2],
                        "case_sensitive": bool(row[3]),
                        "created_at": row[4],
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Error getting badwords for user {user_id}: {e}")
            return []

    async def add_badword(
        self, user_id: int, word: str, penalty: int = 5, case_sensitive: bool = False
    ) -> bool:
        """Add a badword for a user."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """INSERT OR REPLACE INTO user_badwords 
                       (user_id, word, penalty, case_sensitive, updated_at) 
                       VALUES (?, ?, ?, ?, datetime('now'))""",
                    (user_id, word.strip(), penalty, case_sensitive),
                )
                await db.commit()
                logger.info(
                    f"Added badword '{word}' for user {user_id} with penalty {penalty}"
                )
                return True
        except Exception as e:
            logger.error(f"Error adding badword for user {user_id}: {e}")
            return False

    async def remove_badword(self, user_id: int, word: str) -> bool:
        """Remove a badword for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "DELETE FROM user_badwords WHERE user_id = ? AND word = ?",
                    (user_id, word),
                )
                await db.commit()
                if cursor.rowcount > 0:
                    logger.info(f"Removed badword '{word}' for user {user_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error removing badword for user {user_id}: {e}")
            return False

    async def update_badword_penalty(
        self, user_id: int, word: str, penalty: int
    ) -> bool:
        """Update the penalty for a specific badword."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """UPDATE user_badwords SET penalty = ?, updated_at = datetime('now') 
                       WHERE user_id = ? AND word = ?""",
                    (penalty, user_id, word),
                )
                await db.commit()
                if cursor.rowcount > 0:
                    logger.info(
                        f"Updated penalty for badword '{word}' to {penalty} for user {user_id}"
                    )
                    return True
                return False
        except Exception as e:
            logger.error(f"Error updating badword penalty for user {user_id}: {e}")
            return False

    async def check_for_badwords(
        self, user_id: int, message_text: str
    ) -> List[Dict[str, Any]]:
        """Check if message contains any badwords and return list of violations."""
        try:
            badwords = await self.get_user_badwords(user_id)
            violations = []

            if not badwords or not message_text:
                return violations

            # Check each badword
            for badword_info in badwords:
                word = badword_info["word"]
                penalty = badword_info["penalty"]
                case_sensitive = badword_info["case_sensitive"]

                # Determine if word is found in message
                if case_sensitive:
                    found = word in message_text
                else:
                    found = word.lower() in message_text.lower()

                if found:
                    violations.append(
                        {
                            "word": word,
                            "penalty": penalty,
                            "case_sensitive": case_sensitive,
                        }
                    )

            return violations
        except Exception as e:
            logger.error(f"Error checking for badwords for user {user_id}: {e}")
            return []

    async def filter_badwords_from_message(
        self, user_id: int, message_text: str
    ) -> Dict[str, Any]:
        """Filter badwords from message text and return filtered message with violation info."""
        try:
            badwords = await self.get_user_badwords(user_id)

            if not badwords or not message_text:
                return {
                    "filtered_message": message_text,
                    "violations": [],
                    "total_penalty": 0,
                    "has_violations": False,
                }

            filtered_message = message_text
            violations = []

            # Process each badword
            for badword_info in badwords:
                word = badword_info["word"]
                penalty = badword_info["penalty"]
                case_sensitive = badword_info["case_sensitive"]

                # Replace the badword with <redacted>
                if case_sensitive:
                    if word in filtered_message:
                        filtered_message = filtered_message.replace(word, "<redacted>")
                        violations.append(
                            {
                                "word": word,
                                "penalty": penalty,
                                "case_sensitive": case_sensitive,
                            }
                        )
                else:
                    # Case insensitive replacement - we need to find all occurrences
                    import re

                    pattern = re.compile(re.escape(word), re.IGNORECASE)
                    matches = pattern.findall(filtered_message)
                    if matches:
                        filtered_message = pattern.sub("<redacted>", filtered_message)
                        violations.append(
                            {
                                "word": word,
                                "penalty": penalty,
                                "case_sensitive": case_sensitive,
                            }
                        )

            total_penalty = sum(v["penalty"] for v in violations)

            return {
                "filtered_message": filtered_message,
                "violations": violations,
                "total_penalty": total_penalty,
                "has_violations": len(violations) > 0,
            }

        except Exception as e:
            logger.error(f"Error filtering badwords for user {user_id}: {e}")
            return {
                "filtered_message": message_text,
                "violations": [],
                "total_penalty": 0,
                "has_violations": False,
            }

    # Active Sessions Operations
    async def get_all_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all users with active Telegram sessions."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """
                    SELECT u.id, u.username, u.telegram_connected, 
                           u.energy, u.energy_recharge_rate, u.last_energy_update, u.created_at,
                           ts.session_data, ts.updated_at as session_updated_at
                    FROM users u
                    LEFT JOIN telegram_sessions ts ON u.id = ts.user_id
                    WHERE u.telegram_connected = 1
                    ORDER BY ts.updated_at DESC NULLS LAST, u.username
                    """
                )
                rows = await cursor.fetchall()

                active_sessions = []
                for row in rows:
                    # Calculate current energy with recharge
                    current_energy = row[3] if row[3] is not None else 100
                    recharge_rate = row[4] if row[4] is not None else 1
                    last_update = (
                        datetime.fromisoformat(row[5]) if row[5] else datetime.now()
                    )

                    # Calculate recharge
                    now = datetime.now()
                    time_diff = (now - last_update).total_seconds()
                    energy_to_add = (
                        int(time_diff // 60) * recharge_rate
                    )  # recharge per minute
                    current_energy = min(100, current_energy + energy_to_add)

                    session_info = {
                        "user_id": row[0],
                        "username": row[1],
                        "telegram_connected": bool(row[2]),
                        "energy": current_energy,
                        "energy_recharge_rate": recharge_rate,
                        "last_energy_update": row[5],
                        "account_created": row[6],
                        "has_session_data": bool(row[7]),
                        "session_last_updated": row[8],
                        "display_name": row[1],  # Using username as display name
                        "session_active": bool(
                            row[7]
                        ),  # Consider active if has session data
                    }
                    active_sessions.append(session_info)

                return active_sessions

        except Exception as e:
            logger.error(f"Error getting all active sessions: {e}")
            return []

    async def set_user_energy(self, user_id: int, energy: int) -> Dict[str, Any]:
        """Set user's energy level, respecting max_energy limit."""
        try:
            # Get current energy info to check max_energy
            energy_info = await self.get_user_energy(user_id)
            max_energy = energy_info["max_energy"]

            # Clamp energy to valid range
            if energy < 0:
                energy = 0
            elif energy > max_energy:
                energy = max_energy

            async with self.get_connection() as db:
                await db.execute(
                    """
                    UPDATE users 
                    SET energy = ?, last_energy_update = ?
                    WHERE id = ?
                    """,
                    (energy, datetime.now().isoformat(), user_id),
                )
                await db.commit()

            logger.info(
                f"Set energy to {energy} for user {user_id} (max: {max_energy})"
            )

            return {
                "success": True,
                "energy": energy,
                "max_energy": max_energy,
                "recharge_rate": energy_info["recharge_rate"],
                "last_update": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error setting energy for user {user_id}: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    # Autocorrect Settings Operations
    @retry_db_operation()
    async def get_autocorrect_settings(self, user_id: int) -> Dict[str, Any]:
        """Get autocorrect settings for a user."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM user_autocorrect_settings WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            else:
                # Return default settings if none exist
                return {
                    "user_id": user_id,
                    "enabled": False,
                    "penalty_per_correction": 5,
                }

    @retry_db_operation()
    async def update_autocorrect_settings(
        self, user_id: int, enabled: bool, penalty_per_correction: int
    ):
        """Update autocorrect settings for a user."""
        async with self.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO user_autocorrect_settings 
                (user_id, enabled, penalty_per_correction, updated_at)
                VALUES (?, ?, ?, ?)
            """,
                (user_id, enabled, penalty_per_correction, datetime.now().isoformat()),
            )
            await db.commit()

    @retry_db_operation()
    async def log_autocorrect_usage(
        self, user_id: int, original_text: str, corrected_text: str, corrections_count: int
    ):
        """Log autocorrect usage for analytics (optional)."""
        # For now, we'll just log this to the logger, but we could add a table for this later
        logger.info(f"Autocorrect used for user {user_id}: {corrections_count} corrections made")


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
                max_energy INTEGER DEFAULT 100,
                energy_recharge_rate INTEGER DEFAULT 1,
                last_energy_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add max_energy column to existing users table if it doesn't exist
        try:
            await db.execute(
                "ALTER TABLE users ADD COLUMN max_energy INTEGER DEFAULT 100"
            )
            await db.commit()
        except Exception:
            # Column already exists, which is fine
            pass

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

        # User message energy costs table (configurable costs per user)
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

        # User profile protection table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_profile_protection (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                profile_change_penalty INTEGER DEFAULT 10,
                original_first_name VARCHAR(50),
                original_last_name VARCHAR(50),
                original_bio TEXT,
                original_profile_photo_id TEXT,
                profile_locked_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

        # User badwords table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_badwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                word VARCHAR(255) NOT NULL,
                penalty INTEGER DEFAULT 5,
                case_sensitive BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, word)
            )
        """)

        # User autocorrect settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_autocorrect_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                enabled BOOLEAN DEFAULT FALSE,
                penalty_per_correction INTEGER DEFAULT 5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id)
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

    # Autocorrect Settings Operations
    @retry_db_operation()
    async def get_autocorrect_settings(self, user_id: int) -> Dict[str, Any]:
        """Get autocorrect settings for a user."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM user_autocorrect_settings WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            else:
                # Return default settings if none exist
                return {
                    "user_id": user_id,
                    "enabled": False,
                    "penalty_per_correction": 5,
                }

    @retry_db_operation()
    async def update_autocorrect_settings(
        self, user_id: int, enabled: bool, penalty_per_correction: int
    ):
        """Update autocorrect settings for a user."""
        async with self.get_connection() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO user_autocorrect_settings 
                (user_id, enabled, penalty_per_correction, updated_at)
                VALUES (?, ?, ?, ?)
            """,
                (user_id, enabled, penalty_per_correction, datetime.now().isoformat()),
            )
            await db.commit()

    @retry_db_operation()
    async def log_autocorrect_usage(
        self, user_id: int, original_text: str, corrected_text: str, corrections_count: int
    ):
        """Log autocorrect usage for analytics (optional)."""
        # For now, we'll just log this to the logger, but we could add a table for this later
        logger.info(f"Autocorrect used for user {user_id}: {corrections_count} corrections made")


# Standalone functions for backward compatibility
@asynccontextmanager
async def get_db_connection():
    """Get a database connection with proper locking - standalone function for compatibility."""
    db_manager = get_database_manager()
    async with db_manager.get_connection() as db:
        yield db


async def get_db():
    """Get database connection for FastAPI dependency injection."""
    async with get_db_connection() as db:
        yield db


async def init_user_profile_protection(user_id: int):
    """Initialize default profile protection settings for a new user - standalone function."""
    db_manager = get_database_manager()
    return await db_manager.init_user_profile_protection(user_id)
