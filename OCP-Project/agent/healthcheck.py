"""Container probe for the scheduler process.

The scheduler writes a heartbeat after startup checks and after every cycle.
This command is intentionally local-only: it does not call Groq,
PostgreSQL, or OpenShift on every Kubernetes probe.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from agent.config import get_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("startup", "readiness", "liveness"),
        nargs="?",
        default="liveness",
    )
    args = parser.parse_args()

    cfg = get_settings()
    heartbeat = Path(cfg.scheduler_health_file)
    if not heartbeat.is_file():
        print(f"scheduler heartbeat is missing: {heartbeat}", file=sys.stderr)
        return 1

    if args.mode == "startup":
        return 0

    age_seconds = max(0.0, time.time() - heartbeat.stat().st_mtime)
    maximum_age = max(
        cfg.healthcheck_max_age_seconds,
        cfg.interval_minutes * 60 + 300,
    )
    if age_seconds > maximum_age:
        print(
            f"scheduler heartbeat is stale: {age_seconds:.0f}s > {maximum_age}s",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
