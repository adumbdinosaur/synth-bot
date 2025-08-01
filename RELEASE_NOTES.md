# Release Notes - v1.1.0

**Release Date:** August 1, 2025  
**Branch:** develop → main

## 🚀 New Features

### `/grant` Command - Energy Transfer System
**Added in:** [8e36b44](../../commit/8e36b44)

- **New Command:** `/grant @username amount` - Transfer energy between users
- **Smart Username Resolution:** Supports both website usernames and Telegram usernames
- **Profile Status Validation:** 
  - Granter must have inactive profile (not currently using userbot)
  - Recipient must have active profile (currently using userbot)
- **Comprehensive Error Handling:** Clear feedback for all error conditions
- **Energy Cap Enforcement:** Prevents exceeding maximum energy capacity
- **Documentation:** Complete feature documentation in `GRANT_POWER_FEATURE.md`

### Recent Messages Dashboard
**Added in:** [5b58944](../../commit/5b58944)

- **Activity Feed:** Display 5 most recent energy activities (newest to oldest)
- **Smart Filtering:** Shows energy drains and penalties, excludes recharge events
- **Dual Access:** Works for both authenticated users and active Telegram sessions
- **Enhanced UI:** Cyberpunk-themed responsive design with improved styling
- **Real-time Updates:** Automatically refreshes activity data

## 🐛 Bug Fixes

### `/availablepower` Command Fix
**Fixed in:** [3d507ec](../../commit/3d507ec)

- **Issue:** Command was attempting to edit non-existent messages
- **Solution:** Changed to send new message response instead of editing
- **Impact:** Command now properly responds with power status information

### Command Processing Improvements
**Improved in:** [8e36b44](../../commit/8e36b44)

- **Case Sensitivity:** All commands now processed case-insensitively
- **Consistency:** Unified command handling across `/flip`, `/beep`, `/dance`, `/availablepower`
- **Reliability:** Improved command recognition and response handling

## 📊 Technical Improvements

### Database Enhancements
- **New Manager:** `EnergyManager.get_recent_energy_activities()` for activity tracking
- **Improved Queries:** More efficient energy history retrieval
- **Better Data Structure:** Enhanced activity logging and filtering

### UI/UX Enhancements
- **Dashboard Updates:** Refreshed dashboard templates with activity feeds
- **Styling Improvements:** Enhanced CSS for better visual hierarchy
- **Responsive Design:** Improved mobile and desktop experience

### Code Quality
- **Error Handling:** Comprehensive error management in new features
- **Documentation:** Detailed feature documentation and implementation guides
- **Code Organization:** Better separation of concerns in message handling

## 📁 Files Modified

### New Files
- `GRANT_POWER_FEATURE.md` - Complete documentation for grant command
- `IMPLEMENTATION_SUMMARY.md` - Technical implementation details

### Modified Files
- `app/telegram/message_handler.py` - Grant command implementation and fixes
- `app/database/energy_manager.py` - Recent activities tracking
- `app/database/manager.py` - Database manager updates
- `app/routes/api.py` - API endpoints for dashboard data
- `app/routes/dashboard.py` - Dashboard route enhancements
- `templates/dashboard.html` - Dashboard UI improvements
- `templates/dashboard_restricted.html` - Restricted dashboard updates
- `static/style.css` - Enhanced styling and theming

## 🔒 Security & Validation

- **Profile Status Checks:** Enforced profile validation for energy transfers
- **Input Validation:** Comprehensive validation for grant command parameters
- **User Authentication:** Proper user identification and authorization
- **Energy Limits:** Enforced maximum energy capacity constraints

## 🧪 Testing

- Comprehensive testing of grant command functionality
- Validation of profile status checking logic
- Dashboard activity feed testing
- Command processing reliability testing

## 📈 Statistics

- **Total Commits:** 4 new commits
- **Files Changed:** 11 files modified/added
- **Lines Added:** ~500+ lines of new functionality
- **Lines Removed:** ~40 lines of deprecated/fixed code

## 🔄 Migration Notes

This release is backward compatible. No database migrations or configuration changes required.

## 🎯 What's Next

This release focuses on enhanced user interaction and energy management. Future releases will continue to expand userbot capabilities and improve user experience.

---

**Full Changelog:** [main...develop](../../compare/main...develop)
