# Restricted Dashboard for Users with Active Sessions

## Overview
Implemented comprehensive restrictions for users with active Telegram sessions, ensuring they cannot modify any energy-related settings, badwords, autocorrect, or other configurations while their session is active.

## ✅ Implementation Summary

### 1. **Restricted Dashboard View**
- **File**: `templates/dashboard_restricted.html` (new)
- **Features**:
  - Shows current energy level and recharge rate (read-only)
  - Displays session active warning
  - Provides "Disconnect Session" button
  - Lists restricted and available features
  - Clean, informative UI with Bootstrap styling

### 2. **Dashboard Route Logic** 
- **File**: `main.py` (dashboard function updated)
- **Logic**:
  - Checks if user has active Telegram session using `has_active_telegram_session()`
  - Routes users with active sessions to `dashboard_restricted.html`
  - Regular users get full `dashboard.html` with all features

### 3. **Session Disconnect Route**
- **Route**: `POST /disconnect-session` (new)
- **Functionality**:
  - Disconnects active Telegram client
  - Removes client from manager
  - Deletes session files to prevent auto-reconnection
  - Redirects back to dashboard with success message

### 4. **Protected Settings Routes**
All settings routes now use `get_current_user_with_session_check` instead of `get_current_user`:

#### Energy Settings:
- `GET /energy-settings` ✅ Protected
- `POST /energy-settings` ✅ Protected

#### Profile Protection:
- `GET /profile-protection` ✅ Protected  
- `POST /profile-protection` ✅ Protected

#### Badwords Management:
- `GET /badwords` ✅ Already protected
- `POST /badwords/add` ✅ Protected
- `POST /badwords/remove` ✅ Protected

#### Public Dashboard Routes:
- All `/public/*` routes ✅ Already protected with session checking

## 🔒 Access Control Matrix

### Users WITHOUT Active Session:
- ✅ Full dashboard access
- ✅ Energy settings modification
- ✅ Badwords management
- ✅ Profile protection settings
- ✅ Public dashboard access
- ✅ All configuration options

### Users WITH Active Session:
- ✅ View current energy level (read-only)
- ✅ View recharge rate (read-only)
- ✅ Disconnect session capability
- ❌ Energy settings modification
- ❌ Badwords management
- ❌ Profile protection settings
- ❌ Public dashboard access
- ❌ Any configuration changes

## 🎯 User Experience Flow

### Scenario 1: User with Active Session
1. User logs in and visits `/dashboard`
2. System detects active Telegram session
3. User sees restricted dashboard with:
   - Current energy: 85/100 (read-only)
   - Recharge rate: 1 point/minute (read-only)
   - Warning about restrictions
   - "Disconnect Session" button
4. User can disconnect session to regain full access

### Scenario 2: User without Active Session  
1. User logs in and visits `/dashboard`
2. System detects no active session
3. User sees full dashboard with all features
4. Can access all settings and configuration options

## 🔧 Technical Implementation

### Session Detection
```python
# In dashboard route
has_active_session = await db_manager.has_active_telegram_session(current_user["id"])

if has_active_session:
    return templates.TemplateResponse("dashboard_restricted.html", {...})
else:
    return templates.TemplateResponse("dashboard.html", {...})
```

### Route Protection
```python
# Protected routes use session checking dependency
@app.get("/energy-settings")
async def energy_settings_page(
    request: Request, 
    current_user: dict = Depends(get_current_user_with_session_check)
):
```

### Session Disconnection
```python
# Disconnect both client and remove session files
await client.disconnect()  # Disconnect active client
del telegram_manager.clients[user_id]  # Remove from manager
os.remove(session_file_path)  # Delete session files
```

## 🛡️ Security Benefits

1. **Prevents Conflicts**: Users can't modify settings while session is using them
2. **Protects Stability**: Reduces chance of session/settings conflicts
3. **Clear Boundaries**: Users understand when they have full vs restricted access
4. **Safe Disconnection**: Proper cleanup when ending sessions

## 📋 Testing Results

- ✅ Dashboard detects session status correctly
- ✅ Restricted template displays properly
- ✅ Disconnect functionality works
- ✅ Settings routes properly protected
- ✅ Session checking functions operational
- ✅ No access to protected features during active sessions

## 🎉 Outcome

Users with active Telegram sessions now have a clean, informative restricted dashboard that:
- Shows their current status (energy, recharge rate)
- Clearly explains why access is restricted
- Provides easy way to disconnect and regain full access
- Prevents any configuration conflicts during active sessions

This ensures system stability while maintaining a good user experience!
