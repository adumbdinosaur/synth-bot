# Admin Override Command Feature

This feature allows non-locked users to make specified locked users send messages or perform actions via a slash command.

## Overview

The admin override command provides a way for authorized users (typically administrators or controllers) to send messages on behalf of locked users in the system. This is useful for administrative purposes, demonstrations, or emergency situations.

## Command Syntax

```
/admin @username say "message"
```

### Parameters

- `@username` - The target user who will send the message (must be a locked user)
- `"message"` - The message to send (must be enclosed in double quotes)

### Examples

```bash
/admin @alice say "Hello everyone!"
/admin @bob123 say "This is a test message from the admin override system."
/admin @user say "Simple message."
```

## Authorization Requirements

For the command to execute successfully, the following conditions must be met:

### Sender (Admin) Requirements
1. **Unlocked Profile**: The admin must NOT have an active Telegram session (unlocked profile)
2. **Valid Format**: The command must follow the exact syntax pattern
3. **System Access**: The admin can be either registered in the system or unregistered

### Target User Requirements
1. **Locked Profile**: The target user MUST have an active Telegram session (locked profile)
2. **Active Connection**: The target user must have an active Telegram client connection
3. **System Registration**: The target user must be registered in the system
4. **Username Resolution**: The target username must be resolvable either via system username or Telegram username

## Technical Implementation

### Command Processing Flow

1. **Parse Command**: Extract username and message using regex pattern
2. **Resolve Users**: Find both sender and target users in the system
3. **Check Authorization**: Verify sender and target meet requirements
4. **Get Target Client**: Obtain the target user's Telegram client
5. **Send Message**: Execute the message send on behalf of target user
6. **Log Activity**: Record the admin override action
7. **Send Confirmation**: Optionally confirm execution to admin

### Code Components

- **Message Handler**: `app/telegram/message_handler.py` - Main command handler
- **Command Utils**: `app/telegram/command_utils.py` - Reusable authorization logic
- **Authorization Logic**: Extracted from grant command for consistency

### Regex Pattern

```python
pattern = r'^/admin\s+@(\w+)\s+say\s+"([^"]*)"$'
```

This pattern:
- Matches `/admin` command (case insensitive)
- Requires `@username` format (alphanumeric + underscore)
- Requires `say` action word
- Requires double-quoted message (can be empty)
- Allows flexible whitespace

## Security Considerations

### Access Control
- Only unlocked users can execute admin overrides
- Target users must be locked (have active sessions)
- System validates both sender and target authorization

### Logging
- All admin override attempts are logged
- Successful executions include admin info, target info, and message content
- Failed attempts include detailed failure reasons

### Message Validation
- Messages must be properly quoted
- No message content validation beyond format
- Target user's existing filters (badwords, etc.) may still apply

## Error Scenarios

### Command Format Errors
- Invalid syntax (missing quotes, wrong action word, etc.)
- Missing username or @ symbol
- Malformed regex pattern

### Authorization Errors
- Admin has locked profile (active session)
- Target has unlocked profile (no active session)
- Target user not found in system
- Target user has no active Telegram connection

### Execution Errors
- Telegram API errors when sending message
- Network connectivity issues
- Target client disconnection during execution

## Usage Examples

### Successful Command
```
Admin: /admin @alice say "Please respond to the support ticket."
System: ✅ Admin override executed. @alice sent: "Please respond to the support ticket."
Alice's account: Please respond to the Support ticket.
```

### Authorization Error
```
Admin (with locked profile): /admin @alice say "Hello"
System: 🚫 ADMIN OVERRIDE DENIED | Reason: Profile locked (has active session)
```

### Format Error
```
Admin: /admin alice say Hello without quotes
System: 🚫 ADMIN OVERRIDE DENIED | Invalid format
Expected format: /admin @username say "message"
```

## Future Enhancements

Potential improvements for the admin override system:

1. **Additional Actions**: Support for other actions beyond `say`
2. **Bulk Operations**: Send messages to multiple users at once
3. **Scheduled Messages**: Delay message sending until specific time
4. **Message Templates**: Pre-defined message templates for common scenarios
5. **Permission Levels**: Different admin levels with different capabilities
6. **Audit Trail**: Enhanced logging and audit capabilities
7. **Web Interface**: GUI for managing admin overrides

## Testing

The feature includes comprehensive tests in `test_admin_override.py`:

- Command parsing regex validation
- Format validation examples
- Authorization logic testing
- Edge case handling

Run tests with:
```bash
python3 test_admin_override.py
```

## Integration

The admin override command integrates with existing systems:

- **Grant Command**: Shares authorization logic via `command_utils.py`
- **Message Handler**: Uses same event handling pattern
- **Database Manager**: Uses existing user resolution methods
- **Telegram Manager**: Uses existing client management
- **Logging System**: Uses consistent logging format and levels
