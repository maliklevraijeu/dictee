"""Dicter depuis le téléphone : une page web servie par Dictée sur le réseau local.

On scanne un QR code, on dicte avec le micro du clavier du téléphone (la dictée de l'iPhone ou de
Gboard, gratuite et sans clé), et le texte se colle sur le PC là où est le curseur. Pourquoi le
clavier et pas l'audio du téléphone : Safari refuse le micro à une page qui n'est pas en https, et
une page en https ne peut pas joindre le PC sur le Wi-Fi sans serveur relais sur internet.

Garde-fous : un jeton secret dans l'adresse (comparé en temps constant), seulement des appareils du
réseau local, 10 000 caractères au plus par envoi, quelques envois par seconde au plus.
"""
from __future__ import annotations

import ctypes
import hashlib
import hmac
import io
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

from .config import DOSSIER

FICHIER = DOSSIER / "telephone.json"
PORT = 47110
MAX_CARACTERES = 10_000
REGLE_PARE_FEU = "Dictee - dicter depuis le telephone"
_SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _jeton_et_port() -> tuple[str, int]:
    """Gardés d'une fois sur l'autre : la page ajoutée à l'écran d'accueil du téléphone reste valable."""
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
        if isinstance(d.get("jeton"), str) and len(d["jeton"]) >= 16:
            return d["jeton"], int(d.get("port", PORT))
    except (OSError, ValueError, TypeError):
        pass
    return secrets.token_urlsafe(16), PORT


def _garder(jeton: str, port: int) -> None:
    DOSSIER.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps({"jeton": jeton, "port": port}), encoding="utf-8")


def ip_locale() -> str:
    """L'adresse du PC sur le Wi-Fi de la maison. Les box donnent presque toujours du 192.168.x, alors
    qu'un VPN, WSL ou Hyper-V ajoutent des adresses en 10.x ou 172.x : le 192.168.x passe devant."""
    route = ""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # aucun paquet n'est envoyé : on lit l'interface qui sort vers internet
        route = s.getsockname()[0]
    except OSError:
        pass
    finally:
        s.close()
    try:
        toutes = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        toutes = []
    ordre = ([route] if route.startswith("192.168.") else []) + [ip for ip in toutes if ip.startswith("192.168.")]
    ordre += [route] + toutes
    for ip in ordre:
        if ip and adresse_locale(ip) and not ip.startswith("127.") and not ip.startswith("169.254."):
            return ip
    return "127.0.0.1"


