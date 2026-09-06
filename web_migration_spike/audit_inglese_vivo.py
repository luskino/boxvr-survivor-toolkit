# BoxVR Survivor Toolkit - Copyright (C) 2026 Luca Giuseppe Buttacavoli
#
# Questo programma e' software libero: puoi ridistribuirlo e/o modificarlo
# secondo i termini della GNU General Public License come pubblicata dalla
# Free Software Foundation, versione 3 o (a tua scelta) successiva.
#
# E' distribuito nella speranza che sia utile, ma SENZA ALCUNA GARANZIA;
# senza neppure la garanzia implicita di COMMERCIABILITA' o IDONEITA' PER UNO
# SCOPO PARTICOLARE. Vedi la GNU General Public License per i dettagli.
#
# Dovresti aver ricevuto una copia della licenza insieme a questo programma
# (file LICENSE). Altrimenti: <https://www.gnu.org/licenses/>.

"""Con la lingua su inglese, che cosa resta scritto in italiano SULLO SCHERMO?

Gli altri due controlli guardano i sorgenti: uno il markup, l'altro le
stringhe scritte dal codice. Nessuno dei due sa dire se il testo che
l'utente VEDE e' tradotto, perche' molti testi nascono componendo pezzi a
runtime ("1 blocco ritmico, 93 s marcati piu' 2 accenti isolati: ...") e
nel dizionario ci sono i pezzi, non la frase intera.

Qui si apre la pagina vera, si passa all'inglese, si mettono i pannelli
negli stati che producono quei testi, e si legge quello che c'e' scritto.

    python audit_inglese_vivo.py [pagina]
"""
import json
import os
import re
import sys
import time

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import webview                                                  # noqa: E402

PAGINA = (sys.argv[1] if len(sys.argv) > 1 else 'genera')
sys.path.insert(0, os.path.join(QUI, PAGINA + '_real'))
import app as pagina_app                                        # noqa: E402

# Parole che in inglese non esistono con quella grafia. Poche e sicure:
# meglio non segnalare nulla che riempire di falsi allarmi.
ITALIANO = re.compile(
    r'\b(brano|brani|colpi|marcat[oi]|ignorat[oi]|analisi|in corso|'
    r'blocc[oh][io]?|accent[oi]|ritmic[oi]|cadenza|nessun[ao]?|'
    r'ancora|perché|resto|automatic[oa]|imiterà|userà|'
    r'aggiunt[oi]|generat[oi]|piazzat[oi]|registrat[oi]|riuscita|'
    r'seleziona|scegli|rimuovi|muto|spazio|barra|ricerca|'
    r'sezioni|consecutive|totali|playlist scritta|non rilevata)\b',
    re.IGNORECASE)

LEGGI_SCHERMO = """
(function () {
  const fuori = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const t = (n.nodeValue || '').replace(/\\s+/g, ' ').trim();
    if (t.length < 3) continue;
    const el = n.parentElement;
    if (!el || el.closest('script, style')) continue;
    // solo cio' che si vede davvero
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    fuori.push(t);
  }
  for (const el of document.querySelectorAll('[title], [placeholder]')) {
    for (const a of ['title', 'placeholder']) {
      const v = el.getAttribute(a);
      if (v && v.trim().length > 2) fuori.push(v.trim());
    }
  }
  return fuori;
})()
"""


def leggi(window):
    return window.evaluate_js(LEGGI_SCHERMO) or []


def lavora(window):
    time.sleep(3)
    try:
        window.evaluate_js('loadList()')
    except Exception:
        pass
    time.sleep(3)
    window.evaluate_js("setLang('en')")
    time.sleep(2)

    visti = set()
    for testo in leggi(window):
        visti.add(testo)

    # stati che producono testi composti a runtime
    STATI = [
        "try { applicaStatoAnalisi('pending'); } catch (e) {}",
        "try { applicaStatoAnalisi('error'); } catch (e) {}",
        ("try { sidecarState = {markers: [], mode: 'extend', min_gap_ms: 170,"
         " scartati: 4, copertura: {analisi_pronta: true, blocchi: 1,"
         " accenti: 2, secondi: 93, marker: 40, minimo: 45, minimo_marker: 8,"
         " intervalli: [[1,90]], accenti_intervalli: [[120,120]],"
         " sufficiente: true}}; renderSidecarUi(); } catch (e) {}"),
        ("try { sidecarState.copertura.sufficiente = false;"
         " sidecarState.copertura.secondi = 14; renderSidecarUi(); } catch (e) {}"),
        ("try { sidecarState.copertura.blocchi = 0;"
         " renderSidecarUi(); } catch (e) {}"),
    ]
    for js in STATI:
        try:
            window.evaluate_js(js)
        except Exception:
            continue
        time.sleep(0.8)
        for testo in leggi(window):
            visti.add(testo)

    # Un percorso di cartella non e' un testo da tradurre: e' il nome vero
    # di una cartella sul disco dell'utente, e tradurlo la renderebbe
    # irreperibile.
    def e_percorso(t):
        return ('/' in t or chr(92) in t) and ' ' in t and not t.endswith('.')

    sospetti = sorted(t for t in visti
                      if ITALIANO.search(t) and not e_percorso(t))
    print('===== INGLESE VIVO: %s =====' % PAGINA.upper())
    print('testi letti sullo schermo:', len(visti))
    if sospetti:
        print('ancora in italiano (%d):' % len(sospetti))
        for t in sospetti:
            print('   %s' % t[:110])
    else:
        print('nessun testo italiano visibile con la lingua su inglese')
    print()
    print('ESITO:', 'inglese pulito' if not sospetti else 'RESTA ITALIANO')
    window.destroy()
    sys.exit(0 if not sospetti else 1)


def main():
    pagina_app._work_dir = pagina_app.build_serving_dir()
    if hasattr(pagina_app, '_init_songs'):
        pagina_app._init_songs()
    w = webview.create_window(
        'inglese vivo', os.path.join(pagina_app._work_dir, 'index.html'),
        js_api=pagina_app.Api(), width=1500, height=950)
    webview.start(lavora, w)


if __name__ == '__main__':
    main()
