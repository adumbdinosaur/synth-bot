from fastapi import Request
from typing import Optional

def is_authenticated(request: Request) -> bool:
    """Check if user is authenticated by checking for access token."""
    token = request.cookies.get("access_token")
    auth_header = request.headers.get("Authorization")
    
    return bool(token or (auth_header and auth_header.startswith("Bearer ")))

def format_datetime(dt) -> str:
    """Format datetime for display."""
    if not dt:
        return "Unknown"
    
    if isinstance(dt, str):
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
    
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to specified length."""
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length - 3] + "..."
