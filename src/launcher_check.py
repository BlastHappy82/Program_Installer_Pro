#!/usr/bin/env python3
"""
Launcher Check Script - Runs at Windows startup to check for pending installations.
This script runs without admin privileges and shows a notification if installations are pending.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.launcher import LauncherCheck


def main():
    """Entry point for launcher check."""
    checker = LauncherCheck()
    checker.run()


if __name__ == "__main__":
    main()
