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

"""«Estendi» e' spento finche' non ha imparato, e lo spiega?

Cinque cose, sulla pagina VIVA e passando dalla strada vera (si marca coi
metodi che usa il pulsante «Marca», non impostando lo stato a mano):

  1. senza marker il pulsante e' spento          - prima era acceso, e
     sceglierlo dava una generazione tutta automatica sotto un nome che
     prometteva di imparare dai tuoi colpi
  2. spento non ha l'attributo `disabled` vero   - lo toglierebbe dal giro
     del fuoco, e con esso la possibilita' di spiegare perche' e' spento
  3. spento, premerlo non cambia modalita'       - prima cambiava, e SOLO
     ALLORA si spegneva
  4. spento, andandoci sopra compare la spiegazione col conteggio di adesso
  5. quando la marcatura basta si accende, e premendolo entra davvero
"""
import json
import os
import sys
import time

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import webview                                                  # noqa: E402
import fixture_brano                                            # noqa: E402

esiti = []
BRANO = 'prova_estendi.wav'


def leggi(window, js):
    return window.evaluate_js('(function(){%s})()' % js)


JS_STATO = """
  const b = document.querySelector('[data-mode="extend"]');
  const prima = document.getElementById('sidecar-mode').value;
  b.click();
  const dopo = document.getElementById('sidecar-mode').value;
  b.focus();
  return {spento: b.getAttribute('aria-disabled') === 'true',
          disabledVero: !!b.disabled,
          haIlFuoco: document.activeElement === b,
          prima: prima, dopo: dopo, testo: b.dataset.tipVivo || ''};
"""

JS_POPUP = """
  const pop = document.getElementById('info-popover');
  const r = pop.getBoundingClientRect();
  return {visibile: pop.classList.contains('visible') &&
                    getComputedStyle(pop).visibility !== 'hidden',
          testo: document.getElementById('info-popover-body').textContent,
          largh: Math.round(r.width), alt: Math.round(r.height)};
"""


def controlla(window):
    time.sleep(2.0)
    # prima che l'elenco esista non c'e' niente da selezionare
    for _ in range(60):
        if leggi(window, "return (typeof songs !== 'undefined') && songs.length;"):
            break
        time.sleep(0.5)
    window.evaluate_js("selectSong(%s)" % json.dumps(BRANO))
    # l'analisi vera del brano, aspettata come la aspetta l'utente
    for _ in range(180):
        if leggi(window, "return !!(current && current.duration);"):
            break
        time.sleep(1.0)
    else:
        # un test che non riesce a partire e' un test FALLITO, non un test
        # verde: silenziosamente non misurava niente
        esiti.append((False, 'analisi del brano di prova pronta',
                      'mai arrivata: nessun controllo eseguito'))
        window.destroy()
        return
    window.evaluate_js("setGenTab('sidecar')")
    time.sleep(0.3)

    # ------------------------------------------------- 1. niente marker
    window.evaluate_js(
        "(async()=>{sidecarState=await api().sidecar_clear(current.id);"
        "renderSidecarUi();})()")
    time.sleep(0.6)
    r = leggi(window, JS_STATO)
    esiti.append((r['spento'], "senza marker «Estendi» e' spento",
                  'aria-disabled=%s' % r['spento']))
    esiti.append((not r['disabledVero'],
                  "spento SENZA l'attributo disabled",
                  'con `disabled` non prenderebbe il fuoco: disabled=%s'
                  % r['disabledVero']))
    esiti.append((r['haIlFuoco'], 'da spento prende comunque il fuoco',
                  'e\' l\'unico modo, da tastiera, di vedere il perche\''))
    esiti.append((r['prima'] == r['dopo'],
                  "premerlo da spento non cambia modalita'",
                  '%s -> %s' % (r['prima'], r['dopo'])))
    esiti.append(('45' in r['testo'] and ' 0 ' in (' ' + r['testo'] + ' '),
                  'la spiegazione porta la soglia e il conteggio di adesso',
                  r['testo'].replace('\n', ' | ')[:160]))

    # il riquadro: due chiamate, perche' dentro una sola la geometria e'
    # ancora quella di prima (vedi il commento su dopoIlLayout)
    window.evaluate_js(
        "document.querySelector('[data-mode=\"extend\"]')"
        ".dispatchEvent(new MouseEvent('mouseover',{bubbles:true}))")
    time.sleep(0.5)
    p = leggi(window, JS_POPUP)
    esiti.append((p['visibile'], 'passandoci sopra compare il riquadro', ''))
    esiti.append(('45' in p['testo'],
                  "nel riquadro c'e' la spiegazione di Estendi",
                  p['testo'].replace('\n', ' | ')[:160]))
    esiti.append((p['alt'] <= 340,
                  "il riquadro si allarga invece di diventare una striscia alta",
                  '%dx%d' % (p['largh'], p['alt'])))

    # ------------------------------- 2. marcatura larga, dalla strada vera
    window.evaluate_js("""
      (async () => {
        await api().sidecar_start_record(current.id, 0);
        for (let i = 1; i <= 60; i++) await api().sidecar_mark(current.id, i * 1.0);
        sidecarState = await api().sidecar_stop_record(current.id);
        renderSidecarUi();
      })()""")
    time.sleep(3.0)
    c = leggi(window, "return sidecarState && sidecarState.copertura;")
    r2 = leggi(window, JS_STATO)
    esiti.append((not r2['spento'], 'con marcatura sufficiente si accende',
                  'copertura %.0f s, %d colpi (soglia %s s / %s colpi)'
                  % (c['secondi'], c['marker'], c['minimo'], c['minimo_marker'])))
    esiti.append((r2['dopo'] == 'extend',
                  'e premendolo entra davvero in Estendi',
                  '%s -> %s' % (r2['prima'], r2['dopo'])))
    window.destroy()


def apri():
    sys.path.insert(0, os.path.join(QUI, 'genera_real'))
    import app as a
    a._work_dir = a.build_serving_dir()
    # Un brano fabbricato dal test dentro la cartella di servizio: la
    # cartella brani VERA dell'utente non si tocca ne' in lettura ne' in
    # scrittura (stessa registrazione che fa _init_songs, altro percorso).
    wav = os.path.join(a._work_dir, BRANO)
    fixture_brano.scrivi_wav(wav, durata_s=180.0)
    a._song_paths[BRANO] = wav
    if BRANO not in a._active_ids:
        a._active_ids.append(BRANO)
    a._start_background_analysis(BRANO)
    return os.path.join(a._work_dir, 'index.html'), a.Api()


if __name__ == '__main__':
    idx, api = apri()
    w = webview.create_window('estendi', idx, js_api=api, width=1280, height=800)
    webview.start(controlla, w)
    print("===== ESTENDI: SPENTO FINCHE' NON HA IMPARATO =====")
    rossi = 0
    if not esiti:
        print('  FALLITO  nessun controllo eseguito')
        sys.exit(1)
    for ok, nome, dett in esiti:
        print(('  ok       ' if ok else '  FALLITO  ') + nome)
        if dett:
            print('             %s' % dett)
        rossi += 0 if ok else 1
    print('  %d problemi' % rossi)
    sys.exit(1 if rossi else 0)
