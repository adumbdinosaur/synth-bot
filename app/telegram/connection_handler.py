"""
Connection handler for Telegram userbot.
Handles client connection, session management, and connection-related operations.
"""

import logging
import asyncio
from typing import Optional
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)


class ConnectionHandler(BaseHandler):
    """Handles connection-related operations for Telegram userbot."""

    def __init__(self, client_instance):
        super().__init__(client_instance)
        self._is_running = False
        self._listener_task = None

    async def start_message_listener(self) -> bool:
        """Start listening for messages in a background task."""
        if (
            not self.client_instance.client
            or not await self.client_instance.client.is_user_authorized()
        ):
            logger.error(
                f"Client not authorized for user {self.client_instance.user_id} ({self.client_instance.username})"
            )
            return False

        if self._is_running:
            logger.warning(
                f"Message listener already running for user {self.client_instance.user_id} ({self.client_instance.username})"
            )
            return True

        try:
            # Initialize profile handler
            if not self.client_instance.profile_handler:
                from .profile_handler import ProfileHandler

                self.client_instance.profile_handler = ProfileHandler(
                    self.client_instance
                )

            # Initialize profile handler
            profile_initialized = (
                await self.client_instance.profile_handler.initialize()
            )
            if profile_initialized:
                logger.info(
                    f"🎯 Profile handler initialized for user {self.client_instance.user_id} ({self.client_instance.username})"
                )
            else:
                logger.error(
                    f"❌ Failed to initialize profile handler for user {self.client_instance.user_id}"
                )

            # Initialize message handler
            if not self.client_instance.message_handler:
                from .message_handler import MessageHandler

                self.client_instance.message_handler = MessageHandler(
                    self.client_instance
                )

            # Register message handlers
            await self.client_instance.message_handler.register_handlers()

            # Register profile handlers
            await self.client_instance.profile_handler.register_handlers()

            # Start the listener task
            self._listener_task = asyncio.create_task(self._run_listener())
            self._is_running = True
            logger.info(
                f"Started message listener for user {self.client_instance.user_id} ({self.client_instance.username})"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to start message listener for user {self.client_instance.user_id} ({self.client_instance.username}): {e}"
            )
            return False

    async def stop_listener(self):
        """Stop the message listener."""
        # Unlock profile protection when stopping
        if self.client_instance.profile_handler:
            await self.client_instance.profile_handler.unlock_profile()

        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        self._is_running = False
        logger.info(
            f"Stopped message listener for user {self.client_instance.user_id} ({self.client_instance.username})"
        )

    async def disconnect(self):
        """Disconnect the Telegram client."""
        await self.stop_listener()

        if self.client_instance.client:
            try:
                if self.client_instance.client.is_connected():
                    await self.client_instance.client.disconnect()
                logger.info(
                    f"Disconnected Telegram client for user {self.client_instance.user_id} ({self.client_instance.username})"
                )
            except Exception as e:
                logger.error(
                    f"Error disconnecting client for user {self.client_instance.user_id} ({self.client_instance.username}): {e}"
                )
            finally:
                self.client_instance.client = None

    async def get_me(self):
        """Get current user information."""
        if (
            not self.client_instance.client
            or not await self.client_instance.client.is_user_authorized()
        ):
            return None

        try:
            return await self.client_instance.client.get_me()
        except Exception as e:
            logger.error(
                f"Failed to get user info for {self.client_instance.user_id} ({self.client_instance.username}): {e}"
            )
            return None

    async def send_message(self, message: str, chat_id: Optional[int] = None) -> bool:
        """Send a message through this user's client. Returns True if successful."""
        try:
            if (
                not self.client_instance.client
                or not self.client_instance.client.is_connected()
            ):
                logger.error(
                    f"User {self.client_instance.user_id} ({self.client_instance.username}) not connected"
                )
                return False

            # Send the message
            await self.client_instance.client.send_message("me", message)
            logger.info(
                f"Message sent by user {self.client_instance.user_id} ({self.client_instance.username}) - "
                f"Length: {len(message)} chars"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error sending message for user {self.client_instance.user_id}: {e}"
            )
            return False

    async def setup_handlers(self):
        """Setup event handlers for the Telegram client."""
        try:
            if (
                not self.client_instance.client
                or not self.client_instance.client.is_connected()
            ):
                logger.warning(
                    f"Cannot setup handlers - client not connected for user {self.client_instance.user_id}"
                )
                return

            # Initialize and register handlers
            if not self.client_instance.message_handler:
                from .message_handler import MessageHandler

                self.client_instance.message_handler = MessageHandler(
                    self.client_instance
                )

            if not self.client_instance.profile_handler:
                from .profile_handler import ProfileHandler

                self.client_instance.profile_handler = ProfileHandler(
                    self.client_instance
                )

            # Register handlers
            await self.client_instance.message_handler.register_handlers()
            await self.client_instance.profile_handler.register_handlers()

            logger.info(
                f"Event handlers setup completed for user {self.client_instance.user_id}"
            )

        except Exception as e:
            logger.error(
                f"Error setting up handlers for user {self.client_instance.user_id}: {e}"
            )

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected and authorized."""
        return (
            self.client_instance.client is not None
            and self.client_instance.client.is_connected()
            and self._is_running
        )

    @property
    def is_running(self) -> bool:
        """Check if the message listener is running."""
        return self._is_running

    async def _run_listener(self):
        """Run the message listener loop."""
        try:
            logger.info(
                f"Message listener started for user {self.client_instance.user_id} ({self.client_instance.username})"
            )
            await self.client_instance.client.run_until_disconnected()
        except asyncio.CancelledError:
            logger.info(
                f"Message listener cancelled for user {self.client_instance.user_id} ({self.client_instance.username})"
            )
        except Exception as e:
            logger.error(
                f"Message listener error for user {self.client_instance.user_id} ({self.client_instance.username}): {e}"
            )
        finally:
            self._is_running = False
