"""Premier lancement : une petite fenêtre pour coller sa clé. Rien d'autre à configurer."""
from __future__ import annotations

import tkinter as tk
import webbrowser

from . import coffre
from .langues import t

NOIR, SURFACE, OR, CREME, GRIS = "#0D0D0D", "#161615", "#C9A227", "#F5F1E8", "#9A958A"
LIEN_ELEVEN = "https://elevenlabs.io/app/settings/api-keys"
LIEN_GEMINI = "https://aistudio.google.com/apikey"


def demander_cles(racine: tk.Tk) -> bool:
    """Ouvre la fenêtre et attend. Renvoie True si au moins une clé a été enregistrée."""
    f = tk.Toplevel(racine)
    f.title("Dictée")
    f.configure(bg=NOIR, padx=28, pady=24)
    f.resizable(False, False)
    f.attributes("-topmost", True)
    police = ("Segoe UI", 10)
    tk.Label(f, text="Dictée", fg=CREME, bg=NOIR, font=("Segoe UI Semibold", 18)).pack(anchor="w")
    tk.Label(f, text=t("accueil_sous_titre"), fg=GRIS, bg=NOIR,
             font=police).pack(anchor="w", pady=(2, 4))
    tk.Label(f, text=t("accueil_cle"),
             fg=GRIS, bg=NOIR, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 18))

    champs = {}
    for cle, titre, lien, aide in (
        ("elevenlabs", t("cle_eleven"), LIEN_ELEVEN, t("aide_eleven")),
        ("gemini", t("cle_gemini"), LIEN_GEMINI, t("aide_gemini")),
    ):
        tk.Label(f, text=titre, fg=CREME, bg=NOIR, font=("Segoe UI Semibold", 10)).pack(anchor="w")
        e = tk.Entry(f, show="•", width=48, bg=SURFACE, fg=CREME, insertbackground=CREME, relief="flat",
                     font=police, highlightthickness=1, highlightbackground="#3A3420", highlightcolor=OR)
        e.pack(anchor="w", ipady=6, pady=(4, 2))
        ligne = tk.Frame(f, bg=NOIR)
        ligne.pack(anchor="w", pady=(0, 14))
        tk.Label(ligne, text=aide + " · ", fg=GRIS, bg=NOIR, font=("Segoe UI", 9)).pack(side="left")
        l = tk.Label(ligne, text=t("obtenir_cle"), fg=OR, bg=NOIR, font=("Segoe UI", 9, "underline"), cursor="hand2")
        l.pack(side="left")
        l.bind("<Button-1>", lambda _e, u=lien: webbrowser.open(u))
        champs[cle] = e

    resultat = {"ok": False}
    erreur = tk.Label(f, text="", fg="#E8836E", bg=NOIR, font=("Segoe UI", 9))
    erreur.pack(anchor="w")

    def valider(*_):
        cles = {k: e.get().strip() for k, e in champs.items() if e.get().strip()}
        if not cles:
            erreur.config(text=t("aucune_cle"))
            return
        coffre.ecrire({**coffre.lire(), **cles})
        resultat["ok"] = True
        f.destroy()

    tk.Button(f, text=t("commencer"), command=valider, bg=OR, fg="#151208", activebackground="#E5C76B",
              relief="flat", font=("Segoe UI Semibold", 10), padx=18, pady=6, cursor="hand2").pack(anchor="w", pady=(8, 0))
    tk.Label(f, text=t("cles_chiffrees"), fg=GRIS, bg=NOIR, font=("Segoe UI", 8)).pack(anchor="w", pady=(12, 0))
    f.bind("<Return>", valider)
    f.protocol("WM_DELETE_WINDOW", f.destroy)
    champs["elevenlabs"].focus_set()
    f.wait_window()
    return resultat["ok"]