def adresse_locale(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return a.is_private or a.is_loopback or a.is_link_local


def qr_png(texte: str, echelle: int = 7) -> bytes:
    import segno

    tampon = io.BytesIO()
    segno.make(texte, error="m").save(tampon, kind="png", scale=echelle, border=3, dark="#151208", light="#F5F1E8")
    return tampon.getvalue()


# --- pare-feu --------------------------------------------------------------------------------
# Windows règle souvent le Wi-Fi de la box en « réseau public » : le pare-feu y bloque alors le
# téléphone. Une seule règle, posée avec l'accord de l'utilisateur (fenêtre de Windows), ouvre le
# port de Dictée aux seuls appareils du réseau local.

def _exe_reel() -> str:
    """Le programme qui écoute vraiment : derrière un venv, c'est le pythonw.exe (ou python.exe) de base."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                               ctypes.POINTER(wintypes.DWORD)]
    k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    buf = ctypes.create_unicode_buffer(1024)
    n = wintypes.DWORD(1024)
    if k32.QueryFullProcessImageNameW(k32.GetCurrentProcess(), 0, buf, ctypes.byref(n)):
        return buf.value
    return sys.executable


def _netsh() -> str:
    # chemin complet : jamais un netsh.exe trouvé dans le dossier courant, surtout pour une commande élevée
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "netsh.exe")


def nom_regle() -> str:
    """Une règle par programme : lancée par python.exe ou par pythonw.exe, Dictée n'est pas le même
    programme pour le pare-feu, et une règle au bon nom doit aussi viser le bon programme."""
    return f"{REGLE_PARE_FEU} ({hashlib.sha1(_exe_reel().lower().encode()).hexdigest()[:8]})"


def regle_presente() -> bool:
    try:
        r = subprocess.run([_netsh(), "advfirewall", "firewall", "show", "rule", f"name={nom_regle()}"],
                           capture_output=True, creationflags=_SANS_FENETRE, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def demander_pare_feu() -> bool:
    """Ouvre la demande de Windows (« Oui » / « Non »). Bloquant jusqu'à la réponse : à lancer hors du fil
    de l'interface. Renvoie False si la fenêtre n'a pas pu s'ouvrir ou a été refusée."""
    args = (f'advfirewall firewall add rule name="{nom_regle()}" dir=in action=allow '
            f'program="{_exe_reel()}" protocol=TCP localport={PORT}-{PORT + 9} remoteip=localsubnet profile=any')
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", _netsh(), args, None, 0) > 32


def oublier_jeton() -> None:
    """« Couper » : le prochain QR code aura un nouveau code secret, l'ancien ne vaut plus rien."""
    try:
        FICHIER.unlink()
    except OSError:
        pass


# --- le serveur --------------------------------------------------------------------------------
class _ServeurLimite(ThreadingHTTPServer):
    """Au plus 16 connexions à la fois : un appareil du Wi-Fi qui en ouvre des milliers n'épuise rien."""

    daemon_threads = True

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._places = threading.BoundedSemaphore(16)

    def process_request(self, request, client_address):
        if not self._places.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._places.release()


class Serveur:
    """`recevoir(texte) -> dict` est appelé dans le fil du serveur et rend la réponse pour le téléphone."""

    def __init__(self, recevoir: Callable[[str], dict], hote: str = "0.0.0.0", port: int | None = None,
                 jeton: str | None = None):
        j, p = _jeton_et_port()
        self.jeton = jeton or j
        self.port = p if port is None else port
        self.hote = hote
        self.recevoir = recevoir
        self._httpd: ThreadingHTTPServer | None = None
        self._envois: list[float] = []
        self._verrou = threading.Lock()

    @property
    def actif(self) -> bool:
        return self._httpd is not None

    def adresse(self) -> str:
        return f"http://{ip_locale()}:{self.port}/?t={self.jeton}"

    def _cadence(self) -> bool:
        with self._verrou:
            maintenant = time.time()
            self._envois = [t for t in self._envois if maintenant - t < 2]
            if len(self._envois) >= 5:
                return False
            self._envois.append(maintenant)
            return True

    def lancer(self) -> None:
        if self._httpd is not None:
            return
        serveur = self

        class Gestionnaire(BaseHTTPRequestHandler):
            server_version = "Dictee"
            sys_version = ""
            timeout = 10  # une connexion muette (ou un téléphone qui perd le Wi-Fi) ne garde pas un fil

            def log_message(self, *_):
                pass

            def _repondre(self, code: int, corps: bytes, genre: str = "application/json; charset=utf-8"):
                self.send_response(code)
                self.send_header("Content-Type", genre)
                self.send_header("Content-Length", str(len(corps)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(corps)

            def _json(self, code: int, d: dict):
                self._repondre(code, json.dumps(d).encode())

            def _autorise(self) -> bool:
                if not adresse_locale(self.client_address[0]):
                    return False
                t = parse_qs(urlparse(self.path).query).get("t", [""])[0]
                return hmac.compare_digest(t.encode(), serveur.jeton.encode())

            def do_GET(self):
                if urlparse(self.path).path != "/" or not self._autorise():
                    return self._repondre(403, "Lien périmé : rescanne le QR code sur le PC. / Link expired: scan the QR code again.".encode(),
                                          "text/plain; charset=utf-8")
                self._repondre(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")

            def do_POST(self):
                # Le corps est toujours lu (borné) AVANT de répondre, même pour refuser : un serveur qui
                # répond et ferme pendant que le téléphone envoie encore lui coupe la connexion.
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = 0
                trop_gros = n <= 0 or n > MAX_CARACTERES * 4 + 200
                corps, reste = b"", min(max(n, 0), 256 * 1024)
                while reste > 0:
                    bloc = self.rfile.read(min(reste, 65536))
                    if not bloc:
                        break
                    corps += bloc
                    reste -= len(bloc)
                if urlparse(self.path).path != "/envoyer" or not self._autorise():
                    return self._json(403, {"ok": False, "raison": "jeton"})
                if trop_gros:
                    self.close_connection = True
                    return self._json(413, {"ok": False, "raison": "taille"})
                if not serveur._cadence():
                    return self._json(429, {"ok": False, "raison": "cadence"})
                try:
                    texte = json.loads(corps.decode("utf-8")).get("texte", "")
                except (ValueError, UnicodeDecodeError, AttributeError):
                    return self._json(400, {"ok": False, "raison": "format"})
                if not isinstance(texte, str) or not texte.strip():
                    return self._json(400, {"ok": False, "raison": "vide"})
                if len(texte.strip()) > MAX_CARACTERES:  # jamais tronqué en silence
                    return self._json(413, {"ok": False, "raison": "taille"})
                try:
                    reponse = serveur.recevoir(texte.strip())
                except Exception:
                    reponse = {"ok": False, "raison": "erreur"}
                self._json(200, reponse)

        # Port occupé par une autre appli : on prend un des 9 suivants (la règle du pare-feu les couvre).
        for essai in ([self.port] if self.port == 0 else range(PORT, PORT + 10)):
            try:
                self._httpd = _ServeurLimite((self.hote, essai), Gestionnaire)
                break
            except OSError:
                continue
        if self._httpd is None:
            raise OSError(f"aucun port libre de {PORT} à {PORT + 9}")
        self.port = self._httpd.server_address[1]
        if self.hote != "127.0.0.1":
            try:
                _garder(self.jeton, self.port)
            except OSError:
                pass
        threading.Thread(target=self._httpd.serve_forever, name="telephone", daemon=True).start()

    def arreter(self) -> None:
        h, self._httpd = self._httpd, None
        if h is not None:
            h.shutdown()
            h.server_close()


PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Dictée">
<meta name="theme-color" content="#0D0D0D">
<title>Dictée</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; overflow: hidden; background: #0D0D0D; color: #F5F1E8;
    font: 17px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  main { display: flex; flex-direction: column; gap: 14px; height: 100%;
    padding: max(18px, env(safe-area-inset-top)) 16px max(16px, env(safe-area-inset-bottom)); }
  h1 { margin: 0; font-size: 22px; font-weight: 600; }
  textarea { flex: 1; min-height: 160px; width: 100%; resize: none; padding: 14px; border-radius: 14px;
    border: 1px solid #3A3830; background: #161615; color: #F5F1E8; font: inherit; font-size: 19px; }
  textarea:focus { outline: none; border-color: #C9A227; }
  button { width: 100%; padding: 16px; border: 0; border-radius: 14px; background: #C9A227; color: #151208;
    font: inherit; font-weight: 600; font-size: 18px; }
  button:disabled { opacity: .55; }
  #etat { min-height: 1.45em; margin: 0; color: #9A958A; text-align: center; }
  #etat.erreur { color: #E8836E; }
</style>
</head>
<body>
<main>
  <h1>Dictée</h1>
  <textarea id="texte" placeholder="Touche le micro du clavier et parle." maxlength="10000" autofocus></textarea>
  <button id="envoyer" type="button">Envoyer au PC</button>
  <p id="etat" aria-live="polite"></p>
</main>
<script>
  // Français si le téléphone est en français, anglais sinon.
  const FR = (navigator.language || "fr").toLowerCase().startsWith("fr");
  const T = FR ? {
    parle: "Touche le micro du clavier et parle.", envoyer: "Envoyer au PC", envoi: "Envoi…",
    perime: "Lien périmé : rescanne le QR code sur le PC.", long: "Texte trop long : envoie-le en plusieurs fois.",
    vite: "Doucement : réessaie dans une seconde.", colle: "Collé sur le PC.", copie: "Copié sur le PC : fais Ctrl+V.",
    pause: "Dictée est en pause sur le PC.", vide: "Rien à envoyer.", rate: "Pas collé. Réessaie.",
    injoignable: "Le PC ne répond pas. Tu es sur le même Wi-Fi ?"
  } : {
    parle: "Tap the keyboard's microphone and speak.", envoyer: "Send to PC", envoi: "Sending…",
    perime: "Link expired: scan the QR code on the PC again.", long: "Text too long: send it in several parts.",
    vite: "Slow down: try again in a second.", colle: "Pasted on the PC.", copie: "Copied on the PC: press Ctrl+V.",
    pause: "Dictée is paused on the PC.", vide: "Nothing to send.", rate: "Not pasted. Try again.",
    injoignable: "The PC isn't answering. Are you on the same Wi-Fi?"
  };
  document.documentElement.lang = FR ? "fr" : "en";
  const zone = document.getElementById("texte");
  const bouton = document.getElementById("envoyer");
  const etat = document.getElementById("etat");
  zone.placeholder = T.parle;
  bouton.textContent = T.envoyer;
  function dire(t, erreur) { etat.textContent = t; etat.className = erreur ? "erreur" : ""; }
  // Sur iPhone, le clavier recouvre la page sans la rétrécir : on cale la page sur la partie visible,
  // pour que « Envoyer au PC » reste juste au-dessus du clavier.
  const page = document.querySelector("main");
  function ajuster() {
    const v = window.visualViewport;
    if (!v) return;
    page.style.height = v.height + "px";
    window.scrollTo(0, 0);
  }
  if (window.visualViewport) {
    visualViewport.addEventListener("resize", ajuster);
    visualViewport.addEventListener("scroll", ajuster);
  }
  ajuster();
  // Le clavier reste ouvert : le bouton ne prend pas le focus à la zone de texte.
  bouton.addEventListener("pointerdown", e => e.preventDefault());
  bouton.addEventListener("click", async () => {
    // Quitter puis reprendre la zone valide le mot que le clavier est encore en train de composer
    // (sinon Gboard le réinsère après l'envoi) ; le tout dans le même geste, le clavier reste ouvert.
    zone.blur();
    const texte = zone.value.trim();
    zone.focus();
    if (!texte) { dire(T.parle); return; }
    bouton.disabled = true;
    dire(T.envoi);
    try {
      const r = await fetch("/envoyer" + location.search, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texte })
      });
      const d = await r.json().catch(() => ({}));
      if (r.status === 403) dire(T.perime, true);
      else if (r.status === 413) dire(T.long, true);
      else if (r.status === 429) dire(T.vite, true);
      else if (d.ok && d.colle) { zone.value = ""; dire(T.colle); }
      else if (d.ok) { zone.value = ""; dire(T.copie); }
      else if (d.raison === "pause") dire(T.pause, true);
      else if (d.raison === "vide") dire(T.vide, true);
      else dire(T.rate, true);
    } catch (e) {
      dire(T.injoignable, true);
    }
    bouton.disabled = false;
  });
</script>
</body>
</html>
"""
