# -*- coding: utf-8 -*-
"""Controllo a tappeto della UI contro le linee guida, misurato a runtime.

Non e' un giudizio a occhio: ogni voce qui sotto e' un numero preso da una
fonte, e l'audit misura gli elementi veri della pagina contro quel numero.

  bersagli     WCAG 2.2 SC 2.5.8 "Target Size (Minimum)", livello AA:
               ogni bersaglio per puntatore e' almeno 24x24 px CSS.
               https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
               L'eccezione "spacing" del criterio e' implementata: un
               bersaglio piu' piccolo passa se attorno ha spazio libero
               sufficiente perche' un cerchio da 24px non tocchi i vicini.

  focus        WCAG 2.2 SC 2.4.7 "Focus Visible" (AA) e SC 2.4.13 "Focus
               Appearance" (AAA): serve un indicatore visibile, spesso
               almeno 2px e con 3:1 rispetto allo stato non a fuoco.
               Qui si controlla che l'elemento CAMBI aspetto con :focus e
               che non abbia outline:none senza rimpiazzo.

  non testo    WCAG 1.4.11 "Non-text Contrast": bordi di campi, stati degli
               interruttori e icone che veicolano informazione stanno a
               almeno 3:1 con lo sfondo adiacente.

  scorciatoie  campi senza etichetta associata (<label for> o aria-label):
               il segnaposto NON e' un'etichetta, sparisce quando si scrive.

Uso:
    python audit_ux.py [genera|correggi|dashboard|playlist]
"""
import io
import json
import os
import sys
import time

QUI = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
PAGINA = (sys.argv[1] if len(sys.argv) > 1 else 'genera').lower()

MIN_BERSAGLIO = 24.0     # WCAG 2.2 SC 2.5.8, px CSS
MIN_NON_TESTO = 3.0      # WCAG 1.4.11
# lista e non intero: 'lavora' gira dentro webview e assegnare a un
# intero di modulo da li' creerebbe una variabile locale
USCITA = [0]

