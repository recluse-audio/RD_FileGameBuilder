#!/usr/bin/env python3
"""
view_data_layout — visualize the DATA/ folder as nested boxes in a GUI.

Usage:
  python view_data_layout.py                        # opens file dialog
  python view_data_layout.py --project /path/to/DATA
  python view_data_layout.py -p /path/to/MyGame    # auto-detects DATA/ subdir

Left-click  a file (.md / .json / .png) to preview it in the right panel.
Right-click any folder header for context-aware actions:
  - LEVELS dir   -> Add Level
  - LEVEL_N dir  -> Add Scene
  - SCENE_N dir  -> Add Scene (child scene)
  - Any folder   -> New File / New Folder / Delete
  - Any file     -> Delete
"""

from file_game_builder.__main__ import main

if __name__ == "__main__":
    main()
