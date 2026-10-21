"""Chaque dictée est gardée : le texte (toujours) et l'audio (N jours, pour retranscrire).
Une dictée ne se perd jamais, même si le collage ou le réseau ont raté."""
from __future__ import annotations

import ctypes
import json
import os
import time
import wave
from ctypes import wintypes
from pathlib import Path

from .config import DOSSIER

FICHIER = DOSSIER / "historique.jsonl"
AUDIO = DOSSIER / "audio"

u32 = ctypes.WinDLL("user32")
k32 = ctypes.WinDLL("kernel32")
u32.GetForegroundWindow.restype = wintypes.HWND
k32.OpenProcess.restype = wintypes.HANDLE
k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]


def appli_active() -> str:
    try:
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), ctypes.byref(pid))
        h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(520)
            n = wintypes.DWORD(520)
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                return Path(buf.value).stem
        finally:
            k32.CloseHandle(h)
    except Exception:
        pass
    return ""


def garder_audio(pcm: bytes, quand: float) -> str:
    AUDIO.mkdir(parents=True, exist_ok=True)
    f = AUDIO / time.strftime("%Y%m%d-%H%M%S.wav", time.localtime(quand))
    with wave.open(str(f), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    return f.name


def ajouter(entree: dict) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    with FICHIER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entree, ensure_ascii=False) + "\n")


def garder_dernieres(n: int = 5000) -> None:
    """L'historique ne grossit pas sans fin : on garde les n dernières dictées."""
    try:
        lignes = FICHIER.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lignes) > n:
        tmp = FICHIER.with_suffix(".tmp")
        tmp.write_text("\n".join(lignes[-n:]) + "\n", encoding="utf-8")
        os.replace(tmp, FICHIER)


def derniere() -> dict | None:
    if not FICHIER.exists():
        return None
    derniere_ligne = None
    with FICHIER.open(encoding="utf-8") as f:
        for ligne in f:
            if ligne.strip():
                derniere_ligne = ligne
    try:
        return json.loads(derniere_ligne) if derniere_ligne else None
    except ValueError:
        return None


def purger_audio(jours: int) -> None:
    if not AUDIO.exists():
        return
    limite = time.time() - jours * 86400
    for f in AUDIO.glob("*.wav"):
        try:
            if jours <= 0 or f.stat().st_mtime < limite:
                f.unlink()
        except OSError:
            pass
