import logging
from typing import Dict, Any
from .database import get_database_manager

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

    async def remove_energy(self, user_id: int, amount: int) -> Dict[str, Any]:
        """Remove energy from a user (admin function)."""
        return await self.db_manager.remove_user_energy(user_id, amount)

    async def set_energy(self, user_id: int, energy_level: int) -> Dict[str, Any]:
        """Set exact energy level for a user (admin function)."""
        return await self.db_manager.set_user_energy(user_id, energy_level)

    async def update_max_energy(self, user_id: int, max_energy: int) -> Dict[str, Any]:
        """Update maximum energy for a user (admin function)."""
        return await self.db_manager.update_user_max_energy(user_id, max_energy)

    async def update_recharge_rate(
        self, user_id: int, recharge_rate: int
    ) -> Dict[str, Any]:
        """Update energy recharge rate for a user (admin function)."""
        return await self.db_manager.update_user_energy_recharge_rate(
            user_id, recharge_rate
        )
