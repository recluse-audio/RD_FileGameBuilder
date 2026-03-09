#!/usr/bin/env python3
"""
Rebuild level_info.json for each level and regenerate
DATA/GAME_STATE/Default_Game_State.json from the LEVELS directory.

Each level subdirectory must contain SCENE_N subdirectories.
Each scene subdirectory must contain scene_info.json with at least a "name"
field. Optional "md" and "png" fields reference files in the same directory.
Scenes may contain child SCENE_N subdirectories, which are listed in the
parent's scene_info.json under "scenes".

Usage:
    python SCRIPTS/refresh_game_data.py
"""

import argparse
import json
from pathlib import Path


def _scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, str):
        return json.dumps(v)
    return str(v)


def allman_json(obj, indent: int = 0) -> str:
    """Serialize obj to JSON with Allman-style braces (opening brace on its own line)."""
    pad   = "  " * indent
    inner = "  " * (indent + 1)

    if isinstance(obj, list):
        if not obj:
            return "[]"
        items_str = ", ".join(_scalar(v) for v in obj)
        return f"[ {items_str} ]"

    if not isinstance(obj, dict):
        return _scalar(obj)

    if not obj:
        return "{}"

    parts = []
    items = list(obj.items())
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        if isinstance(v, dict) and v:
            parts.append(f'{inner}"{k}":\n{allman_json(v, indent + 1)}{comma}')
        else:
            parts.append(f'{inner}"{k}": {allman_json(v, indent + 1)}{comma}')

    return f"{pad}{{\n" + "\n".join(parts) + f"\n{pad}}}"


ROOT            = Path(__file__).parent.parent
DATA_ROOT       = ROOT / "DATA"
LEVELS_DIR      = DATA_ROOT / "LEVELS"
GAME_STATE_PATH = DATA_ROOT / "GAME_STATE" / "Default_Game_State.json"

# Base path used for display in print() calls — overridden when --data-root is set
_PRINT_BASE = ROOT

SCENE_INFO = "scene_info.json"


def level_display_name(dir_name: str) -> str:
    return dir_name.replace("_", " ").title()


def scene_display_name(dir_name: str) -> str:
    return dir_name.replace("_", " ").title()


def _scene_friendly_name(scene_dir: Path) -> str:
    """Return the friendly name from a scene directory's scene_info.json."""
    info_path = scene_dir / SCENE_INFO
    try:
        info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    except Exception:
        info = {}
    return info.get("name", scene_display_name(scene_dir.name))


def write_level_info(level_dir: Path) -> None:
    """Write level_info.json with the display name and friendly-named list of child scenes."""
    child_dirs = sorted(
        d for d in level_dir.iterdir()
        if d.is_dir() and d.name.startswith("SCENE_")
    )
    info: dict = {"name": level_display_name(level_dir.name)}
    if child_dirs:
        info["scenes"] = [_scene_friendly_name(d) for d in child_dirs]
    out = level_dir / "level_info.json"
    out.write_text(allman_json(info) + "\n", encoding="utf-8")
    print(f"  wrote {out.relative_to(_PRINT_BASE)}")


def scan_scene(scene_dir: Path, depth: int = 1) -> dict:
    """
    Read or create scene_info.json in scene_dir.
    Ensures "name" is set. Recurses into child SCENE_N subdirectories and
    records their directory names in "scenes". Returns the parsed dict.
    md/png/zones fields are left untouched — managed explicitly by the user.
    """
    indent_str = "  " * depth

    info_path = scene_dir / SCENE_INFO
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
        except Exception:
            info = {}
    else:
        info = {}

    info.setdefault("name", scene_display_name(scene_dir.name))

    # Recurse into child scenes
    child_dirs = sorted(
        d for d in scene_dir.iterdir()
        if d.is_dir() and d.name.startswith("SCENE_")
    )

    if child_dirs:
        info["scenes"] = [_scene_friendly_name(d) for d in child_dirs]
    elif "scenes" in info:
        # Remove stale entry if no children exist on disk
        del info["scenes"]

    info_path.write_text(allman_json(info) + "\n", encoding="utf-8")
    print(f"{indent_str}wrote {info_path.relative_to(_PRINT_BASE)}")

    for child_dir in child_dirs:
        print(f"{indent_str}  {child_dir.name}:")
        scan_scene(child_dir, depth + 1)

    return info


