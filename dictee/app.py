"""L'application : raccourci -> micro -> moteur en direct -> nettoyage -> collage -> mémoire.

Fils : le principal fait tourner la pastille (tkinter) et reçoit tout par une file ; le crochet
clavier, le micro, le moteur, l'apprentissage et l'icône ont chacun le leur. Rien de bloquant
dans le principal.
"""
from __future__ import annotations

import ctypes
import os
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path

from . import demarrage, historique, sons
from .apprentissage import Veilleur
from .audio import Micro, lister_micros
from .coller import coller, copier_selection, mettre_texte, titre_fenetre_active
from .config import DOSSIER, FICHIER, Config
from .memoire import Memoire
from .moteur import Moteur, Resultat
from .nettoyage import nettoyer
from .pilule import Pilule
from .raccourci import Raccourcis

DUREE_MIN = 0.3  # un appui plus court est un faux départ : on l'ignore

# Phrases que les moteurs inventent parfois sur un silence. Écartées seulement quand c'est TOUT le
# texte ET que le micro n'a presque rien capté : une vraie dictée « Merci de votre attention. » passe.
_INVENTIONS = re.compile(r"^\W*(sous-titrage [\w\s.'’-]{0,30}|sous-titres réalisés par [\w\s.'’-]{0,30}|"
                         r"merci d'avoir regardé( cette vidéo)?|thank you for watching|"
                         r"merci de votre attention|merci)[\s.!…]*$", re.I)
_PONCTUATION_SEULE = re.compile(r"^[\s.,!?…;:-]*$")
CRETE_CALME = 1500  # sur 32 767 : une voix normale dépasse largement


def _journal_erreur(quoi: str) -> None:
    """Sous pythonw il n'y a pas de console : les erreurs vont dans erreurs.log (gardé court)."""
    import traceback

    try:
        f = DOSSIER / "erreurs.log"
        anciennes = f.read_text(encoding="utf-8").splitlines()[-400:] if f.exists() else []
        lignes = anciennes + [time.strftime("%Y-%m-%d %H:%M:%S ") + quoi] + traceback.format_exc().splitlines()
        f.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    except OSError:
        pass


def _dpi() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _instance_unique() -> bool:
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW(None, False, "Local\\Dictee-instance-unique")
    return k32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


