# Autocorrect Message Logging Fix

## Problem
When autocorrect was applied to a message, both the original (deleted) message and the corrected message were being logged, resulting in duplicate/unnecessary logging.

## Root Cause
In `/mnt/projects/new-tg-user-bot/app/telegram/message_handler.py`, the message handling flow was:

1. **Process autocorrect** - Delete original message, send corrected message
2. **Log message details** - Always log the original message, even if it was deleted

This caused the original message to be logged even though it was immediately deleted and replaced.

## Solution
Modified the message handling flow to:

1. **Capture autocorrect result** - Store the return value from `_process_autocorrect()`
2. **Conditionally skip logging** - Skip logging for original messages when autocorrect applied corrections
3. **Let corrected message be logged separately** - The new corrected message will be logged when it's sent

### Code Changes

1. **Initialize autocorrect_result variable** (line ~81):
```python
autocorrect_result = None
```

2. **Capture autocorrect return value** (line ~93):
```python
# Handle autocorrect and capture result
autocorrect_result = await self._process_autocorrect(event, message_text, db_manager)
```

3. **Conditional logging** (line ~130):
```python
# Skip logging if autocorrect was applied (corrections > 0) since the corrected message will be logged separately
should_skip_logging = (
    message_text and 
    autocorrect_result and 
    autocorrect_result.get("count", 0) > 0
)

if not should_skip_logging:
    await self._log_message_details(event, message_text, special_message_type)
```

## Result
- ✅ **Original messages without autocorrect**: Logged normally
- ✅ **Original messages with autocorrect**: Logging skipped (prevents duplicate)
- ✅ **Corrected messages**: Logged when sent (as separate message events)
- ✅ **Autocorrect actions**: Still logged specifically in autocorrect processing

## Files Modified
- `/mnt/projects/new-tg-user-bot/app/telegram/message_handler.py` - Updated message handling flow

The autocorrect system now avoids duplicate message logging while maintaining proper logging for all other message types.
