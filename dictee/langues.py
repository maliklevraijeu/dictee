"""Les textes de l'interface, en français et en anglais.

La langue de l'interface suit celle de Windows (réglage « interface » : "auto", "fr" ou "en"). La langue
de la dictée est un autre réglage (« langue ») : on peut avoir l'interface en anglais et dicter en français.
"""
from __future__ import annotations

import ctypes

TEXTES: dict[str, dict[str, str]] = {
    "fr": {
        # pastille
        "micro_introuvable": "Micro introuvable : {erreur}",
        "annulee": "Dictée annulée",
        "cle_refusee": "Clé refusée : change-la dans le menu de l'icône",
        "quota": "Crédits ou quota épuisés chez le service de transcription",
        "reseau": "Réseau indisponible : dictée gardée dans l'historique",
        "micro_muet": "Micro muet ({micro}) : change-le dans l'icône Dictée",
        "rien_entendu": "Rien entendu",
        "test": "Test : collage retenu",
        "admin": "Fenêtre administrateur : colle avec Ctrl+V",
        "copie": "Copié : fais Ctrl+V",
        "micro_remplace": "Micro choisi absent, pris : {micro}",
        "appris": "Appris : {mots}",
        "selection_vide": "Sélectionne d'abord un mot",
        "selection_longue": "Sélection trop longue : un nom ou quelques mots",
        "retenu": "Retenu : {mot}",
        "deja_connu": "Déjà connu : {mot}",
        "cles_ok": "Clés enregistrées",
        "recu_telephone": "Reçu du téléphone : fais Ctrl+V",
        "pare_feu_oui": "Réponds « Oui » à Windows pour ouvrir ton Wi-Fi à Dictée",
        "pare_feu_non": "Sans l'accord de Windows, le téléphone ne peut pas joindre le PC",
        "telephone_impossible": "Impossible d'ouvrir la dictée par téléphone",
        "raccourci_invalide": "Raccourci invalide dans les réglages ({erreur}) : Ctrl+Win gardé",
        "demarrage_rate": "Dictée n'a pas pu démarrer. Détail dans :\n{chemin}",
        # menu de l'icône
        "etat": "Dictée : {etat} ({raccourci})",
        "prete": "prête",
        "en_pause": "en pause",
        "menu_memoire": "Ta mémoire",
        "menu_telephone": "Dicter depuis le téléphone",
        "menu_pause": "Pause",
        "menu_recoller": "Recoller la dernière dictée",
        "menu_micro": "Micro",
        "micro_windows": "Celui de Windows",
        "menu_demarrage": "Lancer avec Windows",
        "menu_cles": "Changer de clé",
        "menu_reglages": "Réglages",
        "menu_quitter": "Quitter",
        # première fenêtre
        "accueil_sous_titre": "Maintiens Ctrl+Win, parle, relâche : le texte se colle.",
        "accueil_cle": "Colle au moins une clé : un code qu'ElevenLabs ou Google te donne avec un compte.",
        "cle_eleven": "Clé ElevenLabs",
        "cle_gemini": "Clé Gemini",
        "aide_eleven": "La plus rapide (conseillée)",
        "aide_gemini": "Gratuite, 1 à 2 s par dictée, sert aussi de secours",
        "obtenir_cle": "obtenir une clé",
        "aucune_cle": "Colle au moins une clé.",
        "commencer": "Commencer",
        "cles_chiffrees": "Tes clés restent chiffrées sur ce PC.",
        # Ta mémoire
        "memoire_titre": "Ta mémoire",
        "onglet_mots": "Tes mots",
        "onglet_corrections": "Corrections",
        "onglet_dictees": "Dernières dictées",
        "col_mot": "Mot",
        "col_origine": "Origine",
        "col_dit": "Dit",
        "col_entendu": "Entendu",
        "col_ecrit": "Écrit",
        "col_fois": "Fois",
        "col_quand": "Quand",
        "col_texte": "Texte",
        "source_import": "importé",
        "source_manuel": "ajouté",
        "source_selection": "retenu",
        "source_correction": "appris",
        "indice_mots": "Mars Men, Canva, …",
        "ajouter": "Ajouter",
        "retirer": "Retirer la sélection",
        "copier": "Copier",
        "aide_corrections": "Un nom mal entendu ? Écris ce que le moteur entend, puis le bon mot.",
        "indice_entendu": "entendu : Mark Smead",
        "indice_ecrit": "écrit : Mars Men",
        # téléphone
        "tel_titre": "Dicter depuis ton téléphone",
        "tel_scanne": "Scanne avec l'appareil photo, sur le même Wi-Fi que ce PC.",
        "tel_mode": "Touche le micro du clavier, parle, puis « Envoyer au PC » :\nle texte se colle là où est ton curseur.",
        "tel_couper": "Couper la dictée par téléphone",
        "tel_perime": "Lien périmé : rescanne le QR code sur le PC.",
    },
    "en": {
        "micro_introuvable": "Microphone not found: {erreur}",
        "annulee": "Dictation cancelled",
        "cle_refusee": "Key rejected: change it from the tray icon menu",
        "quota": "The transcription service is out of credits or quota",
        "reseau": "Network unavailable: dictation kept in the history",
        "micro_muet": "Microphone is silent ({micro}): change it from the tray icon",
        "rien_entendu": "Nothing heard",
        "test": "Test: paste skipped",
        "admin": "Administrator window: paste with Ctrl+V",
        "copie": "Copied: press Ctrl+V",
        "micro_remplace": "Chosen microphone missing, using: {micro}",
        "appris": "Learned: {mots}",
        "selection_vide": "Select a word first",
        "selection_longue": "Selection too long: a name or a few words",
        "retenu": "Remembered: {mot}",
        "deja_connu": "Already known: {mot}",
        "cles_ok": "Keys saved",
        "recu_telephone": "Received from your phone: press Ctrl+V",
        "pare_feu_oui": "Answer \"Yes\" in the Windows prompt to open your Wi-Fi to Dictée",
        "pare_feu_non": "Without Windows' approval, your phone can't reach this PC",
        "telephone_impossible": "Couldn't start phone dictation",
        "raccourci_invalide": "Invalid shortcut in the settings ({erreur}): keeping Ctrl+Win",
        "demarrage_rate": "Dictée couldn't start. Details in:\n{chemin}",
        "etat": "Dictée: {etat} ({raccourci})",
        "prete": "ready",
        "en_pause": "paused",
        "menu_memoire": "Your memory",
        "menu_telephone": "Dictate from your phone",
        "menu_pause": "Pause",
        "menu_recoller": "Paste the last dictation again",
        "menu_micro": "Microphone",
        "micro_windows": "Windows default",
        "menu_demarrage": "Start with Windows",
        "menu_cles": "Change key",
        "menu_reglages": "Settings",
        "menu_quitter": "Quit",
        "accueil_sous_titre": "Hold Ctrl+Win, speak, release: the text is pasted.",
        "accueil_cle": "Paste at least one key: a code ElevenLabs or Google gives you with an account.",
        "cle_eleven": "ElevenLabs key",
        "cle_gemini": "Gemini key",
        "aide_eleven": "The fastest (recommended)",
        "aide_gemini": "Free, 1 to 2 s per dictation, also used as a backup",
        "obtenir_cle": "get a key",
        "aucune_cle": "Paste at least one key.",
        "commencer": "Start",
        "cles_chiffrees": "Your keys stay encrypted on this PC.",
        "memoire_titre": "Your memory",
        "onglet_mots": "Your words",
        "onglet_corrections": "Corrections",
        "onglet_dictees": "Recent dictations",
        "col_mot": "Word",
        "col_origine": "Source",
        "col_dit": "Said",
        "col_entendu": "Heard",
        "col_ecrit": "Written",
        "col_fois": "Times",
        "col_quand": "When",
        "col_texte": "Text",
        "source_import": "imported",
        "source_manuel": "added",
        "source_selection": "remembered",
        "source_correction": "learned",
        "indice_mots": "Mars Men, Canva, …",
        "ajouter": "Add",
        "retirer": "Remove selected",
        "copier": "Copy",
        "aide_corrections": "A name misheard? Write what the engine hears, then the right word.",
        "indice_entendu": "heard: Mark Smead",
        "indice_ecrit": "written: Mars Men",
        "tel_titre": "Dictate from your phone",
        "tel_scanne": "Scan with your camera, on the same Wi-Fi as this PC.",
        "tel_mode": "Tap the keyboard's microphone, speak, then \"Send to PC\":\nthe text is pasted where your cursor is.",
        "tel_couper": "Turn off phone dictation",
        "tel_perime": "Link expired: scan the QR code on the PC again.",
    },
}

_choix: str | None = None


def langue_systeme() -> str:
    """« fr » si Windows est en français, « en » sinon."""
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except Exception:
        return "fr"
    return "fr" if (lid & 0x3FF) == 0x0C else "en"  # LANG_FRENCH


def choisir(reglage: str) -> None:
    global _choix
    r = (reglage or "auto").lower()
    _choix = langue_systeme() if r == "auto" else ("fr" if r.startswith("fr") else "en")


def langue() -> str:
    return _choix or langue_systeme()


def t(cle: str, **valeurs) -> str:
    texte = TEXTES[langue()].get(cle) or TEXTES["fr"][cle]
    return texte.format(**valeurs) if valeurs else texte
