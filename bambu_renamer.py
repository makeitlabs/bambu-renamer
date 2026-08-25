"""
Bambu 3MF Naming Convention Enforcer
======================================
Drag a .3mf file onto this executable (or pass it as a command-line arg).

Naming convention: <word(s)>_<word(s)>-<word(s)>
  Examples:  john_smith-benchy.3mf
             jane_doe-miniature_dragon.3mf

Build to EXE:
    pip install pyinstaller
    pyinstaller --onefile --windowed --icon=bambu.ico bambu_rename.py
    (drop --icon flag if you don't have an icon file)
"""

import sys
import os
import re
import zipfile
import shutil
import logging
import tempfile
import subprocess
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

# ─────────────────────────────────────────────────────────────────────────────
# Logging setup  (log file sits next to the EXE / script)
# ─────────────────────────────────────────────────────────────────────────────

def get_log_path() -> Path:
    """Return log path next to the executable (or script when developing)."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    return base / "bambu_rename.log"

logging.basicConfig(
    filename=get_log_path(),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bambu_rename")

# ─────────────────────────────────────────────────────────────────────────────
# Naming convention
#   Pattern: one-or-more word chars, underscore, one-or-more word chars,
#            hyphen, one-or-more word chars  (words may themselves contain _)
#   Essentially:  <stuff with underscores>-<stuff with underscores>
# ─────────────────────────────────────────────────────────────────────────────

NAMING_RE = re.compile(
    r"^"
    r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+"   # two+ segments separated by _
    r"-"                                   # required hyphen separator
    r"[A-Za-z0-9][A-Za-z0-9_]*"           # one+ segments after hyphen
    r"$",
    re.IGNORECASE,
)


def name_ok(stem: str) -> bool:
    """Return True if the filename stem matches the naming convention."""
    return bool(NAMING_RE.match(stem))


# ─────────────────────────────────────────────────────────────────────────────
# 3MF helpers
#
# Two things control what Bambu Studio shows as the project name:
#   1. The filesystem filename  →  shown as {input_filename_base} in gcode output
#   2. 3D/3dmodel.model  →  <metadata name="Title">VALUE</metadata>
#      This is what Bambu Studio shows in the title bar and print dialog.
#
# We update BOTH to firstname_lastname-<original_filename_stem>.
# ─────────────────────────────────────────────────────────────────────────────

def read_3mf_title(path: Path) -> str | None:
    """Read the <metadata name="Title"> value from 3D/3dmodel.model."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            if "3D/3dmodel.model" in zf.namelist():
                raw = zf.read("3D/3dmodel.model").decode("utf-8", errors="replace")
                m = re.search(r'<metadata name="Title">([^<]*)</metadata>', raw)
                return m.group(1).strip() if m else None
    except Exception as e:
        log.warning(f"Could not read 3MF Title metadata: {e}")
    return None


def update_3mf_metadata(src: Path, dst: Path, new_title: str):
    """
    Rewrite the 3MF archive from src to dst with these changes to 3D/3dmodel.model:
      - Title           → new_title   (shown in Bambu Studio title bar)
      - DesignModelId   → ""          (clears MakerWorld cloud ID so Bambu's
      - DesignProfileId → ""           Print History uses Title, not the
                                       original MakerWorld listing name)
    All other files are copied unchanged.
    """
    CLEAR_FIELDS = {"DesignModelId", "DesignProfileId"}
    with zipfile.ZipFile(src, "r") as zin, \
         zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "3D/3dmodel.model":
                text = data.decode("utf-8", errors="replace")
                # Update Title
                text = re.sub(
                    r'(<metadata name="Title"[^>]*>)[^<]*(</metadata>)',
                    lambda m: m.group(1) + new_title + m.group(2),
                    text
                )
                # Clear MakerWorld IDs so the cloud cannot override with the
                # original listing name in Print History
                for field in CLEAR_FIELDS:
                    text = re.sub(
                        rf'(<metadata name="{field}">)[^<]*(</metadata>)',
                        lambda m: m.group(1) + m.group(2),
                        text
                    )
                data = text.encode("utf-8")
            zout.writestr(item, data)


# ─────────────────────────────────────────────────────────────────────────────
# GUI — theme colours & fonts
# ─────────────────────────────────────────────────────────────────────────────

BG          = "#1A1A2E"   # deep navy
CARD        = "#16213E"
ACCENT      = "#0F3460"
GREEN       = "#00C896"
RED         = "#E94560"
TEXT        = "#E0E0F0"
TEXT_DIM    = "#8888AA"
FONT_TITLE  = ("Segoe UI Semibold", 16)
FONT_BODY   = ("Segoe UI", 11)
FONT_SMALL  = ("Segoe UI", 9)
FONT_MONO   = ("Consolas", 10)
FONT_BIG    = ("Segoe UI Semibold", 48)


