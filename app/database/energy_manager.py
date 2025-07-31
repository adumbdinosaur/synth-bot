"""
Energy management database operations.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List
from .base import BaseDatabaseManager, retry_db_operation

logger = logging.getLogger(__name__)


class EnergyManager(BaseDatabaseManager):
    """Handles all energy-related database operations."""

    async def get_user_energy(self, user_id: int) -> Dict[str, Any]:
        """Get user's current energy with automatic recharge calculation."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """SELECT energy, max_energy, energy_recharge_rate, last_energy_update 
                   FROM users WHERE id = ?""",
                (user_id,),
            )
            row = await cursor.fetchone()
            
            if not row:
                return {"success": False, "error": "User not found"}

            current_energy = row[0] if row[0] is not None else 100
            max_energy = row[1] if row[1] is not None else 100
            recharge_rate = row[2] if row[2] is not None else 1
            last_update = row[3]

            # Calculate recharge if we have a last update time
            if last_update:
                try:
                    last_update_dt = datetime.fromisoformat(last_update)
                    now = datetime.now()
                    time_diff = (now - last_update_dt).total_seconds()

                    # Calculate energy to add (1 energy per minute based on recharge rate)
                    energy_to_add = int(time_diff // 60) * recharge_rate
                    if energy_to_add > 0:
                        new_energy = min(max_energy, current_energy + energy_to_add)
                        
                        # Update the database with new energy and timestamp
                        await db.execute(
                            """UPDATE users SET energy = ?, last_energy_update = ? 
                               WHERE id = ?""",
                            (new_energy, now.isoformat(), user_id),
                        )
                        await db.commit()
                        current_energy = new_energy
                        
                        logger.debug(
                            f"Recharged user {user_id}: +{energy_to_add} energy (now {current_energy}/{max_energy})"
                        )
                except Exception as e:
                    logger.error(f"Error calculating energy recharge for user {user_id}: {e}")

            return {
                "success": True,
                "energy": current_energy,
                "max_energy": max_energy,
                "recharge_rate": recharge_rate,
            }

    @retry_db_operation()
    async def consume_user_energy(
        self, user_id: int, amount: int
    ) -> Dict[str, Any]:
        """Consume energy from user account."""
        # First get current energy (with recharge calculation)
        energy_info = await self.get_user_energy(user_id)
        if not energy_info["success"]:
            return energy_info

        current_energy = energy_info["energy"]
        max_energy = energy_info["max_energy"]

        if current_energy < amount:
            return {
                "success": False,
                "error": f"Insufficient energy. Required: {amount}, Available: {current_energy}",
                "energy": current_energy,
                "max_energy": max_energy,
            }

        new_energy = current_energy - amount

        async with self.get_connection() as db:
            await db.execute(
                """UPDATE users SET energy = ?, last_energy_update = ? 
                   WHERE id = ?""",
                (new_energy, datetime.now().isoformat(), user_id),
            )
            await db.commit()

        return {
            "success": True,
            "energy": new_energy,
            "max_energy": max_energy,
            "consumed": amount,
        }

    @retry_db_operation()
    async def add_user_energy(self, user_id: int, amount: int) -> Dict[str, Any]:
        """Add energy to user account."""
        # First get current energy (with recharge calculation)  
        energy_info = await self.get_user_energy(user_id)
        if not energy_info["success"]:
            return energy_info

        current_energy = energy_info["energy"]
        max_energy = energy_info["max_energy"]
        new_energy = min(max_energy, current_energy + amount)

        async with self.get_connection() as db:
            await db.execute(
                """UPDATE users SET energy = ?, last_energy_update = ? 
                   WHERE id = ?""",
                (new_energy, datetime.now().isoformat(), user_id),
            )
            await db.commit()

        return {
            "success": True,
            "energy": new_energy,
            "max_energy": max_energy,
            "added": new_energy - current_energy,
        }

    @retry_db_operation()
    async def update_user_energy_recharge_rate(
        self, user_id: int, recharge_rate: int
    ) -> Dict[str, Any]:
        """Update user's energy recharge rate."""
        if recharge_rate < 0 or recharge_rate > 10:
            return {
                "success": False,
                "error": "Recharge rate must be between 0 and 10",
            }

        async with self.get_connection() as db:
            await db.execute(
                """UPDATE users SET energy_recharge_rate = ?, last_energy_update = ? 
                   WHERE id = ?""",
                (recharge_rate, datetime.now().isoformat(), user_id),
            )
            await db.commit()

        return {
            "success": True,
            "recharge_rate": recharge_rate,
        }

    @retry_db_operation()
    async def update_user_max_energy(
        self, user_id: int, max_energy: int
    ) -> Dict[str, Any]:
        """Update user's maximum energy capacity."""
        if max_energy < 1 or max_energy > 500:
            return {
                "success": False,
                "error": "Maximum energy must be between 1 and 500",
            }

        async with self.get_connection() as db:
            # Also cap current energy if it exceeds new max
            await db.execute(
                """UPDATE users SET max_energy = ?, 
                   energy = CASE WHEN energy > ? THEN ? ELSE energy END,
                   last_energy_update = ? 
                   WHERE id = ?""",
                (max_energy, max_energy, max_energy, datetime.now().isoformat(), user_id),
            )
            await db.commit()

        # Get updated energy info
        energy_info = await self.get_user_energy(user_id)
        return {
            "success": True,
            "max_energy": max_energy,
            "current_energy": energy_info.get("energy", max_energy),
        }

    @retry_db_operation()
    async def remove_user_energy(self, user_id: int, amount: int) -> Dict[str, Any]:
        """Remove energy from user account (can go below 0)."""
        # First get current energy (with recharge calculation)
        energy_info = await self.get_user_energy(user_id)
        if not energy_info["success"]:
            return energy_info

        current_energy = energy_info["energy"]
        max_energy = energy_info["max_energy"]
        new_energy = max(0, current_energy - amount)  # Don't go below 0

        async with self.get_connection() as db:
            await db.execute(
                """UPDATE users SET energy = ?, last_energy_update = ? 
                   WHERE id = ?""",
                (new_energy, datetime.now().isoformat(), user_id),
            )
            await db.commit()

        return {
            "success": True,
            "energy": new_energy,
            "max_energy": max_energy,
            "removed": current_energy - new_energy,
        }

    @retry_db_operation()
    async def set_user_energy(self, user_id: int, energy: int) -> Dict[str, Any]:
        """Set user's energy to a specific amount."""
        # Get max energy first
        energy_info = await self.get_user_energy(user_id)
        if not energy_info["success"]:
            return energy_info

        max_energy = energy_info["max_energy"]
        
        # Ensure energy doesn't exceed maximum
        energy = min(max_energy, max(0, energy))

        async with self.get_connection() as db:
            await db.execute(
                """UPDATE users SET energy = ?, last_energy_update = ? 
                   WHERE id = ?""",
                (energy, datetime.now().isoformat(), user_id),
            )
            await db.commit()

        return {
            "success": True,
            "energy": energy,
            "max_energy": max_energy,
        }

    # Energy Cost Management
    async def get_user_energy_costs(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all energy costs for a user."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM user_energy_costs WHERE user_id = ? ORDER BY message_type",
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_message_energy_cost(self, user_id: int, message_type: str) -> int:
        """Get energy cost for a specific message type."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                "SELECT energy_cost FROM user_energy_costs WHERE user_id = ? AND message_type = ?",
                (user_id, message_type),
            )
            row = await cursor.fetchone()
            return row[0] if row else 1  # Default cost

    @retry_db_operation()
    async def update_user_energy_cost(
        self, user_id: int, message_type: str, energy_cost: int
    ):
        """Update energy cost for a specific message type."""
        async with self.get_connection() as db:
            await db.execute(
                """INSERT OR REPLACE INTO user_energy_costs 
                   (user_id, message_type, energy_cost, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (user_id, message_type, energy_cost, datetime.now().isoformat()),
            )
            await db.commit()

    @retry_db_operation()
    async def init_user_energy_costs(self, user_id: int):
        """Initialize default energy costs for a user."""
        default_costs = {
            "text": 1,
            "photo": 3,
            "video": 5,
            "audio": 4,
            "voice": 2,
            "document": 3,
            "sticker": 1,
            "animation": 3,
            "video_note": 4,
            "location": 2,
            "contact": 2,
            "poll": 3,
            "dice": 1,
        }

        async with self.get_connection() as db:
            for message_type, cost in default_costs.items():
                await db.execute(
                    """INSERT OR IGNORE INTO user_energy_costs 
                       (user_id, message_type, energy_cost)
                       VALUES (?, ?, ?)""",
                    (user_id, message_type, cost),
                )
            await db.commit()

    # Message tracking
    @retry_db_operation()
    async def save_telegram_message(
        self,
        user_id: int,
        chat_id: int,
        message_id: int,
        message_type: str,
        content: str = "",
        energy_cost: int = 0,
    ):
        """Save a Telegram message to the database."""
        async with self.get_connection() as db:
            await db.execute(
                """INSERT INTO messages 
                   (user_id, chat_id, message_id, message_type, content, energy_cost)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, chat_id, message_id, message_type, content, energy_cost),
            )
            await db.commit()

    async def get_user_messages(
        self, user_id: int, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent messages for a user."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """SELECT * FROM messages WHERE user_id = ? 
                   ORDER BY timestamp DESC LIMIT ?""",
                (user_id, limit),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
