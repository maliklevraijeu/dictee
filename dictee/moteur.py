"""Le moteur de transcription : ElevenLabs Scribe v2 en DIRECT (WebSocket), pendant qu'on parle.

Pourquoi en direct : envoyé d'un bloc après la dictée, Scribe met ~1,3 s (mesuré sur 40 vraies
dictées). En direct, le texte est déjà transcrit quand la touche est
relâchée : il ne reste que la dernière phrase, ~0,5 s.

La connexion s'ouvre à l'appui de la touche ; l'audio est gardé en mémoire pendant ce temps, rien
n'est perdu. Si le direct tombe (réseau, serveur), la dictée complète repart en un bloc : on ne
perd jamais une dictée.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import wave
import threading
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field

import websockets

URL_DIRECT = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
URL_BLOC = "https://api.elevenlabs.io/v1/speech-to-text"
TAUX = 16000
FIN = object()
ANNULE = object()


@dataclass
class Resultat:
    texte: str
    voie: str  # "direct" | "bloc" | "vide" | "erreur"
    latence_ms: int  # du relâchement de la touche au texte final
    erreur: str = ""
    morceaux: list[str] = field(default_factory=list)


def _mots_direct(mots: list[str]) -> list[str]:
    # Le direct accepte 50 mots de 20 caractères maximum.
    out = []
    for m in mots:
        m = m.strip()
        if m and len(m) <= 20 and not any(c in m for c in "<>{}[]\\") and m not in out:
            out.append(m)
    return out[:50]


def _mots_bloc(mots: list[str]) -> list[str]:
    # En bloc : jusqu'à 1 000, mais au-delà de 100 Scribe facture 20 s minimum par dictée.
    out = []
    for m in mots:
        m = m.strip()
        if m and len(m) < 50 and len(m.split()) <= 5 and not any(c in m for c in "<>{}[]\\") and m not in out:
            out.append(m)
    return out[:100]


class Moteur:
    """Une boucle asyncio dans son propre fil ; chaque dictée est une Session."""

    def __init__(self, cle: str, langue: str = "fr", mots: list[str] | None = None, reecriture: bool = False,
                 decoupe: str = "vad", langues_secondaires: list[str] | None = None):
        self.cle = cle
        self.langue = langue
        # Autres langues que tu dictes parfois (français + anglais par défaut).
        self.langues_secondaires = langues_secondaires or []
        self.mots = mots or []
        # reecriture=True : option « no_verbatim » du moteur. Elle retire les hésitations MAIS corrige
        # aussi la langue parlée (« c'est pas » -> « ce n'est pas ») : désactivée par défaut, on garde
        # tes mots et on ne retire que les « euh » et les faux départs (nettoyage.py).
        self.sans_hesitations = reecriture
        # "vad" : le moteur valide chaque phrase à la pause (le texte est prêt plus tôt) ;
        # "manuel" : toute la dictée d'un seul tenant (meilleure ponctuation sur les longues).
        self.decoupe = decoupe
        self.boucle = asyncio.new_event_loop()
        self._fil = threading.Thread(target=self.boucle.run_forever, name="moteur", daemon=True)
        self._fil.start()

    def nouvelle_session(self) -> "Session":
        return Session(self)

    def url_direct(self) -> str:
        p = [("model_id", "scribe_v2_realtime"), ("audio_format", "pcm_16000"), ("language_code", self.langue)]
        p += [("secondary_languages", l) for l in self.langues_secondaires]
        if self.decoupe == "vad":
            p += [("commit_strategy", "vad"), ("vad_silence_threshold_secs", "1.2")]
        else:
            p += [("commit_strategy", "manual")]
        if self.sans_hesitations:
            p.append(("no_verbatim", "true"))
        p += [("keyterms", m) for m in _mots_direct(self.mots)]
        return URL_DIRECT + "?" + urllib.parse.urlencode(p)

    def transcrire_bloc(self, pcm: bytes) -> str:
        """La voie de secours : toute la dictée d'un coup (bloquant)."""
        b = uuid.uuid4().hex
        champs = [("model_id", "scribe_v2"), ("language_code", self.langue), ("file_format", "pcm_s16le_16"),
                  ("tag_audio_events", "false")]
        if self.sans_hesitations:
            champs.append(("no_verbatim", "true"))
        champs += [("keyterms", m) for m in _mots_bloc(self.mots)]
        corps = b"".join(f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode() for k, v in champs)
        corps += (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.pcm\"\r\n"
                  "Content-Type: application/octet-stream\r\n\r\n").encode() + pcm + f"\r\n--{b}--\r\n".encode()
        req = urllib.request.Request(URL_BLOC, data=corps, method="POST",
                                     headers={"xi-api-key": self.cle, "Content-Type": f"multipart/form-data; boundary={b}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read()).get("text", "").strip()

    # --- deuxième moteur de secours : Gemini (si ElevenLabs refuse : crédits épuisés, panne) ---
    cle_gemini: str = ""
    # Mesuré le 21/10 : gemini-3.1-flash-lite sans réflexion = 1,4 à 2 s ; gemini-flash-latest = ~60 s
    # (il réfléchit avant de répondre) ; 2.5-flash-lite n'est plus ouvert aux nouveaux comptes.
    MODELES_GEMINI = (("gemini-3.1-flash-lite", {"thinkingConfig": {"thinkingBudget": 0}}),
                      ("gemini-3.5-flash-lite", {}))

    def transcrire_gemini(self, pcm: bytes) -> str:
        if not self.cle_gemini:
            raise RuntimeError("pas de clé Gemini")
        tampon = io.BytesIO()
        with wave.open(tampon, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(TAUX)
            w.writeframes(pcm)
        if self.langue.lower().startswith("fr"):
            consigne = (
                "Transcris exactement ce qui est dit dans cet audio, mot pour mot, en français (les mots anglais "
                "restent en anglais). Ponctue normalement. Ne résume pas, ne reformule pas, ne corrige pas le "
                "langage parlé, n'ajoute rien. Réponds uniquement par la transcription. "
                f"Vocabulaire possible : {', '.join(_mots_direct(self.mots))}."
            )
        else:
            consigne = (
                "Transcribe exactly what is said in this audio, word for word, in the language spoken. Use normal "
                "punctuation. Do not summarize, rephrase or correct spoken language, add nothing. Reply with the "
                f"transcript only. Possible vocabulary: {', '.join(_mots_direct(self.mots))}."
            )
        audio = base64.b64encode(tampon.getvalue()).decode()
        derniere = None
        for modele, reglages in self.MODELES_GEMINI:
            corps = json.dumps({
                "contents": [{"parts": [{"text": consigne}, {"inline_data": {"mime_type": "audio/wav", "data": audio}}]}],
                "generationConfig": {"temperature": 0, **reglages},
            }).encode()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent"
            req = urllib.request.Request(url, data=corps, method="POST",
                                         headers={"Content-Type": "application/json", "x-goog-api-key": self.cle_gemini})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.loads(r.read())
                parts = d["candidates"][0]["content"]["parts"]
                return "".join(p.get("text", "") for p in parts).strip()
            except Exception as e:  # modèle indisponible : on essaie le suivant
                derniere = e
        raise RuntimeError(f"Gemini : {derniere}")


class Session:
    """Une dictée. `pousser()` reçoit l'audio (n'importe quel fil), `terminer()` rend le texte."""

    def __init__(self, moteur: Moteur):
        self.m = moteur
        self.pcm = bytearray()  # toute la dictée, pour la voie de secours et l'historique
        self._file: asyncio.Queue = asyncio.Queue()
        self._fini = threading.Event()
        self._resultat: Resultat | None = None
        self._relache = 0.0
        self._fin_recue = False
        self._annulee = False
        self._tache = asyncio.run_coroutine_threadsafe(self._courir(), moteur.boucle)

    # --- côté application -------------------------------------------------
    def pousser(self, morceau: bytes) -> None:
        self.pcm.extend(morceau)
        self.m.boucle.call_soon_threadsafe(self._file.put_nowait, bytes(morceau))

    def terminer(self, delai: float = 200.0) -> Resultat:
        # Le délai couvre aussi les secours (bloc ElevenLabs puis Gemini) : un texte qui arrive
        # tard vaut mieux qu'une dictée perdue.
        self._relache = time.perf_counter()
        self.m.boucle.call_soon_threadsafe(self._file.put_nowait, FIN)
        if not self._fini.wait(delai):
            return Resultat("", "erreur", int(delai * 1000), "pas de réponse")
        return self._resultat  # type: ignore[return-value]

    def annuler(self) -> None:
        self.m.boucle.call_soon_threadsafe(self._file.put_nowait, ANNULE)

    def duree(self) -> float:
        return len(self.pcm) / 2 / TAUX

    # --- côté moteur --------------------------------------------------------
    def _rendre(self, r: Resultat) -> None:
        self._resultat = r
        self._fini.set()

    async def _courir(self) -> None:
        morceaux: list[str] = []
        try:
            if not self.m.cle:
                raise RuntimeError("pas de clé ElevenLabs : Gemini seul")
            async with websockets.connect(self.m.url_direct(), additional_headers={"xi-api-key": self.m.cle},
                                          max_size=None, open_timeout=8) as ws:
                d = json.loads(await asyncio.wait_for(ws.recv(), 8))
                if d.get("message_type") != "session_started":
                    raise RuntimeError(d.get("error") or d.get("message_type") or "session refusée")
                commit_envoye = asyncio.Event()
                final = asyncio.Event()
                erreurs: list[str] = []

                async def lire():
                    async for brut in ws:
                        msg = json.loads(brut)
                        t = msg.get("message_type")
                        if t == "committed_transcript":
                            if msg.get("text", "").strip():
                                morceaux.append(msg["text"].strip())
                            if commit_envoye.is_set():
                                final.set()
                        elif t in ("partial_transcript", "committed_transcript_with_timestamps", "session_started"):
                            continue
                        elif t == "insufficient_audio_activity":
                            final.set()
                        elif msg.get("error"):
                            erreurs.append(f"{t}: {msg.get('error')}")
                            final.set()

                lecteur = asyncio.create_task(lire())
                tampon = bytearray()
                while True:
                    x = await self._file.get()
                    if x is ANNULE:
                        lecteur.cancel()
                        self._rendre(Resultat("", "vide", 0, "annulée"))
                        return
                    if x is FIN:
                        self._fin_recue = True
                        if tampon:
                            await self._envoyer(ws, bytes(tampon))
                            tampon.clear()
                        await ws.send(json.dumps({"message_type": "input_audio_chunk", "audio_base_64": "",
                                                  "commit": True, "sample_rate": TAUX}))
                        commit_envoye.set()
                        break
                    tampon.extend(x)
                    # Paquets de ~100 ms : assez petits pour le direct, pas trop de messages.
                    if len(tampon) >= 3200:
                        await self._envoyer(ws, bytes(tampon))
                        tampon.clear()
                try:
                    await asyncio.wait_for(final.wait(), timeout=4)
                except asyncio.TimeoutError:
                    raise RuntimeError("pas de texte final en 4 s")
                finally:
                    lecteur.cancel()
                if erreurs and not morceaux:
                    raise RuntimeError(erreurs[0])
                texte = " ".join(morceaux).strip()
                self._rendre(Resultat(texte, "direct" if texte else "vide", self._ms(), morceaux=morceaux))
        except Exception as e:  # le direct est tombé : la dictée complète repart d'un bloc
            await self._attendre_fin()
            if self._annulee:
                self._rendre(Resultat("", "vide", 0, "annulée"))
                return
            if self.duree() < 0.3:
                self._rendre(Resultat("", "vide", self._ms(), str(e)))
                return
            boucle = asyncio.get_running_loop()
            try:
                if not self.m.cle:
                    raise RuntimeError("pas de clé ElevenLabs")
                texte = await boucle.run_in_executor(None, self.m.transcrire_bloc, bytes(self.pcm))
                self._rendre(Resultat(texte, "bloc", self._ms(), f"direct indisponible : {e}"))
            except Exception as e2:
                try:
                    texte = await boucle.run_in_executor(None, self.m.transcrire_gemini, bytes(self.pcm))
                    self._rendre(Resultat(texte, "gemini", self._ms(), f"ElevenLabs indisponible : {e2}"))
                except Exception as e3:
                    self._rendre(Resultat("", "erreur", self._ms(), f"{e} / {e2} / {e3}"))

    async def _envoyer(self, ws, pcm: bytes) -> None:
        await ws.send(json.dumps({"message_type": "input_audio_chunk", "audio_base_64": base64.b64encode(pcm).decode(),
                                  "commit": False, "sample_rate": TAUX}))

    async def _attendre_fin(self) -> None:
        # En secours, on attend que la touche soit relâchée (tout l'audio est alors dans self.pcm).
        while not self._fin_recue:
            x = await self._file.get()
            if x is FIN:
                self._fin_recue = True
            elif x is ANNULE:
                self._annulee = True
                return

    def _ms(self) -> int:
        return int((time.perf_counter() - self._relache) * 1000) if self._relache else 0
