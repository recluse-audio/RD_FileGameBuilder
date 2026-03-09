import os
import tkinter as tk
from tkinter import filedialog

from . import HAS_DND

if HAS_DND:
    from tkinterdnd2 import DND_FILES


class NewSceneDialog(tk.Toplevel):
    """
    Modal dialog to create a new scene.
    Supports Browse buttons and (if tkinterdnd2 is installed) drag-and-drop
    of .md / .png files onto the dialog.

    result dict keys after OK:
      name, md, md_source, png, png_source
    *_source is the full path of an existing file to copy (None = create blank).
    """

    def __init__(self, parent, default_name: str, bg: str, fg: str, font):
        super().__init__(parent)
        self.title("New Scene")
        self.configure(bg=bg)
        self.resizable(False, False)
        self.grab_set()

        self.result: dict | None = None
        self._md_source  = None
        self._png_source = None

        lbl_opts = dict(bg=bg, fg=fg, font=font, anchor="w")
        ent_opts = dict(bg="#263040", fg=fg, font=font, insertbackground=fg,
                        relief=tk.FLAT, bd=4)
        btn_opts = dict(bg="#263040", fg=fg, font=font,
                        activebackground="#303848", relief=tk.FLAT, padx=6)

        tk.Label(self, text="Scene name:", **lbl_opts).grid(
            row=0, column=0, sticky="w", padx=(12, 4), pady=(12, 4))
        self.e_name = tk.Entry(self, width=28, **ent_opts)
        self.e_name.insert(0, default_name)
        self.e_name.grid(row=0, column=1, columnspan=2, padx=(0, 12), pady=(12, 4))

        for row, (label, attr, src_attr, ext_label, filetypes) in enumerate([
            ("MD file:",  "e_md",  "_md_source",
             ".md",  [("Markdown", "*.md"), ("All files", "*.*")]),
            ("PNG file:", "e_png", "_png_source",
             ".png", [("PNG image", "*.png"), ("All files", "*.*")]),
        ], start=1):
            tk.Label(self, text=label, **lbl_opts).grid(
                row=row, column=0, sticky="w", padx=(12, 4), pady=4)

            entry = tk.Entry(self, width=22, **ent_opts)
            entry.grid(row=row, column=1, pady=4)
            setattr(self, attr, entry)

            def _browse(a=attr, sa=src_attr, ft=filetypes):
                path = filedialog.askopenfilename(parent=self, filetypes=ft)
                if not path:
                    return
                getattr(self, a).delete(0, tk.END)
                getattr(self, a).insert(0, os.path.basename(path))
                setattr(self, sa, path)

            tk.Button(self, text="Browse…", command=_browse, **btn_opts).grid(
                row=row, column=2, padx=(4, 12), pady=4)

        if HAS_DND:
            hint = tk.Label(self, text="or drop a .md / .png file anywhere here",
                            bg=bg, fg="#507090", font=font)
            hint.grid(row=3, column=0, columnspan=3, pady=(0, 4))
            self._wire_dnd()
        else:
            tk.Frame(self, bg=bg, height=4).grid(row=3, column=0)

        btn_frame = tk.Frame(self, bg=bg)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=10)
        tk.Button(btn_frame, text="Create", font=font,
                  bg="#2e4a6a", fg=fg, activebackground="#3a5a7a", relief=tk.FLAT,
                  command=self._ok).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frame, text="Cancel", font=font,
                  bg="#263040", fg=fg, activebackground="#303848", relief=tk.FLAT,
                  command=self.destroy).pack(side=tk.LEFT, padx=6)

        self.e_name.focus_set()
        self.bind("<Return>", lambda _: self._ok())
        self.bind("<Escape>", lambda _: self.destroy())

        self.update_idletasks()
        px, py = self.master.winfo_rootx(), self.master.winfo_rooty()
        pw, ph = self.master.winfo_width(), self.master.winfo_height()
        self.geometry(f"+{px + pw//2 - self.winfo_width()//2}"
                      f"+{py + ph//2 - self.winfo_height()//2}")
        self.wait_window()

    def _wire_dnd(self):
        def _on_drop(event):
            raw = event.data.strip()
            paths = self.tk.splitlist(raw)
            for path in paths:
                _, ext = os.path.splitext(path)
                ext = ext.lower()
                if ext == ".md":
                    self.e_md.delete(0, tk.END)
                    self.e_md.insert(0, os.path.basename(path))
                    self._md_source = path
                elif ext == ".png":
                    self.e_png.delete(0, tk.END)
                    self.e_png.insert(0, os.path.basename(path))
                    self._png_source = path

        for widget in (self, *self.winfo_children()):
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", _on_drop)
            except Exception:
                pass

    def _ok(self):
        name = self.e_name.get().strip()
        if not name:
            return
        self.result = {
            "name":       name,
            "md":         self.e_md.get().strip(),
            "md_source":  self._md_source,
            "png":        self.e_png.get().strip(),
            "png_source": self._png_source,
        }
        self.destroy()


class _ZoneInfoDialog(tk.Toplevel):
    """Modal dialog to collect zone id and target after drawing."""

    def __init__(self, parent, bg: str, fg: str, font):
        super().__init__(parent)
        self.title("New Zone")
        self.configure(bg=bg)
        self.resizable(False, False)
        self.grab_set()
        self.result: dict | None = None

        ent = dict(bg="#263040", fg=fg, font=font, insertbackground=fg,
                   relief=tk.FLAT, bd=4)
        lbl = dict(bg=bg, fg=fg, font=font, anchor="w")

        tk.Label(self, text="Zone ID:", **lbl).grid(row=0, column=0, padx=(12, 4), pady=(12, 4))
        self.e_id = tk.Entry(self, width=26, **ent)
        self.e_id.grid(row=0, column=1, padx=(0, 12), pady=(12, 4))

        tk.Label(self, text="Target:", **lbl).grid(row=1, column=0, padx=(12, 4), pady=4)
        self.e_target = tk.Entry(self, width=26, **ent)
        self.e_target.grid(row=1, column=1, padx=(0, 12), pady=4)

        bf = tk.Frame(self, bg=bg)
        bf.grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(bf, text="OK", font=font, bg="#2e4a6a", fg=fg,
                  activebackground="#3a5a7a", relief=tk.FLAT,
                  command=self._ok).pack(side=tk.LEFT, padx=6)
        tk.Button(bf, text="Cancel", font=font, bg="#263040", fg=fg,
                  activebackground="#303848", relief=tk.FLAT,
                  command=self.destroy).pack(side=tk.LEFT, padx=6)

        self.e_id.focus_set()
        self.bind("<Return>", lambda _: self._ok())
        self.bind("<Escape>", lambda _: self.destroy())
        self.update_idletasks()
        px, py = self.master.winfo_rootx(), self.master.winfo_rooty()
        pw, ph = self.master.winfo_width(), self.master.winfo_height()
        self.geometry(f"+{px + pw//2 - self.winfo_width()//2}"
                      f"+{py + ph//2 - self.winfo_height()//2}")
        self.wait_window()

    def _ok(self):
        zone_id = self.e_id.get().strip()
        if not zone_id:
            return
        self.result = {"id": zone_id, "target": self.e_target.get().strip()}
        self.destroy()
