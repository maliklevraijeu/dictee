"""python -m pytest tests  (ou : python tests/test_nettoyage.py)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictee.nettoyage import nettoyer  # noqa: E402

CAS = [
    # hésitations et faux départs
    ("Moi, j'aimerais-- j'aurais aimé que tu demandes, euh, à tout le monde.",
     "Moi, j'aurais aimé que tu demandes à tout le monde."),
    ("Euh, je pense que c'est pas bon. Tu vois?", "Je pense que c'est pas bon. Tu vois ?"),
    ("Envoie à la discussion de-- avec Zorglub, euh, à mon frère",
     "Envoie à la discussion avec Zorglub à mon frère"),
    ("Hum. Ok, du coup on fait ça: demain", "Ok, du coup on fait ça : demain"),
    # sa façon de parler reste
    ("Du coup en fait c'est pas grave, tu vois ?", "Du coup en fait c'est pas grave, tu vois ?"),
    # bégaiements
    ("si le le produit marche", "si le produit marche"),
    ("c'est c'est vraiment bien", "c'est vraiment bien"),
    ("on va on va lancer demain", "on va lancer demain"),
    ("tu peux, tu peux mettre", "tu peux mettre"),
    # répétitions voulues intactes
    ("nous nous sommes trompés", "nous nous sommes trompés"),
    ("c'est très très bien, non non", "c'est très très bien, non non"),
    # typographie
    ("Tu vois?Ok", "Tu vois ? Ok"),
    ("Regarde ça:", "Regarde ça :"),
    ("à 10:30 , ok", "à 10:30, ok"),
    ("https://exemple.com", "https://exemple.com"),
]


def test_nettoyer():
    for brut, attendu in CAS:
        assert nettoyer(brut) == attendu, (brut, nettoyer(brut), attendu)


def test_snippets_et_remplacements():
    snip = {"mon adresse mail": "moi@exemple.com"}
    rempl = {"btw": "by the way", "claude code": "Claude Code"}
    assert nettoyer("Envoie-le à mon adresse mail.", snippets=snip) == "Envoie-le à moi@exemple.com."
    assert nettoyer("btw j'utilise claude code", remplacements=rempl) == "By the way j'utilise Claude Code" or \
        nettoyer("btw j'utilise claude code", remplacements=rempl) == "by the way j'utilise Claude Code"


def test_sans_nettoyage():
    assert nettoyer("euh le le test", hesitations=False) == "euh le le test"


if __name__ == "__main__":
    test_nettoyer()
    test_snippets_et_remplacements()
    test_sans_nettoyage()
    print("ok")
