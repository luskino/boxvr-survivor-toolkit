import io
import os as _os
# I pezzi (.part) stanno accanto a questo script, non in una cartella
# temporanea: cosi' la catena funziona anche in sessioni diverse.
_QUI = _os.path.dirname(_os.path.abspath(__file__))


RACC = """  // Raccoglitore di errori: senza questo un errore JS (o una promise
  // rifiutata, il caso piu' frequente qui perche' quasi tutte le chiamate
  // all'API sono async) sparisce in silenzio e la pagina resta a meta'.
  window.__errs = [];
  window.addEventListener('error', (e) => window.__errs.push(String(e.message)));
  window.addEventListener('unhandledrejection',
    (e) => window.__errs.push('promise: ' + (e.reason && e.reason.message || e.reason)));

"""

FILE = [
    r"F:\BoxVR Songs Tool\web_migration_spike\genera_real\index.html",
    _os.path.join(_QUI, "pezzi") + r"\js_condiviso.part",
    r"F:\BoxVR Songs Tool\web_migration_spike\dashboard_real\index.html",
]

for p in FILE:
    s = io.open(p, encoding='utf-8').read()
    if 'window.__errs = []' in s:
        print('gia presente:', p)
        continue
    if p.endswith('.part'):
        s = RACC + s
    else:
        i = s.index('<script>') + len('<script>')
        s = s[:i] + '\n' + RACC + s[i:]
    io.open(p, 'w', encoding='utf-8', newline='').write(s)
    print('aggiunto a', p)
