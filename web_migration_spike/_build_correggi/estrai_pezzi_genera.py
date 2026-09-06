# Estrae da genera_real/index.html i blocchi riusabili per correggi_real,
# per non riscriverli a mano (e non farli divergere).
import io, os, re
import os as _os
# I pezzi (.part) stanno accanto a questo script, non in una cartella
# temporanea: cosi' la catena funziona anche in sessioni diverse.
_QUI = _os.path.dirname(_os.path.abspath(__file__))


SRC = r"F:\BoxVR Songs Tool\web_migration_spike\genera_real\index.html"
OUT = _os.path.join(_QUI, "pezzi") + r""

s = io.open(SRC, encoding='utf-8').read()
os.makedirs(OUT, exist_ok=True)


def fra(inizio, fine, nome, dal=0):
    i = s.index(inizio, dal)
    j = s.index(fine, i)
    blocco = s[i:j + len(fine)]
    io.open(os.path.join(OUT, nome), 'w', encoding='utf-8', newline='').write(blocco)
    print('%-22s %6d caratteri' % (nome, len(blocco)))
    return blocco


# 1. tutto il foglio di stile (verra' riusato integralmente: le regole dei
#    componenti solo-Genera restano inerti in Correggi, ma tenerle evita di
#    far divergere due copie dello stesso CSS)
fra('<style>', '</style>', 'style.css.part')

# 2. testata della pagina (popover info + header)
fra('<div class="info-popover" id="info-popover">', '</header>', 'header.html.part')

# 3. card "Anteprima brano" completa, dal titolo del blocco alla chiusura
fra('      <h3 class="block-title">Anteprima brano</h3>', '    </main>', 'anteprima.html.part')

# 4. pannello brani a destra
fra('    <aside class="song-panel" id="song-panel">', '    </aside>', 'pannello.html.part')

print('\nfatto in', OUT)
