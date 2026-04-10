from __future__ import annotations

from entrypoints._helpers import run_worker_profile


def main() -> None:
    run_worker_profile("trust-certifier")


if __name__ == "__main__":
    main()