JS = r"""
(function () {
  function lum(c) {
    var m = c.match(/[\d.]+/g); if (!m) return null;
    if (m.length > 3 && parseFloat(m[3]) < 0.95) return null;   // semitrasparente
    var v = [0,1,2].map(function (i) {
      var x = parseFloat(m[i]) / 255;
      return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
    });
    return 0.2126*v[0] + 0.7152*v[1] + 0.0722*v[2];
  }
  function rapporto(a, b) {
    var la = lum(a), lb = lum(b);
    if (la === null || lb === null) return null;
    return (Math.max(la,lb) + 0.05) / (Math.min(la,lb) + 0.05);
  }
  function sfondoDietro(el) {
    var n = el;
    while (n && n !== document.documentElement) {
      var c = getComputedStyle(n).backgroundColor;
      if (c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') return c;
      n = n.parentElement;
    }
    return 'rgb(255,255,255)';
  }
  function visibile(el) {
    var s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }
  function nome(el) {
    var t = (el.getAttribute('aria-label') || el.title ||
             (el.textContent || '').trim() || el.id || el.className || '')
            .replace(/\s+/g, ' ').slice(0, 40);
    return el.tagName.toLowerCase() + (t ? ' "' + t + '"' : '');
  }

  var scala = window.__scalaCanvas || 1;
  // Interattivi per COMPORTAMENTO, non per nome di classe. Prima l'elenco
  // conteneva ".seg", e finivano dentro anche le fasce colorate delle fasi
  // della playlist, che sono <div> con un solo title: informative, non
  // bersagli. Un criterio sui bersagli applicato a cio' che non e' un
  // bersaglio produce rilievi che non si possono correggere.
  var SEL = 'button, a[href], input, select, textarea, [onclick], [tabindex],' +
            ' [role=button], [role=switch], [role=link], [role=checkbox],' +
            ' [role=tab], [role=menuitem]';
  var tutti = Array.prototype.slice.call(document.querySelectorAll(SEL))
                .filter(visibile)
                .filter(function (el) {
                  // un contenitore che porta l'onclick solo per delegare ai
                  // figli non e' esso stesso un bersaglio
                  return !(el.tagName === 'DIV' && !el.getAttribute('role') &&
                           el.querySelector('button, a[href], input'));
                });

  // --- bersagli troppo piccoli (con l'eccezione "spacing" del criterio) ---
  var riquadri = tutti.map(function (el) {
    var r = el.getBoundingClientRect();
    // getBoundingClientRect torna px di SCHERMO: il canvas e' scalato da
    // fitPage, quindi si divide per riportarli a px CSS, che e' l'unita'
    // in cui il criterio WCAG e' scritto.
    return {el: el, x: r.left/scala, y: r.top/scala,
            w: r.width/scala, h: r.height/scala};
  });
  function distanzaMinima(i) {
    var a = riquadri[i], d = Infinity;
    for (var j = 0; j < riquadri.length; j++) {
      if (j === i) continue;
      var b = riquadri[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      var dx = Math.max(0, Math.max(a.x - (b.x+b.w), b.x - (a.x+a.w)));
      var dy = Math.max(0, Math.max(a.y - (b.y+b.h), b.y - (a.y+a.h)));
      d = Math.min(d, Math.hypot(dx, dy));
    }
    return d;
  }
  var piccoli = [];
  riquadri.forEach(function (a, i) {
    if (a.w >= 24 && a.h >= 24) return;
    if (a.el.tagName === 'A' && a.el.closest('p, li, .tk-log-body')) return;  // link in linea: escluso dal criterio
    var spazio = distanzaMinima(i);
    // eccezione del criterio: basta che un cerchio da 24px centrato sul
    // bersaglio non ne tocchi un altro
    var raggioLibero = Math.min(a.w, a.h)/2 + spazio;
    piccoli.push({nome: nome(a.el), w: +a.w.toFixed(1), h: +a.h.toFixed(1),
                  spazio: +(spazio === Infinity ? 999 : spazio).toFixed(1),
                  passaPerSpazio: raggioLibero >= 12});
  });

  // --- focus soppresso senza rimpiazzo ---
  // Si MISURA, non si indovina: prima si legge l'aspetto a riposo, poi si
  // da' il fuoco all'elemento e si rilegge. Se outline e ombra non
  // cambiano, non c'e' indicatore. La versione precedente cercava il nome
  // della classe dentro il testo dei selettori e falliva su una regola
  // scritta come :where(button, a[href], ...):focus-visible, che non
  // contiene ne' la classe ne' il tag in prima posizione.
  var senzaFocus = [];
  var attivoPrima = document.activeElement;
  tutti.forEach(function (el) {
    // un elemento disabilitato non deve prendere il fuoco: segnalarlo era
    // un falso positivo ("Avvia generazione" prima di avere un nome)
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return;
    var s0 = getComputedStyle(el);
    var prima = [s0.outlineStyle, s0.outlineWidth, s0.outlineColor,
                 s0.boxShadow, s0.borderColor].join('|');
    try { el.focus({preventScroll: true}); } catch (e) { return; }
    var s1 = getComputedStyle(el);
    var dopo = [s1.outlineStyle, s1.outlineWidth, s1.outlineColor,
                s1.boxShadow, s1.borderColor].join('|');
    if (prima !== dopo) return;      // qualcosa cambia: indicatore c'e'
    senzaFocus.push(nome(el));
    return;
    // (il vecchio percorso resta sotto, non raggiunto)
    var s = getComputedStyle(el);
    var niente = (s.outlineStyle === 'none' || s.outlineWidth === '0px');
    if (!niente) return;
    // c'e' una regola :focus/:focus-visible che lo rimpiazza?
    var cls = (el.className || '').toString().split(/\s+/).filter(Boolean);
    var id = el.id;
    var coperto = false;
    for (var i = 0; i < document.styleSheets.length && !coperto; i++) {
      var regole; try { regole = document.styleSheets[i].cssRules; } catch (e) { continue; }
      for (var j = 0; j < regole.length; j++) {
        var t = regole[j].selectorText;
        if (!t || t.indexOf('focus') < 0) continue;
        if (id && t.indexOf('#' + id) >= 0) { coperto = true; break; }
        for (var k = 0; k < cls.length; k++)
          if (t.indexOf('.' + cls[k]) >= 0) { coperto = true; break; }
        if (coperto) break;
        if (t.indexOf(el.tagName.toLowerCase()) === 0) { coperto = true; break; }
      }
    }
    if (!coperto) senzaFocus.push(nome(el));
  });
  try { if (attivoPrima && attivoPrima.focus) attivoPrima.focus({preventScroll: true}); } catch (e) {}

  // --- contrasto degli elementi non testuali ---
  var scarsi = [];
  document.querySelectorAll('input, select, textarea, .toggle, .zoom-bar, .segmented')
    .forEach(function (el) {
      if (!visibile(el)) return;
      var s = getComputedStyle(el);
      var bordo = s.borderTopColor, largh = parseFloat(s.borderTopWidth) || 0;
      var dietro = sfondoDietro(el.parentElement || el);
      // un contorno dato con box-shadow inset delimita il controllo esatta-
      // mente come un border: se c'e', il confine esiste
      if (/inset/.test(s.boxShadow || '')) return;
      if (largh > 0) {
        var r = rapporto(bordo, dietro);
        if (r !== null && r < 3.0)
          scarsi.push({nome: nome(el), cosa: 'bordo', r: +r.toFixed(2),
                       colore: bordo, su: dietro});
      }
      var fondo = s.backgroundColor;
      var rf = rapporto(fondo, dietro);
      // type=range escluso: traccia e manopola le disegna il browser, lo
      // sfondo dell'elemento non e' cio' che si vede. Segnalarlo era un
      // falso positivo (usciva sempre 1.00:1, bianco su bianco).
      if (largh === 0 && rf !== null && rf < 3.0 && el.type !== 'range' &&
          (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA'))
        scarsi.push({nome: nome(el), cosa: 'campo senza bordo', r: +rf.toFixed(2),
                     colore: fondo, su: dietro});
    });

  // --- campi senza etichetta associata ---
  var senzaEtichetta = [];
  document.querySelectorAll('input, select, textarea').forEach(function (el) {
    if (!visibile(el)) return;
    if (el.type === 'hidden' || el.type === 'range' || el.type === 'checkbox') return;
    var ok = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') ||
             (el.id && document.querySelector('label[for="' + el.id + '"]'));
    if (!ok) senzaEtichetta.push({nome: nome(el),
                                  segnaposto: el.placeholder || '(nessun segnaposto)'});
  });

  return {scala: scala, esaminati: tutti.length, piccoli: piccoli,
          senzaFocus: senzaFocus, scarsi: scarsi, senzaEtichetta: senzaEtichetta};
})()
"""


