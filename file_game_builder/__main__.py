"""
Entry point for the File Game Builder GUI.

Usage:
  python -m file_game_builder
  python -m file_game_builder --project /path/to/DATA
  python -m file_game_builder -p /path/to/MyGame   # auto-detects DATA/ subdir
"""

import argparse
import os
import sys

from .app import DataLayoutApp


def _resolve_project_root(path: str) -> str:
    """
    Accept either a DATA folder or a project root that contains a DATA/ subfolder.
    Returns the absolute path to the DATA folder, or raises SystemExit on failure.
    """
    path = os.path.abspath(path)
    if os.path.isdir(os.path.join(path, "LEVELS")):
        return path
    candidate = os.path.join(path, "DATA")
    if os.path.isdir(os.path.join(candidate, "LEVELS")):
        return candidate
    print(f"error: '{path}' is not a valid project path.\n"
          f"  Expected a DATA folder (containing LEVELS/) or a project root "
          f"(containing DATA/LEVELS/).")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize a game project DATA folder.")
    parser.add_argument(
        "-p", "--project", metavar="PATH",
        help="Path to the project DATA folder (or project root containing DATA/).",
    )
    args = parser.parse_args()

    if args.project:
        data_root    = _resolve_project_root(args.project)
        project_name = (os.path.basename(os.path.dirname(data_root))
                        or os.path.basename(data_root))
    else:
        data_root    = None
        project_name = ""

    app = DataLayoutApp(data_root, project_name)
    app.run()


if __name__ == "__main__":
    main()
