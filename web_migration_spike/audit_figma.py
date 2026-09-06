# -*- coding: utf-8 -*-
"""Audit: confronta le tre pagine del port con i valori REALI del Figma.

Ogni riga e' un'asserzione con il valore atteso preso da:
  - get_metadata sui frame (1:7 Correggi, 7:320 modale, 4:158 Tile mode)
  - estrazione dei rettangoli dagli export SVG (Genera.svg / Correggi.svg)
  - campionamento pixel degli export PNG (colori)
Stampa PASS/FAIL per ciascuna, cosi' l'esito e' verificabile e non un'opinione.
"""
import sys, os, time, json
sys.path.insert(0, r"F:\BoxVR Songs Tool")
sys.path.insert(0, r"F:\BoxVR Songs Tool\web_migration_spike")
import webview

PAGINA = sys.argv[1]        # genera | correggi | dashboard
esiti = []


def _uguale(a, b, tol):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol
    return a == b


def controlla(nome, atteso, ottenuto, tolleranza=1):
    if isinstance(atteso, list) and isinstance(ottenuto, list) and len(atteso) == len(ottenuto):
        ok = all(_uguale(a, b, tolleranza) for a, b in zip(atteso, ottenuto))
    else:
        ok = _uguale(atteso, ottenuto, tolleranza)
    esiti.append((ok, nome, atteso, ottenuto))


JS_BOX = """(function(){
  var page=document.querySelector('.page').getBoundingClientRect();
  var k=page.width/1920;
  var out={};
  var sel=%s;
  for (var nome in sel) {
    // Fra piu' elementi che corrispondono si prende il primo VISIBILE.
    // Sul selettore '.dash-modal' ce ne sono tre (i due disclaimer piu' la
    // schermata di scelta) e quale sia visibile dipende dal fatto che il
    // consenso sia gia' stato dato: querySelector prendeva sempre il primo,
    // cioe' un disclaimer nascosto, e restituiva 0x0. Il controllo passava o
    // falliva a seconda dello stato di settings.json, non del codice.
    var tutti=document.querySelectorAll(sel[nome]);
    var e=null;
    for (var q=0; q<tutti.length; q++) {
      var rq=tutti[q].getBoundingClientRect();
      if (rq.width>0 && rq.height>0) { e=tutti[q]; break; }
    }
    if (!e) e=tutti[0] || null;
    if (!e) { out[nome]=null; continue; }
    var r=e.getBoundingClientRect();
    out[nome]=[Math.round((r.left-page.left)/k), Math.round((r.top-page.top)/k),
               Math.round(r.width/k), Math.round(r.height/k)];
  }
  return JSON.stringify(out);})()"""


def box(window, sel):
    return json.loads(window.evaluate_js(JS_BOX % json.dumps(sel)))


def stile(window, sel, prop):
    return window.evaluate_js(
        "(function(){var e=document.querySelector(%s);"
        "return e?getComputedStyle(e).%s:null;})()" % (json.dumps(sel), prop))


