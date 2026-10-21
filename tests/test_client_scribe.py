"""La connexion à ElevenLabs : jamais de dictée bloquée par une connexion morte. Sans réseau : un faux
serveur local. python tests/test_client_scribe.py

Vécu le 21/10 à 20h38 : 1re dictée après 24 min sans dicter, la connexion gardée ouverte avait été coupée
en silence par le réseau, et la dictée de 6 s a mis 20,7 s (Windows réessaie environ 20 s avant d'abandonner).
"""
import http.client
import socket
import socketserver
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictee.precis import ClientScribe  # noqa: E402


class Serveur(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    connexions = 0
    trou_noir = False  # True : la 2e requête d'une même connexion ne reçoit jamais de réponse


class Gestion(socketserver.BaseRequestHandler):
    def handle(self):
        self.server.connexions += 1
        f = self.request.makefile("rb")
        n = 0
        while True:
            entetes = {}
            ligne = f.readline()
            if not ligne:
                return
            while (ligne := f.readline().decode()) not in ("\r\n", ""):
                k, _, v = ligne.partition(":")
                entetes[k.strip().lower()] = v.strip()
            f.read(int(entetes.get("content-length", 0)))
            n += 1
            if self.server.trou_noir and n >= 2:
                time.sleep(30)  # la connexion est « morte » : rien ne revient
                return
            corps = b'{"text": "ok"}'
            self.request.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                                 + str(len(corps)).encode() + b"\r\n\r\n" + corps)


def serveur(trou_noir=False):
    s = Serveur(("127.0.0.1", 0), Gestion)
    s.trou_noir = trou_noir
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def client(s):
    port = s.server_address[1]
    return ClientScribe("x", fabrique=lambda: http.client.HTTPConnection("127.0.0.1", port, timeout=60))


PCM = b"\0" * 32000  # 1 s de silence


def test_la_connexion_chauffee_est_celle_qui_sert():
    # à l'appui, la connexion s'ouvre dans un fil ; la transcription part d'un autre fil : même connexion
    s = serveur()
    c = client(s)
    t = threading.Thread(target=c.chauffer)
    t.start()
    t.join()
    r = []
    t = threading.Thread(target=lambda: r.append(c.transcrire(PCM, "fr", [])))
    t.start()
    t.join()
    assert r == ["ok"] and s.connexions == 1, (r, s.connexions)


def test_connexion_morte_apres_une_pause():
    # la 2e requête sur la même connexion ne reçoit jamais de réponse : après une pause, le client doit
    # en ouvrir une neuve à l'appui au lieu d'attendre dans le vide
    s = serveur(trou_noir=True)
    c = client(s)
    c.INACTIF_MAX = 0.2
    assert c.transcrire(PCM, "fr", []) == "ok"
    time.sleep(0.3)
    c.chauffer()
    t0 = time.monotonic()
    assert c.transcrire(PCM, "fr", []) == "ok"
    assert time.monotonic() - t0 < 2, time.monotonic() - t0


def test_jamais_bloque_longtemps():
    # même sans pause (connexion réutilisée qui ne répond plus), la dictée repart sur une connexion
    # neuve au bout de quelques secondes, pas 20
    s = serveur(trou_noir=True)
    c = client(s)
    assert c.transcrire(PCM, "fr", []) == "ok"
    t0 = time.monotonic()
    assert c.transcrire(PCM, "fr", []) == "ok"
    assert time.monotonic() - t0 < 8, time.monotonic() - t0


if __name__ == "__main__":
    socket.setdefaulttimeout(None)
    for nom, f in list(globals().items()):
        if nom.startswith("test_"):
            f()
    print("ok")
