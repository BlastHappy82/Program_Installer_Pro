"""
Database module for tracking installers, installed programs, and installation queue.
Uses SQLite for persistent storage.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class InstallerStatus(Enum):
    PENDING = "pending"
    INSTALLING = "installing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_RESTART = "needs_restart"
    INTERRUPTED = "interrupted"
    ALREADY_INSTALLED = "already_installed"

class UpdateStatus(Enum):
    UP_TO_DATE = "up_to_date"
    UPDATE_AVAILABLE = "update_available"
    UPDATE_NOT_FOUND = "update_not_found"
    UNKNOWN = "unknown"
    MANUAL_REQUIRED = "manual_required"
    INSTALLER_MISSING = "installer_missing"

class Database:
    def __init__(self, db_path: str = None):
        if db_path is None:
            app_data = Path.home() / ".installer_manager"
            app_data.mkdir(exist_ok=True)
            db_path = str(app_data / "installer_manager.db")
        
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
    
    def _create_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS installers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER,
                file_hash TEXT,
                detected_name TEXT,
                detected_version TEXT,
                file_type TEXT,
                update_status TEXT DEFAULT 'unknown',
                latest_version TEXT,
                download_url TEXT,
                custom_download_url TEXT,
                last_checked TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS installed_programs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                display_name TEXT,
                version TEXT,
                publisher TEXT,
                install_location TEXT,
                uninstall_string TEXT,
                registry_key TEXT,
                matched_installer_id INTEGER,
                has_installer BOOLEAN DEFAULT 0,
                is_hidden BOOLEAN DEFAULT 0,
                manually_linked BOOLEAN DEFAULT 0,
                parent_program_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (matched_installer_id) REFERENCES installers(id),
                FOREIGN KEY (parent_program_id) REFERENCES installed_programs(id)
            )
        """)
        
        try:
            cursor.execute("ALTER TABLE installed_programs ADD COLUMN is_hidden BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE installed_programs ADD COLUMN manually_linked BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE installed_programs ADD COLUMN parent_program_id INTEGER")
        except sqlite3.OperationalError:
            pass
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS installation_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                installer_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                exit_code INTEGER,
                error_message TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                restart_required BOOLEAN DEFAULT 0,
                queue_position INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (installer_id) REFERENCES installers(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS download_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                installer_id INTEGER,
                url TEXT NOT NULL,
                file_path TEXT,
                version TEXT,
                status TEXT DEFAULT 'pending',
                progress REAL DEFAULT 0,
                error_message TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (installer_id) REFERENCES installers(id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                pending_installations TEXT,
                current_position INTEGER DEFAULT 0,
                is_resuming BOOLEAN DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
    
    def add_installer(self, file_path: str, file_name: str, file_size: int = None,
                      detected_name: str = None, detected_version: str = None,
                      file_type: str = None, file_hash: str = None) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO installers 
            (file_path, file_name, file_size, detected_name, detected_version, file_type, file_hash, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (file_path, file_name, file_size, detected_name, detected_version, file_type, file_hash))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_installer(self, installer_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM installers WHERE id = ?", (installer_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_installer_by_path(self, file_path: str) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM installers WHERE file_path = ?", (file_path,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_all_installers(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM installers ORDER BY file_name")
        return [dict(row) for row in cursor.fetchall()]
    
    def update_installer_update_status(self, installer_id: int, update_status: str,
                                        latest_version: Optional[str] = None, download_url: Optional[str] = None):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE installers 
            SET update_status = ?, latest_version = ?, download_url = ?, 
                last_checked = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (update_status, latest_version, download_url, installer_id))
        self.conn.commit()
    
    def set_custom_download_url(self, installer_id: int, url: str):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE installers SET custom_download_url = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (url, installer_id))
        self.conn.commit()
    
    def add_installed_program(self, name: str, display_name: Optional[str] = None, version: Optional[str] = None,
                               publisher: Optional[str] = None, install_location: Optional[str] = None,
                               uninstall_string: Optional[str] = None, registry_key: Optional[str] = None) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO installed_programs 
            (name, display_name, version, publisher, install_location, uninstall_string, registry_key)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, display_name, version, publisher, install_location, uninstall_string, registry_key))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_all_installed_programs(self, include_hidden: bool = False) -> List[Dict]:
        cursor = self.conn.cursor()
        if include_hidden:
            cursor.execute("SELECT * FROM installed_programs WHERE parent_program_id IS NULL ORDER BY display_name")
        else:
            cursor.execute("SELECT * FROM installed_programs WHERE (is_hidden = 0 OR is_hidden IS NULL) AND parent_program_id IS NULL ORDER BY display_name")
        return [dict(row) for row in cursor.fetchall()]
    
    def get_installed_program(self, program_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM installed_programs WHERE id = ?", (program_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_programs_without_installers(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM installed_programs 
            WHERE (has_installer = 0 OR matched_installer_id IS NULL) 
            AND (is_hidden = 0 OR is_hidden IS NULL)
            AND parent_program_id IS NULL
            ORDER BY display_name
        """)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_programs_with_installers(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM installed_programs 
            WHERE has_installer = 1 AND matched_installer_id IS NOT NULL
            AND (is_hidden = 0 OR is_hidden IS NULL)
            AND parent_program_id IS NULL
            ORDER BY display_name
        """)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_hidden_programs(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM installed_programs WHERE is_hidden = 1 ORDER BY display_name")
        return [dict(row) for row in cursor.fetchall()]
    
    def get_manually_linked_programs(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM installed_programs WHERE manually_linked = 1 ORDER BY display_name")
        return [dict(row) for row in cursor.fetchall()]
    
    def hide_program(self, program_id: int):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE installed_programs SET is_hidden = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (program_id,))
        self.conn.commit()
    
    def unhide_program(self, program_id: int):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE installed_programs SET is_hidden = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (program_id,))
        self.conn.commit()
    
    def link_program_to_installer(self, program_id: int, installer_id: int):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE installed_programs 
            SET matched_installer_id = ?, has_installer = 1, manually_linked = 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (installer_id, program_id))
        self.conn.commit()
    
    def unlink_program_from_installer(self, program_id: int):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE installed_programs 
            SET matched_installer_id = NULL, has_installer = 0, manually_linked = 0, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (program_id,))
        self.conn.commit()
    
    def set_program_parent(self, child_id: int, parent_id: int):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE installed_programs SET parent_program_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (parent_id, child_id))
        self.conn.commit()
    
    def match_program_to_installer(self, program_id: int, installer_id: int):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE installed_programs 
            SET matched_installer_id = ?, has_installer = 1, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (installer_id, program_id))
        self.conn.commit()
    
    def clear_installed_programs(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM installed_programs")
        self.conn.commit()
    
    def add_to_queue(self, installer_id: int, position: int = None) -> int:
        cursor = self.conn.cursor()
        if position is None:
            cursor.execute("SELECT COALESCE(MAX(queue_position), 0) + 1 FROM installation_queue")
            position = cursor.fetchone()[0]
        
        cursor.execute("""
            INSERT INTO installation_queue (installer_id, queue_position, status)
            VALUES (?, ?, 'pending')
        """, (installer_id, position))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_queue(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT q.*, i.file_name, i.file_path, i.detected_name, i.detected_version
            FROM installation_queue q
            JOIN installers i ON q.installer_id = i.id
            ORDER BY q.queue_position
        """)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_pending_queue_items(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT q.*, i.file_name, i.file_path, i.detected_name, i.detected_version
            FROM installation_queue q
            JOIN installers i ON q.installer_id = i.id
            WHERE q.status IN ('pending', 'needs_restart', 'interrupted')
            ORDER BY q.queue_position
        """)
        return [dict(row) for row in cursor.fetchall()]
    
    def update_queue_status(self, queue_id: int, status: str, exit_code: int = None,
                            error_message: str = None, restart_required: bool = False):
        cursor = self.conn.cursor()
        now = datetime.utcnow().isoformat()
        
        if status == InstallerStatus.INSTALLING.value:
            cursor.execute("""
                UPDATE installation_queue 
                SET status = ?, started_at = ?
                WHERE id = ?
            """, (status, now, queue_id))
        else:
            cursor.execute("""
                UPDATE installation_queue 
                SET status = ?, exit_code = ?, error_message = ?, 
                    restart_required = ?, completed_at = ?
                WHERE id = ?
            """, (status, exit_code, error_message, restart_required, now, queue_id))
        
        self.conn.commit()
    
    def clear_queue(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM installation_queue")
        self.conn.commit()
    
    def save_session_state(self, pending_ids: List[int], current_position: int):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO session_state (id, pending_installations, current_position, is_resuming, last_updated)
            VALUES (1, ?, ?, 1, CURRENT_TIMESTAMP)
        """, (json.dumps(pending_ids), current_position))
        self.conn.commit()
    
    def get_session_state(self) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM session_state WHERE id = 1")
        row = cursor.fetchone()
        if row:
            state = dict(row)
            state['pending_installations'] = json.loads(state['pending_installations']) if state['pending_installations'] else []
            return state
        return None
    
    def clear_session_state(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM session_state")
        self.conn.commit()
    
    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row['value'] if row else default
    
    def set_setting(self, key: str, value: str):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (key, value))
        self.conn.commit()
    
    def add_download(self, installer_id: int, url: str, version: str = None) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO download_history (installer_id, url, version, started_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (installer_id, url, version))
        self.conn.commit()
        return cursor.lastrowid
    
    def update_download(self, download_id: int, status: str = None, progress: float = None,
                        file_path: str = None, error_message: str = None):
        cursor = self.conn.cursor()
        updates = []
        params = []
        
        if status:
            updates.append("status = ?")
            params.append(status)
            if status == 'completed':
                updates.append("completed_at = CURRENT_TIMESTAMP")
        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        if file_path:
            updates.append("file_path = ?")
            params.append(file_path)
        if error_message:
            updates.append("error_message = ?")
            params.append(error_message)
        
        if updates:
            params.append(download_id)
            cursor.execute(f"UPDATE download_history SET {', '.join(updates)} WHERE id = ?", params)
            self.conn.commit()
    
    def close(self):
        self.conn.close()
