"""Le micro : 16 kHz, mono, 16 bits, par paquets de 50 ms.

Le micro choisi est gardé pendant toute la dictée, même si Windows change de micro par défaut
(branchement d'un écran HDMI, d'un casque).

Le premier mot n'est jamais coupé : le micro reste prêt en arrière-plan et garde en mémoire vive les
0,4 dernière seconde (rien n'est envoyé ni enregistré hors d'une dictée). À l'appui, ces 0,4 s partent
en tête de la dictée. Mesuré le 21/10 : ouvert à l'appui, le micro rendait son premier son 100 à 130 ms
après, et les mots qui commencent la phrase perdaient leur première syllabe (« Identifie » -> « Défie »).
Exception : un casque Bluetooth reste fermé entre les dictées, sinon Windows le garde en mode
« mains libres » et la musique y passe en mauvaise qualité.
"""
from __future__ import annotations

import collections
import os
import re
import threading
import time
import wave
from typing import Callable

import numpy as np
import sounddevice as sd

TAUX = 16000
BLOC = 800  # 50 ms
AVANCE_S = 0.4  # audio gardé avant l'appui
_BLUETOOTH = re.compile(r"hands-?free|mains libres|bluetooth|airpods|headset|\bbt\b", re.I)


def lister_micros() -> list[tuple[int, str]]:
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            out.append((i, d["name"]))
    return out


def _accepte_16k(i: int) -> bool:
    try:
        sd.check_input_settings(device=i, samplerate=TAUX, channels=1, dtype="int16")
        return True
    except Exception:
        return False


def trouver_micro(nom: str) -> int | None:
    """Le micro dont le nom contient `nom`, par une entrée qui accepte VRAIMENT 16 kHz mono.
    Piège mesuré le 21/10 : l'entrée WASAPI du micro du PC refuse ce format ; la prendre faisait
    retomber en silence sur la prise casque, muette. DirectSound puis MME convertissent eux-mêmes."""
    if not nom:
        return None
    nom = nom.lower()
    hotes = {i: h["name"] for i, h in enumerate(sd.query_hostapis())}
    ordre = {"Windows DirectSound": 0, "MME": 1, "Windows WASAPI": 2}
    candidats = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and nom in d["name"].lower():
            candidats.append((ordre.get(hotes.get(d["hostapi"], ""), 3), i))
    for _, i in sorted(candidats):
        if _accepte_16k(i):
            return i
    return None


def _relire_les_micros() -> None:
    """PortAudio ne voit que les micros présents à son démarrage : on le redémarre (aucun flux ouvert)."""
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        pass