def build_scene_state(scene_dir: Path) -> tuple[str, dict]:
    """
    Return (friendly_name, state_dict) for a scene directory.
    state_dict is {"isUnlocked": False} plus a nested "scenes" dict if children exist.
    """
    info_path = scene_dir / SCENE_INFO
    try:
        info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    except Exception:
        info = {}

    friendly_name = info.get("name", scene_display_name(scene_dir.name))

    child_dirs = sorted(
        d for d in scene_dir.iterdir()
        if d.is_dir() and d.name.startswith("SCENE_")
    )

    state: dict = {"isUnlocked": False}
    if child_dirs:
        state["scenes"] = {
            name: child_state
            for d in child_dirs
            for name, child_state in [build_scene_state(d)]
        }

    return friendly_name, state


def run(data_root_path: str | None = None) -> None:
    """
    Regenerate all level_info.json, scene_info.json, and Default_Game_State.json
    for the given DATA directory (defaults to the repo's DATA/ folder).
    Can be called directly from other modules without subprocess.
    """
    global DATA_ROOT, LEVELS_DIR, GAME_STATE_PATH, _PRINT_BASE

    _saved = (DATA_ROOT, LEVELS_DIR, GAME_STATE_PATH, _PRINT_BASE)

    if data_root_path is not None:
        data_root       = Path(data_root_path)
        levels_dir      = data_root / "LEVELS"
        game_state_path = data_root / "GAME_STATE" / "Default_Game_State.json"
        print_base      = data_root
    else:
        data_root       = DATA_ROOT
        levels_dir      = LEVELS_DIR
        game_state_path = GAME_STATE_PATH
        print_base      = _PRINT_BASE

    # Patch module globals so write_level_info / scan_scene resolve paths correctly
    DATA_ROOT, LEVELS_DIR, GAME_STATE_PATH, _PRINT_BASE = (
        data_root, levels_dir, game_state_path, print_base
    )

    try:
        levels: dict = {}
        first_level_name = ""
        first_scene_name = ""

        if not levels_dir.exists():
            print(f"LEVELS directory not found: {levels_dir}")
        else:
            for level_dir in sorted(levels_dir.iterdir()):
                if not level_dir.is_dir():
                    continue

                print(f"{level_dir.name}:")
                write_level_info(level_dir)

                scene_dirs = sorted(
                    d for d in level_dir.iterdir()
                    if d.is_dir() and d.name.startswith("SCENE_")
                )

                scenes: dict = {}
                for scene_dir in scene_dirs:
                    print(f"  {scene_dir.name}:")
                    scan_scene(scene_dir, depth=2)
                    scene_name, scene_state = build_scene_state(scene_dir)
                    scenes[scene_name] = scene_state

                level_name = level_display_name(level_dir.name)
                levels[level_name] = {
                    "isUnlocked": False,
                    "scenes": scenes,
                }

                if not first_level_name:
                    first_level_name = level_name
                    if scene_dirs:
                        first_scene_info = json.loads(
                            (scene_dirs[0] / SCENE_INFO).read_text(encoding="utf-8")
                        )
                        first_scene_name = first_scene_info.get("name", "")

        state = {
            "current_level": first_level_name,
            "current_scene": first_scene_name,
            "levels":        levels,
        }

        game_state_path.parent.mkdir(parents=True, exist_ok=True)
        game_state_path.write_text(allman_json(state) + "\n", encoding="utf-8")
        print(f"\nWrote {game_state_path.relative_to(print_base)}")
    finally:
        DATA_ROOT, LEVELS_DIR, GAME_STATE_PATH, _PRINT_BASE = _saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh game data files.")
    parser.add_argument("--data-root", metavar="PATH",
                        help="Override the DATA directory (for external projects)")
    args = parser.parse_args()
    run(args.data_root)


if __name__ == "__main__":
    main()
