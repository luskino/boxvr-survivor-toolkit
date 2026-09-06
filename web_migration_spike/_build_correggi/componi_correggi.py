# Compone correggi_real/index.html dai pezzi: CSS + HTML condivisi presi
# TALE E QUALE da genera_real (stessi componenti, stesse coordinate - il
# frame Figma 1:7 conferma che header, anteprima brano e pannello brani sono
# identici), piu' il blocco Toolkit e il JS specifici di Correggi.
import io, os, re
import os as _os
# I pezzi (.part) stanno accanto a questo script, non in una cartella
# temporanea: cosi' la catena funziona anche in sessioni diverse.
_QUI = _os.path.dirname(_os.path.abspath(__file__))


SP = _QUI
PZ = os.path.join(SP, 'pezzi')
GEN = r"F:\BoxVR Songs Tool\web_migration_spike\genera_real\index.html"
OUT = r"F:\BoxVR Songs Tool\web_migration_spike\correggi_real\index.html"


def leggi(p):
    return io.open(p, encoding='utf-8').read()


style = leggi(os.path.join(PZ, 'style.css.part'))          # <style>...</style>
header = leggi(os.path.join(PZ, 'header.html.part'))
anteprima = leggi(os.path.join(PZ, 'anteprima.html.part'))
pannello = leggi(os.path.join(PZ, 'pannello.html.part'))
js_cond = leggi(os.path.join(PZ, 'js_condiviso.part'))
tk_html = leggi(os.path.join(SP, 'correggi_toolkit.html.part'))
tk_css = leggi(os.path.join(SP, 'correggi_toolkit.css.part'))
js_spec = leggi(os.path.join(SP, 'correggi_specifico.js.part'))

# --- CSS: aggiungo il blocco Correggi dentro <style> ---
style = style.replace('</style>', tk_css + '</style>')

# --- Anteprima: in Correggi NON ci sono il selettore motore (Veloce/Precisa)
#     ne' la modifica del BPM: il frame 1:7 non li contiene (li ha solo
#     Genera, dove il BPM viene stimato da zero dall'mp3). Tolgo quei pezzi.
i = anteprima.index('        <div class="pv-engine">')
j = anteprima.index('</div>', anteprima.index('</div>', anteprima.index('<div class="segmented small"', i)) + 6) + 6
anteprima = anteprima[:i] + anteprima[j:].lstrip('\n')
# bottoni matita / ricerca BPM e riga di modifica
for pat in [r'<button class="bpm-edit-btn".*?</button>',
            r'<button class="bpm-search-btn".*?</button>',
            r'<span class="bpm-edit-row".*?</span>\s*</span>']:
    anteprima = re.sub(pat, '', anteprima, flags=re.S)
# richiudo la .bpm-control rimasta aperta dalla terza sostituzione
anteprima = anteprima.replace('<span class="bpm-value" id="p-bpm">—</span>',
                              '<span class="bpm-value" id="p-bpm">—</span></span>')
# il pannello dei marker non esiste in Correggi
anteprima = anteprima.replace('onclick="retryCurrentSong()"', 'onclick="loadList()"')

# --- pannello brani: il testo dello stato vuoto e' quello di Correggi ---
pannello = pannello.replace(
    'Trascina qui le cartelle o i file per generare un workout o aggiungi un percorso.',
    'Trascina qui le cartelle o i file da correggere o aggiungi un percorso.')

TESTA = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>BoxVR Survivor Toolkit - Correggi</title>
<link rel="stylesheet" href="styles.css">
"""

SEZIONE = """
  <div class="section-title correggi">
    <!-- icona REALE "Big Icons / Icona Correggi" (4:73, 45x45) -->
    <span class="icon"><img src="assets/icons/big_icona_correggi.svg" alt="" width="45" height="45"></span>
    <h2>Correggi Workout esistenti</h2>
  </div>
  <!-- Copy REALE del wireframe, preso dal nodo Figma 1:7 (testo 18:5893) -->
  <p class="section-desc">
    Questa parte del tool migliora i livelli di intensità che BoxVR ha già assegnato a un workout esistente:
    analizza l'audio reale, li confronta con l'originale e ti propone una versione più coerente col ritmo del
    brano. Puoi scegliere quanti eventi trattare come pugni puri, quanto margine di sicurezza tenere nelle
    correzioni, ascoltare il risultato con un click a tempo, e decidere se salvare solo un report o sostituire
    i file (con backup automatico).
    <b>Tieni presente: agisce solo dove BoxVR ha già creato dei segmenti — non riempie i vuoti dove il gioco
    non ha messo nulla. Per quello serve Genera.</b>
  </p>
  <p class="not-wired-note nota-dev" style="margin:4px 0 0; max-width:1301px">
    (nota dev) Corregge con <code>boxvr_fixer</code>. Il file corretto viene
    scritto fuori dalla libreria; ci finisce solo passando da "Installa in
    BoxVR", che chiede conferma e fa il backup.
  </p>
"""

pagina = (TESTA + style + """
</head>
<body>
<div class="page genera-fixed">
  <div class="bg-pattern" id="bg-pattern"></div>

""" + header + "\n" + SEZIONE + """
  <div class="genera-layout">
""" + pannello + """

    <main>
""" + anteprima + """
    </main>
""" + tk_html + """
  </div>
</div>
<script>
""" + js_cond + js_spec + """
</script>
</body>
</html>
""")

io.open(OUT, 'w', encoding='utf-8', newline='').write(pagina)
print('scritto', OUT, len(pagina), 'caratteri')
