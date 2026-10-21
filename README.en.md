# Dictée

[Version française](README.md)

Hold Ctrl+Win, speak, release, and your text is pasted wherever you are typing, in almost any Windows app.

I used Wispr Flow, a dictation app I paid for, all day long, and I didn't want to keep paying a monthly subscription for a tool I can run myself. Dictée transcribes with Scribe v2, the ElevenLabs model that made the fewest mistakes in my tests, and a long dictation is sent in pieces while you speak. On 40 of my own dictations, the text arrives about 0.6 seconds after a short dictation and 1 to 1.5 seconds after a long one.

## Install

You need Windows 10 or 11 and an internet connection. Press the Windows key, type "PowerShell", open it, then paste this line with a right click and press Enter:

```powershell
irm https://raw.githubusercontent.com/maliklevraijeu/dictee/v0.5.1/installer.ps1 | iex
```

The script installs Python for your account if it is missing, without admin rights, then installs Dictée in your user folder and starts it with Windows. You can read [installer.ps1](installer.ps1) before running it. If the script says it can't install Python, install it from python.org first, ticking "Add python.exe to PATH", then run the line again.

The windows and messages follow the language of Windows. On an English Windows you dictate in English from the start, and you can change it with `langue` in `%APPDATA%\Dictee\config.json` (`"en"`, `"fr"`, `"es"`...). The `interface` setting (`"auto"`, `"en"` or `"fr"`) does the same for the windows.

## First launch

Dictée asks for a key, the code a transcription service gives you when you create an account. To try it for free, go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey), sign in with your Google account, create a key and paste it into Dictée.