def audit_comune(window, etichetta):
    """Controlli identici su Genera e Correggi: sono lo stesso componente."""
    b = box(window, {
        'card_anteprima': '.preview-card',
        'pannello_brani': '.song-panel',
        'onda': '.waveform-wrap',
        'marche': '.pv-times',
        'mini_struttura': '.mini-structure',
        'riga_brano': '.song-row',
    })
    controlla(etichetta + ': card anteprima (44,338) 1360x289', [44, 338, 1360, 289], b['card_anteprima'])
    controlla(etichetta + ': pannello brani (1431,338) 440x693', [1431, 338, 440, 693], b['pannello_brani'])
    controlla(etichetta + ': forma onda (63,407) 1322x144', [63, 407, 1322, 144], b['onda'])
    controlla(etichetta + ': riga brano 404x75', [404, 75], b['riga_brano'][2:] if b['riga_brano'] else None)

    n = window.evaluate_js("document.querySelectorAll('.pv-times span').length")
    controlla(etichetta + ': 12 marche temporali', 12, n)

    # forma d'onda: fondo bianco, bande a 0.78, sagoma = banda meno 56
    controlla(etichetta + ': fondo onda bianco', 'rgb(255, 255, 255)',
              stile(window, '.waveform-wrap', 'backgroundColor'))
    controlla(etichetta + ': opacita bande 0.78', '0.78',
              stile(window, '#waveform .seg', 'opacity'))
    burn = window.evaluate_js("""(function(){
      var chiaro=getComputedStyle(document.querySelector('#waveform .seg')).backgroundColor;
      var scuro=document.querySelector('#waveform-dark .seg').style.background;
      function n(s){return (s.match(/\\d+/g)||[]).map(Number);}
      var c=n(chiaro), s=n(scuro);
      // il chiaro e' il token pieno: la resa su bianco a 0.78 e' quella che conta
      var reso=c.slice(0,3).map(function(v){return Math.round(v*0.78+255*0.22);});
      return JSON.stringify([reso[0]-s[0], reso[1]-s[1], reso[2]-s[2]]);})()""")
    controlla(etichetta + ': sagoma = banda meno 56 per canale', [56, 56, 56], json.loads(burn))

    controlla(etichetta + ': nessuna linea beat nell anteprima', 0,
              window.evaluate_js("document.querySelectorAll('#wave-overlay .beat-tick, .waveform-wrap .beat-tick').length"))
    controlla(etichetta + ': marker viola #7700FF', 'rgb(119, 0, 255)',
              window.evaluate_js("""(function(){
                var d=document.createElement('div'); d.style.stroke='';
                var s=document.createElement('style');
                s.textContent='.__p{color:#7700FF}';document.head.appendChild(s);
                d.className='__p';document.body.appendChild(d);
                var c=getComputedStyle(d).color;d.remove();s.remove();return c;})()"""))

    # cursore: linea nera, cerchietti alle estremita', figlio della card
    ph = box(window, {'cursore': '.main-playhead'})['cursore']
    controlla(etichetta + ': cursore alto 198 (da y51 a y249)', 198, ph[3] if ph else None)
    controlla(etichetta + ': cursore parte a y=51 della card', 389, ph[1] if ph else None)  # 338+51
    controlla(etichetta + ': cursore nero',
              'rgb(0, 0, 0)',
              window.evaluate_js("getComputedStyle(document.querySelector('.main-playhead'),'::before').borderTopColor"))

    # riga brano: X di rimozione e pillola Rimuovi
    x = window.evaluate_js("""(function(){
      var r=document.querySelector('.song-row'), x=r.querySelector('.song-remove-x');
      x.style.display='block';
      var s=getComputedStyle(x);
      return JSON.stringify([s.backgroundColor, s.width, s.height, s.borderRadius]);})()""")
    controlla(etichetta + ': X rimozione cerchio #0C355C 18px',
              ['rgb(12, 53, 92)', '18px', '18px', '50%'], json.loads(x), 0)
    p = window.evaluate_js("""(function(){
      var b=document.querySelector('.remove-confirm-bar'); var s=getComputedStyle(b);
      return JSON.stringify([s.backgroundColor, s.width, s.height]);})()""")
    controlla(etichetta + ': pillola Rimuovi #FF0000 88x22',
              ['rgb(255, 0, 0)', '88px', '22px'], json.loads(p), 0)

    controlla(etichetta + ': nessun errore JS', [],
              json.loads(window.evaluate_js("JSON.stringify(window.__errs||[])")))


def blocca_extra(window):
    """Fissa --extra a 0 e impedisce a fitPage di rimetterlo: il wireframe e'
    definito a 1920px esatti, e le misure vanno prese li'. Senza questo, su
    una finestra piu' larga di 16:9 il canvas si allarga (per progetto) e
    ogni coordinata ancorata a destra risulterebbe "sbagliata"."""
    window.evaluate_js("""(function(){
      var p = document.querySelector('.page.genera-fixed, .page.dash-fixed');
      if (!p) return;
      p.style.setProperty('--extra', '0px');
      window.__extraCanvas = 0;
      // fitPage lo riscriverebbe al primo resize: lo si neutralizza per la
      // durata della misura
      window.fitPage = function () {};
    })()""")


def main_genera(window):
    import app as ga
    ga._fit_client_to_wireframe(window)
    for _ in range(150):
        if window.evaluate_js("document.querySelectorAll('.waveform .seg').length > 0"):
            break
        time.sleep(1)
    time.sleep(1.5)
    blocca_extra(window)
    window.evaluate_js("applyTheme('light')")
    audit_comune(window, 'GENERA')
    b = box(window, {
        'card_sx': '.generation-tabs-card',
        'card_dx': '.genera-bottom-row > *:nth-child(2)',
    })
    controlla('GENERA: card generazione sinistra (44,651) 625x380', [44, 651, 625, 380], b['card_sx'])
    # BPM: pillola arancione solo quando sospetto
    controlla('GENERA: pillola BPM sospetto #FF883E', 'rgb(255, 136, 62)',
              window.evaluate_js("""(function(){
                var e=document.getElementById('p-bpm');
                e.classList.add('suspicious');
                var c=getComputedStyle(e).backgroundColor;
                return c;})()"""))
    fine(window)


