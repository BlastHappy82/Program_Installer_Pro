"""
Main GUI module for the Installer Manager application.
Uses ttkbootstrap for a modern, professional look.
"""
import os
import sys
import threading
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox
from tkinter import filedialog
import tkinter as tk
from pathlib import Path
from typing import Optional, List, Dict, Callable

from .database import Database, InstallerStatus
from .scanner import InstallerScanner, InstalledProgramScanner, ProgramMatcher
from .installer import InstallationExecutor, InstallationQueue
from .launcher import StartupManager


def set_dark_title_bar(window):
    """Enable dark mode title bar on Windows 10/11."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        window.update()
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            hwnd = window.winfo_id()
        if hwnd:
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
            )
    except Exception:
        pass


class InstallerManagerGUI:
    """Main GUI application with modern ttkbootstrap styling."""
    
    def __init__(self, resume_mode: bool = False):
        self.root = ttk.Window(
            title="Installer Manager",
            themename="darkly",
            size=(1100, 750),
            minsize=(900, 650)
        )
        
        self._remove_icon()
        set_dark_title_bar(self.root)
        
        self.db = Database()
        self.executor = InstallationExecutor()
        self.startup_manager = StartupManager()
        
        self.installer_folder = self.db.get_setting('installer_folder', str(Path.home() / "Downloads"))
        self.include_subfolders = self.db.get_setting('include_subfolders', 'false') == 'true'
        
        self._create_menu()
        self._create_main_layout()
        
        if resume_mode:
            self._check_pending_installations()
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _create_menu(self):
        """Create application menu."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Set Installer Folder...", command=self._select_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Export Log (CSV)...", command=self._export_csv)
        file_menu.add_command(label="Export Log (JSON)...", command=self._export_json)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        
        self.subfolder_var = tk.BooleanVar(value=self.include_subfolders)
        settings_menu.add_checkbutton(
            label="Include Subfolders",
            variable=self.subfolder_var,
            command=self._toggle_subfolders
        )
        
        self.startup_var = tk.BooleanVar(value=self.startup_manager.is_registered())
        settings_menu.add_checkbutton(
            label="Start on Windows Login",
            variable=self.startup_var,
            command=self._toggle_startup
        )
        
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Dark Theme", command=lambda: self._change_theme("darkly"))
        view_menu.add_command(label="Light Theme", command=lambda: self._change_theme("flatly"))
        view_menu.add_command(label="Superhero Theme", command=lambda: self._change_theme("superhero"))
        view_menu.add_command(label="Cyborg Theme", command=lambda: self._change_theme("cyborg"))
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)
    
    def _change_theme(self, theme_name: str):
        """Change the application theme."""
        self.root.style.theme_use(theme_name)
        self.db.set_setting('theme', theme_name)
    
    def _remove_icon(self):
        """Remove the default window icon."""
        try:
            if sys.platform == 'win32':
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('')
            self.root.iconbitmap('')
        except Exception:
            try:
                empty_icon = tk.PhotoImage(width=1, height=1)
                self.root.iconphoto(True, empty_icon)
            except Exception:
                pass
    
    def _create_main_layout(self):
        """Create the main application layout."""
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=BOTH, expand=YES)
        
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=X, pady=(0, 15))
        
        title_label = ttk.Label(
            header_frame, 
            text="Installer Manager",
            font=("-size", 18, "-weight", "bold")
        )
        title_label.pack(side=LEFT, padx=(0, 20))
        
        folder_frame = ttk.Frame(header_frame)
        folder_frame.pack(side=RIGHT)
        
        ttk.Label(folder_frame, text="Folder:", font=("-size", 10)).pack(side=LEFT, padx=(0, 8))
        
        self.folder_var = tk.StringVar(value=self.installer_folder)
        folder_entry = ttk.Entry(
            folder_frame, 
            textvariable=self.folder_var, 
            width=45, 
            state='readonly',
            bootstyle="secondary"
        )
        folder_entry.pack(side=LEFT, padx=(0, 8))
        
        ttk.Button(
            folder_frame, 
            text="Browse",
            command=self._select_folder,
            bootstyle="outline"
        ).pack(side=LEFT)
        
        self.notebook = ttk.Notebook(main_frame, bootstyle="primary")
        self.notebook.pack(fill=BOTH, expand=YES, pady=(10, 10))
        
        self._create_installers_tab()
        self._create_installed_tab()
        self._create_queue_tab()
        
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=X, pady=(10, 0))
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            status_frame, 
            textvariable=self.status_var,
            font=("-size", 9),
            bootstyle="secondary"
        ).pack(side=LEFT)
        
        self.progress = ttk.Progressbar(
            status_frame, 
            mode='determinate', 
            length=250,
            bootstyle="success-striped"
        )
        self.progress.pack(side=RIGHT)
    
    def _create_installers_tab(self):
        """Create the Installers tab."""
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text="  Installers  ")
        
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=X, pady=(0, 15))
        
        ttk.Button(
            toolbar, 
            text="Scan Folder",
            command=self._scan_installers,
            bootstyle="success",
            width=14
        ).pack(side=LEFT, padx=(0, 8))
        
        ttk.Button(
            toolbar, 
            text="Add to Queue",
            command=self._add_selected_to_queue,
            bootstyle="info",
            width=14
        ).pack(side=LEFT)
        
        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill=BOTH, expand=YES)
        
        columns = ('name', 'version', 'type', 'size')
        self.installers_tree = ttk.Treeview(
            tree_frame, 
            columns=columns, 
            show='headings', 
            selectmode='extended',
            bootstyle="primary"
        )
        
        self.installers_tree.heading('name', text='Program Name', anchor=W)
        self.installers_tree.heading('version', text='Version', anchor=W)
        self.installers_tree.heading('type', text='Type', anchor=CENTER)
        self.installers_tree.heading('size', text='Size', anchor=E)
        
        self.installers_tree.column('name', width=350, minwidth=200)
        self.installers_tree.column('version', width=120, minwidth=80)
        self.installers_tree.column('type', width=80, minwidth=50, anchor=CENTER)
        self.installers_tree.column('size', width=100, minwidth=70, anchor=E)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.installers_tree.yview, bootstyle="primary-round")
        self.installers_tree.configure(yscrollcommand=scrollbar.set)
        
        self.installers_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        self.installers_tree.bind('<Double-1>', self._on_installer_double_click)
        self.installers_tree.bind('<Button-3>', self._show_installer_context_menu)
    
    def _create_installed_tab(self):
        """Create the Installed Programs tab."""
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text="  Installed Programs  ")
        
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=X, pady=(0, 15))
        
        ttk.Button(
            toolbar, 
            text="Scan Programs",
            command=self._scan_installed,
            bootstyle="info",
            width=14
        ).pack(side=LEFT, padx=(0, 15))
        
        ttk.Label(toolbar, text="Filter:", font=("-size", 10)).pack(side=LEFT, padx=(0, 5))
        
        self.installed_filter_var = tk.StringVar(value="All Programs")
        filter_combo = ttk.Combobox(
            toolbar,
            textvariable=self.installed_filter_var,
            values=["All Programs", "Without Installers", "With Installers", "Hidden", "Manually Linked"],
            state="readonly",
            width=18,
            bootstyle="secondary"
        )
        filter_combo.pack(side=LEFT, padx=(0, 15))
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_installed_list())
        
        ttk.Button(
            toolbar,
            text="Show Hidden",
            command=self._toggle_show_hidden,
            bootstyle="secondary-outline",
            width=12
        ).pack(side=LEFT)
        
        self.show_hidden = False
        
        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill=BOTH, expand=YES)
        
        columns = ('name', 'version', 'publisher', 'status')
        self.installed_tree = ttk.Treeview(
            tree_frame, 
            columns=columns, 
            show='headings', 
            selectmode='extended',
            bootstyle="secondary"
        )
        
        self.installed_tree.heading('name', text='Program Name', anchor=W)
        self.installed_tree.heading('version', text='Version', anchor=W)
        self.installed_tree.heading('publisher', text='Publisher', anchor=W)
        self.installed_tree.heading('status', text='Status', anchor=CENTER)
        
        self.installed_tree.column('name', width=350, minwidth=250)
        self.installed_tree.column('version', width=120, minwidth=80)
        self.installed_tree.column('publisher', width=200, minwidth=120)
        self.installed_tree.column('status', width=130, minwidth=100, anchor=CENTER)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.installed_tree.yview, bootstyle="secondary-round")
        self.installed_tree.configure(yscrollcommand=scrollbar.set)
        
        self.installed_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        self.installed_tree.bind('<Button-3>', self._show_installed_context_menu)
    
    def _create_queue_tab(self):
        """Create the Installation Queue tab."""
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text="  Installation Queue  ")
        
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=X, pady=(0, 15))
        
        ttk.Button(
            toolbar, 
            text="Start Installation",
            command=self._start_installation,
            bootstyle="success",
            width=16
        ).pack(side=LEFT, padx=(0, 8))
        
        ttk.Button(
            toolbar, 
            text="Pause",
            command=self._pause_installation,
            bootstyle="warning",
            width=10
        ).pack(side=LEFT, padx=(0, 8))
        
        ttk.Button(
            toolbar, 
            text="Clear Queue",
            command=self._clear_queue,
            bootstyle="danger-outline",
            width=12
        ).pack(side=LEFT, padx=(0, 20))
        
        ttk.Separator(toolbar, orient=VERTICAL).pack(side=LEFT, fill=Y, padx=10)
        
        ttk.Button(
            toolbar, 
            text="Move Up",
            command=self._move_queue_up,
            bootstyle="secondary-outline",
            width=10
        ).pack(side=LEFT, padx=(0, 5))
        
        ttk.Button(
            toolbar, 
            text="Move Down",
            command=self._move_queue_down,
            bootstyle="secondary-outline",
            width=10
        ).pack(side=LEFT, padx=(0, 5))
        
        ttk.Button(
            toolbar, 
            text="Remove",
            command=self._remove_from_queue,
            bootstyle="danger-outline",
            width=10
        ).pack(side=LEFT)
        
        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill=BOTH, expand=YES)
        
        columns = ('position', 'name', 'version', 'status', 'exit_code')
        self.queue_tree = ttk.Treeview(
            tree_frame, 
            columns=columns, 
            show='headings', 
            selectmode='browse',
            bootstyle="warning"
        )
        
        self.queue_tree.heading('position', text='#', anchor=CENTER)
        self.queue_tree.heading('name', text='Program Name', anchor=W)
        self.queue_tree.heading('version', text='Version', anchor=W)
        self.queue_tree.heading('status', text='Status', anchor=W)
        self.queue_tree.heading('exit_code', text='Exit Code', anchor=CENTER)
        
        self.queue_tree.column('position', width=50, minwidth=40, anchor=CENTER)
        self.queue_tree.column('name', width=320, minwidth=250)
        self.queue_tree.column('version', width=120, minwidth=80)
        self.queue_tree.column('status', width=150, minwidth=120)
        self.queue_tree.column('exit_code', width=100, minwidth=80, anchor=CENTER)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.queue_tree.yview, bootstyle="warning-round")
        self.queue_tree.configure(yscrollcommand=scrollbar.set)
        
        self.queue_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        info_frame = ttk.Labelframe(tab, text="Queue Summary", padding=15, bootstyle="info")
        info_frame.pack(fill=X, pady=(15, 0))
        
        self.queue_summary_var = tk.StringVar(value="No items in queue")
        ttk.Label(
            info_frame, 
            textvariable=self.queue_summary_var,
            font=("-size", 10)
        ).pack(side=LEFT)
    
    def _select_folder(self):
        """Open folder selection dialog."""
        folder = filedialog.askdirectory(
            title="Select Installer Folder",
            initialdir=self.installer_folder
        )
        if folder:
            self.installer_folder = folder
            self.folder_var.set(folder)
            self.db.set_setting('installer_folder', folder)
            self._scan_installers()
    
    def _toggle_subfolders(self):
        """Toggle subfolder scanning."""
        self.include_subfolders = self.subfolder_var.get()
        self.db.set_setting('include_subfolders', 'true' if self.include_subfolders else 'false')
    
    def _toggle_startup(self):
        """Toggle startup registration."""
        if self.startup_var.get():
            success = self.startup_manager.register_startup()
            if not success:
                self.startup_var.set(False)
                Messagebox.show_error("Failed to register startup entry", title="Error")
        else:
            self.startup_manager.unregister_startup()
    
    def _scan_installers(self):
        """Scan the installer folder."""
        self.status_var.set("Scanning installer folder...")
        self.progress.configure(mode='indeterminate')
        self.progress.start()
        
        def scan():
            scanner = InstallerScanner(self.installer_folder, self.include_subfolders)
            installers = scanner.scan()
            
            for item in self.installers_tree.get_children():
                self.installers_tree.delete(item)
            
            for installer in installers:
                self.db.add_installer(**installer)
                
                size_str = self._format_size(installer.get('file_size', 0))
                
                self.root.after(0, lambda i=installer, s=size_str: self.installers_tree.insert('', 'end', values=(
                    i.get('detected_name') or i.get('file_name'),
                    i.get('detected_version') or 'Unknown',
                    i.get('file_type', '').upper(),
                    s
                ), tags=(i.get('file_path'),)))
            
            self.root.after(0, lambda: self._finish_scan(len(installers)))
        
        threading.Thread(target=scan, daemon=True).start()
    
    def _finish_scan(self, count: int):
        """Finish scan and update UI."""
        self.progress.stop()
        self.progress.configure(mode='determinate')
        self.status_var.set(f"Found {count} installer(s)")
    
    def _scan_installed(self):
        """Scan for installed programs."""
        self.status_var.set("Scanning installed programs...")
        self.progress.configure(mode='indeterminate')
        self.progress.start()
        
        def scan():
            scanner = InstalledProgramScanner()
            programs = scanner.scan()
            
            self.db.clear_installed_programs()
            
            installers = self.db.get_all_installers()
            matcher = ProgramMatcher()
            matches = matcher.match(programs, installers)
            
            for item in self.installed_tree.get_children():
                self.installed_tree.delete(item)
            
            for program, matched_installer in matches:
                prog_id = self.db.add_installed_program(
                    name=program.get('name'),
                    display_name=program.get('display_name'),
                    version=program.get('version'),
                    publisher=program.get('publisher'),
                    install_location=program.get('install_location'),
                    uninstall_string=program.get('uninstall_string'),
                    registry_key=program.get('registry_key')
                )
                
                if matched_installer:
                    self.db.match_program_to_installer(prog_id, matched_installer['id'])
                
                has_installer = "Yes" if matched_installer else "No"
                action = "" if matched_installer else "Find Installer"
                
                self.root.after(0, lambda p=program, h=has_installer, a=action, m=matched_installer:
                    self.installed_tree.insert('', 'end', values=(
                        p.get('display_name') or p.get('name'),
                        p.get('version') or 'Unknown',
                        p.get('publisher') or 'Unknown',
                        h,
                        a
                    ), tags=(str(prog_id),)))
            
            self.root.after(0, lambda: self._finish_installed_scan(len(programs), len([m for _, m in matches if m])))
        
        threading.Thread(target=scan, daemon=True).start()
    
    def _finish_installed_scan(self, total: int, matched: int):
        """Finish installed programs scan."""
        self.progress.stop()
        self.progress.configure(mode='determinate')
        orphaned = total - matched
        self.status_var.set(f"Found {total} installed programs ({matched} have installers, {orphaned} missing)")
    
    def _refresh_installed_list(self):
        """Refresh the installed programs list based on filter."""
        filter_val = self.installed_filter_var.get()
        
        if filter_val == "Without Installers":
            programs = self.db.get_programs_without_installers()
        elif filter_val == "Hidden":
            programs = self.db.get_hidden_programs()
        elif filter_val == "Manually Linked":
            programs = self.db.get_manually_linked_programs()
        elif filter_val == "With Installers":
            programs = self.db.get_programs_with_installers()
        else:
            programs = self.db.get_all_installed_programs(include_hidden=self.show_hidden)
        
        for item in self.installed_tree.get_children():
            self.installed_tree.delete(item)
        
        for program in programs:
            if program.get('is_hidden'):
                status = "Hidden"
            elif program.get('manually_linked'):
                status = "Linked"
            elif program.get('has_installer'):
                status = "Has Installer"
            else:
                status = "No Installer"
            
            self.installed_tree.insert('', 'end', values=(
                program.get('display_name') or program.get('name'),
                program.get('version') or 'Unknown',
                program.get('publisher') or 'Unknown',
                status
            ), tags=(str(program['id']),))
    
    def _toggle_show_hidden(self):
        """Toggle showing hidden programs."""
        self.show_hidden = not self.show_hidden
        self._refresh_installed_list()
    
    def _show_installed_context_menu(self, event):
        """Show context menu for installed programs."""
        item = self.installed_tree.identify_row(event.y)
        if item:
            self.installed_tree.selection_set(item)
            
            menu = tk.Menu(self.root, tearoff=0)
            
            tags = self.installed_tree.item(item, 'tags')
            if tags:
                program_id = int(tags[0])
                program = self.db.get_installed_program(program_id)
                
                if program:
                    if program.get('is_hidden'):
                        menu.add_command(label="Unhide Program", command=lambda: self._unhide_program(program_id))
                    else:
                        menu.add_command(label="Hide Program", command=lambda: self._hide_program(program_id))
                    
                    menu.add_separator()
                    menu.add_command(label="Link to Installer...", command=lambda: self._link_to_installer(program_id))
                    
                    if program.get('manually_linked'):
                        menu.add_command(label="Remove Link", command=lambda: self._remove_installer_link(program_id))
                    
                    menu.add_separator()
                    menu.add_command(label="Set as Parent (Group)", command=lambda: self._set_as_parent(program_id))
                    
            menu.post(event.x_root, event.y_root)
    
    def _hide_program(self, program_id: int):
        """Hide a program from the list."""
        self.db.hide_program(program_id)
        self._refresh_installed_list()
        self.status_var.set("Program hidden")
    
    def _unhide_program(self, program_id: int):
        """Unhide a program."""
        self.db.unhide_program(program_id)
        self._refresh_installed_list()
        self.status_var.set("Program unhidden")
    
    def _link_to_installer(self, program_id: int):
        """Link a program to an installer file."""
        file_path = filedialog.askopenfilename(
            title="Select Installer File",
            initialdir=self.installer_folder,
            filetypes=[("Installer files", "*.exe *.msi"), ("All files", "*.*")]
        )
        
        if file_path:
            installer = self.db.get_installer_by_path(file_path)
            if not installer:
                from .scanner import InstallerScanner
                scanner = InstallerScanner(self.installer_folder, False)
                info = scanner._parse_installer_file(file_path)
                if info:
                    installer_id = self.db.add_installer(**info)
                    installer = self.db.get_installer(installer_id)
            
            if installer:
                self.db.link_program_to_installer(program_id, installer['id'])
                self._refresh_installed_list()
                self.status_var.set("Program linked to installer")
    
    def _remove_installer_link(self, program_id: int):
        """Remove installer link from a program."""
        self.db.unlink_program_from_installer(program_id)
        self._refresh_installed_list()
        self.status_var.set("Installer link removed")
    
    def _set_as_parent(self, program_id: int):
        """Set a program as parent for grouping related programs."""
        selected = self.installed_tree.selection()
        if len(selected) > 1:
            parent_id = program_id
            for item in selected:
                tags = self.installed_tree.item(item, 'tags')
                if tags:
                    child_id = int(tags[0])
                    if child_id != parent_id:
                        self.db.set_program_parent(child_id, parent_id)
            self._refresh_installed_list()
            self.status_var.set("Programs grouped")
        else:
            Messagebox.show_info("Select multiple programs first, then right-click the parent program", title="Info")
    
    def _add_selected_to_queue(self):
        """Add selected installers to the installation queue."""
        selected = self.installers_tree.selection()
        if not selected:
            Messagebox.show_info("Please select installers to add to queue", title="Info")
            return
        
        for item in selected:
            tags = self.installers_tree.item(item, 'tags')
            if tags:
                file_path = tags[0]
                installer = self.db.get_installer_by_path(file_path)
                if installer:
                    self.db.add_to_queue(installer['id'])
        
        self._refresh_queue()
        self.notebook.select(3)
        self.status_var.set(f"Added {len(selected)} installer(s) to queue")
    
    def _refresh_queue(self):
        """Refresh the installation queue display."""
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        
        queue = self.db.get_queue()
        
        pending = sum(1 for i in queue if i.get('status') == 'pending')
        completed = sum(1 for i in queue if i.get('status') == 'completed')
        failed = sum(1 for i in queue if i.get('status') == 'failed')
        needs_restart = sum(1 for i in queue if i.get('status') == 'needs_restart')
        
        for i, item in enumerate(queue):
            status = item.get('status', 'pending').replace('_', ' ').title()
            exit_code = item.get('exit_code') if item.get('exit_code') is not None else ''
            
            self.queue_tree.insert('', 'end', values=(
                i + 1,
                item.get('detected_name') or item.get('file_name'),
                item.get('detected_version') or 'Unknown',
                status,
                exit_code
            ), tags=(str(item['id']),))
        
        summary = f"Total: {len(queue)} | Pending: {pending} | Completed: {completed} | Failed: {failed}"
        if needs_restart:
            summary += f" | Needs Restart: {needs_restart}"
        self.queue_summary_var.set(summary)
    
    def _start_installation(self):
        """Start the installation queue."""
        queue = self.db.get_pending_queue_items()
        if not queue:
            Messagebox.show_info("No pending installations in queue", title="Info")
            return
        
        if not self.executor.check_elevation():
            if Messagebox.yesno(
                "Installing programs requires administrator privileges.\n\n"
                "Would you like to restart with elevated permissions?",
                title="Admin Required"
            ) == "Yes":
                self.executor.request_elevation()
            return
        
        self.status_var.set("Starting installations...")
        
        def install_loop():
            for item in queue:
                queue_id = item['id']
                file_path = item['file_path']
                name = item.get('detected_name') or item.get('file_name')
                
                self.root.after(0, lambda n=name: self.status_var.set(f"Installing: {n}"))
                self.db.update_queue_status(queue_id, 'installing')
                self.root.after(0, self._refresh_queue)
                
                result = self.executor.run_installer(file_path)
                
                if result.restart_required:
                    self.db.update_queue_status(queue_id, 'needs_restart', result.exit_code, restart_required=True)
                    
                    pending_ids = [i['id'] for i in queue if i['id'] != queue_id]
                    self.db.save_session_state(pending_ids, queue.index(item) + 1)
                    
                    self.root.after(0, lambda: self._prompt_restart(item))
                    return
                elif result.success:
                    self.db.update_queue_status(queue_id, 'completed', result.exit_code)
                else:
                    self.db.update_queue_status(queue_id, 'failed', result.exit_code, result.error_message)
                
                self.root.after(0, self._refresh_queue)
            
            self.db.clear_session_state()
            self.root.after(0, lambda: self.status_var.set("All installations complete"))
            self.root.after(0, lambda: Messagebox.show_info("All installations have been processed", title="Complete"))
        
        threading.Thread(target=install_loop, daemon=True).start()
    
    def _prompt_restart(self, item: Dict):
        """Prompt user about restart requirement."""
        name = item.get('detected_name') or item.get('file_name')
        pending = self.db.get_pending_queue_items()
        
        message = f"'{name}' requires a system restart.\n\n"
        message += f"You have {len(pending)} more installation(s) pending.\n\n"
        message += "What would you like to do?"
        
        result = Messagebox.yesno(message, title="Restart Required")
        self._refresh_queue()
    
    def _pause_installation(self):
        """Pause the installation queue."""
        self.status_var.set("Installation paused")
    
    def _clear_queue(self):
        """Clear the installation queue."""
        if Messagebox.yesno("Clear all items from the installation queue?", title="Confirm") == "Yes":
            self.db.clear_queue()
            self._refresh_queue()
            self.status_var.set("Queue cleared")
    
    def _move_queue_up(self):
        """Move selected item up in queue."""
        selected = self.queue_tree.selection()
        if selected:
            self._refresh_queue()
    
    def _move_queue_down(self):
        """Move selected item down in queue."""
        selected = self.queue_tree.selection()
        if selected:
            self._refresh_queue()
    
    def _remove_from_queue(self):
        """Remove selected item from queue."""
        selected = self.queue_tree.selection()
        if selected:
            self._refresh_queue()
    
    def _on_installer_double_click(self, event):
        """Handle double-click on installer."""
        item = self.installers_tree.selection()
        if item:
            self._add_selected_to_queue()
    
    def _show_installer_context_menu(self, event):
        """Show context menu for installers."""
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Add to Queue", command=self._add_selected_to_queue)
        menu.add_separator()
        menu.add_command(label="Open Folder", command=lambda: os.startfile(self.installer_folder) if os.name == 'nt' else None)
        menu.post(event.x_root, event.y_root)
    
    def _check_pending_installations(self):
        """Check for pending installations on startup."""
        pending = self.db.get_pending_queue_items()
        if pending:
            self._refresh_queue()
            self.notebook.select(3)
            
            if Messagebox.yesno(
                f"You have {len(pending)} pending installation(s).\n\n"
                "Would you like to continue the installation process?",
                title="Resume Installation"
            ) == "Yes":
                self._start_installation()
    
    def _export_csv(self):
        """Export installation log to CSV."""
        from datetime import datetime
        import csv
        
        filename = filedialog.asksaveasfilename(
            title="Export as CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"install_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        if filename:
            queue = self.db.get_queue()
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['name', 'version', 'status', 'exit_code', 'file_path'])
                writer.writeheader()
                for item in queue:
                    writer.writerow({
                        'name': item.get('detected_name') or item.get('file_name'),
                        'version': item.get('detected_version'),
                        'status': item.get('status'),
                        'exit_code': item.get('exit_code'),
                        'file_path': item.get('file_path')
                    })
            
            self.status_var.set(f"Exported to {filename}")
    
    def _export_json(self):
        """Export installation log to JSON."""
        from datetime import datetime
        import json
        
        filename = filedialog.asksaveasfilename(
            title="Export as JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile=f"install_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        if filename:
            queue = self.db.get_queue()
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(queue, f, indent=2, default=str)
            
            self.status_var.set(f"Exported to {filename}")
    
    def _format_size(self, size: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def _show_about(self):
        """Show about dialog."""
        Messagebox.show_info(
            "Installer Manager v1.0\n\n"
            "A modern Python application for managing software installers.\n\n"
            "Features:\n"
            "• Scan and track installer files\n"
            "• Check for and download updates\n"
            "• Detect installed programs\n"
            "• Queue and run installations\n"
            "• Resume after restart\n\n"
            "Themes available in View menu",
            title="About Installer Manager"
        )
    
    def _on_close(self):
        """Handle application close."""
        pending = self.db.get_pending_queue_items()
        if pending:
            if Messagebox.yesno(
                f"You have {len(pending)} pending installation(s).\n"
                "Are you sure you want to exit?",
                title="Confirm Exit"
            ) != "Yes":
                return
        
        self.db.close()
        self.root.destroy()
    
    def run(self):
        """Start the application."""
        self.root.mainloop()
