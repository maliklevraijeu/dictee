"""Après la transcription : hésitations, typographie française, snippets, remplacements du dictionnaire.
Tout est déterministe et testé (tests/test_nettoyage.py) : aucune IA ne réécrit tes phrases.

On ne retire que les « euh » et les faux départs, et rien n'est réécrit ; « du coup », « en fait », « c'est pas », « tu vois » restent : c'est ta voix."""
from __future__ import annotations

import re
import unicodedata

_EUH = r"(?:euh+|heu+|hum+|hm+|mmh+|bah\s+euh)"


def _motif(phrase: str) -> re.Pattern:
    # Phrase entière, insensible à la casse ; virgules ou espaces tolérés entre les mots.
    mots = [re.escape(m) for m in phrase.strip().split()]
    return re.compile(r"(?<![\w-])" + r"[\s,]+".join(mots) + r"(?![\w-])", re.IGNORECASE)


def appliquer_snippets(texte: str, snippets: dict[str, str]) -> str:
    for dit, colle in snippets.items():
        if dit.strip():
            texte = _motif(dit).sub(lambda _m, c=colle: c, texte)
    return texte


def appliquer_remplacements(texte: str, remplacements: dict[str, str]) -> str:
    # Les plus longs d'abord : « Claude Code » avant « Claude ».
    for entendu in sorted(remplacements, key=len, reverse=True):
        ecrit = remplacements[entendu]
        if entendu.strip() and ecrit is not None:
            texte = _motif(entendu).sub(lambda _m, e=ecrit: e, texte)
    return texte


def retirer_hesitations(texte: str) -> str:
    t = texte
    debut_retire = re.match(rf"(?i)\s*(?:{_EUH}\b|[\w'’-]+--)", t) is not None
    # faux départ marqué par le moteur : « j'aimerais-- j'aurais aimé » -> « j'aurais aimé »
    t = re.sub(r"[\w'’-]+--(?=\s|$)\s*", "", t)
    # « , euh, » au milieu d'une phrase : on retire les deux virgules avec
    t = re.sub(rf"(?i),\s*{_EUH}\b\s*,", " ", t)
    # « euh » et la ponctuation qui le suit ; ce qui le précède reste
    t = re.sub(rf"(?i)(^|[\s,.!?…])\s*{_EUH}\b\s*[,.…]*", lambda m: m.group(1) + " ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    t = re.sub(r",\s*([.?!…])", lambda m: m.group(1), t)
    t = re.sub(r"^[,\s]+", "", t)
    # majuscule après un point, et au tout début seulement si on a retiré le premier mot
    t = re.sub(r"([.?!…]\s+)([a-zàâäéèêëîïôöùûüç])", lambda m: m.group(1) + m.group(2).upper(), t)
    if debut_retire and t:
        t = t[0].upper() + t[1:]
    return t


# Doublons voulus qu'on ne touche jamais : « nous nous sommes », « très très », « non non »...
_DOUBLES_VOULUS = {"nous", "vous", "très", "non", "oui", "si", "bon", "allez", "vite", "fort", "beaucoup",
                   "trop", "plus", "encore", "jamais", "toujours", "là", "ah", "oh", "hey", "ok", "bien"}


def retirer_begaiements(texte: str) -> str:
    """« le le produit » -> « le produit » ; « c'est c'est » -> « c'est » ; « on va on va » -> « on va ».
    Seulement des groupes de 1 à 3 mots répétés juste à la suite, dans la même phrase."""
    t = texte
    for n in (3, 2, 1):
        motif = re.compile(r"(?i)(?<![\w'’-])((?:[\w'’-]+\s*,?\s+){" + str(n - 1) + r"}[\w'’-]+)(\s*,?\s+)\1(?![\w'’-])")

        def remplacer(m: re.Match) -> str:
            groupe = m.group(1)
            if n == 1 and groupe.lower() in _DOUBLES_VOULUS:
                return m.group(0)
            return groupe

        avant = None
        while avant != t:
            avant = t
            t = motif.sub(remplacer, t)
    return t


def typographie(texte: str) -> str:
    t = unicodedata.normalize("NFC", texte)
    t = re.sub(r"\s*--\s*", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s+([,.…)])", lambda m: m.group(1), t)
    # Français : une espace avant ? ! ; (« Tu vois ? »)
    t = re.sub(r"(?<=[\w»”\"')])\s*([?!;])", lambda m: " " + m.group(1), t)
    t = re.sub(r"(?<=[^\s\d:/])\s*:(?=\s|$)", " :", t)
    t = re.sub(r"([?!;:])(?=[^\s?!.,)\"»’'/\d])", lambda m: m.group(1) + " ", t)
    t = re.sub(r"\s+\n", "\n", t)
    return t.strip()


def nettoyer(texte: str, remplacements: dict[str, str] | None = None, snippets: dict[str, str] | None = None,
             hesitations: bool = True) -> str:
    t = retirer_begaiements(retirer_hesitations(texte)) if hesitations else texte
    t = typographie(t)
    if snippets:
        t = appliquer_snippets(t, snippets)
    if remplacements:
        t = appliquer_remplacements(t, remplacements)
    return t
