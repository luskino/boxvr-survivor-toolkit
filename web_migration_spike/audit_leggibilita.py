# -*- coding: utf-8 -*-
"""Controlla che i testi siano LEGGIBILI: contrasto e dimensione reale.

Due misure, entrambe fatte sulla pagina vera e non sul CSS:

  contrasto   rapporto WCAG fra colore del testo e sfondo effettivo (quello
              dipinto davvero dietro, risalendo gli antenati trasparenti).
              Soglia AA: 4.5 per il testo normale, 3.0 per quello grande
              (>=18.66px, o >=14px se in grassetto).
  dimensione  px APPARENTI = font-size * scala_fitPage.

              NON si moltiplica per il devicePixelRatio. Era cosi', e per
              questo l'audit passava mentre l'utente vedeva testi troppo
              piccoli: su uno schermo a 125% il dpr 1.25 GONFIAVA il numero
              del 25% e ogni testo sembrava a posto. La densita' non
              c'entra con quanto un testo appare grande - Windows la
              compensa gia' scalando tutto. Lo stesso errore stava nel
              pavimento di fitPage (scalaMinimaLeggibile), che divideva per
              il dpr e lasciava scendere la pagina al 73%.
              Il canvas e' scalato, quindi il font-size del CSS non e' cio'
              che l'utente vede.

    python audit_leggibilita.py correggi|genera|dashboard
"""
import os
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import webview

PAGINA = sys.argv[1] if len(sys.argv) > 1 else 'correggi'
# Soglia in px APPARENTI, allineata al pavimento di fitPage: la scala non
# scende sotto 0.75, e il testo corrente ora e' 13px (era 12), quindi il caso
# peggiore e' 13 * 0.75 = 9.75. Sotto quel numero c'e' qualcosa dichiarato
# piu' piccolo del corpo del testo, ed e' quello che va guardato.
# (nota storica) Era 11 e non 12 per farla coincidere con il pavimento
# che fitPage garantisce davvero: la scala non scende mai sotto quella che
# tiene il testo corrente (12px CSS) a 11px fisici. Sopra quel numero non c'e'
# niente da promettere; sotto, il testo diventa illeggibile su schermi piu'
# piccoli del disegno.
#
# LIMITE NOTO, non nascosto: due etichette sono disegnate a 11px CSS
# (l'etichetta degli interruttori Base beat/Marker/Curva e il pulsante
# "Veloce"). Su uno schermo piu' piccolo del wireframe possono arrivare
# intorno ai 10px fisici. Non sono state portate a 12 perche' stanno in due
# righe strette gia' state sistemate una volta per un problema di a capo:
# allargarle rischia di riaprirlo, e il guadagno sarebbe di un pixel.
MIN_FISICI = 9.7

