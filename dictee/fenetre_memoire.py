"""La fenêtre « Ta mémoire » : ce que Dictée a appris de toi, et tes dernières dictées.
Tout se relit et se corrige ici : rien d'appris n'est caché."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk

from . import historique
from .memoire import Memoire

NOIR, SURFACE, OR, CREME, GRIS = "#0D0D0D", "#161615", "#C9A227", "#F5F1E8", "#9A958A"
SOURCES = {"import": "importé", "manuel": "ajouté", "selection": "retenu", "correction": "appris"}


def _style(racine: tk.Misc) -> None:
    s = ttk.Style(racine)
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass
    s.configure("D.Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=CREME, rowheight=24,
                borderwidth=0, font=("Segoe UI", 10))
    s.configure("D.Treeview.Heading", background=NOIR, foreground=GRIS, borderwidth=0, font=("Segoe UI", 9))
    s.map("D.Treeview", background=[("selected", "#3A3420")], foreground=[("selected", CREME)])
    s.configure("D.TNotebook", background=NOIR, borderwidth=0)
    s.configure("D.TNotebook.Tab", background=NOIR, foreground=GRIS, padding=(14, 6), font=("Segoe UI", 10))
    s.map("D.TNotebook.Tab", background=[("selected", SURFACE)], foreground=[("selected", CREME)])


def _bouton(parent, texte, commande, principal=False):
    return tk.Button(parent, text=texte, command=commande, relief="flat", cursor="hand2",
                     bg=OR if principal else SURFACE, fg="#151208" if principal else CREME,
                     activebackground="#E5C76B" if principal else "#24231F", font=("Segoe UI", 9), padx=12, pady=4)


def _nombre(n: int, mots: str) -> str:
    # « 2 mots dictés » : chaque mot prend la marque du pluriel (sauf ceux déjà en -s, comme « appris »)
    if n > 1:
        mots = " ".join(m if m.endswith("s") else m + "s" for m in mots.split())
    return f"{n:,}".replace(",", " ") + " " + mots


def _duree(secondes: float) -> str:
    if secondes < 60:
        return f"{secondes:.0f} s"
    if secondes < 3600:
        return f"{secondes / 60:.0f} min"
    return f"{secondes / 3600:.1f} h".replace(".", ",")


def ouvrir(racine: tk.Tk, memoire: Memoire, sur_changement=lambda: None) -> tk.Toplevel:
    _style(racine)
    f = tk.Toplevel(racine)
    f.title("Dictée · Ta mémoire")
    f.configure(bg=NOIR, padx=20, pady=16)
    f.geometry("640x560")
    s = memoire.stats
    appris = sum(1 for m in memoire.mots.values() if m.get("source") in ("correction", "selection", "manuel"))
    entete = " · ".join((_nombre(s["dictees"], "dictée"), _nombre(s["mots_dictes"], "mot dicté"),
                         _duree(s["secondes"]) + " de parole", _nombre(appris, "mot appris")))
    tk.Label(f, text="Ta mémoire", fg=CREME, bg=NOIR, font=("Segoe UI Semibold", 16)).pack(anchor="w")
    tk.Label(f, text=entete, fg=GRIS, bg=NOIR, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 12))

    onglets = ttk.Notebook(f, style="D.TNotebook")
    onglets.pack(fill="both", expand=True)

    # --- Tes mots -------------------------------------------------------------------------
    p1 = tk.Frame(onglets, bg=NOIR)
    onglets.add(p1, text="Tes mots")
    arbre = ttk.Treeview(p1, columns=("mot", "source", "fois"), show="headings", style="D.Treeview", height=12)
    for col, titre, l in (("mot", "Mot", 300), ("source", "Origine", 120), ("fois", "Dit", 90)):
        arbre.heading(col, text=titre, anchor="w")
        arbre.column(col, width=l, anchor="w")
    arbre.pack(fill="both", expand=True, pady=(8, 8))

    def remplir_mots():
        arbre.delete(*arbre.get_children())
        for m in sorted(memoire.mots.values(), key=lambda m: -memoire._score(m)):
            arbre.insert("", "end", iid=m["texte"].lower(),
                         values=(m["texte"], SOURCES.get(m.get("source", ""), m.get("source", "")), m.get("utilisations", 0)))

    bas = tk.Frame(p1, bg=NOIR)
    bas.pack(fill="x")
    saisie = tk.Entry(bas, bg=SURFACE, fg=GRIS, insertbackground=CREME, relief="flat", font=("Segoe UI", 10), width=26,
                      highlightthickness=1, highlightbackground="#3A3830", highlightcolor=OR)
    saisie.pack(side="left", ipady=4)
    INDICE = "un nom, une marque…"
    saisie.insert(0, INDICE)

    def entrer(_e):
        if saisie.get() == INDICE:
            saisie.delete(0, "end")
            saisie.config(fg=CREME)

    saisie.bind("<FocusIn>", entrer)

    def ajouter():
        if saisie.get() != INDICE and memoire.ajouter_mot(saisie.get(), "manuel"):
            memoire.enregistrer()
            sur_changement()
            remplir_mots()
        saisie.delete(0, "end")

    def retirer():
        for iid in arbre.selection():
            memoire.oublier_mot(iid)
        memoire.enregistrer()
        sur_changement()
        remplir_mots()

    _bouton(bas, "Ajouter", ajouter, principal=True).pack(side="left", padx=6)
    _bouton(bas, "Retirer la sélection", retirer).pack(side="right")
    saisie.bind("<Return>", lambda _e: ajouter())

    # --- Corrections apprises ---------------------------------------------------------------
    p2 = tk.Frame(onglets, bg=NOIR)
    onglets.add(p2, text="Corrections")
    tk.Label(p2, text="Remplacées automatiquement à partir de 2 corrections identiques.", fg=GRIS, bg=NOIR,
             font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))
    arbre2 = ttk.Treeview(p2, columns=("entendu", "ecrit", "fois"), show="headings", style="D.Treeview", height=12)
    for col, titre, l in (("entendu", "Entendu", 220), ("ecrit", "Écrit", 220), ("fois", "Fois", 70)):
        arbre2.heading(col, text=titre, anchor="w")
        arbre2.column(col, width=l, anchor="w")
    arbre2.pack(fill="both", expand=True, pady=8)

    def remplir_corrections():
        arbre2.delete(*arbre2.get_children())
        for c in sorted(memoire.corrections.values(), key=lambda c: -c["fois"]):
            arbre2.insert("", "end", iid=c["entendu"].lower(), values=(c["entendu"], c["ecrit"], c["fois"]))

    def retirer_correction():
        for iid in arbre2.selection():
            memoire.oublier_correction(iid)
        memoire.enregistrer()
        sur_changement()
        remplir_corrections()

    _bouton(p2, "Retirer la sélection", retirer_correction).pack(anchor="e")

    # --- Dernières dictées -----------------------------------------------------------------
    p3 = tk.Frame(onglets, bg=NOIR)
    onglets.add(p3, text="Dernières dictées")
    arbre3 = ttk.Treeview(p3, columns=("quand", "texte"), show="headings", style="D.Treeview", height=12)
    arbre3.heading("quand", text="Quand", anchor="w")
    arbre3.heading("texte", text="Texte", anchor="w")
    arbre3.column("quand", width=120, anchor="w")
    arbre3.column("texte", width=440, anchor="w")
    arbre3.pack(fill="both", expand=True, pady=8)
    textes = {}
    try:
        lignes = historique.FICHIER.read_text(encoding="utf-8").splitlines()[-50:]
    except OSError:
        lignes = []
    for i, ligne in enumerate(reversed(lignes)):
        try:
            d = json.loads(ligne)
        except ValueError:
            continue
        if d.get("texte"):
            textes[str(i)] = d["texte"]
            arbre3.insert("", "end", iid=str(i), values=(d.get("quand", "")[5:16], d["texte"][:120]))

    def copier():
        sel = arbre3.selection()
        if sel:
            f.clipboard_clear()
            f.clipboard_append(textes[sel[0]])

    _bouton(p3, "Copier", copier, principal=True).pack(anchor="e")

    remplir_mots()
    remplir_corrections()
    f.lift()
    f.focus_force()
    return f
