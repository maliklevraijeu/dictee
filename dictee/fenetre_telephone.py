"""La fenêtre « Dicter depuis ton téléphone » : le QR code à scanner, et de quoi couper."""
from __future__ import annotations

import base64
import tkinter as tk
from typing import Callable

from .telephone import qr_png

NOIR, SURFACE, OR, CREME, GRIS = "#0D0D0D", "#161615", "#C9A227", "#F5F1E8", "#9A958A"


def ouvrir(racine: tk.Misc, adresse: str, sur_couper: Callable[[], None], note: str = "") -> tk.Toplevel:
    f = tk.Toplevel(racine)
    f.title("Dictée · Téléphone")
    f.configure(bg=NOIR, padx=28, pady=22)
    f.resizable(False, False)
    tk.Label(f, text="Dicter depuis ton téléphone", fg=CREME, bg=NOIR, font=("Segoe UI Semibold", 16)).pack(anchor="w")
    tk.Label(f, text="Scanne avec l'appareil photo, sur le même Wi-Fi que ce PC.", fg=GRIS, bg=NOIR,
             font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 14))
    image = tk.PhotoImage(data=base64.b64encode(qr_png(adresse)).decode())
    qr = tk.Label(f, image=image, bg=NOIR)
    qr.image = image  # garder une référence, sinon Tk efface l'image
    qr.pack()
    tk.Label(f, text="Touche le micro du clavier, parle, puis « Envoyer au PC » :\nle texte se colle là où est ton curseur.",
             fg=CREME, bg=NOIR, font=("Segoe UI", 10), justify="left").pack(anchor="w", pady=(14, 4))
    if note:
        tk.Label(f, text=note, fg="#E8836E", bg=NOIR, font=("Segoe UI", 9), justify="left",
                 wraplength=380).pack(anchor="w", pady=(4, 0))
    tk.Label(f, text=adresse.split("?")[0], fg=GRIS, bg=NOIR, font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 12))

    def couper():
        sur_couper()
        f.destroy()

    tk.Button(f, text="Couper la dictée par téléphone", command=couper, relief="flat", cursor="hand2", bg=SURFACE,
              fg=CREME, activebackground="#24231F", font=("Segoe UI", 9), padx=12, pady=5).pack(anchor="w")
    f.lift()
    f.focus_force()
    return f