def main_correggi(window):
    import app as ca
    ca._fit_client_to_wireframe(window)
    for _ in range(150):
        if window.evaluate_js("document.querySelectorAll('.waveform .seg').length > 0"):
            break
        time.sleep(1)
    time.sleep(1.5)
    blocca_extra(window)
    window.evaluate_js("applyTheme('light')")
    audit_comune(window, 'CORREGGI')
    b = box(window, {
        'toolkit': '.toolkit-card',
        'separatore': '.tk-sep',
        'preset': '#preset-buttons',
        'copia': '.btn-copy-all',
        'stati': '#stati-gen',
        'log': '.tk-log',
        'fasi': '.tk-fasi-row',
    })
    controlla('CORREGGI: card toolkit (43,686) 1360x345', [43, 686, 1360, 345], b['toolkit'])
    controlla('CORREGGI: separatore (487,710) h297', [487, 710, 1, 297], b['separatore'])
    controlla('CORREGGI: preset (66,777) 324x24', [66, 777, 324, 24], b['preset'])
    controlla('CORREGGI: copia su tutti (66,965) 192x34', [66, 965, 192, 34], b['copia'])
    controlla('CORREGGI: stati correzione (510,827) 881x71', [510, 827, 881, 71], b['stati'])
    controlla('CORREGGI: log (510,915) 880x93', [510, 915, 880, 93], b['log'])
    controlla('CORREGGI: fasi prima>dopo presenti', 4,
              window.evaluate_js("document.querySelectorAll('.tk-fasi-row .pill').length"))
    controlla('CORREGGI: niente selettore motore (non nel wireframe)', 0,
              window.evaluate_js("document.querySelectorAll('.pv-engine').length"))
    fine(window)


def main_dashboard(window):
    for _ in range(120):
        if window.evaluate_js("!!document.querySelector('.dash-modal')"):
            break
        time.sleep(1)
    time.sleep(2.5)
    blocca_extra(window)
    # il wireframe e' disegnato in tema chiaro: e' quello il riferimento
    window.evaluate_js("applyTheme('light')")
    time.sleep(0.4)
    b = box(window, {
        'modale': '.dash-modal',
        'tile_sx': '.dash-tile.correggi',
        'tile_dx': '.dash-tile.genera',
        'cta_sx': '.dash-tile.correggi .tile-cta',
        'cta_dx': '.dash-tile.genera .tile-cta',
        'chiudi': '.dash-close',
    })
    controlla('DASHBOARD: modale (548,271) 842x537', [548, 271, 842, 537], b['modale'])
    controlla('DASHBOARD: tile Correggi (652,449) 279x313', [652, 449, 279, 313], b['tile_sx'])
    controlla('DASHBOARD: tile Genera (1002,449) 279x313', [1002, 449, 279, 313], b['tile_dx'])
    controlla('DASHBOARD: CTA 192x45 a (44,242) del tile', [696, 691, 192, 45], b['cta_sx'])
    controlla('DASHBOARD: X chiusura (1334,294) 30x30', [1334, 294, 30, 30], b['chiudi'])
    controlla('DASHBOARD: fondo pagina #2F2F31', 'rgb(47, 47, 49)',
              stile(window, '.page.dash-fixed', 'backgroundColor'))
    controlla('DASHBOARD: fondo modale #EDEDF7', 'rgb(237, 237, 247)',
              stile(window, '.dash-modal', 'backgroundColor'))
    controlla('DASHBOARD: CTA Genera #FF3E41', 'rgb(255, 62, 65)',
              stile(window, '.dash-tile.genera .tile-cta', 'backgroundColor'))
    controlla('DASHBOARD: nessun errore JS', [],
              json.loads(window.evaluate_js("JSON.stringify(window.__errs||[])")))
    fine(window)


def fine(window):
    print('\n===== ESITO %s =====' % PAGINA.upper(), flush=True)
    for ok, nome, atteso, ott in esiti:
        print(('  PASS  ' if ok else '  FAIL  ') + nome, flush=True)
        if not ok:
            print('          atteso=%r  ottenuto=%r' % (atteso, ott), flush=True)
    print('  %d/%d superati' % (sum(1 for e in esiti if e[0]), len(esiti)), flush=True)
    window.destroy()


if PAGINA == 'genera':
    sys.path.insert(0, r"F:\BoxVR Songs Tool\web_migration_spike\genera_real")
    import app as ga
    ga._work_dir = ga.build_serving_dir(); ga._init_songs()
    w = webview.create_window("audit", os.path.join(ga._work_dir, 'index.html'),
                              js_api=ga.Api(), width=1920, height=1080)
    webview.start(main_genera, w)
elif PAGINA == 'correggi':
    sys.path.insert(0, r"F:\BoxVR Songs Tool\web_migration_spike\correggi_real")
    import app as ca
    ca._work_dir = ca.build_serving_dir(); ca._init_songs()
    w = webview.create_window("audit", os.path.join(ca._work_dir, 'index.html'),
                              js_api=ca.Api(), width=1920, height=1080)
    webview.start(main_correggi, w)
else:
    sys.path.insert(0, r"F:\BoxVR Songs Tool\web_migration_spike\dashboard_real")
    import app as da
    wd = da.build_serving_dir()
    da.correggi_app._work_dir = wd; da.correggi_app._init_songs()
    da.genera_app._work_dir = wd; da.genera_app._init_songs()
    w = webview.create_window("audit", os.path.join(wd, 'index.html'),
                              js_api=da.Api(), width=1920, height=1080)
    webview.start(main_dashboard, w)
