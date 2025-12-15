"""
Installation executor module.
Handles running installers and detecting restart requirements.
"""
import os
import subprocess
import logging
from pathlib import Path
from typing import Dict, Optional, Callable
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExitCode(Enum):
    SUCCESS = 0
    SUCCESS_REBOOT_REQUIRED = 3010
    SUCCESS_REBOOT_INITIATED = 1641
    ALREADY_RUNNING = 1618
    CANCELLED = 1602
    ERROR = 1


class InstallResult:
    """Result of an installation attempt."""
    
    def __init__(self, installer_path: str, exit_code: int, 
                 success: bool = False, restart_required: bool = False,
                 error_message: str = None):
        self.installer_path = installer_path
        self.exit_code = exit_code
        self.success = success
        self.restart_required = restart_required
        self.error_message = error_message
    
    @classmethod
    def from_exit_code(cls, installer_path: str, exit_code: int):
        """Create result from installer exit code."""
        success = exit_code in (0, 3010, 1641)
        restart_required = exit_code in (3010, 1641)
        
        error_message = None
        if not success:
            error_messages = {
                1602: "Installation cancelled by user",
                1618: "Another installation is already in progress",
                1619: "Installation package could not be opened",
                1620: "Installation package is invalid",
                1622: "Error opening installation log file",
                1625: "Installation prohibited by system policy",
                1638: "Another version is already installed",
            }
            error_message = error_messages.get(exit_code, f"Installation failed with exit code {exit_code}")
        
        return cls(
            installer_path=installer_path,
            exit_code=exit_code,
            success=success,
            restart_required=restart_required,
            error_message=error_message
        )
    
    def to_dict(self) -> Dict:
        return {
            'installer_path': self.installer_path,
            'exit_code': self.exit_code,
            'success': self.success,
            'restart_required': self.restart_required,
            'error_message': self.error_message
        }


class InstallationExecutor:
    """Executes installer files and tracks results."""
    
    def __init__(self):
        self.is_windows = os.name == 'nt'
        self.current_process = None
    
    def run_installer(self, installer_path: str, 
                      silent: bool = False,
                      wait: bool = True,
                      timeout: int = None) -> InstallResult:
        """
        Run an installer file.
        
        Args:
            installer_path: Path to the installer file
            silent: Run in silent/unattended mode (if supported)
            wait: Wait for installation to complete
            timeout: Max time to wait (None = infinite)
        
        Returns:
            InstallResult with exit code and status
        """
        path = Path(installer_path)
        
        if not path.exists():
            return InstallResult(
                installer_path=installer_path,
                exit_code=-1,
                success=False,
                error_message=f"Installer file not found: {installer_path}"
            )
        
        file_type = path.suffix.lower()
        
        try:
            if file_type == '.msi':
                return self._run_msi(path, silent, wait, timeout)
            elif file_type == '.exe':
                return self._run_exe(path, silent, wait, timeout)
            else:
                return InstallResult(
                    installer_path=installer_path,
                    exit_code=-1,
                    success=False,
                    error_message=f"Unsupported installer type: {file_type}"
                )
        except Exception as e:
            logger.error(f"Installation error: {e}")
            return InstallResult(
                installer_path=installer_path,
                exit_code=-1,
                success=False,
                error_message=str(e)
            )
    
    def _run_msi(self, path: Path, silent: bool, wait: bool, timeout: int) -> InstallResult:
        """Run an MSI installer."""
        if not self.is_windows:
            return self._simulate_installation(str(path))
        
        args = ['msiexec.exe', '/i', str(path)]
        
        if silent:
            args.extend(['/quiet', '/norestart'])
        
        logger.info(f"Running MSI: {' '.join(args)}")
        
        if wait:
            result = subprocess.run(args, capture_output=True, timeout=timeout)
            return InstallResult.from_exit_code(str(path), result.returncode)
        else:
            self.current_process = subprocess.Popen(args)
            return InstallResult(str(path), 0, success=True)
    
    def _run_exe(self, path: Path, silent: bool, wait: bool, timeout: int) -> InstallResult:
        """Run an EXE installer."""
        if not self.is_windows:
            return self._simulate_installation(str(path))
        
        args = [str(path)]
        
        if silent:
            silent_switches = self._detect_silent_switches(path.name)
            args.extend(silent_switches)
        
        logger.info(f"Running EXE: {' '.join(args)}")
        
        if wait:
            result = subprocess.run(args, capture_output=True, timeout=timeout)
            return InstallResult.from_exit_code(str(path), result.returncode)
        else:
            self.current_process = subprocess.Popen(args)
            return InstallResult(str(path), 0, success=True)
    
    def _detect_silent_switches(self, filename: str) -> list:
        """Detect common silent installation switches based on installer type."""
        filename_lower = filename.lower()
        
        if 'inno' in filename_lower or '_setup' in filename_lower:
            return ['/VERYSILENT', '/NORESTART']
        
        if 'nsis' in filename_lower:
            return ['/S']
        
        if 'installshield' in filename_lower:
            return ['/s', '/v"/qn"']
        
        return ['/S', '/silent', '/quiet']
    
    def _simulate_installation(self, installer_path: str) -> InstallResult:
        """Simulate installation for non-Windows development."""
        import random
        import time
        
        time.sleep(0.5)
        
        outcomes = [
            (0, False),
            (0, False),
            (0, False),
            (3010, True),
            (1602, False),
        ]
        
        exit_code, restart = random.choice(outcomes)
        return InstallResult.from_exit_code(installer_path, exit_code)
    
    def check_elevation(self) -> bool:
        """Check if running with administrator privileges."""
        if not self.is_windows:
            return os.geteuid() == 0 if hasattr(os, 'geteuid') else True
        
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    
    def request_elevation(self, script_path: str = None):
        """Request UAC elevation on Windows."""
        if not self.is_windows:
            return
        
        try:
            import ctypes
            import sys
            
            if script_path is None:
                script_path = sys.executable
            
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, script_path, None, 1
            )
        except Exception as e:
            logger.error(f"Failed to request elevation: {e}")


