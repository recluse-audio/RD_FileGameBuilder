import json
import os

from .constants import PAD, GAP, HEADER_H, FILE_H, MIN_W, COLORS, EXT_COLORS


def _friendly_name(path: str, dir_name: str) -> str:
    """Return the friendly name from level_info.json or scene_info.json, falling back to dir_name."""
    for info_file in ("level_info.json", "scene_info.json"):
        info_path = os.path.join(path, info_file)
        if os.path.isfile(info_path):
            try:
                data = json.loads(open(info_path, encoding="utf-8").read())
                name = data.get("name", "").strip()
                if name:
                    return name
            except Exception:
                pass
    return dir_name


def ext_color(name: str) -> str:
    _, ext = os.path.splitext(name)
    return EXT_COLORS.get(ext.lower(), COLORS["ext_other"])


def node_kind(node) -> str:
    if node.name == "LEVELS":
        return "levels_dir"
    if node.name.startswith("LEVEL_"):
        return "level"
    if node.name.startswith("SCENE_"):
        return "scene"
    return "other"


def _next_numbered_dir(parent_path: str, prefix: str) -> tuple[str, int]:
    existing = []
    for entry in os.scandir(parent_path):
        if entry.is_dir() and entry.name.startswith(prefix):
            try:
                existing.append(int(entry.name[len(prefix):]))
            except ValueError:
                pass
    n = max(existing, default=0) + 1
    return f"{prefix}{n}", n


def _scene_info_for_png(node) -> str | None:
    if node.is_dir:
        return None
    _, ext = os.path.splitext(node.name)
    if ext.lower() != ".png":
        return None
    parent = os.path.dirname(node.path)
    if not os.path.basename(parent).startswith("SCENE_"):
        return None
    info = os.path.join(parent, "scene_info.json")
    return info if os.path.isfile(info) else None


class Node:
    def __init__(self, name: str, path: str, is_dir: bool):
        self.name         = name   # always the filesystem entry name
        self.display_name = name   # friendly name shown in the GUI
        self.path         = path
        self.is_dir       = is_dir
        self.children: list["Node"] = []

    def add(self, child: "Node") -> None:
        self.children.append(child)


def build_tree(path: str, name: str | None = None) -> Node:
    name = name or os.path.basename(path)
    node = Node(name, path, os.path.isdir(path))
    if node.is_dir:
        if name.startswith("LEVEL_") or name.startswith("SCENE_"):
            node.display_name = _friendly_name(path, name)
        try:
            entries = sorted(os.scandir(path), key=lambda e: (not e.is_dir(), e.name.lower()))
            for entry in entries:
                node.add(build_tree(entry.path, entry.name))
        except PermissionError:
            pass
    return node


def measure(node: Node, canvas_font, file_font, collapsed: set | None = None) -> tuple[int, int]:
    if not node.is_dir:
        tw = file_font.measure(node.name) + 24
        return max(tw, MIN_W), FILE_H

    if collapsed and node.path in collapsed:
        label_w = canvas_font.measure(node.display_name) + 8
        return max(label_w + PAD * 2, MIN_W), HEADER_H

    child_sizes = [measure(c, canvas_font, file_font, collapsed) for c in node.children]
    inner_w = max((cw for cw, _ in child_sizes), default=0)
    inner_w = max(inner_w, canvas_font.measure(node.display_name) + 8)
    inner_h = sum(ch for _, ch in child_sizes) + GAP * max(len(node.children) - 1, 0)
    return max(inner_w + PAD * 2, MIN_W), HEADER_H + PAD + inner_h + PAD


def draw_node(canvas, node: Node, x: int, y: int, w: int, h: int,
              canvas_font, file_font, hit_areas: list,
              collapsed: set | None = None, depth: int = 0) -> None:
    if not node.is_dir:
        canvas.create_rectangle(x, y, x + w, y + h,
                                 fill=COLORS["file_bg"], outline=COLORS["border"], width=1)
        dot_color = ext_color(node.name)
        canvas.create_oval(x + 6, y + h // 2 - 4, x + 14, y + h // 2 + 4,
                            fill=dot_color, outline="")
        canvas.create_text(x + 20, y + h // 2, text=node.name,
                            anchor="w", fill=COLORS["file_text"], font=file_font)
        hit_areas.append((x, y, x + w, y + h, node))
        return

    is_collapsed = bool(collapsed and node.path in collapsed)
    indicator    = "\u25b6" if is_collapsed else "\u25bc"  # ▶ / ▼

    canvas.create_rectangle(x, y, x + w, y + h,
                             fill=COLORS["folder_bg"], outline=COLORS["border"], width=1)
    canvas.create_rectangle(x, y, x + w, y + HEADER_H,
                             fill=COLORS["folder_hdr"], outline="", width=0)
    canvas.create_text(x + PAD, y + HEADER_H // 2, text=node.display_name,
                        anchor="w", fill=COLORS["folder_text"], font=canvas_font)
    canvas.create_text(x + w - PAD, y + HEADER_H // 2, text=indicator,
                        anchor="e", fill="#6a9abf", font=canvas_font)

    hit_areas.append((x, y, x + w, y + HEADER_H, node))

    if is_collapsed:
        return

    cx = x + PAD
    cy = y + HEADER_H + PAD
    child_sizes = [measure(c, canvas_font, file_font, collapsed) for c in node.children]
    inner_w = w - PAD * 2
    for child, (cw, ch) in zip(node.children, child_sizes):
        draw_node(canvas, child, cx, cy, inner_w, ch, canvas_font, file_font,
                  hit_areas, collapsed, depth + 1)
        cy += ch + GAP