The Gemini key is free, and the text arrives in 1 to 2 seconds in my tests. An [ElevenLabs](https://elevenlabs.io/app/settings/api-keys) key is faster and more accurate, and you can add both, in which case Gemini takes over when ElevenLabs doesn't answer. Your keys stay encrypted on your PC, and you change them from the menu of the icon next to the clock.

## Shortcuts

| Shortcut | What it does |
| --- | --- |
| Hold Ctrl+Win | Dictate, then release to paste |
| Ctrl+Win+Space | Hands-free, press Ctrl+Win again to finish |
| Esc | Cancel the current dictation |
| Alt+Shift+Z | Paste the last dictation again |
| Quick tap on Ctrl+Win, with a word selected | Remember that word (a brand, a name) |

## No microphone on your PC

Headphones with a microphone, wired or Bluetooth (AirPods included), work as they are, and you pick them in the "Microphone" menu of the Dictée icon, next to the clock (under the ^ arrow if you don't see it). If you have none, your phone will do, with nothing to install on it.

In the same menu, "Dictate from your phone" shows a QR code that you scan with your camera. Click on the PC where you want to write, then on the phone tap the text box, the keyboard's microphone, speak, and tap "Send to PC". Your phone does the transcription for free, and Dictée then applies the corrections it has learned. If the microphone doesn't show on the iPhone keyboard, go to Settings, General, Keyboard, and turn on dictation.

Your PC and your phone need to be on the same Wi-Fi. The first time, Windows asks whether Dictée may make changes to the device: answer "Yes", which opens your PC to the devices on your Wi-Fi only. The text goes from your phone to your PC over your Wi-Fi only, and the secret code in the QR code stops other devices from typing on your PC.

## It learns your words

To teach it a name right away, a brand for example, open "Your memory" and type it, or paste several separated by commas. If the engine keeps hearing something else, the Corrections tab tells it what to write instead, so "Mark Smead" becomes "Mars Men" in every dictation.

When you fix a word right after a dictation, Dictée notices. If it wrote "Kanvas" and you replace it with "Canva", the right word enters your vocabulary, and after the 2nd identical fix it makes the replacement on its own. To see it, it reads the field you are typing in for 45 seconds at most, through the Windows accessibility features, and never a password field.

It doesn't learn grammar fixes, like "petit" turned into "petite", or a sentence you dictate again over the first one, because those aren't hearing mistakes, and never more than 4 words per dictation. Your words rank themselves, the ones you say most and most recently first, because the engine receives only 50 per dictation. Everything it learned can be read and fixed in "Your memory", which opens with a click on the icon.

When you press the keys, Dictée also reads the names shown in the window you are typing in, like the first name of the person you are replying to or a brand on the page. They go first in the engine's word list for that dictation only, nothing is kept, and `"contexte_ecran": false` in the settings turns this off.

## What it does with your voice

It keeps your sentences the way you said them. It removes the "um" and the false starts, and in French it adds the space French puts before question marks.

Your voice goes to ElevenLabs for the transcription, and to Google only if you added just a Gemini key or if ElevenLabs doesn't answer. What these services keep depends on their terms: on the free Gemini tier, Google may use it to improve its products, except in the European Union, Switzerland and the United Kingdom ([Gemini API terms](https://ai.google.dev/gemini-api/terms)). When you dictate from your phone, its keyboard handles your voice, so Apple or Google depending on the phone and its settings.

The microphone stays ready in the background so your first word is never cut: it keeps the last half second in memory, nothing is sent or recorded outside a dictation, and the Windows microphone indicator therefore stays on. You can turn this off with `"micro_pret": false` in the settings, and a Bluetooth headset is never kept open anyway.

Everything else stays on your PC, in `%APPDATA%\Dictee`. The history keeps the text of your last 5,000 dictations, with the app name and the window title, and audio is only kept when a dictation failed, for 7 days, so you can redo it. The keyboard shortcut only watches its own keys and records nothing you type, and what it reads after a dictation is only used to find your fixes: you can check it in [raccourci.py](dictee/raccourci.py) and [apprentissage.py](dictee/apprentissage.py).

## What it costs

Dictée is free, and only the transcription may cost something. Gemini has a free tier with usage limits. At ElevenLabs, an hour of speech costs about 30 cents, and their free plan covers about 4 hours of dictation a month ([their pricing](https://elevenlabs.io/pricing/api)).

## If something goes wrong

- Windows stops other apps from typing into an app run as administrator. Dictée then puts the text in the clipboard and tells you to press Ctrl+V.
- If ElevenLabs doesn't answer, your dictation goes to Gemini. If that fails too, it stays in the history with its audio.
- Settings are in `%APPDATA%\Dictee\config.json`, and the icon menu opens that file. Errors are written to `erreurs.log` in the same folder.

This is a personal project, shared as is and without warranty, under the MIT license. You can report a problem in the repository's issues, with no promised response time.

## Uninstall

Quit Dictée from the icon menu, unticking "Start with Windows" just before. Then delete the `%LOCALAPPDATA%\Dictee` folder and the "Dictée" shortcut in the Start menu, and delete `%APPDATA%\Dictee` too if you want to erase your history, memory and keys. If you dictated from your phone, the "Dictee - dicter depuis le telephone" rule stays in the Windows firewall, and you can delete it from its inbound rules.

## How I measured

I took 40 of my real dictations, from a few seconds to 3 and a half minutes. The same code as the app replays them at speaking speed and times the gap between the end of speech and the final text: about 0.6 seconds for a dictation under 8 seconds, 0.9 seconds up to 15 seconds, and 1.1 to 1.4 seconds beyond.

I also compared the words. Dictée's first engine, live streaming, differed from Wispr's text on 11% of the words, and I could read meaning errors in it. The current engine differs on only 7% of the words, and most of these gaps are plain variants ("t'en" or "tu en"). The live engine is still available with `"moteur": "rapide"` in the settings: the text arrives in about 0.2 seconds, with more word errors.

Wispr Flow records its own delay for each dictation in its history, on the PC (the `e2eLatency` field of its local database), and for these 40 dictations its median is 0.59 seconds, from 0.4 seconds on short dictations to 1 second on long ones. The two clocks may not start at exactly the same moment, so read the gap as an order of magnitude, measured on one PC and one connection. To time Dictée on your own 16 kHz mono WAV recordings, there is `python -m dictee essai file.wav`.

Wispr Flow is a trademark of its owners, and Dictée has no link with them. I only name it because it is the tool Dictée replaces for me.

## For developers

```powershell
git clone https://github.com/maliklevraijeu/dictee
cd dictee
python -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\python -m dictee
```

The tests in the `tests` folder run without a microphone or keyboard, for example `python tests/test_nettoyage.py`. They also run on GitHub every time code is pushed, and `tests/e2e_collage.py` needs a real Windows desktop. The code and its comments are in French.
