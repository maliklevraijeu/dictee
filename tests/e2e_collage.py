"""Test de bout en bout, sans micro ni clavier :
une fenêtre cible (autre processus) a le focus, un vrai fichier de dictée joue le rôle du micro,
Dictée transcrit en direct et colle. On vérifie le texte collé ET que le presse-papiers est rendu.

  python tests/e2e_collage.py <dictee.wav>
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ICI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ICI))
from dictee.coller import CF_UNICODETEXT, _ouvrir, mettre_texte  # noqa: E402

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32

CIBLE = r'''
import tkinter as tk, sys
r = tk.Tk(); r.title("Cible Dictée"); r.geometry("700x300+200+200")
t = tk.Text(r); t.pack(fill="both", expand=True)
def garder():
    open(sys.argv[1], "w", encoding="utf-8").write(t.get("1.0", "end-1c")); r.after(300, garder)
touches = open(sys.argv[1] + ".touches", "w", encoding="utf-8")
r.bind_all("<Key>", lambda e: (touches.write(f"{e.keysym} state={e.state} focus={r.focus_get()}\n"), touches.flush()))
r.bind("<FocusIn>", lambda e: (touches.write(f"FocusIn {e.widget}\n"), touches.flush()))
r.bind("<FocusOut>", lambda e: (touches.write(f"FocusOut {e.widget}\n"), touches.flush()))
r.attributes("-topmost", True); r.after(100, lambda: (r.focus_force(), t.focus_set())); r.after(300, garder)
r.mainloop()
'''


def lire_presse_papiers() -> str:
    u32.GetClipboardData.restype = ctypes.c_void_p
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    if not _ouvrir():
        return "?"
    try:
        h = u32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = k32.GlobalLock(h)
        s = ctypes.wstring_at(p)
        k32.GlobalUnlock(h)
        return s
    finally:
        u32.CloseClipboard()


def main():
    wav = sys.argv[1]
    with wave.open(wav) as w:
        duree = w.getnframes() / w.getframerate()
    sortie = Path(tempfile.gettempdir()) / "dictee_cible.txt"
    sortie.unlink(missing_ok=True)
    script = Path(tempfile.gettempdir()) / "dictee_cible.py"
    script.write_text(CIBLE, encoding="utf-8")
    py = sys.executable
    cible = subprocess.Popen([py, str(script), str(sortie)])
    time.sleep(1.5)
    hwnd = u32.FindWindowW(None, "Cible Dictée")
    # Windows ne donne le focus qu'à certaines conditions : une touche neutre (0xE8) débloque
    # SetForegroundWindow. Surtout pas Alt : Alt seul ouvre le menu de la fenêtre et avale la touche suivante.
    u32.keybd_event(0xE8, 0, 0, 0)
    u32.SetForegroundWindow(hwnd)
    u32.keybd_event(0xE8, 0, 2, 0)
    time.sleep(0.5)
    print("fenêtre cible au premier plan :", u32.GetForegroundWindow() == hwnd)
    mettre_texte("ANCIEN CONTENU DU PRESSE-PAPIERS", discret=False)

    # DICTEE_CIBLE_TITRE : Dictée refuse de coller ailleurs que dans la fenêtre de test.
    env = dict(os.environ, DICTEE_FICHIER_MICRO=wav, DICTEE_AUTOTEST=str(duree + 0.3), DICTEE_CIBLE_TITRE="Cible Dictée")
    t0 = time.time()
    app = subprocess.run([py, "-m", "dictee"], cwd=str(ICI), env=env, timeout=duree + 40, capture_output=True, text=True)
    if app.returncode:
        print("Dictée a planté :", app.stderr[-800:])
    time.sleep(1)
    colle = sortie.read_text(encoding="utf-8") if sortie.exists() else ""
    cible.terminate()
    print(f"durée de la dictée {duree:.1f} s, test complet en {time.time() - t0:.1f} s")
    print("TEXTE COLLÉ :", colle[:400] if colle else "(rien)")
    pp = lire_presse_papiers()
    print("presse-papiers rendu :", pp == "ANCIEN CONTENU DU PRESSE-PAPIERS", repr(pp[:60]))
    ok = bool(colle.strip()) and pp == "ANCIEN CONTENU DU PRESSE-PAPIERS"
    print("RÉSULTAT :", "OK" if ok else "ÉCHEC")
    sys.exit(0 if ok else 1)


main()
