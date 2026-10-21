"""L'application : raccourci -> micro -> moteur en direct -> nettoyage -> collage -> mémoire.

Fils : le principal fait tourner la pastille (tkinter) et reçoit tout par une file ; le crochet
clavier, le micro, le moteur, l'apprentissage et l'icône ont chacun le leur. Rien de bloquant
dans le principal.
"""
from __future__ import annotations

import collections
import ctypes
import os
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path

from . import demarrage, ecran, historique, sons
from .apprentissage import Veilleur
from .audio import Micro, lister_micros
from .coller import coller, copier_selection, mettre_texte, titre_fenetre_active
from .config import DOSSIER, FICHIER, Config
from .langues import choisir as choisir_langue
from .langues import t
from .memoire import Memoire
from .moteur import Moteur, Resultat
from .nettoyage import nettoyer
from .pilule import Pilule
from .raccourci import Raccourcis

DUREE_MIN = 0.3  # un appui plus court est un faux départ : on l'ignore
TRAINE_MS = 300  # le micro écoute encore ce temps après le relâchement, pour la dernière syllabe

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
        choisir_langue(cfg.interface)
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
        self.moteur.mode = cfg.moteur
        self.micro = Micro(cfg.micro, cfg.micro_pret)
        self._traine = None  # dictée relâchée dont le micro écoute encore un instant
        self.file: queue.Queue = queue.Queue()
        self.alerte = ""
        try:
            self.racc = Raccourcis(cfg.raccourci, cfg.mains_libres, cfg.recoller, lambda e: self.file.put((e, None)),
                                   cfg.memoriser)
        except ValueError as e:  # raccourci mal écrit dans les réglages : on garde ceux par défaut
            d = Config()
            self.racc = Raccourcis(d.raccourci, d.mains_libres, d.recoller, lambda e: self.file.put((e, None)),
                                   d.memoriser)
            self.alerte = t("raccourci_invalide", erreur=e)
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
        self.telephone = None  # le serveur de la page du téléphone, lancé à la demande
        self.fenetre_telephone = None
        self._pare_feu_en_cours = False
        self.recentes: collections.deque[str] = collections.deque(maxlen=30)  # dernières dictées collées

    # --- boucle principale ----------------------------------------------
    def lancer(self) -> None:
        historique.purger_audio(self.cfg.garder_audio_jours)
        historique.garder_dernieres()
        # Test de bout en bout sans toucher au clavier : DICTEE_AUTOTEST=<secondes de dictée>
        auto = os.environ.get("DICTEE_AUTOTEST")
        if not auto:
            self.racc.lancer()
            self._icone()
            threading.Thread(target=self.micro.preparer, daemon=True).start()
            if self.cfg.telephone:
                threading.Thread(target=self._relancer_telephone, daemon=True).start()
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
        self.memoire.synchroniser()
        self.moteur.mots = self.memoire.mots_prioritaires(100)
        self.session = self.moteur.nouvelle_session()
        try:
            self.micro.demarrer(self.session.pousser)
        except Exception as e:
            self.session.annuler()
            self.session = None
            self.racc.reinitialiser()
            self.pilule.message(t("micro_introuvable", erreur=e)[:60], 3000, erreur=True)
            return
        # les noms affichés dans la fenêtre (un prénom dans un mail, une marque dans la page) : lus pendant
        # que tu parles, ils rejoignent les mots de CETTE dictée
        if self.cfg.contexte_ecran and hasattr(self.session, "ajouter_mots"):
            ecran.en_fond(self.session.ajouter_mots)
        if self.cfg.sons:
            sons.jouer(sons.DEBUT)
        self.pilule.ecoute()

    def _sur_mains_libres(self, _):
        if self.session is not None:
            self.pilule.ecoute(mains_libres=True)

    def _sur_annuler(self, _):
        if self.session is None:
            return
        self._traine = None
        self.micro.arreter()
        self.session.annuler()
        self.session = None
        self.pilule.message(t("annulee"), 1000)

    def _sur_fin(self, _):
        s = self.session
        if s is None or self._traine is s:
            return
        if time.time() - self.debut < DUREE_MIN:
            # Appui bref sur le raccourci, sans parler : si un mot est sélectionné, Dictée le retient.
            # Sans sélection, rien ne se passe (c'était un faux départ).
            self.session = None
            self.micro.arreter()
            s.annuler()
            self.pilule.cacher()
            self._sur_memoriser("appui bref")
            return
        # On relâche souvent la touche en prononçant encore la dernière syllabe : le micro continue un
        # court instant (mesuré le 21/10 : des dictées finissaient sur un mot coupé, « On en est- »).
        self._traine = s
        self.racine.after(TRAINE_MS, lambda: self._fin_apres_traine(s))

    def _fin_apres_traine(self, s):
        self._traine = None
        if self.session is not s:  # annulée (Échap) pendant la traîne
            return
        self.session = None
        self.micro.arreter()
        self.dernier_muet = self.micro.muet()
        self.dernier_remplacant = self.micro.remplacant
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
        texte = nettoyer(r.texte, remplacements, self.cfg.snippets, self.cfg.sans_hesitations, self.cfg.langue)
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
            self.recentes.append(texte)
            self.memoire.synchroniser()
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
                quoi = t("cle_refusee")
            elif any(k in e for k in ("402", "429", "quota", "insufficient", "credits")):
                quoi = t("quota")
            else:
                quoi = t("reseau")
            self.pilule.message(quoi, 4000, erreur=True)
        elif not texte and self.dernier_muet:
            micro = self.dernier_remplacant or self.micro.nom_actif()
            self.pilule.message(t("micro_muet", micro=micro[:28]), 4000, erreur=True)
        elif not texte:
            self.pilule.message(t("rien_entendu"), 1200)
        elif not colle and raison == "test":
            self.pilule.message(t("test"), 1500)
        elif not colle:
            mettre_texte(texte, discret=False)
            if raison == "admin":
                self.pilule.message(t("admin"), 3000)
            else:
                self.pilule.message(t("copie"), 2500)
        elif self.dernier_remplacant:
            self.pilule.message(t("micro_remplace", micro=self.dernier_remplacant[:30]), 2500)
        else:
            self.pilule.cacher()

    def _sur_recoller(self, _):
        if self.derniere:
            threading.Thread(target=coller, args=(self.derniere + " ",), daemon=True).start()

    # --- mémoire ---------------------------------------------------------------
    def _sur_appris(self, corrections):
        self.memoire.synchroniser()
        nouveaux = []
        for entendu, ecrit in corrections:
            # Le « bon » texte vient d'une autre dictée (on a redicté par-dessus) : ce n'est pas une
            # correction tapée à la main, le moteur a juste entendu autre chose une 2e fois.
            if any(ecrit in d for d in self.recentes):
                continue
            if self.memoire.apprendre_correction(entendu, ecrit):
                nouveaux.append(ecrit)
        if nouveaux:
            try:
                self.memoire.enregistrer()
            except OSError:
                pass
            if self.session is None:
                self.pilule.message(t("appris", mots=", ".join(nouveaux)[:48]), 2200)

    def _sur_memoriser(self, origine):
        def faire():
            sel = copier_selection()
            if sel or origine != "appui bref":  # un appui bref sans sélection reste silencieux
                self.file.put(("selection", sel))
        threading.Thread(target=faire, daemon=True).start()

    def _sur_selection(self, sel: str):
        sel = re.sub(r"\s+", " ", sel or "").strip()
        if not sel:
            self.pilule.message(t("selection_vide"), 1800)
        elif len(sel) > 50 or len(sel.split()) > 5:
            self.pilule.message(t("selection_longue"), 2200)
        elif self.memoire.synchroniser() or self.memoire.ajouter_mot(sel, "selection"):
            self.memoire.enregistrer()
            self.pilule.message(t("retenu", mot=sel)[:52], 2000)
        else:
            self.pilule.message(t("deja_connu", mot=sel)[:52], 1800)

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
            self.pilule.message(t("cles_ok"), 1500)

    # --- téléphone ------------------------------------------------------------------
    def _relancer_telephone(self) -> None:
        from . import telephone

        # allumé à la dernière session : on ne réécoute que si le pare-feu est toujours d'accord
        if telephone.regle_presente():
            self.file.put(("lancer_telephone", None))

    def _sur_lancer_telephone(self, _):
        self._lancer_telephone()

    def _lancer_telephone(self) -> bool:
        from .telephone import Serveur

        if self.telephone is None:
            self.telephone = Serveur(self._du_telephone)
        try:
            self.telephone.lancer()
            return True
        except OSError:
            _journal_erreur("serveur du téléphone")
            return False

    def _du_telephone(self, texte: str) -> dict:
        """Appelé dans le fil du serveur : on passe par la file, et on attend le collage pour répondre."""
        reponse, fait = {}, threading.Event()
        self.file.put(("telephone", (texte, reponse, fait)))
        if not fait.wait(10):
            # Trop tard : le téléphone dira « réessaie », donc ce texte-là ne doit plus être collé.
            reponse["abandon"] = True
            return {"ok": False, "raison": "occupe"}
        return reponse

    def _sur_telephone(self, x):
        texte, reponse, fait = x
        if reponse.get("abandon"):
            return
        if self.pause:
            reponse.update(ok=False, raison="pause")
            fait.set()
            return
        remplacements = {**self.cfg.remplacements, **self.memoire.remplacements()}
        propre = nettoyer(texte, remplacements, self.cfg.snippets, self.cfg.sans_hesitations, self.cfg.langue)
        if _PONCTUATION_SEULE.match(propre):
            reponse.update(ok=False, raison="vide")
            fait.set()
            return
        appli, fenetre = historique.appli_active(), titre_fenetre_active()

        def faire():
            if reponse.get("abandon"):
                return
            colle, raison = coller(propre + " ")
            copie = not colle and raison != "test" and mettre_texte(propre, discret=False)
            reponse.update(ok=bool(colle or copie), colle=colle, raison=raison)
            fait.set()
            historique.ajouter({"quand": time.strftime("%Y-%m-%d %H:%M:%S"), "texte": propre, "brut": texte,
                                "duree_s": 0, "latence_ms": 0, "voie": "telephone", "appli": appli, "fenetre": fenetre,
                                "colle": colle, "raison": raison, "erreur": "", "audio": ""})
            self.file.put(("telephone_colle", (propre, colle, raison, appli)))

        threading.Thread(target=faire, daemon=True).start()

    def _sur_telephone_colle(self, x):
        propre, colle, raison, appli = x
        self.derniere = propre
        self.memoire.synchroniser()
        self.memoire.noter_dictee(propre, 0)
        try:
            self.memoire.enregistrer()
        except OSError:
            pass
        if colle and self.cfg.apprendre:
            self.veilleur.surveiller(propre, appli)
        elif raison == "admin":
            self.pilule.message(t("admin"), 3000)
        elif not colle:
            self.pilule.message(t("recu_telephone"), 2500)

    def _sur_ouvrir_telephone(self, _):
        if self.fenetre_telephone is not None and self.fenetre_telephone.winfo_exists():
            self.fenetre_telephone.lift()
            return
        if self._pare_feu_en_cours:
            return
        self._pare_feu_en_cours = True

        def preparer():
            # Hors du fil de l'interface : netsh et la demande de Windows peuvent prendre du temps.
            from . import telephone

            pret = telephone.regle_presente()
            if not pret:
                # Sans la règle, Windows bloque le téléphone sur un réseau « public » (le réglage par
                # défaut de beaucoup de box). On n'écoute jamais avant : pas d'alerte du pare-feu dont
                # le « Annuler » bloquerait Dictée pour de bon.
                self.file.put(("message", t("pare_feu_oui")))
                if telephone.demander_pare_feu():
                    fin = time.time() + 30
                    while time.time() < fin and not pret:
                        time.sleep(0.7)
                        pret = telephone.regle_presente()
            self.file.put(("montrer_telephone", pret))

        threading.Thread(target=preparer, daemon=True).start()

    def _sur_message(self, texte: str):
        self.pilule.message(texte, 4000)

    def _sur_montrer_telephone(self, pret: bool):
        from .fenetre_telephone import ouvrir

        self._pare_feu_en_cours = False
        if not pret:
            self.pilule.message(t("pare_feu_non"), 4000, erreur=True)
            return
        if not self._lancer_telephone():
            self.pilule.message(t("telephone_impossible"), 3000, erreur=True)
            return
        if not self.cfg.telephone:
            self.cfg.telephone = True
            Config.modifier(telephone=True)
        self.fenetre_telephone = ouvrir(self.racine, self.telephone.adresse(), self._couper_telephone)

    def _couper_telephone(self):
        from . import telephone

        if self.telephone is not None:
            self.telephone.arreter()
        self.telephone = None
        telephone.oublier_jeton()  # le QR code déjà scanné ne marchera plus
        self.cfg.telephone = False
        Config.modifier(telephone=False)

    def _sur_quitter(self, _):
        if self.telephone is not None:
            self.telephone.arreter()
        self.racc.arreter()
        self.micro.fermer()
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
                self.micro.fermer()
                self.micro.preparer()
                Config.modifier(micro=nom)
            return faire

        def basculer_demarrage(*_):
            try:
                demarrage.desactiver() if demarrage.actif() else demarrage.activer()
            except Exception:
                _journal_erreur("démarrage")

        menu = pystray.Menu(
            pystray.MenuItem(lambda _i: t("etat", etat=t("en_pause") if self.pause else t("prete"), raccourci=self.cfg.raccourci),
                             None, enabled=False),
            pystray.MenuItem(t("menu_memoire"), envoyer("ouvrir_memoire"), default=True),
            pystray.MenuItem(t("menu_telephone"), envoyer("ouvrir_telephone"),
                             checked=lambda _i: self.telephone is not None and self.telephone.actif),
            pystray.MenuItem(t("menu_pause"), lambda *_: setattr(self, "pause", not self.pause), checked=lambda _i: self.pause),
            pystray.MenuItem(t("menu_recoller"), envoyer("recoller")),
            pystray.MenuItem(t("menu_micro"), pystray.Menu(
                pystray.MenuItem(t("micro_windows"), choisir(""), checked=lambda _i: not self.cfg.micro, radio=True),
                *[pystray.MenuItem(m[:60], choisir(m), checked=lambda _i, m=m: self.cfg.micro == m, radio=True) for m in uniques[:12]],
            )),
            pystray.MenuItem(t("menu_demarrage"), basculer_demarrage, checked=lambda _i: demarrage.actif()),
            pystray.MenuItem(t("menu_cles"), envoyer("changer_cles")),
            pystray.MenuItem(t("menu_reglages"), lambda *_: (self.cfg.enregistrer() if not FICHIER.exists() else None, _ouvrir(FICHIER))),
            pystray.MenuItem(t("menu_quitter"), envoyer("quitter")),
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
        ctypes.windll.user32.MessageBoxW(None, t("demarrage_rate", chemin=DOSSIER / "erreurs.log"),
                                         "Dictée", 0x10)
