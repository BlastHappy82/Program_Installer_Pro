"""
Scanner module for detecting installers and installed programs.
"""
import os
import re
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from packaging import version as pkg_version

class InstallerScanner:
    INSTALLER_EXTENSIONS = {'.exe', '.msi'}
    
    VERSION_PATTERNS = [
        r'[_\-\s]v?(\d+\.\d+\.\d+\.\d+)',
        r'[_\-\s]v?(\d+\.\d+\.\d+)',
        r'[_\-\s]v?(\d+\.\d+)',
        r'[_\-\s](\d+)',
    ]
    
    COMMON_SUFFIXES = [
        'setup', 'install', 'installer', 'x64', 'x86', 'win64', 'win32',
        'amd64', 'i386', 'portable', 'full', 'lite', 'pro', 'free',
        'offline', 'online', 'web'
    ]
    
    def __init__(self, folder_path: str, include_subfolders: bool = False):
        self.folder_path = Path(folder_path)
        self.include_subfolders = include_subfolders
    
    def scan(self) -> List[Dict]:
        """Scan folder for installer files."""
        installers = []
        
        if not self.folder_path.exists():
            return installers
        
        if self.include_subfolders:
            files = self.folder_path.rglob('*')
        else:
            files = self.folder_path.glob('*')
        
        for file_path in files:
            if file_path.is_file() and file_path.suffix.lower() in self.INSTALLER_EXTENSIONS:
                installer_info = self._analyze_installer(file_path)
                installers.append(installer_info)
        
        return installers
    
    def _analyze_installer(self, file_path: Path) -> Dict:
        """Extract information from an installer file."""
        file_name = file_path.name
        file_size = file_path.stat().st_size
        file_type = file_path.suffix.lower()
        
        detected_name, detected_version = self._parse_filename(file_name)
        
        file_hash = self._calculate_hash(file_path)
        
        return {
            'file_path': str(file_path),
            'file_name': file_name,
            'file_size': file_size,
            'file_type': file_type,
            'detected_name': detected_name,
            'detected_version': detected_version,
            'file_hash': file_hash
        }
    
    def _parse_filename(self, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """Parse filename to extract program name and version."""
        name_without_ext = Path(filename).stem
        
        detected_version = None
        for pattern in self.VERSION_PATTERNS:
            match = re.search(pattern, name_without_ext, re.IGNORECASE)
            if match:
                detected_version = match.group(1)
                name_without_ext = name_without_ext[:match.start()]
                break
        
        name = name_without_ext
        for suffix in self.COMMON_SUFFIXES:
            pattern = rf'[_\-\s]*{suffix}[_\-\s]*'
            name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)
        
        name = re.sub(r'[_\-]+', ' ', name)
        name = ' '.join(name.split())
        name = name.strip()
        
        return name if name else None, detected_version
    
    def _calculate_hash(self, file_path: Path, algorithm: str = 'sha256') -> str:
        """Calculate file hash for verification."""
        hash_obj = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()


