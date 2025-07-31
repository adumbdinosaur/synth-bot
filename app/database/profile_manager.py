"""
Profile protection database operations.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from .base import BaseDatabaseManager, retry_db_operation

logger = logging.getLogger(__name__)


class ProfileManager(BaseDatabaseManager):
    """Handles all profile protection database operations."""

    @retry_db_operation()
    async def init_user_profile_protection(self, user_id: int) -> bool:
        """Initialize profile protection settings for a user."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """INSERT OR IGNORE INTO user_profile_protection 
                       (user_id, profile_protection_enabled, profile_change_penalty)
                       VALUES (?, TRUE, ?)""",
                    (user_id, 10),
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error initializing profile protection for user {user_id}: {e}")
            return False

    @retry_db_operation()
    async def set_profile_change_penalty(self, user_id: int, penalty: int) -> bool:
        """Set the energy penalty for profile changes."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """INSERT OR REPLACE INTO user_profile_protection 
                       (user_id, profile_change_penalty, updated_at)
                       VALUES (?, ?, ?)""",
                    (user_id, penalty, datetime.now().isoformat()),
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error setting profile change penalty for user {user_id}: {e}")
            return False

    async def get_profile_change_penalty(self, user_id: int) -> int:
        """Get the energy penalty for profile changes."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "SELECT profile_change_penalty FROM user_profile_protection WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()
                return row[0] if row else 10  # Default penalty
        except Exception as e:
            logger.error(f"Error getting profile change penalty for user {user_id}: {e}")
            return 10

    async def get_profile_protection_settings(self, user_id: int) -> Dict[str, Any]:
        """Get all profile protection settings for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """SELECT profile_protection_enabled, profile_change_penalty,
                              original_first_name, original_last_name, original_bio,
                              original_profile_photo_id, profile_locked_at
                       FROM user_profile_protection WHERE user_id = ?""",
                    (user_id,),
                )
                row = await cursor.fetchone()
                if row:
                    return {
                        "profile_protection_enabled": row[0],
                        "profile_change_penalty": row[1],
                        "original_first_name": row[2],
                        "original_last_name": row[3],
                        "original_bio": row[4],
                        "original_profile_photo_id": row[5],
                        "profile_locked_at": row[6],
                    }
                else:
                    # Return default settings if none exist
                    return {
                        "profile_protection_enabled": False,
                        "profile_change_penalty": 10,
                        "original_first_name": None,
                        "original_last_name": None,
                        "original_bio": None,
                        "original_profile_photo_id": None,
                        "profile_locked_at": None,
                    }
        except Exception as e:
            logger.error(f"Error getting profile protection settings for user {user_id}: {e}")
            return {}

    @retry_db_operation()
    async def store_original_profile(
        self,
        user_id: int,
        first_name: str = "",
        last_name: str = "",
        bio: str = "",
        profile_photo_id: str = None,
    ) -> bool:
        """Store the user's original profile data."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """INSERT OR REPLACE INTO user_profile_protection 
                       (user_id, profile_protection_enabled, profile_change_penalty,
                        original_first_name, original_last_name, original_bio,
                        original_profile_photo_id, profile_locked_at, updated_at)
                       VALUES (?, TRUE, 
                               COALESCE((SELECT profile_change_penalty FROM user_profile_protection WHERE user_id = ?), 10),
                               ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                    (user_id, user_id, first_name, last_name, bio, profile_photo_id),
                )
                await db.commit()
                logger.info(f"Stored original profile for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error storing original profile for user {user_id}: {e}")
            return False

    @retry_db_operation()
    async def lock_user_profile(self, user_id: int) -> bool:
        """Lock a user's profile for protection."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """UPDATE user_profile_protection 
                       SET profile_locked_at = datetime('now'),
                           updated_at = datetime('now')
                       WHERE user_id = ?""",
                    (user_id,),
                )
                await db.commit()
                
                # If no row was updated, create one
                if db.total_changes == 0:
                    await db.execute(
                        """INSERT INTO user_profile_protection 
                           (user_id, profile_protection_enabled, profile_change_penalty, profile_locked_at)
                           VALUES (?, TRUE, 10, datetime('now'))""",
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

    @retry_db_operation()
    async def clear_profile_lock(self, user_id: int) -> bool:
        """Clear the profile lock for a user."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """UPDATE user_profile_protection 
                       SET profile_locked_at = NULL,
                           updated_at = datetime('now')
                       WHERE user_id = ?""",
                    (user_id,),
                )
                await db.commit()
                logger.info(f"Cleared profile lock for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error clearing profile lock for user {user_id}: {e}")
            return False

    @retry_db_operation()
    async def update_saved_profile_state(
        self,
        user_id: int,
        first_name: str = "",
        last_name: str = "",
        bio: str = "",
        profile_photo_id: str = None,
    ) -> bool:
        """Update the saved profile state (what we consider 'original')."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """UPDATE user_profile_protection 
                       SET original_first_name = ?, original_last_name = ?, 
                           original_bio = ?, original_profile_photo_id = ?,
                           updated_at = datetime('now')
                       WHERE user_id = ?""",
                    (first_name, last_name, bio, profile_photo_id, user_id),
                )
                await db.commit()
                
                if db.total_changes == 0:
                    # Create record if it doesn't exist
                    await db.execute(
                        """INSERT INTO user_profile_protection 
                           (user_id, profile_protection_enabled, profile_change_penalty,
                            original_first_name, original_last_name, original_bio,
                            original_profile_photo_id)
                           VALUES (?, TRUE, 10, ?, ?, ?, ?)""",
                        (user_id, first_name, last_name, bio, profile_photo_id),
                    )
                    await db.commit()
                
                logger.info(f"Updated saved profile state for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error updating saved profile state for user {user_id}: {e}")
            return False

    # Profile revert cost management
    async def get_profile_revert_cost(self, user_id: int) -> int:
        """Get the energy cost for reverting profile changes."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "SELECT revert_cost FROM user_profile_revert_costs WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()
                return row[0] if row else 15  # Default cost
        except Exception as e:
            logger.error(f"Error getting profile revert cost for user {user_id}: {e}")
            return 15

    @retry_db_operation()
    async def set_profile_revert_cost(self, user_id: int, cost: int) -> bool:
        """Set the energy cost for reverting profile changes."""
        try:
            if not (0 <= cost <= 100):
                logger.error(f"Invalid revert cost {cost} for user {user_id}. Must be 0-100.")
                return False

            async with self.get_connection() as db:
                await db.execute(
                    """INSERT OR REPLACE INTO user_profile_revert_costs 
                       (user_id, revert_cost, updated_at)
                       VALUES (?, ?, ?)""",
                    (user_id, cost, datetime.now().isoformat()),
                )
                await db.commit()
                logger.info(f"Set profile revert cost to {cost} for user {user_id}")
                return True
        except Exception as e:
            logger.error(f"Error setting profile revert cost for user {user_id}: {e}")
            return False
