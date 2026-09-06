# Estrae dallo <script> di genera_real i blocchi top-level CONDIVISI, per
# comporre correggi_real senza duplicare a mano (e far divergere) la stessa
# logica. Un blocco top-level comincia con esattamente 2 spazi di rientro e
# finisce alla riga successiva che torna a rientro <= 2 chiudendo.
import io, os, re
import os as _os
# I pezzi (.part) stanno accanto a questo script, non in una cartella
# temporanea: cosi' la catena funziona anche in sessioni diverse.
_QUI = _os.path.dirname(_os.path.abspath(__file__))


SRC = r"F:\BoxVR Songs Tool\web_migration_spike\genera_real\index.html"
OUT = _os.path.join(_QUI, "pezzi") + r"\js_condiviso.part"

s = io.open(SRC, encoding='utf-8').read()
i = s.index('<script>') + len('<script>')
j = s.rindex('</script>')
righe = s[i:j].split('\n')

# indice dei blocchi: (nome, riga_inizio, riga_fine_esclusa)
INIZIO = re.compile(r'^  (?:async\s+)?function\s+(\w+)|^  (?:const|let|var)\s+(\w+)')
blocchi = []
k = 0
while k < len(righe):
    m = INIZIO.match(righe[k])
    if not m:
        k += 1
        continue
    nome = m.group(1) or m.group(2)
    # commento che precede il blocco (righe di commento contigue sopra)
    c = k
    while c > 0 and righe[c - 1].strip().startswith(('//', '/*', '*')):
        c -= 1
    # fine: prima riga successiva con rientro <= 2 che non sia continuazione
    e = k + 1
    graffe = righe[k].count('{') - righe[k].count('}')
    tonde = righe[k].count('(') - righe[k].count(')')
    while e < len(righe) and (graffe > 0 or tonde > 0):
        graffe += righe[e].count('{') - righe[e].count('}')
        tonde += righe[e].count('(') - righe[e].count(')')
        e += 1
    # includi la riga "window.nome = nome;" se segue
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

VOLUTI = """
api audio songs
toPageCoords dopoIlLayout mostraSuggerimento showInfoPopover adattaLarghezzaSuggerimento posizionaInfoPopover hideInfoPopover
fmt
PRESET_DOT_COLOR PRESET_DOT_TITLE presetDaPercentuale aggiornaRigaBrano
apriConfermaRimozione chiudiConfermaRimozione confirmRemove forseChiudiRimozione
canvasW canvasH extraMax scalaMinimaLeggibile extraCorrente
SOGLIA_IMPILATA SOGLIA_COMPATTA fasciaCanvas impilata impilaDalContenuto
toggleMuto bmPlayClick fermaRegistrazioneSeInPausa collegaTrascinamento
attivaConTastiera temaDiSistema temaCorrente aggiornaInterruttoreTema scriviSogliaMarker applicaZoomPista
braniVisibili filtraBrani azzeraRicerca
aggiornaVolumeUi saltoSecondi comandiRiproduzione collegaTastiera
clearList addFiles altezzaListaInteraRighe perAttributo statoBottoneEstendi
renderMiniStructure
zoomFactor zoomLabel viewStartFrac visibleFrac clampView centerViewOn applyZoom
setZoomLevel panWheel renderTimeMarks
setVolume
LEVEL_LABEL WAVE_BURN coloreBanda renderWaveform toggleWaveOption
wavePolygon renderWaveShape renderWaveOverlay curvaMorbida
LEVEL_COLOR_VAR showSegTooltip moveSegTooltip hideSegTooltip
vizAudioCtx beatClickIdx BEAT_CLICK_GAIN beatClickAt resyncBeatClicks pumpBeatClicks
ICON_PLAY ICON_PAUSE ICON_STOP_IDLE ICON_STOP_ACTIVE setTransportIcons
stopMainPlayback renderMainPlayhead _seekFromEvent startSeek
loadAppInfo applyTheme initTheme toggleTheme setLang initLang
renderPatchPill PATCH_CHECK_ICON PATCH_DOWNLOAD_ICON renderBgPattern fitPage
""".split()

os.makedirs(os.path.dirname(OUT), exist_ok=True)
fuori = []
pezzi = []
for nome in VOLUTI:
    if nome not in per_nome:
        fuori.append(nome)
        continue
    a, b = per_nome[nome]
    pezzi.append('\n'.join(righe[a:b]))

io.open(OUT, 'w', encoding='utf-8', newline='').write('\n\n'.join(pezzi) + '\n')
print('blocchi trovati nello script :', len(blocchi))
print('estratti                     :', len(pezzi))
print('NON trovati                  :', fuori)
print('scritti', len(io.open(OUT, encoding='utf-8').read()), 'caratteri in', OUT)

# stesso ragionamento di estrai_js_playlist.py: un blocco richiesto e
# non trovato deve fermare la catena, non finire in una riga di stampa
# che nessuno legge.
_fuori = [n for n in VOLUTI if n not in per_nome] if 'VOLUTI' in dir() else []
if _fuori:
    import sys as _sys
    _sys.exit('BLOCCHI RICHIESTI E NON TROVATI in genera_real: %s'
              % ', '.join(_fuori))
