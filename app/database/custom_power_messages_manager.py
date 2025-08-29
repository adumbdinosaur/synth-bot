"""
Custom power messages database operations.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from .base import BaseDatabaseManager, retry_db_operation

logger = logging.getLogger(__name__)


class CustomPowerMessagesManager(BaseDatabaseManager):
    """Handles all custom power messages database operations."""

    @retry_db_operation()
    async def add_custom_power_message(self, user_id: int, message: str) -> Dict[str, Any]:
        """Add a custom out-of-power message for a user."""
        try:
            async with self.get_connection() as db:
                await db.execute(
                    """INSERT INTO user_custom_power_messages (user_id, message, created_at)
                       VALUES (?, ?, ?)""",
                    (user_id, message.strip(), datetime.now().isoformat()),
                )
                await db.commit()

            return {"success": True, "message": "Custom power message added successfully"}
        except Exception as e:
            logger.error(f"Error adding custom power message for user {user_id}: {e}")
            return {"success": False, "error": str(e)}

    @retry_db_operation()
    async def get_user_custom_power_messages(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all custom out-of-power messages for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """SELECT id, message, is_active, created_at, updated_at 
                       FROM user_custom_power_messages 
                       WHERE user_id = ? 
                       ORDER BY created_at DESC""",
                    (user_id,),
                )
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching custom power messages for user {user_id}: {e}")
            return []

    @retry_db_operation()
    async def get_active_custom_power_messages(self, user_id: int) -> List[str]:
        """Get all active custom out-of-power messages for a user."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """SELECT message FROM user_custom_power_messages 
                       WHERE user_id = ? AND is_active = 1 
                       ORDER BY created_at DESC""",
                    (user_id,),
                )
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error fetching active custom power messages for user {user_id}: {e}")
            return []

    @retry_db_operation()
    async def update_custom_power_message(self, user_id: int, message_id: int, message: str) -> Dict[str, Any]:
        """Update a custom out-of-power message."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """UPDATE user_custom_power_messages 
                       SET message = ?, updated_at = ?
                       WHERE id = ? AND user_id = ?""",
                    (message.strip(), datetime.now().isoformat(), message_id, user_id),
                )
                await db.commit()

                if cursor.rowcount == 0:
                    return {"success": False, "error": "Message not found or access denied"}

                return {"success": True, "message": "Custom power message updated successfully"}
        except Exception as e:
            logger.error(f"Error updating custom power message {message_id} for user {user_id}: {e}")
            return {"success": False, "error": str(e)}

    @retry_db_operation()
    async def toggle_custom_power_message(self, user_id: int, message_id: int, is_active: bool) -> Dict[str, Any]:
        """Toggle the active status of a custom out-of-power message."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """UPDATE user_custom_power_messages 
                       SET is_active = ?, updated_at = ?
                       WHERE id = ? AND user_id = ?""",
                    (is_active, datetime.now().isoformat(), message_id, user_id),
                )
                await db.commit()

                if cursor.rowcount == 0:
                    return {"success": False, "error": "Message not found or access denied"}

                status = "activated" if is_active else "deactivated"
                return {"success": True, "message": f"Custom power message {status} successfully"}
        except Exception as e:
            logger.error(f"Error toggling custom power message {message_id} for user {user_id}: {e}")
            return {"success": False, "error": str(e)}

    @retry_db_operation()
    async def delete_custom_power_message(self, user_id: int, message_id: int) -> Dict[str, Any]:
        """Delete a custom out-of-power message."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """DELETE FROM user_custom_power_messages 
                       WHERE id = ? AND user_id = ?""",
                    (message_id, user_id),
                )
                await db.commit()

                if cursor.rowcount == 0:
                    return {"success": False, "error": "Message not found or access denied"}

                return {"success": True, "message": "Custom power message deleted successfully"}
        except Exception as e:
            logger.error(f"Error deleting custom power message {message_id} for user {user_id}: {e}")
            return {"success": False, "error": str(e)}

    async def get_random_custom_power_message(self, user_id: int) -> Optional[str]:
        """Get a random active custom out-of-power message for a user."""
        import random
        
        active_messages = await self.get_active_custom_power_messages(user_id)
        if active_messages:
            return random.choice(active_messages)
        return None

    async def get_custom_power_message_count(self, user_id: int) -> Dict[str, int]:
        """Get the count of custom power messages for a user."""
        try:
            async with self.get_connection() as db:
                # Get total count
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM user_custom_power_messages WHERE user_id = ?",
                    (user_id,),
                )
                total_count = (await cursor.fetchone())[0]

                # Get active count
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM user_custom_power_messages WHERE user_id = ? AND is_active = 1",
                    (user_id,),
                )
                active_count = (await cursor.fetchone())[0]

                return {
                    "total": total_count,
                    "active": active_count,
                    "inactive": total_count - active_count
                }
        except Exception as e:
            logger.error(f"Error getting custom power message count for user {user_id}: {e}")
            return {"total": 0, "active": 0, "inactive": 0}
