#!/usr/bin/env python3
"""Build FileGameBuilder.exe using PyInstaller."""

import subprocess
import sys

subprocess.run([
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", "FileGameBuilder",
    "--distpath", "BUILD",
    "--workpath", "BUILD/_work",
    "--specpath", "BUILD",
    "view_data_layout.py",
], check=True)
