"""La pastille à l'écran : en bas au centre de l'écran où tu travailles.
Elle ne prend jamais le focus et laisse passer les clics : le curseur reste dans ton appli.

États : écoute (barres qui suivent ta voix), mains libres (cadenas), transcription (points),
message court (« Rien entendu », « Copié, Ctrl+V »...)."""
from __future__ import annotations

import ctypes
import math
import tkinter as tk
from ctypes import wintypes

u32 = ctypes.WinDLL("user32", use_last_error=True)

NOIR = "#0D0D0D"
OR = "#C9A227"
OR_CLAIR = "#E5C76B"
CREME = "#F5F1E8"
GRIS = "#8C877D"
ROUGE = "#E8836E"
MAGIQUE = "#010203"  # couleur rendue transparente (coins arrondis)

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE, WS_EX_LAYERED = 0x80, 0x8, 0x20, 0x08000000, 0x80000


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]


u32.GetForegroundWindow.restype = wintypes.HWND
u32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
u32.MonitorFromWindow.restype = wintypes.HANDLE
u32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
u32.GetParent.argtypes = [wintypes.HWND]
u32.GetParent.restype = wintypes.HWND
u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
u32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]


def zone_de_travail() -> tuple[int, int, int, int]:
    """La zone utile (sans la barre des tâches) de l'écran où est l'appli active."""
    mon = u32.MonitorFromWindow(u32.GetForegroundWindow(), 2)  # MONITOR_DEFAULTTONEAREST
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if mon and u32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        r = mi.rcWork
        return r.left, r.top, r.right, r.bottom
    return 0, 0, u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)


