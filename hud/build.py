#!/usr/bin/env python3
"""
Builds every HUD panel on the profile into assets/.

    python hud/build.py                    # live intel from the GitHub API
    python hud/build.py --offline          # rebuild from hud/intel.json
    python hud/build.py --only hero,record # just some components

Content lives in hud/config.json; live stats come from hud/intel.py.
Each component module exposes render(cfg, intel) -> {filename: svg}.
Standard library only.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

HUD = Path(__file__).resolve().parent
ASSETS = HUD.parent / "assets"
COMPONENTS = ["hero", "lobby", "loadout", "streaks", "record"]

sys.path.insert(0, str(HUD))
import intel as intel_mod  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    cfg = json.loads((HUD / "config.json").read_text())
    intel = intel_mod.load(cfg, offline=args.offline)
    ASSETS.mkdir(exist_ok=True)
    for name in [c for c in args.only.split(",") if c] or COMPONENTS:
        for fname, content in importlib.import_module(name).render(cfg, intel).items():
            path = ASSETS / fname
            if not path.exists() or path.read_text() != content:
                path.write_text(content)
                print(f"  wrote {fname} ({len(content.encode()) // 1024} KB)")


if __name__ == "__main__":
    main()