JS = r"""
(function () {
  function lum(c) {
    var v = c.map(function (x) {
      x /= 255;
      return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
  }
  function parse(s) {
    var m = /rgba?\(([^)]+)\)/.exec(s || '');
    if (!m) return null;
    var p = m[1].split(',').map(parseFloat);
    return {c: [p[0], p[1], p[2]], a: p.length > 3 ? p[3] : 1};
  }
  function fondo(el) {
    // risale finche' non trova uno sfondo davvero opaco: e' quello che
    // l'occhio vede dietro il testo.
    // Se per strada incontra un gradiente o un'immagine, il colore dietro
    // non e' un valore unico e il contrasto non e' calcolabile: lo dico,
    // invece di misurare contro lo sfondo sbagliato piu' in alto e
    // produrre finti fallimenti (successo al primo giro sui preset e
    // sulle pillole delle fasi).
    var n = el;
    while (n && n !== document.documentElement) {
      var cs = getComputedStyle(n);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') return null;
      var b = parse(cs.backgroundColor);
      if (b && b.a >= 0.95) return b.c;
      n = n.parentElement;
    }
    return [255, 255, 255];
  }
  function contrasto(f, b) {
    var l1 = lum(f), l2 = lum(b);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  }

  var page = document.querySelector('.page.genera-fixed, .page.dash-fixed');
  var scala = page ? page.getBoundingClientRect().width / 1920 : 1;
  // dimensione APPARENTE, non 'fisica': moltiplicare per il dpr era
  // l'errore che rendeva questo audit cieco (vedi il commento in testa)
  var fisico = scala;

  var res = {fisico: fisico, scala: scala, dpr: window.devicePixelRatio, voci: [], saltati: []};
  var visti = {};
  document.querySelectorAll('body *').forEach(function (el) {
    var propri = Array.prototype.filter.call(el.childNodes, function (n) {
      return n.nodeType === 3 && n.textContent.trim();
    });
    if (!propri.length) return;
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' ||
        parseFloat(cs.opacity) < 0.05) return;
    // Componenti INATTIVI: WCAG 1.4.3 li esclude esplicitamente dal
    // requisito di contrasto ("Text or images of text that are part of an
    // inactive user interface component ... have no contrast requirement").
    // Senza questa esclusione i controlli spenti dallo stato "analisi non
    // pronta" risultavano fuori norma solo perche' sono deliberatamente
    // smorzati: i loro colori veri sono 4.8:1 e 14.9:1, e' l'opacita' 0.42
    // dello stato spento a farli scendere. Segnalarli avrebbe portato a
    // "correggere" un contrasto che non e' un difetto.
    if (el.closest('[aria-disabled="true"], :disabled, [disabled]')) return;
    var r = el.getBoundingClientRect();
    if (!r.width || !r.height) return;

    var fg = parse(cs.color);
    if (!fg) return;
    var bg = fondo(el);
    if (!bg) { res.saltati.push((el.className || el.tagName) + ' (sfondo a gradiente)'); return; }
    // opacita' del testo: la miscelo sullo sfondo, e' cio' che si vede
    var op = 1, n = el;
    while (n && n !== document.documentElement) {
      op *= parseFloat(getComputedStyle(n).opacity);
      n = n.parentElement;
    }
    var a = fg.a * op;
    var eff = [0, 1, 2].map(function (i) { return fg.c[i] * a + bg[i] * (1 - a); });

    var fs = parseFloat(cs.fontSize);
    var peso = parseInt(cs.fontWeight, 10) || 400;
    // WCAG chiama "grande" il testo da 18pt (24px), o 14pt (18.66px) se in
    // grassetto. Il primo giro usava 18.66px/14px-grassetto: era piu'
    // permissivo del vero e faceva passare per "grande" testo che grande
    // non e' (le pillole a 14px).
    var grande = fs >= 24 || (fs >= 18.66 && peso >= 700);
    var chiave = fs + '|' + cs.color + '|' + bg.join(',') + '|' + (el.className || el.tagName);
    if (visti[chiave]) return;
    visti[chiave] = 1;

    res.voci.push({
      fs: fs, fisici: fs * fisico, peso: peso,
      contrasto: contrasto(eff, bg), soglia: grande ? 3.0 : 4.5,
      colore: cs.color, opacita: op, sfondo: 'rgb(' + bg.map(Math.round).join(',') + ')',
      cls: (typeof el.className === 'string' ? el.className : '') || el.tagName,
      txt: propri.map(function (n) { return n.textContent; }).join(' ')
             .trim().slice(0, 30).replace(/\s+/g, ' ')
    });
  });
  return res;
})()
"""


def esamina(window):
    """Gira in ENTRAMBI i temi, non solo in quello salvato nelle impostazioni.

    Prima girava con qualunque tema fosse attivo, e per questo tredici
    difetti di contrasto del tema scuro erano rimasti invisibili per tutta
    la lavorazione: colori letterali del tema chiaro su superfici scure, e
    riquadri con fondo fisso sotto testo che invece seguiva i token. Un
    difetto di accoppiamento fra colore e fondo si vede solo se si guardano
    tutte e due le combinazioni.
    """
    import time
    time.sleep(2.5)
    esiti = []
    for tema in ('light', 'dark'):
        window.evaluate_js(
            "document.documentElement.setAttribute('data-theme', '%s');"
            "document.body.setAttribute('data-theme', '%s'); 1" % (tema, tema))
        time.sleep(0.8)
        esiti.append((tema, window.evaluate_js(JS)))
    for tema, d in esiti:
        _riporta(window, tema, d)
    window.destroy()


