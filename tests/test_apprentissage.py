import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictee.apprentissage import corrections, present  # noqa: E402
from dictee.memoire import SEUIL_REMPLACEMENT, Memoire  # noqa: E402


def test_correction_de_nom():
    colle = "C'était de faire la même chose que Kanvas.com a fait avec Air Jordane."
    final = "C'était de faire la même chose que canva.com a fait avec Air Jordan."
    c = corrections(colle, final)
    assert ("Kanvas.com", "canva.com") in c, c
    assert ("Jordane", "Jordan") in c, c


def test_texte_autour_ignore():
    colle = "le lien du Trust Pilot de Rocket Tomars"
    final = "Bonjour, regarde le lien du Trustpilot de Rocket to Mars stp"
    c = corrections(colle, final)
    assert ("Trust Pilot", "Trustpilot") in c, c
    assert ("Tomars", "to Mars") in c, c


def test_rien_a_apprendre():
    # reformulation, mot courant, nombre : on n'apprend rien
    assert corrections("je pense que c'est bien", "selon moi c'est super") == []
    assert corrections("le produit marche", "la produit marche") == []
    assert corrections("on se voit à dix heures", "on se voit à 10 heures") == []
    # texte effacé (message envoyé)
    assert corrections("une longue phrase dictée ici", "") == []
    assert corrections("une longue phrase dictée ici", "tout autre chose sans rapport") == []


def test_reformulation_pas_apprise():
    # « moi aussi » remplacé par « Fais-moi ça » : une reformulation, faite de mots courants
    assert corrections("Tu peux faire moi aussi le point", "Tu peux faire Fais-moi ça le point") == []


def test_grammaire_pas_apprise():
    # un accord ou un infinitif corrigé, ce n'est pas une faute d'écoute
    assert corrections("elle est petit et belle", "elle est petite et belle") == []
    assert corrections("on va allé voir le stock", "on va aller voir le stock") == []
    # une majuscule de début de phrase non plus
    assert corrections("ok voiture garée devant", "Ok. Voiture garée devant") == []


def test_majuscule_de_marque():
    assert ("claude", "Claude") in corrections("je travaille avec claude tous les jours",
                                               "je travaille avec Claude tous les jours")


def test_present():
    assert present("bonjour je teste la dictée", "Salut, bonjour je teste la dictée !")
    assert not present("bonjour je teste la dictée", "")


def test_memoire_apprend_et_classe():
    with tempfile.TemporaryDirectory() as d:
        m = Memoire(Path(d) / "m.json")
        m.ajouter_mot("Zorglub", "import")
        assert not m.ajouter_mot("le", "manuel"), "mot courant refusé"
        assert m.apprendre_correction("Kanvas", "Canva") == "mot"
        assert "Canva" in m.mots_prioritaires(5)
        assert m.remplacements() == {}, "un seul cas ne suffit pas"
        for _ in range(SEUIL_REMPLACEMENT - 1):
            m.apprendre_correction("Kanvas", "Canva")
        assert m.remplacements() == {"Kanvas": "Canva"}
        m.noter_dictee("on parle de Zorglub et de Zorglub", 3.0)
        assert m.stats["dictees"] == 1
        m.enregistrer()
        m2 = Memoire(Path(d) / "m.json")
        assert "Canva" in m2.mots_prioritaires(5)
        # un mot oublié n'est jamais ré-appris
        assert m2.oublier_mot("Canva")
        assert m2.apprendre_correction("Kanvas", "Canva") == ""
        assert "Canva" not in m2.mots_prioritaires(10)


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
    print("ok")
