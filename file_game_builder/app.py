import json
import os
import re
import shutil
import sys
import tkinter as tk
from tkinter import font as tkfont, simpledialog, messagebox, filedialog

from . import TkRoot
from .constants import COLORS, PREVIEW_EXTS, LORES_W, LORES_H
from .node import (
    Node, build_tree, measure, draw_node,
    node_kind, _next_numbered_dir, _scene_info_for_png,
)
from .dialogs import NewSceneDialog, _ZoneInfoDialog
from . import refresh_game_data
from . import resize_png

_ZONE_COLORS = ["#ff6060", "#60dd60", "#6090ff", "#ffdd40", "#ff60ff", "#40ffee"]

# Collapse arrays of [x,y] point pairs onto a single line in JSON output.
_INLINE_POINTS_RE = re.compile(r'\[\s*(\[\s*-?\d+\s*,\s*-?\d+\s*\](?:\s*,\s*\[\s*-?\d+\s*,\s*-?\d+\s*\])*)\s*\]', re.DOTALL)

def _dump_scene_info(data: dict) -> str:
    raw = json.dumps(data, indent=2)
    def _collapse(m):
        pairs = re.findall(r'\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]', m.group(1))
        return '[' + ', '.join(f'[{x}, {y}]' for x, y in pairs) + ']'
    return _INLINE_POINTS_RE.sub(_collapse, raw)


def run_refresh(data_root: str | None = None) -> None:
    """Regenerate level_info.json / scene_info.json / Default_Game_State.json."""
    try:
        refresh_game_data.run(data_root)
    except Exception as e:
        print(f"[run_refresh] error: {e}", file=sys.stderr)


def gen_lores_pngs(data_root: str) -> tuple[int, list[str]]:
    """
    Walk all LEVEL_*/SCENE_* dirs and find PNGs whose native resolution exceeds
    320x240. For each one, write a 320x240 crop-to-fill version named
    <original>_320x240.png into the same scene directory.

    Returns (count_generated, list_of_warning_strings).
    """
    try:
        from PIL import Image
    except Exception as e:
        return 0, [f"Failed to import Pillow: {e}. Run: pip install Pillow"]

    levels_dir = os.path.join(data_root, "LEVELS")
    count      = 0
    warnings   = []

    if not os.path.isdir(levels_dir):
        return 0, [f"LEVELS directory not found: {levels_dir}"]

    for level_name in sorted(os.listdir(levels_dir)):
        level_path = os.path.join(levels_dir, level_name)
        if not os.path.isdir(level_path):
            continue

        for scene_name in sorted(os.listdir(level_path)):
            if not scene_name.startswith("SCENE_"):
                continue
            scene_path = os.path.join(level_path, scene_name)
            if not os.path.isdir(scene_path):
                continue

            info_path = os.path.join(scene_path, "scene_info.json")
            try:
                info = json.loads(open(info_path, encoding="utf-8").read()) if os.path.isfile(info_path) else {}
            except Exception:
                info = {}

            png_file = info.get("png", "")
            if not png_file:
                continue

            png_path = os.path.join(scene_path, png_file)
            if not os.path.isfile(png_path):
                warnings.append(f"Missing PNG: {png_path}")
                continue

            try:
                with Image.open(png_path) as img:
                    if img.width <= LORES_W and img.height <= LORES_H:
                        continue
                    src = img if img.mode == "RGB" else img.convert("RGB")
                    resized = resize_png.resize_crop(src, (LORES_W, LORES_H))
                    base, _ = os.path.splitext(png_file)
                    lores_path = os.path.join(scene_path, f"{base}_{LORES_W}x{LORES_H}.png")
                    resized.save(lores_path, "PNG")
                    count += 1
            except Exception as e:
                warnings.append(f"Error processing {png_path}: {e}")

    return count, warnings


