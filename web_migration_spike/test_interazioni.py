# -*- coding: utf-8 -*-
"""Controlli di COMPORTAMENTO sulla pagina viva.

Gli altri audit misurano com'e' fatta la pagina; questo verifica cosa fa
quando la si usa. Tutte le prove qui dentro nascono da difetti veri
segnalati dall'utente, e quasi tutte da difetti **rientrati piu' volte**:

  stato "Rimuovi"   e' regredito due volte. Prima si chiudeva solo uscendo
                    dalla riga intera; poi il `mouseleave` sulla pillola non
                    scattava, perche' la pillola compare gia' sotto un
                    puntatore fermo e il browser non registra mai l'ingresso.
                    Qui si simulano i movimenti veri del mouse.
  allineamento      allargando il canvas con --extra alcuni gruppi della
                    barra dell'anteprima scorrevano e altri no. La prova
                    non guarda le coordinate assolute (cambiano per
                    progetto) ma l'INVARIANTE: tutti quelli ancorati a
                    destra devono spostarsi della stessa quantita'.
  note di sviluppo  testi per chi sviluppa, mai per chi usa il programma.

    python test_interazioni.py correggi
    python test_interazioni.py genera
"""
import os
import sys
import time

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import webview

PAGINA = sys.argv[1] if len(sys.argv) > 1 else 'correggi'
esiti = []

JS_RIMOZIONE = r"""
(function () {
  const riga = document.querySelector('.song-row');
  if (!riga) return {saltato: 'nessuna riga brano nell elenco'};
  const x = riga.querySelector('.song-remove-x');
  const barra = riga.querySelector('.remove-confirm-bar');
  if (!x || !barra) return {saltato: 'riga senza comando di rimozione'};

  function muovi(el, tipo, cx, cy) {
    el.dispatchEvent(new MouseEvent(tipo, {bubbles: tipo === 'mousemove',
                                           clientX: cx, clientY: cy}));
  }
  const rx = x.getBoundingClientRect();
  muovi(x, 'mouseenter', rx.left + rx.width / 2, rx.top + rx.height / 2);
  const dopoIngresso = riga.classList.contains('confirm-remove');

  // 1. resta aperto muovendosi SOPRA la pillola
  const rb = barra.getBoundingClientRect();
  muovi(riga, 'mousemove', rb.left + rb.width / 2, rb.top + rb.height / 2);
  const restaSullaPillola = riga.classList.contains('confirm-remove');

  // 2. si chiude muovendosi al CENTRO della riga, lontano dalla pillola
  const rr = riga.getBoundingClientRect();
  muovi(riga, 'mousemove', rr.left + rr.width / 2, rr.top + rr.height / 2);
  const chiusoAlCentro = !riga.classList.contains('confirm-remove');

  return {dopoIngresso: dopoIngresso,
          restaSullaPillola: restaSullaPillola,
          chiusoAlCentro: chiusoAlCentro};
})()
"""

JS_ALLINEAMENTO = r"""
(function () {
  const page = document.querySelector('.page.genera-fixed');
  if (!page) return {saltato: 'pagina senza canvas genera-fixed'};
  const card = document.querySelector('.preview-card');
  if (!card) return {saltato: 'nessuna card di anteprima'};

  const SEL = ['.pv-bpm', '.pv-engine', '.pv-volume', '.pv-zoom', '.pv-toggles'];
  function lefts() {
    const r = page.getBoundingClientRect();
    const s = r.width / (1920 + (window.__extraCanvas || 0));
    const out = {};
    SEL.forEach(function (q) {
      const e = document.querySelector(q);
      out[q] = e ? (e.getBoundingClientRect().left - r.left) / s : null;
    });
    return out;
  }
  const salvato = page.style.getPropertyValue('--extra');
  page.style.setProperty('--extra', '0px');
  window.__extraCanvas = 0;
  const a = lefts();
  page.style.setProperty('--extra', '400px');
  window.__extraCanvas = 400;
  const b = lefts();
  page.style.setProperty('--extra', salvato || '0px');
  window.__extraCanvas = parseInt(salvato) || 0;

  const spostamenti = {};
  SEL.forEach(function (q) {
    spostamenti[q] = (a[q] === null || b[q] === null) ? null
                     : Math.round(b[q] - a[q]);
  });
  return {spostamenti: spostamenti};
})()
"""

