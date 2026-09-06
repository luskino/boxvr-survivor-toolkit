# -*- coding: utf-8 -*-
"""Verifica che lo script di ogni pagina SIA DAVVERO PARTITO.

PERCHE' ESISTE
--------------
Tutti gli altri controlli sono statici: leggono il file e ragionano sul
testo. Nessuno di loro poteva accorgersi di quello che ha trovato il test su
macchina pulita del 2026-09-03: la pagina Genera aveva quattro copie dello
stesso `let _pendente`, cioe' un SyntaxError di PARSING, e un errore di
parsing non fa fallire una riga - butta via l'INTERO blocco <script>.

Il risultato era il peggiore possibile da diagnosticare: la pagina si
disegnava perfetta (l'HTML e il CSS non c'entrano niente), i pulsanti
sembravano premibili, e non succedeva assolutamente nulla. Nemmeno il
raccoglitore `window.__errs` entrava in funzione, perche' sta dentro lo
stesso blocco morto.

Questo audit fa esattamente le tre domande che ha fatto il tester:

    document.scripts.length     lo script c'e'?
    typeof window.<funzione>    le funzioni esistono a runtime?
    window.__errs               ha raccolto errori?

piu' una quarta: fitPage ha davvero applicato una trasformazione al canvas?

    python audit_runtime.py            tutte le pagine
    python audit_runtime.py correggi   una sola
"""
import os
import sys
import time

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import webview

# Funzioni che DEVONO esistere a runtime su ogni pagina. Sono scelte fra
# quelle in fondo al blocco <script>: se il blocco muore a meta' o non viene
# compilato affatto, queste sono le prime a sparire.
ATTESE = {
    'genera': ['fitPage', 'traduciPagina', 'selectSong', 'setLang', 'apriConfermaRimozione'],
    'correggi': ['fitPage', 'traduciPagina', 'selectSong', 'setLang', 'apriConfermaRimozione'],
    # la Dashboard ora HA il selettore di lingua e l'interruttore del tema
    # (frame scuro 81:5252, in alto a destra), quindi setLang qui ci vuole
    'dashboard': ['fitPage', 'traduciPagina', 'initLang', 'setLang', 'toggleTheme'],
    'playlist': ['traduciPagina', 'setLang'],
}

JS = """
(function () {
  const nomi = %s;
  const mancanti = nomi.filter(n => typeof window[n] !== 'function');
  const page = document.querySelector('.page.genera-fixed, .page.dash-fixed');
  return {
    script: document.scripts.length,
    errs: (window.__errs === undefined) ? null : window.__errs.slice(0, 8),
    mancanti: mancanti,
    trasformato: !!(page && page.style.transform),
    canvas: page ? page.className : '(nessun canvas)'
  };
})()
"""

esiti = []


def controlla(nome, window):
    time.sleep(2.5)
    d = window.evaluate_js(JS % ATTESE[nome])
    problemi = []
    if not d['script']:
        problemi.append('nessun blocco <script> nella pagina')
    if d['errs'] is None:
        problemi.append("window.__errs NON esiste: lo script non e' stato "
                        "compilato (quasi sempre un SyntaxError)")
    elif d['errs']:
        problemi.append('errori raccolti a runtime: %s' % d['errs'])
    if d['mancanti']:
        problemi.append('funzioni assenti a runtime: %s' % ', '.join(d['mancanti']))
    if not d['trasformato']:
        problemi.append('fitPage non ha applicato nessuna scala al canvas (%s)'
                        % d['canvas'])
    esiti.append((nome, problemi))
    window.destroy()


def apri(nome):
    if nome == 'genera':
        sys.path.insert(0, os.path.join(QUI, 'genera_real'))
        import app as a
        a._work_dir = a.build_serving_dir(); a._init_songs()
        return os.path.join(a._work_dir, 'index.html'), a.Api()
    if nome == 'correggi':
        sys.path.insert(0, os.path.join(QUI, 'correggi_real'))
        import app as a
        a._work_dir = a.build_serving_dir(); a._init_songs()
        return os.path.join(a._work_dir, 'index.html'), a.Api()
    if nome == 'playlist':
        sys.path.insert(0, os.path.join(QUI, 'playlist_real'))
        import app as a
        wd = a.build_serving_dir()
        return os.path.join(wd, 'index.html'), a.Api()
    sys.path.insert(0, os.path.join(QUI, 'dashboard_real'))
    import app as a
    wd = a.build_serving_dir()
    a.correggi_app._work_dir = wd; a.correggi_app._init_songs()
    a.genera_app._work_dir = wd; a.genera_app._init_songs()
    return os.path.join(wd, 'index.html'), a.Api()


if __name__ == '__main__':
    nome = sys.argv[1] if len(sys.argv) > 1 else None
    if nome not in ATTESE and nome is not None:
        print('pagina sconosciuta: %s (disponibili: %s)' % (nome, ', '.join(ATTESE)))
        sys.exit(2)
    # una pagina per processo: due finestre pywebview nello stesso processo
    # si contendono il ciclo degli eventi
    if nome is None:
        import subprocess
        uscita = 0
        for n in ATTESE:
            r = subprocess.run([sys.executable, __file__, n], cwd=QUI)
            uscita |= r.returncode
        sys.exit(uscita)

    idx, api = apri(nome)
    w = webview.create_window('runtime', idx, js_api=api, width=1280, height=800)
    webview.start(lambda win: controlla(nome, win), w)

    print('===== SCRIPT VIVO: %s =====' % nome.upper(), flush=True)
    n, problemi = esiti[0]
    if not problemi:
        print('  ok    lo script gira, le funzioni esistono, nessun errore', flush=True)
        sys.exit(0)
    for p in problemi:
        print('  PROBLEMA  %s' % p, flush=True)
    sys.exit(1)
