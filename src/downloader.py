"""
Download manager for fetching updated installers.
"""
import os
import hashlib
import threading
import requests
from pathlib import Path
from typing import Optional, Callable, Dict, Union
from urllib.parse import urlparse, unquote
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DownloadManager:
    """Manages downloads with progress tracking and resume capability."""
    
    def __init__(self, download_folder: str = None):
        if download_folder:
            self.download_folder = Path(download_folder)
        else:
            self.download_folder = Path.home() / "Downloads" / "InstallerManager"
        
        self.download_folder.mkdir(parents=True, exist_ok=True)
        self.active_downloads: Dict[int, threading.Thread] = {}
        self.cancelled: Dict[int, bool] = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'InstallerManager/1.0 (Windows)'
        })
    
    def download(self, url: str, filename: str = None, 
                 progress_callback: Callable[[int, int, float], None] = None,
                 complete_callback: Callable[[bool, str, str], None] = None,
                 download_id: int = None) -> Optional[str]:
        """
        Download a file from URL.
        
        Args:
            url: Download URL
            filename: Target filename (auto-detected if None)
            progress_callback: Called with (bytes_downloaded, total_bytes, percentage)
            complete_callback: Called with (success, file_path, error_message)
            download_id: Optional ID for tracking/cancellation
        
        Returns:
            File path on success, None on failure
        """
        if download_id is not None:
            self.cancelled[download_id] = False
        
        try:
            if not filename:
                filename = self._extract_filename(url)
            
            file_path = self.download_folder / filename
            temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
            
            response = self.session.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if download_id is not None and self.cancelled.get(download_id):
                        temp_path.unlink(missing_ok=True)
                        if complete_callback:
                            complete_callback(False, None, "Download cancelled")
                        return None
                    
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback:
                            percentage = (downloaded / total_size * 100) if total_size > 0 else 0
                            progress_callback(downloaded, total_size, percentage)
            
            if file_path.exists():
                file_path.unlink()
            temp_path.rename(file_path)
            
            logger.info(f"Download complete: {file_path}")
            
            if complete_callback:
                complete_callback(True, str(file_path), None)
            
            return str(file_path)
        
        except requests.exceptions.RequestException as e:
            error_msg = f"Download failed: {str(e)}"
            logger.error(error_msg)
            
            if complete_callback:
                complete_callback(False, None, error_msg)
            
            return None
        
        except Exception as e:
            error_msg = f"Download error: {str(e)}"
            logger.error(error_msg)
            
            if complete_callback:
                complete_callback(False, None, error_msg)
            
            return None
    
    def download_async(self, url: str, filename: str = None,
                       progress_callback: Callable[[int, int, float], None] = None,
                       complete_callback: Callable[[bool, str, str], None] = None,
                       download_id: int = None) -> int:
        """
        Start download in background thread.
        Returns download ID for tracking/cancellation.
        """
        if download_id is None:
            download_id = id(url)
        
        thread = threading.Thread(
            target=self.download,
            args=(url, filename, progress_callback, complete_callback, download_id),
            daemon=True
        )
        
        self.active_downloads[download_id] = thread
        thread.start()
        
        return download_id
    
    def cancel_download(self, download_id: int):
        """Cancel an active download."""
        self.cancelled[download_id] = True
    
    def is_downloading(self, download_id: int) -> bool:
        """Check if a download is still active."""
        thread = self.active_downloads.get(download_id)
        return thread is not None and thread.is_alive()
    
    def _extract_filename(self, url: str) -> str:
        """Extract filename from URL."""
        parsed = urlparse(url)
        path = unquote(parsed.path)
        
        if path and '/' in path:
            filename = path.split('/')[-1]
            if filename:
                return filename
        
        return "installer.exe"
    
    def verify_checksum(self, file_path: str, expected_hash: str, 
                        algorithm: str = 'sha256') -> bool:
        """Verify file checksum."""
        hash_obj = hashlib.new(algorithm)
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hash_obj.update(chunk)
        
        actual_hash = hash_obj.hexdigest().lower()
        return actual_hash == expected_hash.lower()
    
    def get_file_size(self, url: str) -> Optional[int]:
        """Get file size from URL without downloading."""
        try:
            response = self.session.head(url, timeout=10, allow_redirects=True)
            return int(response.headers.get('content-length', 0))
        except Exception:
            return None
    
    def set_download_folder(self, folder: Optional[str]):
        """Change download folder."""
        if folder:
            self.download_folder = Path(folder)
            self.download_folder.mkdir(parents=True, exist_ok=True)


class BatchDownloader:
    """Handles batch downloads with queue management."""
    
    def __init__(self, download_manager: DownloadManager, max_concurrent: int = 3):
        self.manager = download_manager
        self.max_concurrent = max_concurrent
        self.queue = []
        self.active = []
        self.completed = []
        self.failed = []
        self._lock = threading.Lock()
    
    def add_to_queue(self, url: str, filename: str = None, 
                     installer_id: int = None) -> int:
        """Add a download to the queue. Returns queue position."""
        item = {
            'url': url,
            'filename': filename,
            'installer_id': installer_id,
            'status': 'queued'
        }
        
        with self._lock:
            self.queue.append(item)
            return len(self.queue) - 1
    
    def start(self, progress_callback: Callable = None, 
              complete_callback: Callable = None):
        """Start processing the download queue."""
        
        def process_queue():
            while self.queue or self.active:
                with self._lock:
                    while len(self.active) < self.max_concurrent and self.queue:
                        item = self.queue.pop(0)
                        item['status'] = 'downloading'
                        self.active.append(item)
                        
                        def on_complete(success, path, error, item=item):
                            with self._lock:
                                self.active.remove(item)
                                if success:
                                    item['file_path'] = path
                                    item['status'] = 'completed'
                                    self.completed.append(item)
                                else:
                                    item['error'] = error
                                    item['status'] = 'failed'
                                    self.failed.append(item)
                            
                            if complete_callback:
                                complete_callback(item)
                        
                        self.manager.download_async(
                            item['url'],
                            item['filename'],
                            progress_callback=progress_callback,
                            complete_callback=on_complete
                        )
        
        thread = threading.Thread(target=process_queue, daemon=True)
        thread.start()
        return thread
    
    def get_status(self) -> Dict:
        """Get current queue status."""
        with self._lock:
            return {
                'queued': len(self.queue),
                'active': len(self.active),
                'completed': len(self.completed),
                'failed': len(self.failed),
                'total': len(self.queue) + len(self.active) + len(self.completed) + len(self.failed)
            }
