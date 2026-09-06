# -*- coding: utf-8 -*-
"""Confronta il tema scuro RESO con quello DISEGNATO su Figma.

I valori attesi sono misurati sui frame del tema scuro (81:5252, 81:5370,
81:5542, 81:5659, 81:5772, 81:5885, 81:6033), scaricati in
`UI Figma dark/`. Non sono scelte mie: sono ciò che c'è nel disegno.

Serve perché "allineato al tema scuro" a occhio non è verificabile: due blu
molto scuri si somigliano tutti, e la differenza fra #0B0E17 e #1A1A2E si
vede solo mettendo i numeri uno accanto all'altro.

    python audit_tema_scuro.py correggi|genera|dashboard
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

# superficie -> (selettore, proprieta', valore atteso dal Figma)
ATTESI = {
    'correggi': [
        ('sfondo pagina',      'body',              'backgroundColor', '#1A1A2E'),
        ('card',               '.preview-card',     'backgroundColor', '#2A2A3E'),
        ('pannello brani',     '.song-panel',       'backgroundColor', '#2A2A3E'),
        ('riga brano',         '.song-row:not(.selected)',   'backgroundColor', '#29293D'),
        ('testo intestazione', '.section-title',    'color',           '#E6E6ED'),
        ('campo di testo',     '.text-input',       'backgroundColor', '#2A2A3E'),
        ('log (incassato)',    '.log-section pre',  'backgroundColor', '#1A1A2E'),
        ('pillola Silenzio',   '.pill.silenzio',    'backgroundColor', '#33334C'),
        ('testo su Silenzio',  '.pill.silenzio',    'color',           '#E6E6ED'),
        ('pillola Leggero',    '.pill.leggero',     'backgroundColor', '#549CDE'),
        ('pillola Solo pugni', '.pill.pugni',       'backgroundColor', '#F0546B'),
    ],
    'genera': [
        ('sfondo pagina',      'body',              'backgroundColor', '#1A1A2E'),
        ('card',               '.preview-card',     'backgroundColor', '#2A2A3E'),
        ('pannello brani',     '.song-panel',       'backgroundColor', '#2A2A3E'),
        ('riga brano',         '.song-row:not(.selected)',   'backgroundColor', '#29293D'),
        ('testo intestazione', '.section-title',    'color',           '#E6E6ED'),
        ('campo di testo',     '.text-input',       'backgroundColor', '#2A2A3E'),
        ('log (incassato)',    '.log-section pre',  'backgroundColor', '#1A1A2E'),
        ('pillola Silenzio',   '.pill.silenzio',    'backgroundColor', '#33334C'),
        ('testo su Silenzio',  '.pill.silenzio',    'color',           '#E6E6ED'),
    ],
    'dashboard': [
        ('sfondo pagina',      'body',              'backgroundColor', '#05050A'),
        ('canvas',             '.page.dash-fixed',  'backgroundColor', '#05050A'),
        ('modale',             '.dash-modal',       'backgroundColor', '#2A2A3E'),
    ],
}

JS = """
(function () {
  applyTheme('dark');
  const voci = %s;
  return voci.map(function (v) {
    const el = document.querySelector(v[1]);
    if (!el) return {nome: v[0], reso: null, atteso: v[3]};
    return {nome: v[0], reso: getComputedStyle(el)[v[2]], atteso: v[3]};
  });
})()
"""

esiti = []


def rgb2hex(s):
    if not s:
        return None
    import re
    m = re.findall(r'\d+', s)
    if len(m) < 3:
        return s
    return '#%02X%02X%02X' % (int(m[0]), int(m[1]), int(m[2]))


def controlla(window):
    time.sleep(2.5)
    import json
    voci = [[a, b, c, d] for a, b, c, d in ATTESI[PAGINA]]
    dati = window.evaluate_js(JS % json.dumps(voci))
    for d in dati:
        reso = rgb2hex(d['reso'])
        esiti.append((reso == d['atteso'], d['nome'], reso, d['atteso']))
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
    w = webview.create_window('tema', idx, js_api=api, width=1280, height=800)
    webview.start(controlla, w)

    print('===== TEMA SCURO vs FIGMA: %s =====' % PAGINA.upper())
    rossi = 0
    for ok, nome, reso, atteso in esiti:
        if reso is None:
            print('  saltato  %-22s (elemento assente in questa pagina)' % nome)
            continue
        print(('  ok      ' if ok else '  DIVERSO ') + '%-22s reso %s  atteso %s'
              % (nome, reso, atteso))
        if not ok:
            rossi += 1
    print('  %d differenze' % rossi)
    sys.exit(1 if rossi else 0)
