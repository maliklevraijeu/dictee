"""La logique du raccourci, sans toucher au vrai clavier : on rejoue des séquences de touches."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dictee.raccourci as rc  # noqa: E402

CTRL, WIN, ESPACE, ECHAP, ALT, MAJ, Z, A, M = 0xA2, 0x5B, 0x20, 0x1B, 0xA4, 0xA0, 0x5A, 0x41, 0x4D


def faire(sequence):
    """sequence : liste de (vk, bas). Renvoie (événements émis, touches avalées)."""
    evts, avalees, injections = [], [], []
    rc.envoyer_touches = lambda *e: injections.append(e)  # pas de vraie injection pendant le test
    rc.Raccourcis._vraiment_enfoncee = staticmethod(lambda vk: True)  # le vrai clavier n'est pas lu
    r = rc.Raccourcis("ctrl+win", "ctrl+win+space", "alt+shift+z", evts.append)
    for vk, bas in sequence:
        if r._traiter(vk, bas):
            avalees.append(vk)
    return evts, avalees, injections


def test_maintenir_relacher():
    e, av, inj = faire([(CTRL, True), (WIN, True), (WIN, False), (CTRL, False)])
    assert e == ["debut", "fin"]
    assert av == []
    assert inj, "le menu Démarrer doit être bloqué au relâchement de Win"


def test_ordre_inverse():
    e, _, _ = faire([(WIN, True), (CTRL, True), (CTRL, False), (WIN, False)])
    assert e == ["debut", "fin"]


def test_mains_libres_puis_arret():
    e, av, _ = faire([(CTRL, True), (WIN, True), (ESPACE, True), (ESPACE, False), (WIN, False), (CTRL, False),
                      # ... il parle sans rien tenir ...
                      (CTRL, True), (WIN, True), (WIN, False), (CTRL, False)])
    assert e == ["debut", "mains_libres", "fin"]
    assert ESPACE in av, "l'espace des mains libres ne doit pas partir dans l'appli"


def test_annuler():
    e, av, _ = faire([(CTRL, True), (WIN, True), (ECHAP, True), (ECHAP, False), (WIN, False), (CTRL, False)])
    assert e == ["debut", "annuler"]
    assert ECHAP in av


def test_echap_sans_dictee_passe():
    e, av, _ = faire([(ECHAP, True), (ECHAP, False)])
    assert e == [] and av == []


def test_ctrl_seul_rien():
    e, _, _ = faire([(CTRL, True), (A, True), (A, False), (CTRL, False)])
    assert e == []


def test_repetition_automatique():
    # Windows répète l'appui tant qu'on tient : une seule dictée
    e, _, _ = faire([(CTRL, True), (WIN, True), (WIN, True), (WIN, True), (CTRL, True), (WIN, False), (CTRL, False)])
    assert e == ["debut", "fin"]


def test_recoller():
    e, av, _ = faire([(ALT, True), (MAJ, True), (Z, True), (Z, False), (MAJ, False), (ALT, False)])
    assert e == ["recoller"] and Z in av


def test_touche_relachee_sur_ecran_verrouille():
    # Win+L : le relâchement de Win n'arrive jamais au crochet. Ctrl seul ne doit pas lancer de dictée.
    evts = []
    rc.envoyer_touches = lambda *e: None
    r = rc.Raccourcis("ctrl+win", "ctrl+win+space", "alt+shift+z", evts.append)
    tenues = {WIN}
    r._vraiment_enfoncee = lambda vk: vk in tenues
    r._traiter(WIN, True)
    tenues.clear()  # Win relâchée pendant que le PC était verrouillé
    tenues.add(CTRL)
    r._traiter(CTRL, True)
    assert evts == [], evts


def test_memoriser():
    e, av, _ = faire([(ALT, True), (MAJ, True), (M, True), (M, False), (MAJ, False), (ALT, False)])
    assert e == ["memoriser"] and M in av


def test_memoriser_ignore_pendant_une_dictee():
    e, _, _ = faire([(CTRL, True), (WIN, True), (ALT, True), (MAJ, True), (M, True), (M, False), (MAJ, False),
                     (ALT, False), (WIN, False), (CTRL, False)])
    assert "memoriser" not in e


if __name__ == "__main__":
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
    print("ok")
