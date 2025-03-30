from fastapi import FastAPI, Depends, HTTPException, Request, status, Query
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from redis import asyncio as aioredis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_cache.decorator import cache

from database import get_async_session
from schemas import ShortUrlResponse, ShortUrlCreate, UrlUpdate, ShortUrlStatsResponse
from models import UrlsDB
import shortuuid
from datetime import datetime
from sqlalchemy import select, update, delete
from fastapi.responses import RedirectResponse

import uvicorn

from database import engine
from models import Base


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def invalidate_cache(short_code: str):
    await FastAPICache.clear(key=f"short_to_orig:{short_code}")


def generate_short_code() -> str:
    return shortuuid.uuid()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    redis = aioredis.from_url("redis://redis_app")
    FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
    await create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/links/search", response_model=list[ShortUrlResponse])
async def search_links(
    original_url: str = Query(),
    db: AsyncSession = Depends(get_async_session)
):
    result = await db.execute(
        select(UrlsDB).where(UrlsDB.original == original_url)
    )
    urls_lst = result.scalars().all()
    
    if not urls_lst:
        raise HTTPException(status_code=404, detail="Ссылки не найдены")
    
    return [
        {
            "short_url": url.short,
            "orig_url": url.original,
            "registered_at": url.registered_at,
        }
        for url in urls_lst
    ]


@app.post("/links/shorten", response_model=ShortUrlResponse)
async def create_short(
    url: ShortUrlCreate,
    db: AsyncSession = Depends(get_async_session)
):
    if url.alias_url is not None:
        short_code = url.alias_url
        existing = await db.execute(
            select(UrlsDB).where(UrlsDB.short == short_code)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Этот alias уже занят"
            )
    else:
        short_code = generate_short_code()

    new_url = UrlsDB(
        short=short_code,
        original=url.orig_url,
        registered_at=datetime.now()
    )
    
    db.add(new_url)
    await db.commit()
    await db.refresh(new_url)

    await invalidate_cache(short_code=new_url.short)
    
    return {
        "orig_url": url.orig_url,
        "short_url": short_code,
        "registered_at": new_url.registered_at
    }


@app.get("/links/{short_code}")
@cache(expire=60)
async def short_to_orig(
    short_code: str,
    db: AsyncSession = Depends(get_async_session)
):
    with open("tw.txt", "w") as f:
        f.write(short_code)
    result = await db.execute(select(UrlsDB).where(UrlsDB.short == short_code))
    url_entry = result.scalar_one_or_none()
    
    if not url_entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Короткий URL не найден")
    
    url_entry.get_num += 1
    url_entry.last_time = datetime.now()
    await db.commit()
    await db.refresh(url_entry)
    
    return {"redirect_url": url_entry.original}


@app.delete("/links/{short_code}")
async def delete_short_url(
    short_code: str,
    db: AsyncSession = Depends(get_async_session)
):
    result = await db.execute(delete(UrlsDB).where(UrlsDB.short == short_code))
    await db.commit()
    
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Короткий URL не найден")
    
    await invalidate_cache(short_code=short_code)
    
    return {"status": "deleted"}


@app.put("/links/{short_code}", response_model=ShortUrlResponse)
async def update_original_url(
    short_code: str,
    url_data: UrlUpdate,
    db: AsyncSession = Depends(get_async_session)
):
    result = await db.execute(
        update(UrlsDB)
        .where(UrlsDB.short == short_code)
        .values(original=url_data.orig_url)
        .returning(UrlsDB)
    )
    updated_url = result.scalar_one_or_none()
    await db.commit()
    
    if not updated_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Короткий URL не найден")
    
    await invalidate_cache(short_code=short_code)
    
    return {
        "orig_url": updated_url.original,
        "short_url": updated_url.short,
        "registered_at": updated_url.registered_at
    }


@app.get("/links/{short_code}/stats", response_model=ShortUrlStatsResponse)
async def get_url_stats(
    short_code: str,
    db: AsyncSession = Depends(get_async_session)
):
    result = await db.execute(select(UrlsDB).where(UrlsDB.short == short_code))
    url_entry = result.scalar_one_or_none()
    
    if not url_entry:
        raise HTTPException(status_code=404, detail="Короткий URL не найден")
    
    return {
        "orig_url": url_entry.original,
        "short_url": url_entry.short,
        "registered_at": url_entry.registered_at,
        "get_num": url_entry.get_num,
        "last_time": url_entry.last_time
    }


if __name__ == "__main__":
    uvicorn.run("main:app", reload=True, host="0.0.0.0", log_level="info")