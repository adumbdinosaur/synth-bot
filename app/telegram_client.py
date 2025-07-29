import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Set
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, AuthKeyDuplicatedError
import weakref
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class TelegramUserBot:
    """Individual Telegram userbot instance for a single user."""
    
    def __init__(self, api_id: int, api_hash: str, phone_number: str, user_id: int, username: str):
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
        self._auth_state = "none"  # none, code_sent, code_verified, requires_2fa, authenticated
        
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
                        logger.warning(f"Removed corrupted session file for user {self.user_id}")
                    except:
                        pass
            
            # Create client with unique session
            self.client = TelegramClient(
                self.session_name, 
                self.api_id, 
                self.api_hash,
                device_model=f"UserBot-{self.username}",
                app_version="1.0.0",
                system_version="Linux"
            )
            
            await self.client.connect()
            logger.info(f"Telegram client connected for user {self.user_id}")
            
            # Check if already signed in
            if await self.client.is_user_authorized():
                logger.info(f"User {self.user_id} ({self.username}) already authorized")
                self._auth_state = "authenticated"
                return {"success": True, "already_authorized": True}
            
            # Send code request with detailed logging
            logger.info(f"Attempting to send verification code to {self.phone_number} for user {self.user_id} ({self.username})")
            try:
                sent_code = await self.client.send_code_request(self.phone_number)
                logger.info(f"Telegram API response for code request: {sent_code}")
                
                # Extract information about how the code was sent
                code_type = sent_code.type
                delivery_method = "unknown"
                if hasattr(code_type, '__class__'):
                    type_name = code_type.__class__.__name__
                    if type_name == "SentCodeTypeApp":
                        delivery_method = "telegram_app"
                        logger.info(f"Code sent via Telegram app for {self.phone_number}")
                    elif type_name == "SentCodeTypeSms":
                        delivery_method = "sms"
                        logger.info(f"Code sent via SMS for {self.phone_number}")
                    elif type_name == "SentCodeTypeCall":
                        delivery_method = "phone_call"
                        logger.info(f"Code sent via phone call for {self.phone_number}")
                    else:
                        delivery_method = type_name.lower()
                        logger.info(f"Code sent via {type_name} for {self.phone_number}")
                
                logger.info(f"Code request successful for {self.phone_number} - user {self.user_id} ({self.username})")
                self._auth_state = "code_sent"
                return {
                    "success": True, 
                    "delivery_method": delivery_method,
                    "code_length": getattr(code_type, 'length', 5)
                }
            except Exception as code_error:
                logger.error(f"Error during code request for {self.phone_number}: {code_error}")
                raise
            
        except AuthKeyDuplicatedError:
            logger.warning(f"Auth key duplicated for user {self.user_id}, creating new session")
            # Remove existing session and try again
            try:
                os.remove(f"{self.session_name}.session")
            except FileNotFoundError:
                pass
            return await self.send_code_request()
        except Exception as e:
            logger.error(f"Failed to send code request for user {self.user_id} ({self.username}): {e}")
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
                return {"success": False, "error": "No client available", "requires_2fa": False}
            
            try:
                # Try to sign in with just the code
                await self.client.sign_in(self.phone_number, code)
                logger.info(f"Successfully signed in user {self.user_id} ({self.username}) - no 2FA required")
                self._auth_state = "authenticated"
                return {"success": True, "requires_2fa": False}
                
            except SessionPasswordNeededError:
                # 2FA is enabled, password is required - this is actually partial success
                logger.info(f"Code verified for user {self.user_id} ({self.username}) - 2FA password required")
                self._auth_state = "requires_2fa"
                return {"success": True, "requires_2fa": True, "code_verified": True}
                
            except PhoneCodeInvalidError:
                logger.warning(f"Invalid phone code for user {self.user_id} ({self.username})")
                return {"success": False, "error": "Invalid verification code", "requires_2fa": False}
                
        except Exception as e:
            logger.error(f"Code verification failed for user {self.user_id} ({self.username}): {e}")
            return {"success": False, "error": str(e), "requires_2fa": False}
    
    async def verify_2fa_password(self, password: str) -> bool:
        """Verify 2FA password after code verification."""
        try:
            if not self.client:
                logger.error(f"No client available for user {self.user_id}")
                return False
            
            await self.client.sign_in(password=password)
            logger.info(f"Successfully signed in user {self.user_id} ({self.username}) with 2FA")
            self._auth_state = "authenticated"
            return True
                
        except Exception as e:
            logger.error(f"2FA verification failed for user {self.user_id} ({self.username}): {e}")
            return False
    
    async def start_message_listener(self) -> bool:
        """Start listening for outgoing messages in a background task."""
        if not self.client or not await self.client.is_user_authorized():
            logger.error(f"Client not authorized for user {self.user_id} ({self.username})")
            return False
        
        if self._is_running:
            logger.warning(f"Message listener already running for user {self.user_id} ({self.username})")
            return True
        
        try:
            # Register message handler if not already registered
            if not self._message_handler_registered:
                @self.client.on(events.NewMessage(outgoing=True))
                async def message_handler(event):
                    await self._handle_outgoing_message(event)
                
                self._message_handler_registered = True
                logger.info(f"Message handler registered for user {self.user_id} ({self.username})")
            
            # Start the listener task
            self._listener_task = asyncio.create_task(self._run_listener())
            self._is_running = True
            logger.info(f"Started message listener for user {self.user_id} ({self.username})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start message listener for user {self.user_id} ({self.username}): {e}")
            return False
    
    async def _handle_outgoing_message(self, event):
        """Handle outgoing message event."""
        try:
            # Get chat information
            chat = await event.get_chat()
            chat_title = getattr(chat, 'title', getattr(chat, 'first_name', 'Unknown'))
            chat_type = 'channel' if hasattr(chat, 'broadcast') and chat.broadcast else \
                       'group' if hasattr(chat, 'megagroup') and chat.megagroup else \
                       'private'
            
            message_text = event.message.text or "[Media/Sticker/File]"
            
            # Log to console instead of database as requested
            logger.info(
                f"📤 MESSAGE SENT | User: {self.username} (ID: {self.user_id}) | "
                f"Chat: {chat_title} ({chat_type}) | "
                f"Content: {message_text[:100]}{'...' if len(message_text) > 100 else ''} | "
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
        except Exception as e:
            logger.error(f"Error handling message for user {self.user_id} ({self.username}): {e}")
    
    async def _run_listener(self):
        """Run the message listener loop."""
        try:
            logger.info(f"Message listener started for user {self.user_id} ({self.username})")
            await self.client.run_until_disconnected()
        except asyncio.CancelledError:
            logger.info(f"Message listener cancelled for user {self.user_id} ({self.username})")
        except Exception as e:
            logger.error(f"Message listener error for user {self.user_id} ({self.username}): {e}")
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
        logger.info(f"Stopped message listener for user {self.user_id} ({self.username})")
    
    async def disconnect(self):
        """Disconnect the Telegram client."""
        await self.stop_listener()
        
        if self.client:
            try:
                if self.client.is_connected():
                    await self.client.disconnect()
                logger.info(f"Disconnected Telegram client for user {self.user_id} ({self.username})")
            except Exception as e:
                logger.error(f"Error disconnecting client for user {self.user_id} ({self.username}): {e}")
            finally:
                self.client = None
    
    async def get_me(self):
        """Get current user information."""
        if not self.client or not await self.client.is_user_authorized():
            return None
        
        try:
            return await self.client.get_me()
        except Exception as e:
            logger.error(f"Failed to get user info for {self.user_id} ({self.username}): {e}")
            return None
    
    @property
    def is_connected(self) -> bool:
        """Check if the client is connected and authorized."""
        return (self.client is not None and 
                self.client.is_connected() and 
                self._is_running)
    
    def get_auth_state(self) -> str:
        """Get current authentication state."""
        return self._auth_state
    
    async def is_fully_authenticated(self) -> bool:
        """Check if user is fully authenticated and ready to use."""
        return (self._auth_state == "authenticated" and 
                self.client and 
                await self.client.is_user_authorized())
    
    async def restore_from_session(self) -> bool:
        """Restore client from existing session file without sending new code."""
        try:
            # Check if session file exists
            session_file = f"{self.session_name}.session"
            if not os.path.exists(session_file):
                logger.warning(f"No session file found for user {self.user_id}: {session_file}")
                return False
            
            # Create client with existing session
            self.client = TelegramClient(
                self.session_name, 
                self.api_id, 
                self.api_hash,
                device_model=f"UserBot-{self.username}",
                app_version="1.0.0",
                system_version="Linux"
            )
            
            await self.client.connect()
            logger.info(f"Telegram client connected for user {self.user_id} using existing session")
            
            # Check if already signed in
            if await self.client.is_user_authorized():
                logger.info(f"User {self.user_id} ({self.username}) restored from session - already authorized")
                self._auth_state = "authenticated"
                return True
            else:
                logger.warning(f"Session file exists but user {self.user_id} is not authorized")
                await self.client.disconnect()
                self.client = None
                return False
                
        except Exception as e:
            logger.error(f"Failed to restore session for user {self.user_id} ({self.username}): {e}")
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            return False

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
    
    async def get_or_create_client(self, user_id: int, username: str, phone_number: str) -> TelegramUserBot:
        """Get existing client or create new one for user."""
        async with self._lock:
            if user_id not in self.clients:
                client = TelegramUserBot(
                    self.api_id, 
                    self.api_hash, 
                    phone_number, 
                    user_id, 
                    username
                )
                self.clients[user_id] = client
                logger.info(f"Created new Telegram client for user {user_id} ({username})")
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
                    logger.error(f"Failed to remove session file for user {user_id}: {e}")
                
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
            {"user_id": user_id, "username": client.username, "phone": client.phone_number}
            for user_id, client in self.clients.items()
            if client.is_connected
        ]
    
    async def recover_clients_from_sessions(self, db):
        """Recover clients from existing session files on startup."""
        logger.info("🔄 Starting client recovery from session files...")
        
        sessions_dir = "sessions"
        if not os.path.exists(sessions_dir):
            logger.info("No sessions directory found, skipping recovery")
            return
        
        # Get all session files
        session_files = [f for f in os.listdir(sessions_dir) if f.endswith('.session')]
        logger.info(f"Found {len(session_files)} session files to process")
        
        recovered_count = 0
        
        for session_file in session_files:
            try:
                # Parse session filename to extract user_id and phone
                # Format: user_{user_id}_{phone}.session
                base_name = session_file.replace('.session', '')
                if not base_name.startswith('user_'):
                    continue
                
                parts = base_name.split('_')
                if len(parts) < 3:
                    continue
                
                user_id = int(parts[1])
                phone_number = '+' + parts[2]  # Add back the + prefix
                
                logger.info(f"Attempting to recover session for user {user_id}, phone {phone_number}")
                
                # Get user details from database
                try:
                    cursor = await db.execute(
                        "SELECT username, telegram_connected FROM users WHERE id = ?", 
                        (user_id,)
                    )
                    user_row = await cursor.fetchone()
                except Exception as db_error:
                    logger.error(f"Database error while checking user {user_id}: {db_error}")
                    continue
                
                if not user_row:
                    logger.warning(f"User {user_id} not found in database, skipping session recovery")
                    continue
                
                username = user_row[0]
                
                # Create client instance
                client = TelegramUserBot(
                    self.api_id,
                    self.api_hash,
                    phone_number,
                    user_id,
                    username
                )
                
                # Try to restore from session
                if await client.restore_from_session():
                    # Session restored successfully
                    async with self._lock:
                        self.clients[user_id] = client
                    
                    # Start message listener
                    listener_started = await client.start_message_listener()
                    if listener_started:
                        logger.info(f"✅ Successfully recovered and started listener for user {user_id} ({username})")
                        recovered_count += 1
                        
                        # Update database to reflect connection status
                        try:
                            await db.execute(
                                "UPDATE users SET telegram_connected = ?, phone_number = ? WHERE id = ?",
                                (True, phone_number, user_id)
                            )
                        except Exception as db_error:
                            logger.error(f"Database error updating user {user_id} status: {db_error}")
                            # Continue anyway, the client is still recovered
                    else:
                        logger.error(f"❌ Failed to start message listener for recovered user {user_id} ({username})")
                        # Remove from clients if listener failed
                        async with self._lock:
                            if user_id in self.clients:
                                del self.clients[user_id]
                        await client.disconnect()
                else:
                    logger.warning(f"❌ Failed to restore session for user {user_id} ({username})")
                    await client.disconnect()
                    
            except Exception as e:
                logger.error(f"Error recovering session from {session_file}: {e}")
                import traceback
                traceback.print_exc()
        
        if recovered_count > 0:
            try:
                await db.commit()
                logger.info(f"🎉 Successfully recovered {recovered_count} client(s) from session files")
            except Exception as db_error:
                logger.error(f"Database error during commit: {db_error}")
                logger.info(f"🎉 Successfully recovered {recovered_count} client(s) from session files (database commit failed)")
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