class App:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        _dpi()
        self.racine = tk.Tk()
        self.racine.withdraw()
        cle, cle_gemini = cfg.cle_api(), cfg.cle_gemini()
        if not cle and not cle_gemini:
            from .accueil import demander_cles

            if not demander_cles(self.racine):
                raise SystemExit(0)
            cle, cle_gemini = cfg.cle_api(), cfg.cle_gemini()
        self.memoire = Memoire()
        if not self.memoire.mots and (cfg.mots or cfg.remplacements):
            # reprise de l'ancienne configuration : le vocabulaire vit désormais dans la mémoire
            self.memoire.reprendre(cfg.mots, cfg.remplacements)
            self.memoire.enregistrer()
            cfg.mots, cfg.remplacements = [], {}
            cfg.enregistrer()
        self.moteur = Moteur(cle, cfg.langue, self.memoire.mots_prioritaires(100), cfg.reecriture, cfg.decoupe,
                             cfg.langues_secondaires)
        self.moteur.cle_gemini = cle_gemini
        self.micro = Micro(cfg.micro)
        self.file: queue.Queue = queue.Queue()
        self.alerte = ""
        try:
            self.racc = Raccourcis(cfg.raccourci, cfg.mains_libres, cfg.recoller, lambda e: self.file.put((e, None)),
                                   cfg.memoriser)
        except ValueError as e:  # raccourci mal écrit dans les réglages : on garde ceux par défaut
            d = Config()
            self.racc = Raccourcis(d.raccourci, d.mains_libres, d.recoller, lambda e: self.file.put((e, None)),
                                   d.memoriser)
            self.alerte = f"Raccourci invalide dans les réglages ({e}) : Ctrl+Win gardé"
        self.veilleur = Veilleur(lambda c, appli: self.file.put(("appris", c)))
        self.session = None
        self.debut = 0.0
        self.appli = ""
        self.pause = False
        self.dernier_muet = False
        self.dernier_remplacant = ""
        self.derniere = (historique.derniere() or {}).get("texte", "")
        self.pilule = Pilule(self.racine, lambda: self.micro.niveau)
        self.icone = None
        self.fenetre_memoire = None

    # --- boucle principale ----------------------------------------------
    def lancer(self) -> None:
        historique.purger_audio(self.cfg.garder_audio_jours)
        historique.garder_dernieres()
        # Test de bout en bout sans toucher au clavier : DICTEE_AUTOTEST=<secondes de dictée>
        auto = os.environ.get("DICTEE_AUTOTEST")
        if not auto:
            self.racc.lancer()
            self._icone()
        self.racine.after(15, self._depiler)
        if self.alerte:
            self.racine.after(800, lambda: self.pilule.message(self.alerte[:70], 6000, erreur=True))
        if auto:
            n = int(float(auto) * 1000)
            self.racine.after(1500, lambda: self.file.put(("debut", None)))
            self.racine.after(1500 + n, lambda: self.file.put(("fin", None)))
            self.racine.after(1500 + n + 6000, lambda: self.file.put(("quitter", None)))
        self.racine.mainloop()

    def _depiler(self) -> None:
        try:
            while True:
                try:
                    e, x = self.file.get_nowait()
                except queue.Empty:
                    break
                try:
                    getattr(self, "_sur_" + e)(x)
                except Exception:  # un événement qui plante ne doit jamais arrêter les suivants
                    _journal_erreur(f"événement {e}")
            if self.session is not None and time.time() - self.debut > self.cfg.duree_max:
                self.racc.reinitialiser()
                self._sur_fin(None)
        except Exception:
            _journal_erreur("boucle")
        finally:
            self.racine.after(15, self._depiler)

    # --- dictée --------------------------------------------------------------
    def _sur_debut(self, _):
        if self.pause or self.session is not None:
            return
        self.debut = time.time()
        self.appli = historique.appli_active()
        # les mots qui comptent le plus en ce moment (la mémoire les reclasse à chaque dictée)
        self.moteur.mots = self.memoire.mots_prioritaires(100)
        self.session = self.moteur.nouvelle_session()
        try:
            self.micro.demarrer(self.session.pousser)
        except Exception as e:
            self.session.annuler()
            self.session = None
            self.racc.reinitialiser()
            self.pilule.message(f"Micro introuvable : {e}"[:60], 3000, erreur=True)
            return
        if self.cfg.sons:
            sons.jouer(sons.DEBUT)
        self.pilule.ecoute()

    def _sur_mains_libres(self, _):
        if self.session is not None:
            self.pilule.ecoute(mains_libres=True)

    def _sur_annuler(self, _):
        if self.session is None:
            return
        self.micro.arreter()
        self.session.annuler()
        self.session = None
        self.pilule.message("Dictée annulée", 1000)

    def _sur_fin(self, _):
        s = self.session
        if s is None:
            return
        self.session = None
        self.micro.arreter()
        self.dernier_muet = self.micro.muet()
        self.dernier_remplacant = self.micro.remplacant
        if time.time() - self.debut < DUREE_MIN:
            s.annuler()
            self.pilule.cacher()
            return
        if self.cfg.sons:
            sons.jouer(sons.FIN)
        self.pilule.transcription()
        # La mémoire ne se touche que dans ce fil : on lui prend une copie des remplacements ici.
        remplacements = {**self.cfg.remplacements, **self.memoire.remplacements()}
        quand, appli = self.debut, self.appli
        calme = self.micro.crete < CRETE_CALME
        threading.Thread(target=self._finir, args=(s, quand, appli, remplacements, calme), daemon=True).start()

    def _finir(self, s, quand: float, appli: str, remplacements: dict[str, str], calme: bool = False) -> None:
        r: Resultat = s.terminer()
        texte = nettoyer(r.texte, remplacements, self.cfg.snippets, self.cfg.sans_hesitations)
        if _PONCTUATION_SEULE.match(texte) or (calme and _INVENTIONS.match(texte)):
            texte = ""
        colle, raison = False, ""
        fenetre = titre_fenetre_active()
        if texte:
            # Espace de liaison : dicter à la suite d'un texte déjà là ne colle pas les mots.
            colle, raison = coller(texte + " ")
            self.derniere = texte
        # L'audio n'est gardé que si la dictée a raté (pour la retranscrire) : rien ne s'accumule.
        audio = ""
        if r.voie == "erreur" and self.cfg.garder_audio_jours > 0 and s.pcm:
            try:
                audio = historique.garder_audio(bytes(s.pcm), quand)
            except OSError:
                pass
        historique.ajouter({"quand": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(quand)), "texte": texte,
                            "brut": r.texte, "duree_s": round(s.duree(), 1), "latence_ms": r.latence_ms, "voie": r.voie,
                            "appli": appli, "fenetre": fenetre, "colle": colle, "raison": raison, "erreur": r.erreur,
                            "audio": audio})
        self.file.put(("resultat", (texte, colle, raison, r, s.duree(), appli)))

    def _sur_resultat(self, x):
        texte, colle, raison, r, duree, appli = x
        if texte:
            self.memoire.noter_dictee(texte, duree)
            try:
                self.memoire.enregistrer()
            except OSError:
                pass
            if colle and self.cfg.apprendre:
                self.veilleur.surveiller(texte, appli)
        if r.voie == "erreur":
            if self.cfg.sons:
                sons.jouer(sons.ERREUR)
            e = (r.erreur or "").lower()
            if any(k in e for k in ("401", "403", "invalid_api_key", "api key not valid", "unauthorized")):
                quoi = "Clé refusée : change-la dans le menu de l'icône"
            elif any(k in e for k in ("402", "429", "quota", "insufficient", "credits")):
                quoi = "Crédits ou quota épuisés chez le service de transcription"
            else:
                quoi = "Réseau indisponible : dictée gardée dans l'historique"
            self.pilule.message(quoi, 4000, erreur=True)
        elif not texte and self.dernier_muet:
            micro = self.dernier_remplacant or self.micro.nom_actif()
            self.pilule.message(f"Micro muet ({micro[:28]}) : change-le dans l'icône Dictée", 4000, erreur=True)
        elif not texte:
            self.pilule.message("Rien entendu", 1200)
        elif not colle and raison == "test":
            self.pilule.message("Test : collage retenu", 1500)
        elif not colle:
            mettre_texte(texte, discret=False)
            if raison == "admin":
                self.pilule.message("Fenêtre administrateur : colle avec Ctrl+V", 3000)
            else:
                self.pilule.message("Copié : fais Ctrl+V", 2500)
        elif self.dernier_remplacant:
            self.pilule.message(f"Micro choisi absent, pris : {self.dernier_remplacant[:30]}", 2500)
        else:
            self.pilule.cacher()

    def _sur_recoller(self, _):
        if self.derniere:
            threading.Thread(target=coller, args=(self.derniere + " ",), daemon=True).start()

    # --- mémoire ---------------------------------------------------------------
    def _sur_appris(self, corrections):
        nouveaux = []
        for entendu, ecrit in corrections:
            if self.memoire.apprendre_correction(entendu, ecrit):
                nouveaux.append(ecrit)
        if nouveaux:
            try:
                self.memoire.enregistrer()
            except OSError:
                pass
            if self.session is None:
                self.pilule.message("Appris : " + ", ".join(nouveaux)[:48], 2200)

    def _sur_memoriser(self, _):
        def faire():
            sel = copier_selection()
            self.file.put(("selection", sel))
        threading.Thread(target=faire, daemon=True).start()

    def _sur_selection(self, sel: str):
        sel = re.sub(r"\s+", " ", sel or "").strip()
        if not sel:
            self.pilule.message("Sélectionne d'abord un mot", 1800)
        elif len(sel) > 50 or len(sel.split()) > 5:
            self.pilule.message("Sélection trop longue : un nom ou quelques mots", 2200)
        elif self.memoire.ajouter_mot(sel, "selection"):
            self.memoire.enregistrer()
            self.pilule.message(f"Retenu : {sel}"[:52], 2000)
        else:
            self.pilule.message(f"Déjà connu : {sel}"[:52], 1800)

    def _sur_ouvrir_memoire(self, _):
        from .fenetre_memoire import ouvrir

        if self.fenetre_memoire is not None and self.fenetre_memoire.winfo_exists():
            self.fenetre_memoire.lift()
            return
        self.fenetre_memoire = ouvrir(self.racine, self.memoire)

    def _sur_changer_cles(self, _):
        from .accueil import demander_cles

        if demander_cles(self.racine):
            self.moteur.cle, self.moteur.cle_gemini = self.cfg.cle_api(), self.cfg.cle_gemini()
            self.pilule.message("Clés enregistrées", 1500)

    def _sur_quitter(self, _):
        self.racc.arreter()
        self.micro.arreter()
        try:
            self.memoire.enregistrer()
        except OSError:
            pass
        if self.icone:
            self.icone.stop()
        self.racine.destroy()

    # --- icône dans la barre des tâches -------------------------------------
    def _icone(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            return
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse((2, 2, 62, 62), fill=(13, 13, 13, 255), outline=(201, 162, 39, 255), width=3)
        d.rounded_rectangle((25, 14, 39, 38), radius=7, fill=(229, 199, 107, 255))
        d.arc((19, 24, 45, 46), start=0, end=180, fill=(229, 199, 107, 255), width=3)
        d.line((32, 46, 32, 52), fill=(229, 199, 107, 255), width=3)
        envoyer = lambda e: (lambda *_: self.file.put((e, None)))
        vus, uniques = set(), []
        for _, m in lister_micros():
            if m not in vus:
                vus.add(m)
                uniques.append(m)

        def choisir(nom):
            def faire(*_):
                self.cfg.micro = nom
                self.micro.nom = nom
                Config.modifier(micro=nom)
            return faire

        def basculer_demarrage(*_):
            try:
                demarrage.desactiver() if demarrage.actif() else demarrage.activer()
            except Exception:
                _journal_erreur("démarrage")

        menu = pystray.Menu(
            pystray.MenuItem(lambda _i: f"Dictée : {'en pause' if self.pause else 'prête'} ({self.cfg.raccourci})", None, enabled=False),
            pystray.MenuItem("Ta mémoire", envoyer("ouvrir_memoire"), default=True),
            pystray.MenuItem("Pause", lambda *_: setattr(self, "pause", not self.pause), checked=lambda _i: self.pause),
            pystray.MenuItem("Recoller la dernière dictée", envoyer("recoller")),
            pystray.MenuItem("Micro", pystray.Menu(
                pystray.MenuItem("Celui de Windows", choisir(""), checked=lambda _i: not self.cfg.micro, radio=True),
                *[pystray.MenuItem(m[:60], choisir(m), checked=lambda _i, m=m: self.cfg.micro == m, radio=True) for m in uniques[:12]],
            )),
            pystray.MenuItem("Lancer avec Windows", basculer_demarrage, checked=lambda _i: demarrage.actif()),
            pystray.MenuItem("Changer de clé", envoyer("changer_cles")),
            pystray.MenuItem("Réglages", lambda *_: (self.cfg.enregistrer() if not FICHIER.exists() else None, _ouvrir(FICHIER))),
            pystray.MenuItem("Quitter", envoyer("quitter")),
        )
        self.icone = pystray.Icon("dictee", im, "Dictée", menu)
        self.icone.run_detached()


def _ouvrir(chemin: Path) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if not chemin.exists():
        chemin.write_text("", encoding="utf-8")
    os.startfile(str(chemin))


def principal() -> None:
    if not os.environ.get("DICTEE_AUTOTEST") and not _instance_unique():
        return
    DOSSIER.mkdir(parents=True, exist_ok=True)
    try:
        App(Config.charger()).lancer()
    except SystemExit:
        raise
    except Exception:
        # Sous pythonw, un plantage au démarrage serait invisible : on le dit, et on le garde.
        _journal_erreur("démarrage de Dictée")
        ctypes.windll.user32.MessageBoxW(None, f"Dictée n'a pas pu démarrer. Détail dans :\n{DOSSIER / 'erreurs.log'}",
                                         "Dictée", 0x10)
