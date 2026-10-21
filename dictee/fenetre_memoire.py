"""La fenêtre « Ta mémoire » : ce que Dictée a appris de toi, et tes dernières dictées.
Tout se relit et se corrige ici : rien d'appris n'est caché. On y apprend aussi à Dictée, en une ligne,
des noms qu'elle ne connaît pas (« Mars Men, Canva ») ou ce qu'elle entend mal (« Mark Smead » -> « Mars Men »)."""
from __future__ import annotations

import json
import re
import tkinter as tk
from tkinter import ttk

from . import historique
from .langues import langue, t
from .memoire import Memoire

NOIR, SURFACE, OR, CREME, GRIS = "#0D0D0D", "#161615", "#C9A227", "#F5F1E8", "#9A958A"


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


def _champ(parent, indice: str, largeur: int) -> tk.Entry:
    """Un champ avec un exemple écrit en gris dedans, qui s'efface quand on clique."""
    e = tk.Entry(parent, bg=SURFACE, fg=GRIS, insertbackground=CREME, relief="flat", font=("Segoe UI", 10),
                 width=largeur, highlightthickness=1, highlightbackground="#3A3830", highlightcolor=OR)
    e.insert(0, indice)
    e.indice = indice

    def entrer(_e):
        if e.get() == indice:
            e.delete(0, "end")
            e.config(fg=CREME)

    e.bind("<FocusIn>", entrer)
    return e


def _valeur(e: tk.Entry) -> str:
    v = e.get().strip()
    return "" if v == e.indice else v


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
    h = f"{secondes / 3600:.1f} h"
    return h.replace(".", ",") if langue() == "fr" else h


def entete(stats: dict, appris: int) -> str:
    d, m = stats["dictees"], stats["mots_dictes"]
    if langue() == "en":
        return (f"{d:,} dictation{'s' if d != 1 else ''} · {m:,} word{'s' if m != 1 else ''} dictated · "
                f"{_duree(stats['secondes'])} of speech · {appris:,} word{'s' if appris != 1 else ''} learned")
    return " · ".join((_nombre(d, "dictée"), _nombre(m, "mot dicté"), _duree(stats["secondes"]) + " de parole",
                       _nombre(appris, "mot appris")))


def morceaux(saisie: str) -> list[str]:
    """« Mars Men, Canva ; Huel » -> trois mots : on colle une liste entière d'un coup."""
    return [m.strip() for m in re.split(r"[,;\n]+", saisie) if m.strip()]


