# -*- coding: utf-8 -*-
"""Elenca il testo che resta in italiano passando all'inglese.

Non e' un controllo statico sul dizionario: apre la pagina, passa a EN e
guarda che cosa NON e' cambiato. E' l'unico modo di vedere anche i testi
costruiti dal codice a runtime, che in un file non compaiono mai.

Alcune cose non vanno tradotte e non sono difetti: il nome del prodotto, il
numero di versione, i nomi di brani e artisti, i numeri. Vengono filtrate
qui sotto, con il criterio scritto accanto: un elenco pieno di falsi
allarmi non lo guarda nessuno.

    python audit_traduzione.py correggi|genera|dashboard|playlist
"""
import os
import re
import sys
import time

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import webview

PAGINA = sys.argv[1] if len(sys.argv) > 1 else 'correggi'

# Cose che restano in italiano APPOSTA.
NON_TRADURRE = re.compile(
    r'^(?:'
    r'BoxVR|BOXVR|BoxVR Survivor Toolkit|Ver [\d.]+|'   # nome e versione
    r'[\d.,:/%\s\-–—]+|'                                # solo numeri e simboli
    r'IT|EN|BPM|\d+ BPM|'                               # sigle
    r'[A-Za-z]{1,2}|'                                   # sigle di una-due lettere
    r'Ver [\d.]+\s*[—\-]?|'                          # "Ver 1.28.1 —"
    r'[A-Za-z]:[\\/].*|'                                 # percorsi su disco
    r'patched|original|unknown|missing'                 # stati della patch, gia' in inglese
    r')$')

# Simboli, frecce e icone testuali: non c'e' niente da tradurre, e in lista
# facevano solo rumore (✕ 🔊 🔍 ›).
SOLO_SIMBOLI = re.compile(r'^[^\w]+$', re.UNICODE)


def comincia_con_valore(t, valori):
    """"Punches only - 54.3%" e' gia' tradotto: e' un nome dal dizionario
    piu' un numero. Vale per i tooltip, dove la stringa e' per forza
    composta in un attributo e non puo' essere una voce a se'."""
    for v in valori:
        if v and t.startswith(v) and len(t) > len(v):
            return True
    return False


def composto_con_numero(t, valori):
    """"8 tracks in the list" e' gia' tradotto: e' un numero piu' una coda
    che sta nel dizionario. Senza questo controllo risultava non tradotto a
    ogni giro."""
    m = re.match(r'^\d+\s+(.+)$', t)
    return bool(m and m.group(1) in valori)

# I contenuti reali (nomi di brano e artista) arrivano dai file dell'utente:
# non sono interfaccia e non si traducono.
def da_contenuto(t, nomi):
    return any(t == n or t in n for n in nomi if n)


JS = """
(function () {
  setLang('en');
  const nomi = Array.prototype.map.call(
      document.querySelectorAll('.track-name, .artist, .song-row .row-top span'),
      e => (e.textContent || '').trim())
    .concat(Array.prototype.map.call(
      // nomi di playlist e di brano dentro il Playlist Manager: sono
      // contenuto dell'utente, non interfaccia
      document.querySelectorAll('.pl-titolo, #playlist-list .track-name, #pl-nome'),
      e => (e.textContent || '').trim()));
  // Tre casi diversi, e il primo giro li aveva confusi tutti:
  //  - il testo e' un VALORE del dizionario  -> tradotto, tutto a posto;
  //  - il testo e' una CHIAVE del dizionario -> la voce c'e' ma non e'
  //    stata applicata: e' un difetto del meccanismo, non una voce mancante;
  //  - ne' l'uno ne' l'altra                 -> manca dal dizionario.
  const valori = new Set(Object.values(TRAD));
  const fuori = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = w.nextNode())) {
    const t = (n.nodeValue || '').trim();
    if (!t) continue;
    if (n.parentElement && n.parentElement.closest('script, style')) continue;
    // testo nascosto: non lo legge nessuno, e teneva in lista le note di
    // sviluppo (che restano nel markup apposta, spente)
    if (n.parentElement && n.parentElement.offsetParent === null) continue;
    if (valori.has(t)) continue;
    const haVoce = TRAD[t] || _TRAD_NORM[t.replace(/\\s+/g, ' ')];
    fuori.push((haVoce ? '[VOCE PRESENTE, NON APPLICATA] ' : '') + t);
  }
  const attributi = [];
  document.querySelectorAll('[title]').forEach(function (e) {
    const t = e.getAttribute('title').trim();
    if (t && !valori.has(t)) attributi.push((TRAD[t] ? '[NON APPLICATA] ' : '') + t);
  });
  return {testi: Array.from(new Set(fuori)),
          titoli: Array.from(new Set(attributi)),
          nomi: Array.from(new Set(nomi)),
          valori: Array.from(valori)};
})()
"""

esiti = {}


def controlla(window):
    time.sleep(2.5)
    esiti.update(window.evaluate_js(JS))
    window.destroy()


def apri(nome):
    if nome == 'dashboard':
        sys.path.insert(0, os.path.join(QUI, 'dashboard_real'))
        import app as a
        wd = a.build_serving_dir()
        a.correggi_app._work_dir = wd; a.correggi_app._init_songs()
        a.genera_app._work_dir = wd; a.genera_app._init_songs()
        return os.path.join(wd, 'index.html'), a.Api()
    if nome == 'playlist':
        sys.path.insert(0, os.path.join(QUI, 'playlist_real'))
        import app as a
        return os.path.join(a.build_serving_dir(), 'index.html'), a.Api()
    sys.path.insert(0, os.path.join(QUI, nome + '_real'))
    import app as a
    a._work_dir = a.build_serving_dir(); a._init_songs()
    return os.path.join(a._work_dir, 'index.html'), a.Api()


if __name__ == '__main__':
    idx, api = apri(PAGINA)
    w = webview.create_window('traduzione', idx, js_api=api, width=1280, height=800)
    webview.start(controlla, w)

    nomi = esiti.get('nomi') or []
    valori = set(esiti.get('valori') or [])
    def utile(t):
        pulito = t.replace('[VOCE PRESENTE, NON APPLICATA] ', '')
        pulito = pulito.replace('[NON APPLICATA] ', '')
        return (not NON_TRADURRE.match(pulito)
                and not SOLO_SIMBOLI.match(pulito)
                and not composto_con_numero(pulito, valori)
                and not comincia_con_valore(pulito, valori)
                and not da_contenuto(pulito, nomi))

    testi = [t for t in esiti.get('testi', []) if utile(t)]
    titoli = [t for t in esiti.get('titoli', []) if utile(t)]

    print('===== NON TRADOTTO: %s =====' % PAGINA.upper())
    print('-- testi visibili (%d) --' % len(testi))
    for t in sorted(testi, key=len, reverse=True):
        print('   %s' % (t[:110].replace('\n', ' ')))
    print('-- tooltip (%d) --' % len(titoli))
    for t in sorted(titoli, key=len, reverse=True):
        print('   %s' % (t[:110].replace('\n', ' ')))
    print('  totale da valutare: %d' % (len(testi) + len(titoli)))
    sys.exit(0)
