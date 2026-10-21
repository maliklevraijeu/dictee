"""La page du téléphone, sans téléphone : un vrai serveur sur 127.0.0.1. python tests/test_telephone.py"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictee.telephone import PAGE, Serveur, adresse_locale, qr_png  # noqa: E402

recus = []


def recevoir(texte):
    recus.append(texte)
    return {"ok": True, "colle": True}


s = Serveur(recevoir, hote="127.0.0.1", port=0, jeton="jeton-de-test-0123456789")
s.lancer()
base = f"http://127.0.0.1:{s.port}"


def appeler(chemin, corps=None):
    req = urllib.request.Request(base + chemin, data=corps, method="POST" if corps is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


try:
    # la page ne s'ouvre qu'avec le bon jeton
    assert appeler("/")[0] == 403
    assert appeler("/?t=mauvais")[0] == 403
    code, page = appeler("/?t=jeton-de-test-0123456789")
    assert code == 200 and "Envoyer au PC" in page and page == PAGE

    # un envoi arrive tel quel, sans les espaces autour
    code, rep = appeler("/envoyer?t=jeton-de-test-0123456789", json.dumps({"texte": "  Bonjour Karim.  "}).encode())
    assert code == 200 and json.loads(rep) == {"ok": True, "colle": True} and recus == ["Bonjour Karim."]

    # refusés : mauvais jeton, texte vide, pas du JSON, trop long
    assert appeler("/envoyer?t=faux", json.dumps({"texte": "x"}).encode())[0] == 403
    assert appeler("/envoyer?t=jeton-de-test-0123456789", json.dumps({"texte": "   "}).encode())[0] == 400
    assert appeler("/envoyer?t=jeton-de-test-0123456789", b"pas du json")[0] == 400
    assert appeler("/envoyer?t=jeton-de-test-0123456789", json.dumps({"texte": "a" * 50_000}).encode())[0] == 413
    # jamais tronqué en silence : 10 001 caractères sont refusés, pas coupés
    assert appeler("/envoyer?t=jeton-de-test-0123456789", json.dumps({"texte": "a" * 10_001}).encode())[0] == 413
    assert recus == ["Bonjour Karim."]

    # pas plus de 5 envois en 2 secondes
    codes = [appeler("/envoyer?t=jeton-de-test-0123456789", json.dumps({"texte": "x"}).encode())[0] for _ in range(6)]
    assert 429 in codes, codes
finally:
    s.arreter()

# seuls les appareils du réseau local sont acceptés
assert adresse_locale("192.168.1.23") and adresse_locale("10.0.0.5") and adresse_locale("127.0.0.1")
assert adresse_locale("::ffff:192.168.1.23")
assert not adresse_locale("8.8.8.8") and not adresse_locale("pas une ip")

assert qr_png("http://192.168.1.23:47110/?t=abc").startswith(b"\x89PNG")

# le programme visé par la règle du pare-feu existe (et l'appel ne plante pas sur Windows 64 bits)
from dictee.telephone import _exe_reel, ip_locale, nom_regle  # noqa: E402

assert Path(_exe_reel()).exists(), _exe_reel()
assert nom_regle() == nom_regle() and nom_regle().startswith("Dictee")
assert adresse_locale(ip_locale())
print("ok")