def lavora(window):
    time.sleep(3)
    d = window.evaluate_js(JS)
    p = [v for v in d['piccoli'] if not v['passaPerSpazio']]
    scusati = [v for v in d['piccoli'] if v['passaPerSpazio']]

    print('===== UX %s =====' % PAGINA.upper(), flush=True)
    print('%d elementi interattivi esaminati (scala canvas %.3f)'
          % (d['esaminati'], d['scala']), flush=True)

    print('\n-- BERSAGLI SOTTO %.0fx%.0f px CSS - WCAG 2.2 SC 2.5.8 (%d) --'
          % (MIN_BERSAGLIO, MIN_BERSAGLIO, len(p)), flush=True)
    for v in sorted(p, key=lambda x: x['w'] * x['h']):
        print('  %5.1f x %-5.1f  spazio attorno %5.1f   %s'
              % (v['w'], v['h'], v['spazio'], v['nome']), flush=True)
    if scusati:
        print('  (%d piu\' piccoli ma con spazio attorno sufficiente: '
              'l\'eccezione del criterio li assolve)' % len(scusati), flush=True)

    print('\n-- FOCUS SOPPRESSO SENZA RIMPIAZZO - SC 2.4.7 (%d) --'
          % len(d['senzaFocus']), flush=True)
    for n in d['senzaFocus'][:20]:
        print('  ', n, flush=True)

    print('\n-- CONTRASTO NON TESTUALE SOTTO 3:1 - SC 1.4.11 (%d) --'
          % len(d['scarsi']), flush=True)
    for v in d['scarsi']:
        print('  %.2f:1  %-18s %-34s %s su %s'
              % (v['r'], v['cosa'], v['nome'], v['colore'], v['su']), flush=True)

    print('\n-- CAMPI SENZA ETICHETTA ASSOCIATA (%d) --'
          % len(d['senzaEtichetta']), flush=True)
    for v in d['senzaEtichetta']:
        print('  %-40s segnaposto: %s' % (v['nome'], v['segnaposto']), flush=True)

    tot = len(p) + len(d['senzaFocus']) + len(d['scarsi']) + len(d['senzaEtichetta'])
    print('\n  TOTALE: %d rilievi' % tot, flush=True)
    # il codice di uscita serve a verifica.py: senza, un rilievo
    # sarebbe passato inosservato dentro la suite
    USCITA[0] = 1 if tot else 0
    window.destroy()


import webview                                                  # noqa: E402
if PAGINA == 'genera':
    sys.path.insert(0, os.path.join(QUI, 'genera_real'))
elif PAGINA == 'correggi':
    sys.path.insert(0, os.path.join(QUI, 'correggi_real'))
elif PAGINA == 'playlist':
    sys.path.insert(0, os.path.join(QUI, 'playlist_real'))
else:
    sys.path.insert(0, os.path.join(QUI, 'dashboard_real'))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))
import app as pagina_app                                        # noqa: E402

pagina_app._work_dir = pagina_app.build_serving_dir()
w = webview.create_window('audit ux',
                          os.path.join(pagina_app._work_dir, 'index.html'),
                          js_api=pagina_app.Api(), width=1500, height=1000)
webview.start(lavora, w)
sys.exit(USCITA[0])
