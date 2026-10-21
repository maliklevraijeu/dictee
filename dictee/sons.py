"""Deux petits sons discrets (début, fin), fabriqués à la volée : aucun fichier à fournir."""
from __future__ import annotations

import io
import math
import struct
import threading
import wave
import winsound


def _bip(f1: float, f2: float, duree: float = 0.07, volume: float = 0.18) -> bytes:
    taux = 44100
    n = int(taux * duree)
    ech = []
    for i in range(n):
        t = i / taux
        f = f1 + (f2 - f1) * i / n
        env = min(1.0, i / (taux * 0.008)) * min(1.0, (n - i) / (taux * 0.03))
        ech.append(int(32767 * volume * env * math.sin(2 * math.pi * f * t)))
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taux)
        w.writeframes(struct.pack(f"<{n}h", *ech))
    return b.getvalue()


DEBUT = _bip(660, 880)
FIN = _bip(880, 660)
ERREUR = _bip(300, 220, 0.12)


def jouer(son: bytes) -> None:
    # winsound ne sait pas jouer un son en mémoire de façon asynchrone : petit fil dédié.
    threading.Thread(target=winsound.PlaySound, args=(son, winsound.SND_MEMORY), daemon=True).start()
