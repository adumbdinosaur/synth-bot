# Dashboard Authentication & Session Protection

This branch implements enhanced security features for the Telegram UserBot dashboard:

## 🔐 New Authentication Features

### 1. Invite Code Registration
- **Required for new user registration**
- Current invite code: `peterpepperpickedapepper`
- Prevents unauthorized account creation
- Unlimited uses (configurable)

### 2. Dashboard Access Protection
- **Users with active Telegram sessions are blocked from dashboard settings**
- Prevents settings changes while bot is running
- Protects against accidental misconfigurations
- Shows user-friendly blocked page with instructions

### 3. Protected Routes
The following dashboard routes now require session-free access:
- `/dashboard` - Main dashboard
- `/energy-settings` (GET/POST) - Energy cost configuration  
- `/profile-protection` (GET/POST) - Profile protection settings
- `/badwords` (GET/POST) - Badwords management
- `/badwords/add` - Add badwords
- `/badwords/remove` - Remove badwords

## 🚀 How It Works

### Registration Flow
1. User visits `/register`
2. Must enter valid invite code: `peterpepperpickedapepper`
3. Invalid codes are rejected with error message
4. Valid codes allow registration to proceed

### Dashboard Access Flow
1. User logs in normally
2. System checks if user has active Telegram session
3. **If session active**: Shows blocked page with instructions
4. **If no session**: Normal dashboard access granted

### Session Status Detection
- Checks if user has connected Telegram client
- Verifies client is authenticated  
- Real-time detection during each dashboard access

## 📋 User Instructions

### To Access Dashboard Settings:
1. Disconnect your Telegram session from "Active Sessions" page
2. Wait for session to fully disconnect
3. Return to dashboard to access settings
4. Reconnect session when done with configuration

### For New Users:
1. Get invite code from administrator
2. Use code during registration: `peterpepperpickedapepper`
3. Complete normal registration process

## 🛠️ Technical Implementation

### Files Modified:
- `app/auth.py` - Added session checking authentication
- `app/database_manager.py` - Added invite code management & session detection
- `main.py` - Updated routes to use session protection
- `templates/register.html` - Added invite code field
- `templates/dashboard_blocked.html` - New blocked access page

### Database Changes:
- New `invite_codes` table for managing registration codes
- Enhanced session detection capabilities
- Backward compatible with existing users

### Key Functions:
- `get_current_user_with_session_check()` - Enhanced auth with session blocking
- `validate_invite_code()` - Invite code validation  
- `has_active_telegram_session()` - Real-time session detection

## 🔧 Administration

### Managing Invite Codes:
```bash
# Initialize default invite code
python init_invite_code.py

# Add custom invite codes via database or future admin panel
```

### Monitoring:
- Check application logs for session blocking events
- Monitor active sessions via dashboard
- Track invite code usage

## ⚠️ Security Notes

- Invite codes prevent spam registrations
- Session blocking prevents configuration conflicts
- Users can still view public sessions while active
- Telegram connection/disconnection remains available
- Enhanced error handling for better UX

## 🧪 Testing

Run the test suite to verify functionality:
```bash
python test_auth_system.py
```

This validates:
- Invite code validation (valid/invalid)
- User creation with invite codes
- Session detection accuracy
- Authentication flow integrity
