"""
Telegram session database operations.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from .base import BaseDatabaseManager, retry_db_operation

logger = logging.getLogger(__name__)


class SessionManager(BaseDatabaseManager):
    """Handles all Telegram session database operations."""

    @retry_db_operation()
    async def save_telegram_session(self, user_id: int, session_data: str):
        """Save Telegram session data for a user."""
        async with self.get_connection() as db:
            # Check if session already exists
            cursor = await db.execute(
                "SELECT id FROM telegram_sessions WHERE user_id = ?", (user_id,)
            )
            existing_session = await cursor.fetchone()

            if existing_session:
                # Update existing session
                await db.execute(
                    """UPDATE telegram_sessions 
                       SET session_data = ?, updated_at = ? 
                       WHERE user_id = ?""",
                    (session_data, datetime.now().isoformat(), user_id),
                )
            else:
                # Create new session
                await db.execute(
                    """INSERT INTO telegram_sessions (user_id, session_data) 
                       VALUES (?, ?)""",
                    (user_id, session_data),
                )
            await db.commit()

    async def get_telegram_session(self, user_id: int) -> Optional[str]:
        """Get Telegram session data for a user."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                "SELECT session_data FROM telegram_sessions WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    @retry_db_operation()
    async def delete_telegram_session(self, user_id: int):
        """Delete Telegram session data for a user."""
        async with self.get_connection() as db:
            await db.execute(
                "DELETE FROM telegram_sessions WHERE user_id = ?", (user_id,)
            )
            await db.commit()

    async def get_all_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all users with active sessions for the public dashboard."""
        try:
            async with self.get_connection() as db:
                cursor = await db.execute(
                    """SELECT u.id, u.username, u.email, u.energy, u.max_energy, 
                              u.energy_recharge_rate, u.last_energy_update, u.telegram_connected,
                              ts.session_data, ts.updated_at as session_updated_at
                       FROM users u
                       LEFT JOIN telegram_sessions ts ON u.id = ts.user_id
                       WHERE u.telegram_connected = TRUE OR ts.session_data IS NOT NULL
                       ORDER BY u.username"""
                )
                rows = await cursor.fetchall()

                sessions = []
                for row in rows:
                    # Calculate current energy with recharge
                    current_energy = row[3] if row[3] is not None else 100
                    max_energy = row[4] if row[4] is not None else 100
                    recharge_rate = row[5] if row[5] is not None else 1
                    last_update = row[6]

                    if last_update:
                        try:
                            last_update_dt = datetime.fromisoformat(last_update)
                            now = datetime.now()
                            time_diff = (now - last_update_dt).total_seconds()
                            energy_to_add = int(time_diff // 60) * recharge_rate
                            current_energy = min(
                                max_energy, current_energy + energy_to_add
                            )
                        except Exception as e:
                            logger.error(
                                f"Error calculating energy recharge for user {row[0]}: {e}"
                            )

                    sessions.append(
                        {
                            "user_id": row[0],
                            "username": row[1],
                            "email": row[2],
                            "energy": current_energy,
                            "max_energy": max_energy,
                            "energy_percentage": int(
                                (current_energy / max_energy * 100)
                            )
                            if max_energy > 0
                            else 0,
                            "energy_recharge_rate": recharge_rate,
                            "last_energy_update": last_update,
                            "telegram_connected": bool(row[7]),
                            "has_session_data": row[8] is not None,
                            "session_updated_at": row[9],
                            "is_connected": bool(row[7]) and row[8] is not None,
                        }
                    )

                return sessions
        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")
            return []

    async def has_active_telegram_session(self, user_id: int) -> bool:
        """Check if a user has an active Telegram session."""
        try:
            # First check if user is marked as telegram_connected
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "SELECT telegram_connected FROM users WHERE id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()

                if not row or not row[0]:
                    return False

            # Also check real-time state from Telegram manager
            try:
                from app.telegram_client import get_telegram_manager

                telegram_manager = get_telegram_manager()

                if telegram_manager:
                    # Check if user has an active client
                    client = await telegram_manager.get_client(user_id)
                    if client and client.is_connected:
                        return True

                    # Also check connected users list
                    connected_users = await telegram_manager.get_connected_users()
                    user_is_connected = any(
                        user["user_id"] == user_id for user in connected_users
                    )
                    if user_is_connected:
                        return True

            except Exception as telegram_error:
                logger.warning(
                    f"Could not check Telegram manager state for user {user_id}: {telegram_error}"
                )
                # Fall back to database check only
                pass

            # Fallback: check telegram_sessions table
            async with self.get_connection() as db:
                cursor = await db.execute(
                    "SELECT session_data FROM telegram_sessions WHERE user_id = ?",
                    (user_id,),
                )
                session_row = await cursor.fetchone()
                return session_row is not None and session_row[0] is not None

        except Exception as e:
            logger.error(f"Error checking active session for user {user_id}: {e}")
            return False

    @retry_db_operation()
    async def save_telegram_session_with_timer(self, user_id: int, session_data: str, timer_minutes: int = None):
        """Save Telegram session data with optional timer for a user."""
        from datetime import datetime, timedelta
        
        timer_end = None
        if timer_minutes and timer_minutes > 0:
            timer_end = (datetime.now() + timedelta(minutes=timer_minutes)).isoformat()
            
        async with self.get_connection() as db:
            # Check if session already exists
            cursor = await db.execute(
                "SELECT id FROM telegram_sessions WHERE user_id = ?", (user_id,)
            )
            existing_session = await cursor.fetchone()

            if existing_session:
                # Update existing session
                await db.execute(
                    """UPDATE telegram_sessions 
                       SET session_data = ?, updated_at = ?, session_timer_minutes = ?, session_timer_end = ?
                       WHERE user_id = ?""",
                    (session_data, datetime.now().isoformat(), timer_minutes, timer_end, user_id),
                )
            else:
                # Create new session
                await db.execute(
                    """INSERT INTO telegram_sessions (user_id, session_data, session_timer_minutes, session_timer_end) 
                       VALUES (?, ?, ?, ?)""",
                    (user_id, session_data, timer_minutes, timer_end),
                )
            await db.commit()

    async def get_session_timer_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get session timer information for a user."""
        async with self.get_connection() as db:
            cursor = await db.execute(
                """SELECT session_timer_minutes, session_timer_end, created_at 
                   FROM telegram_sessions WHERE user_id = ?""",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row:
                timer_minutes, timer_end, created_at = row
                
                # Calculate remaining time if timer exists
                remaining_seconds = 0
                timer_expired = True
                
                if timer_end:
                    try:
                        end_time = datetime.fromisoformat(timer_end)
                        now = datetime.now()
                        remaining_seconds = max(0, int((end_time - now).total_seconds()))
                        timer_expired = remaining_seconds <= 0
                    except Exception as e:
                        logger.error(f"Error parsing timer end time: {e}")
                
                return {
                    "timer_minutes": timer_minutes,
                    "timer_end": timer_end,
                    "remaining_seconds": remaining_seconds,
                    "timer_expired": timer_expired,
                    "has_timer": timer_minutes is not None and timer_minutes > 0,
                    "created_at": created_at
                }
            return None

    @retry_db_operation()
    async def update_session_timer(self, user_id: int, timer_minutes: int = None):
        """Update session timer for an existing session."""
        from datetime import datetime, timedelta
        
        timer_end = None
        if timer_minutes and timer_minutes > 0:
            timer_end = (datetime.now() + timedelta(minutes=timer_minutes)).isoformat()
            
        async with self.get_connection() as db:
            await db.execute(
                """UPDATE telegram_sessions 
                   SET session_timer_minutes = ?, session_timer_end = ?, updated_at = ?
                   WHERE user_id = ?""",
                (timer_minutes, timer_end, datetime.now().isoformat(), user_id),
            )
            await db.commit()

    @retry_db_operation()
    async def clear_session_timer(self, user_id: int):
        """Clear session timer for a user."""
        async with self.get_connection() as db:
            await db.execute(
                """UPDATE telegram_sessions 
                   SET session_timer_minutes = NULL, session_timer_end = NULL, updated_at = ?
                   WHERE user_id = ?""",
                (datetime.now().isoformat(), user_id),
            )
            await db.commit()
