# -*- coding: utf-8 -*-
"""Compone playlist_real/index.html con gli STESSI componenti e le stesse
coordinate delle altre pagine. Il Playlist Manager non ha un wireframe Figma:
questa e' un'ipotesi coerente, non una copia di un disegno esistente."""
import io
import os as _os

_QUI = _os.path.dirname(_os.path.abspath(__file__))
PZ = _os.path.join(_QUI, 'pezzi')
OUT = r"F:\BoxVR Songs Tool\web_migration_spike\playlist_real\index.html"


def leggi(p):
    return io.open(p, encoding='utf-8').read()


style = leggi(_os.path.join(PZ, 'style.css.part'))
header = leggi(_os.path.join(PZ, 'header.html.part'))
# «Cartella BoxVR» apre TrackData, che qui non c'entra: questa pagina lavora
# su WorkoutPlaylists. E la funzione che chiama non esiste nel blocco JS
# ridotto di questa pagina, quindi sarebbe un comando che schianta. Fuori.
import re as _re
header = _re.sub(r'\s*<button class="header-btn" id="game-folder-btn".*?</button>',
                 '', header, flags=_re.S)
# blocco RIDOTTO: questa pagina non ha l'anteprima brano
js_cond = leggi(_os.path.join(PZ, 'js_playlist.part'))
corpo = leggi(_os.path.join(_QUI, 'playlist_corpo.html.part'))
css = leggi(_os.path.join(_QUI, 'playlist_stile.css.part'))
js_spec = leggi(_os.path.join(_QUI, 'playlist_specifico.js.part'))

# il toolkit di Correggi porta con se' le coordinate della card in basso, che
# riuso identiche: le prendo dal suo foglio invece di riscriverle
css_toolkit = leggi(_os.path.join(_QUI, 'correggi_toolkit.css.part'))
style = style.replace('</style>', css_toolkit + css + '</style>')

TESTA = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>BoxVR Survivor Toolkit - Gestione playlist</title>
<link rel="stylesheet" href="styles.css">
"""

pagina = (TESTA + style + """
</head>
<body>
<div class="page genera-fixed">
  <div class="bg-pattern" id="bg-pattern"></div>

""" + header + "\n" + corpo + """
</div>
<script>
""" + js_cond + js_spec + """
</script>
</body>
</html>
""")

io.open(OUT, 'w', encoding='utf-8', newline='').write(pagina)
print('scritto', OUT, len(pagina), 'caratteri')
