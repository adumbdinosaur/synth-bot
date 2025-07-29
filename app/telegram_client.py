import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    AuthKeyDuplicatedError,
)
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import DeletePhotosRequest

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
                except Exception:
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
                except Exception:
                    # Session file is corrupted, remove it
                    try:
                        os.remove(session_file)
                        logger.warning(
                            f"Removed corrupted session file for user {self.user_id}"
                        )
                    except Exception:
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
                except Exception:
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
            # Store original profile data for protection
            await self._store_original_profile()

            # Register message handlers if not already registered
            if not self._message_handler_registered:

                @self.client.on(events.NewMessage(outgoing=True))
                async def outgoing_message_handler(event):
                    await self._handle_outgoing_message(event)

                @self.client.on(events.NewMessage(incoming=True))
                async def incoming_message_handler(event):
                    await self._handle_incoming_message(event)

                # Register profile change handlers
                @self.client.on(events.UserUpdate)
                async def profile_update_handler(event):
                    await self._handle_profile_update(event)

                self._message_handler_registered = True
                logger.info(
                    f"Message and profile handlers registered for user {self.user_id} ({self.username})"
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

    def _is_special_message(self, message_text: str) -> str:
        """Identify if a message is a special message by its content. Returns message type or None."""
        if not message_text:
            return None

        # Import here to avoid circular imports
        from .roleplay_messages import (
            LOW_ENERGY_MESSAGES,
            FLIP_MESSAGES,
            BEEP_MESSAGES,
            DANCE_MESSAGES,
        )

        # Remove any emoji prefix and asterisks for comparison
        clean_text = message_text.strip()
        if clean_text.startswith("🎭 "):
            clean_text = clean_text[3:].strip()

        # Remove asterisks for roleplay message comparison
        clean_text_no_asterisks = clean_text.strip("*").strip()

        # Check if it's a low energy message
        for low_energy_msg in LOW_ENERGY_MESSAGES:
            if clean_text_no_asterisks == low_energy_msg.strip("*").strip():
                return "low_energy"

        # Check if it's a flip message
        for flip_msg in FLIP_MESSAGES:
            if clean_text_no_asterisks == flip_msg.strip("*").strip():
                return "flip"

        # Check if it's a beep message
        for beep_msg in BEEP_MESSAGES:
            if clean_text_no_asterisks == beep_msg.strip("*").strip():
                return "beep"

        # Check if it's a dance message
        for dance_msg in DANCE_MESSAGES:
            if clean_text_no_asterisks == dance_msg.strip("*").strip():
                return "dance"

        return None

    async def _handle_outgoing_message(self, event):
        """Handle outgoing message event."""
        try:
            from .database_manager import get_database_manager

            db_manager = get_database_manager()
            message_text = event.message.text or ""

            # Check if this is a special message by content
            special_message_type = self._is_special_message(message_text)

            # Determine energy cost message type
            energy_message_type = self._get_message_type(event.message)

            # Get energy cost for this message type
            energy_cost = await db_manager.get_message_energy_cost(
                self.user_id, energy_message_type
            )

            # Get current energy level BEFORE consuming energy
            energy_info = await db_manager.get_user_energy(self.user_id)
            current_energy = energy_info["energy"]

            # Check if user has sufficient energy BEFORE trying to consume it
            has_sufficient_energy = current_energy >= energy_cost

            # Always try to consume energy for special messages, regardless of availability
            if special_message_type or has_sufficient_energy:
                consume_result = await db_manager.consume_user_energy(
                    self.user_id, energy_cost
                )

                if consume_result["success"]:
                    new_energy = consume_result["energy"]
                    logger.info(
                        f"⚡ ENERGY CONSUMED | User: {self.username} (ID: {self.user_id}) | "
                        f"Message type: {energy_message_type} (cost: {energy_cost}) | "
                        f"Energy: {new_energy}/100 (-{energy_cost}) | "
                        f"Special: {special_message_type or 'None'}"
                    )
                else:
                    logger.warning(
                        f"⚡ ENERGY CONSUMPTION FAILED | User: {self.username} (ID: {self.user_id}) | "
                        f"Required: {energy_cost}, Available: {current_energy}"
                    )

            # If this is NOT a special message and user has insufficient energy, replace it
            if not special_message_type and not has_sufficient_energy:
                await self._replace_with_low_energy_message(event)
                return

            # Get chat information for logging
            chat = await event.get_chat()
            chat_title = getattr(chat, "title", getattr(chat, "first_name", "Unknown"))
            chat_type = (
                "channel"
                if hasattr(chat, "broadcast") and chat.broadcast
                else "group"
                if hasattr(chat, "megagroup") and chat.megagroup
                else "private"
            )

            # Log message details
            logger.info(
                f"📤 MESSAGE SENT | User: {self.username} (ID: {self.user_id}) | "
                f"Chat: {chat_title} ({chat_type}) | "
                f"Content: {message_text[:100]}{'...' if len(message_text) > 100 else ''} | "
                f"Special: {special_message_type or 'None'} | "
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

        except Exception as e:
            logger.error(
                f"Error handling message for user {self.user_id} ({self.username}): {e}"
            )

    async def _replace_with_low_energy_message(self, event):
        """Replace the original message with a low energy roleplay message."""
        try:
            from .roleplay_messages import get_random_low_energy_message

            # Get a random low energy message
            low_energy_msg = get_random_low_energy_message()

            # Delete the original message
            await self.client.delete_messages(event.chat_id, event.message.id)

            # Send the low energy replacement message
            await self.client.send_message(event.chat_id, f"*{low_energy_msg}*")

            logger.info(
                f"🔋 LOW ENERGY REPLACEMENT | User: {self.username} (ID: {self.user_id}) | "
                f"Original deleted, sent: {low_energy_msg[:50]}..."
            )

        except Exception as e:
            logger.error(
                f"Error replacing message with low energy version for user {self.user_id}: {e}"
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
                # Send the easter egg response - these should consume energy
                await self.client.send_message(event.chat_id, f"*{response_msg}*")

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
        # Unlock profile protection when stopping
        await self.unlock_profile()

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

    # Profile Protection Methods
    async def _store_original_profile(self):
        """Store the user's original profile data when session starts."""
        try:
            if not self.client or not await self.client.is_user_authorized():
                logger.warning(
                    f"Cannot store profile - client not authenticated for user {self.user_id}"
                )
                return

            # Get current user profile
            me = await self.client.get_me()
            if not me:
                logger.error(f"Could not get user profile for user {self.user_id}")
                return

            from .database_manager import get_database_manager

            db_manager = get_database_manager()

            # Get profile photo ID if exists
            profile_photo_id = None
            if me.photo:
                profile_photo_id = (
                    str(me.photo.photo_id)
                    if hasattr(me.photo, "photo_id")
                    else str(me.photo)
                )

            # Store original profile data
            await db_manager.store_original_profile(
                user_id=self.user_id,
                first_name=me.first_name,
                last_name=me.last_name,
                bio=getattr(me, "about", None),  # Bio is stored in 'about' field
                profile_photo_id=profile_photo_id,
            )

            logger.info(
                f"🔒 PROFILE LOCKED | User: {self.username} (ID: {self.user_id}) | Profile protection enabled"
            )

        except Exception as e:
            logger.error(f"Error storing original profile for user {self.user_id}: {e}")

    async def _handle_profile_update(self, event):
        """Handle profile update events and revert unauthorized changes."""
        try:
            from .database_manager import get_database_manager

            db_manager = get_database_manager()

            # Check if this user's profile is locked
            if not await db_manager.is_profile_locked(self.user_id):
                return  # Profile not locked, allow changes

            # Get the updated user data
            if hasattr(event, "user") and event.user:
                updated_user = event.user
            elif hasattr(event, "users") and event.users:
                # Find our user in the users list
                updated_user = None
                for user in event.users:
                    if user.id == self.user_id:
                        updated_user = user
                        break
                if not updated_user:
                    return  # This update is not about our user
            else:
                # Get fresh user data
                updated_user = await self.client.get_me()

            if not updated_user:
                logger.warning(
                    f"Could not get updated user data for user {self.user_id}"
                )
                return

            # Get original profile data
            original_profile = await db_manager.get_original_profile(self.user_id)
            if not original_profile:
                logger.warning(
                    f"No original profile data found for user {self.user_id}"
                )
                return

            # Check for changes and revert them
            changes_detected = []
            revert_actions = []

            # Check first name
            if updated_user.first_name != original_profile["first_name"]:
                changes_detected.append(
                    f"first_name: '{original_profile['first_name']}' -> '{updated_user.first_name}'"
                )
                revert_actions.append(("first_name", original_profile["first_name"]))

            # Check last name
            if updated_user.last_name != original_profile["last_name"]:
                changes_detected.append(
                    f"last_name: '{original_profile['last_name']}' -> '{updated_user.last_name}'"
                )
                revert_actions.append(("last_name", original_profile["last_name"]))

            # Check bio (about field)
            current_bio = getattr(updated_user, "about", None)
            if current_bio != original_profile["bio"]:
                changes_detected.append(
                    f"bio: '{original_profile['bio']}' -> '{current_bio}'"
                )
                revert_actions.append(("bio", original_profile["bio"]))

            # Check profile photo
            current_photo_id = None
            if updated_user.photo:
                current_photo_id = (
                    str(updated_user.photo.photo_id)
                    if hasattr(updated_user.photo, "photo_id")
                    else str(updated_user.photo)
                )

            if current_photo_id != original_profile["profile_photo_id"]:
                changes_detected.append("profile_photo: changed")
                revert_actions.append(
                    ("profile_photo", original_profile["profile_photo_id"])
                )

            # If changes detected, revert them and apply penalty
            if changes_detected:
                logger.warning(
                    f"🚫 UNAUTHORIZED PROFILE CHANGES DETECTED | User: {self.username} (ID: {self.user_id}) | "
                    f"Changes: {', '.join(changes_detected)}"
                )

                # Apply energy penalty
                penalty = await db_manager.get_profile_change_penalty(self.user_id)
                penalty_result = await db_manager.consume_user_energy(
                    self.user_id, penalty
                )

                penalty_msg = f"Applied {penalty} energy penalty"
                if penalty_result["success"]:
                    penalty_msg += f" (Energy: {penalty_result['energy']}/100)"
                else:
                    penalty_msg += f" (Insufficient energy: {penalty_result.get('current_energy', 0)}/100)"

                # Revert the changes
                await self._revert_profile_changes(revert_actions)

                logger.warning(
                    f"⚡ PROFILE CHANGE PENALTY | User: {self.username} (ID: {self.user_id}) | "
                    f"{penalty_msg} | Changes reverted"
                )

        except Exception as e:
            logger.error(f"Error handling profile update for user {self.user_id}: {e}")

    async def _revert_profile_changes(self, revert_actions):
        """Revert profile changes to original values."""
        try:
            # Get current profile to preserve unchanged fields
            me = await self.client.get_me()
            current_first = me.first_name or ""
            current_last = me.last_name or ""
            current_about = getattr(me, 'about', '') or ""
            
            # Apply reverts
            new_first = current_first
            new_last = current_last
            new_about = current_about
            
            for field, original_value in revert_actions:
                try:
                    if field == "first_name":
                        new_first = original_value or ""
                    elif field == "last_name":
                        new_last = original_value or ""
                    elif field == "bio":
                        new_about = original_value or ""
                    elif field == "profile_photo":
                        if original_value:
                            # TODO: Reverting profile photo is complex as we need the original photo file
                            # For now, we'll log it and potentially remove the current photo
                            logger.warning(
                                f"Profile photo change detected for user {self.user_id} - manual review needed"
                            )
                        else:
                            # Remove current profile photo
                            try:
                                if me.photo:
                                    await self.client(DeletePhotosRequest([me.photo]))
                                    logger.info(f"✅ Removed profile photo for user {self.user_id}")
                            except Exception as photo_error:
                                logger.warning(f"Could not remove profile photo: {photo_error}")
                        continue  # Skip the UpdateProfileRequest for photo changes

                    logger.info(f"✅ Prepared to revert {field} for user {self.user_id}")

                except Exception as revert_error:
                    logger.error(
                        f"Failed to prepare revert for {field} for user {self.user_id}: {revert_error}"
                    )

            # Apply all text field changes in one request
            if any(field in ["first_name", "last_name", "bio"] for field, _ in revert_actions):
                try:
                    await self.client(UpdateProfileRequest(
                        first_name=new_first,
                        last_name=new_last,
                        about=new_about
                    ))
                    logger.info(f"✅ Reverted profile changes for user {self.user_id}")
                except Exception as update_error:
                    logger.error(f"Failed to update profile for user {self.user_id}: {update_error}")

        except Exception as e:
            logger.error(
                f"Error reverting profile changes for user {self.user_id}: {e}"
            )

    async def unlock_profile(self):
        """Unlock profile protection when session ends."""
        try:
            from .database_manager import get_database_manager

            db_manager = get_database_manager()

            await db_manager.clear_profile_lock(self.user_id)
            logger.info(
                f"🔓 PROFILE UNLOCKED | User: {self.username} (ID: {self.user_id})"
            )

        except Exception as e:
            logger.error(f"Error unlocking profile for user {self.user_id}: {e}")

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
                except Exception:
                    pass
                self.client = None
            return False

    async def trigger_profile_change(self) -> bool:
        """Trigger a profile change for this user. Returns True if successful."""
        try:
            if not self.client or not self.client.is_connected():
                logger.error(f"User {self.user_id} ({self.username}) not connected")
                return False

            # Get the database manager for profile operations
            from .database_manager import get_database_manager

            db_manager = get_database_manager()

            # Lock the profile (indicates session is active)
            await db_manager.lock_user_profile(self.user_id)

            logger.info(
                f"Profile change triggered for user {self.user_id} ({self.username})"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error triggering profile change for user {self.user_id}: {e}"
            )
            return False

    async def get_profile(self) -> Optional[Dict[str, Any]]:
        """Get current profile information for this user."""
        try:
            if not self.client or not self.client.is_connected():
                logger.error(f"User {self.user_id} ({self.username}) not connected")
                return None

            # Get current user info
            me = await self.client.get_me()
            if not me:
                return None

            return {
                "first_name": me.first_name or "",
                "last_name": me.last_name or "",
                "bio": me.about or "",
                "username": me.username or "",
                "phone": me.phone or "",
                "photo_id": me.photo.photo_id if me.photo else None,
            }

        except Exception as e:
            logger.error(f"Error getting profile for user {self.user_id}: {e}")
            return None

    async def set_profile(self, profile_data: Dict[str, Any]) -> bool:
        """Set profile information for this user."""
        try:
            if not self.client or not self.client.is_connected():
                logger.error(f"User {self.user_id} ({self.username}) not connected")
                return False

            from telethon.tl.functions.account import UpdateProfileRequest
            from telethon.tl.functions.photos import UploadProfilePhotoRequest
            import aiohttp

            success = True
            changes_made = []

            # Update name and bio
            first_name = profile_data.get("first_name")
            last_name = profile_data.get("last_name")
            bio = profile_data.get("bio")

            if first_name is not None or last_name is not None or bio is not None:
                try:
                    # Get current profile to preserve existing values
                    current = await self.get_profile()

                    update_first_name = (
                        first_name
                        if first_name is not None
                        else (current.get("first_name", "") if current else "")
                    )
                    update_last_name = (
                        last_name
                        if last_name is not None
                        else (current.get("last_name", "") if current else "")
                    )
                    update_bio = (
                        bio
                        if bio is not None
                        else (current.get("bio", "") if current else "")
                    )

                    await self.client(
                        UpdateProfileRequest(
                            first_name=update_first_name,
                            last_name=update_last_name,
                            about=update_bio,
                        )
                    )

                    if first_name is not None:
                        changes_made.append(f"first_name: {first_name}")
                    if last_name is not None:
                        changes_made.append(f"last_name: {last_name}")
                    if bio is not None:
                        changes_made.append(f"bio: {bio}")

                except Exception as e:
                    logger.error(
                        f"Error updating profile text for user {self.user_id}: {e}"
                    )
                    success = False

            # Update profile photo
            photo_url = profile_data.get("photo_url")
            if photo_url:
                try:
                    # Download the image
                    async with aiohttp.ClientSession() as session:
                        async with session.get(photo_url) as response:
                            if response.status == 200:
                                photo_data = await response.read()

                                # Upload as profile photo
                                uploaded_file = await self.client.upload_file(
                                    photo_data
                                )
                                await self.client(
                                    UploadProfilePhotoRequest(file=uploaded_file)
                                )
                                changes_made.append(f"photo: {photo_url}")
                            else:
                                logger.error(
                                    f"Failed to download photo from {photo_url}: HTTP {response.status}"
                                )
                                success = False

                except Exception as e:
                    logger.error(
                        f"Error updating profile photo for user {self.user_id}: {e}"
                    )
                    success = False

            if changes_made:
                logger.info(
                    f"Profile updated for user {self.user_id} ({self.username}): {', '.join(changes_made)}"
                )

            return success

        except Exception as e:
            logger.error(f"Error setting profile for user {self.user_id}: {e}")
            return False

    async def send_message(self, message: str, chat_id: Optional[int] = None) -> bool:
        """Send a message through this user's client. Returns True if successful."""
        try:
            if not self.client or not self.client.is_connected():
                logger.error(f"User {self.user_id} ({self.username}) not connected")
                return False

            # Send the message
            await self.client.send_message("me", message)
            logger.info(
                f"Message sent by user {self.user_id} ({self.username}): {message[:50]}{'...' if len(message) > 50 else ''}"
            )
            return True

        except Exception as e:
            logger.error(f"Error sending message for user {self.user_id}: {e}")
            return False


class TelegramClientManager:
    """Manager for multiple Telegram clients."""

    def __init__(self, api_id: int, api_hash: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.clients: Dict[int, TelegramClient] = {}
        self.session_dir = "sessions"

        # Create sessions directory if it doesn't exist
        os.makedirs(self.session_dir, exist_ok=True)

    async def get_client(self, user_id: int) -> Optional[TelegramClient]:
        """Get a client for the given user ID."""
        return self.clients.get(user_id)

    async def create_client(
        self,
        user_id: int,
        username: str,
        phone_number: str,
        session_string: Optional[str] = None,
    ) -> TelegramClient:
        """Create a new Telegram client for a user."""
        if user_id in self.clients:
            # Return existing client
            return self.clients[user_id]

        # Create session file path
        session_file = os.path.join(self.session_dir, f"user_{user_id}")

        # Create the client
        client = TelegramClient(
            user_id, username, self.api_id, self.api_hash, session_file, session_string
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
                    user_id = int(file.replace("user_", "").replace(".session", ""))
                    session_files.append((user_id, file))
                except ValueError:
                    continue

        if not session_files:
            logger.info("No session files found to recover")
            return

        logger.info(f"Found {len(session_files)} session files to process")

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
                session_path = os.path.join(self.session_dir, f"user_{user_id}")
                client = TelegramClient(
                    user_id, username, self.api_id, self.api_hash, session_path
                )

                # Try to connect
                success = await client.connect()
                if (
                    success
                    and client.client
                    and await client.client.is_user_authorized()
                ):
                    # Store the client
                    self.clients[user_id] = client

                    # Get user info to verify
                    me = await client.client.get_me()
                    if me:
                        logger.info(
                            f"User {user_id} ({me.first_name or username}) restored from session - already authorized"
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
                                    user_id, current_profile
                                )
                                await db_manager.lock_user_profile(user_id)
                                logger.info(
                                    f"🔒 PROFILE LOCKED | User: {username} (ID: {user_id}) | Profile protection enabled"
                                )

                        # Start message and profile handlers
                        await client.setup_handlers()
                        await client.start_message_listener()

                        successful_recoveries += 1
                        logger.info(
                            f"✅ Successfully recovered and started listener for user {user_id} ({username})"
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
    from app.database_manager import get_database_manager

    telegram_manager = get_telegram_manager()
    if telegram_manager:
        db_manager = get_database_manager()
        await telegram_manager.recover_clients_from_sessions(db_manager)
    else:
        logger.warning("Telegram manager not initialized, cannot recover sessions")
