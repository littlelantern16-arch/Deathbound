"""Headless CLI for the Deathbound visual generation pipeline.

Examples (run from the repository root, any OS, Python 3.10+):

    # Preflight readiness report (NO generation, NO credentials):
    python3 -m automation.video.run preflight --shots S01-SHOT-001 S01-SHOT-002 S01-SHOT-003

    # Mandatory dry-run of the 3-shot vertical slice (no credentials):
    python3 -m automation.video.run --shots S01-SHOT-001 S01-SHOT-002 S01-SHOT-003

    # Full 58-shot episode dry-run:
    python3 -m automation.video.run

    # Resume a failed run (completed shots are skipped):
    python3 -m automation.video.run --resume

The provider is resolved through the registry — nothing here is hard-coded to
a vendor. Real providers register themselves in provider_adapter.py and are
gated by the ZERO_RUPEE_ONLY policy (capabilities.py).
"""

from __future__ import annotations

import argparse
import json
import sys

from .capabilities import PRODUCTION_COST_POLICY
from .executor import EpisodeExecutor
from .preflight import Preflight
from .provider_adapter import registered_providers

try:  # register bundled local providers (ltx-local, ...); heavy imports lazy
    from . import providers as _providers  # noqa: F401
except Exception:  # pragma: no cover - optional component
    pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m automation.video.run",
        description="Deathbound Visual State + Temporal Continuity Engine",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "preflight"],
        help="run: generate via the selected provider (dry-run default). "
        "preflight: readiness report without generating anything.",
    )
    parser.add_argument(
        "--shots",
        nargs="*",
        default=None,
        help="Contiguous shot IDs to run in order (default: full episode order).",
    )
    parser.add_argument(
        "--provider",
        default="dryrun",
        help=f"Registered provider id (default: dryrun). Registered: {registered_providers()}",
    )
    parser.add_argument(
        "--episode",
        default="EP001",
        help="Episode directory name under projects/ (default: EP001).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume: skip shots already completed in this run id.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Bounded retry attempts per shot (default: 3).",
    )
    args = parser.parse_args(argv)

    if args.command == "preflight":
        report = Preflight(
            provider_id=args.provider,
            episode=args.episode,
            shot_ids=args.shots,
        ).run()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if report["blocking_errors"]:
            print("PREFLIGHT: BLOCKED", file=sys.stderr)
            return 1
        print("PREFLIGHT: OK")
        return 0

    executor = EpisodeExecutor(
        episode=args.episode,
        provider=args.provider,
        shot_ids=args.shots,
        resume=args.resume,
        max_attempts=args.max_attempts,
    )
    report = executor.execute()

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report.get("overall_pass"):
        print("OVERALL: FAIL", file=sys.stderr)
        return 1
    print("OVERALL: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
