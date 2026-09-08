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

"""Muovendo uno slider, l'anteprima cambia davvero?

IL DIFETTO CHE QUESTO TEST ESISTE PER FERMARE (08/09). Il pannello chiedeva
`get_action_list(track_id, rigenera=True)`, che salta il file su disco e
ricostruisce - ma `_actionlist_anteprima` ha una cache sua, e la sua firma
guardava solo le impostazioni del brano: marker, modalita', min_gap,
esclusione ostacoli. Nessuna traccia del tuning.

Risultato: muovi lo slider, la firma non cambia, torna la coreografia di
prima. Misurato: `respiro fra colpi stesso lato` da 1.0 a 2.0 dava 279 colpi
prima e 279 dopo, agli stessi istanti al millesimo. Non riguardava un
valore, riguardava TUTTI - il pannello non ha mai rigenerato niente da
quando esiste.

E' rimasto invisibile per due giorni per una ragione precisa che vale la
pena ricordare: l'unica guardia che avevo, in test_tuning.py, verifica che i
valori arrivino alle COSTANTI dei motori. Ci arrivavano. Fra le costanti e
cio' che l'utente vede sullo schermo c'era ancora una cache, e nessun test
percorreva quel tratto.

Questo test lo percorre: chiama la funzione vera dell'app, non le sue parti.
"""
import json
import os
import sys

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (RADICE,
          os.path.join(RADICE, 'sidecar sandbox'),
          os.path.join(RADICE, 'web_migration_spike'),
          os.path.join(RADICE, 'web_migration_spike', 'genera_real')):
    sys.path.insert(0, p)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import tuning                                                   # noqa: E402
import boxvr_generator as gen                                   # noqa: E402
import brano_di_prova                                           # noqa: E402

esiti = []


def prova(ok, nome, dettaglio=''):
    esiti.append((bool(ok), nome, dettaglio))


def colpi(app, chiave):
    """Numero e istanti dei colpi che l'anteprima mostrerebbe adesso."""
    lista = app._actionlist_anteprima(chiave)
    if lista is None:
        return None
    eventi = [json.loads(a['musicActionJSON']) for a in lista['actionList']]
    mosse = [e for e in eventi if e.get('musicActiontype') == 0]
    return (len(mosse),
            tuple(round(m['startTime'], 3) for m in mosse))


