"""Verifica un bug di collegamento reale trovato il 30/08 mentre si
valutava la richiesta di una "griglia magnetica" piu' ampia per i marker:
la correzione di imprecisione a 80ms (sidecar sandbox/engine.py,
_snap_marker_to_onset, `correct_imprecision`) era gia' implementata e
testata a livello di motore (sidecar sandbox/test_engine.py), ma non era
MAI stata effettivamente attivata dalle chiamate reali - ne'
boxvr_generator.generate_track (la generazione vera, quella che scrive il
file installato nel gioco) ne' _open_visual_preview nella GUI passavano
`correct_imprecision=True`. Il parametro di default e' False: senza
passarlo esplicitamente, la correzione semplicemente non girava mai."""
import os
import sys
import shutil
import tempfile
import json

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
# la radice del progetto: questo file sta in tests/
RADICE_PROGETTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brano_di_prova import audio_di_prova
import boxvr_generator as gen

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


mp3 = audio_di_prova('Chop Suey!.mp3')
analysis = gen.generate_song_analysis(mp3)
onsets = sorted(analysis.get('onsets') or [])
assert onsets, "il brano di test non ha rilevato nessun accento - impossibile verificare l'aggancio"

# un marker piazzato 40ms prima di un vero accento (dentro la finestra di
# aggancio di 80ms) - senza la correzione attiva finirebbe quasi certamente
# su un beat diverso da quello dell'accento reale piu' vicino
target_onset = onsets[len(onsets) // 2]
marker = target_onset - 0.04

import boxvr_choreo as choreo

out_dir = tempfile.mkdtemp(prefix="boxvr_marker_snap_test_")
try:
    result = gen.generate_track(mp3, out_dir, marker_times=[marker], log=lambda *a, **k: None)
    track_id = result['track_id']
    actionlist_path = os.path.join(out_dir, f"{track_id}.actionlist.json")
    check("generate_track scrive un .actionlist.json", os.path.isfile(actionlist_path))
    with open(actionlist_path, encoding='utf-8') as f:
        action_list = json.load(f)
    # formato serializzato reale (boxvr_choreo.serialize_actions): ogni mossa
    # e' un JSON annidato DENTRO una stringa ('musicActionJSON'), non un dict
    # diretto - va deserializzato un livello in piu'.
    move_times = [
        json.loads(entry['musicActionJSON'])['startTime']
        for entry in action_list['actionList']
        if entry['musicActionType'] == choreo.ACT_MOVECUE
    ]
    nearest = min(move_times, key=lambda t: abs(t - target_onset)) if move_times else None
    check(f"generate_track: la mossa piu' vicina al marker e' agganciata esattamente "
          f"all'accento reale (marker={marker:.4f}, accento={target_onset:.4f}, trovata={nearest})",
          nearest is not None and abs(nearest - target_onset) < 1e-6)
finally:
    shutil.rmtree(out_dir, ignore_errors=True)

# stessa correzione deve essere attiva anche nell'anteprima visiva della GUI,
# altrimenti anteprima e generazione reale mostrerebbero coreografie diverse
# per lo stesso brano - verificato leggendo la sorgente: e' un controllo di
# collegamento, non di comportamento (aprire davvero la finestra di anteprima
# richiederebbe un giro Tkinter completo per un guadagno marginale qui).
with open(os.path.join(RADICE_PROGETTO, 'boxvr_fixer_gui.py'), encoding='utf-8') as f:
    gui_src = f.read()
open_preview_start = gui_src.index("def _open_visual_preview")
open_preview_body = gui_src[open_preview_start:open_preview_start + 2500]
check("_open_visual_preview passa correct_imprecision=True a build_choreography",
      "correct_imprecision=True" in open_preview_body)

# slider soglia minima (30/08, "possiamo avere uno slider per la soglia?") -
# min_gap_ms deve arrivare fino a generate_track. NOTA IMPORTANTE scoperta
# scrivendo questo test: a questo tempo (~127 BPM, Chop Suey!) il vincolo
# CHE DAVVERO DOMINA per due colpi ravvicinati non e' MIN_INPUT_GAP_S (170ms,
# il filtro sui marker) ma il vincolo generale di recupero braccio di
# enforce_playability (MIN_GAP_BEATS/MIN_GAP_ARM_BEATS, boxvr_choreo.py -
# 0.5-1.0 beat, qui 236-472ms), che questo slider NON tocca (e' una regola
# universale, non specifica della sidecar). Il verificarlo end-to-end con un
# brano reale a questo tempo darebbe quindi un esito sempre uguale a
# prescindere dallo slider, non perche' lo slider non funzioni ma perche' un
# ALTRO vincolo prende il sopravvento prima - la verifica isolata del solo
# effetto di min_gap_s (senza il confondimento del tempo del brano) e' in
# sidecar sandbox/test_engine.py con beat sintetici ad alto BPM.
out_dir3 = tempfile.mkdtemp(prefix="boxvr_min_gap_wiring_")
try:
    res_min_gap = gen.generate_track(mp3, out_dir3, marker_times=[10.0, 10.1], min_gap_ms=50,
                                      log=lambda *a, **k: None)
    check("generate_track accetta min_gap_ms senza sollevare eccezioni",
          res_min_gap is not None and 'track_id' in res_min_gap)
finally:
    shutil.rmtree(out_dir3, ignore_errors=True)

print(f"\n{'====================================================' }")
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
