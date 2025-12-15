"""
Update checker module for finding newer versions of installers.
Uses Winget manifests and known software update sources.
"""
import re
import json
import requests
from typing import Dict, Optional, List
from packaging import version as pkg_version
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UpdateChecker:
    """Checks for updates for known software packages."""
    
    WINGET_MANIFEST_URL = "https://raw.githubusercontent.com/microsoft/winget-pkgs/master/manifests"
    
    KNOWN_SOFTWARE = {
        'chrome': {
            'winget_id': 'Google.Chrome',
            'name_patterns': ['chrome', 'google chrome'],
        },
        'firefox': {
            'winget_id': 'Mozilla.Firefox',
            'name_patterns': ['firefox', 'mozilla firefox'],
        },
        '7zip': {
            'winget_id': 'Igor Pavlov.7-Zip',
            'name_patterns': ['7-zip', '7zip', '7 zip'],
        },
        'vlc': {
            'winget_id': 'VideoLAN.VLC',
            'name_patterns': ['vlc', 'vlc media player', 'videolan'],
        },
        'notepadpp': {
            'winget_id': 'Notepad++.Notepad++',
            'name_patterns': ['notepad++', 'notepad plus', 'npp'],
        },
        'vscode': {
            'winget_id': 'Microsoft.VisualStudioCode',
            'name_patterns': ['visual studio code', 'vscode', 'vs code'],
        },
        'git': {
            'winget_id': 'Git.Git',
            'name_patterns': ['git for windows', 'git'],
        },
        'python': {
            'winget_id': 'Python.Python.3.12',
            'name_patterns': ['python'],
        },
        'nodejs': {
            'winget_id': 'OpenJS.NodeJS.LTS',
            'name_patterns': ['node', 'nodejs', 'node.js'],
        },
        'putty': {
            'winget_id': 'PuTTY.PuTTY',
            'name_patterns': ['putty'],
        },
        'winscp': {
            'winget_id': 'WinSCP.WinSCP',
            'name_patterns': ['winscp'],
        },
        'filezilla': {
            'winget_id': 'TimKosse.FileZilla.Client',
            'name_patterns': ['filezilla'],
        },
    }
    
    DIRECT_SOURCES = {
        'chrome': {
            'version_url': 'https://chromiumdash.appspot.com/fetch_releases?channel=Stable&platform=Windows',
            'download_url': 'https://dl.google.com/chrome/install/latest/chrome_installer.exe',
        },
        '7zip': {
            'version_url': 'https://www.7-zip.org/',
            'download_pattern': r'https://www\.7-zip\.org/a/7z(\d+)-x64\.exe',
        },
    }
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'InstallerManager/1.0'
        })
    
    def check_update(self, detected_name: Optional[str], current_version: Optional[str] = None) -> Dict:
        """
        Check if an update is available for the given software.
        Returns dict with: status, latest_version, download_url
        """
        software_key = self._identify_software(detected_name)
        
        if not software_key:
            return {
                'status': 'unknown',
                'latest_version': None,
                'download_url': None,
                'message': 'Software not recognized in update database'
            }
        
        latest_info = self._get_latest_version(software_key)
        
        if not latest_info or not latest_info.get('version'):
            return {
                'status': 'update_not_found',
                'latest_version': None,
                'download_url': None,
                'message': 'Could not retrieve latest version information'
            }
        
        latest_version = latest_info['version']
        download_url = latest_info.get('download_url')
        
        if current_version:
            comparison = self._compare_versions(current_version, latest_version)
            if comparison >= 0:
                return {
                    'status': 'up_to_date',
                    'latest_version': latest_version,
                    'download_url': download_url,
                    'message': 'Installer is up to date'
                }
            else:
                return {
                    'status': 'update_available',
                    'latest_version': latest_version,
                    'download_url': download_url,
                    'message': f'Update available: {current_version} → {latest_version}'
                }
        else:
            return {
                'status': 'update_available',
                'latest_version': latest_version,
                'download_url': download_url,
                'message': f'Latest version: {latest_version}'
            }
    
    def _identify_software(self, name: str) -> Optional[str]:
        """Identify which known software matches the given name."""
        if not name:
            return None
        
        name_lower = name.lower().strip()
        
        for key, info in self.KNOWN_SOFTWARE.items():
            for pattern in info['name_patterns']:
                if pattern in name_lower or name_lower in pattern:
                    return key
        
        return None
    
    def _get_latest_version(self, software_key: str) -> Optional[Dict]:
        """Get the latest version info for a software package."""
        if software_key in self.DIRECT_SOURCES:
            result = self._check_direct_source(software_key)
            if result:
                return result
        
        return self._check_winget_api(software_key)
    
    def _check_direct_source(self, software_key: str) -> Optional[Dict]:
        """Check direct update sources for version info."""
        source = self.DIRECT_SOURCES.get(software_key)
        if not source:
            return None
        
        try:
            if software_key == 'chrome':
                resp = self.session.get(source['version_url'], timeout=self.timeout)
                data = resp.json()
                if data and len(data) > 0:
                    version = data[0].get('version')
                    return {
                        'version': version,
                        'download_url': source['download_url']
                    }
            
            elif software_key == '7zip':
                resp = self.session.get(source['version_url'], timeout=self.timeout)
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    match = re.search(source['download_pattern'], href)
                    if match:
                        version_num = match.group(1)
                        version = f"{version_num[0:2]}.{version_num[2:]}" if len(version_num) > 2 else version_num
                        return {
                            'version': version,
                            'download_url': urljoin(source['version_url'], href)
                        }
        
        except Exception as e:
            logger.debug(f"Direct source check failed for {software_key}: {e}")
        
        return None
    
    def _check_winget_api(self, software_key: str) -> Optional[Dict]:
        """Check Winget community API for version info."""
        software_info = self.KNOWN_SOFTWARE.get(software_key)
        if not software_info:
            return None
        
        winget_id = software_info.get('winget_id')
        if not winget_id:
            return None
        
        try:
            api_url = f"https://api.winget.run/v2/packages/{winget_id}"
            resp = self.session.get(api_url, timeout=self.timeout)
            
            if resp.status_code == 200:
                data = resp.json()
                versions = data.get('Versions', [])
                if versions:
                    latest = versions[0]
                    return {
                        'version': latest.get('Version'),
                        'download_url': latest.get('Installers', [{}])[0].get('InstallerUrl')
                    }
        except Exception as e:
            logger.debug(f"Winget API check failed for {software_key}: {e}")
        
        return self._get_fallback_version(software_key)
    
    def _get_fallback_version(self, software_key: str) -> Optional[Dict]:
        """Return fallback version data for demo/offline mode."""
        fallback_data = {
            'chrome': {'version': '120.0.6099.130', 'download_url': 'https://dl.google.com/chrome/install/latest/chrome_installer.exe'},
            'firefox': {'version': '121.0', 'download_url': 'https://download.mozilla.org/?product=firefox-latest&os=win64&lang=en-US'},
            '7zip': {'version': '23.01', 'download_url': 'https://www.7-zip.org/a/7z2301-x64.exe'},
            'vlc': {'version': '3.0.20', 'download_url': 'https://get.videolan.org/vlc/3.0.20/win64/vlc-3.0.20-win64.exe'},
            'notepadpp': {'version': '8.6', 'download_url': 'https://github.com/notepad-plus-plus/notepad-plus-plus/releases/download/v8.6/npp.8.6.Installer.x64.exe'},
            'vscode': {'version': '1.85.0', 'download_url': 'https://code.visualstudio.com/sha/download?build=stable&os=win32-x64'},
            'git': {'version': '2.43.0', 'download_url': 'https://github.com/git-for-windows/git/releases/download/v2.43.0.windows.1/Git-2.43.0-64-bit.exe'},
            'python': {'version': '3.12.1', 'download_url': 'https://www.python.org/ftp/python/3.12.1/python-3.12.1-amd64.exe'},
            'nodejs': {'version': '20.10.0', 'download_url': 'https://nodejs.org/dist/v20.10.0/node-v20.10.0-x64.msi'},
            'putty': {'version': '0.80', 'download_url': 'https://the.earth.li/~sgtatham/putty/latest/w64/putty-64bit-0.80-installer.msi'},
            'winscp': {'version': '6.1.2', 'download_url': 'https://winscp.net/download/WinSCP-6.1.2-Setup.exe'},
            'filezilla': {'version': '3.66.1', 'download_url': 'https://download.filezilla-project.org/client/FileZilla_3.66.1_win64_sponsored2-setup.exe'},
        }
        return fallback_data.get(software_key)
    
    def _compare_versions(self, version1: str, version2: str) -> int:
        """
        Compare two version strings.
        Returns: -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2
        """
        try:
            v1 = pkg_version.parse(version1)
            v2 = pkg_version.parse(version2)
            
            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1
            else:
                return 0
        except Exception:
            if version1 == version2:
                return 0
            return -1 if version1 < version2 else 1
    
    def get_all_known_software(self) -> List[Dict]:
        """Get list of all software that can be checked for updates."""
        result = []
        for key, info in self.KNOWN_SOFTWARE.items():
            result.append({
                'key': key,
                'winget_id': info.get('winget_id'),
                'name_patterns': info['name_patterns']
            })
        return result
    
    def check_multiple(self, installers: List[Dict], progress_callback=None) -> List[Dict]:
        """Check updates for multiple installers with optional progress callback."""
        results = []
        total = len(installers)
        
        for i, installer in enumerate(installers):
            name = installer.get('detected_name', '')
            version = installer.get('detected_version')
            
            update_info = self.check_update(name, version)
            update_info['installer'] = installer
            results.append(update_info)
            
            if progress_callback:
                progress_callback(i + 1, total, installer.get('file_name', ''))
        
        return results
