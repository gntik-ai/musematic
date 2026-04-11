from __future__ import annotations

from entrypoints._helpers import run_uvicorn_profile


def main() -> None:
    run_uvicorn_profile("scheduler", 8001)


if __name__ == "__main__":
    main()
