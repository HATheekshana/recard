"""Refresh the game assets managed by enka-py."""
import asyncio
from recard import Client

async def main():
    async with Client() as client:
        await client.update_assets()

if __name__ == "__main__":
    asyncio.run(main())
