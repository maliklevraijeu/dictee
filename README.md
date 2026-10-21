# Dictée

[English version](README.en.md)

Tu maintiens Ctrl+Win, tu parles, tu relâches, et ton texte se colle là où tu écris, dans n'importe quelle appli Windows.

J'utilisais Wispr Flow, une appli de dictée payante, toute la journée, et je ne voulais plus payer un abonnement chaque mois pour un outil que je peux faire tourner moi-même. Dictée envoie ta voix pendant que tu parles, donc quand tu relâches la touche il ne reste presque plus rien à transcrire, et le texte arrive environ un quart de seconde après, avec ElevenLabs, sur 40 de mes dictées.

## Installer

Il faut Windows 10 ou 11 et une connexion internet. Appuie sur la touche Windows, tape « PowerShell », ouvre-le, puis colle cette ligne avec un clic droit et appuie sur Entrée :

```powershell
irm https://raw.githubusercontent.com/maliklevraijeu/dictee/v0.3.0/installer.ps1 | iex
```

Le script installe Python pour ton compte s'il manque, sans droits administrateur, puis Dictée dans ton dossier utilisateur, et il la lance avec Windows. Tu peux lire [installer.ps1](installer.ps1) avant de le lancer. Si le script dit qu'il n'arrive pas à installer Python, installe-le d'abord depuis python.org en cochant « Add python.exe to PATH », puis relance la ligne.

## Le premier lancement

Dictée te demande une clé, le code qu'un service de transcription te donne quand tu crées un compte chez lui. Pour essayer gratuitement, va sur [aistudio.google.com/apikey](https://aistudio.google.com/apikey), connecte-toi avec ton compte Google, crée une clé et colle-la dans Dictée.

