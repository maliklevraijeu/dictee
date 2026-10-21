"""Mots trop courants pour être « appris » : on n'apprend jamais à remplacer « le » par « la ».
L'apprentissage ne retient que les noms, marques et mots rares (voir apprentissage.py)."""

FRANCAIS = set("""
a à ai aie ait alors après as au aucun aussi autre autres aux avais avait avant avec avez avoir avons ayant
bah bien bon bonne c ça car ce ceci cela celle celles celui cependant ces cet cette ceux chaque chez ci
comme comment contre d dans de dedans dehors déjà des dessous dessus deux devant devrait dire dit dois doit
donc dont du durant e elle elles en encore entre es est et étaient était été être eu eux fait faire fais
faut fois font fut grand gros hors i ici il ils j je jusqu jusque l la là le les leur leurs lui m ma mais
me même mêmes mes moi moins mon n ne ni non nos notre nous on ont ou où oui par parce pas peu peut peux
plus plutôt pour pourquoi pouvait pu puis qu quand que quel quelle quelles quels qui quoi s sa sans se sera
ses si sien soi soit son sont sous suis sur t ta tant te tes toi ton tous tout toute toutes très trop tu
un une va vais vas vers veut veux via vite voici voilà vos votre vous vu y
truc trucs chose choses gens frère frères personne personnes coup moment jour jours temps fin début
vraiment exactement justement simplement juste genre enfin bref ok okay voilà allez écoute regarde
mettre mets met mis prendre prends pris donner donne voir vois vu savoir sais sait aller vas va venir viens
faire fais fait dire dis dit pouvoir peux peut vouloir veux veut falloir faut parler parle
""".split())

ANGLAIS = set("""
a about after all also an and any are as at be because been but by can could do does for from get got
had has have he her him his how i if in into is it its just like me more my no not now of on one or our
out so some than that the their them then there these they this to too up us was we were what when which
who will with would you your yes ok okay
""".split())

COURANTS = FRANCAIS | ANGLAIS


def courant(mot: str) -> bool:
    return mot.lower().strip("'’-.,;:!?") in COURANTS
