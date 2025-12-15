"""
Launcher module for startup notifications and resumption.
This runs without admin privileges to show notifications.
"""
import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StartupManager:
    """Manages Windows startup registration for the launcher."""
    
    STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "InstallerManager"
    
    def __init__(self):
        self.is_windows = os.name == 'nt'
        self.launcher_path = self._get_launcher_path()
    
    def _get_launcher_path(self) -> str:
        """Get path to the launcher script."""
        launcher_path = Path(__file__).parent / "launcher_check.py"
        if launcher_path.exists():
            return str(launcher_path)
        main_path = Path(__file__).parent.parent / "main.py"
        return str(main_path)
    
    def register_startup(self) -> bool:
        """Register the launcher to run at Windows startup."""
        if not self.is_windows:
            logger.info("Startup registration is Windows-only")
            return False
        
        try:
            import winreg
            
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.STARTUP_KEY,
                0,
                winreg.KEY_SET_VALUE
            )
            
            python_exe = sys.executable
            if self.launcher_path.endswith('main.py'):
                command = f'"{python_exe}" "{self.launcher_path}" --check'
            else:
                command = f'"{python_exe}" "{self.launcher_path}"'
            
            winreg.SetValueEx(key, self.APP_NAME, 0, winreg.REG_SZ, command)
            winreg.CloseKey(key)
            
            logger.info("Registered startup entry")
            return True
        
        except Exception as e:
            logger.error(f"Failed to register startup: {e}")
            return False
    
    def unregister_startup(self) -> bool:
        """Remove the launcher from Windows startup."""
        if not self.is_windows:
            return False
        
        try:
            import winreg
            
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.STARTUP_KEY,
                0,
                winreg.KEY_SET_VALUE
            )
            
            try:
                winreg.DeleteValue(key, self.APP_NAME)
            except FileNotFoundError:
                pass
            
            winreg.CloseKey(key)
            logger.info("Removed startup entry")
            return True
        
        except Exception as e:
            logger.error(f"Failed to unregister startup: {e}")
            return False
    
    def is_registered(self) -> bool:
        """Check if launcher is registered for startup."""
        if not self.is_windows:
            return False
        
        try:
            import winreg
            
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.STARTUP_KEY,
                0,
                winreg.KEY_READ
            )
            
            try:
                winreg.QueryValueEx(key, self.APP_NAME)
                winreg.CloseKey(key)
                return True
            except FileNotFoundError:
                winreg.CloseKey(key)
                return False
        
        except Exception:
            return False


class NotificationManager:
    """Manages toast notifications for pending installations."""
    
    def __init__(self):
        self.is_windows = os.name == 'nt'
    
    def show_notification(self, title: str, message: str, 
                          on_click: callable = None) -> bool:
        """Show a toast notification."""
        if self.is_windows:
            return self._show_windows_notification(title, message, on_click)
        else:
            return self._show_fallback_notification(title, message)
    
    def _show_windows_notification(self, title: str, message: str, 
                                    on_click: callable = None) -> bool:
        """Show Windows toast notification."""
        try:
            from tkinter import messagebox
            import tkinter as tk
            
            root = tk.Tk()
            root.withdraw()
            
            result = messagebox.askyesno(
                title,
                f"{message}\n\nWould you like to continue now?"
            )
            
            root.destroy()
            
            if result and on_click:
                on_click()
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to show notification: {e}")
            return False
    
    def _show_fallback_notification(self, title: str, message: str) -> bool:
        """Show fallback notification for non-Windows."""
        print(f"\n{'='*50}")
        print(f"NOTIFICATION: {title}")
        print(f"{'='*50}")
        print(message)
        print(f"{'='*50}\n")
        return True


class LauncherCheck:
    """Checks for pending installations on startup."""
    
    def __init__(self):
        self.db_path = Path.home() / ".installer_manager" / "installer_manager.db"
        self.notification_manager = NotificationManager()
    
    def check_pending_installations(self) -> Optional[int]:
        """Check database for pending installations. Returns count or None."""
        if not self.db_path.exists():
            return None
        
        try:
            import sqlite3
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) FROM installation_queue 
                WHERE status IN ('pending', 'needs_restart', 'interrupted')
            """)
            
            count = cursor.fetchone()[0]
            conn.close()
            
            return count if count > 0 else None
        
        except Exception as e:
            logger.error(f"Failed to check pending installations: {e}")
            return None
    
    def check_session_state(self) -> Optional[dict]:
        """Check for interrupted session state."""
        if not self.db_path.exists():
            return None
        
        try:
            import sqlite3
            
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM session_state WHERE id = 1")
            row = cursor.fetchone()
            conn.close()
            
            if row and row['is_resuming']:
                return {
                    'pending_installations': json.loads(row['pending_installations']) if row['pending_installations'] else [],
                    'current_position': row['current_position']
                }
            
            return None
        
        except Exception as e:
            logger.error(f"Failed to check session state: {e}")
            return None
    
    def run(self):
        """Run startup check and show notification if needed."""
        pending_count = self.check_pending_installations()
        session_state = self.check_session_state()
        
        if pending_count or session_state:
            count = pending_count or len(session_state.get('pending_installations', []))
            
            def launch_main_app():
                import subprocess
                main_app = Path(__file__).parent.parent / "main.py"
                subprocess.Popen([sys.executable, str(main_app), "--resume"])
            
            self.notification_manager.show_notification(
                "Installer Manager",
                f"You have {count} pending installation(s).\n"
                "Click 'Yes' to continue the installation process.",
                on_click=launch_main_app
            )


def main():
    """Entry point for launcher check."""
    checker = LauncherCheck()
    checker.run()


if __name__ == "__main__":
    main()
