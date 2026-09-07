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

"""La tabella di tuning fa quello che promette?

Quattro promesse, e la terza e' quella che conta piu' di tutte:

  1. un valore valido viene applicato
  2. un valore assurdo viene RIFIUTATO, e lo dice - non ignorato in silenzio
  3. i valori regolabili arrivano davvero alle costanti dei motori: una
     tabella che non e' collegata e' peggio di nessuna tabella, perche' fa
     credere di aver cambiato qualcosa
  4. senza il file, tutto resta esattamente di fabbrica

Il file di prova si scrive in una cartella temporanea e `tuning` ci viene
puntato: quello dell'autore, se esiste, non si tocca.
"""
import importlib
import json
import os
import shutil
import sys
import tempfile

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra.
RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RADICE)
sys.path.insert(0, os.path.join(RADICE, 'sidecar sandbox'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import tuning                                                   # noqa: E402

esiti = []


def prova(ok, nome, dettaglio=''):
    esiti.append((bool(ok), nome, dettaglio))


def con_file(contenuto):
    """Ricarica `tuning` puntandolo a una cartella con questo tuning.json."""
    d = tempfile.mkdtemp(prefix='prova_tuning_')
    if contenuto is not None:
        with open(os.path.join(d, tuning.NOME_FILE), 'w', encoding='utf-8') as f:
            json.dump(contenuto, f)
    tuning._cartella = lambda: d
    tuning._caricato = None
    tuning._problemi = []
    return d


def main():
    # ------------------------------------------------- 1. valore valido
    d = con_file({'respiro_dopo_swing_altro_lato': 1.1})
    prova(tuning.valore('respiro_dopo_swing_altro_lato') == 1.1,
          'un valore valido viene applicato',
          'letto %s' % tuning.valore('respiro_dopo_swing_altro_lato'))
    prova(tuning.valore('respiro_minimo') == tuning.VALORI['respiro_minimo'][0],
          'e gli altri restano di fabbrica')
    shutil.rmtree(d, ignore_errors=True)

    # ------------------------------ 2. valori assurdi: rifiutati E detti
    d = con_file({
        'quota_ganci_bassi': 5.0,          # fuori intervallo
        'respiro_minimo': 'tanto',         # non un numero
        'valore_inventato': 3,             # non esiste
    })
    prova(tuning.valore('quota_ganci_bassi') == tuning.VALORI['quota_ganci_bassi'][0],
          'un valore fuori intervallo NON viene applicato',
          'resta %s' % tuning.valore('quota_ganci_bassi'))
    p = tuning.problemi()
    prova(len(p) == 3, 'e ciascun problema viene DETTO, non ingoiato',
          '%d messaggi: %s' % (len(p), ' | '.join(x[:60] for x in p)))
    prova(any('0.35' in x for x in p),
          "il messaggio dice l'intervallo ammesso, non solo che e' sbagliato",
          [x for x in p if 'quota_ganci' in x][:1])
    shutil.rmtree(d, ignore_errors=True)

    # --------------- 3. i valori ARRIVANO DAVVERO dentro i motori
    d = con_file({
        'respiro_dopo_swing_altro_lato': 1.4,
        'quota_ganci_bassi': 0.33,
        'catena_massima_di_squat': 2,
        'soglia_fra_i_tuoi_colpi_ms': 250,
        'estendi_secondi_minimi': 60.0,
    })
    for nome in ('boxvr_choreo', 'engine'):
        sys.modules.pop(nome, None)
    import boxvr_choreo as choreo
    import engine
    prova(choreo.MIN_GAP_AFTER_SWING_OPPOSITE_BEATS == 1.4,
          'il respiro dopo uno swing arriva a boxvr_choreo',
          'costante = %s' % choreo.MIN_GAP_AFTER_SWING_OPPOSITE_BEATS)
    prova(abs(choreo.QUOTA_CORSIA_BASSA[choreo.MOVE_HOOK] - 0.33) < 1e-9,
          'la quota dei ganci bassi pure',
          'quota = %s' % choreo.QUOTA_CORSIA_BASSA[choreo.MOVE_HOOK])
    prova(choreo.MAX_SQUAT_CHAIN == 2,
          'e la catena massima di squat')
    prova(abs(engine.MIN_INPUT_GAP_S - 0.250) < 1e-9,
          'la soglia fra i colpi arriva a engine, convertita in secondi',
          '%s s' % engine.MIN_INPUT_GAP_S)
    prova(engine.EXTEND_MIN_COVERAGE_S == 60.0,
          'e la soglia di Estendi')

    # e il comportamento cambia davvero, non solo la costante
    prova(choreo._required_gap_beats(
        {'moveType': choreo.MOVE_HOOK, 'moveChannel': choreo.CH_FRONT},
        {'moveType': choreo.MOVE_JAB, 'moveChannel': choreo.CH_BACK}) == 1.4,
        "e la REGOLA lo usa, non e' solo un numero in un modulo")
    shutil.rmtree(d, ignore_errors=True)

    # ------------------------------------- 4. senza il file, di fabbrica
    d = con_file(None)
    for nome in ('boxvr_choreo', 'engine'):
        sys.modules.pop(nome, None)
    import boxvr_choreo as choreo2
    prova(not tuning.modificati() and not tuning.problemi(),
          'senza il file non c\'e\' niente di modificato e niente da dire')
    prova(choreo2.MIN_GAP_AFTER_SWING_OPPOSITE_BEATS
          == tuning.VALORI['respiro_dopo_swing_altro_lato'][0],
          'e le costanti tornano di fabbrica')

    # ------------------------------ 5. il file di esempio e' completo
    percorso = tuning.scrivi_esempio(d)
    with open(percorso, encoding='utf-8') as f:
        esempio = json.load(f)
    mancanti = [k for k in tuning.VALORI if k not in esempio]
    prova(not mancanti,
          'il file di esempio contiene TUTTI i valori regolabili',
          'mancano: %s' % mancanti if mancanti else '%d valori' % len(tuning.VALORI))
    senza_prov = [k for k in tuning.VALORI if '_' + k not in esempio]
    prova(not senza_prov,
          'e ognuno ha accanto la sua spiegazione e provenienza',
          'senza: %s' % senza_prov if senza_prov else '')
    shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    main()
    print('===== LA TABELLA DI TUNING =====')
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
