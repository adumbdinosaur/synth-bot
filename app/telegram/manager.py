"""
Manager for multiple Telegram clients with session recovery functionality.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from .telegram_userbot import TelegramUserBot

logger = logging.getLogger(__name__)


class TelegramClientManager:
    """Manager for multiple Telegram clients."""

    def __init__(self, api_id: int, api_hash: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.clients: Dict[int, TelegramUserBot] = {}
        self.session_dir = "sessions"

        # Create sessions directory if it doesn't exist
        os.makedirs(self.session_dir, exist_ok=True)

    def get_client_count(self) -> int:
        """Get the number of currently connected Telegram clients."""
        count = 0
        for client in self.clients.values():
            if client.is_connected:  # Property, not method - no await, no parentheses
                count += 1
        return count

    async def get_client(self, user_id: int) -> Optional[TelegramUserBot]:
        """Get a client for the given user ID."""
        return self.clients.get(user_id)

    async def get_or_create_client(
        self,
        user_id: int,
        username: str,
        phone_number: str,
        session_string: Optional[str] = None,
    ) -> TelegramUserBot:
        """Get existing client or create a new one for the given user."""
        # Check if client already exists
        existing_client = self.clients.get(user_id)
        if existing_client:
            logger.info(f"Returning existing client for user {user_id} ({username})")
            return existing_client

        # Create new client
        logger.info(f"Creating new client for user {user_id} ({username})")
        client = TelegramUserBot(
            self.api_id, self.api_hash, phone_number, user_id, username
        )

        # Store the client
        self.clients[user_id] = client

        return client

    async def remove_client(self, user_id: int) -> bool:
        """Remove and disconnect a client."""
        if user_id in self.clients:
            client = self.clients[user_id]
            await client.disconnect()
            del self.clients[user_id]
            return True
        return False

    async def disconnect_all(self) -> None:
        """Disconnect all clients."""
        logger.info(f"Disconnecting {len(self.clients)} Telegram clients...")
        for user_id, client in list(self.clients.items()):
            try:
                await client.disconnect()
                logger.info(f"✅ Disconnected client for user {user_id}")
            except Exception as e:
                logger.error(f"❌ Error disconnecting client for user {user_id}: {e}")
        self.clients.clear()
        logger.info("All clients disconnected")

    async def get_connected_users(self) -> List[Dict[str, Any]]:
        """Get list of currently connected users."""
        connected = []
        for user_id, client in self.clients.items():
            if client.client and client.client.is_connected():
                connected.append(
                    {
                        "user_id": user_id,
                        "username": client.username,
                        "phone": client.phone_number,
                        "connected": True,
                    }
                )
        return connected

    async def trigger_profile_change(self, user_id: int) -> bool:
        """Trigger profile change for a specific user."""
        try:
            client = self.clients.get(user_id)
            if client:
                return await client.trigger_profile_change()
            else:
                logger.error(f"No active client found for user {user_id}")
                return False
        except Exception as e:
            logger.error(f"Error triggering profile change for user {user_id}: {e}")
            return False

    async def get_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get profile information for a specific user."""
        try:
            client = self.clients.get(user_id)
            if client:
                return await client.get_profile()
            else:
                logger.error(f"No active client found for user {user_id}")
                return None
        except Exception as e:
            logger.error(f"Error getting profile for user {user_id}: {e}")
            return None

    async def set_profile(self, user_id: int, profile_data: Dict[str, Any]) -> bool:
        """Set profile information for a specific user."""
        try:
            client = self.clients.get(user_id)
            if client:
                return await client.set_profile(profile_data)
            else:
                logger.error(f"No active client found for user {user_id}")
                return False
        except Exception as e:
            logger.error(f"Error setting profile for user {user_id}: {e}")
            return False

    async def send_message(
        self, user_id: int, message: str, chat_id: Optional[int] = None
    ) -> bool:
        """Send a message through a user's client."""
        try:
            client = self.clients.get(user_id)
            if client:
                return await client.send_message(message, chat_id)
            else:
                logger.error(f"No active client found for user {user_id}")
                return False
        except Exception as e:
            logger.error(f"Error sending message for user {user_id}: {e}")
            return False

    async def recover_clients_from_sessions(self, db_manager):
        """Recover clients from existing session files."""
        logger.info("🔄 Starting client recovery from session files...")

        if not os.path.exists(self.session_dir):
            logger.info("No sessions directory found, creating it...")
            os.makedirs(self.session_dir, exist_ok=True)
            return

        # Find all session files
        session_files = []
        for file in os.listdir(self.session_dir):
            if file.startswith("user_") and file.endswith(".session"):
                try:
                    # Handle format: user_{user_id}_{phone}.session
                    parts = file.replace("user_", "").replace(".session", "").split("_")
                    if len(parts) >= 1:
                        user_id = int(parts[0])  # First part is always user_id
                        session_files.append((user_id, file))
                except ValueError as e:
                    logger.warning(f"Could not parse session file {file}: {e}")
                    continue

        if not session_files:
            logger.info("No session files found to recover")
            return

        logger.info(f"Found {len(session_files)} session files to process")
        for user_id, filename in session_files:
            logger.info(f"  - Session file: {filename} -> User ID: {user_id}")

        successful_recoveries = 0
        for user_id, session_file in session_files:
            try:
                # Get user info from database
                user_data = await db_manager.get_user_by_id(user_id)
                if not user_data:
                    logger.warning(
                        f"User {user_id} not found in database, skipping session recovery"
                    )
                    continue

                if not user_data.get("telegram_connected"):
                    logger.info(
                        f"User {user_id} not marked as connected, skipping session recovery"
                    )
                    continue

                username = user_data.get("username", f"user_{user_id}")
                phone = user_data.get("phone_number")

                if not phone:
                    logger.warning(
                        f"No phone number found for user {user_id}, skipping recovery"
                    )
                    continue

                logger.info(
                    f"Attempting to recover session for user {user_id}, phone {phone}"
                )

                # Create client with existing session
                client = TelegramUserBot(
                    self.api_id, self.api_hash, phone, user_id, username
                )

                # Try to restore from session
                success = await client.restore_from_session()
                if success and await client.is_fully_authenticated():
                    # Store the client
                    self.clients[user_id] = client

                    # Get user info to verify
                    me = await client.client.get_me()
                    if me:
                        logger.info(
                            f"User {user_id} ({me.first_name or username}) "
                            f"restored from session - already authorized"
                        )

                        # Store original profile data if profile protection is enabled
                        protection_settings = (
                            await db_manager.get_profile_protection_settings(user_id)
                        )
                        if protection_settings and protection_settings.get(
                            "profile_protection_enabled"
                        ):
                            current_profile = await client.get_profile()
                            if current_profile:
                                await db_manager.store_original_profile(
                                    user_id,
                                    first_name=current_profile.get("first_name", ""),
                                    last_name=current_profile.get("last_name", ""),
                                    bio=current_profile.get("bio", ""),
                                    profile_photo_id=current_profile.get(
                                        "profile_photo_id"
                                    ),
                                )
                                await db_manager.lock_user_profile(user_id)
                                logger.info(
                                    f"🔒 PROFILE LOCKED | User: {username} (ID: {user_id}) | "
                                    f"Profile protection enabled"
                                )

                        # Start message and profile handlers
                        await client.setup_handlers()
                        await client.start_message_listener()

                        successful_recoveries += 1
                        logger.info(
                            f"✅ Successfully recovered and started listener for user "
                            f"{user_id} ({username})"
                        )
                    else:
                        logger.error(
                            f"Could not get user info for {user_id} after connection"
                        )
                        await client.disconnect()
                else:
                    logger.warning(
                        f"Could not restore session for user {user_id} - session may be expired"
                    )
                    if client.client:
                        await client.disconnect()

            except Exception as e:
                logger.error(f"Error recovering session for user {user_id}: {e}")
                continue

        logger.info(
            f"🎉 Successfully recovered {successful_recoveries} client(s) from session files"
        )


# Global telegram manager instance
_telegram_manager: Optional[TelegramClientManager] = None


def get_telegram_manager() -> Optional[TelegramClientManager]:
    """Get the global telegram manager instance."""
    global _telegram_manager
    return _telegram_manager


def initialize_telegram_manager(api_id: int, api_hash: str) -> TelegramClientManager:
    """Initialize the telegram manager with API credentials."""
    global _telegram_manager
    if _telegram_manager is None:
        _telegram_manager = TelegramClientManager(api_id, api_hash)
    return _telegram_manager


async def recover_telegram_sessions():
    """Recover existing telegram sessions."""
    from ..database import get_database_manager

    telegram_manager = get_telegram_manager()
    if telegram_manager:
        db_manager = get_database_manager()
        await telegram_manager.recover_clients_from_sessions(db_manager)
    else:
        logger.warning("Telegram manager not initialized, cannot recover sessions")
