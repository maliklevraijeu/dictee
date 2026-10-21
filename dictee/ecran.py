"""Les noms visibles à l'écran au moment où tu dictes.

Tu réponds à un mail de Khalil, ou tu parles d'une marque affichée dans la page : son nom est à l'écran,
mais pas forcément dans ta mémoire. À l'appui du raccourci, Dictée lit le texte de la fenêtre active
(le champ où tu écris, puis le document qui le contient, par l'accessibilité de Windows), en tire
les noms propres et les ajoute en tête des mots envoyés au moteur, pour cette dictée seulement.
Rien n'est gardé ni enregistré, et un champ de mot de passe n'est jamais lu.

Wispr Flow fait la même chose (vu dans son code le 21/10/2026), mais envoie le texte à son serveur
pour en extraire les noms. Ici l'extraction est locale : seuls 10 noms au plus partent au moteur.

`noms_propres()` est une fonction pure, testée dans tests/test_ecran.py.
"""
from __future__ import annotations

import re
import threading
from collections import Counter
from typing import Callable

from .mots_courants import courant

MAX_NOMS = 10
MAX_CARACTERES = 20000
_JETON = re.compile(r"[\w'’.@-]*\w")
_DEBUT = re.compile(r"(^|[.!?…:;]\s*|\n\s*|[«\"(]\s*)$")


def _fort(m: str) -> bool:
    """Un mot qui se voit comme un nom où qu'il soit : TrendTrack, IM8, levraijeu.com, SEO."""
    lettres = re.sub(r"[^\w]", "", m)
    if not any(c.isalpha() for c in lettres):
        return False
    if any(c.isdigit() for c in m):
        # IM8, 4Life, Web3 ; pas un code tiré au hasard (o7hm4N3) ni une vitesse (2X)
        return bool(re.fullmatch(r"[A-Za-z]{2,10}\d{1,3}|\d{1,3}[A-Za-z]{2,10}", m))
    if any(c.isupper() for c in m[1:]) and any(c.islower() for c in m):
        return True  # majuscule à l'intérieur : TrendTrack
    if re.fullmatch(r"[a-zA-Z0-9-]+\.[a-z]{2,6}", m):
        return True  # un site
    return 3 <= len(m) <= 6 and m.isupper()  # un sigle (deux lettres : trop de faux, « JO », « OK »)


def noms_propres(texte: str, n: int = MAX_NOMS) -> list[str]:
    """Les noms d'un texte affiché, les plus fréquents d'abord, puis les plus proches de la fin."""
    texte = (texte or "")[-MAX_CARACTERES:]
    jetons = []  # (mot, position, en début de phrase ?)
    for m in _JETON.finditer(texte):
        mot = m.group(0).strip(".'’-")
        if not mot or "@" in mot:
            continue
        debut = bool(_DEBUT.search(texte[max(0, m.start() - 4):m.start()])) or m.start() == 0
        jetons.append((mot, m.start(), m.end(), debut))
    # En début de phrase ou de ligne, la majuscule ne dit rien : les boutons d'une page (« Répondre »,
    # « Modifier ») s'y répètent à chaque message. Un nom porte sa majuscule AU MILIEU d'une phrase au
    # moins une fois, et ne s'écrit jamais en minuscules dans le même texte.
    au_milieu = Counter(mot for mot, _, _, debut in jetons if mot[:1].isupper() and not debut)
    minuscules = {mot.lower() for mot, _, _, _ in jetons if mot[:1].islower()}

    def candidat(mot: str) -> bool:
        if courant(mot) or len(mot) > 30:
            return False
        if _fort(mot):
            return True
        if not mot[:1].isupper() or len(mot) < 3 or mot.isupper():
            return False
        return au_milieu[mot] >= 1 and mot.lower() not in minuscules

    trouves: list[tuple[str, int]] = []
    i = 0
    while i < len(jetons):
        mot, pos, fin, debut = jetons[i]
        if not candidat(mot):
            i += 1
            continue
        groupe, j = [mot], i + 1
        # « Le Vrai Jeu » : un petit mot avec majuscule au milieu d'une ligne fait partie du nom
        if i and not jetons[i - 1][3] and jetons[i - 1][0][:1].isupper() and texte[jetons[i - 1][2]:pos] == " ":
            groupe.insert(0, jetons[i - 1][0])
            pos = jetons[i - 1][1]
        # des noms qui se suivent forment un seul nom : « Shaun Eng », « Mars Men »
        while (j < len(jetons) and len(groupe) < 3 and texte[fin:jetons[j][1]] == " "
               and jetons[j][0][:1].isupper() and not courant(jetons[j][0])):
            groupe.append(jetons[j][0])
            fin = jetons[j][2]
            j += 1
        trouves.append((" ".join(groupe), pos))
        i = j
    # « Vrai Jeu » trouvé là où « Le » ouvrait la ligne : il compte pour « Le Vrai Jeu »
    longs = {nom for nom, _ in trouves if " " in nom}
    trouves = [(next((l for l in longs if l != nom and l.endswith(" " + nom)), nom), pos) for nom, pos in trouves]
    compte = Counter(nom for nom, _ in trouves)
    dernier = {nom: pos for nom, pos in trouves}
    vus, sortie = set(), []
    for nom in sorted(compte, key=lambda x: (-compte[x], -dernier[x])):
        if nom.lower() not in vus:
            vus.add(nom.lower())
            sortie.append(nom)
    return sortie[:n]


def lire() -> str:
    """Le texte de la fenêtre active : son titre, le champ qui a le focus, puis le document qui le contient.
    Chaîne vide si rien n'est lisible. Appel bloquant : à lancer hors du fil de l'interface."""
    from .coller import titre_fenetre_active

    morceaux = [titre_fenetre_active()]
    try:
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
    except Exception:
        return morceaux[0]
    try:
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as U

        ua = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
        el = ua.GetFocusedElement()
        if not el or el.CurrentIsPassword:
            return morceaux[0]

        def texte_de(e) -> str:
            try:
                p = e.GetCurrentPattern(U.UIA_TextPatternId)
                if p:
                    return p.QueryInterface(U.IUIAutomationTextPattern).DocumentRange.GetText(MAX_CARACTERES) or ""
                p = e.GetCurrentPattern(U.UIA_ValuePatternId)
                if p:
                    return (p.QueryInterface(U.IUIAutomationValuePattern).CurrentValue or "")[-MAX_CARACTERES:]
            except Exception:
                return ""
            return ""

        morceaux.append(texte_de(el))
        # le document autour du champ (la page du navigateur, le fil de messages)
        marcheur = ua.ControlViewWalker
        e = el
        for _ in range(12):
            e = marcheur.GetParentElement(e)
            if not e:
                break
            if e.CurrentControlType == U.UIA_DocumentControlTypeId:
                morceaux.append(texte_de(e))
                break
    except Exception:
        pass
    finally:
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass
    return "\n".join(m for m in morceaux if m)


_occupe = threading.Lock()


def en_fond(rappel: Callable[[list[str]], None]) -> None:
    """Lit l'écran dans un fil à part et rend les noms trouvés (rien si la lecture échoue). Une appli figée
    peut bloquer la lecture : tant que la précédente n'a pas rendu, on n'en lance pas d'autre."""
    if not _occupe.acquire(blocking=False):
        return

    def courir():
        try:
            noms = noms_propres(lire())
        except Exception:
            noms = []
        finally:
            _occupe.release()
        if noms:
            rappel(noms)

    threading.Thread(target=courir, name="ecran", daemon=True).start()
