import asyncio

from app.bot.run import run_bot


def main() -> None:
    asyncio.run(run_bot())

