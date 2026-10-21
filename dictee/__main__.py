"""Dictée : la dictée vocale partout dans Windows, en direct, avec ton vocabulaire.

  python -m dictee                    lance l'application (icône près de l'horloge)
  python -m dictee essai fichier.wav  passe un fichier dans le moteur, au rythme de la parole
  python -m dictee micros             liste les micros
  python -m dictee importer-wispr     reprend le dictionnaire et les snippets de Wispr Flow
  python -m dictee demarrage on|off   lancer (ou non) Dictée à l'ouverture de Windows
  python -m dictee ajouter "Mars Men" "Canva"      apprendre des noms (ou --fichier liste.txt)
  python -m dictee corriger "Mark Smead" "Mars Men"  écrire toujours le 2e quand le moteur entend le 1er

  English: same commands. "ajouter" = add words, "corriger" = always write B when the engine hears A.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
import wave
from pathlib import Path

from .config import Config


def essai(chemin: str) -> None:
    from .memoire import Memoire
    from .moteur import Moteur
    from .nettoyage import nettoyer

    cfg = Config.charger()
    mem = Memoire()
    m = Moteur(cfg.cle_api(), cfg.langue, mem.mots_prioritaires(100) or cfg.mots, cfg.reecriture, cfg.decoupe,
               cfg.langues_secondaires)
    m.cle_gemini = cfg.cle_gemini()
    with wave.open(chemin) as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (16000, 1, 2):
            sys.exit("Il faut un WAV 16 kHz mono 16 bits.")
        pcm = w.readframes(w.getnframes())
    s = m.nouvelle_session()
    for i in range(0, len(pcm), 1600):  # 50 ms, au rythme réel
        s.pousser(pcm[i:i + 1600])
        time.sleep(0.05)
    r = s.terminer()
    print(f"[{r.voie}] {r.latence_ms} ms après la fin" + (f" ({r.erreur})" if r.erreur else ""))
    print(nettoyer(r.texte, {**cfg.remplacements, **mem.remplacements()}, cfg.snippets, cfg.sans_hesitations, cfg.langue))


def micros() -> None:
    from .audio import lister_micros

    for i, nom in lister_micros():
        print(i, nom)


def importer_wispr() -> None:
    base = Path(os.environ["APPDATA"]) / "Wispr Flow" / "flow.sqlite"
    if not base.exists():
        sys.exit("Wispr Flow introuvable sur ce PC.")
    # Lecture seule, sur ce PC : rien n'est envoyé nulle part.
    try:
        con = sqlite3.connect(f"file:{base}?mode=ro&immutable=1", uri=True)
        # Les mots les plus dits d'abord : le moteur en direct n'en prend que 50.
        lignes = con.execute("select phrase, replacement, isSnippet from Dictionary where (isDeleted=0 or isDeleted is null) "
                             "order by coalesce(frequencyUsed,0) + coalesce(remoteFrequencyUsed,0) desc, manualEntry desc").fetchall()
    except sqlite3.Error as e:
        sys.exit(f"Le format de Wispr Flow a changé, import ignoré ({e}).")
    from .memoire import Memoire

    cfg = Config.charger()
    mots, rempl, snip = [], {}, dict(cfg.snippets)
    for phrase, remplacement, est_snippet in lignes:
        phrase = (phrase or "").strip()
        if not phrase:
            continue
        if est_snippet and remplacement:
            snip.setdefault(phrase, remplacement)
        elif remplacement and remplacement.strip() and remplacement.strip() != phrase:
            rempl.setdefault(phrase, remplacement.strip())
        elif phrase not in mots and "@" not in phrase:
            mots.append(phrase)
    mem = Memoire()
    nouveaux = mem.reprendre(mots, rempl)
    mem.enregistrer()
    cfg.snippets = snip
    # Le micro choisi dans Wispr (le premier de sa liste classée).
    try:
        import json

        w = json.loads((base.parent / "config.json").read_text(encoding="utf-8"))
        classes = w.get("prefs", {}).get("user", {}).get("rankedAudioDevices", [])
        if classes and not cfg.micro:
            nom = classes[0].get("name", "")
            cfg.micro = nom.split("(")[0].strip() or nom
    except (OSError, ValueError):
        pass
    cfg.enregistrer()
    print(f"{nouveaux} mots, {len(rempl)} remplacements, {len(snip)} snippets repris de Wispr Flow. "
          f"Micro : {cfg.micro or 'celui de Windows'}.")


def demarrage(etat: str) -> None:
    from . import demarrage as d

    if etat == "off":
        d.desactiver()
        print("Dictée ne se lancera plus au démarrage.")
    else:
        d.activer()
        print("Dictée se lancera au démarrage de Windows.")


def ajouter(args: list[str]) -> None:
    """Des noms d'un coup : ils partent au moteur dès la dictée suivante (même si Dictée tourne déjà)."""
    from .fenetre_memoire import morceaux
    from .memoire import Memoire

    if args[0] == "--fichier" and len(args) > 1:
        mots = morceaux(Path(args[1]).read_text(encoding="utf-8"))
    else:
        mots = [m for a in args for m in morceaux(a)]
    mem = Memoire()
    ajoutes = [m for m in mots if mem.ajouter_mot(m, "manuel")]
    mem.enregistrer()
    print(f"{len(ajoutes)} ajouté(s) / added: {', '.join(ajoutes) or '-'}")


def corriger(entendu: str, ecrit: str) -> None:
    from .memoire import Memoire

    mem = Memoire()
    if mem.ajouter_correction(entendu, ecrit):
        mem.enregistrer()
        print(f"« {entendu} » -> « {ecrit} »")


def main() -> None:
    a = sys.argv[1:]
    if not a:
        from .app import principal

        principal()
    elif a[0] == "essai" and len(a) > 1:
        essai(a[1])
    elif a[0] == "micros":
        micros()
    elif a[0] == "importer-wispr":
        importer_wispr()
    elif a[0] == "demarrage" and len(a) > 1:
        demarrage(a[1])
    elif a[0] == "ajouter" and len(a) > 1:
        ajouter(a[1:])
    elif a[0] == "corriger" and len(a) == 3:
        corriger(a[1], a[2])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