class DataLayoutApp:
    """
    Main application window — visualizes a game project DATA/ folder as
    nested boxes and provides editing actions for levels, scenes, and zones.
    """

    _MARGIN = 20

    def __init__(self, data_root: str | None, project_name: str | None = None):
        self._project = {
            "root":   data_root,
            "levels": os.path.join(data_root, "LEVELS") if data_root else None,
            "name":   project_name or "",
        }
        self._preview_image_ref = None
        self._preview_path      = None
        self._is_modified       = False
        self._hit_areas: list   = []
        self._protected: set    = set()
        self._zed = {
            "mode":       None,    # "polygon" | "rect" | None
            "points":     [],      # [(gx, gy)] in 320x240 game coords
            "ids":        [],      # canvas item IDs for in-progress drawing
            "preview_id": None,    # rubber-band / dashed preview line
            "scale_x":    1.0,
            "scale_y":    1.0,
            "img_w":      0,
            "img_h":      0,
            "scene_path": None,    # path to scene_info.json
            "node":       None,    # current PNG Node
            "photo":      None,    # ImageTk ref (prevent GC)
            "drag_start": None,    # (gx, gy) for rect first click
        }
        self._build_ui()
        if data_root:
            self._refresh_protected()

    # ------------------------------------------------------------------ build

    def _build_ui(self) -> None:
        self._win = TkRoot()
        self._win.title(f"DATA Layout  —  {self._project['name']}")
        self._win.configure(bg=COLORS["canvas_bg"])

        self._folder_font      = tkfont.Font(family="Consolas", size=9, weight="bold")
        self._file_font        = tkfont.Font(family="Consolas", size=8)
        self._preview_font     = tkfont.Font(family="Consolas", size=9)
        self._preview_hdr_font = tkfont.Font(family="Consolas", size=9, weight="bold")

        self._build_toolbar()
        self._build_paned()
        self._build_menubar()

    def _build_toolbar(self) -> None:
        toolbar = tk.Frame(self._win, bg=COLORS["preview_hdr"], pady=3)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        _tb = dict(bg="#263040", fg=COLORS["folder_text"], font=self._file_font,
                   activebackground="#2e4a6a", activeforeground="#ffffff",
                   relief=tk.FLAT, padx=10, pady=2)

        self._save_all_btn = tk.Button(toolbar, text="Save All",
                                        command=self._do_save_all, **_tb)
        self._save_all_btn.pack(side=tk.LEFT, padx=(6, 2), pady=2)

        self._refresh_btn = tk.Button(toolbar, text="Refresh",
                                       command=self._do_refresh, **_tb)
        self._refresh_btn.pack(side=tk.LEFT, padx=2, pady=2)

        self._lores_btn = tk.Button(toolbar, text="Refresh Lo-Res PNGs",
                                     command=self._do_refresh_lores, **_tb)
        self._lores_btn.pack(side=tk.LEFT, padx=2, pady=2)

    def _build_paned(self) -> None:
        self._paned = tk.PanedWindow(self._win, orient=tk.HORIZONTAL,
                                      bg=COLORS["canvas_bg"], sashwidth=5,
                                      sashrelief=tk.FLAT)
        self._paned.pack(fill=tk.BOTH, expand=True)
        self._build_left_panel()
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        left_frame = tk.Frame(self._paned, bg=COLORS["canvas_bg"])
        self._paned.add(left_frame, stretch="always")

        self._vscroll = tk.Scrollbar(left_frame, orient=tk.VERTICAL)
        self._hscroll = tk.Scrollbar(left_frame, orient=tk.HORIZONTAL)
        self._canvas  = tk.Canvas(left_frame, bg=COLORS["canvas_bg"],
                                   yscrollcommand=self._vscroll.set,
                                   xscrollcommand=self._hscroll.set,
                                   highlightthickness=0)
        self._vscroll.config(command=self._canvas.yview)
        self._hscroll.config(command=self._canvas.xview)
        self._vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._canvas.bind("<MouseWheel>",
                          lambda e: self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        self._canvas.bind("<Button-1>", self._on_left_click)
        self._canvas.bind("<Button-3>", self._on_right_click)

    def _build_right_panel(self) -> None:
        right_frame = tk.Frame(self._paned, bg=COLORS["preview_bg"], width=340)
        self._paned.add(right_frame, stretch="never")

        # Header row: filename label + save button
        preview_hdr_frame = tk.Frame(right_frame, bg=COLORS["preview_hdr"])
        preview_hdr_frame.pack(side=tk.TOP, fill=tk.X)

        self._preview_header = tk.Label(preview_hdr_frame, text="No file selected",
                                         bg=COLORS["preview_hdr"], fg=COLORS["folder_text"],
                                         font=self._preview_hdr_font, anchor="w", padx=8, pady=4)
        self._preview_header.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._save_btn = tk.Button(preview_hdr_frame, text="Save", font=self._file_font,
                                    bg="#2a5a3a", fg="#80e8a0", activebackground="#3a7a50",
                                    relief=tk.FLAT, padx=8, pady=2, state=tk.DISABLED,
                                    command=self._save_preview)
        self._save_btn.pack(side=tk.RIGHT, padx=4, pady=2)

        self._preview_text_scroll = tk.Scrollbar(right_frame, orient=tk.VERTICAL)
        self._preview_text = tk.Text(right_frame, bg=COLORS["preview_bg"],
                                      fg=COLORS["preview_txt"], font=self._preview_font,
                                      wrap=tk.WORD, state=tk.DISABLED, relief=tk.FLAT,
                                      borderwidth=0, padx=8, pady=6,
                                      yscrollcommand=self._preview_text_scroll.set,
                                      insertbackground=COLORS["preview_txt"], undo=True)
        self._preview_text_scroll.config(command=self._preview_text.yview)
        self._preview_text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Zone-editor controls bar (hidden until a scene PNG is selected)
        self._zone_controls = tk.Frame(right_frame, bg=COLORS["preview_hdr"])
        _zc = dict(bg="#263040", fg=COLORS["folder_text"], font=self._file_font,
                   activebackground="#2e4a6a", activeforeground="#ffffff",
                   relief=tk.FLAT, padx=6, pady=1)
        self._poly_btn   = tk.Button(self._zone_controls, text="+ Polygon", **_zc)
        self._rect_btn   = tk.Button(self._zone_controls, text="+ Rect",    **_zc)
        self._done_btn   = tk.Button(self._zone_controls, text="Done",   state=tk.DISABLED, **_zc)
        self._cancel_btn = tk.Button(self._zone_controls, text="Cancel", state=tk.DISABLED, **_zc)
        for b in (self._poly_btn, self._rect_btn, self._done_btn, self._cancel_btn):
            b.pack(side=tk.LEFT, padx=2, pady=2)

        self._poly_btn.config(
            command=lambda: (self._cancel_draw(),
                             self._zed.update(mode="polygon"),
                             self._set_draw_controls(True)))
        self._rect_btn.config(
            command=lambda: (self._cancel_draw(),
                             self._zed.update(mode="rect"),
                             self._set_draw_controls(True)))
        self._done_btn.config(command=self._finish_draw)
        self._cancel_btn.config(command=self._on_cancel_btn)

        # Scrollable canvas for scene PNG + zone overlay (hidden until needed)
        self._pv_frame   = tk.Frame(right_frame, bg=COLORS["preview_bg"])
        self._pv_vscroll = tk.Scrollbar(self._pv_frame, orient=tk.VERTICAL)
        self._pv_hscroll = tk.Scrollbar(self._pv_frame, orient=tk.HORIZONTAL)
        self._pv_canvas  = tk.Canvas(self._pv_frame, bg=COLORS["preview_bg"],
                                      highlightthickness=0,
                                      yscrollcommand=self._pv_vscroll.set,
                                      xscrollcommand=self._pv_hscroll.set)
        self._pv_vscroll.config(command=self._pv_canvas.yview)
        self._pv_hscroll.config(command=self._pv_canvas.xview)
        self._pv_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._pv_hscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self._pv_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._pv_canvas.bind("<Button-1>",        self._on_pv_click)
        self._pv_canvas.bind("<Double-Button-1>", self._on_pv_double_click)
        self._pv_canvas.bind("<Motion>",          self._on_pv_motion)

        self._win.bind("<Control-s>", lambda _: self._save_preview())

    def _build_menubar(self) -> None:
        _mo = dict(bg="#1e2a3a", fg="#a8c8f0",
                   activebackground="#2e4a6a", activeforeground="#ffffff",
                   font=self._file_font)
        menubar   = tk.Menu(self._win, **_mo)
        file_menu = tk.Menu(menubar, tearoff=0, **_mo)
        file_menu.add_command(label="New Project…",     command=self._new_project)
        file_menu.add_command(label="Open Project…",    command=self._open_project)
        file_menu.add_separator()
        file_menu.add_command(label="Save Project As…", command=self._save_project_as)
        menubar.add_cascade(label="File", menu=file_menu)
        self._win.config(menu=menubar)

    # ------------------------------------------------------------------ run

    def run(self) -> None:
        if self._project["root"] and os.path.isdir(self._project["root"]):
            self._redraw()
        else:
            # No valid project on startup — prompt immediately after window appears
            self._win.after(100, self._open_project)
        self._win.mainloop()

    # ------------------------------------------------------------------ preview

    def _mark_modified(self, event=None) -> None:
        if not self._is_modified:
            self._is_modified = True
            name = os.path.basename(self._preview_path) if self._preview_path else ""
            self._preview_header.config(text=f"{name}  •")

    def _save_preview(self) -> None:
        if not self._preview_path:
            return
        try:
            content = self._preview_text.get("1.0", tk.END)
            if content.endswith("\n"):
                content = content[:-1]
            with open(self._preview_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError as e:
            messagebox.showerror("Save Error", str(e), parent=self._win)
            return
        self._is_modified = False
        self._preview_header.config(text=os.path.basename(self._preview_path))

    def _do_save_all(self) -> None:
        self._save_preview()

    def _do_refresh(self) -> None:
        run_refresh(self._project["root"])
        self._redraw()

    def _do_refresh_lores(self) -> None:
        count, warnings = gen_lores_pngs(self._project["root"])
        if warnings:
            messagebox.showwarning("Refresh Lo-Res PNGs", "\n".join(warnings), parent=self._win)
        if count:
            self._redraw()

    # ------------------------------------------------------------------ zone editor

    def _g2c(self, gx, gy) -> tuple[float, float]:
        """Game coords → canvas pixel coords."""
        return gx * self._zed["scale_x"], gy * self._zed["scale_y"]

    def _c2g(self, cx, cy) -> tuple[int, int]:
        """Canvas pixel coords → rounded game coords (clamped to 320×240)."""
        gx = max(0, min(319, round(cx / self._zed["scale_x"])))
        gy = max(0, min(239, round(cy / self._zed["scale_y"])))
        return gx, gy

    def _draw_zones(self, scene_info: dict) -> None:
        for i, zone in enumerate(scene_info.get("zones", [])):
            color = _ZONE_COLORS[i % len(_ZONE_COLORS)]
            zid   = zone.get("id", "")
            pts   = zone.get("points", [])
            if pts:
                flat = []
                for p in pts:
                    cx, cy = self._g2c(p[0], p[1])
                    flat += [cx, cy]
                if len(flat) >= 4:
                    self._pv_canvas.create_polygon(flat, outline=color,
                                                    fill=color, stipple="gray25", width=2)
                if flat:
                    self._pv_canvas.create_text(flat[0], flat[1] - 8, text=zid,
                                                fill=color, font=self._file_font, anchor="sw")
            elif "x" in zone:
                x1, y1 = self._g2c(zone["x"], zone["y"])
                x2, y2 = self._g2c(zone["x"] + zone.get("w", 0),
                                    zone["y"] + zone.get("h", 0))
                self._pv_canvas.create_rectangle(x1, y1, x2, y2,
                                                  outline=color, fill=color, stipple="gray25", width=2)
                self._pv_canvas.create_text(x1, y1 - 8, text=zid,
                                             fill=color, font=self._file_font, anchor="sw")

    def _show_scene_png(self, node: Node, scene_info_path: str) -> None:
        try:
            from PIL import Image, ImageTk
            with Image.open(node.path) as img:
                avail_w = max(self._pv_frame.winfo_width(), 400)
                avail_h = max(self._pv_frame.winfo_height(), 300)
                scale   = min(avail_w / img.width, avail_h / img.height)
                disp_w  = max(1, int(img.width  * scale))
                disp_h  = max(1, int(img.height * scale))
                disp    = img.convert("RGBA").resize((disp_w, disp_h), Image.Resampling.LANCZOS)
                photo   = ImageTk.PhotoImage(disp)
        except Exception as e:
            self._preview_header.config(text=f"{node.name}  [error: {e}]")
            return

        self._zed["photo"]      = photo
        self._zed["scale_x"]    = disp_w / 320.0
        self._zed["scale_y"]    = disp_h / 240.0
        self._zed["img_w"]      = disp_w
        self._zed["img_h"]      = disp_h
        self._zed["scene_path"] = scene_info_path
        self._zed["node"]       = node

        self._pv_canvas.delete("all")
        self._pv_canvas.config(scrollregion=(0, 0, disp_w, disp_h))
        self._pv_canvas.create_image(0, 0, anchor="nw", image=photo)

        try:
            info = json.loads(open(scene_info_path, encoding="utf-8").read())
        except Exception:
            info = {}
        self._draw_zones(info)

    def _set_draw_controls(self, drawing: bool) -> None:
        s_draw = tk.DISABLED if drawing else tk.NORMAL
        s_done = tk.NORMAL   if drawing else tk.DISABLED
        self._poly_btn.config(state=s_draw)
        self._rect_btn.config(state=s_draw)
        self._done_btn.config(state=s_done)
        self._cancel_btn.config(state=s_done)

    def _cancel_draw(self) -> None:
        for cid in self._zed["ids"]:
            self._pv_canvas.delete(cid)
        if self._zed["preview_id"]:
            self._pv_canvas.delete(self._zed["preview_id"])
        self._zed.update(mode=None, points=[], ids=[], preview_id=None, drag_start=None)
        self._set_draw_controls(False)

    def _on_cancel_btn(self) -> None:
        """Cancel button: discard in-progress draw and refresh so zones stay visible."""
        node = self._zed["node"]
        path = self._zed["scene_path"]
        self._cancel_draw()
        if node and path:
            self._show_scene_png(node, path)

    def _finish_draw(self) -> None:
        mode      = self._zed["mode"]
        points    = list(self._zed["points"])
        info_path = self._zed["scene_path"]
        node      = self._zed["node"]

        if mode == "polygon" and len(points) < 3:
            return
        if mode == "rect" and len(points) < 2:
            return
        if not info_path or not node:
            self._cancel_draw()
            return

        self._cancel_draw()

        dlg = _ZoneInfoDialog(self._win, bg=COLORS["canvas_bg"],
                              fg=COLORS["folder_text"], font=self._file_font)
        if dlg.result is None:
            self._show_scene_png(node, info_path)
            return

        zone_id = dlg.result["id"]
        target  = dlg.result["target"]

        if mode == "polygon":
            zone = {"id": zone_id, "points": [list(p) for p in points], "target": target}
        else:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            zone = {"id": zone_id,
                    "x": min(xs), "y": min(ys),
                    "w": abs(xs[1] - xs[0]), "h": abs(ys[1] - ys[0]),
                    "target": target}

        try:
            info = json.loads(open(info_path, encoding="utf-8").read())
        except Exception:
            info = {}
        info.setdefault("zones", []).append(zone)
        with open(info_path, "w", encoding="utf-8") as f:
            f.write(_dump_scene_info(info))

        self._show_scene_png(node, info_path)

    def _on_pv_click(self, event) -> None:
        if self._zed["mode"] is None:
            return
        cx, cy = self._pv_canvas.canvasx(event.x), self._pv_canvas.canvasy(event.y)
        gx, gy = self._c2g(cx, cy)

        if self._zed["mode"] == "polygon":
            self._zed["points"].append((gx, gy))
            dot = self._pv_canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3,
                                               fill="#ffcc00", outline="")
            self._zed["ids"].append(dot)
            if len(self._zed["points"]) > 1:
                prev = self._zed["points"][-2]
                px, py = self._g2c(*prev)
                line = self._pv_canvas.create_line(px, py, cx, cy,
                                                    fill="#ffcc00", width=2)
                self._zed["ids"].append(line)

        elif self._zed["mode"] == "rect":
            if self._zed["drag_start"] is None:
                self._zed["drag_start"] = (gx, gy)
                dot = self._pv_canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3,
                                                   fill="#ffcc00", outline="")
                self._zed["ids"].append(dot)
            else:
                self._zed["points"] = [self._zed["drag_start"], (gx, gy)]
                self._finish_draw()

    def _on_pv_double_click(self, event) -> None:
        if self._zed["mode"] == "polygon" and len(self._zed["points"]) >= 3:
            self._finish_draw()

    def _on_pv_motion(self, event) -> None:
        if self._zed["mode"] is None:
            return
        cx, cy = self._pv_canvas.canvasx(event.x), self._pv_canvas.canvasy(event.y)
        if self._zed["preview_id"]:
            self._pv_canvas.delete(self._zed["preview_id"])
            self._zed["preview_id"] = None

        if self._zed["mode"] == "polygon" and self._zed["points"]:
            px, py = self._g2c(*self._zed["points"][-1])
            self._zed["preview_id"] = self._pv_canvas.create_line(
                px, py, cx, cy, fill="#ffcc0099", width=1, dash=(5, 3))

        elif self._zed["mode"] == "rect" and self._zed["drag_start"] is not None:
            sx, sy = self._g2c(*self._zed["drag_start"])
            self._zed["preview_id"] = self._pv_canvas.create_rectangle(
                sx, sy, cx, cy, outline="#ffcc00", fill="", width=1, dash=(5, 3))

    def _show_zone_editor(self, node: Node, scene_info_path: str) -> None:
        self._cancel_draw()
        self._preview_text_scroll.pack_forget()
        self._preview_text.pack_forget()
        self._zone_controls.pack(side=tk.TOP, fill=tk.X)
        self._pv_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._preview_header.config(text=node.name)
        self._save_btn.config(state=tk.DISABLED)
        self._show_scene_png(node, scene_info_path)

    def _hide_zone_editor(self) -> None:
        self._cancel_draw()
        self._pv_frame.pack_forget()
        self._zone_controls.pack_forget()
        self._preview_text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def show_preview(self, node: Node) -> None:
        _, ext = os.path.splitext(node.name)
        ext = ext.lower()

        scene_info_path = _scene_info_for_png(node)
        if scene_info_path:
            self._preview_path      = None
            self._is_modified       = False
            self._preview_image_ref = None
            self._show_zone_editor(node, scene_info_path)
            return

        self._hide_zone_editor()
        self._preview_path      = None
        self._is_modified       = False
        self._preview_image_ref = None

        self._preview_header.config(text=node.name)
        self._preview_text.config(state=tk.NORMAL)
        self._preview_text.delete("1.0", tk.END)

        if ext == ".png":
            self._save_btn.config(state=tk.DISABLED)
            self._preview_text.edit_reset()
            try:
                img = tk.PhotoImage(file=node.path)
                self._preview_image_ref = img
                self._preview_text.image_create(tk.END, image=img)
            except Exception as e:
                self._preview_text.insert(tk.END, f"[Could not load image]\n{e}")
            self._preview_text.config(state=tk.DISABLED)

        elif ext in (".md", ".json"):
            try:
                with open(node.path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                self._preview_text.insert(tk.END, content)
                self._preview_text.edit_reset()
                self._preview_text.config(state=tk.NORMAL)
                self._preview_path = node.path
                self._save_btn.config(state=tk.NORMAL)
                self._preview_text.bind("<<Modified>>", self._on_text_modified)
            except Exception as e:
                self._preview_text.insert(tk.END, f"[Could not read file]\n{e}")
                self._preview_text.config(state=tk.DISABLED)
                self._save_btn.config(state=tk.DISABLED)
        else:
            self._preview_text.config(state=tk.DISABLED)
            self._save_btn.config(state=tk.DISABLED)

    def _on_text_modified(self, event=None) -> None:
        if self._preview_text.edit_modified():
            self._mark_modified()
            self._preview_text.edit_modified(False)

    def clear_preview(self) -> None:
        self._hide_zone_editor()
        self._preview_path      = None
        self._is_modified       = False
        self._preview_image_ref = None
        self._preview_header.config(text="No file selected")
        self._preview_text.config(state=tk.NORMAL)
        self._preview_text.delete("1.0", tk.END)
        self._preview_text.config(state=tk.DISABLED)
        self._save_btn.config(state=tk.DISABLED)

    # ------------------------------------------------------------------ tree

    def _redraw(self) -> None:
        self._canvas.delete("all")
        self._hit_areas = []
        tree = build_tree(self._project["root"], "DATA")
        tw, th = measure(tree, self._folder_font, self._file_font)
        canvas_w = tw + self._MARGIN * 2
        canvas_h = th + self._MARGIN * 2
        self._canvas.config(scrollregion=(0, 0, canvas_w, canvas_h))
        draw_node(self._canvas, tree, self._MARGIN, self._MARGIN, tw, th,
                  self._folder_font, self._file_font, self._hit_areas)
        screen_w = self._win.winfo_screenwidth()
        screen_h = self._win.winfo_screenheight()
        preview_w = 420
        total_w = min(canvas_w + preview_w, screen_w - 60)
        total_h = min(canvas_h + 20, screen_h - 100)
        self._win.geometry(f"{total_w}x{total_h}")
        self._win.update_idletasks()
        self._paned.sash_place(0, canvas_w, 0)

    def _canvas_to_world(self, event) -> tuple[float, float]:
        return self._canvas.canvasx(event.x), self._canvas.canvasy(event.y)

    def _find_node_at(self, cx, cy) -> Node | None:
        for x1, y1, x2, y2, node in self._hit_areas:
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                return node
        return None

    # ------------------------------------------------------------------ context actions

    def _add_scene(self, parent_node: Node) -> None:
        dir_name, n = _next_numbered_dir(parent_node.path, "SCENE_")
        dlg = NewSceneDialog(self._win, f"Scene {n}",
                             bg=COLORS["canvas_bg"], fg=COLORS["folder_text"],
                             font=self._file_font)
        if dlg.result is None:
            return

        dest = os.path.join(parent_node.path, dir_name)
        try:
            os.makedirs(dest)
            info: dict = {"name": dlg.result["name"], "zones": []}

            for key, src_key in (("md", "md_source"), ("png", "png_source")):
                fname  = dlg.result[key]
                source = dlg.result[src_key]
                if not fname:
                    continue
                info[key] = fname
                dest_file = os.path.join(dest, fname)
                if source and os.path.isfile(source):
                    shutil.copy2(source, dest_file)
                else:
                    open(dest_file, "w").close()

            with open(os.path.join(dest, "scene_info.json"), "w", encoding="utf-8") as f:
                f.write(_dump_scene_info(info))
        except OSError as e:
            messagebox.showerror("Error", str(e), parent=self._win)
            return
        run_refresh(self._project["root"])
        self._redraw()

    def _add_level(self) -> None:
        dir_name, n = _next_numbered_dir(self._project["levels"], "LEVEL_")
        dest = os.path.join(self._project["levels"], dir_name)
        try:
            os.makedirs(dest)
            with open(os.path.join(dest, "level_info.json"), "w", encoding="utf-8") as f:
                json.dump({"name": f"Level {n}"}, f, indent=2)
        except OSError as e:
            messagebox.showerror("Error", str(e), parent=self._win)
            return
        run_refresh(self._project["root"])
        self._redraw()

    def _add_file(self, parent_node: Node) -> None:
        name = simpledialog.askstring(
            "New File", f"File name (inside {parent_node.name}):", parent=self._win)
        if not name or not name.strip():
            return
        dest = os.path.join(parent_node.path, name.strip())
        if os.path.exists(dest):
            messagebox.showerror("Error", f"Already exists:\n{dest}", parent=self._win)
            return
        try:
            open(dest, "w").close()
        except OSError as e:
            messagebox.showerror("Error", str(e), parent=self._win)
            return
        self._redraw()

    def _add_folder(self, parent_node: Node) -> None:
        name = simpledialog.askstring(
            "New Folder", f"Folder name (inside {parent_node.name}):", parent=self._win)
        if not name or not name.strip():
            return
        dest = os.path.join(parent_node.path, name.strip())
        if os.path.exists(dest):
            messagebox.showerror("Error", f"Already exists:\n{dest}", parent=self._win)
            return
        try:
            os.makedirs(dest)
        except OSError as e:
            messagebox.showerror("Error", str(e), parent=self._win)
            return
        run_refresh(self._project["root"])
        self._redraw()

    def _refresh_protected(self) -> None:
        self._protected.clear()
        self._protected.add(self._project["root"])
        self._protected.add(self._project["levels"])

    def _delete_node(self, node: Node) -> None:
        if os.path.abspath(node.path) in self._protected:
            messagebox.showerror("Protected", f"{node.name} cannot be deleted.", parent=self._win)
            return
        msg = (f"Delete '{node.name}' and all its contents?\n\n{node.path}"
               if node.is_dir else f"Delete '{node.name}'?\n\n{node.path}")
        if not messagebox.askyesno("Confirm Delete", msg, icon="warning", parent=self._win):
            return
        try:
            shutil.rmtree(node.path) if node.is_dir else os.remove(node.path)
        except OSError as e:
            messagebox.showerror("Error", str(e), parent=self._win)
            return
        if node.is_dir:
            run_refresh(self._project["root"])
        self.clear_preview()
        self._redraw()

    # ------------------------------------------------------------------ project management

    def _set_project(self, new_root: str, name: str | None = None) -> None:
        self._project["root"]   = os.path.abspath(new_root)
        self._project["levels"] = os.path.join(self._project["root"], "LEVELS")
        self._project["name"]   = (name
                                    or os.path.basename(os.path.dirname(new_root))
                                    or os.path.basename(new_root))
        self._refresh_protected()
        self._win.title(f"DATA Layout  —  {self._project['name']}")
        self.clear_preview()
        self._redraw()

    def _new_project(self) -> None:
        name = simpledialog.askstring("New Project", "Project name:", parent=self._win)
        if not name or not name.strip():
            return
        name = name.strip()
        dest_parent = filedialog.askdirectory(
            title="Choose location for new project",
            initialdir=r"C:\FILE_GAMES\GAMES",
            parent=self._win)
        if not dest_parent:
            return
        project_root = os.path.join(dest_parent, name)
        data_dir     = os.path.join(project_root, "DATA")
        if os.path.exists(project_root):
            messagebox.showerror("Error", f"Already exists:\n{project_root}", parent=self._win)
            return
        try:
            os.makedirs(os.path.join(data_dir, "LEVELS"), exist_ok=True)
            os.makedirs(os.path.join(data_dir, "GUI"),    exist_ok=True)
            gs_dir = os.path.join(data_dir, "GAME_STATE")
            os.makedirs(gs_dir,                            exist_ok=True)
            curr_gui = (os.path.join(self._project["root"], "GUI")
                        if self._project.get("root") else None)
            if curr_gui and os.path.isdir(curr_gui):
                for fname in os.listdir(curr_gui):
                    src = os.path.join(curr_gui, fname)
                    if os.path.isfile(src):
                        shutil.copy2(src, os.path.join(data_dir, "GUI", fname))
            default_state = {"current_level": "", "current_scene": "", "levels": {}}
            with open(os.path.join(gs_dir, "Default_Game_State.json"), "w", encoding="utf-8") as f:
                json.dump(default_state, f, indent=2)
        except OSError as e:
            messagebox.showerror("Error", str(e), parent=self._win)
            return
        self._set_project(data_dir, name)

    def _open_project(self) -> None:
        path = filedialog.askdirectory(
            title="Open project — select the DATA folder or project root",
            initialdir=r"C:\FILE_GAMES\GAMES",
            parent=self._win,
        )
        if not path:
            return
        path = os.path.abspath(path)
        if os.path.isdir(os.path.join(path, "LEVELS")):
            data_path = path
        elif os.path.isdir(os.path.join(path, "DATA", "LEVELS")):
            data_path = os.path.join(path, "DATA")
        else:
            messagebox.showerror(
                "Invalid Project",
                "Could not find a LEVELS folder.\n\n"
                "Select either:\n"
                "  \u2022 the DATA folder (containing LEVELS/)\n"
                "  \u2022 the project root (containing DATA/LEVELS/)",
                parent=self._win,
            )
            return
        parent_name = os.path.basename(os.path.dirname(data_path))
        name = parent_name if parent_name else os.path.basename(data_path)
        self._set_project(data_path, name)

    def _save_project_as(self) -> None:
        if not self._project.get("root"):
            messagebox.showerror("No Project", "Open a project first.", parent=self._win)
            return
        name = simpledialog.askstring(
            "Save Project As", "Project name:",
            initialvalue=self._project.get("name", ""), parent=self._win)
        if not name or not name.strip():
            return
        name = name.strip()
        dest_parent = filedialog.askdirectory(
            title="Choose destination folder",
            initialdir=r"C:\FILE_GAMES\GAMES",
            parent=self._win)
        if not dest_parent:
            return
        target = os.path.join(dest_parent, name)
        if os.path.exists(target):
            if not messagebox.askyesno("Overwrite?",
                                        f"'{target}'\nalready exists. Overwrite?",
                                        parent=self._win):
                return
            shutil.rmtree(target)
        try:
            shutil.copytree(self._project["root"], target)
        except OSError as e:
            messagebox.showerror("Save Error", str(e), parent=self._win)
            return
        messagebox.showinfo("Saved", f"Project saved to:\n{target}", parent=self._win)

    # ------------------------------------------------------------------ click handlers

    def _on_left_click(self, event) -> None:
        cx, cy = self._canvas_to_world(event)
        node = self._find_node_at(cx, cy)
        if node is None or node.is_dir:
            return
        _, ext = os.path.splitext(node.name)
        if ext.lower() in PREVIEW_EXTS:
            self.show_preview(node)

    def _on_right_click(self, event) -> None:
        cx, cy = self._canvas_to_world(event)
        node = self._find_node_at(cx, cy)
        if node is None:
            return

        kind = node_kind(node)
        menu = tk.Menu(self._win, tearoff=0,
                       bg="#1e2a3a", fg="#a8c8f0",
                       activebackground="#2e4a6a", activeforeground="#ffffff",
                       font=self._file_font)

        if kind == "levels_dir":
            menu.add_command(label="Add Level", command=self._add_level)
            menu.add_separator()

        if kind in ("level", "scene"):
            menu.add_command(label=f"Add Scene to {node.name}",
                             command=lambda n=node: self._add_scene(n))
            menu.add_separator()

        if node.is_dir:
            menu.add_command(label="New File...",   command=lambda n=node: self._add_file(n))
            menu.add_command(label="New Folder...", command=lambda n=node: self._add_folder(n))
            menu.add_separator()

        menu.add_command(label=f"Delete {node.name}...",
                         command=lambda n=node: self._delete_node(n),
                         foreground="#e07070", activeforeground="#ff9090")
        menu.tk_popup(event.x_root, event.y_root)
