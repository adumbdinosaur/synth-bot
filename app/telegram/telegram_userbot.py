"""
Modular Telegram UserBot client manager.
Coordinates authentication, messaging, profile management, and connection handling.
"""

import logging
from typing import Optional, Dict, Any
from .authentication_handler import AuthenticationHandler
from .message_handler import MessageHandler
from .profile_handler import ProfileHandler
from .connection_handler import ConnectionHandler

logger = logging.getLogger(__name__)


class TelegramUserBot:
    """Individual Telegram userbot instance for a single user with modular handlers."""

    def __init__(
        self, api_id: int, api_hash: str, phone_number: str, user_id: int, username: str
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.user_id = user_id
        self.username = username
        self.client = None
        self.session_name = f"sessions/user_{user_id}_{phone_number.replace('+', '')}"

        # Initialize handlers
        self.auth_handler = AuthenticationHandler(self)
        self.message_handler = MessageHandler(self)
        self.profile_handler = ProfileHandler(self)
        self.connection_handler = ConnectionHandler(self)

    # Authentication methods - delegated to AuthenticationHandler
    async def send_code_request(self) -> Dict[str, Any]:
        """Send verification code to phone number."""
        return await self.auth_handler.send_code_request()

    async def verify_code(self, code: str) -> Dict[str, Any]:
        """Verify SMS code."""
        return await self.auth_handler.verify_code(code)

    async def verify_2fa_password(self, password: str) -> bool:
        """Verify 2FA password after code verification."""
        return await self.auth_handler.verify_2fa_password(password)

    async def restore_from_session(self) -> bool:
        """Restore client from existing session file without sending new code."""
        return await self.auth_handler.restore_from_session()

    def get_auth_state(self) -> str:
        """Get current authentication state."""
        return self.auth_handler.get_auth_state()

    async def is_fully_authenticated(self) -> bool:
        """Check if user is fully authenticated and ready to use."""
        return await self.auth_handler.is_fully_authenticated()

    # Connection methods - delegated to ConnectionHandler
    async def start_message_listener(self) -> bool:
        """Start listening for outgoing messages in a background task."""
        return await self.connection_handler.start_message_listener()

    async def stop_listener(self):
        """Stop the message listener."""
        await self.connection_handler.stop_listener()

    async def disconnect(self):
        """Disconnect the Telegram client."""
        await self.connection_handler.disconnect()

    async def get_me(self):
        """Get current user information."""
        return await self.connection_handler.get_me()

    async def send_message(self, message: str, chat_id: Optional[int] = None) -> bool:
        """Send a message through this user's client."""
        return await self.connection_handler.send_message(message, chat_id)

    async def setup_handlers(self):
        """Setup event handlers for the Telegram client."""
        await self.connection_handler.setup_handlers()

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected and authorized."""
        return self.connection_handler.is_connected

    # Profile methods - delegated to ProfileHandler
    async def get_profile(self) -> Optional[Dict[str, Any]]:
        """Get current profile information for this user."""
        return await self.profile_handler.get_profile()

    async def set_profile(self, profile_data: Dict[str, Any]) -> bool:
        """Set profile information for this user."""
        return await self.profile_handler.set_profile(profile_data)

    async def trigger_profile_change(self) -> bool:
        """Trigger a profile change for this user."""
        return await self.profile_handler.trigger_profile_change()

    async def unlock_profile(self):
        """Unlock profile protection when session ends."""
        await self.profile_handler.unlock_profile()

    async def get_profile_status(self):
        """Get current profile monitoring status."""
        return await self.profile_handler.get_profile_status()

    async def update_original_profile(self, new_profile_data: Dict[str, Any]):
        """Update the stored original profile data."""
        return await self.profile_handler.update_original_profile(new_profile_data)
