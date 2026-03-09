try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    TkRoot = TkinterDnD.Tk
    HAS_DND = True
except ImportError:
    import tkinter as tk
    TkRoot = tk.Tk
    HAS_DND = False
    DND_FILES = None