class InstalledProgramScanner:
    """
    Scans for installed programs.
    Note: On Windows, this reads from the Registry.
    This implementation provides a cross-platform simulation for development.
    """
    
    REGISTRY_PATHS = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    
    def __init__(self):
        self.is_windows = os.name == 'nt'
    
    def scan(self) -> List[Dict]:
        """Scan for installed programs."""
        if self.is_windows:
            return self._scan_windows_registry()
        else:
            return self._get_demo_programs()
    
    def _scan_windows_registry(self) -> List[Dict]:
        """Scan Windows Registry for installed programs."""
        programs = []
        
        try:
            import winreg
            
            for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                for reg_path in self.REGISTRY_PATHS:
                    try:
                        key = winreg.OpenKey(hive, reg_path)
                        for i in range(winreg.QueryInfoKey(key)[0]):
                            try:
                                subkey_name = winreg.EnumKey(key, i)
                                subkey = winreg.OpenKey(key, subkey_name)
                                
                                program = self._read_program_info(subkey, subkey_name, reg_path)
                                if program and program.get('display_name'):
                                    programs.append(program)
                                
                                winreg.CloseKey(subkey)
                            except (WindowsError, OSError):
                                continue
                        winreg.CloseKey(key)
                    except (WindowsError, OSError):
                        continue
        except ImportError:
            return self._get_demo_programs()
        
        seen = set()
        unique_programs = []
        for prog in programs:
            key = (prog.get('display_name', '').lower(), prog.get('version', ''))
            if key not in seen:
                seen.add(key)
                unique_programs.append(prog)
        
        return unique_programs
    
    def _read_program_info(self, subkey, subkey_name: str, reg_path: str) -> Optional[Dict]:
        """Read program information from a registry subkey."""
        try:
            import winreg
            
            def get_value(name):
                try:
                    return winreg.QueryValueEx(subkey, name)[0]
                except (WindowsError, OSError):
                    return None
            
            display_name = get_value('DisplayName')
            if not display_name:
                return None
            
            system_component = get_value('SystemComponent')
            if system_component == 1:
                return None
            
            return {
                'name': subkey_name,
                'display_name': display_name,
                'version': get_value('DisplayVersion'),
                'publisher': get_value('Publisher'),
                'install_location': get_value('InstallLocation'),
                'uninstall_string': get_value('UninstallString'),
                'registry_key': f"{reg_path}\\{subkey_name}"
            }
        except Exception:
            return None
    
    def _get_demo_programs(self) -> List[Dict]:
        """Return demo programs for non-Windows development."""
        return [
            {
                'name': 'GoogleChrome',
                'display_name': 'Google Chrome',
                'version': '120.0.6099.130',
                'publisher': 'Google LLC',
                'install_location': 'C:\\Program Files\\Google\\Chrome',
                'uninstall_string': None,
                'registry_key': 'DEMO'
            },
            {
                'name': 'Mozilla Firefox',
                'display_name': 'Mozilla Firefox (x64 en-US)',
                'version': '121.0',
                'publisher': 'Mozilla',
                'install_location': 'C:\\Program Files\\Mozilla Firefox',
                'uninstall_string': None,
                'registry_key': 'DEMO'
            },
            {
                'name': '7-Zip',
                'display_name': '7-Zip 23.01 (x64)',
                'version': '23.01',
                'publisher': 'Igor Pavlov',
                'install_location': 'C:\\Program Files\\7-Zip',
                'uninstall_string': None,
                'registry_key': 'DEMO'
            },
            {
                'name': 'VLC media player',
                'display_name': 'VLC media player',
                'version': '3.0.20',
                'publisher': 'VideoLAN',
                'install_location': 'C:\\Program Files\\VideoLAN\\VLC',
                'uninstall_string': None,
                'registry_key': 'DEMO'
            },
            {
                'name': 'Notepad++',
                'display_name': 'Notepad++ (64-bit x64)',
                'version': '8.6',
                'publisher': 'Notepad++ Team',
                'install_location': 'C:\\Program Files\\Notepad++',
                'uninstall_string': None,
                'registry_key': 'DEMO'
            },
            {
                'name': 'Python 3.11',
                'display_name': 'Python 3.11.7 (64-bit)',
                'version': '3.11.7',
                'publisher': 'Python Software Foundation',
                'install_location': 'C:\\Python311',
                'uninstall_string': None,
                'registry_key': 'DEMO'
            },
        ]


class ProgramMatcher:
    """Matches installed programs to installer files."""
    
    def __init__(self):
        self.name_variations = {}
    
    def match(self, programs: List[Dict], installers: List[Dict]) -> List[Tuple[Dict, Optional[Dict]]]:
        """Match installed programs to their corresponding installers."""
        results = []
        
        for program in programs:
            best_match = self._find_best_match(program, installers)
            results.append((program, best_match))
        
        return results
    
    def _find_best_match(self, program: Dict, installers: List[Dict]) -> Optional[Dict]:
        """Find the best matching installer for a program."""
        program_name = (program.get('display_name') or program.get('name') or '').lower()
        program_name_clean = self._normalize_name(program_name)
        
        best_match = None
        best_score = 0
        
        for installer in installers:
            installer_name = (installer.get('detected_name') or '').lower()
            installer_name_clean = self._normalize_name(installer_name)
            
            score = self._calculate_match_score(program_name_clean, installer_name_clean)
            
            if score > best_score and score >= 0.6:
                best_score = score
                best_match = installer
        
        return best_match
    
    def _normalize_name(self, name: str) -> str:
        """Normalize program/installer name for comparison."""
        name = name.lower()
        name = re.sub(r'\(.*?\)', '', name)
        name = re.sub(r'\d+(\.\d+)*', '', name)
        name = re.sub(r'[^\w\s]', ' ', name)
        name = ' '.join(name.split())
        return name.strip()
    
    def _calculate_match_score(self, name1: str, name2: str) -> float:
        """Calculate similarity score between two names."""
        if not name1 or not name2:
            return 0.0
        
        if name1 == name2:
            return 1.0
        
        if name1 in name2 or name2 in name1:
            return 0.9
        
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
