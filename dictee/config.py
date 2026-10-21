"""Réglages de Dictée : un fichier JSON lisible dans %APPDATA%\\Dictee\\config.json.
Tout a une valeur par défaut ; une valeur absente ou du mauvais type garde la sienne."""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

DOSSIER = Path(os.environ.get("APPDATA", Path.home())) / "Dictee"
FICHIER = DOSSIER / "config.json"


@dataclass
class Config:
    # Maintenir pour parler, relâcher pour coller.
    raccourci: str = "ctrl+win"
    # Mains libres : ce raccourci démarre, le raccourci principal (ou Échap) arrête.
    mains_libres: str = "ctrl+win+space"
    # Recoller la dernière dictée (si le collage a raté ou pour la remettre ailleurs).
    recoller: str = "alt+shift+z"
    # Langue de la dictée ("fr", "en"...) et autres langues que tu glisses parfois dedans. Au premier
    # lancement, elles suivent la langue de Windows.
    langue: str = "fr"
    langues_secondaires: list[str] = field(default_factory=lambda: ["en"])
    # Langue des fenêtres et des messages : "auto" (celle de Windows), "fr" ou "en".
    interface: str = "auto"
    # Nom (ou morceau du nom) du micro à utiliser. Vide = micro par défaut de Windows au démarrage.
    # On ne suit PAS les changements du micro par défaut en cours de route : un écran branché en HDMI
    # peut devenir le micro par défaut de Windows plusieurs fois par jour.
    micro: str = ""
    # Retirer les « euh » et les faux départs (« j'aimerais-- j'aurais aimé »), rien d'autre.
    sans_hesitations: bool = True
    # Laisser le moteur réécrire en français « propre » (« c'est pas » -> « ce n'est pas »). Non par
    # défaut : on garde ta façon de parler.
    reecriture: bool = False
    # "manuel" : la dictée est validée d'un seul tenant au relâchement (le plus fiable) ; "vad" : chaque
    # phrase est validée à la pause.
    decoupe: str = "manuel"
    # Mots à reconnaître en priorité (noms, marques, jargon). 50 maximum envoyés au moteur en direct.
    mots: list[str] = field(default_factory=list)
    # Remplacements après transcription : « ce qui est entendu » -> « ce qui est écrit ».
    remplacements: dict[str, str] = field(default_factory=dict)
    # Raccourcis de texte : dire la phrase colle le texte complet.
    snippets: dict[str, str] = field(default_factory=dict)
    # Retenir le mot sélectionné (dans n'importe quelle appli) : il entre dans ton vocabulaire.
    memoriser: str = "alt+shift+m"
    # Apprendre des corrections que tu fais juste après un collage (voir apprentissage.py).
    apprendre: bool = True
    # Dicter depuis le téléphone (page sur le Wi-Fi local, voir telephone.py). Allumé depuis l'icône.
    telephone: bool = False
    sons: bool = True
    # Durée maximale d'une dictée, en secondes.
    duree_max: int = 600
    # L'audio n'est gardé que pour les dictées RATÉES (pour pouvoir les retranscrire), N jours.
    # Les dictées réussies ne laissent que leur texte : rien ne s'accumule sur le disque.
    garder_audio_jours: int = 7
    # Où lire la clé ElevenLabs : variable d'environnement, sinon commande (un gestionnaire de secrets), sinon le coffre chiffré.
    cle_env: str = "ELEVENLABS_API_KEY"
    cle_commande: str = ""
    # Moteur de secours si ElevenLabs refuse (crédits épuisés, panne) : Gemini. Vide = pas de secours.
    cle_gemini_env: str = "GEMINI_API_KEY"
    cle_gemini_commande: str = ""

    @classmethod
    def charger(cls) -> "Config":
        c = cls()
        if not FICHIER.exists():
            from .langues import langue_systeme

            if langue_systeme() == "en":  # premier lancement sur un Windows anglais : on dicte en anglais
                c.langue, c.langues_secondaires = "en", []
            return c
        try:
            d = json.loads(FICHIER.read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                raise ValueError("pas un objet JSON")
        except (OSError, ValueError):
            # Réglages illisibles : on les met de côté (jamais écrasés) et on repart des valeurs par défaut.
            try:
                os.replace(FICHIER, FICHIER.with_name(time.strftime("config-abimee-%Y%m%d-%H%M%S.json")))
            except OSError:
                pass
            return c
        for k, v in d.items():
            defaut = getattr(c, k, None)
            if defaut is None or isinstance(defaut, bool) != isinstance(v, bool):
                continue
            if isinstance(defaut, (int, float)) and not isinstance(defaut, bool):
                if isinstance(v, (int, float)):
                    setattr(c, k, type(defaut)(v))
            elif isinstance(v, type(defaut)):  # une valeur du mauvais type garde la valeur par défaut
                setattr(c, k, v)
        return c

    @classmethod
    def modifier(cls, **valeurs) -> "Config":
        """Change quelques réglages en relisant le fichier d'abord : ce que l'utilisateur a écrit à la
        main pendant que Dictée tournait n'est pas écrasé."""
        c = cls.charger()
        for k, v in valeurs.items():
            setattr(c, k, v)
        c.enregistrer()
        return c

    def enregistrer(self) -> None:
        DOSSIER.mkdir(parents=True, exist_ok=True)
        FICHIER.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    def cle_api(self) -> str:
        return _lire_cle(self.cle_env, self.cle_commande) or _du_coffre("elevenlabs")

    def cle_gemini(self) -> str:
        return _lire_cle(self.cle_gemini_env, self.cle_gemini_commande) or _du_coffre("gemini")


def _du_coffre(nom: str) -> str:
    from . import coffre

    return coffre.lire().get(nom, "")


def _lire_cle(env: str, commande: str) -> str:
    v = os.environ.get(env, "").strip() if env else ""
    if v:
        return v
    if commande:
        try:
            r = subprocess.run(commande, shell=True, capture_output=True, text=True, timeout=20,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return r.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    return ""
