from __future__ import annotations

from entrypoints._helpers import run_uvicorn_profile


def main() -> None:
    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except Exception:
        scheduler = None
    else:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(lambda: None, "interval", minutes=5, id="placeholder-heartbeat")
        scheduler.start()

    try:
        run_uvicorn_profile("scheduler", 8001)
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