def _style_entry(e: tk.Entry):
    e.configure(
        bg=ACCENT, fg=TEXT, insertbackground=TEXT,
        relief="flat", font=FONT_BODY,
        highlightthickness=1, highlightcolor=GREEN, highlightbackground=TEXT_DIM,
    )


def _style_button(b: tk.Button, color=GREEN, fg=BG):
    b.configure(
        bg=color, fg=fg, activebackground=color, activeforeground=fg,
        relief="flat", font=("Segoe UI Semibold", 11),
        cursor="hand2", padx=16, pady=8,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dialog: file already OK
# ─────────────────────────────────────────────────────────────────────────────

class OKDialog(tk.Toplevel):
    def __init__(self, master, filename: str):
        super().__init__(master)
        self.title("Naming Check — OK")
        self.configure(bg=BG)
        self.resizable(False, False)
        self._center(500, 320)

        # Big green checkmark
        tk.Label(self, text="✔", font=("Segoe UI", 80), fg=GREEN, bg=BG).pack(pady=(30, 0))

        # Message
        short = Path(filename).name
        tk.Label(
            self,
            text=f'"{short}"\nmeets naming requirements.\n\nYou can print it.',
            font=("Segoe UI Semibold", 13),
            fg=TEXT, bg=BG,
            justify="center",
        ).pack(pady=12)

        btn = tk.Button(self, text="Close", command=self.destroy)
        _style_button(btn, color=GREEN)
        btn.pack(pady=(0, 28))

        self.grab_set()
        self.wait_window()

    def _center(self, w, h):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")


# ─────────────────────────────────────────────────────────────────────────────
# Dialog: rename needed
# ─────────────────────────────────────────────────────────────────────────────

class RenameDialog(tk.Toplevel):
    def __init__(self, master, file_path: Path, issues: list[str]):
        super().__init__(master)
        self.title("Naming Convention Required")
        self.configure(bg=BG)
        self.resizable(False, False)
        self._center(520, 460)

        self.file_path = file_path
        self.result    = None   # Will be set to new Path on success

        # ── header ──────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=RED, padx=20, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚠  Naming Convention Required",
                 font=FONT_TITLE, fg="white", bg=RED).pack(anchor="w")

        # ── issues list ─────────────────────────────────────────────────────
        body = tk.Frame(self, bg=BG, padx=24, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Issues found:", font=("Segoe UI Semibold", 10),
                 fg=TEXT_DIM, bg=BG).pack(anchor="w")
        for iss in issues:
            tk.Label(body, text=f"  • {iss}", font=FONT_SMALL,
                     fg=RED, bg=BG).pack(anchor="w")

        tk.Label(body,
                 text="\nEnter your name to prepend to the filename.\n"
                      "Format will be:  Firstname_Lastname-<original name>",
                 font=FONT_BODY, fg=TEXT_DIM, bg=BG, justify="left").pack(anchor="w")

        # ── entry fields ────────────────────────────────────────────────────
        fields = tk.Frame(body, bg=BG)
        fields.pack(fill="x", pady=(12, 0))

        tk.Label(fields, text="Firstname", font=FONT_BODY, fg=TEXT, bg=BG).grid(
            row=0, column=0, sticky="w", pady=4)
        self.first_var = tk.StringVar()
        self.first_entry = tk.Entry(fields, textvariable=self.first_var, width=22)
        _style_entry(self.first_entry)
        self.first_entry.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=4)

        tk.Label(fields, text="Lastname", font=FONT_BODY, fg=TEXT, bg=BG).grid(
            row=1, column=0, sticky="w", pady=4)
        self.last_var = tk.StringVar()
        self.last_entry = tk.Entry(fields, textvariable=self.last_var, width=22)
        _style_entry(self.last_entry)
        self.last_entry.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=4)

        # Personal filament checkbox
        self.personal_filament_var = tk.BooleanVar(value=False)
        personal_filament_cb = tk.Checkbutton(
            fields, text="Personal filament", variable=self.personal_filament_var,
            command=self._on_change, font=FONT_BODY, fg=TEXT, bg=BG,
            activeforeground=TEXT, activebackground=BG, selectcolor=ACCENT,
            cursor="hand2"
        )
        personal_filament_cb.grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(6, 4))

        fields.columnconfigure(1, weight=1)

        # Preview label
        self.preview_var = tk.StringVar(value="")
        tk.Label(body, textvariable=self.preview_var, font=FONT_MONO,
                 fg=GREEN, bg=BG, wraplength=460).pack(anchor="w", pady=(8, 0))

        # ── rename button ────────────────────────────────────────────────────
        self.rename_btn = tk.Button(body, text="Rename My File",
                                    command=self._do_rename, state="disabled")
        _style_button(self.rename_btn)
        self.rename_btn.pack(pady=(16, 4), anchor="w")

        tk.Button(body, text="Cancel", command=self.destroy,
                  bg=CARD, fg=TEXT_DIM, relief="flat", font=FONT_BODY,
                  cursor="hand2", padx=12, pady=6).pack(anchor="w")

        # Bind traces
        self.first_var.trace_add("write", self._on_change)
        self.last_var.trace_add("write",  self._on_change)
        self.first_entry.focus_set()

        self.grab_set()
        self.wait_window()

    # ── helpers ─────────────────────────────────────────────────────────────

    def _sanitize(self, s: str) -> str:
        """Keep only alphanumeric and underscores."""
        return re.sub(r"[^A-Za-z0-9_]", "", s.strip())

    def _proposed_stem(self) -> str | None:
        first = self._sanitize(self.first_var.get())
        last  = self._sanitize(self.last_var.get())
        if not first or not last:
            return None
        old_stem = self.file_path.stem
        suffix = "_P" if self.personal_filament_var.get() else ""
        return f"{first}_{last}-{old_stem}{suffix}"

    def _on_change(self, *_):
        stem = self._proposed_stem()
        if stem:
            self.rename_btn.configure(state="normal")
            self.preview_var.set(f"→ {stem}.3mf")
        else:
            self.rename_btn.configure(state="disabled")
            self.preview_var.set("")

    def _do_rename(self):
        new_stem = self._proposed_stem()
        if not new_stem:
            return

        orig_path        = self.file_path
        initial_filename = orig_path.name
        original_title   = read_3mf_title(orig_path)
        new_path         = orig_path.parent / f"{new_stem}.3mf"

        # Step 1: rewrite the archive with updated Title metadata → temp file
        import tempfile
        try:
            tmp_fd, tmp_str = tempfile.mkstemp(suffix=".3mf", dir=orig_path.parent)
            import os; os.close(tmp_fd)
            tmp_path = Path(tmp_str)
            update_3mf_metadata(orig_path, tmp_path, new_stem)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update file contents:\n{e}", parent=self)
            log.error(f"Title update failed: {e}")
            if tmp_path.exists(): tmp_path.unlink()
            return

        # Step 2: replace original with rewritten archive, renamed
        try:
            orig_path.unlink()
            tmp_path.rename(new_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to rename file:\n{e}", parent=self)
            log.error(f"File rename failed: {e}")
            return

        log.info(
            f"RENAMED | scope=filename+Title | "
            f"original_filename={initial_filename} | "
            f"original_title={repr(original_title)} | "
            f"new_filename={new_path.name} | "
            f"new_title={new_stem}"
        )

        self.result = new_path
        self.destroy()

        messagebox.showinfo(
            "File Renamed — Action Required",
            f'File saved as:\n\n  {new_path.name}\n\n'
            f'Please:\n'
            f'  1. Close Bambu Studio if it is open\n'
            f'  2. Reopen the renamed file:\n     {new_path}\n\n'
            f'Then you can proceed with printing.',
        )

    def _center(self, w, h):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")


# ─────────────────────────────────────────────────────────────────────────────
# Main logic
# ─────────────────────────────────────────────────────────────────────────────

def process_file(file_path: Path):
    log.info(f"Processing: {file_path}")

    if not file_path.exists():
        messagebox.showerror("File Not Found", f"Cannot find:\n{file_path}")
        return

    if file_path.suffix.lower() != ".3mf":
        messagebox.showerror("Wrong File Type",
                             f'Expected a .3mf file.\nGot: "{file_path.name}"')
        return

    issues = []

    # Check the filesystem filename
    file_stem = file_path.stem
    if not name_ok(file_stem):
        issues.append(f'Filename "{file_path.name}" does not match the required pattern')

    # Check the Title metadata inside the archive (shown in Bambu Studio title bar)
    internal_title = read_3mf_title(file_path)
    if internal_title and not name_ok(internal_title):
        issues.append(f'Internal Title "{internal_title}" does not match the required pattern')

    # ── all good ─────────────────────────────────────────────────────────────
    if not issues:
        log.info(f"PASS | {file_path.name} | filename and Title OK")
        root = tk.Tk()
        root.withdraw()
        root.configure(bg=BG)
        OKDialog(root, str(file_path))
        root.destroy()
        return

    # ── needs rename ─────────────────────────────────────────────────────────
    log.info(f"FAIL | {file_path.name} | issues: {issues}")
    root = tk.Tk()
    root.withdraw()
    root.configure(bg=BG)
    dlg = RenameDialog(root, file_path, issues)
    root.destroy()


def main():
    if len(sys.argv) < 2:
        # No file dragged — show usage hint
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            "Bambu 3MF Renamer",
            "Drag and drop a Bambu .3mf file onto this executable to check "
            "or enforce the naming convention.\n\n"
            "Required format:\n"
            "  firstname_lastname-projectname.3mf\n\n"
            f"Log file: {get_log_path()}",
        )
        root.destroy()
        return

    file_path = Path(sys.argv[1])
    process_file(file_path)


if __name__ == "__main__":
    main()
