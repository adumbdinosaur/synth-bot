import logging
from typing import Dict, Any
from .database_manager import get_database_manager

logger = logging.getLogger(__name__)


class EnergyManager:
    """Simplified energy manager that delegates to DatabaseManager."""

    def __init__(self):
        self.db_manager = get_database_manager()

    async def get_user_energy(self, user_id: int) -> Dict[str, Any]:
        """Get current energy level for a user, applying recharge if needed."""
        return await self.db_manager.get_user_energy(user_id)

    async def consume_energy(self, user_id: int, amount: int = 1) -> Dict[str, Any]:
        """Consume energy for a user. Returns updated energy info or error."""
        return await self.db_manager.consume_user_energy(user_id, amount)

    async def add_energy(self, user_id: int, amount: int) -> Dict[str, Any]:
        """Add energy to a user (admin function)."""
        return await self.db_manager.add_user_energy(user_id, amount)

    async def get_energy_status(self, user_id: int) -> Dict[str, Any]:
        """Get energy status without applying recharge (for display purposes)."""
        energy_info = await self.db_manager.get_user_energy(user_id)
        return {
            "current_energy": energy_info["energy"],
            "max_energy": energy_info["max_energy"],
            "recharge_rate": energy_info["recharge_rate"],
            "percentage": (energy_info["energy"] / energy_info["max_energy"]) * 100,
        }