def main():
    import app as genera

    chiave = 'brano_di_prova'
    analisi = gen.generate_song_analysis(
        brano_di_prova.audio_di_prova('Chop Suey!.mp3'))
    genera._analysis_cache[chiave] = {'analysis': analisi}
    genera._song_paths[chiave] = 'brano.mp3'
    genera._work_dir = RADICE

    # DEI MARKER, e non e' un dettaglio del banco di prova: senza, si passa
    # da `build_move_actions`, che il seme lo deriva da titolo|artista da
    # sempre ed e' quindi gia' ripetibile. La strada che l'08/09 pescava
    # dall'orologio e' l'altra - `build_choreography`, quella con i marker -
    # e senza marker questo test la lascerebbe fuori, dichiarandosi verde su
    # codice che non ha esercitato.
    battiti = [b['_triggerTime'] for b in analisi['beats']]
    genera._sidecar_markers[chiave] = [battiti[i] + 0.03
                                       for i in range(30, min(200, len(battiti) - 1), 2)]

    motore = gen.sidecar_engine()
    tuning.azzera_dal_vivo()
    motore.rileggi_tuning()
    fabbrica = colpi(genera, chiave)
    prova(fabbrica is not None,
          "l'anteprima si costruisce", '%d colpi' % fabbrica[0] if fabbrica else '')
    if fabbrica is None:
        return

    # ---- prima di tutto: lo stesso brano da' la stessa coreografia
    #
    # Segnalato l'08/09: «se voglio distanziare due colpi, dopo aver toccato
    # lo slider magari gli eventi si sono distanziati ma sono anche
    # cambiati». La causa era `rng = rng or random.Random()` in
    # build_choreography: seme dall'orologio, coreografia diversa a ogni
    # giro. Rende il pannello inutile - l'effetto dello slider non e'
    # distinguibile dal rumore - e rendeva irriproducibile anche la
    # generazione vera.
    genera._anteprima_choreo.clear()
    di_nuovo = colpi(genera, chiave)
    prova(di_nuovo == fabbrica,
          "lo stesso brano, rigenerato, da' la STESSA coreografia",
          "due ricostruzioni diverse: il seme non e' stabile"
          if di_nuovo != fabbrica else '%d colpi, identici' % fabbrica[0])

    # Il valore dello screenshot del 08/09: e' quello su cui l'utente ha
    # chiesto «e' corretto che non crei aggiornamenti sull'anteprima?».
    # Da 1.0 a 2.0 raddoppia il respiro fra due colpi dello stesso braccio:
    # e' un cambiamento grosso, se non si vede non lo si sta applicando.
    tuning.imposta_dal_vivo({'respiro_fra_colpi_stesso_lato': 2.0})
    motore.rileggi_tuning()
    spostato = colpi(genera, chiave)
    prova(spostato != fabbrica,
          'muovendo uno slider, la coreografia dell\'anteprima CAMBIA',
          '%d colpi di fabbrica -> %d con il respiro a 2.0'
          % (fabbrica[0], spostato[0]))
    prova(spostato[0] < fabbrica[0],
          'e cambia nel verso giusto: piu\' respiro, meno colpi',
          '%d -> %d' % (fabbrica[0], spostato[0]))

    # ---- e il cambiamento e' LOCALIZZATO, non un rimescolamento
    #
    # E' la meta' che conta della segnalazione: non basta che sia
    # deterministico, deve anche restare riconoscibile. Se muovendo uno
    # slider cambia ogni istante, chi guarda non puo' dire cosa ha fatto il
    # valore e cosa il caso.
    comuni = set(fabbrica[1]) & set(spostato[1])
    quota = len(comuni) / float(len(fabbrica[1]))
    prova(quota > 0.75,
          "e il resto della coreografia resta dov'era",
          '%d istanti su %d restano identici (%.0f%%)'
          % (len(comuni), len(fabbrica[1]), quota * 100))

    # e tornando indietro si torna esattamente da dove si era partiti: se
    # non fosse cosi', la cache starebbe accumulando stati invece di
    # seguire i valori
    tuning.azzera_dal_vivo()
    motore.rileggi_tuning()
    tornato = colpi(genera, chiave)
    prova(tornato == fabbrica,
          'e azzerando si torna ESATTAMENTE alla coreografia di partenza',
          '%d colpi' % tornato[0])

    # ---- la causa, guardata da vicino
    #
    # Non basta che il risultato cambi: se un giorno qualcuno riscrivesse la
    # firma dimenticando il tuning, i controlli qui sopra fallirebbero senza
    # dire dove guardare. Questo lo dice.
    prima = genera._firma_anteprima(chiave)
    tuning.imposta_dal_vivo({'respiro_fra_colpi_stesso_lato': 2.0})
    dopo = genera._firma_anteprima(chiave)
    prova(prima != dopo,
          'la firma della cache dell\'anteprima contiene il tuning',
          'la cache non distinguerebbe due assetti diversi' if prima == dopo
          else 'cambia con i valori, come deve')
    tuning.azzera_dal_vivo()
    motore.rileggi_tuning()

    # e la firma della tabella copre TUTTI i valori, non un elenco scritto
    # a mano che il prossimo valore aggiunto lascerebbe fuori
    f = dict(tuning.firma())
    mancanti = [k for k in tuning.VALORI if k not in f]
    prova(not mancanti,
          'e la firma della tabella copre tutti i valori regolabili',
          'fuori: %s' % mancanti if mancanti else '%d valori' % len(f))


def il_caso_vero():
    """Il percorso dell'app su un brano GIA' GENERATO, senza analisi in cache.

    E' il caso normale - la tendina dell'anteprima elenca i brani generati,
    e all'apertura del programma nessuno di quelli ha un'analisi in memoria
    - ed e' quello che i controlli qui sopra NON coprono: mettono l'analisi
    in cache a mano, cioe' simulano un brano appena aperto in analisi.

    E' costato tre giri. Dopo due correzioni con tutti i test verdi, la
    segnalazione era ancora «mi sembra che gli slider non abbiano per
    niente effetto»: sul caso provato funzionavano, su quello vero la
    rigenerazione veniva rifiutata con "Analisi del brano non ancora
    pronta". Un test che simula il caso comodo non e' un test.
    """
    import shutil
    import tempfile
    import app as genera

    d = tempfile.mkdtemp(prefix='prova_rigenera_')
    try:
        sorgente = brano_di_prova.audio_di_prova('Chop Suey!.mp3')
        dest = os.path.join(d, os.path.basename(sorgente))
        shutil.copy2(sorgente, dest)
        chiave = os.path.splitext(os.path.basename(sorgente))[0]
        genera._analysis_cache.pop(chiave, None)
        genera._work_dir = d
        genera._song_paths[chiave] = dest
        if chiave not in genera._active_ids:
            genera._active_ids.append(chiave)

        api = genera.Api()

        def eventi():
            r = api.get_action_list(chiave, True)
            if not r.get('ok'):
                return None, r.get('error')
            return tuple(round(e['time'], 3) for e in r['events']), None

        prima, errore = eventi()
        prova(prima is not None,
              "un brano generato si rigenera anche senza analisi in cache",
              errore or '%d eventi' % len(prima))
        if prima is None:
            return
        api.tuning_applica({'respiro_fra_colpi_stesso_lato': 2.0})
        dopo, errore = eventi()
        prova(dopo is not None and dopo != prima,
              'e su quel brano lo slider ha effetto, dal percorso vero '
              "dell'Api",
              errore or '%d eventi -> %d' % (len(prima), len(dopo or ())))
        api.tuning_azzera()
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    main()
    il_caso_vero()
    print("===== L'ANTEPRIMA SEGUE IL TUNING =====")
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
