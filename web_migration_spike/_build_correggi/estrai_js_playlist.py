# -*- coding: utf-8 -*-
"""Il Playlist Manager non ha l'anteprima brano: dargli l'intero blocco JS
condiviso significava portarsi dietro forma d'onda, cursore, trasporto e
tooltip dei segmenti, che cercano elementi inesistenti (13 riferimenti non
protetti trovati da audit_codice.py). Qui estraggo solo i blocchi che gli
servono davvero."""
import io
import os as _os
import re

_QUI = _os.path.dirname(_os.path.abspath(__file__))
SRC = r"F:\BoxVR Songs Tool\web_migration_spike\genera_real\index.html"
OUT = _os.path.join(_QUI, 'pezzi', 'js_playlist.part')

s = io.open(SRC, encoding='utf-8').read()
i = s.index('<script>') + len('<script>')
j = s.rindex('</script>')
righe = s[i:j].split('\n')

INIZIO = re.compile(r'^  (?:async\s+)?function\s+(\w+)|^  (?:const|let|var)\s+(\w+)')
blocchi, k = [], 0
while k < len(righe):
    m = INIZIO.match(righe[k])
    if not m:
        k += 1
        continue
    nome = m.group(1) or m.group(2)
    c = k
    while c > 0 and righe[c - 1].strip().startswith(('//', '/*', '*')):
        c -= 1
    e = k + 1
    graffe = righe[k].count('{') - righe[k].count('}')
    tonde = righe[k].count('(') - righe[k].count(')')
    while e < len(righe) and (graffe > 0 or tonde > 0):
        graffe += righe[e].count('{') - righe[e].count('}')
        tonde += righe[e].count('(') - righe[e].count(')')
        e += 1
    # Oltre a `window.<nome> = <nome>;` si porta dietro anche la CHIAMATA
    # `<nome>();` che segue subito la definizione: un blocco che si
    # attiva da solo (come collegaTrascinamento) senza quella riga
    # arrivava nella pagina composta ma non veniva mai eseguito.
    while e < len(righe) and (righe[e].strip().startswith('window.' + nome)
                              or righe[e].strip() == nome + '();'):
        e += 1
    blocchi.append((nome, c, e))
    k = e

per_nome = {}
for nome, a, b in blocchi:
    per_nome.setdefault(nome, (a, b))

# solo cio' che serve a una pagina SENZA anteprima brano
VOLUTI = """
api
toPageCoords dopoIlLayout mostraSuggerimento showInfoPopover adattaLarghezzaSuggerimento posizionaInfoPopover hideInfoPopover
fmt
loadAppInfo applyTheme initTheme toggleTheme setLang initLang
temaDiSistema temaCorrente aggiornaInterruttoreTema
renderPatchPill PATCH_CHECK_ICON PATCH_DOWNLOAD_ICON renderBgPattern fitPage
canvasW canvasH extraMax scalaMinimaLeggibile extraCorrente
SOGLIA_IMPILATA SOGLIA_COMPATTA fasciaCanvas impilata impilaDalContenuto
attivaConTastiera
perAttributo
""".split()

pezzi, fuori = [], []
for nome in VOLUTI:
    if nome not in per_nome:
        fuori.append(nome)
        continue
    a, b = per_nome[nome]
    pezzi.append('\n'.join(righe[a:b]))

# il dizionario di traduzione e il raccoglitore di errori, presi dagli stessi
# file usati dalle altre pagine
diz = io.open(_os.path.join(_QUI, 'i18n.js.part'), encoding='utf-8').read()
racc = """  window.__errs = [];
  window.addEventListener('error', (e) => window.__errs.push(String(e.message)));
  window.addEventListener('unhandledrejection',
    (e) => window.__errs.push('promise: ' + (e.reason && e.reason.message || e.reason)));

"""

testo = racc + diz + '\n\n'.join(pezzi) + '\n'

# Il proxy arriva da genera_real e cerca il prefisso "genera_". Dentro la
# Dashboard i metodi di questa pagina sono esposti come "playlist_*"
# (dashboard_real/app.py: playlist_list_playlists -> self._playlist...),
# quindi il prefisso giusto qui e' "playlist_". Senza questa riga la pagina
# funziona da sola ma NON quando ci si arriva dalla Dashboard.
testo = testo.replace("real['genera_' + prop]", "real['playlist_' + prop]")

_os.makedirs(_os.path.dirname(OUT), exist_ok=True)
io.open(OUT, 'w', encoding='utf-8', newline='').write(testo)
print('js_playlist.part: %d blocchi (NON trovati: %s)' % (len(pezzi), fuori or 'nessuno'))
# Un nome richiesto e non trovato NON e' una nota: e' una pagina che a
# runtime morira' su "X is not defined". Prima veniva solo stampato, e
# rigenera.py mostra l'output di un passo soltanto se quel passo fallisce -
# quindi l'avviso non lo leggeva nessuno. Ora fallisce davvero.
if fuori:
    import sys as _sys
    _sys.exit('BLOCCHI RICHIESTI E NON TROVATI in genera_real: %s' % ', '.join(fuori))
