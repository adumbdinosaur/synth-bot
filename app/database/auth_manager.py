"""
Authentication and invite code database operations.
"""

import logging
from datetime import datetime
from .base import BaseDatabaseManager, retry_db_operation

logger = logging.getLogger(__name__)


class AuthManager(BaseDatabaseManager):
    """Handles authentication and invite code database operations."""

    async def validate_invite_code(self, code: str) -> bool:
        """Validate an invite code."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """SELECT id, max_uses, current_uses, is_active 
                   FROM invite_codes 
                   WHERE code = ? AND is_active = TRUE""",
                (code,),
            )
            invite_data = await cursor.fetchone()

            if not invite_data:
                return False

            max_uses = invite_data[1]
            current_uses = invite_data[2]

            # If max_uses is None, unlimited uses allowed
            if max_uses is None:
                return True

            # Check if we haven't exceeded the max uses
            return current_uses < max_uses

    @retry_db_operation()
    async def use_invite_code(self, code: str) -> bool:
        """Mark an invite code as used (increment usage count)."""
        try:
            async with self.get_connection() as db:
                # First validate the code
                cursor = await db.execute(
                    """SELECT id, max_uses, current_uses, is_active 
                       FROM invite_codes 
                       WHERE code = ? AND is_active = TRUE""",
                    (code,),
                )
                invite_data = await cursor.fetchone()

                if not invite_data:
                    logger.warning(f"Attempted to use invalid invite code: {code}")
                    return False

                invite_id, max_uses, current_uses, is_active = invite_data

                # Check if we can still use this code
                if max_uses is not None and current_uses >= max_uses:
                    logger.warning(f"Invite code {code} has reached max uses")
                    return False

                # Increment usage count
                await db.execute(
                    """UPDATE invite_codes 
                       SET current_uses = current_uses + 1, 
                           updated_at = ? 
                       WHERE id = ?""",
                    (datetime.now().isoformat(), invite_id),
                )
                await db.commit()

                logger.info(f"Invite code {code} used successfully")
                return True

        except Exception as e:
            logger.error(f"Error using invite code {code}: {e}")
            return False

    @retry_db_operation()
    async def create_invite_code(self, code: str, max_uses: int = None) -> int:
        """Create a new invite code."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO invite_codes (code, max_uses) 
                   VALUES (?, ?)""",
                (code, max_uses),
            )
            await db.commit()
            return cursor.lastrowid

    @retry_db_operation()
    async def initialize_default_invite_code(self) -> bool:
        """Initialize the default invite code if it doesn't exist."""
        try:
            default_code = "peterpepperpickedapepper"
            
            async with self.get_connection() as db:
                # Check if the default code already exists
                cursor = await db.execute(
                    "SELECT id FROM invite_codes WHERE code = ?",
                    (default_code,),
                )
                existing = await cursor.fetchone()

                if not existing:
                    # Create the default invite code
                    await db.execute(
                        """INSERT INTO invite_codes (code, max_uses, is_active) 
                           VALUES (?, NULL, TRUE)""",
                        (default_code,),
                    )
                    await db.commit()
                    logger.info(f"✅ Created default invite code: {default_code}")
                else:
                    logger.info(f"✅ Default invite code already exists: {default_code}")

                return True

        except Exception as e:
            logger.error(f"❌ Error initializing default invite code: {e}")
            return False
