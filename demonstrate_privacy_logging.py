#!/usr/bin/env python3
"""
Demonstration script showing the privacy-focused logging changes.

This script shows the difference between the old logging (with message content)
and the new logging (without message content for privacy).
"""

import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('demo_logging')

def old_style_logging(username, user_id, chat_title, chat_type, message_text, special_message_type=None):
    """Example of old logging style that exposed message content."""
    logger.info(
        f"📤 MESSAGE SENT | User: {username} (ID: {user_id}) | "
        f"Chat: {chat_title} ({chat_type}) | "
        f"Content: {message_text[:100]}{'...' if len(message_text) > 100 else ''} | "
        f"Special: {special_message_type or 'None'} | "
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

def new_style_logging(username, user_id, chat_title, chat_type, message_text, special_message_type=None):
    """Example of new logging style that protects message content privacy."""
    logger.info(
        f"📤 MESSAGE SENT | User: {username} (ID: {user_id}) | "
        f"Chat: {chat_title} ({chat_type}) | "
        f"Length: {len(message_text)} chars | "
        f"Special: {special_message_type or 'None'} | "
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

if __name__ == "__main__":
    # Example message data
    username = "M1sty"
    user_id = 4
    chat_title = "FVD Horny Jail"
    chat_type = "group"
    message_text = "This is a private message that should not be logged in full!"
    
    print("=== OLD LOGGING STYLE (exposes content) ===")
    old_style_logging(username, user_id, chat_title, chat_type, message_text)
    
    print("\n=== NEW LOGGING STYLE (privacy-focused) ===")
    new_style_logging(username, user_id, chat_title, chat_type, message_text)
    
    print("\n✅ Privacy improvement: Message content is no longer logged!")
    print("📊 We still track message length for analytics purposes.")
    print("🔒 All other metadata (user, chat, timestamp) is preserved.")