class Pilule:
    def __init__(self, racine: tk.Tk, niveau=lambda: 0.0):
        self.racine = racine
        self.niveau = niveau
        self.echelle = max(1.0, racine.winfo_fpixels("1i") / 96)
        self.f = tk.Toplevel(racine)
        self.f.withdraw()
        self.f.overrideredirect(True)
        self.f.attributes("-topmost", True)
        self.f.configure(bg=MAGIQUE)
        self.f.attributes("-transparentcolor", MAGIQUE)
        self.c = tk.Canvas(self.f, bg=MAGIQUE, highlightthickness=0, bd=0)
        self.c.pack(fill="both", expand=True)
        self.etat = "cache"
        self.texte = ""
        self.t = 0
        self._apres_cache = None
        self._barres = [0.0] * 9
        # La fenêtre est affichée UNE fois, invisible et hors de l'écran, puis on ne fait plus que la
        # rendre visible ou invisible : afficher une fenêtre (deiconify) peut voler le focus de l'appli
        # où tu écris. Le style « jamais activée » est posé dès le départ.
        avant = u32.GetForegroundWindow()
        self.f.attributes("-alpha", 0.0)
        self.f.geometry("10x10+-20000+-20000")
        self.f.update_idletasks()
        self._sans_focus()
        self.f.deiconify()
        self.f.update_idletasks()
        self._sans_focus()
        if avant and u32.GetForegroundWindow() != avant:
            u32.SetForegroundWindow(avant)
        self._animer()

    def _s(self, v: float) -> int:
        return int(round(v * self.echelle))

    def _sans_focus(self) -> None:
        hwnd = u32.GetParent(self.f.winfo_id()) or self.f.winfo_id()
        style = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE
                           | WS_EX_TRANSPARENT | WS_EX_LAYERED)

    def _placer(self, largeur: int, hauteur: int) -> None:
        g, h, d, b = zone_de_travail()
        x = g + (d - g - largeur) // 2
        y = b - hauteur - self._s(18)
        self.f.geometry(f"{largeur}x{hauteur}+{x}+{y}")

    # --- API ------------------------------------------------------------
    def ecoute(self, mains_libres: bool = False) -> None:
        self._montrer("libres" if mains_libres else "ecoute")

    def transcription(self) -> None:
        self._montrer("transcription")

    def message(self, texte: str, duree_ms: int = 1800, erreur: bool = False) -> None:
        self.texte = texte
        self._montrer("erreur" if erreur else "message")
        self._apres_cache = self.racine.after(duree_ms, self.cacher)

    def cacher(self) -> None:
        self.etat = "cache"
        self.f.attributes("-alpha", 0.0)
        self.f.geometry("10x10+-20000+-20000")

    def _montrer(self, etat: str) -> None:
        if self._apres_cache:
            self.racine.after_cancel(self._apres_cache)
            self._apres_cache = None
        self.etat = etat
        if etat in ("message", "erreur"):
            largeur = self._s(24) + int(len(self.texte) * 7.4 * self.echelle) + self._s(24)
        else:
            largeur = self._s(118 if etat != "libres" else 136)
        self._placer(largeur, self._s(36))
        self.f.attributes("-topmost", True)
        self.f.update_idletasks()
        self._dessiner()
        self.f.attributes("-alpha", 0.97)

    # --- dessin ----------------------------------------------------------
    def _pilule(self, l: int, h: int, bord: str) -> None:
        r = h // 2
        c = self.c
        c.create_oval(0, 0, h, h, fill=NOIR, outline="")
        c.create_oval(l - h, 0, l, h, fill=NOIR, outline="")
        c.create_rectangle(r, 0, l - r, h, fill=NOIR, outline="")
        c.create_arc(1, 1, h - 1, h - 1, start=90, extent=180, style="arc", outline=bord)
        c.create_arc(l - h + 1, 1, l - 1, h - 1, start=-90, extent=180, style="arc", outline=bord)
        c.create_line(r, 1, l - r, 1, fill=bord)
        c.create_line(r, h - 1, l - r, h - 1, fill=bord)

    def _dessiner(self) -> None:
        if self.etat == "cache":
            return
        c = self.c
        c.delete("all")
        l, h = self.f.winfo_width(), self.f.winfo_height()
        if l < 10:
            l, h = self._s(118), self._s(36)
        bord = ROUGE if self.etat == "erreur" else ("#3A3420" if self.etat != "libres" else OR)
        self._pilule(l, h, bord)
        mid = h / 2
        if self.etat in ("ecoute", "libres"):
            n = len(self._barres)
            niv = self.niveau()
            for i in range(n):
                cible = niv * (0.55 + 0.45 * math.sin(self.t * 0.35 + i * 0.9)) * (1 - abs(i - n // 2) / (n + 2))
                self._barres[i] = 0.55 * self._barres[i] + 0.45 * cible
            x0 = l / 2 - (n - 1) * self._s(4.5) - (self._s(9) if self.etat == "libres" else 0)
            for i, v in enumerate(self._barres):
                hh = max(self._s(2), v * h * 0.9)
                x = x0 + i * self._s(9)
                c.create_line(x, mid - hh / 2, x, mid + hh / 2, fill=OR_CLAIR, width=self._s(3), capstyle="round")
            if self.etat == "libres":
                x = l - self._s(26)
                c.create_rectangle(x, mid - self._s(1), x + self._s(10), mid + self._s(7), fill=OR, outline="")
                c.create_arc(x + self._s(1.5), mid - self._s(8), x + self._s(8.5), mid + self._s(4), start=0, extent=180,
                             style="arc", outline=OR, width=self._s(2))
        elif self.etat == "transcription":
            for i in range(3):
                phase = (self.t * 0.25 - i * 0.8)
                a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(phase))
                couleur = OR if a > 0.75 else ("#8A7020" if a > 0.5 else "#4A3E18")
                x = l / 2 + (i - 1) * self._s(13)
                r = self._s(3.2)
                c.create_oval(x - r, mid - r, x + r, mid + r, fill=couleur, outline="")
        else:
            c.create_text(l / 2, mid, text=self.texte, fill=ROUGE if self.etat == "erreur" else CREME,
                          font=("Segoe UI", 10, "bold" if self.etat == "erreur" else "normal"))

    def _animer(self) -> None:
        self.t += 1
        if self.etat in ("ecoute", "libres", "transcription"):
            self._dessiner()
        self.racine.after(33, self._animer)
