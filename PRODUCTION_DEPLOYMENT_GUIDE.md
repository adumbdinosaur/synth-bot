# Production Deployment Guide - Invite Code System

## Overview
The authentication system now automatically initializes the permanent invite code during database setup, ensuring production deployments work seamlessly without manual intervention.

## ✅ Automatic Initialization

### What Happens During Deployment
When the application starts for the first time in production:

1. **Database Tables Creation**: The `init_database_manager()` function creates all necessary tables
2. **Automatic Invite Code Setup**: The permanent invite code `"peterpepperpickedapepper"` is automatically inserted into the database
3. **Duplicate Prevention**: Re-deployments or restarts will NOT create duplicate invite codes

### Key Benefits
- ✅ **Zero Manual Setup**: No need to run `init_invite_code.py` manually
- ✅ **Production Ready**: Works immediately after deployment
- ✅ **Idempotent**: Safe to run multiple times without side effects
- ✅ **Consistent**: Same invite code across all environments

## 🚀 Deployment Steps

### For New Deployments
1. Deploy the application with all files
2. Set environment variables (see `.env.example`)
3. Start the application - the invite code will be automatically available

### For Existing Deployments
- The system will detect existing invite codes and won't create duplicates
- Your existing invite codes remain untouched

## 🔧 Technical Implementation

The automatic initialization happens in `app/database_manager.py` within the `init_database_manager()` function:

```python
# Initialize the permanent invite code if it doesn't exist
permanent_invite_code = "peterpepperpickedapepper"
cursor = await db.execute(
    "SELECT COUNT(*) FROM invite_codes WHERE code = ?",
    (permanent_invite_code,)
)
count = await cursor.fetchone()

if count[0] == 0:
    await db.execute(
        """
        INSERT INTO invite_codes (code, max_uses, current_uses, is_active)
        VALUES (?, NULL, 0, TRUE)
        """,
        (permanent_invite_code,)
    )
```

## 📋 Verification

After deployment, you can verify the invite code is available by:

1. **Web Interface**: Try registering with invite code `"peterpepperpickedapepper"`
2. **Database Check**: Query the `invite_codes` table
3. **Application Logs**: Look for the initialization message in logs

## 🔄 Migration from Manual Setup

If you previously used the `init_invite_code.py` script:
- The new automatic system will detect your existing invite code
- No migration or manual steps needed
- The `init_invite_code.py` script is now optional (kept for backward compatibility)

## 🛡️ Security Considerations

### Invite Code Management
- The permanent invite code `"peterpepperpickedapepper"` has unlimited uses
- Consider changing this code for production if needed
- Additional invite codes can be created through the admin interface or database

### Production Recommendations
1. **Change Default Code**: Consider using a different invite code for production
2. **Monitor Usage**: Track invite code usage through the database
3. **Additional Codes**: Create time-limited or use-limited codes for specific purposes

## 🔧 Customization

### Changing the Default Invite Code
To use a different permanent invite code, modify the `permanent_invite_code` variable in `app/database_manager.py`:

```python
permanent_invite_code = "your-custom-production-code-here"
```

### Environment-Based Codes
You could also make it environment-configurable:

```python
permanent_invite_code = os.getenv("DEFAULT_INVITE_CODE", "peterpepperpickedapepper")
```

## ✅ Production Checklist

- [ ] Environment variables set (TELEGRAM_API_ID, TELEGRAM_API_HASH, SECRET_KEY)
- [ ] Database path configured
- [ ] Application deployed and started
- [ ] Invite code automatically initialized (check logs)
- [ ] Registration working with invite code
- [ ] Authentication system functional

## 🎉 Result

**Your production deployment will have the permanent invite code `"peterpepperpickedapepper"` automatically available for user registration without any manual setup required.**
