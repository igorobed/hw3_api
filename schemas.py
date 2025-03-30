from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional


class ShortUrlCreate(BaseModel):
    orig_url: str
    alias_url: Optional[str] = None


class ShortUrlResponse(BaseModel):
    orig_url: str
    short_url: str
    registered_at: datetime


class ShortUrlStatsResponse(ShortUrlResponse):
    get_num: int
    last_time: Optional[datetime]


class UrlUpdate(BaseModel):
    orig_url: str