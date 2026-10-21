"""Le mode précis : découpe aux pauses, recollage des morceaux. Sans réseau. python tests/test_precis.py"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictee.mots_courants import courant  # noqa: E402
from dictee.precis import SessionPrecise, joindre  # noqa: E402

# recollage : une majuscule due à la coupe redevient minuscule si la phrase continue
assert joindre(["Je pense que", "Ce serait mieux"], courant) == "Je pense que ce serait mieux"
assert joindre(["C'est fini.", "Ce serait mieux"], courant) == "C'est fini. Ce serait mieux"
assert joindre(["On parle de", "Shopify demain"], courant) == "On parle de Shopify demain"
assert joindre(["", "Bonjour"], courant) == "Bonjour"
assert joindre(["qui va venir", "M'aider en fait"], courant) == "qui va venir m'aider en fait"


class FauxClient:
    cle = "x"

    def __init__(self):
        self.morceaux = []

    def chauffer(self):
        pass

    def transcrire(self, pcm, langue, mots):
        self.morceaux.append(len(pcm) / 32000)
        return f"morceau{len(self.morceaux)}"


class FauxMoteur:
    langue = "fr"

    def mots_fichier(self):
        return ["Shopify"]

    def transcrire_gemini(self, pcm):
        raise RuntimeError("pas de Gemini")


def son(secondes, fort):
    rng = np.random.default_rng(1)
    amp = 4000 if fort else 30
    return (rng.normal(0, amp, int(16000 * secondes))).astype(np.int16).tobytes()


client = FauxClient()
s = SessionPrecise(FauxMoteur(), client, ThreadPoolExecutor(2))
# 21 s de voix, une vraie pause de 0,9 s, puis 3 s de voix : le premier morceau part PENDANT la dictée
for bout in (son(0.5, False), son(21, True), son(0.9, False), son(3, True), son(0.2, False)):
    for i in range(0, len(bout), 1600):
        s.pousser(bout[i:i + 1600])
assert len(client.morceaux) >= 1 and 21 <= client.morceaux[0] <= 22.5, client.morceaux
r = s.terminer()
assert r.texte == "morceau1 morceau2" and r.voie == "precis", (r.texte, r.voie)
assert len(client.morceaux) == 2

# une dictée de moins de 20 s, même avec une pause : un seul morceau, au relâchement (tout le contexte)
client2 = FauxClient()
s2 = SessionPrecise(FauxMoteur(), client2, ThreadPoolExecutor(2))
for i in range(0, len(b := son(6, True) + son(1, False) + son(4, True)), 1600):
    s2.pousser(b[i:i + 1600])
assert client2.morceaux == []
assert s2.terminer().texte == "morceau1"
print("ok")
