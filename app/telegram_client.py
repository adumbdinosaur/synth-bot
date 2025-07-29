import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Set
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    AuthKeyDuplicatedError,
)
import weakref
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class TelegramUserBot:
    """Individual Telegram userbot instance for a single user."""

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
        self._message_handler_registered = False
        self._listener_task = None
        self._is_running = False
        self._auth_state = (
            "none"  # none, code_sent, code_verified, requires_2fa, authenticated
        )

    async def send_code_request(self) -> dict:
        """Send verification code to phone number. Returns dict with status and delivery method."""
        try:
            # Ensure any previous client is properly disconnected
            if self.client:
                try:
                    if self.client.is_connected():
                        await self.client.disconnect()
                except:
                    pass
                self.client = None

            # Clean up any corrupted session files
            import os

            session_file = f"{self.session_name}.session"
            if os.path.exists(session_file):
                try:
                    # Try to remove if corrupted
                    import sqlite3

                    conn = sqlite3.connect(session_file)
                    conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    conn.close()
                except:
                    # Session file is corrupted, remove it
                    try:
                        os.remove(session_file)
                        logger.warning(
                            f"Removed corrupted session file for user {self.user_id}"
                        )
                    except:
                        pass

            # Create client with unique session
            self.client = TelegramClient(
                self.session_name,
                self.api_id,
                self.api_hash,
                device_model=f"UserBot-{self.username}",
                app_version="1.0.0",
                system_version="Linux",
            )

            await self.client.connect()
            logger.info(f"Telegram client connected for user {self.user_id}")

            # Check if already signed in
            if await self.client.is_user_authorized():
                logger.info(f"User {self.user_id} ({self.username}) already authorized")
                self._auth_state = "authenticated"
                return {"success": True, "already_authorized": True}

            # Send code request with detailed logging
            logger.info(
                f"Attempting to send verification code to {self.phone_number} for user {self.user_id} ({self.username})"
            )
            try:
                sent_code = await self.client.send_code_request(self.phone_number)
                logger.info(f"Telegram API response for code request: {sent_code}")

                # Extract information about how the code was sent
                code_type = sent_code.type
                delivery_method = "unknown"
                if hasattr(code_type, "__class__"):
                    type_name = code_type.__class__.__name__
                    if type_name == "SentCodeTypeApp":
                        delivery_method = "telegram_app"
                        logger.info(
                            f"Code sent via Telegram app for {self.phone_number}"
                        )
                    elif type_name == "SentCodeTypeSms":
                        delivery_method = "sms"
                        logger.info(f"Code sent via SMS for {self.phone_number}")
                    elif type_name == "SentCodeTypeCall":
                        delivery_method = "phone_call"
                        logger.info(f"Code sent via phone call for {self.phone_number}")
                    else:
                        delivery_method = type_name.lower()
                        logger.info(
                            f"Code sent via {type_name} for {self.phone_number}"
                        )

                logger.info(
                    f"Code request successful for {self.phone_number} - user {self.user_id} ({self.username})"
                )
                self._auth_state = "code_sent"
                return {
                    "success": True,
                    "delivery_method": delivery_method,
                    "code_length": getattr(code_type, "length", 5),
                }
            except Exception as code_error:
                logger.error(
                    f"Error during code request for {self.phone_number}: {code_error}"
                )
                raise

        except AuthKeyDuplicatedError:
            logger.warning(
                f"Auth key duplicated for user {self.user_id}, creating new session"
            )
            # Remove existing session and try again
            try:
                os.remove(f"{self.session_name}.session")
            except FileNotFoundError:
                pass
            return await self.send_code_request()
        except Exception as e:
            logger.error(
                f"Failed to send code request for user {self.user_id} ({self.username}): {e}"
            )
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            return {"success": False, "error": str(e)}

    async def verify_code(self, code: str) -> dict:
        """Verify SMS code. Returns dict with status and whether 2FA is needed."""
        try:
            if not self.client:
                logger.error(f"No client available for user {self.user_id}")
                return {
                    "success": False,
                    "error": "No client available",
                    "requires_2fa": False,
                }

            try:
                # Try to sign in with just the code
                await self.client.sign_in(self.phone_number, code)
                logger.info(
                    f"Successfully signed in user {self.user_id} ({self.username}) - no 2FA required"
                )
                self._auth_state = "authenticated"
                return {"success": True, "requires_2fa": False}

            except SessionPasswordNeededError:
                # 2FA is enabled, password is required - this is actually partial success
                logger.info(
                    f"Code verified for user {self.user_id} ({self.username}) - 2FA password required"
                )
                self._auth_state = "requires_2fa"
                return {"success": True, "requires_2fa": True, "code_verified": True}

            except PhoneCodeInvalidError:
                logger.warning(
                    f"Invalid phone code for user {self.user_id} ({self.username})"
                )
                return {
                    "success": False,
                    "error": "Invalid verification code",
                    "requires_2fa": False,
                }

        except Exception as e:
            logger.error(
                f"Code verification failed for user {self.user_id} ({self.username}): {e}"
            )
            return {"success": False, "error": str(e), "requires_2fa": False}

    async def verify_2fa_password(self, password: str) -> bool:
        """Verify 2FA password after code verification."""
        try:
            if not self.client:
                logger.error(f"No client available for user {self.user_id}")
                return False

            await self.client.sign_in(password=password)
            logger.info(
                f"Successfully signed in user {self.user_id} ({self.username}) with 2FA"
            )
            self._auth_state = "authenticated"
            return True

        except Exception as e:
            logger.error(
                f"2FA verification failed for user {self.user_id} ({self.username}): {e}"
            )
            return False

    async def start_message_listener(self) -> bool:
        """Start listening for outgoing messages in a background task."""
        if not self.client or not await self.client.is_user_authorized():
            logger.error(
                f"Client not authorized for user {self.user_id} ({self.username})"
            )
            return False

        if self._is_running:
            logger.warning(
                f"Message listener already running for user {self.user_id} ({self.username})"
            )
            return True

        try:
            # Register message handlers if not already registered
            if not self._message_handler_registered:

                @self.client.on(events.NewMessage(outgoing=True))
                async def outgoing_message_handler(event):
                    await self._handle_outgoing_message(event)

                @self.client.on(events.NewMessage(incoming=True))
                async def incoming_message_handler(event):
                    await self._handle_incoming_message(event)

                self._message_handler_registered = True
                logger.info(
                    f"Message handlers registered for user {self.user_id} ({self.username})"
                )

            # Start the listener task
            self._listener_task = asyncio.create_task(self._run_listener())
            self._is_running = True
            logger.info(
                f"Started message listener for user {self.user_id} ({self.username})"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to start message listener for user {self.user_id} ({self.username}): {e}"
            )
            return False

    async def _handle_outgoing_message(self, event):
        """Handle outgoing message event."""
        try:
            # Skip energy consumption for roleplay messages
            if event.message.text and event.message.text.startswith("🎭"):
                logger.info("🎭 Skipping energy consumption for roleplay message")
                return

            from .database_manager import get_database_manager

            db_manager = get_database_manager()

            # Determine message type
            message_type = self._get_message_type(event.message)

            # Get energy cost for this message type
            energy_cost = await db_manager.get_message_energy_cost(
                self.user_id, message_type
            )

            # Get current energy level
            energy_info = await db_manager.get_user_energy(self.user_id)
            current_energy = energy_info["energy"]

            # Consume energy for sending this message
            consume_result = await db_manager.consume_user_energy(
                self.user_id, energy_cost
            )

            if not consume_result["success"]:
                # Energy consumption failed (user had insufficient energy)
                # Send a roleplay message to indicate low energy
                try:
                    from .roleplay_messages import get_random_low_energy_message

                    roleplay_msg = get_random_low_energy_message()

                    # Send the roleplay message to the same chat
                    # Important: We disable the outgoing message handler temporarily
                    # to prevent this roleplay message from triggering energy consumption
                    await self._send_roleplay_message(event, roleplay_msg)

                    logger.warning(
                        f"⚡ LOW ENERGY | User: {self.username} (ID: {self.user_id}) | "
                        f"Message type: {message_type} (cost: {energy_cost}) | "
                        f"Required: {energy_cost}, Available: {current_energy} | "
                        f"Sent roleplay message: {roleplay_msg[:50]}..."
                    )
                except Exception as e:
                    logger.error(f"Failed to send roleplay message: {e}")
                    # Fallback to just logging
                    logger.warning(
                        f"⚡ LOW ENERGY | User: {self.username} (ID: {self.user_id}) | "
                        f"Message type: {message_type} (cost: {energy_cost}) | "
                        f"Message sent but user has insufficient energy! | "
                        f"Energy: {current_energy}/100"
                    )
            else:
                # Successfully consumed energy
                new_energy = consume_result["energy"]
                logger.info(
                    f"⚡ ENERGY CONSUMED | User: {self.username} (ID: {self.user_id}) | "
                    f"Message type: {message_type} (cost: {energy_cost}) | "
                    f"Energy: {new_energy}/100 (-{energy_cost})"
                )

            # Get chat information
            chat = await event.get_chat()
            chat_title = getattr(chat, "title", getattr(chat, "first_name", "Unknown"))
            chat_type = (
                "channel"
                if hasattr(chat, "broadcast") and chat.broadcast
                else "group"
                if hasattr(chat, "megagroup") and chat.megagroup
                else "private"
            )

            message_text = event.message.text or "[Media/Sticker/File]"

            # Log message details
            logger.info(
                f"📤 MESSAGE SENT | User: {self.username} (ID: {self.user_id}) | "
                f"Chat: {chat_title} ({chat_type}) | "
                f"Content: {message_text[:100]}{'...' if len(message_text) > 100 else ''} | "
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

        except Exception as e:
            logger.error(
                f"Error handling message for user {self.user_id} ({self.username}): {e}"
            )

    async def _handle_incoming_message(self, event):
        """Handle incoming message events for easter eggs and commands."""
        try:
            # Check if the message is a text message
            if not event.message.text:
                return

            message_text = event.message.text.strip().lower()

            # Check for easter egg commands
            response_msg = None
            command_type = None

            if message_text == "/flip":
                from .roleplay_messages import get_random_flip_message

                response_msg = get_random_flip_message()
                command_type = "FLIP"
            elif message_text == "/beep":
                from .roleplay_messages import get_random_beep_message

                response_msg = get_random_beep_message()
                command_type = "BEEP"
            elif message_text == "/dance":
                from .roleplay_messages import get_random_dance_message

                response_msg = get_random_dance_message()
                command_type = "DANCE"

            # If we have a response, send it
            if response_msg:
                # Send the roleplay message directly (no emoji prefix for easter eggs)
                await self.client.send_message(event.chat_id, response_msg)

                logger.info(
                    f"🎪 {command_type} EASTER EGG | User: {self.username} (ID: {self.user_id}) | "
                    f"Responded to /{command_type.lower()} command with: {response_msg[:50]}..."
                )

        except Exception as e:
            logger.error(
                f"Error handling incoming message for user {self.user_id} ({self.username}): {e}"
            )

    async def _run_listener(self):
        """Run the message listener loop."""
        try:
            logger.info(
                f"Message listener started for user {self.user_id} ({self.username})"
            )
            await self.client.run_until_disconnected()
        except asyncio.CancelledError:
            logger.info(
                f"Message listener cancelled for user {self.user_id} ({self.username})"
            )
        except Exception as e:
            logger.error(
                f"Message listener error for user {self.user_id} ({self.username}): {e}"
            )
        finally:
            self._is_running = False

    async def stop_listener(self):
        """Stop the message listener."""
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        self._is_running = False
        logger.info(
            f"Stopped message listener for user {self.user_id} ({self.username})"
        )

    async def disconnect(self):
        """Disconnect the Telegram client."""
        await self.stop_listener()

        if self.client:
            try:
                if self.client.is_connected():
                    await self.client.disconnect()
                logger.info(
                    f"Disconnected Telegram client for user {self.user_id} ({self.username})"
                )
            except Exception as e:
                logger.error(
                    f"Error disconnecting client for user {self.user_id} ({self.username}): {e}"
                )
            finally:
                self.client = None

    async def get_me(self):
        """Get current user information."""
        if not self.client or not await self.client.is_user_authorized():
            return None

        try:
            return await self.client.get_me()
        except Exception as e:
            logger.error(
                f"Failed to get user info for {self.user_id} ({self.username}): {e}"
            )
            return None

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected and authorized."""
        return (
            self.client is not None and self.client.is_connected() and self._is_running
        )

    def get_auth_state(self) -> str:
        """Get current authentication state."""
        return self._auth_state

    async def is_fully_authenticated(self) -> bool:
        """Check if user is fully authenticated and ready to use."""
        return (
            self._auth_state == "authenticated"
            and self.client
            and await self.client.is_user_authorized()
        )

    async def restore_from_session(self) -> bool:
        """Restore client from existing session file without sending new code."""
        try:
            # Check if session file exists
            session_file = f"{self.session_name}.session"
            if not os.path.exists(session_file):
                logger.warning(
                    f"No session file found for user {self.user_id}: {session_file}"
                )
                return False

            # Create client with existing session
            self.client = TelegramClient(
                self.session_name,
                self.api_id,
                self.api_hash,
                device_model=f"UserBot-{self.username}",
                app_version="1.0.0",
                system_version="Linux",
            )

            await self.client.connect()
            logger.info(
                f"Telegram client connected for user {self.user_id} using existing session"
            )

            # Check if already signed in
            if await self.client.is_user_authorized():
                logger.info(
                    f"User {self.user_id} ({self.username}) restored from session - already authorized"
                )
                self._auth_state = "authenticated"
                return True
            else:
                logger.warning(
                    f"Session file exists but user {self.user_id} is not authorized"
                )
                await self.client.disconnect()
                self.client = None
                return False

        except Exception as e:
            logger.error(
                f"Failed to restore session for user {self.user_id} ({self.username}): {e}"
            )
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            return False

    def _get_message_type(self, message) -> str:
        """Determine the type of message for energy cost calculation."""
        try:
            # Check for media first
            if hasattr(message, "media") and message.media:
                # Photo
                if hasattr(message.media, "photo") and message.media.photo:
                    return "photo"

                # Document (can be various things)
                if hasattr(message.media, "document") and message.media.document:
                    doc = message.media.document
                    mime_type = getattr(doc, "mime_type", "")

                    # Video
                    if mime_type.startswith("video/"):
                        return "video"

                    # GIF/Animation
                    if mime_type == "video/mp4" and any(
                        attr.alt == "animated"
                        for attr in getattr(doc, "attributes", [])
                    ):
                        return "gif"
                    if mime_type == "image/gif":
                        return "gif"

                    # Audio
                    if mime_type.startswith("audio/"):
                        return "audio"

                    # Voice message
                    if any(
                        hasattr(attr, "voice")
                        for attr in getattr(doc, "attributes", [])
                    ):
                        return "voice"

                    # Sticker
                    if any(
                        hasattr(attr, "stickerset")
                        for attr in getattr(doc, "attributes", [])
                    ):
                        return "sticker"

                    # General document
                    return "document"

                # Game
                if hasattr(message.media, "game") and message.media.game:
                    return "game"

                # Poll
                if hasattr(message.media, "poll") and message.media.poll:
                    return "poll"

                # Contact
                if hasattr(message.media, "contact") and message.media.contact:
                    return "contact"

                # Location/Venue
                if hasattr(message.media, "geo") and message.media.geo:
                    if hasattr(message.media, "venue") and message.media.venue:
                        return "venue"
                    return "location"

                # Web page preview
                if hasattr(message.media, "webpage") and message.media.webpage:
                    return "web_page"

            # Check if it's part of a media group (album)
            if hasattr(message, "grouped_id") and message.grouped_id:
                return "media_group"

            # Default to text message
            return "text"

        except Exception as e:
            logger.warning(f"Error determining message type: {e}")
            return "text"  # Default fallback

    async def _send_roleplay_message(self, original_event, roleplay_text: str):
        """Send a roleplay message without triggering energy consumption."""
        try:
            # Add a special flag to identify this as a roleplay message
            # We check for this flag in the message handler to skip energy consumption
            roleplay_msg = f"🎭 {roleplay_text}"

            # Send the roleplay message
            await self.client.send_message(original_event.chat_id, roleplay_msg)

            logger.info(
                f"🎭 Sent roleplay message for low energy: {roleplay_text[:50]}..."
            )

        except Exception as e:
            logger.error(f"Error sending roleplay message: {e}")
            # Don't re-raise, just log the error


class TelegramClientManager:
    """Manages multiple Telegram client instances for different users."""

    def __init__(self, api_id: int, api_hash: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.clients: Dict[int, TelegramUserBot] = {}
        self._lock = asyncio.Lock()

    async def get_client(self, user_id: int) -> Optional[TelegramUserBot]:
        """Get existing client for user."""
        async with self._lock:
            return self.clients.get(user_id)

    async def get_or_create_client(
        self, user_id: int, username: str, phone_number: str
    ) -> TelegramUserBot:
        """Get existing client or create new one for user."""
        async with self._lock:
            if user_id not in self.clients:
                client = TelegramUserBot(
                    self.api_id, self.api_hash, phone_number, user_id, username
                )
                self.clients[user_id] = client
                logger.info(
                    f"Created new Telegram client for user {user_id} ({username})"
                )
            return self.clients[user_id]

    async def remove_client(self, user_id: int) -> bool:
        """Remove and disconnect client for user."""
        async with self._lock:
            if user_id in self.clients:
                client = self.clients[user_id]
                await client.disconnect()
                del self.clients[user_id]
                logger.info(f"Removed Telegram client for user {user_id}")

                # Also clean up session file
                try:
                    session_file = f"{client.session_name}.session"
                    if os.path.exists(session_file):
                        os.remove(session_file)
                        logger.info(f"Removed session file for user {user_id}")
                except Exception as e:
                    logger.error(
                        f"Failed to remove session file for user {user_id}: {e}"
                    )

                return True
            return False

    async def disconnect_all(self):
        """Disconnect all clients."""
        async with self._lock:
            for user_id, client in list(self.clients.items()):
                try:
                    await client.disconnect()
                    logger.info(f"Disconnected client for user {user_id}")
                except Exception as e:
                    logger.error(f"Error disconnecting client for user {user_id}: {e}")
            self.clients.clear()

    def get_client_count(self) -> int:
        """Get total number of active clients."""
        return len(self.clients)

    def get_connected_users(self) -> list:
        """Get list of connected user IDs."""
        return [
            {
                "user_id": user_id,
                "username": client.username,
                "phone": client.phone_number,
            }
            for user_id, client in self.clients.items()
            if client.is_connected
        ]

    async def recover_clients_from_sessions(self, db_manager):
        """Recover clients from existing session files on startup."""
        logger.info("🔄 Starting client recovery from session files...")

        sessions_dir = "sessions"
        if not os.path.exists(sessions_dir):
            logger.info("No sessions directory found, skipping recovery")
            return

        # Get all session files
        session_files = [f for f in os.listdir(sessions_dir) if f.endswith(".session")]
        logger.info(f"Found {len(session_files)} session files to process")

        recovered_count = 0

        for session_file in session_files:
            try:
                # Parse session filename to extract user_id and phone
                # Format: user_{user_id}_{phone}.session
                base_name = session_file.replace(".session", "")
                if not base_name.startswith("user_"):
                    continue

                parts = base_name.split("_")
                if len(parts) < 3:
                    continue

                user_id = int(parts[1])
                phone_number = "+" + parts[2]  # Add back the + prefix

                logger.info(
                    f"Attempting to recover session for user {user_id}, phone {phone_number}"
                )

                # Get user details from database
                try:
                    user_data = await db_manager.get_user_by_id(user_id)
                except Exception as db_error:
                    logger.error(
                        f"Database error while checking user {user_id}: {db_error}"
                    )
                    continue

                if not user_data:
                    logger.warning(
                        f"User {user_id} not found in database, skipping session recovery"
                    )
                    continue

                username = user_data["username"]

                # Create client instance
                client = TelegramUserBot(
                    self.api_id, self.api_hash, phone_number, user_id, username
                )

                # Try to restore from session
                if await client.restore_from_session():
                    # Session restored successfully
                    async with self._lock:
                        self.clients[user_id] = client

                    # Start message listener
                    listener_started = await client.start_message_listener()
                    if listener_started:
                        logger.info(
                            f"✅ Successfully recovered and started listener for user {user_id} ({username})"
                        )
                        recovered_count += 1

                        # Update database to reflect connection status
                        try:
                            await db_manager.update_user_telegram_info(
                                user_id, phone_number, True
                            )
                        except Exception as db_error:
                            logger.error(
                                f"Database error updating user {user_id} status: {db_error}"
                            )
                            # Continue anyway, the client is still recovered
                    else:
                        logger.error(
                            f"❌ Failed to start message listener for recovered user {user_id} ({username})"
                        )
                        # Remove from clients if listener failed
                        async with self._lock:
                            if user_id in self.clients:
                                del self.clients[user_id]
                        await client.disconnect()
                else:
                    logger.warning(
                        f"❌ Failed to restore session for user {user_id} ({username})"
                    )
                    await client.disconnect()

            except Exception as e:
                logger.error(f"Error recovering session from {session_file}: {e}")
                import traceback

                traceback.print_exc()

        if recovered_count > 0:
            logger.info(
                f"🎉 Successfully recovered {recovered_count} client(s) from session files"
            )
        else:
            logger.info("No clients were recovered from session files")


# Global manager instance
telegram_manager = None


def initialize_telegram_manager(api_id: int, api_hash: str):
    """Initialize the global telegram manager."""
    global telegram_manager
    telegram_manager = TelegramClientManager(api_id, api_hash)
    return telegram_manager


def get_telegram_manager():
    """Get the global telegram manager instance."""
    global telegram_manager
    return telegram_manager
