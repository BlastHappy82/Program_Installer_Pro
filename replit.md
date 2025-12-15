# Installer Manager

A Python application for managing software installers with automatic update checking, download capabilities, and restart-aware installation handling.

## Overview

This application is a conversion from a PowerShell script to a full-featured Python GUI application. It helps manage a folder of installer files (.exe, .msi) with the following capabilities:

1. **Installer Scanning** - Scan a folder for installer files and detect program names/versions
2. **Update Checking** - Check for newer versions using Winget manifests and direct sources
3. **Download Manager** - Download updated installers with progress tracking
4. **Installed Program Detection** - Scan Windows Registry to find installed programs
5. **Installation Queue** - Queue and execute installers with restart handling
6. **Session Persistence** - Resume installations after system restart

## Project Structure

```
├── main.py                 # Entry point
├── src/
│   ├── __init__.py
│   ├── database.py         # SQLite database for tracking
│   ├── scanner.py          # Installer and installed program scanning
│   ├── updater.py          # Update checking via Winget/direct sources
│   ├── downloader.py       # Download manager with async support
│   ├── installer.py        # Installation executor with exit code handling
│   ├── launcher.py         # Startup manager and notifications
│   └── gui.py              # Main tkinter GUI application
└── attached_assets/        # Original PowerShell script
```

## Features

### Update Installers Mode
- Scan installer folder for .exe and .msi files
- Detect program name and version from filename
- Check for updates via Winget API and direct sources
- Download newer versions to the installer folder
- Set custom download URLs for unknown software

### Run Installations Mode
- Add installers to a queue
- Execute installers interactively
- Track exit codes and detect restart requirements
- Save session state for resumption after restart
- Show notifications for pending installations

### Scan Installed Programs Mode
- Read installed programs from Windows Registry
- Match installed programs to existing installers
- Identify programs without corresponding installers
- Offer to download missing installers

## Technical Details

- **Database**: SQLite stored in `~/.installer_manager/installer_manager.db`
- **GUI Framework**: tkinter (cross-platform)
- **Update Sources**: Winget API, Chromium API, direct website scraping
- **Platform**: Designed for Windows, with demo mode for development on other platforms

## Usage

```bash
# Normal startup
python main.py

# Resume pending installations
python main.py --resume

# Check for pending installations (launcher mode)
python main.py --check

# Specify installer folder
python main.py --folder "C:\Users\username\Installers"
```

## Known Software with Update Support

- Google Chrome
- Mozilla Firefox
- 7-Zip
- VLC Media Player
- Notepad++
- Visual Studio Code
- Git for Windows
- Python
- Node.js
- PuTTY
- WinSCP
- FileZilla

## Session State & Restart Handling

When an installer requires a restart (exit code 3010 or 1641):
1. The application saves the current queue state to the database
2. A non-admin launcher can be registered to run at Windows startup
3. On next login, a notification prompts to continue installations
4. The main app can be launched with `--resume` to continue

## Development Notes

- The application runs on Linux/macOS for development with simulated Windows features
- InstalledProgramScanner returns demo data on non-Windows platforms
- InstallationExecutor simulates installations on non-Windows platforms
