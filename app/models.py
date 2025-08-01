from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class UserBase(BaseModel):
    username: str
    email: str


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int
    telegram_connected: bool = False
    phone_number: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TelegramMessageBase(BaseModel):
    content: str
    chat_id: int
    chat_title: Optional[str] = None
    chat_type: Optional[str] = None
    sent_at: datetime


class TelegramMessageCreate(TelegramMessageBase):
    user_id: int
    message_id: int


class TelegramMessage(TelegramMessageBase):
    id: int
    user_id: int
    message_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class TelegramSessionBase(BaseModel):
    session_data: str


class TelegramSessionCreate(TelegramSessionBase):
    user_id: int


class TelegramSession(TelegramSessionBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatBlacklistBase(BaseModel):
    chat_id: int
    chat_title: str = None
    chat_type: str = None


class ChatBlacklistCreate(ChatBlacklistBase):
    user_id: int


class ChatBlacklist(ChatBlacklistBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ChatWhitelistBase(BaseModel):
    chat_id: int
    chat_title: str = None
    chat_type: str = None


class ChatWhitelistCreate(ChatWhitelistBase):
    user_id: int


class ChatWhitelist(ChatWhitelistBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ChatListSettingsBase(BaseModel):
    list_mode: str = "blacklist"  # "blacklist" or "whitelist"


class ChatListSettingsCreate(ChatListSettingsBase):
    user_id: int


class ChatListSettings(ChatListSettingsBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
