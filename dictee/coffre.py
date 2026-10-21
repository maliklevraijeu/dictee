"""Les clés d'API, chiffrées par Windows (DPAPI) pour ton compte seulement, dans %APPDATA%\\Dictee\\cles.bin.
Personne d'autre (ni un autre compte Windows, ni un autre PC) ne peut les relire."""
from __future__ import annotations

import ctypes
import json
from ctypes import wintypes

from .config import DOSSIER

FICHIER = DOSSIER / "cles.bin"


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_c32 = ctypes.WinDLL("crypt32")
_k32 = ctypes.WinDLL("kernel32")


def _entree(octets: bytes) -> _BLOB:
    tampon = ctypes.create_string_buffer(octets, len(octets))
    return _BLOB(len(octets), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char)))


def _sortie(b: _BLOB) -> bytes:
    data = ctypes.string_at(b.pbData, b.cbData)
    _k32.LocalFree(b.pbData)
    return data


def chiffrer(octets: bytes) -> bytes:
    e, s = _entree(octets), _BLOB()
    if not _c32.CryptProtectData(ctypes.byref(e), "Dictee", None, None, None, 0, ctypes.byref(s)):
        raise OSError("chiffrement impossible")
    return _sortie(s)


def dechiffrer(octets: bytes) -> bytes:
    e, s = _entree(octets), _BLOB()
    if not _c32.CryptUnprotectData(ctypes.byref(e), None, None, None, None, 0, ctypes.byref(s)):
        raise OSError("déchiffrement impossible")
    return _sortie(s)


def lire() -> dict[str, str]:
    try:
        return json.loads(dechiffrer(FICHIER.read_bytes()).decode("utf-8"))
    except (OSError, ValueError):
        return {}


def ecrire(cles: dict[str, str]) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    FICHIER.write_bytes(chiffrer(json.dumps(cles).encode("utf-8")))
