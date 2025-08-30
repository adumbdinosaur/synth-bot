# Low Energy Message Infinite Loop Bug Fix

## Summary
Fixed a critical bug where custom low power messages could cause themselves to be deleted and then spammed repeatedly, creating an infinite loop.

## Problem Description
The issue occurred in the message handler when a user's energy was low:

1. When energy reached 0, the system would replace the original message with a custom low power message
2. The replacement message was sent using `send_message()`, which triggered the outgoing message handler
3. If the custom low power message itself caused energy consumption or filtering, it could trigger another replacement
4. This created an infinite loop of deletion and re-sending

## Root Cause
The `_replace_with_low_energy_message()` method in `MessageHandler` would:
- Delete the original message
- Send a new message with the low power content
- The new message would be processed by the same outgoing message handler
- If the new message triggered any processing that consumed energy or required filtering, it could cause another low energy replacement

## Solution
Added a flag-based mechanism to prevent infinite loops:

### Changes Made

1. **Added instance variable** in `MessageHandler.__init__()`:
   ```python
   self._low_energy_replacement_in_progress = False
   ```

2. **Modified outgoing message handler** to bypass processing for replacement messages:
   ```python
   async def _handle_outgoing_message(self, event):
       # Skip processing if this is a low energy replacement message
       if self._low_energy_replacement_in_progress:
           self._low_energy_replacement_in_progress = False
           logger.debug(...)
           return
   ```

3. **Updated replacement method** to set the flag before sending:
   ```python
   async def _replace_with_low_energy_message(self, event):
       # ... existing code ...
       # Set flag to prevent infinite loop
       self._low_energy_replacement_in_progress = True
       
       await self.client_instance.client.send_message(
           chat_entity, f"*{low_energy_msg}*"
       )
   ```

4. **Added error handling** to reset the flag on exceptions:
   ```python
   except Exception as e:
       # Reset flag on error
       self._low_energy_replacement_in_progress = False
   ```

## How It Works
1. When a low energy replacement is needed, the flag is set to `True`
2. The replacement message is sent
3. When that message triggers the outgoing handler, it checks the flag
4. If the flag is `True`, processing is bypassed and the flag is reset to `False`
5. This prevents the replacement message from being processed as a regular message

## Testing
Created and ran comprehensive tests to verify:
- ✅ Flag is correctly set before sending replacement message
- ✅ Flag is correctly reset after bypassing replacement message processing
- ✅ Only one replacement message is sent (no infinite loop)
- ✅ Flag is reset even if errors occur during replacement
- ✅ No syntax errors in the updated code

## Files Modified
- `app/telegram/message_handler.py` - Added flag mechanism to prevent infinite loop

## Benefits
1. **Prevents infinite loops** - Custom low power messages can no longer cause themselves to be repeatedly replaced
2. **Maintains functionality** - Low energy replacement still works as intended for legitimate cases
3. **Error resilient** - Flag is properly reset even if errors occur during the replacement process
4. **Minimal impact** - Changes are localized to the message handler and don't affect other functionality

## Backwards Compatibility
This fix is fully backwards compatible. Existing custom power messages will continue to work normally, they just won't cause infinite loops anymore.
