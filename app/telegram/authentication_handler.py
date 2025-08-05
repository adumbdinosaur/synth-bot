"""
Authentication handler for Telegram userbot.
Handles code sending, verification, and 2FA authentication.
"""

import os
import logging
from typing import Dict, Any
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    AuthKeyDuplicatedError,
)
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)


class AuthenticationHandler(BaseHandler):
    """Handles authentication-related operations for Telegram userbot."""

    def __init__(self, client_instance):
        super().__init__(client_instance)
        self._auth_state = (
            "none"  # none, code_sent, code_verified, requires_2fa, authenticated
        )

    async def send_code_request(self) -> Dict[str, Any]:
        """Send verification code to phone number. Returns dict with status and delivery method."""
        try:
            # Ensure any previous client is properly disconnected
            if self.client_instance.client:
                try:
                    if self.client_instance.client.is_connected():
                        await self.client_instance.client.disconnect()
                except Exception:
                    pass
                self.client_instance.client = None

            # Clean up any corrupted session files
            await self._cleanup_corrupted_session()

            # Create client with unique session
            await self._create_telegram_client()

            await self.client_instance.client.connect()

            # Check if already signed in
            if await self.client_instance.client.is_user_authorized():
                logger.info(
                    f"User {self.client_instance.user_id} ({self.client_instance.username}) already authorized"
                )
                self._auth_state = "authenticated"
                return {"success": True, "already_authorized": True}

            # Send code request with detailed logging
            logger.info(
                f"Attempting to send verification code to {self.client_instance.phone_number} "
                f"for user {self.client_instance.user_id} ({self.client_instance.username})"
            )

            sent_code = await self.client_instance.client.send_code_request(
                self.client_instance.phone_number
            )
            logger.info(f"Telegram API response for code request: {sent_code}")

            # Extract information about how the code was sent
            delivery_info = self._parse_code_delivery_info(sent_code)

            logger.info(
                f"Code request successful for {self.client_instance.phone_number} - "
                f"user {self.client_instance.user_id} ({self.client_instance.username})"
            )
            self._auth_state = "code_sent"
            return {
                "success": True,
                "delivery_method": delivery_info["method"],
                "code_length": delivery_info["length"],
            }

        except AuthKeyDuplicatedError:
            logger.warning(
                f"Auth key duplicated for user {self.client_instance.user_id}, creating new session"
            )
            # Remove existing session and try again
            try:
                os.remove(f"{self.client_instance.session_name}.session")
            except FileNotFoundError:
                pass
            return await self.send_code_request()
        except Exception as e:
            logger.error(
                f"Failed to send code request for user {self.client_instance.user_id} "
                f"({self.client_instance.username}): {e}"
            )
            if self.client_instance.client:
                try:
                    await self.client_instance.client.disconnect()
                except Exception:
                    pass
                self.client_instance.client = None
            return {"success": False, "error": str(e)}

    async def verify_code(self, code: str) -> Dict[str, Any]:
        """Verify SMS code. Returns dict with status and whether 2FA is needed."""
        try:
            if not self.client_instance.client:
                logger.error(
                    f"No client available for user {self.client_instance.user_id}"
                )
                return {
                    "success": False,
                    "error": "No client available",
                    "requires_2fa": False,
                }

            try:
                # Try to sign in with just the code
                await self.client_instance.client.sign_in(
                    self.client_instance.phone_number, code
                )
                logger.info(
                    f"Successfully signed in user {self.client_instance.user_id} "
                    f"({self.client_instance.username}) - no 2FA required"
                )
                self._auth_state = "authenticated"
                return {"success": True, "requires_2fa": False}

            except SessionPasswordNeededError:
                # 2FA is enabled, password is required - this is actually partial success
                logger.info(
                    f"Code verified for user {self.client_instance.user_id} "
                    f"({self.client_instance.username}) - 2FA password required"
                )
                self._auth_state = "requires_2fa"
                return {"success": True, "requires_2fa": True, "code_verified": True}

            except PhoneCodeInvalidError:
                logger.warning(
                    f"Invalid phone code for user {self.client_instance.user_id} ({self.client_instance.username})"
                )
                return {
                    "success": False,
                    "error": "Invalid verification code",
                    "requires_2fa": False,
                }

        except Exception as e:
            logger.error(
                f"Code verification failed for user {self.client_instance.user_id} "
                f"({self.client_instance.username}): {e}"
            )
            return {"success": False, "error": str(e), "requires_2fa": False}

    async def verify_2fa_password(self, password: str) -> bool:
        """Verify 2FA password after code verification."""
        try:
            if not self.client_instance.client:
                logger.error(
                    f"No client available for user {self.client_instance.user_id}"
                )
                return False

            await self.client_instance.client.sign_in(password=password)
            logger.info(
                f"Successfully signed in user {self.client_instance.user_id} "
                f"({self.client_instance.username}) with 2FA"
            )
            self._auth_state = "authenticated"
            return True

        except Exception as e:
            logger.error(
                f"2FA verification failed for user {self.client_instance.user_id} "
                f"({self.client_instance.username}): {e}"
            )
            return False

    async def restore_from_session(self) -> bool:
        """Restore client from existing session file without sending new code."""
        try:
            # Check if session file exists
            session_file = f"{self.client_instance.session_name}.session"
            if not os.path.exists(session_file):
                logger.warning(
                    f"No session file found for user {self.client_instance.user_id}: {session_file}"
                )
                return False

            # Create client with existing session
            await self._create_telegram_client()

            await self.client_instance.client.connect()

            # Check if already signed in
            if await self.client_instance.client.is_user_authorized():
                self._auth_state = "authenticated"
                return True
            else:
                logger.warning(
                    f"Session file exists but user {self.client_instance.user_id} is not authorized"
                )
                await self.client_instance.client.disconnect()
                self.client_instance.client = None
                return False

        except Exception as e:
            logger.error(
                f"Failed to restore session for user {self.client_instance.user_id} "
                f"({self.client_instance.username}): {e}"
            )
            if self.client_instance.client:
                try:
                    await self.client_instance.client.disconnect()
                except Exception:
                    pass
                self.client_instance.client = None
            return False

    def get_auth_state(self) -> str:
        """Get current authentication state."""
        return self._auth_state

    async def is_fully_authenticated(self) -> bool:
        """Check if user is fully authenticated and ready to use."""
        return (
            self._auth_state == "authenticated"
            and self.client_instance.client
            and await self.client_instance.client.is_user_authorized()
        )

    async def _cleanup_corrupted_session(self):
        """Clean up any corrupted session files."""
        session_file = f"{self.client_instance.session_name}.session"
        if os.path.exists(session_file):
            try:
                # Try to validate session file
                import sqlite3

                conn = sqlite3.connect(session_file)
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                conn.close()
            except Exception:
                # Session file is corrupted, remove it
                try:
                    os.remove(session_file)
                    logger.warning(
                        f"Removed corrupted session file for user {self.client_instance.user_id}"
                    )
                except Exception:
                    pass

    async def _create_telegram_client(self):
        """Create Telegram client with proper configuration."""
        from telethon import TelegramClient

        self.client_instance.client = TelegramClient(
            self.client_instance.session_name,
            self.client_instance.api_id,
            self.client_instance.api_hash,
            device_model=f"UserBot-{self.client_instance.username}",
            app_version="1.0.0",
            system_version="Linux",
        )

    def _parse_code_delivery_info(self, sent_code) -> Dict[str, Any]:
        """Parse code delivery information from Telegram response."""
        code_type = sent_code.type
        delivery_method = "unknown"
        code_length = 5  # Default length

        if hasattr(code_type, "__class__"):
            type_name = code_type.__class__.__name__
            if type_name == "SentCodeTypeApp":
                delivery_method = "telegram_app"
                logger.info(
                    f"Code sent via Telegram app for {self.client_instance.phone_number}"
                )
            elif type_name == "SentCodeTypeSms":
                delivery_method = "sms"
                logger.info(
                    f"Code sent via SMS for {self.client_instance.phone_number}"
                )
            elif type_name == "SentCodeTypeCall":
                delivery_method = "phone_call"
                logger.info(
                    f"Code sent via phone call for {self.client_instance.phone_number}"
                )
            else:
                delivery_method = type_name.lower()
                logger.info(
                    f"Code sent via {type_name} for {self.client_instance.phone_number}"
                )

        # Get code length if available
        if hasattr(code_type, "length"):
            code_length = code_type.length

        return {"method": delivery_method, "length": code_length}
