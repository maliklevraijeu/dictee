"""Apprendre de tes corrections.

Après un collage, Dictée relit pendant 45 secondes au plus la zone de texte où tu écris (celle qui a
le focus, par l'accessibilité de Windows), sans rien enregistrer d'autre que les mots corrigés. Si tu
remplaces « Kanvas » par « Canva », le bon mot entre dans ton vocabulaire.

Léger par conception : une seule lecture toutes les 0,8 s, de l'élément qui a le focus seulement,
arrêt dès que le focus change, jamais dans un champ de mot de passe, et une appli qui ne laisse pas
lire son texte n'est plus interrogée.

`corrections()` est une fonction pure, testée dans tests/test_apprentissage.py.
"""
from __future__ import annotations

import ctypes
import re
import threading
import time
from difflib import SequenceMatcher
from typing import Callable

from .mots_courants import courant

_MOT = re.compile(r"[\w'’@.-]*\w")
MAX_PAR_DICTEE = 4


def _mots(t: str) -> list[str]:
    return _MOT.findall(t or "")


def _commun(mot: str) -> bool:
    """« Fais-moi » est aussi courant que « fais » et « moi » : un mot composé de mots courants l'est."""
    return courant(mot) or all(courant(x) for x in re.split(r"[-'’]", mot) if x)


_TERMINAISON = re.compile(r"(ées|és|ée|ait|ais|ai|ent|er|ez|es|e|s|x|é)$")


def _accord(entendu: str, ecrit: str) -> bool:
    """« petit » corrigé en « petite », « allé » en « aller » : de la grammaire, pas une faute d'écoute.
    Un nom propre (majuscule) n'est jamais traité comme un accord : « Jordane » -> « Jordan » s'apprend."""
    a, b = entendu.lower().split(), ecrit.split()
    if len(a) != len(b) or any(m[:1].isupper() for m in b):
        return False
    racine = lambda m: _TERMINAISON.sub("", m.lower()) if len(m) > 3 else m.lower()
    return all(racine(x) == racine(y) for x, y in zip(a, b))


def _debut_de_phrase(mot: str, texte: str) -> bool:
    """Toutes les apparitions du mot sont en début de phrase : sa majuscule ne dit rien."""
    vus = [m.start() for m in re.finditer(r"(?<![\w'’])" + re.escape(mot) + r"(?![\w'’])", texte)]
    return bool(vus) and all(re.search(r"(^|[.!?…:]\s*|\n\s*)$", texte[:i]) for i in vus)


def corrections(colle: str, final: str) -> list[tuple[str, str]]:
    """Les mots que l'utilisateur a corrigés : [(« entendu », « écrit »)].
    On ne garde que les corrections d'orthographe (mots proches) de 1 à 3 mots, jamais les
    reformulations, les mots courants, les nombres."""
    a, b = _mots(colle), _mots(final)
    if not a or not b:
        return []
    al, bl = [x.lower() for x in a], [x.lower() for x in b]
    sm = SequenceMatcher(None, al, bl, autojunk=False)
    blocs = [m for m in sm.get_matching_blocks() if m.size]
    if not blocs or sum(m.size for m in blocs) < 0.5 * len(a):
        return []  # le texte collé n'est plus là (message envoyé, effacé) : rien à apprendre
    # La zone du champ qui correspond au texte collé, avec 2 mots de marge de chaque côté (une
    # correction peut couper un mot en deux : « Tomars » -> « to Mars »).
    debut = max(0, blocs[0].b - blocs[0].a - 2)
    fin = min(len(b), blocs[-1].b + blocs[-1].size + (len(a) - blocs[-1].a - blocs[-1].size) + 2)
    zone = b[debut:fin]
    sortie = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, al, [x.lower() for x in zone], autojunk=False).get_opcodes():
        if tag == "equal":
            # même mot, autre casse : « claude » corrigé en « Claude » (une marque, un prénom)
            for x, y in zip(a[i1:i2], zone[j1:j2]):
                if (x != y and y[:1].isupper() and not courant(y) and not any(c.isdigit() for c in y)
                        and not _debut_de_phrase(y, final)):
                    sortie.append((x, y))
            continue
        if tag != "replace":
            continue
        avant, apres = a[i1:i2], zone[j1:j2]
        entendu = " ".join(avant)
        # Aux bords du texte collé, la marge peut ajouter des mots qui ne sont pas la correction :
        # on garde le morceau le plus proche de ce qui a été entendu.
        if i2 == len(a) or i1 == 0:
            candidats = []
            for n in range(1, min(3, len(apres)) + 1):
                morceau = apres[:n] if i2 == len(a) else apres[-n:]
                candidats.append((SequenceMatcher(None, entendu.lower(), " ".join(morceau).lower()).ratio(), morceau))
            apres = max(candidats, key=lambda c: c[0])[1]
        if not (1 <= len(avant) <= 3 and 1 <= len(apres) <= 3):
            continue
        ecrit = " ".join(apres)
        if entendu == ecrit:
            continue
        if SequenceMatcher(None, entendu.lower(), ecrit.lower()).ratio() <= 0.5:
            continue  # trop différent : une reformulation, pas une faute d'écoute
        if all(_commun(m) for m in apres) or any(c.isdigit() for c in ecrit) or "@" in ecrit or "/" in ecrit:
            continue
        if _accord(entendu, ecrit):
            continue
        # une ou deux lettres tapées par accident devant ou derrière (« Parle-toi » -> « wParle-toi ») :
        # une faute de frappe, pas un mot à apprendre
        if 0 < len(ecrit) - len(entendu) <= 2 and (ecrit.endswith(entendu) or ecrit.startswith(entendu)):
            continue
        sortie.append((entendu, ecrit))
    # 4 au plus par dictée, les noms (majuscule) d'abord : au-delà, c'est un texte retravaillé, pas une
    # série de fautes d'écoute (Wispr Flow applique le même plafond, vu dans son code le 21/10)
    sortie.sort(key=lambda c: not c[1][:1].isupper())
    return sortie[:MAX_PAR_DICTEE]


