"""Lancer Dictée à l'ouverture de Windows : un raccourci dans le dossier Démarrage de l'utilisateur."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RACCOURCI = Path(os.environ.get("APPDATA", Path.home())) / "Microsoft/Windows/Start Menu/Programs/Startup/Dictée.lnk"


def actif() -> bool:
    return RACCOURCI.exists()


def activer() -> None:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    dossier = Path(__file__).resolve().parent.parent

    def ps(chemin) -> str:  # chaîne PowerShell entre apostrophes (un nom comme N'Diaye en contient une)
        return "'" + str(chemin).replace("'", "''") + "'"

    commande = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({ps(RACCOURCI)});"
                f"$s.TargetPath={ps(pythonw)};$s.Arguments='-m dictee';$s.WorkingDirectory={ps(dossier)};"
                f"$s.Description='Dictée vocale';$s.Save()")
    RACCOURCI.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["powershell", "-NoProfile", "-Command", commande], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def desactiver() -> None:
    RACCOURCI.unlink(missing_ok=True)