def ouvrir(racine: tk.Tk, memoire: Memoire, sur_changement=lambda: None) -> tk.Toplevel:
    _style(racine)
    memoire.synchroniser()
    f = tk.Toplevel(racine)
    f.title("Dictée · " + t("memoire_titre"))
    f.configure(bg=NOIR, padx=20, pady=16)
    f.geometry("660x620")
    appris = sum(1 for m in memoire.mots.values() if m.get("source") in ("correction", "selection", "manuel"))
    tk.Label(f, text=t("memoire_titre"), fg=CREME, bg=NOIR, font=("Segoe UI Semibold", 16)).pack(anchor="w")
    tk.Label(f, text=entete(memoire.stats, appris), fg=GRIS, bg=NOIR, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 12))

    onglets = ttk.Notebook(f, style="D.TNotebook")
    onglets.pack(fill="both", expand=True)

    def sauver():
        memoire.enregistrer()
        sur_changement()

    # --- Tes mots -------------------------------------------------------------------------
    p1 = tk.Frame(onglets, bg=NOIR)
    onglets.add(p1, text=t("onglet_mots"))
    arbre = ttk.Treeview(p1, columns=("mot", "source", "fois"), show="headings", style="D.Treeview", height=10)
    for col, cle, l in (("mot", "col_mot", 300), ("source", "col_origine", 120), ("fois", "col_dit", 90)):
        arbre.heading(col, text=t(cle), anchor="w")
        arbre.column(col, width=l, anchor="w")
    arbre.pack(fill="both", expand=True, pady=(8, 8))

    def remplir_mots():
        arbre.delete(*arbre.get_children())
        for m in sorted(memoire.mots.values(), key=lambda m: -memoire._score(m)):
            source = m.get("source", "")
            arbre.insert("", "end", iid=m["texte"].lower(),
                         values=(m["texte"], t("source_" + source) if source in ("import", "manuel", "selection", "correction")
                                 else source, m.get("utilisations", 0)))

    bas = tk.Frame(p1, bg=NOIR)
    bas.pack(fill="x")
    saisie = _champ(bas, t("indice_mots"), 30)

    def ajouter():
        for mot in morceaux(_valeur(saisie)):
            memoire.ajouter_mot(mot, "manuel")
        sauver()
        remplir_mots()
        saisie.delete(0, "end")

    def retirer():
        for iid in arbre.selection():
            memoire.oublier_mot(iid)
        sauver()
        remplir_mots()

    # le bouton d'abord, à droite : le champ prend la place qui reste, quelle que soit la langue
    _bouton(bas, t("ajouter"), ajouter, principal=True).pack(side="right", padx=(6, 0))
    saisie.pack(side="left", fill="x", expand=True, ipady=4)
    _bouton(p1, t("retirer"), retirer).pack(anchor="e", pady=(6, 0))
    saisie.bind("<Return>", lambda _e: ajouter())

    # --- Corrections ------------------------------------------------------------------------
    p2 = tk.Frame(onglets, bg=NOIR)
    onglets.add(p2, text=t("onglet_corrections"))
    tk.Label(p2, text=t("aide_corrections"), fg=GRIS, bg=NOIR, font=("Segoe UI", 9), wraplength=600, justify="left").pack(anchor="w", pady=(8, 0))
    arbre2 = ttk.Treeview(p2, columns=("entendu", "ecrit", "fois"), show="headings", style="D.Treeview", height=8)
    for col, cle, l in (("entendu", "col_entendu", 230), ("ecrit", "col_ecrit", 230), ("fois", "col_fois", 70)):
        arbre2.heading(col, text=t(cle), anchor="w")
        arbre2.column(col, width=l, anchor="w")
    arbre2.pack(fill="both", expand=True, pady=8)

    def remplir_corrections():
        arbre2.delete(*arbre2.get_children())
        for c in sorted(memoire.corrections.values(), key=lambda c: -c["fois"]):
            arbre2.insert("", "end", iid=c["entendu"].lower(), values=(c["entendu"], c["ecrit"], c["fois"]))

    ligne = tk.Frame(p2, bg=NOIR)
    ligne.pack(fill="x")
    entendu = _champ(ligne, t("indice_entendu"), 20)
    ecrit = _champ(ligne, t("indice_ecrit"), 20)

    def ajouter_correction():
        a, b = _valeur(entendu), _valeur(ecrit)
        if a and b and memoire.ajouter_correction(a, b):
            sauver()
            remplir_corrections()
            remplir_mots()
            entendu.delete(0, "end")
            ecrit.delete(0, "end")

    def retirer_correction():
        for iid in arbre2.selection():
            memoire.oublier_correction(iid)
        sauver()
        remplir_corrections()

    _bouton(ligne, t("ajouter"), ajouter_correction, principal=True).pack(side="right", padx=(6, 0))
    entendu.pack(side="left", fill="x", expand=True, ipady=4)
    tk.Label(ligne, text="→", fg=GRIS, bg=NOIR, font=("Segoe UI", 11)).pack(side="left", padx=6)
    ecrit.pack(side="left", fill="x", expand=True, ipady=4)
    _bouton(p2, t("retirer"), retirer_correction).pack(anchor="e", pady=(6, 0))
    ecrit.bind("<Return>", lambda _e: ajouter_correction())

    # --- Dernières dictées -----------------------------------------------------------------
    p3 = tk.Frame(onglets, bg=NOIR)
    onglets.add(p3, text=t("onglet_dictees"))
    arbre3 = ttk.Treeview(p3, columns=("quand", "texte"), show="headings", style="D.Treeview", height=12)
    arbre3.heading("quand", text=t("col_quand"), anchor="w")
    arbre3.heading("texte", text=t("col_texte"), anchor="w")
    arbre3.column("quand", width=120, anchor="w")
    arbre3.column("texte", width=460, anchor="w")
    arbre3.pack(fill="both", expand=True, pady=8)
    textes = {}
    try:
        lignes = historique.FICHIER.read_text(encoding="utf-8").splitlines()[-50:]
    except OSError:
        lignes = []
    for i, brut in enumerate(reversed(lignes)):
        try:
            d = json.loads(brut)
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

    _bouton(p3, t("copier"), copier, principal=True).pack(anchor="e")

    remplir_mots()
    remplir_corrections()
    f.lift()
    f.focus_force()
    return f
