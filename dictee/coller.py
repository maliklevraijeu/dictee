"""Coller le texte dans l'application active, sans abîmer le presse-papiers.

1. on garde tout ce qu'il y avait dans le presse-papiers (texte, image, fichiers) ;
2. on y met la dictée, marquée pour ne pas encombrer l'historique Win+V ;
3. Ctrl+V ;
4. on remet le contenu d'origine.
"""
from __future__ import annotations

import ctypes
import os
import re
import threading
import time
from ctypes import wintypes

from .raccourci import envoyer_touches

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
# Formats qui ne sont pas de la mémoire simple (objets GDI) : on ne sait pas les recopier.
_HANDLES_GDI = {2, 3, 9, 14, 0x0082, 0x008E}

u32.OpenClipboard.argtypes = [wintypes.HWND]
u32.GetClipboardData.restype = wintypes.HANDLE
u32.GetClipboardData.argtypes = [wintypes.UINT]
u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
u32.SetClipboardData.restype = wintypes.HANDLE
u32.EnumClipboardFormats.argtypes = [wintypes.UINT]
u32.EnumClipboardFormats.restype = wintypes.UINT
u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
u32.RegisterClipboardFormatW.restype = wintypes.UINT
u32.GetForegroundWindow.restype = wintypes.HWND
k32.OpenProcess.restype = wintypes.HANDLE
k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
k32.GlobalAlloc.restype = wintypes.HGLOBAL
k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
k32.GlobalSize.argtypes = [wintypes.HGLOBAL]
k32.GlobalSize.restype = ctypes.c_size_t

_PAS_D_HISTORIQUE = u32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")
_PAS_DE_NUAGE = u32.RegisterClipboardFormatW("CanUploadToCloudClipboard")
# Un seul collage ou copie à la fois : deux fils qui sauvent et restaurent le presse-papiers en même
# temps feraient coller l'ancien contenu de l'utilisateur, puis le perdraient.
_UN_A_LA_FOIS = threading.Lock()
_ALT_MAJ_WIN = (0x10, 0x12, 0x5B, 0x5C)


def _relachees(touches=_ALT_MAJ_WIN, delai: float = 1.5) -> bool:
    """Attend que ces touches soient relâchées : sinon Ctrl+V deviendrait Ctrl+Alt+Maj+V ou Win+V."""
    fin = time.time() + delai
    while any(u32.GetAsyncKeyState(v) & 0x8000 for v in touches):
        if time.time() > fin:
            return False
        time.sleep(0.02)
    return True


def _ouvrir(essais: int = 20) -> bool:
    for _ in range(essais):
        if u32.OpenClipboard(None):
            return True
        time.sleep(0.02)  # une autre appli le tient : on réessaie
    return False


def _global(octets: bytes) -> int:
    h = k32.GlobalAlloc(GMEM_MOVEABLE, max(1, len(octets)))
    p = k32.GlobalLock(h)
    ctypes.memmove(p, octets, len(octets))
    k32.GlobalUnlock(h)
    return h


def _sauver() -> list[tuple[int, bytes]]:
    sauve = []
    if not _ouvrir():
        return sauve
    try:
        f = 0
        while True:
            f = u32.EnumClipboardFormats(f)
            if not f:
                break
            if f in _HANDLES_GDI:
                continue
            h = u32.GetClipboardData(f)
            if not h:
                continue
            taille = k32.GlobalSize(h)
            p = k32.GlobalLock(h)
            if p and taille:
                sauve.append((f, ctypes.string_at(p, taille)))
                k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()
    return sauve


def _mettre(formats: list[tuple[int, bytes]]) -> bool:
    if not _ouvrir():
        return False
    try:
        u32.EmptyClipboard()
        for f, octets in formats:
            u32.SetClipboardData(f, _global(octets))
        return True
    finally:
        u32.CloseClipboard()


def mettre_texte(texte: str, discret: bool = True) -> bool:
    formats = [(CF_UNICODETEXT, (texte + "\0").encode("utf-16-le"))]
    if discret:
        formats += [(_PAS_D_HISTORIQUE, b"\0\0\0\0"), (_PAS_DE_NUAGE, b"\0\0\0\0")]
    return _mettre(formats)


def titre_fenetre_active() -> str:
    h = u32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    u32.GetWindowTextW(h, buf, 256)
    return buf.value


_TERMINAUX = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty", "PuTTY", "VirtualConsoleClass"}


def _classe(h) -> str:
    buf = ctypes.create_unicode_buffer(128)
    u32.GetClassNameW(h, buf, 128)
    return buf.value


