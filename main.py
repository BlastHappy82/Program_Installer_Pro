#!/usr/bin/env python3
"""
Installer Manager - Main Entry Point

A Python application for managing software installers with:
- Installer scanning and version detection
- Automatic update checking and downloading
- Installed program detection
- Installation queue with restart handling
- Session resumption after reboot

Usage:
    python main.py              # Normal startup
    python main.py --resume     # Resume pending installations
    python main.py --check      # Check for pending (launcher mode)
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.gui import InstallerManagerGUI
from src.launcher import LauncherCheck


def main():
    parser = argparse.ArgumentParser(description='Installer Manager')
    parser.add_argument('--resume', action='store_true', 
                        help='Resume pending installations')
    parser.add_argument('--check', action='store_true',
                        help='Check for pending installations (launcher mode)')
    parser.add_argument('--folder', type=str,
                        help='Set initial installer folder')
    
    args = parser.parse_args()
    
    if args.check:
        checker = LauncherCheck()
        checker.run()
        return
    
    app = InstallerManagerGUI(resume_mode=args.resume)
    
    if args.folder:
        app.installer_folder = args.folder
        app.folder_var.set(args.folder)
    
    app.run()


if __name__ == "__main__":
    main()
