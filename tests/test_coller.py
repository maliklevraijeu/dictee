"""Retenir un mot par un appui bref : seule une vraie sélection compte. python tests/test_coller.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dictee.coller import vraie_selection  # noqa: E402

assert vraie_selection("Mars Men") == "Mars Men"
assert vraie_selection("  Canva ") == "Canva"
# sans sélection, VS Code copie la ligne entière avec son retour à la ligne : ignorée
assert vraie_selection("    const total = prix * 2;\n") == ""
assert vraie_selection("une ligne\r\n") == ""
assert vraie_selection("") == ""
print("ok")
