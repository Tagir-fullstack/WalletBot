"""Configuration is read only from the environment; never commit credentials."""
import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    webhook_secret: str
    currency: str = 'KZT'
    timezone: str = 'Asia/Almaty'
    allowed_users: frozenset[int] = frozenset()

    @classmethod
    def from_env(cls, *, webhook=False):
        token = os.environ.get('BOT_TOKEN', '')
        database = os.environ.get('DATABASE_URL', '')
        secret = os.environ.get('WEBHOOK_SECRET', '')
        if not token or not database or (webhook and not secret):
            raise ValueError('Set BOT_TOKEN, DATABASE_URL and WEBHOOK_SECRET (for webhook)')
        timezone = os.environ.get('BOT_TIMEZONE', 'Asia/Almaty')
        ZoneInfo(timezone)
        return cls(token, database, secret, os.environ.get('BOT_CURRENCY', 'KZT'), timezone,
                   frozenset(int(x.strip()) for x in os.environ.get('ALLOWED_USER_IDS', '').split(',') if x.strip()))