class InstallationQueue:
    """Manages a queue of installations with state persistence."""
    
    def __init__(self, executor: InstallationExecutor):
        self.executor = executor
        self.queue = []
        self.current_index = 0
        self.results = []
        self.paused = False
        self.callbacks = {
            'on_start': None,
            'on_complete': None,
            'on_restart_required': None,
            'on_error': None,
            'on_queue_complete': None
        }
    
    def add(self, installer_path: str, installer_id: int = None):
        """Add an installer to the queue."""
        self.queue.append({
            'path': installer_path,
            'id': installer_id,
            'status': 'pending'
        })
    
    def set_callback(self, event: str, callback: Callable):
        """Set a callback for queue events."""
        if event in self.callbacks:
            self.callbacks[event] = callback
    
    def run(self, start_index: int = 0, silent: bool = False):
        """Run the installation queue."""
        self.current_index = start_index
        self.paused = False
        
        while self.current_index < len(self.queue) and not self.paused:
            item = self.queue[self.current_index]
            item['status'] = 'installing'
            
            if self.callbacks['on_start']:
                self.callbacks['on_start'](self.current_index, item)
            
            result = self.executor.run_installer(item['path'], silent=silent)
            item['result'] = result
            self.results.append(result)
            
            if result.restart_required:
                item['status'] = 'needs_restart'
                if self.callbacks['on_restart_required']:
                    action = self.callbacks['on_restart_required'](self.current_index, item, result)
                    if action == 'pause':
                        self.paused = True
                        return self.get_state()
            elif result.success:
                item['status'] = 'completed'
                if self.callbacks['on_complete']:
                    self.callbacks['on_complete'](self.current_index, item, result)
            else:
                item['status'] = 'failed'
                if self.callbacks['on_error']:
                    self.callbacks['on_error'](self.current_index, item, result)
            
            self.current_index += 1
        
        if self.callbacks['on_queue_complete'] and not self.paused:
            self.callbacks['on_queue_complete'](self.results)
        
        return self.get_state()
    
    def pause(self):
        """Pause the queue."""
        self.paused = True
    
    def resume(self, silent: bool = False):
        """Resume the queue from current position."""
        return self.run(self.current_index, silent)
    
    def get_state(self) -> Dict:
        """Get current queue state for persistence."""
        return {
            'queue': self.queue,
            'current_index': self.current_index,
            'results': [r.to_dict() for r in self.results],
            'paused': self.paused
        }
    
    def restore_state(self, state: Dict):
        """Restore queue state from persistence."""
        self.queue = state.get('queue', [])
        self.current_index = state.get('current_index', 0)
        self.paused = state.get('paused', False)
    
    def get_pending_count(self) -> int:
        """Get number of pending installations."""
        return len(self.queue) - self.current_index
    
    def get_completed_count(self) -> int:
        """Get number of completed installations."""
        return sum(1 for item in self.queue if item.get('status') == 'completed')
    
    def get_failed_count(self) -> int:
        """Get number of failed installations."""
        return sum(1 for item in self.queue if item.get('status') == 'failed')
