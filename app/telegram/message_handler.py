"""
Message handler for Telegram userbot.
Handles incoming and outgoing message processing, energy consumption, badwords filtering, and autocorrect.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from telethon import events
from .base_handler import BaseHandler

logger = logging.getLogger(__name__)


class MessageHandler(BaseHandler):
    """Handles message-related operations for Telegram userbot."""

    def __init__(self, client_instance):
        super().__init__(client_instance)
        self._message_handler_registered = False

    async def register_handlers(self):
        """Register message event handlers."""
        if not self.client_instance.client or self._message_handler_registered:
            return False

        try:

            @self.client_instance.client.on(events.NewMessage(outgoing=True))
            async def outgoing_message_handler(event):
                await self._handle_outgoing_message(event)

            @self.client_instance.client.on(events.NewMessage(incoming=True))
            async def incoming_message_handler(event):
                await self._handle_incoming_message(event)

            self._message_handler_registered = True
            logger.info(
                f"Message handlers registered for user {self.client_instance.user_id} ({self.client_instance.username})"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to register message handlers for user {self.client_instance.user_id}: {e}"
            )
            return False

    async def _handle_outgoing_message(self, event):
        """Handle outgoing message event."""
        try:
            from ..database import get_database_manager

            db_manager = get_database_manager()
            message_text = event.message.text or ""

            # Check if this is an OOC (Out of Character) message FIRST - bypasses all filtering
            is_ooc_message = self._is_ooc_message(message_text)

            if is_ooc_message:
                # OOC messages bypass all filtering and energy requirements
                return

            # Check if user has a locked profile and should apply filtering based on list mode
            is_profile_locked = await db_manager.is_profile_locked(
                self.client_instance.user_id
            )
            if is_profile_locked:
                # Use the new unified filtering logic that supports both blacklist and whitelist modes
                should_filter = await db_manager.should_filter_chat(
                    self.client_instance.user_id, event.chat_id
                )
                if not should_filter:
                    # Get the current list mode for logging
                    list_mode = await db_manager.get_user_chat_list_mode(
                        self.client_instance.user_id
                    )
                    logger.info(
                        f"🔓 FILTERING BYPASSED | User: {self.client_instance.username} (ID: {self.client_instance.user_id}) | "
                        f"Chat: {event.chat_id} | Mode: {list_mode} | Filtering bypassed"
                    )
                    return

            # Check if this is a special message by content FIRST
            special_message_type = self._is_special_message(message_text)

            # Determine energy cost message type
            energy_message_type = self._get_message_type(event.message)

            # Get energy cost for this message type
            energy_cost = await db_manager.get_message_energy_cost(
                self.client_instance.user_id, energy_message_type
            )

            # Get current energy level BEFORE any processing
            energy_info = await db_manager.get_user_energy(self.client_instance.user_id)
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
                # Handle badwords filtering
                badword_violations = await self._process_badwords(
                    event, message_text, db_manager
                )
                if badword_violations:
                    message_text = badword_violations["filtered_message"]

                # Handle autocorrect and capture result
                autocorrect_result = await self._process_autocorrect(
                    event, message_text, db_manager
                )

            # Always consume base energy cost for the message (can go to 0 or below)
            consume_result = await db_manager.consume_user_energy(
                self.client_instance.user_id, energy_cost
            )

            new_energy = consume_result["energy"]
            # Get max energy for proper logging
            energy_info = await db_manager.get_user_energy(self.client_instance.user_id)
            max_energy = energy_info["max_energy"]

            logger.info(
                f"⚡ ENERGY CONSUMED | User: {self.client_instance.username} (ID: {self.client_instance.user_id}) | "
                f"Message type: {energy_message_type} (cost: {energy_cost}) | "
                f"Energy: {new_energy}/{max_energy} (-{energy_cost}) | "
                f"Special: {special_message_type or 'None'}"
            )

            # Apply badword penalties if violations were found
            if badword_violations:
                await self._apply_badword_penalties(badword_violations, event)

            # Save message to database for activity tracking
            try:
                # Extract chat information
                chat_id = event.chat_id if hasattr(event, "chat_id") else 0
                message_id = event.message.id if hasattr(event.message, "id") else 0

                # Save message to database (excluding content for privacy)
                await db_manager.save_telegram_message(
                    user_id=self.client_instance.user_id,
                    chat_id=chat_id,
                    message_id=message_id,
                    message_type=energy_message_type,
                    content="",  # Content excluded for privacy
                    energy_cost=energy_cost,
                )
            except Exception as save_error:
                logger.error(f"Error saving message to database: {save_error}")

            # Log message details (content excluded for privacy)
            # Skip logging if autocorrect was applied (corrections > 0) since the corrected message will be logged separately
            should_skip_logging = (
                message_text
                and autocorrect_result
                and autocorrect_result.get("count", 0) > 0
            )

            if not should_skip_logging:
                await self._log_message_details(
                    event, message_text, special_message_type
                )

        except Exception as e:
            logger.error(
                f"Error handling message for user {self.client_instance.user_id} ({self.client_instance.username}): {e}"
            )

    async def _handle_incoming_message(self, event):
        """Handle incoming message events for easter eggs and commands."""
        try:
            # Check if the message is a text message
            if not event.message.text:
                return

            message_text = event.message.text.strip()
            message_text_lower = message_text.lower()

            # Check for grant command first (before converting to lowercase for processing)
            if message_text_lower.startswith("/grant "):
                await self._handle_grant_command(event, message_text)
                return  # Early return since we handle the response ourselves

            # Check for easter egg commands
            response_msg = None
            command_type = None

            if message_text_lower == "/flip":
                from ..roleplay_messages import get_random_flip_message

                response_msg = get_random_flip_message()
                command_type = "FLIP"
            elif message_text_lower == "/beep":
                from ..roleplay_messages import get_random_beep_message

                response_msg = get_random_beep_message()
                command_type = "BEEP"
            elif message_text_lower == "/dance":
                from ..roleplay_messages import get_random_dance_message

                response_msg = get_random_dance_message()
                command_type = "DANCE"
            elif message_text_lower == "/availablepower":
                await self._handle_power_status_command(event)
                return  # Early return since we handle the response ourselves

            # If we have a response, send it
            if response_msg:
                # Send the easter egg response - these should consume energy
                try:
                    # Use the message's peer_id for more reliable entity resolution
                    chat_entity = event.message.peer_id
                    await self.client_instance.client.send_message(
                        chat_entity, f"*{response_msg}*"
                    )

                    logger.info(
                        f"🎪 {command_type} EASTER EGG | User: {self.client_instance.username} (ID: {self.client_instance.user_id}) | "
                        f"Responded to /{command_type.lower()} command with: {response_msg[:50]}..."
                    )
                except Exception as e:
                    logger.error(
                        f"Error sending easter egg response for user {self.client_instance.user_id}: {e}"
                    )

        except Exception as e:
            logger.error(
                f"Error handling incoming message for user {self.client_instance.user_id} ({self.client_instance.username}): {e}"
            )

    async def _handle_power_status_command(self, event):
        """Handle /availablepower command."""
        try:
            from ..database import get_database_manager

            db_manager = get_database_manager()
            energy_info = await db_manager.get_user_energy(self.client_instance.user_id)

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

            # Send a new message with the power status instead of editing the original
            chat_entity = event.message.peer_id
            await self.client_instance.client.send_message(
                chat_entity, f"*{response_msg}*"
            )

            logger.info(
                f"⚡ POWER STATUS | User: {self.client_instance.username} (ID: {self.client_instance.user_id}) | "
                f"Energy: {current_energy}/{max_energy} | Recharge: {recharge_rate}/min"
            )

        except Exception as e:
            logger.error(
                f"Error handling power status command for user {self.client_instance.user_id}: {e}"
            )

    async def _handle_grant_command(self, event, message_text: str):
        """Handle /grant @username amount command."""
        try:
            from ..database import get_database_manager

            # Get the actual sender of the message from the event
            sender_id = event.message.sender_id

            # Find which system user corresponds to this Telegram sender ID
            db_manager = get_database_manager()
            granter_user = None

            # Check all connected users to find who this Telegram sender is
            from ..telegram_client import get_telegram_manager

            telegram_manager = get_telegram_manager()

            if telegram_manager:
                connected_users = await telegram_manager.get_connected_users()
                for user_info in connected_users:
                    try:
                        user_client = await telegram_manager.get_client(
                            user_info["user_id"]
                        )
                        if user_client and user_client.client:
                            me = await user_client.client.get_me()
                            if me and me.id == sender_id:
                                granter_user = await db_manager.get_user_by_id(
                                    user_info["user_id"]
                                )
                                break
                    except Exception as check_error:
                        logger.debug(
                            f"Error checking user {user_info['user_id']}: {check_error}"
                        )
                        continue

            if not granter_user:
                # User is not registered in our system, but we allow them to grant power
                # We'll skip the session checks since they're not in our system
                logger.info(
                    f"Unregistered Telegram user (ID: {sender_id}) attempting to grant power"
                )
            else:
                # Check if the granting user does NOT have an active session (profile not locked)
                granter_has_active_session = (
                    await db_manager.has_active_telegram_session(granter_user["id"])
                )

                if granter_has_active_session:
                    logger.warning(
                        f"🚫 GRANT DENIED | Granter: {granter_user['username']} (ID: {granter_user['id']}) | "
                        f"Reason: Profile locked (has active session)"
                    )
                    return

            # Parse the command: /grant @username amount
            parts = message_text.strip().split()
            if len(parts) != 3:
                logger.warning(
                    f"🚫 GRANT DENIED | Invalid format from Telegram ID {sender_id}: {message_text}"
                )
                return

            username_arg = parts[1]
            amount_arg = parts[2]

            # Validate username format (should start with @)
            if not username_arg.startswith("@"):
                logger.warning(
                    f"🚫 GRANT DENIED | Invalid username format from Telegram ID {sender_id}: {username_arg}"
                )
                return

            # Extract username without @
            target_username = username_arg[1:]

            # Validate amount
            try:
                amount = int(amount_arg)
                if amount <= 0:
                    logger.warning(
                        f"🚫 GRANT DENIED | Invalid amount from Telegram ID {sender_id}: {amount_arg} (must be positive)"
                    )
                    return
            except ValueError:
                logger.warning(
                    f"🚫 GRANT DENIED | Invalid amount from Telegram ID {sender_id}: {amount_arg} (not a number)"
                )
                return

            # Find the target user by trying multiple approaches
            target_user = None

            # Approach 1: Try to find by website username (fallback for compatibility)
            target_user = await db_manager.get_user_by_username(target_username)

            # Approach 2: If not found, try to resolve via Telegram and match with active users
            if not target_user:
                try:
                    # Use the Telegram client to resolve the username to get user info
                    target_entity = await self.client_instance.client.get_entity(
                        target_username
                    )
                    target_telegram_id = target_entity.id
                    target_first_name = getattr(target_entity, "first_name", "")
                    target_last_name = getattr(target_entity, "last_name", "")

                    logger.info(
                        f"Resolved @{target_username} to Telegram ID {target_telegram_id} ({target_first_name} {target_last_name})"
                    )

                    # Now we need to find which of our system users corresponds to this Telegram user
                    # We'll check active Telegram sessions to see if any user has this Telegram account
                    from ..telegram_client import get_telegram_manager

                    telegram_manager = get_telegram_manager()

                    if telegram_manager:
                        connected_users = await telegram_manager.get_connected_users()
                        for user_info in connected_users:
                            try:
                                # Get the client for this user and check their Telegram ID
                                user_client = await telegram_manager.get_client(
                                    user_info["user_id"]
                                )
                                if user_client and user_client.client:
                                    me = await user_client.client.get_me()
                                    if me and me.id == target_telegram_id:
                                        # Found a match! This system user corresponds to the target Telegram user
                                        target_user = await db_manager.get_user_by_id(
                                            user_info["user_id"]
                                        )
                                        logger.info(
                                            f"Found system user {target_user['username']} (ID: {target_user['id']}) for Telegram @{target_username}"
                                        )
                                        break
                            except Exception as check_error:
                                logger.debug(
                                    f"Error checking user {user_info['user_id']}: {check_error}"
                                )
                                continue

                    # If still not found, the user doesn't have an account in our system
                    if not target_user:
                        logger.warning(
                            f"🚫 GRANT DENIED | Target @{target_username} found on Telegram but not registered in system"
                        )
                        return

                except Exception as telegram_error:
                    logger.warning(
                        f"🚫 GRANT DENIED | Failed to resolve Telegram username @{target_username}: {telegram_error}"
                    )
                    return

            # Check if the recipient HAS an active session (profile locked/restricted)
            recipient_has_active_session = await db_manager.has_active_telegram_session(
                target_user["id"]
            )

            if not recipient_has_active_session:
                granter_info = (
                    f"{granter_user['username']} (ID: {granter_user['id']})"
                    if granter_user
                    else f"Unregistered (Telegram ID: {sender_id})"
                )
                logger.warning(
                    f"🚫 GRANT DENIED | Granter: {granter_info} | "
                    f"Recipient: @{target_username} (ID: {target_user['id']}) | "
                    f"Reason: Recipient has no active session (profile not locked)"
                )
                return

            # Grant the energy to the target user
            grant_result = await db_manager.add_user_energy(target_user["id"], amount)

            if grant_result["success"]:
                # Calculate how much was actually added (might be capped by max energy)
                actual_amount = grant_result["added"]
                new_energy = grant_result["energy"]
                max_energy = grant_result["max_energy"]

                response_msg = "⚡ Power Granted! ⚡\n\n"

                chat_entity = event.message.peer_id
                await self.client_instance.client.send_message(
                    chat_entity, response_msg
                )

                granter_info = (
                    f"{granter_user['username']} (ID: {granter_user['id']})"
                    if granter_user
                    else f"Unregistered (Telegram ID: {sender_id})"
                )

                logger.info(
                    f"⚡ POWER GRANTED | Granter: {granter_info} | "
                    f"Recipient: @{target_username} (ID: {target_user['id']}) | "
                    f"Amount: {actual_amount} | New Power: {new_energy}/{max_energy}"
                )
            else:
                granter_info = (
                    f"{granter_user['username']} (ID: {granter_user['id']})"
                    if granter_user
                    else f"Unregistered (Telegram ID: {sender_id})"
                )

                logger.error(
                    f"❌ GRANT FAILED | Granter: {granter_info} | "
                    f"Target: @{target_username} | Error: {grant_result.get('error', 'Unknown error')}"
                )

        except Exception as e:
            logger.error(
                f"Error handling grant command for user {self.client_instance.user_id}: {e}"
            )

            try:
                response_msg = "❌ An error occurred while processing the grant command. Please try again later."
                chat_entity = event.message.peer_id
                await self.client_instance.client.send_message(
                    chat_entity, response_msg
                )
            except Exception as send_error:
                logger.error(f"Error sending error message: {send_error}")

    async def _process_badwords(
        self, event, message_text: str, db_manager
    ) -> Optional[Dict[str, Any]]:
        """Process badwords filtering for a message."""
        filter_result = await db_manager.filter_badwords_from_message(
            self.client_instance.user_id, message_text
        )

        # If badwords found, handle them
        if filter_result["has_violations"]:
            # Edit the message with filtered version instead of deleting and sending new
            try:
                await event.message.edit(filter_result["filtered_message"])
                return filter_result
            except Exception as e:
                logger.error(
                    f"Error editing badwords message for user {self.client_instance.user_id}: {e}"
                )
                # Still return the filter result for penalty application
                return filter_result

        return None

    async def _process_autocorrect(
        self, event, message_text: str, db_manager
    ) -> Optional[Dict[str, Any]]:
        """Process autocorrect for a message."""
        # Check autocorrect settings and apply if enabled
        autocorrect_settings = await db_manager.get_autocorrect_settings(
            self.client_instance.user_id
        )
        if not autocorrect_settings["enabled"] or not message_text:
            return None

        try:
            from ..autocorrect import get_autocorrect_manager

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

                # Edit the message with corrected text instead of deleting and sending new
                try:
                    await event.message.edit(corrected_text)

                    # Apply penalty
                    await db_manager.consume_user_energy(
                        self.client_instance.user_id, penalty
                    )

                    # Log the autocorrection
                    await db_manager.log_autocorrect_usage(
                        self.client_instance.user_id,
                        message_text,
                        corrected_text,
                        autocorrect_result["count"],
                    )

                    logger.info(
                        f"📝 AUTOCORRECT | User: {self.client_instance.username} (ID: {self.client_instance.user_id}) | "
                        f"Corrections: {autocorrect_result['count']} | Penalty: {penalty}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error applying autocorrect for user {self.client_instance.user_id}: {e}"
                    )

            return autocorrect_result

        except Exception as e:
            logger.error(
                f"Error in autocorrect processing for user {self.client_instance.user_id}: {e}"
            )
            return None

    async def _apply_badword_penalties(self, filter_result: Dict[str, Any], event):
        """Apply energy penalties for badword violations."""
        try:
            from ..database import get_database_manager

            db_manager = get_database_manager()

            violations = filter_result["violations"]
            total_penalty = filter_result["total_penalty"]
            violated_words = [violation["word"] for violation in violations]

            # Apply energy penalty
            penalty_result = await db_manager.consume_user_energy(
                self.client_instance.user_id, total_penalty
            )

            # Get max energy for proper logging
            energy_info = await db_manager.get_user_energy(self.client_instance.user_id)
            max_energy = energy_info["max_energy"]

            # Check if energy went to 0 or below after penalty
            current_energy = penalty_result.get("energy", 0)
            if current_energy <= 0:
                # Replace the already filtered message with a low energy message
                try:
                    await self._replace_with_low_energy_message(event)
                    logger.info(
                        f"🔋 LOW ENERGY REPLACEMENT | User: {self.client_instance.username} "
                        f"(ID: {self.client_instance.user_id}) | Energy after badword penalty: {current_energy}/{max_energy}"
                    )
                except Exception as replacement_error:
                    logger.error(
                        f"Error replacing badword message with low energy message for user {self.client_instance.user_id}: {replacement_error}"
                    )

            # Log the violation
            violation_log = f"Badwords detected: {', '.join(violated_words)} | Total penalty: {total_penalty}"
            violation_log += (
                f" | Energy: {penalty_result['energy']}/{max_energy} (-{total_penalty})"
            )

            logger.warning(
                f"🚫 BADWORD VIOLATION | User: {self.client_instance.username} (ID: {self.client_instance.user_id}) | "
                f"{violation_log} | Badwords replaced with <redacted>"
            )

        except Exception as e:
            logger.error(
                f"Error applying badword penalties for user {self.client_instance.user_id}: {e}"
            )

    async def _replace_with_low_energy_message(self, event):
        """Replace the original message with a low energy roleplay message."""
        try:
            from ..roleplay_messages import get_random_low_energy_message

            # Get a random low energy message
            low_energy_msg = get_random_low_energy_message()

            # For low energy, we always delete and send new message because:
            # 1. The original might be media (sticker, photo, etc.) which can't be edited to text
            # 2. We want to replace any type of content with a text response
            try:
                # Use the message's peer_id for more reliable entity resolution
                chat_entity = event.message.peer_id

                await self.client_instance.client.delete_messages(
                    chat_entity, event.message.id
                )
                await self.client_instance.client.send_message(
                    chat_entity, f"*{low_energy_msg}*"
                )

                logger.info(
                    f"🔋 LOW ENERGY REPLACEMENT | User: {self.client_instance.username} (ID: {self.client_instance.user_id}) | "
                    f"Original deleted, sent: {low_energy_msg[:50]}..."
                )
            except Exception as e:
                logger.error(
                    f"Error with delete+send for low energy message (user {self.client_instance.user_id}): {e}"
                )
                # Fallback: try to edit if it was a text message
                try:
                    await event.message.edit(f"*{low_energy_msg}*")
                    logger.info(
                        f"🔋 LOW ENERGY FALLBACK EDIT | User: {self.client_instance.username} (ID: {self.client_instance.user_id}) | "
                        f"Message edited to: {low_energy_msg[:50]}..."
                    )
                except Exception as edit_error:
                    logger.error(
                        f"Error with fallback edit for low energy message (user {self.client_instance.user_id}): {edit_error}"
                    )

        except Exception as e:
            logger.error(
                f"Error replacing message with low energy version for user {self.client_instance.user_id}: {e}"
            )

    async def _log_message_details(
        self, event, message_text: str, special_message_type: Optional[str]
    ):
        """Log message details for monitoring."""
        try:
            # Log message details (content excluded for privacy)
            logger.info(
                f"📤 MESSAGE SENT | User: {self.client_instance.username} (ID: {self.client_instance.user_id}) | "
                f"Length: {len(message_text)} chars | "
                f"Special: {special_message_type or 'None'} | "
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )

        except Exception as e:
            logger.error(
                f"Error logging message details for user {self.client_instance.user_id}: {e}"
            )

    def _get_message_type(self, message) -> str:
        """Determine the message type for energy cost calculation."""
        if not message:
            return "text"

        # Check for different media types based on Telethon message attributes
        if hasattr(message, "media") and message.media:
            return self._parse_media_type(message)

        # Check for grouped media (media group/album)
        if hasattr(message, "grouped_id") and message.grouped_id:
            return "media_group"

        # Default to text message
        return "text"

    def _parse_media_type(self, message) -> str:
        """Parse media type from message."""
        media_type = type(message.media).__name__

        if "Photo" in media_type:
            return "photo"
        elif "Document" in media_type:
            return self._parse_document_type(message)
        elif "Game" in media_type:
            return "game"
        elif "Poll" in media_type:
            return "poll"
        elif "Contact" in media_type:
            return "location"
        elif "GeoPoint" in media_type or "Geo" in media_type:
            return "location"
        elif "Venue" in media_type:
            return "venue"
        elif "WebPage" in media_type:
            return "web_page"
        elif "MessageMediaDocument" in media_type:
            return self._parse_document_type(message)

        return "document"

    def _parse_document_type(self, message) -> str:
        """Parse document-specific media types."""
        if not hasattr(message.media, "document"):
            return "document"

        doc = message.media.document

        # Check for stickers first (they are documents with sticker attributes)
        if hasattr(doc, "attributes"):
            for attr in doc.attributes:
                attr_name = type(attr).__name__
                if "DocumentAttributeSticker" in attr_name or "Sticker" in attr_name:
                    return "sticker"

        if not hasattr(doc, "mime_type"):
            return "document"

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

        return "document"

    def _is_special_message(self, message_text: str) -> Optional[str]:
        """Identify if a message is a special message by its content. Returns message type or None."""
        if not message_text:
            return None

        # Import here to avoid circular imports
        from ..roleplay_messages import (
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

        # Check against different message types
        message_sets = [
            (LOW_ENERGY_MESSAGES, "low_energy"),
            (FLIP_MESSAGES, "flip"),
            (BEEP_MESSAGES, "beep"),
            (DANCE_MESSAGES, "dance"),
        ]

        for message_set, message_type in message_sets:
            for special_msg in message_set:
                if clean_text_no_asterisks == special_msg.strip("*").strip():
                    return message_type

        return None

    def _is_ooc_message(self, message_text: str) -> bool:
        """Check if a message is an OOC (Out of Character) message that should bypass all filtering."""
        if not message_text:
            return False

        # Check if message starts with "ooc:" (case insensitive)
        return message_text.strip().lower().startswith("ooc:")