def _eleve(pid: int) -> bool | None:
    """Le processus tourne-t-il en administrateur ? None si on ne peut pas le savoir."""
    adv = ctypes.WinDLL("advapi32")
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        jeton = wintypes.HANDLE()
        if not adv.OpenProcessToken(h, 0x0008, ctypes.byref(jeton)):  # TOKEN_QUERY
            return True  # refusé : c'est presque toujours une appli lancée en administrateur
        try:
            val, taille = wintypes.DWORD(), wintypes.DWORD()
            if adv.GetTokenInformation(jeton, 20, ctypes.byref(val), 4, ctypes.byref(taille)):  # TokenElevation
                return bool(val.value)
            return None
        finally:
            k32.CloseHandle(jeton)
    finally:
        k32.CloseHandle(h)


def fenetre_admin(h) -> bool:
    """Une fenêtre administrateur n'accepte pas les touches d'une appli normale (protection de Windows) :
    on le détecte au lieu de rater le collage en silence."""
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    cible = _eleve(pid.value)
    nous = _eleve(k32.GetCurrentProcessId())
    return bool(cible) and not nous


def coller(texte: str) -> tuple[bool, str]:
    """Colle `texte` là où est le curseur. Renvoie (collé ?, raison si non)."""
    if not texte:
        return False, "vide"
    h = u32.GetForegroundWindow()
    if not h:
        return False, "aucune fenêtre"
    # Garde-fou des tests automatiques : on ne colle QUE dans la fenêtre de test, jamais dans une appli
    # réelle passée au premier plan entre-temps.
    cible = os.environ.get("DICTEE_CIBLE_TITRE")
    if cible and titre_fenetre_active() != cible:
        _journal(f"collage refusé : « {titre_fenetre_active()} » n'est pas la fenêtre de test")
        return False, "test"
    if fenetre_admin(h):
        return False, "admin"
    with _UN_A_LA_FOIS:
        if not _relachees():
            # Alt, Maj ou Win toujours tenues (par exemple la dictée suivante déjà commencée) : on ne
            # colle pas à l'aveugle, l'appli le mettra dans le presse-papiers.
            return False, "touches tenues"
        terminal = _classe(h) in _TERMINAUX
        if terminal:
            # Dans un terminal, un retour à la ligne exécute la ligne : on n'en colle jamais.
            texte = re.sub(r"\s*[\r\n]+\s*", " ", texte)
        ancien = _sauver()
        if not mettre_texte(texte):
            _journal("presse-papiers indisponible")
            return False, "presse-papiers"
        ctrl_tenu = bool(u32.GetAsyncKeyState(0x11) & 0x8000)
        if terminal and not ctrl_tenu:
            # Les terminaux collent tous avec Maj+Inser (Ctrl+V n'y marche pas toujours).
            n = envoyer_touches((0xA0, True), (0x2D, True), (0x2D, False), (0xA0, False))
        elif ctrl_tenu:
            # l'utilisateur tient encore Ctrl : on ne le relâche pas à sa place
            n = envoyer_touches((0x56, True), (0x56, False))
        else:
            n = envoyer_touches((0xA2, True), (0x56, True), (0x56, False), (0xA2, False))
        _journal(f"collage vers « {titre_fenetre_active()} » : {n} touches acceptées")
        # L'appli lit le presse-papiers après coup : on lui laisse le temps avant de remettre l'ancien.
        time.sleep(0.35)
        if ancien:
            _mettre(ancien)
    return n > 0, "" if n > 0 else "touches refusées"


def copier_selection() -> str:
    """Le texte sélectionné dans l'appli active (Ctrl+C), presse-papiers rendu tel quel ensuite."""
    with _UN_A_LA_FOIS:
        return _copier_selection()


def vraie_selection(copie: str) -> str:
    """Ce que Ctrl+C a copié, seulement si c'est une vraie sélection. Sans sélection, VS Code (comme
    Sublime) copie la ligne entière AVEC son retour à la ligne : ce n'est pas un mot choisi."""
    if not copie or copie.endswith(("\n", "\r")) and copie.count("\n") <= 1:
        return ""
    return copie.strip()


def _copier_selection() -> str:
    # Alt et Maj du raccourci encore tenues : Ctrl+C deviendrait Ctrl+Alt+Maj+C
    _relachees()
    if _classe(u32.GetForegroundWindow()) in _TERMINAUX:
        return ""  # Ctrl+C dans un terminal arrête le programme en cours : jamais
    ancien = _sauver()
    _mettre([])
    envoyer_touches((0xA2, True), (0x43, True), (0x43, False), (0xA2, False))
    texte = ""
    for _ in range(15):
        time.sleep(0.04)
        if _ouvrir():
            try:
                h = u32.GetClipboardData(CF_UNICODETEXT)
                if h:
                    p = k32.GlobalLock(h)
                    texte = ctypes.wstring_at(p)
                    k32.GlobalUnlock(h)
            finally:
                u32.CloseClipboard()
        if texte:
            break
    _mettre(ancien) if ancien else _mettre([])
    return vraie_selection(texte)


def _journal(ligne: str) -> None:
    import os

    if os.environ.get("DICTEE_DEBUG"):
        from .config import DOSSIER

        with (DOSSIER / "debug.log").open("a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + ligne + "\n")