def present(colle: str, texte: str) -> bool:
    """Le texte collé est-il encore (en bonne partie) dans le champ ?"""
    a = [m.lower() for m in _mots(colle)]
    if not a:
        return False
    vus = set(m.lower() for m in _mots(texte))
    return sum(1 for m in a if m in vus) >= 0.6 * len(a)


class Veilleur:
    """Surveille le champ après un collage et signale les corrections."""

    DUREE = 45.0
    PAS = 0.8

    def __init__(self, sur_corrections: Callable[[list[tuple[str, str]], str], None]):
        self.sur_corrections = sur_corrections
        # Applis qui ne laissent pas lire leur texte : écartées après 3 échecs de suite (un seul échec
        # peut venir d'une appli lente ou d'un très long document).
        self.echecs: dict[str, int] = {}
        self.applis_muettes: set[str] = set()
        self._en_cours: threading.Event | None = None

    def surveiller(self, colle: str, appli: str) -> None:
        if appli in self.applis_muettes:
            return
        if self._en_cours:
            self._en_cours.set()  # une nouvelle dictée remplace la surveillance précédente
        stop = threading.Event()
        self._en_cours = stop
        threading.Thread(target=self._courir, args=(colle, appli, stop), daemon=True).start()

    def _courir(self, colle: str, appli: str, stop: threading.Event) -> None:
        try:
            import comtypes
            import comtypes.client

            comtypes.CoInitialize()
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient as U

            ua = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)
        except Exception:
            return
        try:
            stop.wait(0.6)  # le collage a le temps de s'appliquer
            u32 = ctypes.windll.user32
            fenetre = u32.GetForegroundWindow()
            el = ua.GetFocusedElement()
            if not el or el.CurrentIsPassword:
                return
            ident = list(el.GetRuntimeId() or [])

            def lire(e) -> str | None:
                try:
                    p = e.GetCurrentPattern(U.UIA_ValuePatternId)
                    if p:
                        return p.QueryInterface(U.IUIAutomationValuePattern).CurrentValue
                    p = e.GetCurrentPattern(U.UIA_TextPatternId)
                    if p:
                        return p.QueryInterface(U.IUIAutomationTextPattern).DocumentRange.GetText(20000)
                except Exception:
                    return None
                return None

            texte = lire(el)
            if texte is None or not present(colle, texte):
                self.echecs[appli] = self.echecs.get(appli, 0) + 1
                if appli and self.echecs[appli] >= 3:
                    self.applis_muettes.add(appli)
                return
            self.echecs.pop(appli, None)
            dernier = texte
            fin = time.time() + self.DUREE
            while time.time() < fin and not stop.is_set():
                stop.wait(self.PAS)
                if u32.GetForegroundWindow() != fenetre:
                    break
                e = ua.GetFocusedElement()
                if not e or list(e.GetRuntimeId() or []) != ident:
                    break
                t = lire(e)
                if t is None or len(t) > 100000:
                    break
                if not present(colle, t):
                    break  # envoyé ou effacé : on garde la dernière version lue
                dernier = t
            trouvees = corrections(colle, dernier)
            if trouvees:
                self.sur_corrections(trouvees, appli)
        except Exception:
            return
        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass
