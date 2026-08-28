from __future__ import annotations

import asyncio

from app.config import load_config
from app.storage.database import Database


async def main() -> None:
    config = load_config()
    db = Database(config)
    await db.connect()
    try:
        if not await db.health():
            raise SystemExit(1)
        print("Supabase: OK")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