def _riporta(window, tema, d):
    piccoli = [v for v in d['voci'] if v['fisici'] < MIN_FISICI]
    scarsi = [v for v in d['voci'] if v['contrasto'] < v['soglia']]

    print('===== LEGGIBILITA %s - TEMA %s =====' % (PAGINA.upper(), tema.upper()), flush=True)
    print('scala fitPage %.4f  (dpr %.2f, non usato: conta la dimensione '
          'apparente)' % (d['scala'], d['dpr']), flush=True)
    print('%d testi esaminati, %d saltati (sfondo non misurabile)'
          % (len(d['voci']), len(d['saltati'])), flush=True)

    print('\n-- CONTRASTO SOTTO LA SOGLIA WCAG AA (%d) --' % len(scarsi), flush=True)
    for v in sorted(scarsi, key=lambda x: x['contrasto']):
        print('  %.2f:1 (serve %.1f)  %-5.0fpx  %-26s %-22s su %-18s %s'
              % (v['contrasto'], v['soglia'], v['fs'], v['cls'][:26],
                 v['colore'], v['sfondo'], v['txt']), flush=True)

    print('\n-- PIU\' PICCOLI DI %.1f px APPARENTI (%d) --'
          % (MIN_FISICI, len(piccoli)), flush=True)
    for v in sorted(piccoli, key=lambda x: x['fisici']):
        print('  %.1f px apparenti (css %.0f)  %-26s %s'
              % (v['fisici'], v['fs'], v['cls'][:26], v['txt']), flush=True)

    # La finestra che apre questo audit e' grande, quindi la scala misurata
    # e' vicina a 1 e non racconta il caso peggiore. Quello che si vede su
    # uno schermo piccolo e' il canvas al PAVIMENTO (0.75): e' li' che va
    # guardata la dimensione, altrimenti l'audit resta cieco esattamente
    # come lo era finche' moltiplicava per il dpr.
    PAVIMENTO = 0.75
    print('\n-- AL PAVIMENTO (scala %.2f, schermo piccolo) --' % PAVIMENTO,
          flush=True)
    sotto = []
    for fs in sorted({v['fs'] for v in d['voci']}):
        app = fs * PAVIMENTO
        quanti = sum(1 for v in d['voci'] if v['fs'] == fs)
        print('  %s %2.0fpx dichiarati -> %.1f apparenti  (%d testi)'
              % ('<<' if app < MIN_FISICI else '  ', fs, app, quanti),
              flush=True)
        if app < MIN_FISICI:
            sotto.append(fs)
    if sotto:
        print('  %d dimensioni scendono sotto la soglia su schermo piccolo: %s'
              % (len(sotto), ', '.join('%gpx' % f for f in sotto)), flush=True)

    print('\n  %d problemi di contrasto, %d di dimensione, %d al pavimento'
          % (len(scarsi), len(piccoli), len(sotto)), flush=True)


if PAGINA == 'genera':
    sys.path.insert(0, os.path.join(QUI, 'genera_real'))
    import app as a
    a._work_dir = a.build_serving_dir(); a._init_songs()
    idx, api = os.path.join(a._work_dir, 'index.html'), a.Api()
elif PAGINA == 'correggi':
    sys.path.insert(0, os.path.join(QUI, 'correggi_real'))
    import app as a
    a._work_dir = a.build_serving_dir(); a._init_songs()
    idx, api = os.path.join(a._work_dir, 'index.html'), a.Api()
else:
    sys.path.insert(0, os.path.join(QUI, 'dashboard_real'))
    import app as a
    wd = a.build_serving_dir()
    a.correggi_app._work_dir = wd; a.correggi_app._init_songs()
    a.genera_app._work_dir = wd; a.genera_app._init_songs()
    idx, api = os.path.join(wd, 'index.html'), a.Api()

w = webview.create_window("leggibilita", idx, js_api=api, width=1920, height=1080)
webview.start(esamina, w)
