"""Tests de la mémoire : classement, apprentissage par correction, oubli. python tests/test_memoire.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dictee.memoire import Memoire  # noqa: E402


def nouvelle() -> Memoire:
    return Memoire(Path(tempfile.mkdtemp()) / "memoire.json")


m = nouvelle()
# reprise d'un dictionnaire : l'ordre devient une avance, pas un faux nombre d'utilisations
assert m.reprendre(["Shopify", "Discord", "TikTok"], {"btw": "by the way"}) == 3
assert all(x["utilisations"] == 0 for x in m.mots.values())
assert m.mots_prioritaires(1) == ["Shopify"]
assert m.remplacements() == {"btw": "by the way"}

# un mot dit souvent remonte en tête
for _ in range(3):
    m.noter_dictee("je parle de TikTok sur TikTok", 2.0)
assert m.mots_prioritaires(1) == ["TikTok"], m.mots_prioritaires(3)
assert m.mots["tiktok"]["utilisations"] == 3
assert m.stats["dictees"] == 3

# un mot ajouté à la main passe devant tout un dictionnaire importé : il est envoyé au moteur tout de suite
gros = nouvelle()
gros.reprendre([f"Mot{i}x" for i in range(300)], {})
gros.ajouter_mot("La Tour Eiffel", "manuel")
assert "La Tour Eiffel" in gros.mots_prioritaires(5)

# les mots courants ne deviennent jamais du vocabulaire
assert not m.ajouter_mot("dans", "correction")
assert m.ajouter_mot("Zorglub", "correction")

# correction de plusieurs mots : on retient le mot rare, ou l'ensemble quand c'est un nom
m.apprendre_correction("Tomars", "to Mars")
assert "mars" in m.mots and "to mars" not in m.mots
m.apprendre_correction("la tour et fêle", "La Tour Eiffel")
assert "la tour eiffel" in m.mots

# le remplacement automatique attend une 2e correction identique
assert "la tour et fêle" not in m.remplacements()
assert m.apprendre_correction("la tour et fêle", "La Tour Eiffel") == "remplacement"
assert m.remplacements()["la tour et fêle"] == "La Tour Eiffel"

# oublier un mot : retiré, ses corrections aussi, et jamais ré-appris tout seul
m.oublier_mot("La Tour Eiffel")
assert "la tour eiffel" not in m.mots and "la tour et fêle" not in m.remplacements()
m.apprendre_correction("la tour et fêle", "La Tour Eiffel")
assert "la tour eiffel" not in m.mots
assert m.ajouter_mot("La Tour Eiffel", "manuel")  # remis à la main : accepté

# une correction ajoutée à la main est active tout de suite, et le bon mot entre au vocabulaire
assert m.ajouter_correction("Mark Smead", "Mars Men")
assert m.remplacements()["Mark Smead"] == "Mars Men" and "mars men" in m.mots

# un autre lancement (ou la commande `ajouter`) écrit le fichier : on le relit avant d'y toucher
m.enregistrer()
autre = Memoire(m.fichier)
autre.ajouter_mot("Huel", "manuel")
autre.enregistrer()
import os, time  # noqa: E401,E402
os.utime(m.fichier, (time.time() + 5, time.time() + 5))  # date différente même si tout va très vite
m.synchroniser()
assert "huel" in m.mots

# le fichier se relit à l'identique
m.enregistrer()
r = Memoire(m.fichier)
assert r.mots.keys() == m.mots.keys() and r.stats == m.stats and r.refuses == m.refuses

# un fichier abîmé est mis de côté, jamais écrasé ; une liste de mots écrite à la main est acceptée
d = Path(tempfile.mkdtemp())
(d / "memoire.json").write_text('{"mots": ["Canva",], }', encoding="utf-8")
m = Memoire(d / "memoire.json")
assert not m.mots and list(d.glob("memoire-abimee-*.json"))
(d / "memoire.json").write_text('{"mots": ["Canva", {"texte": "Zorglub"}], "stats": {"dictees": null}}', encoding="utf-8")
m = Memoire(d / "memoire.json")
assert m.mots_prioritaires(5) and "canva" in m.mots and m.stats["dictees"] == 0
m.noter_dictee("Canva", 1.0)
print("ok")
