"""
Main database manager that combines all specialized managers.
"""

import logging
from .base import BaseDatabaseManager
from .user_manager import UserManager
from .energy_manager import EnergyManager
from .profile_manager import ProfileManager
from .badwords_manager import BadwordsManager
from .session_manager import SessionManager
from .auth_manager import AuthManager
from .autocorrect_manager import AutocorrectManager
from .chat_blacklist_manager import ChatBlacklistManager

logger = logging.getLogger(__name__)


class DatabaseManager(BaseDatabaseManager):
    """
    Main database manager that provides all database operations.

    This class uses composition to provide access to all specialized
    manager operations while keeping the code modular and organized.
    """

    def __init__(self, database_path: str):
        """Initialize the database manager."""
        super().__init__(database_path)

        # Initialize specialized managers with the same database path
        self.users = UserManager(database_path)
        self.energy = EnergyManager(database_path)
        self.profiles = ProfileManager(database_path)
        self.badwords = BadwordsManager(database_path)
        self.sessions = SessionManager(database_path)
        self.auth = AuthManager(database_path)
        self.autocorrect = AutocorrectManager(database_path)
        self.chat_blacklist = ChatBlacklistManager(database_path)

        logger.info(f"DatabaseManager initialized with database: {database_path}")

    async def initialize_all(self):
        """Initialize database and default data."""
        try:
            # Initialize database tables
            await self.initialize_database()

            # Initialize default invite code
            await self.auth.initialize_default_invite_code()

            logger.info("✅ Database and default data initialized successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Error during database initialization: {e}")
            return False

    # Delegate methods to specialized managers for backward compatibility

    # User management
    async def get_user_by_id(self, user_id: int):
        return await self.users.get_user_by_id(user_id)

    async def get_user_by_username(self, username: str):
        return await self.users.get_user_by_username(username)

    async def create_user(self, username: str, email: str, hashed_password: str):
        return await self.users.create_user(username, email, hashed_password)

    async def get_all_users(self):
        return await self.users.get_all_users()

    async def update_user_telegram_info(
        self, user_id: int, phone_number: str, connected: bool = True
    ):
        return await self.users.update_user_telegram_info(
            user_id, phone_number, connected
        )

    async def create_admin_user(self, username: str, email: str, hashed_password: str):
        return await self.users.create_admin_user(username, email, hashed_password)

    async def toggle_admin_status(self, user_id: int) -> bool:
        return await self.users.toggle_admin_status(user_id)

    async def is_admin(self, user_id: int):
        return await self.users.is_admin(user_id)

    # Energy management
    async def get_user_energy(self, user_id: int):
        return await self.energy.get_user_energy(user_id)

    async def consume_user_energy(self, user_id: int, amount: int):
        return await self.energy.consume_user_energy(user_id, amount)

    async def add_user_energy(self, user_id: int, amount: int):
        return await self.energy.add_user_energy(user_id, amount)

    async def update_user_energy_recharge_rate(self, user_id: int, recharge_rate: int):
        return await self.energy.update_user_energy_recharge_rate(
            user_id, recharge_rate
        )

    async def update_user_max_energy(self, user_id: int, max_energy: int):
        return await self.energy.update_user_max_energy(user_id, max_energy)

    async def remove_user_energy(self, user_id: int, amount: int):
        return await self.energy.remove_user_energy(user_id, amount)

    async def set_user_energy(self, user_id: int, energy: int):
        return await self.energy.set_user_energy(user_id, energy)

    async def get_user_energy_costs(self, user_id: int):
        return await self.energy.get_user_energy_costs(user_id)

    async def get_message_energy_cost(self, user_id: int, message_type: str):
        return await self.energy.get_message_energy_cost(user_id, message_type)

    async def update_user_energy_cost(
        self, user_id: int, message_type: str, energy_cost: int
    ):
        return await self.energy.update_user_energy_cost(
            user_id, message_type, energy_cost
        )

    async def init_user_energy_costs(self, user_id: int):
        return await self.energy.init_user_energy_costs(user_id)

    async def save_telegram_message(
        self,
        user_id: int,
        chat_id: int,
        message_id: int,
        message_type: str,
        content: str = "",
        energy_cost: int = 0,
    ):
        return await self.energy.save_telegram_message(
            user_id, chat_id, message_id, message_type, content, energy_cost
        )

    async def get_user_messages(self, user_id: int, limit: int = 100):
        return await self.energy.get_user_messages(user_id, limit)

    async def get_recent_activity(self, user_id: int, limit: int = 5):
        return await self.energy.get_recent_activity(user_id, limit)

    # Profile protection
    async def init_user_profile_protection(self, user_id: int):
        return await self.profiles.init_user_profile_protection(user_id)

    async def set_profile_change_penalty(self, user_id: int, penalty: int):
        return await self.profiles.set_profile_change_penalty(user_id, penalty)

    async def get_profile_change_penalty(self, user_id: int):
        return await self.profiles.get_profile_change_penalty(user_id)

    async def get_profile_protection_settings(self, user_id: int):
        return await self.profiles.get_profile_protection_settings(user_id)

    async def store_original_profile(
        self,
        user_id: int,
        first_name: str = "",
        last_name: str = "",
        bio: str = "",
        profile_photo_id: str = None,
    ):
        return await self.profiles.store_original_profile(
            user_id, first_name, last_name, bio, profile_photo_id
        )

    async def lock_user_profile(self, user_id: int):
        return await self.profiles.lock_user_profile(user_id)

    async def is_profile_locked(self, user_id: int):
        return await self.profiles.is_profile_locked(user_id)

    async def get_original_profile(self, user_id: int):
        return await self.profiles.get_original_profile(user_id)

    async def clear_profile_lock(self, user_id: int):
        return await self.profiles.clear_profile_lock(user_id)

    async def update_saved_profile_state(
        self,
        user_id: int,
        first_name: str = "",
        last_name: str = "",
        bio: str = "",
        profile_photo_id: str = None,
    ):
        return await self.profiles.update_saved_profile_state(
            user_id, first_name, last_name, bio, profile_photo_id
        )

    async def get_profile_revert_cost(self, user_id: int):
        return await self.profiles.get_profile_revert_cost(user_id)

    async def set_profile_revert_cost(self, user_id: int, cost: int):
        return await self.profiles.set_profile_revert_cost(user_id, cost)

    # Badwords management
    async def get_user_badwords(self, user_id: int):
        return await self.badwords.get_user_badwords(user_id)

    async def add_badword(
        self, user_id: int, word: str, penalty: int = 5, case_sensitive: bool = False
    ):
        return await self.badwords.add_badword(user_id, word, penalty, case_sensitive)

    async def remove_badword(self, user_id: int, word: str):
        return await self.badwords.remove_badword(user_id, word)

    async def update_badword_penalty(self, user_id: int, word: str, penalty: int):
        return await self.badwords.update_badword_penalty(user_id, word, penalty)

    async def check_for_badwords(self, user_id: int, message: str):
        return await self.badwords.check_for_badwords(user_id, message)

    async def filter_badwords_from_message(self, user_id: int, message: str):
        return await self.badwords.filter_badwords_from_message(user_id, message)

    # Session management
    async def save_telegram_session(self, user_id: int, session_data: str):
        return await self.sessions.save_telegram_session(user_id, session_data)

    async def get_telegram_session(self, user_id: int):
        return await self.sessions.get_telegram_session(user_id)

    async def delete_telegram_session(self, user_id: int):
        return await self.sessions.delete_telegram_session(user_id)

    async def get_all_active_sessions(self):
        return await self.sessions.get_all_active_sessions()

    async def has_active_telegram_session(self, user_id: int):
        return await self.sessions.has_active_telegram_session(user_id)

    # Authentication
    async def validate_invite_code(self, code: str):
        return await self.auth.validate_invite_code(code)

    async def use_invite_code(self, code: str):
        return await self.auth.use_invite_code(code)

    async def create_invite_code(self, code: str, max_uses: int = None):
        return await self.auth.create_invite_code(code, max_uses)

    async def initialize_default_invite_code(self):
        return await self.auth.initialize_default_invite_code()

    # Autocorrect
    async def get_autocorrect_settings(self, user_id: int):
        return await self.autocorrect.get_autocorrect_settings(user_id)

    async def update_autocorrect_settings(
        self, user_id: int, enabled: bool, penalty_per_correction: int
    ):
        return await self.autocorrect.update_autocorrect_settings(
            user_id, enabled, penalty_per_correction
        )

    async def log_autocorrect_usage(
        self,
        user_id: int,
        original_text: str,
        corrected_text: str,
        corrections_count: int,
    ):
        return await self.autocorrect.log_autocorrect_usage(
            user_id, original_text, corrected_text, corrections_count
        )

    # Chat blacklist
    async def get_user_blacklisted_chats(self, user_id: int):
        return await self.chat_blacklist.get_user_blacklisted_chats(user_id)

    async def add_blacklisted_chat(
        self, user_id: int, chat_id: int, chat_title: str = None, chat_type: str = None
    ):
        return await self.chat_blacklist.add_blacklisted_chat(
            user_id, chat_id, chat_title, chat_type
        )

    async def remove_blacklisted_chat(self, user_id: int, chat_id: int):
        return await self.chat_blacklist.remove_blacklisted_chat(user_id, chat_id)

    async def is_chat_blacklisted(self, user_id: int, chat_id: int):
        return await self.chat_blacklist.is_chat_blacklisted(user_id, chat_id)

    async def update_chat_info(
        self, user_id: int, chat_id: int, chat_title: str = None, chat_type: str = None
    ):
        return await self.chat_blacklist.update_chat_info(
            user_id, chat_id, chat_title, chat_type
        )


# Global database manager instance
_database_manager = None


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    global _database_manager
    if _database_manager is None:
        import os

        # Use DATABASE_URL environment variable if available
        database_url = os.getenv("DATABASE_URL", "sqlite:///./app.db")

        # Extract the path from sqlite URL
        if database_url.startswith("sqlite:///"):
            database_path = database_url[10:]  # Remove 'sqlite:///' prefix
            # Convert relative path to absolute if needed
            if database_path.startswith("./"):
                database_path = os.path.join(os.getcwd(), database_path[2:])
        else:
            database_path = "app.db"  # Fallback

        # Ensure the directory exists
        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        _database_manager = DatabaseManager(database_path)
    return _database_manager


def set_database_path(path: str):
    """Set a custom database path (must be called before first use)."""
    global _database_manager
    _database_manager = DatabaseManager(path)
