"""Le raccourci clavier global, par un crochet clavier bas niveau de Windows (aucune dépendance).

- Maintenir Ctrl+Win : on parle ; relâcher : la dictée part et se colle.
- Ctrl+Win puis Espace (ou Ctrl+Win+Espace) : mains libres ; Ctrl+Win à nouveau pour finir.
- Échap pendant une dictée : annuler.
- Alt+Maj+Z : recoller la dernière dictée.
- Alt+Maj+M : retenir le mot sélectionné (il entre dans ton vocabulaire).

Deux pièges Windows gérés ici :
1. Relâcher Win ouvre le menu Démarrer : on envoie une touche neutre (0xE8) juste avant.
2. Windows retire en silence un crochet trop lent : le rappel ne fait que poser un événement dans
   une file, et le crochet est réinstallé toutes les 5 minutes.
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_TIMER, WM_QUIT = 0x113, 0x12
LLKHF_INJECTED = 0x10
LRESULT = ctypes.c_ssize_t

VK = {
    "ctrl": {0x11, 0xA2, 0xA3},
    "win": {0x5B, 0x5C},
    "alt": {0x12, 0xA4, 0xA5},
    "shift": {0x10, 0xA0, 0xA1},
    "space": {0x20},
    "esc": {0x1B},
    "enter": {0x0D},
}
for c in "abcdefghijklmnopqrstuvwxyz0123456789":
    VK[c] = {ord(c.upper())}
for i in range(1, 13):
    VK[f"f{i}"] = {0x6F + i}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("_pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
u32.SetWindowsHookExW.restype = wintypes.HHOOK
u32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
u32.CallNextHookEx.restype = LRESULT
u32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
u32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
u32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
u32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
u32.SetTimer.restype = ctypes.c_size_t
u32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
k32.GetModuleHandleW.restype = wintypes.HMODULE


def touches(combo: str) -> list[set[int]]:
    """« ctrl+win+space » -> [{ctrl...}, {win...}, {space}]"""
    out = []
    for nom in combo.lower().replace(" ", "").split("+"):
        if nom not in VK:
            raise ValueError(f"touche inconnue : {nom}")
        out.append(VK[nom])
    return out


def envoyer_touches(*evenements: tuple[int, bool]) -> int:
    """Envoie (vk, appui?) au système, marqués comme injectés. Renvoie le nombre d'événements acceptés."""
    tab = (INPUT * len(evenements))()
    for i, (vk, bas) in enumerate(evenements):
        tab[i].type = 1
        tab[i].u.ki = KEYBDINPUT(vk, 0, 0 if bas else 2, 0, 0)
    return u32.SendInput(len(evenements), tab, ctypes.sizeof(INPUT))


