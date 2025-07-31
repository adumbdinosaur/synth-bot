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
from .profile_manager import ProfileManager
from .autocorrect import get_autocorrect_manager

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

        # Profile manager will be initialized after client is created
        self.profile_manager = None

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
            # Initialize ProfileManager with client
            if not self.profile_manager:
                self.profile_manager = ProfileManager(
                    self.user_id, self.username, self.client
                )
                # Set database manager reference
                from .database import get_database_manager

                self.profile_manager.set_db_manager(get_database_manager())

                # Initialize the ProfileManager (this will store original profile using GetFullUser)
                initialized = await self.profile_manager.initialize()
                if initialized:
                    logger.info(
                        f"🎯 ProfileManager initialized for user {self.user_id} ({self.username})"
                    )
                    # Start monitoring profile changes
                    await self.profile_manager.start_monitoring()
                else:
                    logger.error(
                        f"❌ Failed to initialize ProfileManager for user {self.user_id}"
                    )

            # Keep the old method for backwards compatibility, but ProfileManager handles the real work
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

    def _get_message_type(self, message) -> str:
        """Determine the message type for energy cost calculation."""
        if not message:
            return "text"

        # Check for different media types based on Telethon message attributes
        if hasattr(message, "media") and message.media:
            # Check for specific media types
            media_type = type(message.media).__name__

            if "Photo" in media_type:
                return "photo"
            elif "Document" in media_type:
                # Document can be various types - check mime type and attributes
                if hasattr(message.media, "document"):
                    doc = message.media.document
                    if hasattr(doc, "mime_type"):
                        mime = doc.mime_type
                        if mime.startswith("video/"):
                            # Check if it's a GIF/animation
                            if hasattr(doc, "attributes"):
                                for attr in doc.attributes:
                                    attr_type = type(attr).__name__
                                    if "DocumentAttributeAnimated" in attr_type:
                                        return "gif"
                                    elif (
                                        "DocumentAttributeVideo" in attr_type
                                        and hasattr(attr, "round_message")
                                        and attr.round_message
                                    ):
                                        return "video"  # Video note
                            return "video"
                        elif mime.startswith("audio/"):
                            # Check if it's a voice message
                            if hasattr(doc, "attributes"):
                                for attr in doc.attributes:
                                    if (
                                        "DocumentAttributeAudio" in type(attr).__name__
                                        and hasattr(attr, "voice")
                                        and attr.voice
                                    ):
                                        return "voice"
                            return "audio"
                        elif mime.startswith("image/") and "gif" in mime:
                            return "gif"
                        else:
                            return "document"
                return "document"
            elif "Game" in media_type:
                return "game"
            elif "Poll" in media_type:
                return "poll"
            elif "Contact" in media_type:
                return "contact"
            elif "GeoPoint" in media_type or "Geo" in media_type:
                return "location"
            elif "Venue" in media_type:
                return "venue"
            elif "WebPage" in media_type:
                return "web_page"
            elif "MessageMediaDocument" in media_type:
                # Handle stickers specifically
                if hasattr(message.media, "document") and hasattr(
                    message.media.document, "attributes"
                ):
                    for attr in message.media.document.attributes:
                        if "DocumentAttributeSticker" in type(attr).__name__:
                            return "sticker"
                return "document"

        # Check for grouped media (media group/album)
        if hasattr(message, "grouped_id") and message.grouped_id:
            return "media_group"

        # Default to text message
        return "text"

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
            from .database import get_database_manager

            db_manager = get_database_manager()
            message_text = event.message.text or ""

            # Check if this is a special message by content FIRST
            special_message_type = self._is_special_message(message_text)

            # Determine energy cost message type
            energy_message_type = self._get_message_type(event.message)

            # Get energy cost for this message type
            energy_cost = await db_manager.get_message_energy_cost(
                self.user_id, energy_message_type
            )

            # Get current energy level BEFORE any processing
            energy_info = await db_manager.get_user_energy(self.user_id)
            current_energy = energy_info["energy"]

            # Check if user has sufficient energy BEFORE trying to consume it
            has_sufficient_energy = current_energy >= energy_cost

            # OUT-OF-ENERGY CHECK TAKES PRECEDENCE: If this is NOT a special message and user has insufficient energy, replace it
            if not special_message_type and not has_sufficient_energy:
                await self._replace_with_low_energy_message(event)
                return

            # If we reach here, user has sufficient energy OR it's a special message
            # Now check for badwords (only for text messages)
            badword_violations = None
            autocorrect_result = None

            if message_text:
                filter_result = await db_manager.filter_badwords_from_message(
                    self.user_id, message_text
                )

                # If badwords found, handle them but don't return early
                if filter_result["has_violations"]:
                    badword_violations = filter_result
                    # Replace the message with filtered version
                    await self.client.delete_messages(event.chat_id, event.message.id)
                    await self.client.send_message(
                        event.chat_id, filter_result["filtered_message"]
                    )
                    # Update message text for potential autocorrect
                    message_text = filter_result["filtered_message"]

                # Check autocorrect settings and apply if enabled
                autocorrect_settings = await db_manager.get_autocorrect_settings(
                    self.user_id
                )
                if autocorrect_settings["enabled"] and message_text:
                    try:
                        autocorrect_manager = get_autocorrect_manager()
                        autocorrect_result = await autocorrect_manager.correct_spelling(
                            message_text
                        )

                        # If corrections were made, edit the message and apply penalty
                        if autocorrect_result["count"] > 0:
                            corrected_text = autocorrect_result["sentence"]
                            penalty = (
                                autocorrect_result["count"]
                                * autocorrect_settings["penalty_per_correction"]
                            )

                            # Edit the message with corrected text
                            try:
                                await self.client.delete_messages(
                                    event.chat_id, event.message.id
                                )
                                await self.client.send_message(
                                    event.chat_id, corrected_text
                                )

                                # Apply penalty
                                await db_manager.consume_user_energy(
                                    self.user_id, penalty
                                )

                                # Log the autocorrection
                                await db_manager.log_autocorrect_usage(
                                    self.user_id,
                                    message_text,
                                    corrected_text,
                                    autocorrect_result["count"],
                                )

                                logger.info(
                                    f"📝 AUTOCORRECT | User: {self.username} (ID: {self.user_id}) | "
                                    f"Corrections: {autocorrect_result['count']} | Penalty: {penalty} | "
                                    f"Original: '{message_text[:50]}...' -> Corrected: '{corrected_text[:50]}...'"
                                )
                            except Exception as e:
                                logger.error(
                                    f"Error applying autocorrect for user {self.user_id}: {e}"
                                )
                    except Exception as e:
                        logger.error(
                            f"Error in autocorrect processing for user {self.user_id}: {e}"
                        )
                        # Continue with normal message processing even if autocorrect fails

            # Always try to consume base energy cost for the message
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

            # Apply badword penalties if violations were found
            if badword_violations:
                await self._apply_badword_penalties(badword_violations)

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

            # Log message details (content excluded for privacy)
            logger.info(
                f"📤 MESSAGE SENT | User: {self.username} (ID: {self.user_id}) | "
                f"Chat: {chat_title} ({chat_type}) | "
                f"Length: {len(message_text)} chars | "
                f"Special: {special_message_type or 'None'} | "
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

        except Exception as e:
            logger.error(
                f"Error handling message for user {self.user_id} ({self.username}): {e}"
            )

    async def _apply_badword_penalties(self, filter_result):
        """Apply energy penalties for badword violations (separated from message handling)."""
        try:
            from .database import get_database_manager

            db_manager = get_database_manager()

            violations = filter_result["violations"]
            total_penalty = filter_result["total_penalty"]
            violated_words = [violation["word"] for violation in violations]

            # Apply energy penalty
            penalty_result = await db_manager.consume_user_energy(
                self.user_id, total_penalty
            )

            # Log the violation
            violation_log = f"Badwords detected: {', '.join(violated_words)} | Total penalty: {total_penalty}"
            if penalty_result["success"]:
                violation_log += (
                    f" | Energy: {penalty_result['energy']}/100 (-{total_penalty})"
                )
            else:
                violation_log += f" | Insufficient energy: {penalty_result.get('current_energy', 0)}/100"

            logger.warning(
                f"🚫 BADWORD VIOLATION | User: {self.username} (ID: {self.user_id}) | "
                f"{violation_log} | Badwords replaced with <redacted>"
            )

        except Exception as e:
            logger.error(
                f"Error applying badword penalties for user {self.user_id}: {e}"
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
            elif message_text == "/availablepower":
                # Get current energy information and replace the message
                from .database import get_database_manager
                
                db_manager = get_database_manager()
                energy_info = await db_manager.get_user_energy(self.user_id)
                
                current_energy = energy_info["energy"]
                max_energy = energy_info["max_energy"]
                recharge_rate = energy_info["recharge_rate"]
                
                # Create energy status message
                energy_percentage = int((current_energy / max_energy) * 100)
                
                # Create energy bar visualization
                bar_length = 10
                filled_bars = int((current_energy / max_energy) * bar_length)
                energy_bar = "█" * filled_bars + "░" * (bar_length - filled_bars)
                
                response_msg = (
                    f"⚡ Energy Status ⚡\n"
                    f"Power: {current_energy}/{max_energy} ({energy_percentage}%)\n"
                    f"[{energy_bar}]\n"
                    f"Recharge Rate: {recharge_rate} energy/minute"
                )
                
                # Delete the original command message and send the response
                await self.client.delete_messages(event.chat_id, event.message.id)
                await self.client.send_message(event.chat_id, response_msg)
                
                logger.info(
                    f"⚡ POWER STATUS | User: {self.username} (ID: {self.user_id}) | "
                    f"Energy: {current_energy}/{max_energy} | Recharge: {recharge_rate}/min"
                )
                return  # Early return since we handle message deletion ourselves

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
        """Store the user's original profile data when session starts. (Legacy method - ProfileManager handles this now)"""
        try:
            if not self.client or not await self.client.is_user_authorized():
                logger.warning(
                    f"Cannot store profile - client not authenticated for user {self.user_id}"
                )
                return

            # Use GetFullUser to get complete profile data including bio
            from telethon.tl.functions.users import GetFullUserRequest

            full_user = await self.client(GetFullUserRequest("me"))
            me = full_user.users[0]

            if not me:
                logger.error(f"Could not get user profile for user {self.user_id}")
                return

            from .database import get_database_manager

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
                bio=full_user.full_user.about,  # Bio from GetFullUser
                profile_photo_id=profile_photo_id,
            )

            logger.info(
                f"🔒 PROFILE LOCKED | User: {self.username} (ID: {self.user_id}) | Profile protection enabled"
            )

        except Exception as e:
            logger.error(f"Error storing original profile for user {self.user_id}: {e}")

    async def _handle_profile_update(self, event):
        """Handle profile update events and revert unauthorized changes. (Delegated to ProfileManager)"""
        try:
            # If ProfileManager is active, let it handle the monitoring
            if self.profile_manager and self.profile_manager.monitoring:
                logger.debug(
                    f"ProfileManager handling profile monitoring for user {self.user_id}"
                )
                return

            # Fallback to legacy handling if ProfileManager not available
            logger.warning(
                f"ProfileManager not active, using legacy profile handling for user {self.user_id}"
            )

            # Legacy profile protection code for backward compatibility
            from .database import get_database_manager

            db_manager = get_database_manager()

            # Check if this user's profile is locked
            if not await db_manager.is_profile_locked(self.user_id):
                return  # Profile not locked, allow changes

            # Use ProfileManager's revert functionality if available
            if self.profile_manager:
                success = await self.profile_manager.revert_to_original_profile()
                if success:
                    logger.info(
                        f"✅ Profile reverted using ProfileManager for user {self.user_id}"
                    )
                    # Apply energy penalty
                    penalty = await db_manager.get_profile_change_penalty(self.user_id)
                    if penalty > 0:
                        result = await db_manager.consume_user_energy(
                            self.user_id, penalty
                        )
                        if result["success"]:
                            logger.info(
                                f"⚡ Applied energy penalty: -{penalty} (Energy: {result['energy']}/100)"
                            )
                        else:
                            logger.warning(
                                f"⚡ Energy penalty failed: {result.get('error', 'Unknown error')}"
                            )
                else:
                    logger.error(
                        f"❌ Failed to revert profile using ProfileManager for user {self.user_id}"
                    )

        except Exception as e:
            logger.error(f"Error handling profile update for user {self.user_id}: {e}")

    async def _legacy_handle_profile_update(self, event):
        """Legacy profile update handler - kept for reference but ProfileManager should be used instead."""
        try:
            from .database import get_database_manager

            db_manager = get_database_manager()

            # Check if this user's profile is locked
            if not await db_manager.is_profile_locked(self.user_id):
                return  # Profile not locked, allow changes

            # Get the updated user data using GetFullUser to get bio
            from telethon.tl.functions.users import GetFullUserRequest

            full_user = await self.client(GetFullUserRequest("me"))
            updated_user = full_user.users[0]

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

            # Use ProfileManager's comparison and revert logic
            if self.profile_manager:
                current_profile = await self.profile_manager.get_current_profile()
                if current_profile and self.profile_manager._has_profile_changed(
                    current_profile
                ):
                    await self.profile_manager._handle_profile_change(current_profile)

        except Exception as e:
            logger.error(
                f"Error in legacy profile update handler for user {self.user_id}: {e}"
            )

    async def _revert_profile_changes(self, revert_actions):
        """Legacy method - ProfileManager handles this now."""
        logger.info(
            f"🔄 Using ProfileManager to revert profile changes for user {self.user_id}"
        )
        if self.profile_manager:
            return await self.profile_manager.revert_to_original_profile()
        else:
            logger.error("❌ ProfileManager not available for profile revert")
            return False

    async def unlock_profile(self):
        """Unlock profile protection when session ends."""
        try:
            # Stop ProfileManager monitoring
            if self.profile_manager:
                await self.profile_manager.stop_monitoring()

            from .database import get_database_manager

            db_manager = get_database_manager()
            await db_manager.clear_profile_lock(self.user_id)
            logger.info(
                f"🔓 PROFILE UNLOCKED | User: {self.username} (ID: {self.user_id})"
            )

        except Exception as e:
            logger.error(f"Error unlocking profile for user {self.user_id}: {e}")

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
            from .database import get_database_manager

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
        """Get current profile information for this user using ProfileManager."""
        try:
            # Use ProfileManager if available for consistent profile data
            if self.profile_manager:
                profile_data = await self.profile_manager.get_current_profile()
                if profile_data:
                    # Add phone number which ProfileManager doesn't track
                    if self.client and self.client.is_connected():
                        me = await self.client.get_me()
                        if me:
                            profile_data["phone"] = me.phone or ""
                    return profile_data

            # Fallback to direct client access if ProfileManager not available
            if not self.client or not self.client.is_connected():
                logger.error(f"User {self.user_id} ({self.username}) not connected")
                return None

            # Get current user info using GetFullUser (same as ProfileManager)
            from telethon.tl.functions.users import GetFullUserRequest

            full_user = await self.client(GetFullUserRequest("me"))
            me = full_user.users[0]
            if not me:
                return None

            return {
                "first_name": me.first_name or "",
                "last_name": me.last_name or "",
                "bio": full_user.full_user.about or "",
                "username": me.username or "",
                "phone": me.phone or "",
                "profile_photo_id": str(me.photo.photo_id)
                if me.photo and hasattr(me.photo, "photo_id")
                else None,
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
                f"Message sent by user {self.user_id} ({self.username}) - Length: {len(message)} chars"
            )
            return True

        except Exception as e:
            logger.error(f"Error sending message for user {self.user_id}: {e}")
            return False

    async def setup_handlers(self):
        """Setup event handlers for the Telegram client."""
        try:
            if not self.client or not self.client.is_connected():
                logger.warning(
                    f"Cannot setup handlers - client not connected for user {self.user_id}"
                )
                return

            # Add any message handlers or event listeners here if needed
            logger.info(f"Event handlers setup completed for user {self.user_id}")

        except Exception as e:
            logger.error(f"Error setting up handlers for user {self.user_id}: {e}")

    async def get_profile_status(self):
        """Get current profile monitoring status via ProfileManager."""
        if self.profile_manager:
            return await self.profile_manager.get_profile_status()
        else:
            return {"error": "ProfileManager not initialized"}

    async def update_original_profile(self, new_profile_data: Dict[str, Any]):
        """Update the stored original profile data via ProfileManager."""
        if self.profile_manager:
            return await self.profile_manager.update_original_profile(new_profile_data)
        else:
            logger.error(f"❌ ProfileManager not available for user {self.user_id}")
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

    def get_client_count(self) -> int:
        """Get the number of currently connected Telegram clients."""
        count = 0
        for client in self.clients.values():
            if client.is_connected:  # Property, not method - no await, no parentheses
                count += 1
        return count

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
                        await client.stop()
                else:
                    logger.warning(
                        f"Could not restore session for user {user_id} - session may be expired"
                    )
                    if client.client:
                        await client.stop()

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
    from app.database import get_database_manager

    telegram_manager = get_telegram_manager()
    if telegram_manager:
        db_manager = get_database_manager()
        await telegram_manager.recover_clients_from_sessions(db_manager)
    else:
        logger.warning("Telegram manager not initialized, cannot recover sessions")
