"""L'anglais : textes de l'interface complets, nettoyage à l'anglaise. python tests/test_langues.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictee import langues  # noqa: E402
from dictee.nettoyage import nettoyer  # noqa: E402

# chaque texte existe dans les deux langues, avec les mêmes {valeurs}
fr, en = langues.TEXTES["fr"], langues.TEXTES["en"]
assert set(fr) == set(en), set(fr) ^ set(en)
for cle in fr:
    assert sorted(__import__("re").findall(r"{(\w+)}", fr[cle])) == sorted(__import__("re").findall(r"{(\w+)}", en[cle])), cle

langues.choisir("en")
assert langues.t("appris", mots="Mars Men") == "Learned: Mars Men"
langues.choisir("fr")
assert langues.t("appris", mots="Mars Men") == "Appris : Mars Men"
langues.choisir("auto")
assert langues.langue() in ("fr", "en")

# anglais : « um / uh » retirés, aucune espace avant ? ! : ;
assert nettoyer("um so uh what do you think ?", langue="en") == "So what do you think?"
assert nettoyer("Wait , really ! Here : the plan", langue="en") == "Wait, really! Here: the plan"
assert nettoyer("I I think it works", langue="en") == "I think it works"
assert nettoyer("it was very very good", langue="en") == "it was very very good"
# français : inchangé
assert nettoyer("euh tu vois ?") == "Tu vois ?"
print("ok")