class Raccourcis:
    """Lance le crochet dans son propre fil. `rappel(evenement)` reçoit :
    "debut", "fin", "mains_libres", "annuler", "recoller", "memoriser"."""

    def __init__(self, principal: str, mains_libres: str, recoller: str, rappel: Callable[[str], None],
                 memoriser: str = "alt+shift+m"):
        self.principal = touches(principal)
        self.libres = touches(mains_libres)
        self.recoller = touches(recoller)
        self.memoriser = touches(memoriser) if memoriser else []
        self.rappel = rappel
        self.enfoncees: set[int] = set()
        self.actif = False  # une dictée tient le micro
        self.verrou = False  # mains libres
        self._win_dans_combo = False
        self._crochet = None
        self._proc = HOOKPROC(self._sur_touche)
        self._id_fil = 0
        self._fil = threading.Thread(target=self._boucle, name="raccourcis", daemon=True)

    def lancer(self) -> None:
        self._fil.start()

    def arreter(self) -> None:
        if self._id_fil:
            u32.PostThreadMessageW(self._id_fil, WM_QUIT, 0, 0)

    # La dictée s'est arrêtée d'elle-même (durée max, erreur) : on remet l'état à zéro.
    def reinitialiser(self) -> None:
        self.actif = False
        self.verrou = False

    def _tenu(self, combo: list[set[int]]) -> bool:
        return all(self.enfoncees & groupe for groupe in combo)

    def _emettre(self, e: str) -> None:
        try:
            self.rappel(e)
        except Exception:
            pass

    def _sur_touche(self, code, wparam, lparam):
        if code == 0:
            k = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if not (k.flags & LLKHF_INJECTED):
                vk = k.vkCode
                bas = wparam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                if self._traiter(vk, bas):
                    return 1  # touche avalée (Espace des mains libres, Z du recollage, Échap d'annulation)
        return u32.CallNextHookEx(self._crochet, code, wparam, lparam)

    @staticmethod
    def _vraiment_enfoncee(vk: int) -> bool:
        return bool(u32.GetAsyncKeyState(vk) & 0x8000)

    def _oublier_les_relachees(self, sauf: int) -> None:
        # Un relâchement fait sur l'écran de verrouillage (Win+L, Ctrl+Alt+Suppr, UAC) n'arrive jamais au
        # crochet : sans ce contrôle, Win resterait « tenue » et Ctrl seul lancerait une dictée.
        for v in [v for v in self.enfoncees if v != sauf and not self._vraiment_enfoncee(v)]:
            self.enfoncees.discard(v)

    def _traiter(self, vk: int, bas: bool) -> bool:
        if bas and vk not in self.enfoncees:
            self._oublier_les_relachees(vk)
        etait = self._tenu(self.principal)
        if bas:
            deja = vk in self.enfoncees
            self.enfoncees.add(vk)
            if deja:
                # répétition automatique : on avale celle des touches qu'on consomme
                return self.actif and vk in VK["space"] and self.verrou
            tenu = self._tenu(self.principal)
            if self.actif and vk in VK["esc"]:
                self.actif = self.verrou = False
                self._emettre("annuler")
                return True
            if self._tenu(self.recoller) and not self.actif:
                self._emettre("recoller")
                envoyer_touches((0xE8, True), (0xE8, False))  # Alt+Maj relâchées seules changeraient la langue du clavier
                return True
            if self.memoriser and self._tenu(self.memoriser) and not self.actif:
                self._emettre("memoriser")
                envoyer_touches((0xE8, True), (0xE8, False))
                return True
            if self.actif and not self.verrou and self._tenu(self.libres):
                self.verrou = True
                self._emettre("mains_libres")
                return True
            if tenu and not etait:
                if vk in VK["win"] or any(w in self.enfoncees for w in VK["win"]):
                    self._win_dans_combo = True
                if self.actif and self.verrou:
                    # mains libres : Ctrl+Win une deuxième fois = fin
                    self.actif = self.verrou = False
                    self._emettre("fin")
                elif not self.actif:
                    self.actif = True
                    self._emettre("debut")
                    if self._tenu(self.libres):
                        self.verrou = True
                        self._emettre("mains_libres")
                        return vk in VK["space"]
            return False
        # relâchement
        self.enfoncees.discard(vk)
        if vk in VK["win"] and self._win_dans_combo:
            self._win_dans_combo = False
            envoyer_touches((0xE8, True), (0xE8, False))  # empêche le menu Démarrer de s'ouvrir
        if self.actif and not self.verrou and etait and not self._tenu(self.principal):
            self.actif = False
            self._emettre("fin")
        return False

    def _installer(self) -> None:
        if self._crochet:
            u32.UnhookWindowsHookEx(self._crochet)
        self._crochet = u32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, k32.GetModuleHandleW(None), 0)

    def _boucle(self) -> None:
        self._id_fil = k32.GetCurrentThreadId()
        self._installer()
        u32.SetTimer(None, 0, 5 * 60 * 1000, None)
        msg = wintypes.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_TIMER:
                # réinstallation périodique : Windows retire un crochet jugé trop lent sans prévenir
                self._oublier_les_relachees(sauf=-1)
                if not self.enfoncees:
                    self._installer()
                continue
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        if self._crochet:
            u32.UnhookWindowsHookEx(self._crochet)
