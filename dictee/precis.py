"""Le mode « précis » : le modèle fichier d'ElevenLabs (Scribe v2), découpé aux pauses pendant qu'on parle.

Pourquoi : sur 40 vraies dictées (étude du 21/10/2026), le modèle « direct » (Scribe v2 Realtime) faisait des
fautes de sens que le modèle fichier ne faisait pas (« il me va lui » au lieu de « j'aimerais bien »,
« Célium » au lieu de « sélénium », « TGCRF » au lieu de « DGCRF »), et le modèle fichier tombait d'accord
avec Wispr Flow bien plus souvent. Il coûte aussi moins cher à l'heure.

Son défaut : il attend le fichier entier, donc 1 à 2 s de plus sur une longue dictée. D'où le découpage :
pendant que tu parles, une dictée longue est coupée à ses vraies pauses (0,7 s), et chaque morceau part tout de suite en
transcription. Au relâchement, il ne reste que le dernier morceau, quelques secondes au plus.
"""
from __future__ import annotations

import http.client
import json
import re
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor

import numpy as np

TAUX = 16000
OCTETS_PAR_MS = TAUX * 2 // 1000
PAUSE_MS = 700  # silence qui ferme un morceau (une vraie fin de phrase, pas une respiration)
MORCEAU_MIN_MS = 20000  # en dessous de 20 s, un seul envoi au relâchement : le modèle garde tout le contexte
MORCEAU_MAX_MS = 45000  # au-delà, on coupe au moment le plus calme
BLOC_MS = 50
MAX_MOTS = 50  # mesuré le 21/10 sur 40 dictées : 100 ou 200 mots ne retrouvent pas plus de mots que 50


def _rms(pcm: bytes) -> float:
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


class ClientScribe:
    """Des connexions HTTPS gardées ouvertes et partagées entre les fils : on ne repaie pas la poignée de
    main TLS (100 à 200 ms) à chaque dictée, et celle ouverte à l'appui est celle qui sert.

    Une connexion restée inactive peut être morte sans le dire : le 21/10 à 20h38, après 24 min sans
    dicter, le réseau l'avait coupée en silence et une dictée de 6 s a mis 20,7 s (Windows réessaie ~20 s
    avant d'abandonner). Au-delà de INACTIF_MAX on en ouvre une neuve, pendant que tu parles, et le 1er essai
    d'une requête a un délai court : s'il ne répond pas, on repart aussitôt sur une connexion neuve."""

    INACTIF_MAX = 20.0  # secondes

    def __init__(self, cle: str, fabrique=None):
        self.cle = cle
        self._fabrique = fabrique or (lambda: http.client.HTTPSConnection("api.elevenlabs.io", timeout=60))
        self._libres: list[tuple[http.client.HTTPConnection, float]] = []  # (connexion, dernier usage)
        self._verrou = threading.Lock()

    def _prendre(self) -> http.client.HTTPConnection:
        """La connexion libre la plus récente si elle a servi il y a peu ; sinon une neuve."""
        with self._verrou:
            while self._libres:
                c, quand = self._libres.pop()
                if c.sock is not None and time.monotonic() - quand < self.INACTIF_MAX:
                    return c
                c.close()
        return self._fabrique()

    def _rendre(self, c: http.client.HTTPConnection) -> None:
        with self._verrou:
            self._libres.append((c, time.monotonic()))

    def chauffer(self) -> None:
        c = self._prendre()
        try:
            if c.sock is None:
                c.connect()
        except OSError:
            c.close()
            return
        self._rendre(c)

    def transcrire(self, pcm: bytes, langue: str, mots: list[str]) -> str:
        b = uuid.uuid4().hex
        champs = [("model_id", "scribe_v2"), ("language_code", langue), ("file_format", "pcm_s16le_16"),
                  ("tag_audio_events", "false")] + [("keyterms", m) for m in mots]
        corps = b"".join(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode() for k, v in champs)
        corps += (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.pcm\"\r\n"
                  "Content-Type: application/octet-stream\r\n\r\n").encode() + pcm + f"\r\n--{b}--\r\n".encode()
        entetes = {"xi-api-key": self.cle, "Content-Type": f"multipart/form-data; boundary={b}"}
        # 1er essai : délai court, à la mesure de l'audio (Scribe rend 45 s d'audio en ~1,5 s) ; 2e essai, sur
        # une connexion neuve, avec le délai long
        delais = (4.0 + 0.3 * len(pcm) / OCTETS_PAR_MS / 1000, 60.0)
        for essai, delai in enumerate(delais):
            c = self._prendre() if essai == 0 else self._fabrique()
            try:
                c.timeout = delai
                if c.sock is not None:
                    c.sock.settimeout(delai)
                c.request("POST", "/v1/speech-to-text", body=corps, headers=entetes)
                r = c.getresponse()
                brut = r.read()
            except (http.client.HTTPException, OSError):
                c.close()  # connexion morte, coupée ou muette : on repart sur une neuve
                if essai:
                    raise
                continue
            if r.status >= 400:
                c.close()
                raise RuntimeError(f"HTTP {r.status} {brut[:200]!r}")
            self._rendre(c)
            return json.loads(brut).get("text", "").strip()
        return ""