JS_VARIE = r"""
(function () {
  const dev = Array.prototype.map.call(
      document.querySelectorAll('.nota-dev'),
      e => ({testo: (e.textContent || '').trim().slice(0, 30),
             visibile: e.offsetParent !== null}));
  const pillole = Array.prototype.map.call(
      document.querySelectorAll('.pill-row .pill:not(:has(.coda))'),
      e => Math.round(e.getBoundingClientRect().width));
  const page = document.querySelector('.page.genera-fixed, .page.dash-fixed');
  return {
    dev: dev,
    pillole: pillole,
    sfondoBody: getComputedStyle(document.body).backgroundColor,
    sfondoCanvas: page ? getComputedStyle(page).backgroundColor : null
  };
})()
"""


def controlla(window):
    time.sleep(2.5)

    r = window.evaluate_js(JS_RIMOZIONE)
    if r.get('saltato'):
        esiti.append((None, 'stato "Rimuovi"', r['saltato']))
    else:
        esiti.append((r['dopoIngresso'], 'si apre passando sulla X', ''))
        esiti.append((r['restaSullaPillola'], 'resta aperto sopra la pillola', ''))
        esiti.append((r['chiusoAlCentro'],
                      'si CHIUDE al centro della riga, lontano dalla pillola',
                      'e\' il difetto segnalato: restava rosa'))

    a = window.evaluate_js(JS_ALLINEAMENTO)
    if a.get('saltato'):
        esiti.append((None, 'allineamento barra anteprima', a['saltato']))
    else:
        sp = a['spostamenti']
        presenti = {k: v for k, v in sp.items() if v is not None}
        tutti_uguali = len(set(presenti.values())) == 1 and 400 in set(presenti.values())
        esiti.append((tutti_uguali,
                      'i gruppi ancorati a destra si spostano tutti insieme',
                      ' '.join('%s=%s' % (k, v) for k, v in sp.items())))

    v = window.evaluate_js(JS_VARIE)
    visibili = [d['testo'] for d in v['dev'] if d['visibile']]
    esiti.append((not visibili, 'nessuna nota di sviluppo visibile',
                  'visibili: %s' % visibili if visibili else
                  '%d note presenti nel markup, tutte nascoste' % len(v['dev'])))
    if v['pillole']:
        esiti.append((len(set(v['pillole'])) == 1,
                      'le pillole delle fasi hanno tutte la stessa larghezza',
                      'larghezze: %s' % v['pillole']))
    if v['sfondoCanvas'] and 'dash' in (PAGINA or ''):
        esiti.append((v['sfondoBody'] == v['sfondoCanvas'],
                      'la tela dietro il canvas ha lo stesso colore del canvas',
                      'body %s vs canvas %s' % (v['sfondoBody'], v['sfondoCanvas'])))
    window.destroy()


def apri(nome):
    if nome == 'dashboard':
        sys.path.insert(0, os.path.join(QUI, 'dashboard_real'))
        import app as a
        wd = a.build_serving_dir()
        a.correggi_app._work_dir = wd; a.correggi_app._init_songs()
        a.genera_app._work_dir = wd; a.genera_app._init_songs()
        return os.path.join(wd, 'index.html'), a.Api()
    sys.path.insert(0, os.path.join(QUI, nome + '_real'))
    import app as a
    a._work_dir = a.build_serving_dir(); a._init_songs()
    return os.path.join(a._work_dir, 'index.html'), a.Api()


if __name__ == '__main__':
    idx, api = apri(PAGINA)
    w = webview.create_window('interazioni', idx, js_api=api, width=1280, height=800)
    webview.start(controlla, w)

    print('===== INTERAZIONI: %s =====' % PAGINA.upper())
    rossi = 0
    for ok, nome, dettaglio in esiti:
        if ok is None:
            print('  saltato  %s  (%s)' % (nome, dettaglio))
            continue
        print(('  ok      ' if ok else '  FALLITO ') + nome)
        if dettaglio:
            print('            %s' % dettaglio)
        if not ok:
            rossi += 1
    print('  %d problemi' % rossi)
    sys.exit(1 if rossi else 0)