class Micro:
    def __init__(self, nom: str = "", pret: bool = True):
        self.nom = nom
        self.pret = pret  # garder le micro ouvert entre les dictées (voir en tête du fichier)
        self._flux: sd.InputStream | None = None
        self._ouvert_pour: str | None = None  # le réglage « micro » au moment de l'ouverture
        self._verrou = threading.Lock()  # ouverture et fermeture du flux
        self._verrou_audio = threading.Lock()  # bascule entre « en attente » et « en dictée »
        self._recevoir: Callable[[bytes], None] | None = None
        self._avance: collections.deque[bytes] = collections.deque(maxlen=int(AVANCE_S * TAUX / BLOC))
        self._lecture = False
        self.niveau = 0.0  # 0..1, pour la pastille
        self.crete = 0  # plus forte valeur entendue pendant la dictée
        self.remplacant = ""  # nom du micro pris à la place du micro choisi, s'il manquait

    # --- le flux ---------------------------------------------------------------------------
    def _rappel(self, donnees, _n, _t, _statut) -> None:
        x = donnees[:, 0]
        morceau = x.tobytes()
        with self._verrou_audio:
            recevoir = self._recevoir
            if recevoir is None:
                self._avance.append(morceau)
                return
        self._mesurer(x)
        recevoir(morceau)

    def _mesurer(self, x) -> None:
        self.crete = max(self.crete, int(np.abs(x).max()) if len(x) else 0)
        # niveau lissé pour l'affichage (RMS en échelle « perceptive »)
        rms = float(np.sqrt(np.mean((x.astype(np.float32) / 32768.0) ** 2))) if len(x) else 0.0
        self.niveau = 0.6 * self.niveau + 0.4 * min(1.0, rms * 12)

    def _actif(self) -> bool:
        try:
            return self._flux is not None and self._flux.active and self._ouvert_pour == self.nom
        except Exception:
            return False

    def _garder_pret(self) -> bool:
        if not self.pret or os.environ.get("DICTEE_FICHIER_MICRO"):
            return False
        return not _BLUETOOTH.search(self.nom or self.nom_par_defaut())

    def _ouvrir(self) -> None:
        self._fermer_flux()
        self.remplacant = ""
        appareil = trouver_micro(self.nom)
        if self.nom and appareil is None:
            # La liste des micros n'est lue qu'au démarrage : un casque branché depuis n'y est pas.
            _relire_les_micros()
            appareil = trouver_micro(self.nom)
        if self.nom and appareil is None:
            # Micro choisi absent (débranché) : on prend celui de Windows, et on le DIT.
            self.remplacant = self.nom_par_defaut()
        try:
            flux = sd.InputStream(samplerate=TAUX, channels=1, dtype="int16", blocksize=BLOC,
                                  device=appareil, callback=self._rappel)
        except Exception:
            # le micro par défaut d'il y a une heure a été débranché : on relit la liste une fois
            _relire_les_micros()
            flux = sd.InputStream(samplerate=TAUX, channels=1, dtype="int16", blocksize=BLOC,
                                  device=trouver_micro(self.nom), callback=self._rappel)
        flux.start()
        self._flux, self._ouvert_pour = flux, self.nom

    def _fermer_flux(self) -> None:
        f, self._flux, self._ouvert_pour = self._flux, None, None
        with self._verrou_audio:
            self._avance.clear()
        if f is not None:
            try:
                f.stop()
                f.close()
            except Exception:
                pass

    # --- ce que l'appli appelle ---------------------------------------------------------------
    def preparer(self) -> None:
        """Au lancement et après un changement de micro : le micro se met en attente, prêt."""
        with self._verrou:
            if self._garder_pret() and not self._actif():
                try:
                    self._ouvrir()
                except Exception:
                    self._fermer_flux()  # pas de micro pour l'instant : on réessaiera à l'appui

    def demarrer(self, recevoir: Callable[[bytes], None]) -> None:
        essai = os.environ.get("DICTEE_FICHIER_MICRO")
        if essai:
            self._depuis_fichier(essai, recevoir)
            return
        with self._verrou:
            self.crete = 0
            if not self._actif():
                self._ouvrir()
            # l'audio d'avant l'appui part en tête, puis tout le reste suit au fil de l'eau
            with self._verrou_audio:
                avance = list(self._avance)
                self._avance.clear()
                for morceau in avance:
                    self._mesurer(np.frombuffer(morceau, dtype=np.int16))
                    recevoir(morceau)
                self._recevoir = recevoir

    def _depuis_fichier(self, chemin: str, recevoir: Callable[[bytes], None]) -> None:
        """Pour les tests : un WAV 16 kHz joue le rôle du micro, au rythme réel."""
        self._lecture = True
        self.crete = 0

        def lire():
            with wave.open(chemin) as w:
                pcm = w.readframes(w.getnframes())
            for i in range(0, len(pcm), BLOC * 2):
                if not self._lecture:
                    break
                self._mesurer(np.frombuffer(pcm[i:i + BLOC * 2], dtype=np.int16))
                recevoir(pcm[i:i + BLOC * 2])
                time.sleep(BLOC / TAUX)

        threading.Thread(target=lire, daemon=True).start()

    def arreter(self) -> None:
        """Fin de la dictée : plus rien n'est transmis ; le micro reste prêt (sauf Bluetooth)."""
        self._lecture = False
        with self._verrou_audio:
            self._recevoir = None
        self.niveau = 0.0
        with self._verrou:
            if not self._garder_pret():
                self._fermer_flux()

    def fermer(self) -> None:
        """Quitter, ou changer de micro (suivi de preparer())."""
        self._lecture = False
        with self._verrou_audio:
            self._recevoir = None
        with self._verrou:
            self._fermer_flux()

    def muet(self) -> bool:
        """Silence numérique parfait pendant toute la dictée : micro coupé ou mauvais micro."""
        return self.crete <= 2

    @staticmethod
    def nom_par_defaut() -> str:
        try:
            return sd.query_devices(sd.default.device[0])["name"]
        except Exception:
            return "?"

    def nom_actif(self) -> str:
        i = trouver_micro(self.nom)
        try:
            return sd.query_devices(i if i is not None else sd.default.device[0])["name"]
        except Exception:
            return "?"
