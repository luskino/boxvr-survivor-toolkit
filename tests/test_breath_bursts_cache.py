"""Verifica la cache di detect_breath_and_bursts (30/08, trovata cercando di
velocizzare l'analisi): a differenza della segmentazione strutturale,
QUESTA non e' un compromesso qualita'/velocita' - detect_breath_and_bursts
dipende SOLO da (mono_audio, sr), mai da BPM/beat_engine, eppure una
correzione di BPM (_apply_forced_bpm) invalidava l'intera analisi e la
rifaceva da zero, ricalcolando hpss (l'80% del tempo su un brano lungo) per
un risultato che sarebbe stato IDENTICO."""
import sys
import os
import time
import json

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
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

# pulizia: rimuove un'eventuale cache gia' presente da una sessione precedente,
# cosi' la prima chiamata di questo test e' garantita un vero cache-miss
key = gen.audio_cache_key(mp3)
cache_path = os.path.join(gen.sections_cache_dir(), f"breath_{key}.json")
if os.path.isfile(cache_path):
    os.remove(cache_path)

check("nessuna cache presente all'inizio del test", not os.path.isfile(cache_path))

t0 = time.perf_counter()
analysis_a = gen.generate_song_analysis(mp3, structural_segments=False)
t_first = time.perf_counter() - t0
check(f"prima chiamata (cache-miss): la cache viene scritta su disco "
      f"(impiegata {t_first:.1f}s)", os.path.isfile(cache_path))

# una CORREZIONE DI BPM (forced_bpm diverso) invalida l'intera analisi e la
# rifa' da zero in _apply_forced_bpm - qui si simula lo stesso richiamando
# generate_song_analysis con un forced_bpm diverso, stesso file audio
t0 = time.perf_counter()
analysis_b = gen.generate_song_analysis(mp3, structural_segments=False,
                                         forced_bpm=round(analysis_a['bpm']) + 5)
t_second = time.perf_counter() - t0
check(f"seconda chiamata (BPM diverso, stesso audio) e' NETTAMENTE piu' veloce "
      f"grazie alla cache (prima={t_first:.1f}s, seconda={t_second:.1f}s, "
      f"{t_first / max(t_second, 0.001):.1f}x)", t_second < t_first / 3)

check(f"gli eventi respiro/raffica/veloce sono IDENTICI fra le due chiamate "
      f"(prima {len(analysis_a['rhythm_events'])}, seconda {len(analysis_b['rhythm_events'])})",
      analysis_a['rhythm_events'] == analysis_b['rhythm_events'])
check(f"gli onset sono IDENTICI fra le due chiamate "
      f"(prima {len(analysis_a['onsets'])}, seconda {len(analysis_b['onsets'])})",
      analysis_a['onsets'] == analysis_b['onsets'])

# round-trip di lettura/scrittura della cache in isolamento
events = [{'type': 'breath', 'start': 1.0, 'end': 2.0}]
centers = [0.0, 0.1, 0.2]
density = [0.0, 1.0, 2.0]
onsets = [0.5, 1.5]
gen.save_cached_breath_bursts("test_roundtrip_key", events, centers, density, onsets)
loaded = gen.load_cached_breath_bursts("test_roundtrip_key")
check("round-trip: eventi identici dopo salvataggio/lettura", loaded[0] == events)
check("round-trip: centers/density/onsets identici (con tolleranza float)",
      list(loaded[1]) == centers and list(loaded[2]) == density and loaded[3] == onsets)
os.remove(os.path.join(gen.sections_cache_dir(), "breath_test_roundtrip_key.json"))

check("chiave vuota: nessuna eccezione, nessun file scritto",
      gen.save_cached_breath_bursts(None, events, centers, density, onsets) is None)
check("chiave sconosciuta: nessuna eccezione, ritorna None",
      gen.load_cached_breath_bursts("chiave_mai_vista_xyz") is None)

print(f"\n{'====================================================' }")
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