def joindre(parties: list[str], courant) -> str:
    """Recolle les morceaux : une majuscule due à la coupe redevient minuscule quand la phrase continue."""
    out = ""
    for p in parties:
        p = p.strip()
        if not p:
            continue
        if out and not re.search(r"[.!?…:]$", out):
            premier = re.match(r"[\w'’-]+", p)
            elision = premier and re.match(r"(?i)(qu|[ldjmtsnc])['’]", premier.group(0))  # « M'aider », « L'idée »
            if premier and p[:1].isupper() and (courant(premier.group(0)) or elision):
                p = p[0].lower() + p[1:]
        out = f"{out} {p}".strip()
    return out


class SessionPrecise:
    """Même interface que moteur.Session : pousser(), terminer(), annuler(), duree(), pcm."""

    def __init__(self, moteur, client: ClientScribe, pool: ThreadPoolExecutor):
        self.m = moteur
        self.client = client
        self.pool = pool
        self.mots = list(moteur.mots_fichier())
        self.pcm = bytearray()
        self._debut_morceau = 0
        self._morceaux: list[Future] = []
        self._silence_ms = 0
        self._parole_ms = 0
        self._rms: list[float] = []  # par bloc de 50 ms, pour la coupe la plus calme
        self._fond: float | None = None
        self._tampon = bytearray()
        self._annulee = False
        self._verrou = threading.Lock()
        pool.submit(client.chauffer)  # la connexion s'ouvre pendant que tu commences à parler

    # --- côté application -------------------------------------------------
    def ajouter_mots(self, mots: list[str]) -> None:
        """Des noms lus à l'écran (ecran.py) : en tête de la liste, pour les morceaux pas encore partis."""
        from .moteur import _mots_bloc

        n = getattr(self.m, "mots_max", MAX_MOTS)
        with self._verrou:
            self.mots = _mots_bloc(list(mots) + self.mots, n)

    def pousser(self, morceau: bytes) -> None:
        with self._verrou:
            self.pcm.extend(morceau)
            self._tampon.extend(morceau)
            n = BLOC_MS * OCTETS_PAR_MS
            while len(self._tampon) >= n:
                bloc, self._tampon = bytes(self._tampon[:n]), self._tampon[n:]
                self._analyser(bloc)

    def _seuil(self) -> float:
        # Mesuré le 21/10 : sur ce genre de micro, le fond est vers 20 (sur 32 768) et la voix vers 60 à 250 ;
        # un micro avec réduction de bruit descend à 1 au calme. Le seuil suit donc le fond MESURÉ.
        return max(2.5 * (self._fond or 0.0), 8.0)

    def _analyser(self, bloc: bytes) -> None:
        r = _rms(bloc)
        self._rms.append(r)
        # Bruit de fond : les 10 % de blocs les plus calmes (hors silence numérique pur). La demi-seconde
        # gardée avant l'appui en donne une première mesure.
        utiles = [v for v in self._rms[-900:] if v >= 2]
        fond = float(np.percentile(utiles, 10)) if utiles else 0.0
        # Garde-fou : une longue voix sans aucun blanc ne doit jamais devenir le « fond ». Le fond ne
        # dépasse pas 3 fois le calme mesuré dans la première seconde (avant l'appui, puis le début).
        debut = [v for v in self._rms[:20] if v >= 2]
        if debut:
            fond = min(fond, 3 * min(debut))
        self._fond = fond
        if r > self._seuil():
            self._parole_ms += BLOC_MS
            self._silence_ms = 0
        else:
            self._silence_ms += BLOC_MS
        fin = len(self.pcm) - len(self._tampon)
        longueur_ms = (fin - self._debut_morceau) // OCTETS_PAR_MS
        if self._silence_ms >= PAUSE_MS and longueur_ms >= MORCEAU_MIN_MS and self._parole_ms > 0:
            # on coupe au milieu de la pause : aucun mot n'est tranché
            coupe = fin - (self._silence_ms // 2) * OCTETS_PAR_MS
            self._envoyer(self._debut_morceau, coupe)
        elif longueur_ms >= MORCEAU_MAX_MS:
            # pas de pause depuis 25 s : on coupe au bloc le plus calme de la dernière seconde
            derniers = self._rms[-20:]
            k = len(derniers) - 1 - int(np.argmin(derniers[::-1]))
            coupe = fin - (len(derniers) - k) * BLOC_MS * OCTETS_PAR_MS
            self._envoyer(self._debut_morceau, max(coupe, self._debut_morceau + OCTETS_PAR_MS * 1000))

    def _envoyer(self, debut: int, fin: int) -> None:
        pcm = bytes(self.pcm[debut:fin])
        self._debut_morceau = fin
        self._silence_ms = 0
        if self._parole_ms == 0:
            return  # que du silence : rien à transcrire (et pas d'invention du moteur sur un silence)
        self._parole_ms = 0
        self._morceaux.append(self.pool.submit(self._transcrire, pcm))

    def _transcrire(self, pcm: bytes) -> tuple[str, str, str]:
        """(texte, voie, erreur) : le modèle fichier d'ElevenLabs, sinon Gemini."""
        erreur = ""
        if self.client.cle:
            try:
                return self.client.transcrire(pcm, self.m.langue, self.mots), "precis", ""
            except Exception as e:
                erreur = str(e)
        try:
            return self.m.transcrire_gemini(pcm), "gemini", erreur
        except Exception as e:
            return "", "erreur", f"{erreur} / {e}"

    def terminer(self, delai: float = 200.0):
        from .moteur import Resultat
        from .mots_courants import courant

        relache = time.perf_counter()
        with self._verrou:
            fin = len(self.pcm)  # le reste du tampon d'analyse est déjà dans pcm
            # le dernier morceau part s'il contient de la voix ; une dictée entière sans voix détectée part
            # quand même (voix très faible) : le moteur et les filtres de l'appli trancheront
            if fin - self._debut_morceau >= 300 * OCTETS_PAR_MS and (self._parole_ms > 0 or not self._morceaux):
                pcm = bytes(self.pcm[self._debut_morceau:fin])
                self._morceaux.append(self.pool.submit(self._transcrire, pcm))
            morceaux = list(self._morceaux)
        textes, voies, erreurs = [], set(), []
        for f in morceaux:
            try:
                t, v, e = f.result(timeout=max(1.0, delai - (time.perf_counter() - relache)))
            except Exception as e:
                t, v, e = "", "erreur", str(e)
            textes.append(t)
            voies.add(v)
            if e:
                erreurs.append(e)
        ms = int(1000 * (time.perf_counter() - relache))
        texte = joindre(textes, courant)
        if self._annulee:
            return Resultat("", "vide", ms, "annulée")
        if not texte:
            voie = "erreur" if "erreur" in voies else "vide"
        else:
            voie = "gemini" if "gemini" in voies else "precis"
        return Resultat(texte, voie, ms, " | ".join(erreurs), morceaux=textes)

    def annuler(self) -> None:
        self._annulee = True

    def duree(self) -> float:
        return len(self.pcm) / 2 / TAUX
