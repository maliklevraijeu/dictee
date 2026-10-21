"""Le micro : 16 kHz, mono, 16 bits, par paquets de 50 ms.

Le micro choisi est gardé pendant toute la dictée, même si Windows change de micro par défaut
(branchement d'un écran HDMI, d'un casque). Le flux s'ouvre à l'appui et se ferme au relâchement :
le voyant micro de Windows ne reste pas allumé en permanence.
"""
from __future__ import annotations

import os
import threading
import time
import wave
from typing import Callable

import numpy as np
import sounddevice as sd

TAUX = 16000
BLOC = 800  # 50 ms


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
    def __init__(self, nom: str = ""):
        self.nom = nom
        self._flux: sd.InputStream | None = None
        self._verrou = threading.Lock()
        self._lecture = False
        self.niveau = 0.0  # 0..1, pour la pastille
        self.crete = 0  # plus forte valeur entendue pendant la dictée
        self.remplacant = ""  # nom du micro pris à la place du micro choisi, s'il manquait

    def demarrer(self, recevoir: Callable[[bytes], None]) -> None:
        essai = os.environ.get("DICTEE_FICHIER_MICRO")
        if essai:
            self._depuis_fichier(essai, recevoir)
            return

        def rappel(donnees, _n, _t, _statut):
            x = donnees[:, 0]
            self.crete = max(self.crete, int(np.abs(x).max()) if len(x) else 0)
            # niveau lissé pour l'affichage (RMS en échelle « perceptive »)
            rms = float(np.sqrt(np.mean((x.astype(np.float32) / 32768.0) ** 2)))
            self.niveau = 0.6 * self.niveau + 0.4 * min(1.0, rms * 12)
            recevoir(x.tobytes())

        with self._verrou:
            self.arreter()
            self.crete = 0
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
                self._flux = sd.InputStream(samplerate=TAUX, channels=1, dtype="int16", blocksize=BLOC,
                                            device=appareil, callback=rappel)
            except Exception:
                # le micro par défaut d'il y a une heure a été débranché : on relit la liste une fois
                _relire_les_micros()
                self._flux = sd.InputStream(samplerate=TAUX, channels=1, dtype="int16", blocksize=BLOC,
                                            device=trouver_micro(self.nom), callback=rappel)
            self._flux.start()

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
                x = np.frombuffer(pcm[i:i + BLOC * 2], dtype=np.int16)
                self.crete = max(self.crete, int(np.abs(x).max()) if len(x) else 0)
                rms = float(np.sqrt(np.mean((x.astype(np.float32) / 32768.0) ** 2))) if len(x) else 0.0
                self.niveau = 0.6 * self.niveau + 0.4 * min(1.0, rms * 12)
                recevoir(pcm[i:i + BLOC * 2])
                time.sleep(BLOC / TAUX)

        threading.Thread(target=lire, daemon=True).start()

    def arreter(self) -> None:
        self._lecture = False
        f = self._flux
        self._flux = None
        self.niveau = 0.0
        if f is not None:
            try:
                f.stop()
                f.close()
            except Exception:
                pass

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
