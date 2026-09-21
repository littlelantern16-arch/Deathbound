"""Phase 7 download-safety verification (run BEFORE the smoke test).

Proves, against the actual installed provider source:
  1. A stale DEATHBOUND_T5_ENCODER=google/t5-v1_1-xxl is REFUSED (no download).
  2. The default Phase A source is city96/t5-v1_1-xxl-encoder-bf16.
  3. A valid DEATHBOUND_T5_LOCAL_PATH pin wins and bypasses the network.

Exit code 0 = safe to run the smoke test; 1 = do not generate.

Usage (any Python, no GPU required):
    python scripts/verify_encoder_safety.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FORBIDDEN = "google/t5-v1_1-xxl"
SANCTIONED = "city96/t5-v1_1-xxl-encoder-bf16"


def main() -> int:
    from automation.video.ltx_provider import resolve_t5_encoder_source

    failures: list[str] = []

    saved = {k: os.environ.get(k) for k in ("DEATHBOUND_T5_ENCODER", "DEATHBOUND_T5_LOCAL_PATH")}
    for key in saved:
        os.environ.pop(key, None)

    try:
        # 1. Worst case: stale forbidden env value left on the workstation.
        os.environ["DEATHBOUND_T5_ENCODER"] = FORBIDDEN
        try:
            source = resolve_t5_encoder_source()
            failures.append(f"forbidden env value RESOLVED to {source!r} — must raise")
        except Exception as exc:
            message = str(exc)
            print(f"[OK] forbidden DEATHBOUND_T5_ENCODER refused: {message.splitlines()[0][:110]}")
            if "44" not in message or SANCTIONED not in message:
                failures.append("refusal message must name the 44.54 GB fact and the sanctioned repo")

        # 2. Default must be the sanctioned bf16 encoder.
        os.environ.pop("DEATHBOUND_T5_ENCODER", None)
        source = resolve_t5_encoder_source()
        if source != SANCTIONED:
            failures.append(f"default source is {source!r}, expected {SANCTIONED!r}")
        else:
            print(f"[OK] default Phase A source: {source} (~9.52 GB bf16)")

        # 3. A valid local pin wins without touching the network source.
        pin = Path(os.environ.get("DEATHBOUND_ROOT", Path.cwd())) / "cache" / "t5-v1_1-xxl-encoder-bf16"
        if pin.is_dir():
            os.environ["DEATHBOUND_T5_LOCAL_PATH"] = str(pin)
            os.environ["DEATHBOUND_T5_ENCODER"] = FORBIDDEN  # pin must still win
            source = resolve_t5_encoder_source()
            if source != str(pin):
                failures.append(f"local pin not honored: resolved to {source!r}")
            else:
                print(f"[OK] local pin honored (network bypassed): {pin}")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    if failures:
        print("\nNOT SAFE TO GENERATE:")
        for failure in failures:
            print("  -", failure)
        return 1
    print("\nSAFE: the 44.54 GB fp32 repo is unreachable from the active path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
