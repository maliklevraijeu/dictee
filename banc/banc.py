"""Banc d'essai de Dictée contre Wispr Flow, sur de VRAIES dictées (audio + texte final de Wispr).

  python banc/banc.py <dossier_clips> [--verbatim] [--fils 4]

<dossier_clips> contient cNN.wav et meta.json (champ "wispr" = texte final de Wispr,
"latence_wispr_ms" = son délai). Chaque dictée est envoyée au rythme réel de la parole par le
même code que l'application, puis on mesure :
- le délai entre la fin de la parole et le texte final ;
- l'écart mot à mot avec le texte final de Wispr (0 = identique).
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictee.config import Config  # noqa: E402
from dictee.memoire import Memoire  # noqa: E402
from dictee.moteur import Moteur  # noqa: E402
from dictee.nettoyage import nettoyer  # noqa: E402


def norm(t: str) -> list[str]:
    t = unicodedata.normalize("NFC", (t or "").lower()).replace("’", "'")
    return re.sub(r"[^\w'\s-]", " ", t).split()


def ecart(a: str, b: str) -> float:
    x, y = norm(a), norm(b)
    if not y:
        return 0.0
    prec = list(range(len(y) + 1))
    for i, mx in enumerate(x, 1):
        cur = [i] + [0] * len(y)
        for j, my in enumerate(y, 1):
            cur[j] = min(prec[j] + 1, cur[j - 1] + 1, prec[j - 1] + (mx != my))
        prec = cur
    return prec[-1] / len(y)


def main() -> None:
    dossier = Path(sys.argv[1])
    reecriture = "--reecriture" in sys.argv
    decoupe = "manuel" if "--manuel" in sys.argv else "vad"
    fils = int(sys.argv[sys.argv.index("--fils") + 1]) if "--fils" in sys.argv else 4
    meta = json.loads((dossier / "meta.json").read_text(encoding="utf-8"))
    cfg = Config.charger()
    m = Moteur(cfg.cle_api(), cfg.langue, Memoire().mots_prioritaires(100) or cfg.mots, reecriture=reecriture, decoupe=decoupe,
               langues_secondaires=cfg.langues_secondaires)

    def une(x: dict) -> dict:
        with wave.open(str(dossier / x["f"])) as w:
            pcm = w.readframes(w.getnframes())
        s = m.nouvelle_session()
        for i in range(0, len(pcm), 1600):
            s.pousser(pcm[i:i + 1600])
            time.sleep(0.05)
        r = s.terminer()
        texte = nettoyer(r.texte, {**cfg.remplacements, **Memoire().remplacements()}, cfg.snippets)
        return {"f": x["f"], "duree": x["duree"], "latence_wispr_ms": x["latence_wispr_ms"], "latence_ms": r.latence_ms,
                "voie": r.voie, "ecart_vs_wispr": round(ecart(texte, x["wispr"]), 3), "texte": texte, "wispr": x["wispr"],
                "erreur": r.erreur}

    with ThreadPoolExecutor(fils) as ex:
        res = list(ex.map(une, meta))
    for r in res:
        print(f"{r['f']} {r['duree']:.0f}s  wispr {r['latence_wispr_ms']:.0f} ms | dictée {r['latence_ms']} ms ({r['voie']}) | écart {r['ecart_vs_wispr']}")
    med = lambda v: sorted(v)[len(v) // 2]
    ok = [r for r in res if r["voie"] == "direct"]
    print(f"\n{len(res)} dictées, {len(ok)} en direct, {sum(r['voie'] == 'bloc' for r in res)} en secours, "
          f"{sum(r['voie'] == 'erreur' for r in res)} en erreur")
    print(f"Délai médian : Wispr {med([r['latence_wispr_ms'] for r in res]):.0f} ms | Dictée {med([r['latence_ms'] for r in res])} ms")
    print(f"Plus lent (sur 10) : Wispr {sorted(r['latence_wispr_ms'] for r in res)[int(len(res) * .9)]:.0f} ms | "
          f"Dictée {sorted(r['latence_ms'] for r in res)[int(len(res) * .9)]} ms")
    print(f"Écart avec le texte de Wispr : médian {med([r['ecart_vs_wispr'] for r in res])}, "
          f"moyen {sum(r['ecart_vs_wispr'] for r in res) / len(res):.3f}")
    nom = f"resultats-{decoupe}" + ("-reecriture" if reecriture else "") + ".json"
    (dossier / nom).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
