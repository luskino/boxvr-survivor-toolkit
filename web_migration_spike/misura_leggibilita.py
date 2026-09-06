# -*- coding: utf-8 -*-
"""Misura QUANTO sono davvero grandi i testi sullo schermo dell'utente.

Il canvas e' 1920x1080 CSS scalato con transform (fitPage). La dimensione
PERCEPITA di un testo non e' quindi il suo font-size, ma:

    px fisici = font-size * scala_fitPage * devicePixelRatio

Questo script apre una pagina vera, legge la scala reale e stampa la
dimensione fisica di ogni testo, ordinata dal piu' piccolo. Serve a smettere
di ragionare sui font-size del CSS, che non sono cio' che l'utente vede.
"""
import os
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))

import webview

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PAGINA = sys.argv[1] if len(sys.argv) > 1 else 'correggi'

JS = r"""
(function () {
  var page = document.querySelector('.page.genera-fixed, .page.dash-fixed');
  var s = 1;
  if (page) { var r = page.getBoundingClientRect(); s = r.width / 1920; }
  var dpr = window.devicePixelRatio || 1;
  var out = {
    innerW: window.innerWidth, innerH: window.innerHeight,
    screenW: window.screen.width, screenH: window.screen.height,
    dpr: dpr, scala: s, fisico: s * dpr, testi: []
  };
  var visti = {};
  document.querySelectorAll('body *').forEach(function (el) {
    if (el.children.length && !Array.prototype.some.call(el.childNodes,
        function (n) { return n.nodeType === 3 && n.textContent.trim(); })) return;
    var t = (el.textContent || '').trim();
    if (!t) return;
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    var fs = parseFloat(cs.fontSize);
    var chiave = fs + '|' + cs.color + '|' + (el.className || el.tagName);
    if (visti[chiave]) return;
    visti[chiave] = 1;
    out.testi.push({
      fs: fs, peso: cs.fontWeight, colore: cs.color,
      sfondo: cs.backgroundColor,
      cls: (typeof el.className === 'string' ? el.className : '') || el.tagName,
      txt: t.slice(0, 34).replace(/\s+/g, ' ')
    });
  });
  out.testi.sort(function (a, b) { return a.fs - b.fs; });
  return out;
})()
"""


def misura(window):
    import time
    time.sleep(2.5)
    d = window.evaluate_js(JS)
    print('===== %s =====' % PAGINA.upper(), flush=True)
    print('viewport CSS   : %sx%s' % (d['innerW'], d['innerH']), flush=True)
    print('schermo CSS    : %sx%s' % (d['screenW'], d['screenH']), flush=True)
    print('devicePixelRatio: %.3f' % d['dpr'], flush=True)
    print('scala fitPage  : %.4f' % d['scala'], flush=True)
    print('fattore fisico : %.4f  (font-size * questo = px veri a schermo)'
          % d['fisico'], flush=True)
    print(flush=True)
    print('%-7s %-7s %-8s %-26s %s' % ('css', 'FISICI', 'peso', 'classe', 'testo'), flush=True)
    for t in d['testi'][:40]:
        fisici = t['fs'] * d['fisico']
        segno = '  <-- TROPPO PICCOLO' if fisici < 11 else ''
        print('%-7.1f %-7.1f %-8s %-26s %s%s'
              % (t['fs'], fisici, t['peso'], t['cls'][:26], t['txt'], segno), flush=True)
    window.destroy()


if PAGINA == 'correggi':
    sys.path.insert(0, os.path.join(QUI, 'correggi_real'))
    import app as a
    a._work_dir = a.build_serving_dir(); a._init_songs()
    idx = os.path.join(a._work_dir, 'index.html')
    api = a.Api()
else:
    sys.path.insert(0, os.path.join(QUI, 'dashboard_real'))
    import app as a
    wd = a.build_serving_dir()
    a.correggi_app._work_dir = wd; a.correggi_app._init_songs()
    idx = os.path.join(wd, 'index.html')
    api = a.Api()

w = webview.create_window("misura", idx, js_api=api, width=1920, height=1080)
webview.start(misura, w)
