import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictee.ecran import noms_propres  # noqa: E402


def test_noms_d_un_mail():
    texte = ("Bonjour Malik,\nMerci pour ton retour sur la boutique Shopify, Khalil m'a parlé de TrendTrack "
             "et du site levraijeu.com hier.\nBonne soirée,\nKhalil")
    n = noms_propres(texte)
    for nom in ("Khalil", "Shopify", "TrendTrack", "levraijeu.com", "Malik"):
        assert nom in n, n
    # un mot en début de phrase ou de ligne n'est pas un nom pour autant
    for mot in ("Bonjour", "Merci", "Bonne"):
        assert mot not in n, n


def test_nom_compose_et_sigles():
    n = noms_propres("On a regardé la vidéo de Shaun Eng sur le SEO et les UGC avec Mars Men.")
    assert "Shaun Eng" in n, n
    assert "Mars Men" in n, n
    assert "SEO" in n and "UGC" in n, n


def test_menus_et_bruit_ignores():
    # des libellés d'interface, chacun sur sa ligne, et une adresse mail : rien à retenir
    texte = "Accueil\nParamètres\nRechercher\nNouveau message\ncontact@exemple.com\n12345"
    assert noms_propres(texte) == [], noms_propres(texte)


def test_boutons_d_une_page_ignores():
    # une page Discord lue le 21/10 : chaque message répète ses boutons en début de ligne
    message = "Hokuto\nsalut Malik, tu as vu la vidéo sur Shopify ? je vais répondre demain\nRépondre\nModifier\nTransférer\n"
    n = noms_propres(message * 6 + "Créer un salon\nAjouter une réaction\nLe Vrai Jeu - Discord")
    assert "Malik" in n and "Shopify" in n, n
    for bouton in ("Répondre", "Modifier", "Transférer", "Créer", "Ajouter"):
        assert bouton not in n, n
    # « Le » fait partie du nom quand il porte une majuscule au milieu d'une ligne
    assert "Le Vrai Jeu" in noms_propres("le serveur Le Vrai Jeu sur Discord"), noms_propres("le serveur Le Vrai Jeu")


def test_codes_et_doublons():
    # un lien d'invitation, une vitesse, un sigle de deux lettres : du bruit ; IM8 et 4Life sont des marques
    n = noms_propres("rejoins discord.gg/o7hm4N3 en 2X avec JO, la marque IM8 et 4Life\nLe Vrai Jeu\nle serveur Le Vrai Jeu")
    for bruit in ("o7hm4N3", "2X", "JO"):
        assert bruit not in n, n
    assert "IM8" in n and "4Life" in n, n
    # « Vrai Jeu » (ligne qui commence par « Le ») et « Le Vrai Jeu » : un seul nom, le plus long
    assert "Le Vrai Jeu" in n and "Vrai Jeu" not in n, n


def test_les_plus_frequents_d_abord_et_plafond():
    texte = " ".join(f"je parle de Nom{i}x." for i in range(30)) + " encore Zorglub et Zorglub et Zorglub."
    n = noms_propres(texte, 10)
    assert len(n) == 10, n
    assert n[0] == "Zorglub", n


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
    print("ok")
