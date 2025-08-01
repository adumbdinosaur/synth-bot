# Grant Power Command Feature

## Overview

The `/grant` command allows users to grant energy/power to other users through the3. **User Lookup**: Uses a two-tier approach:
   - First tries `UserManager.get_user_by_username()` for website usernames
   - If not found, uses Telegram client to resolve the username, then matches with active users
4. **Energy Grant**: Uses `EnergyManager.add_user_energy()` to grant the energyelegram userbot. This is useful for sharing power with friends or helping users who are running low on energy.

## Command Format

```
/grant @username amount
```

### Parameters

- `@username`: The target user's username (must include the @ symbol)
- `amount`: The amount of energy to grant (must be a positive integer)

### Examples

```
/grant @johndoe 15
/grant @alice123 25
/grant @poweruser 50
```

## Restrictions

1. **Granter Profile Status**: The user granting power must NOT have an active session (their profile must not be locked/restricted). This ensures they are not actively using the userbot features when granting power.

2. **Recipient Profile Status**: The recipient user MUST have an active session (their profile must be locked/restricted). This ensures they are actively using the system and their profile is protected.

## How Username Resolution Works

The `/grant` command supports Telegram usernames and uses a two-tier approach to find users:

1. **Fallback to Website Username**: First tries to find a user by their website username (for backward compatibility)
2. **Telegram Username Resolution**: If not found, resolves the Telegram username to get the user's Telegram ID, then searches for any system user with an active session using that Telegram account

This means:
- Users can be found by their actual Telegram username (@their_telegram_handle)
- The system will correctly identify which registered user corresponds to that Telegram account
- Users must be registered in the system AND have connected their Telegram account to receive grants

3. **Positive Amount**: The amount must be a positive integer greater than 0.

4. **Energy Cap**: If granting the energy would exceed the recipient's maximum energy capacity, only the amount that fits will be granted.

## Usage Flow

1. User types `/grant @targetuser 15` in a Telegram chat
2. System checks if the granting user does NOT have an active session (profile not locked)
   - If yes (has active session): Command is denied with an error message
   - If no (no active session): Continue to next step
3. System validates the command format and parameters
4. System looks up the target user by username
5. System checks if the recipient DOES have an active session (profile locked)
   - If no (no active session): Command is denied with an error message
   - If yes (has active session): Continue to next step
6. System grants the specified energy to the target user
7. System sends a confirmation message with the results

## Response Messages

### Success Messages

**Full Amount Granted:**
```
⚡ Power Granted! ⚡

Successfully granted 15 energy to @johndoe
Their new power level: 65/100
```

**Capped by Max Energy:**
```
⚡ Power Granted! ⚡

Granted 10 energy to @johndoe
(Limited by max capacity: 100/100)
Note: 5 energy was not added due to capacity limit
```

### Error Messages

**Granter Has Active Session:**
```
❌ You cannot grant power while your profile is locked (active session). Please disconnect from the website first.
```

**Recipient Has No Active Session:**
```
❌ Cannot grant power to @johndoe. They must have an active session (profile locked) to receive power grants.
```

**Invalid Format:**
```
❌ Invalid format. Use: /grant @username amount
Example: /grant @johndoe 15
```

**Missing @ Symbol:**
```
❌ Username must start with @
Example: /grant @johndoe 15
```

**Invalid Amount:**
```
❌ Amount must be a valid number
Example: /grant @johndoe 15
```

**Negative Amount:**
```
❌ Amount must be a positive number
Example: /grant @johndoe 15
```

**User Not Found (Not Registered):**
```
❌ Telegram user @johndoe was found but is not registered in our system.
They need to create an account and connect their Telegram to receive power grants.
```

**User Not Found (Doesn't Exist):**
```
❌ Could not find user @johndoe. Please check the username is correct and the user exists.
```

## Technical Implementation

The grant command is implemented in the `MessageHandler` class in `/app/telegram/message_handler.py`. Key components:

1. **Command Detection**: The handler detects messages starting with `/grant `
2. **Granter Session Check**: Uses `SessionManager.has_active_telegram_session()` to verify the granter has no active session (profile not locked)
3. **Parameter Validation**: Validates username format and amount
4. **User Lookup**: Uses a two-tier approach:
   - First tries `UserManager.get_user_by_username()` for website usernames
   - If not found, uses Telegram client to resolve the username, then matches with active users
5. **Recipient Session Check**: Uses `SessionManager.has_active_telegram_session()` to verify the recipient has an active session (profile locked)
6. **Energy Grant**: Uses `EnergyManager.add_user_energy()` to grant the energy
6. **Logging**: All grant attempts are logged with relevant details

## Logging

The system logs all grant attempts with the following information:
- Granter's username and ID
- Recipient's username and ID  
- Amount granted
- Success/failure status
- Error details (if applicable)

Example log entries:
```
⚡ POWER GRANTED | Granter: alice (ID: 123) | Recipient: @bob (ID: 456) | Amount: 15 | New Power: 65/100
🚫 GRANT DENIED | User: charlie (ID: 789) | Reason: Has active session
❌ GRANT FAILED | Granter: dave (ID: 101) | Target: @nonexistent | Error: User not found
```

## Database Operations

The command interacts with several database tables:
- `users`: To check session status and update energy
- `telegram_sessions`: To verify active sessions
- Database operations are wrapped in proper error handling and transactions

## Security Considerations

1. **Session Validation**: Prevents users with active sessions from granting power to prevent exploitation
2. **Input Validation**: All parameters are validated before processing
3. **User Verification**: Target users must exist in the system
4. **Energy Caps**: Energy cannot exceed maximum capacity to maintain game balance
5. **Logging**: All operations are logged for audit purposes
