"""`python -m viz <exp_id>` or `python -m viz --latest`."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from viz.report import build_for_latest, build_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exp_id", nargs="?", default=None,
                        help="exp_id directory under output/")
    parser.add_argument("--output-dir", default="output",
                        help="parent directory holding output/<exp_id>/")
    parser.add_argument("--latest", action="store_true",
                        help="build the most-recently-modified experiment")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.latest or args.exp_id is None:
        out = build_for_latest(args.output_dir)
    else:
        out = build_report(Path(args.output_dir) / args.exp_id)
    print(f"\nopen file://{out.resolve()}")


if __name__ == "__main__":
    main()
