import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from app.database import get_db_connection, retry_db_operation

logger = logging.getLogger(__name__)


class EnergyManager:
    """Manages user energy levels, consumption, and recharging."""

    def __init__(self):
        self.energy_cache: Dict[int, Dict[str, Any]] = {}
        # Remove the async lock to prevent deadlocks with database lock

    async def _get_user_energy_nolock(self, user_id: int) -> Dict[str, Any]:
        """Get current energy level for a user, applying recharge if needed. No lock acquired."""
        try:
            async with get_db_connection() as db:
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
                    }
                current_energy = row[0] or 100
                recharge_rate = row[1] or 1
                last_update = (
                    datetime.fromisoformat(row[2]) if row[2] else datetime.now()
                )
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
        except Exception as e:
            logger.error(f"Error getting energy for user {user_id}: {e}")
            return {
                "energy": 0,
                "recharge_rate": 1,
                "last_update": datetime.now(),
                "max_energy": 100,
            }

    @retry_db_operation(max_retries=3)
    async def get_user_energy(self, user_id: int) -> Dict[str, Any]:
        """Get current energy level for a user, applying recharge if needed."""
        return await self._get_user_energy_nolock(user_id)

    @retry_db_operation(max_retries=3)
    async def consume_energy(self, user_id: int, amount: int = 1) -> Dict[str, Any]:
        """Consume energy for a user. Returns updated energy info or error."""
        try:
            # Get current energy (this will apply recharge)
            energy_info = await self._get_user_energy_nolock(user_id)
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

            async with get_db_connection() as db:
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
                "energy_consumed": amount,
                "previous_energy": current_energy,
                "current_energy": new_energy,
                "max_energy": 100,
                "recharge_rate": energy_info["recharge_rate"],
            }

        except Exception as e:
            logger.error(f"Error consuming energy for user {user_id}: {e}")
            return {
                "success": False,
                "error": f"Energy consumption failed: {str(e)}",
                "current_energy": 0,
                "max_energy": 100,
            }

    @retry_db_operation(max_retries=3)
    async def set_energy_recharge_rate(self, user_id: int, rate: int) -> bool:
        """Set the energy recharge rate for a user."""
        try:
            async with get_db_connection() as db:
                await db.execute(
                    """UPDATE users SET energy_recharge_rate = ? WHERE id = ?""",
                    (rate, user_id),
                )
                await db.commit()

            logger.info(f"Updated energy recharge rate for user {user_id} to {rate}")
            return True

        except Exception as e:
            logger.error(f"Error setting energy recharge rate for user {user_id}: {e}")
            return False

    @retry_db_operation(max_retries=3)
    async def add_energy(self, user_id: int, amount: int) -> Dict[str, Any]:
        """Add energy to a user (admin function or bonus)."""
        try:
            energy_info = await self.get_user_energy(user_id)
            current_energy = energy_info["energy"]
            new_energy = min(100, current_energy + amount)  # Cap at 100
            now = datetime.now()

            async with get_db_connection() as db:
                await db.execute(
                    """UPDATE users SET energy = ?, last_energy_update = ? WHERE id = ?""",
                    (new_energy, now.isoformat(), user_id),
                )
                await db.commit()

            logger.info(
                f"Added {amount} energy to user {user_id}: {current_energy} -> {new_energy}"
            )

            return {
                "success": True,
                "energy_added": new_energy
                - current_energy,  # Actual amount added (might be less due to cap)
                "previous_energy": current_energy,
                "current_energy": new_energy,
                "max_energy": 100,
            }

        except Exception as e:
            logger.error(f"Error adding energy for user {user_id}: {e}")
            return {
                "success": False,
                "error": f"Energy addition failed: {str(e)}",
                "current_energy": 0,
            }

    async def get_energy_stats(self, user_id: int) -> Dict[str, Any]:
        """Get comprehensive energy statistics for a user."""
        try:
            energy_info = await self.get_user_energy(user_id)

            # Calculate time until full recharge
            current_energy = energy_info["energy"]
            recharge_rate = energy_info["recharge_rate"]
            energy_needed = 100 - current_energy

            if energy_needed <= 0:
                time_until_full = timedelta(0)
            else:
                minutes_until_full = energy_needed / recharge_rate
                time_until_full = timedelta(minutes=minutes_until_full)

            # Calculate next energy point
            if current_energy >= 100:
                time_until_next = timedelta(0)
            else:
                minutes_until_next = 1 / recharge_rate
                time_until_next = timedelta(minutes=minutes_until_next)

            return {
                "current_energy": current_energy,
                "max_energy": 100,
                "recharge_rate": recharge_rate,
                "energy_percentage": (current_energy / 100) * 100,
                "time_until_full": str(time_until_full),
                "time_until_next": str(time_until_next),
                "last_update": energy_info["last_update"].isoformat(),
                "can_send_message": current_energy >= 1,
            }

        except Exception as e:
            logger.error(f"Error getting energy stats for user {user_id}: {e}")
            return {
                "current_energy": 0,
                "max_energy": 100,
                "recharge_rate": 1,
                "energy_percentage": 0,
                "time_until_full": "Unknown",
                "time_until_next": "Unknown",
                "last_update": datetime.now().isoformat(),
                "can_send_message": False,
                "error": str(e),
            }


# Global energy manager instance
energy_manager = EnergyManager()


async def check_and_consume_energy(
    user_id: int, amount: int = 1
) -> tuple[bool, Dict[str, Any]]:
    """
    Check if user has enough energy and consume it if available.
    Returns (success, energy_info).
    """
    result = await energy_manager.consume_energy(user_id, amount)
    return result.get("success", False), result


async def get_user_energy_info(user_id: int) -> Dict[str, Any]:
    """Get user energy information."""
    return await energy_manager.get_user_energy(user_id)


async def get_user_energy_stats(user_id: int) -> Dict[str, Any]:
    """Get comprehensive energy statistics."""
    return await energy_manager.get_energy_stats(user_id)
