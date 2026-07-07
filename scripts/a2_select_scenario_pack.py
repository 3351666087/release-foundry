from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.judge.scenario_selection import (  # noqa: E402
    build_project_scenario_selection,
    build_scenario_selection_report,
    load_selection_config,
)


DEFAULT_PROFILE = Path("fixtures/a2/config/a2_saas_project_selection_profile.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a project-aware A2 scenario selection report.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE.as_posix())
    parser.add_argument("--selection-config", help="Project profile config for --project-id mode.")
    parser.add_argument("--project-id", help="Build the compact per-project selection contract for this project.")
    parser.add_argument("--environment", default="prod", help="Environment for --project-id mode.")
    parser.add_argument("--pack", default="packages/scenarios/a2_g3_full_pack.json")
    parser.add_argument("--output", help="Optional JSON output path. Omitting it prints to stdout.")
    parser.add_argument("--check", action="store_true", help="Compare generated report with --output.")
    args = parser.parse_args()

    os.chdir(ROOT)
    if args.project_id:
        selection_config = load_selection_config(args.selection_config) if args.selection_config else None
        report = build_project_scenario_selection(
            project_id=args.project_id,
            environment=args.environment,
            selection_config=selection_config,
            pack_path=Path(args.pack),
        )
    else:
        profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
        report = build_scenario_selection_report(profile, pack_path=Path(args.pack))
    text = json.dumps(report, indent=2) + "\n"

    if args.check:
        if not args.output:
            parser.error("--check requires --output")
        output = Path(args.output)
        if not output.exists() or output.read_text(encoding="utf-8") != text:
            print(f"scenario selection drift: {output.as_posix()}")
            return 1
        print(f"scenario selection report matches {output.as_posix()}")
        return 0

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        print(f"wrote scenario selection report: {output.as_posix()}")
        return 0

    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
