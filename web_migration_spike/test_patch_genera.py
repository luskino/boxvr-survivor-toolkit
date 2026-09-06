# -*- coding: utf-8 -*-
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

"""Senza patch, «Crea Workout da Mp3» si apre lo stesso?

Le coreografie che scrive Genera il gioco le legge SOLO da patchato: senza
patch si puo' fare tutto il giro - analisi, anteprima, generazione, file
scritti - e scoprire che in VR non e' cambiato niente. La Dashboard lo fa
gia' nell'altro verso (Correggi si blocca QUANDO la patch c'e'); qui si
verifica la porta dall'altro lato.

Quattro stati veri di `boxvr_patch.state`, uno per giro:

  patched   -> Genera aperto, Correggi bloccato   (com'era)
  original  -> Genera bloccato, e chiede la PATCH
  missing   -> Genera bloccato, e chiede la CARTELLA: la patch non si
               potrebbe nemmeno applicare, non si sa dove
  unknown   -> come missing: build non riconosciuta, niente automatismi

NIENTE SI TOCCA SUL GIOCO. Gli stati sono finti - non si legge nemmeno lo
stato vero dell'installazione - e le tre chiamate che potrebbero agire
davvero sono sostituite prima di cominciare: `confirm` risponde sempre no,
`toggle_patch` (l'unica che scriverebbe nella DLL) registra e basta,
`choose_game_dir` non apre nessun selettore.

Nota sul perche' e' scritto cosi': il clic sta in una chiamata SEPARATA da
quella che legge il risultato. Premendo, la pagina chiama l'API di
pywebview; farlo da dentro un evaluate_js significa aspettare Python da
dentro Python, e la chiamata non torna piu' - la prima versione di questa
prova moriva li', senza dire niente.
"""
import os
import sys
import time

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import webview                                                  # noqa: E402

esiti = []

JS_PREPARA = r"""
(function () {
  window.__chiesto = [];
  window.confirm = function (t) { window.__chiesto.push('confirm: ' + t); return false; };
  window.alert = function (t) { window.__chiesto.push('alert: ' + t); };
  const proxy = api();
  proxy.toggle_patch = async function () {
    window.__chiesto.push('toggle_patch'); return {ok: false, message: 'prova'};
  };
  proxy.choose_game_dir = async function () {
    window.__chiesto.push('choose_game_dir');
    return {state: 'original', game_dir: 'C:/finto/BoxVR'};
  };
  return true;
})()
"""

JS_LEGGI = r"""
(function () {
  const nota = document.getElementById('genera-patch-note');
  return {
    generaBloccato: document.getElementById('tile-genera').classList.contains('bloccato'),
    correggiBloccato: document.getElementById('tile-correggi').classList.contains('bloccato'),
    cta: document.getElementById('genera-cta').textContent,
    nota: (nota ? nota.textContent : '').trim(),
    haInstalla: !!document.getElementById('install-patch-link'),
    haScegli: !!document.getElementById('pick-dir-link'),
  };
})()
"""


def controlla(window):
    time.sleep(2.5)
    window.evaluate_js("mostraSchermata('dash-scelta')")

    def giro(stato):
        """Applica lo stato, legge com'e' messa la card, POI preme."""
        window.evaluate_js(JS_PREPARA)
        window.evaluate_js('applyStatus(%s)' % stato)
        r = window.evaluate_js(JS_LEGGI)
        # il clic in una chiamata a parte: chiama l'API, e aspettarla da
        # dentro evaluate_js bloccherebbe tutto
        window.evaluate_js("document.getElementById('genera-cta').click()")
        time.sleep(1.2)
        r['chiesto'] = ' | '.join(
            window.evaluate_js("window.__chiesto") or [])
        r['dove'] = window.evaluate_js("location.href.split('/').pop()")
        return r

    # I casi BLOCCATI per primi: quello patchato apre davvero genera.html,
    # e da li' non si torna indietro senza ricaricare la pagina.

    # ------------------------------------------ gioco trovato, non patchato
    r = giro("{state:'original', game_dir:'C:/gioco', version:'1.0'}")
    esiti.append((r['generaBloccato'], "senza patch Genera e' bloccato",
                  'cta: %s' % r['cta']))
    esiti.append(('\U0001f512' in r['cta'], 'la CTA mostra il lucchetto', r['cta']))
    esiti.append((r['haInstalla'] and not r['haScegli'],
                  'la nota offre di INSTALLARE la patch', r['nota']))
    esiti.append((r['dove'] != 'genera.html',
                  'premendo non si entra comunque in Genera',
                  'pagina: %s' % r['dove']))
    esiti.append(('confirm' in r['chiesto'] and 'patch' in r['chiesto'].lower(),
                  'premendo viene CHIESTA la patch, e si dice perche\'',
                  r['chiesto'][:180] or '(niente)'))

    # ------------------------------------- gioco non trovato / non capito
    for stato, nome in (("{state:'missing', game_dir:''}", 'gioco non trovato'),
                        ("{state:'unknown', game_dir:'C:/gioco'}", 'build ignota')):
        r = giro(stato)
        esiti.append((r['generaBloccato'], "%s: Genera e' bloccato" % nome,
                      'cta: %s' % r['cta']))
        esiti.append((r['haScegli'] and not r['haInstalla'],
                      '%s: la nota chiede la CARTELLA, non la patch' % nome,
                      r['nota']))
        esiti.append(('choose_game_dir' in r['chiesto'],
                      '%s: premendo si apre la scelta della cartella' % nome,
                      r['chiesto'][:180] or '(niente)'))

    # ------------------------------------------- patchato: per ultimo, apre
    r = giro("{state:'patched', game_dir:'C:/gioco', version:'1.0'}")
    esiti.append((not r['generaBloccato'], "con la patch Genera e' aperto",
                  'cta: %s' % r['cta']))
    esiti.append((r['correggiBloccato'],
                  "con la patch Correggi resta bloccato (com'era)", ''))
    esiti.append((r['dove'] == 'genera.html',
                  'con la patch premendo si entra davvero in Genera',
                  'pagina: %s' % r['dove']))
    window.destroy()


if __name__ == '__main__':
    sys.path.insert(0, os.path.join(QUI, 'dashboard_real'))
    import app as a
    wd = a.build_serving_dir()
    a.correggi_app._work_dir = wd
    a.genera_app._work_dir = wd
    w = webview.create_window('patch', os.path.join(wd, 'index.html'),
                              js_api=a.Api(), width=1280, height=800)
    webview.start(controlla, w)
    print('===== GENERA RICHIEDE LA PATCH =====')
    if not esiti:
        print('  FALLITO  nessun controllo eseguito')
        sys.exit(1)
    rossi = 0
    for ok, nome, dett in esiti:
        print(('  ok       ' if ok else '  FALLITO  ') + nome)
        if dett:
            print('             %s' % dett)
        rossi += 0 if ok else 1
    print('  %d problemi' % rossi)
    sys.exit(1 if rossi else 0)
