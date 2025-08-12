"""
Utility functions for Telegram command handling.
Contains reusable logic for command authorization and user resolution.
"""

import logging
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)


async def resolve_command_sender(event, telegram_manager, db_manager) -> Optional[Dict[str, Any]]:
    """
    Resolve which system user corresponds to the Telegram sender ID.
    
    Returns:
        dict: User info if found, None otherwise
    """
    sender_id = event.message.sender_id
    
    if not telegram_manager:
        return None
    
    connected_users = await telegram_manager.get_connected_users()
    for user_info in connected_users:
        try:
            user_client = await telegram_manager.get_client(user_info["user_id"])
            if user_client and user_client.client:
                me = await user_client.client.get_me()
                if me and me.id == sender_id:
                    return await db_manager.get_user_by_id(user_info["user_id"])
        except Exception as check_error:
            logger.debug(f"Error checking user {user_info['user_id']}: {check_error}")
            continue
    
    return None


async def resolve_target_user(username: str, client_instance, telegram_manager, db_manager) -> Optional[Dict[str, Any]]:
    """
    Resolve a target username to a system user.
    Tries multiple approaches: website username lookup, then Telegram resolution.
    
    Args:
        username: Username without @ prefix
        client_instance: Telegram client instance
        telegram_manager: Telegram manager
        db_manager: Database manager
        
    Returns:
        dict: User info if found, None otherwise
    """
    # Approach 1: Try to find by website username (fallback for compatibility)
    target_user = await db_manager.get_user_by_username(username)
    
    # Approach 2: If not found, try to resolve via Telegram and match with active users
    if not target_user:
        try:
            # Use the Telegram client to resolve the username to get user info
            target_entity = await client_instance.client.get_entity(username)
            target_telegram_id = target_entity.id
            target_first_name = getattr(target_entity, "first_name", "")
            target_last_name = getattr(target_entity, "last_name", "")

            logger.info(
                f"Resolved @{username} to Telegram ID {target_telegram_id} ({target_first_name} {target_last_name})"
            )

            # Now we need to find which of our system users corresponds to this Telegram user
            if telegram_manager:
                connected_users = await telegram_manager.get_connected_users()
                for user_info in connected_users:
                    try:
                        # Get the client for this user and check their Telegram ID
                        user_client = await telegram_manager.get_client(user_info["user_id"])
                        if user_client and user_client.client:
                            me = await user_client.client.get_me()
                            if me and me.id == target_telegram_id:
                                # Found a match! This system user corresponds to the target Telegram user
                                target_user = await db_manager.get_user_by_id(user_info["user_id"])
                                logger.info(
                                    f"Found system user {target_user['username']} (ID: {target_user['id']}) for Telegram @{username}"
                                )
                                break
                    except Exception as check_error:
                        logger.debug(f"Error checking user {user_info['user_id']}: {check_error}")
                        continue

        except Exception as telegram_error:
            logger.warning(f"Failed to resolve Telegram username @{username}: {telegram_error}")
            
    return target_user


async def check_command_authorization(sender_user: Optional[Dict[str, Any]], target_user: Dict[str, Any], db_manager, command_name: str = "COMMAND") -> Tuple[bool, str]:
    """
    Check if the sender is authorized to execute a command on the target user.
    
    For grant command:
    - Sender must NOT have an active session (unlocked profile)
    - Target must HAVE an active session (locked profile)
    
    For admin override command:
    - Sender must NOT have an active session (unlocked profile) 
    - Target must HAVE an active session (locked profile)
    
    Args:
        sender_user: The user sending the command (None if unregistered)
        target_user: The target user for the command
        db_manager: Database manager
        command_name: Name of the command for logging
        
    Returns:
        tuple: (is_authorized: bool, reason: str)
    """
    # Check sender authorization
    if sender_user:
        # Check if the sender does NOT have an active session (profile not locked)
        sender_has_active_session = await db_manager.has_active_telegram_session(sender_user["id"])
        
        if sender_has_active_session:
            sender_info = f"{sender_user['username']} (ID: {sender_user['id']})"
            reason = f"🚫 {command_name} DENIED | Sender: {sender_info} | Reason: Profile locked (has active session)"
            return False, reason
    
    # Check target authorization - target MUST have an active session (profile locked/restricted)
    target_has_active_session = await db_manager.has_active_telegram_session(target_user["id"])
    
    if not target_has_active_session:
        sender_info = (
            f"{sender_user['username']} (ID: {sender_user['id']})"
            if sender_user
            else "Unregistered user"
        )
        reason = (
            f"🚫 {command_name} DENIED | Sender: {sender_info} | "
            f"Target: @{target_user.get('username', 'unknown')} (ID: {target_user['id']}) | "
            f"Reason: Target has no active session (profile not locked)"
        )
        return False, reason
    
    return True, "Authorized"


async def should_process_command_for_target(client_instance, target_username: str, command_name: str = "COMMAND") -> bool:
    try:
        if not client_instance.client:
            logger.debug(f"No client available for username comparison in {command_name}")
            return False

        # Get the current user's Telegram information
        me = await client_instance.client.get_me()
        if not me or not me.username:
            logger.debug(
                f"No Telegram username available for user {client_instance.user_id} in {command_name}"
            )
            return False

        current_telegram_username = me.username
        should_process = current_telegram_username.lower() == target_username.lower()
        
        logger.info(
            f"{command_name}: target='{target_username}', current_telegram='{current_telegram_username}', should_process={should_process}"
        )

        if not should_process:
            # This session is not the target, ignore the command
            logger.debug(
                f"{command_name} for @{target_username} ignored by Telegram session @{current_telegram_username}"
            )

        return should_process

    except Exception as username_error:
        logger.error(
            f"Error getting Telegram username for comparison in {command_name}: {username_error}"
        )
        return False