La clé Gemini est gratuite, et le texte arrive en 1 à 2 secondes dans mes essais. La clé [ElevenLabs](https://elevenlabs.io/app/settings/api-keys) donne le quart de seconde, et tu peux mettre les deux : Gemini prend alors le relais si ElevenLabs ne répond pas. Les clés restent chiffrées sur ton PC, et tu les changes dans le menu de l'icône près de l'horloge.

## Les raccourcis

| Raccourci | Ce que ça fait |
| --- | --- |
| Maintenir Ctrl+Win | Dicter, puis relâcher pour coller |
| Ctrl+Win+Espace | Mains libres, Ctrl+Win une 2e fois pour finir |
| Échap | Annuler la dictée en cours |
| Alt+Maj+Z | Recoller la dernière dictée |
| Alt+Maj+M | Retenir le mot que tu as sélectionné |

## Sans micro sur ton PC

Des écouteurs avec micro, en jack ou en Bluetooth (AirPods compris), marchent tels quels : tu les choisis dans le menu « Micro » de l'icône de Dictée, près de l'horloge (sous la flèche ^ si tu ne la vois pas). Si tu n'en as pas, ton téléphone fait l'affaire, sans rien installer dessus.

Dans le même menu, « Dicter depuis le téléphone » affiche un QR code, que tu scannes avec l'appareil photo. Clique sur le PC là où tu veux écrire, puis, sur le téléphone, touche la zone de texte, le micro du clavier, parle, et touche « Envoyer au PC ». C'est ton téléphone qui transcrit, gratuitement, et Dictée repasse ensuite sur le texte avec les corrections qu'elle a apprises. Si le micro n'apparaît pas sur le clavier de l'iPhone, va dans Réglages, Général, Clavier, et active la dictée.

Il faut que ton PC et ton téléphone soient sur le même Wi-Fi. La première fois, Windows demande si Dictée peut modifier l'appareil : réponds « Oui », c'est ce qui ouvre ton PC aux seuls appareils de ton Wi-Fi. Le texte ne passe jamais par internet, et le code secret du QR code empêche les autres appareils d'écrire sur ton PC.

## Elle apprend tes mots

Pour lui apprendre un nom tout de suite, une marque par exemple, ouvre « Ta mémoire » et tape-le, ou colles-en plusieurs séparés par des virgules. Si le moteur entend toujours autre chose, l'onglet Corrections lui dit quoi écrire à la place : « Mark Smead » devient alors « Mars Men » à chaque dictée.

Quand tu corriges un mot juste après une dictée, Dictée le remarque. Si elle a écrit « Kanvas » et que tu remplaces par « Canva », le bon mot entre dans ton vocabulaire, et à la 2e correction identique elle fait le remplacement d'elle-même. Pour le voir, elle relit le champ où tu écris pendant 45 secondes au plus, avec les fonctions d'accessibilité de Windows, et jamais un champ de mot de passe.

Elle ne retient pas les accords que tu corriges, comme « petit » devenu « petite », ni une phrase que tu redictes par-dessus, parce que ce ne sont pas des erreurs d'écoute. Tes mots se classent tout seuls, ceux que tu dis le plus et le plus récemment passant devant, parce que le direct d'ElevenLabs n'en accepte que 50 par dictée. Tout ce qu'elle a appris se relit et se corrige dans « Ta mémoire », qui s'ouvre d'un clic sur l'icône.

## Ce qu'elle fait de ta voix

Elle garde tes phrases telles que tu les as dites. Elle enlève les « euh » (les « um » en anglais) et les faux départs. En français, elle met une espace devant les points d'interrogation, et en anglais elle n'en met pas.

Ta voix part chez ElevenLabs le temps de la transcription, et chez Google seulement si tu n'as mis qu'une clé Gemini ou si ElevenLabs ne répond pas. Ce que ces services en gardent dépend de leurs conditions : sur l'offre gratuite de Gemini, Google peut s'en servir pour améliorer ses produits, sauf si tu es dans l'Union européenne, en Suisse ou au Royaume-Uni ([conditions de l'API Gemini](https://ai.google.dev/gemini-api/terms)). Quand tu dictes depuis le téléphone, c'est son clavier qui traite ta voix, donc Apple ou Google selon le téléphone et ses réglages.

Tout le reste reste sur ton PC, dans `%APPDATA%\Dictee`. L'historique garde le texte de tes 5 000 dernières dictées, avec le nom de l'appli et le titre de la fenêtre, et l'audio n'est gardé que si une dictée a échoué, 7 jours, pour que tu puisses la refaire. Le raccourci clavier ne surveille que ses propres touches et n'enregistre rien de ce que tu tapes, et ce qu'elle relit après une dictée ne sert qu'à trouver tes corrections : tu peux le vérifier dans [raccourci.py](dictee/raccourci.py) et [apprentissage.py](dictee/apprentissage.py).

## Ce que ça coûte

Dictée est gratuite, et seule la transcription peut coûter quelque chose. Gemini a une offre gratuite, avec des limites d'usage. Chez ElevenLabs, une heure de parole coûte moins de 50 centimes, et leur offre gratuite couvre environ 2 heures de dictée par mois ([leurs tarifs](https://elevenlabs.io/pricing/api)).

## Si quelque chose coince

- Windows empêche les autres applis d'écrire dans une appli lancée en administrateur. Dictée met alors le texte dans le presse-papiers et te dit de faire Ctrl+V.
- Si la connexion en direct coupe, ta dictée est renvoyée en entier chez ElevenLabs, puis chez Gemini si ça échoue encore. Si tout échoue, elle reste dans l'historique avec son audio.
- Les réglages sont dans `%APPDATA%\Dictee\config.json`, et le menu de l'icône ouvre ce fichier. Une erreur est notée dans `erreurs.log`, dans le même dossier.

C'est un projet personnel, partagé tel quel et sans garantie, sous licence MIT. Tu peux signaler un problème dans les issues du dépôt, sans délai de réponse promis.

## Désinstaller

Quitte Dictée depuis le menu de l'icône et décoche « Lancer avec Windows » juste avant. Supprime ensuite le dossier `%LOCALAPPDATA%\Dictee` et le raccourci « Dictée » du menu Démarrer, et supprime aussi `%APPDATA%\Dictee` si tu veux effacer ton historique, ta mémoire et tes clés. Si tu as dicté depuis le téléphone, la règle « Dictee - dicter depuis le telephone » reste dans le pare-feu de Windows, et tu peux la supprimer dans ses règles de trafic entrant.

## Comment j'ai mesuré

J'ai pris 40 de mes vraies dictées, de quelques secondes à 3 minutes et demie. Le même code que l'application les rejoue au rythme de la parole et chronomètre le temps entre la fin de la parole et le texte final, et Dictée met 0,23 seconde en médiane, avec ElevenLabs.

Wispr Flow note lui-même un délai pour chaque dictée dans son historique, sur le PC (le champ `e2eLatency` de sa base locale), et pour ces 40 dictées sa médiane est de 0,59 seconde. Les deux chronos ne partent peut-être pas exactement du même instant, donc lis l'écart comme un ordre de grandeur, mesuré sur un seul PC et une seule connexion. Pour chronométrer Dictée sur tes propres enregistrements en WAV 16 kHz mono, il y a `python -m dictee essai fichier.wav`.

Wispr Flow est une marque de ses propriétaires, et Dictée n'a aucun lien avec eux. Je le cite seulement parce que c'est l'outil que Dictée remplace chez moi.

## Pour les développeurs

```powershell
git clone https://github.com/maliklevraijeu/dictee
cd dictee
python -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\python -m dictee
```

Les tests du dossier `tests` se lancent sans micro ni clavier, par exemple `python tests/test_nettoyage.py`. Ils tournent aussi sur GitHub à chaque mise en ligne du code, et `tests/e2e_collage.py` demande un vrai bureau Windows.

## English

Dictée works in English too: the windows and messages follow the language of Windows, and on an English Windows you dictate in English from the start. The full page is in [README.en.md](README.en.md).
