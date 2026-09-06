"""Verifica i due bug reali trovati il 25/08 confrontando la nostra
coreografia con una mappa BeatSaver vera (Believer - Imagine Dragons):

1. build_segments() estendeva _length dell'ultimo segmento fino alla fine
   del brano (per superare find_no_coverage_gaps) ma non aggiornava
   _numBeats, che e' il campo che build_move_actions usa DAVVERO - la
   coreografia si fermava comunque, silenziosamente, dove si fermava
   l'ultimo confine strutturale rilevato.
2. librosa.beat.beat_track puo' smettere di produrre beat prima della fine
   del brano (anche durante il passaggio piu' energico dell'intero brano,
   non un fade-out) - una griglia "stabile" ma incompleta superava il
   controllo di qualita' esistente (beat_grid_stability), che misura solo
   la regolarita' di CIO' CHE C'E', non se manca un pezzo alla fine.
"""
import os
import sys

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brano_di_prova import audio_di_prova
import boxvr_generator as gen
import boxvr_choreo as m

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


print("1. build_segments: l'ultimo segmento copre DAVVERO fino alla fine (non solo _length)")
import numpy as np
bpm = 120.0
beat_len = 60.0 / bpm
n_beats = 40
beats = [{'_triggerTime': i * beat_len, '_beatLength': beat_len, '_index': i,
          '_beatInBar': (i % 4) + 1, '_bpm': bpm, '_isLastBeat': False, '_magnitude': 0.5}
         for i in range(n_beats)]
bars = [{'_beatIndex': i, '_startTime': beats[i]['_triggerTime']} for i in range(0, n_beats, 4)]
bar_score = [0.5] * len(bars)
# durata VOLUTAMENTE piu' lunga dell'ultimo beat rilevato, come nel caso reale
duration = n_beats * beat_len + 15.0
segs = gen.build_segments(bars, beats, bar_score, duration, boundary_bars=None)
last = segs[-1]
real_end_from_numbeats = beats[last['_startBeatIndex']]['_triggerTime'] + last['_numBeats'] * beat_len
check(f"_length dell'ultimo segmento arriva alla durata ({last['_startTime'] + last['_length']:.2f} ~= {duration:.2f})",
      abs((last['_startTime'] + last['_length']) - duration) < 0.01)
check(f"_numBeats dell'ultimo segmento arriva ANCH'ESSO alla durata reale (fine calcolata da _numBeats: "
      f"{real_end_from_numbeats:.2f}, ultimo beat disponibile: {beats[-1]['_triggerTime'] + beat_len:.2f})",
      last['_startBeatIndex'] + last['_numBeats'] == n_beats)

print("\n2. Integrazione: build_move_actions copre fino all'ultimo beat vero, non si ferma prima")
segs_for_analysis = segs
analysis = {'beats': beats, 'segs': segs_for_analysis, 'bars': bars, 'bar_score': bar_score,
            'duration': duration, 'bpm': bpm, 'name': 'test', 'artist': 'test',
            'rhythm_events': [], 'rhythm_density': None}
actions = m.build_move_actions(analysis, preset='medium')
last_action_beat_idx = max((a['beatNumber'] for a in actions), default=0)
check(f"almeno un'azione arriva vicino all'ultimo beat disponibile (trovato beatNumber max {last_action_beat_idx:.1f} su {n_beats-1})",
      last_action_beat_idx > n_beats * 0.7)  # tollerante: dipende dal pattern scelto, ma deve avvicinarsi

print("\n3. analyze_for_generate: sceglie madmom quando librosa lascia un buco di coda, anche se la griglia sembra 'pulita'")
if gen.is_madmom_available():
    result = gen.analyze_for_generate(audio_di_prova('Believer.mp3'), engine_mode='auto')
    check(f"motore scelto = madmom (stability_std era {result['stability_std']:.2f}, "
          f"sotto la soglia veloce {gen.FAST_PATH_STABILITY_THRESHOLD} - la sola stabilita' non l'avrebbe presa)",
          result['engine_used'] == 'madmom')
    a = result['analysis']
    tail_gap = a['duration'] - a['beats'][-1]['_triggerTime']
    check(f"il buco di coda ora e' sotto la soglia ({tail_gap:.2f}s < {gen.COVERAGE_GAP_THRESHOLD_S}s)",
          tail_gap < gen.COVERAGE_GAP_THRESHOLD_S)
    actions = m.build_move_actions(a, preset='medium')
    tail_actions = [act for act in actions if act['startTime'] > 190]
    check(f"la coreografia reale ha mosse dopo t=190s (trovate {len(tail_actions)}, prima del fix erano 0)",
          len(tail_actions) > 0)
else:
    print("  (madmom non disponibile in questo ambiente, test 3 saltato)")

print("\n" + "=" * 52)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
