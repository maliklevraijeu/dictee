"""La mémoire de Dictée : ton vocabulaire et les corrections apprises, dans un fichier lisible
(%APPDATA%\\Dictee\\memoire.json) que tu peux relire et corriger.

- Les mots sont classés tout seuls : ceux que tu dis le plus et le plus récemment passent en tête,
  car le moteur en direct n'en reçoit que 50 par dictée.
- Une correction (« Kanvas » corrigé en « Canva ») ajoute tout de suite le bon mot au
  vocabulaire ; le remplacement automatique ne s'active qu'à la 2e fois (on ne généralise pas
  sur une seule correction, qui peut être une reformulation).
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from pathlib import Path

from .config import DOSSIER
from .mots_courants import courant

FICHIER = DOSSIER / "memoire.json"
SEUIL_REMPLACEMENT = 2
DEMI_VIE_JOURS = 30


def _maintenant() -> float:
    return time.time()


class Memoire:
    def __init__(self, fichier: Path = FICHIER):
        self.fichier = fichier
        self.mots: dict[str, dict] = {}  # clé : mot en minuscules
        self.corrections: dict[str, dict] = {}  # clé : « entendu » en minuscules
        self.refuses: set[str] = set()  # mots retirés par l'utilisateur : jamais ré-appris tout seuls
        self.stats = {"dictees": 0, "mots_dictes": 0, "secondes": 0.0, "depuis": _maintenant()}
        self._verrou = threading.Lock()
        self._date_fichier = 0.0  # date du fichier quand on l'a lu ou écrit pour la dernière fois
        self.charger()

    # --- fichier --------------------------------------------------------------
    def _date(self) -> float:
        try:
            return self.fichier.stat().st_mtime
        except OSError:
            return 0.0

    def synchroniser(self) -> None:
        """Le fichier a changé ailleurs (fenêtre « Ta mémoire » d'un autre lancement, commande
        `python -m dictee ajouter`, retouche à la main) : on le relit avant d'y toucher."""
        if self._date() != self._date_fichier:
            self.charger()

    def charger(self) -> None:
        self.mots, self.corrections, self.refuses = {}, {}, set()
        self._date_fichier = self._date()
        if not self.fichier.exists():
            return
        try:
            d = json.loads(self.fichier.read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                raise ValueError("pas un objet JSON")
        except (OSError, ValueError):
            # Fichier abîmé (souvent une retouche à la main) : on le met de côté au lieu de l'écraser
            # à la prochaine sauvegarde, pour que rien de ce qui a été appris ne soit perdu.
            try:
                os.replace(self.fichier, self.fichier.with_name(time.strftime("memoire-abimee-%Y%m%d-%H%M%S.json")))
            except OSError:
                pass
            return
        for m in d.get("mots", []):
            if isinstance(m, str):  # une simple liste de mots écrite à la main
                m = {"texte": m, "source": "manuel"}
            if isinstance(m, dict) and isinstance(m.get("texte"), str) and m["texte"].strip():
                m = {"source": "manuel", "ajoute": _maintenant(), "utilisations": 0, "poids": 0, "derniere": 0.0, **m}
                self.mots[m["texte"].lower()] = m
        for c in d.get("corrections", []):
            if isinstance(c, dict) and isinstance(c.get("entendu"), str) and isinstance(c.get("ecrit"), str):
                self.corrections[c["entendu"].lower()] = {"fois": 1, "derniere": _maintenant(), **c}
        self.refuses = {r for r in d.get("refuses", []) if isinstance(r, str)}
        for k, v in (d.get("stats") or {}).items():
            if k in self.stats and isinstance(v, (int, float)):
                self.stats[k] = v

    def enregistrer(self) -> None:
        with self._verrou:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            d = {
                "mots": sorted(self.mots.values(), key=lambda m: -self._score(m)),
                "corrections": sorted(self.corrections.values(), key=lambda c: -c["fois"]),
                "refuses": sorted(self.refuses),
                "stats": self.stats,
            }
            tmp = self.fichier.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.fichier)  # écriture atomique : jamais de fichier à moitié écrit
            self._date_fichier = self._date()

    # --- vocabulaire ------------------------------------------------------------
    def ajouter_mot(self, texte: str, source: str, poids: float = 0) -> bool:
        """`poids` : avance de départ dans le classement (rang dans un dictionnaire importé),
        distincte des utilisations réellement entendues."""
        texte = re.sub(r"\s+", " ", texte).strip(" .,;:!?\"'’«»")
        if not texte or len(texte) > 50 or len(texte.split()) > 5:
            return False
        if len(texte.split()) == 1 and courant(texte):
            return False
        cle = texte.lower()
        if cle in self.refuses:
            if source not in ("manuel", "selection"):
                return False
            self.refuses.discard(cle)  # remis à la main : l'utilisateur a changé d'avis
        if cle in self.mots:
            m = self.mots[cle]
            if m["texte"] != texte and source in ("manuel", "selection", "correction"):
                m["texte"] = texte  # la graphie choisie par l'utilisateur l'emporte
            return False
        self.mots[cle] = {"texte": texte, "source": source, "ajoute": _maintenant(), "utilisations": 0,
                          "poids": poids, "derniere": 0.0}
        return True

    def oublier_mot(self, texte: str) -> bool:
        cle = texte.lower().strip()
        self.refuses.add(cle)
        for k in [k for k, c in self.corrections.items() if c["ecrit"].lower() == cle]:
            del self.corrections[k]
        return self.mots.pop(cle, None) is not None

    def _score(self, m: dict) -> float:
        # utilisations, avec un bonus de fraîcheur qui s'efface en ~1 mois ; les mots ajoutés à la
        # main ou appris d'une correction gardent une avance.
        age = (_maintenant() - (m.get("derniere") or m.get("ajoute") or 0)) / 86400
        fraicheur = math.exp(-age / DEMI_VIE_JOURS)
        bonus = {"manuel": 8, "selection": 8, "correction": 8}.get(m.get("source", ""), 0)
        return m.get("utilisations", 0) + m.get("poids", 0) + 10 * fraicheur + bonus

    def mots_prioritaires(self, n: int) -> list[str]:
        return [m["texte"] for m in sorted(self.mots.values(), key=lambda m: -self._score(m))[:n]]

    def noter_dictee(self, texte: str, secondes: float) -> None:
        """Après chaque dictée : compte les mots du vocabulaire entendus, et les statistiques."""
        bas = texte.lower()
        maintenant = _maintenant()
        for cle, m in self.mots.items():
            if cle and re.search(r"(?<![\w-])" + re.escape(cle) + r"(?![\w-])", bas):
                m["utilisations"] = m.get("utilisations", 0) + 1
                m["derniere"] = maintenant
        self.stats["dictees"] += 1
        self.stats["mots_dictes"] += len(texte.split())
        self.stats["secondes"] += secondes

    # --- corrections -------------------------------------------------------------
    def apprendre_correction(self, entendu: str, ecrit: str) -> str:
        """Renvoie ce qui a été appris : "mot", "remplacement" ou "" (rien de nouveau)."""
        if ecrit.lower() in self.refuses:
            return ""
        appris = ""
        # « La Tour Eiffel » (un nom : plusieurs majuscules) se retient en entier ; « to Mars », seulement « Mars »
        mots = ecrit.split()
        if len(mots) == 1 or sum(m[:1].isupper() for m in mots) >= 2:
            retenus = [ecrit]
        else:
            retenus = [m for m in mots if not courant(m)] or [ecrit]
        for mot in retenus:
            if self.ajouter_mot(mot, "correction"):
                appris = "mot"
        cle = entendu.lower()
        c = self.corrections.get(cle)
        if c and c["ecrit"] == ecrit:
            c["fois"] += 1
            c["derniere"] = _maintenant()
            if c["fois"] == SEUIL_REMPLACEMENT:
                appris = "remplacement"
        else:
            self.corrections[cle] = {"entendu": entendu, "ecrit": ecrit, "fois": 1, "derniere": _maintenant()}
        return appris

    def remplacements(self) -> dict[str, str]:
        return {c["entendu"]: c["ecrit"] for c in self.corrections.values() if c["fois"] >= SEUIL_REMPLACEMENT}

    def ajouter_correction(self, entendu: str, ecrit: str) -> bool:
        """Ajoutée à la main (« Mark Smead » -> « Mars Men ») : active tout de suite, et le bon mot entre
        dans le vocabulaire pour que le moteur l'entende mieux la fois suivante."""
        entendu, ecrit = re.sub(r"\s+", " ", entendu).strip(), re.sub(r"\s+", " ", ecrit).strip()
        if not entendu or not ecrit or entendu.lower() == ecrit.lower():
            return False
        self.refuses.discard(ecrit.lower())
        self.ajouter_mot(ecrit, "manuel")
        self.corrections[entendu.lower()] = {"entendu": entendu, "ecrit": ecrit, "fois": SEUIL_REMPLACEMENT,
                                             "derniere": _maintenant(), "source": "manuel"}
        return True

    def oublier_correction(self, entendu: str) -> bool:
        return self.corrections.pop(entendu.lower(), None) is not None

    # --- reprise de l'ancienne configuration ------------------------------------------------
    def reprendre(self, mots: list[str], remplacements: dict[str, str]) -> int:
        n = 0
        for i, m in enumerate(mots):
            # l'ordre d'origine (les plus utilisés d'abord) devient une avance de départ
            if self.ajouter_mot(m, "import", poids=round(3 * (len(mots) - i) / len(mots), 2)):
                n += 1
        for entendu, ecrit in remplacements.items():
            self.corrections.setdefault(entendu.lower(), {"entendu": entendu, "ecrit": ecrit,
                                                          "fois": SEUIL_REMPLACEMENT, "derniere": _maintenant()})
        return n
