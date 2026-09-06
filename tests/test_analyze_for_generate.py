"""Test di analyze_for_generate: la decisione "quale motore usare" tirata
fuori da _background_analysis_loop (boxvr_fixer_gui.py). Finto generate_song_analysis
e finto is_madmom_available, cosi' si verifica la DECISIONE senza mai
analizzare un audio vero - prima non era testabile senza aprire una finestra
e aspettare un'analisi reale.
"""
import os
import sys

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boxvr_generator as g

ok = fail = 0


def check(desc, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK   {desc}")
    else:
        fail += 1
        print(f"  FAIL {desc}")


def fake_beats(n, spacing, duration=None):
    # duration di default = subito dopo l'ultimo beat, cosi' il controllo di
    # copertura aggiunto il 25/08 (analyze_for_generate.tail_gap) non scatta
    # per caso nei test che non lo stanno esercitando apposta
    last_t = (n - 1) * spacing if n else 0.0
    return {'beats': [{'_triggerTime': i * spacing} for i in range(n)],
            'native_audio': None, 'sr': None,
            'duration': duration if duration is not None else last_t + spacing}


def patch(monkeypatch_calls, madmom_available, beats_by_engine, raise_on_madmom=None):
    """madmom_available: bool. beats_by_engine: {'librosa': analysis, 'madmom': analysis}.
    raise_on_madmom: se dato, generate_song_analysis(beat_engine='madmom') solleva questo."""
    def fake_generate(audio_path, forced_bpm=None, beat_engine='librosa'):
        monkeypatch_calls.append(beat_engine)
        if beat_engine == 'madmom' and raise_on_madmom is not None:
            raise raise_on_madmom
        return beats_by_engine[beat_engine]
    g.generate_song_analysis = fake_generate
    g.is_madmom_available = lambda: madmom_available


real_generate = g.generate_song_analysis
real_is_madmom = g.is_madmom_available
real_recommend = g.recommend_engine_from_beats


def restore():
    g.generate_song_analysis = real_generate
    g.is_madmom_available = real_is_madmom
    g.recommend_engine_from_beats = real_recommend


print("auto - griglia librosa ECCEZIONALMENTE pulita -> resta su librosa, niente escalation")
calls = []
try:
    # spaziatura beat perfettamente regolare -> std vicino a 0, ben sotto FAST_PATH_STABILITY_THRESHOLD
    patch(calls, madmom_available=True,
          beats_by_engine={'librosa': fake_beats(60, 0.5), 'madmom': fake_beats(60, 0.5)})
    out = g.analyze_for_generate('finto.mp3', engine_mode='auto')
    check("chiama SOLO librosa, mai madmom", calls == ['librosa'])
    check("engine_used = librosa", out['engine_used'] == 'librosa')
    check("stability_std valorizzato", out['stability_std'] is not None and out['stability_std'] < 3.0)
    check("non sospetto", out['suspicious'] is False)
finally:
    restore()

print("\nauto - griglia PULITA ma con un buco di coda vero -> escalation a madmom lo stesso"
      " (25/08, il caso Believer: la sola stabilita' non basta)")
calls = []
try:
    # stessa griglia regolare di sopra (std ~0, resterebbe su librosa per la
    # sola stabilita'), ma la durata reale del brano e' molto oltre l'ultimo
    # beat rilevato - deve scattare comunque
    librosa_beats = fake_beats(60, 0.5)               # ultimo beat a 29.5s, duration a 30.0s di default
    librosa_beats['duration'] = 60.0                  # ma il brano dura davvero 60s: buco di 30s
    patch(calls, madmom_available=True,
          beats_by_engine={'librosa': librosa_beats, 'madmom': fake_beats(120, 0.5)})
    out = g.analyze_for_generate('finto.mp3', engine_mode='auto')
    check("prova prima librosa", calls[0] == 'librosa')
    check("scala a madmom nonostante la griglia sembri pulita", 'madmom' in calls)
    check("engine_used = madmom", out['engine_used'] == 'madmom')
finally:
    restore()

print("\nauto - griglia pulita, coda breve legittima (fade-out) -> NESSUNA escalation")
calls = []
try:
    librosa_beats = fake_beats(60, 0.5)
    librosa_beats['duration'] = 33.0   # 3.5s di coda: sotto COVERAGE_GAP_THRESHOLD_S, non deve scattare
    patch(calls, madmom_available=True,
          beats_by_engine={'librosa': librosa_beats, 'madmom': fake_beats(60, 0.5)})
    out = g.analyze_for_generate('finto.mp3', engine_mode='auto')
    check("resta su librosa, una coda breve e' normale", out['engine_used'] == 'librosa')
    check("non richiama madmom", calls == ['librosa'])
finally:
    restore()

print("\nauto - griglia instabile -> escalation a madmom")
calls = []
try:
    import random
    random.seed(1)
    # spaziatura irregolare -> std alto, sopra la soglia fast-path
    times, t = [], 0.0
    for _ in range(60):
        t += 0.5 + random.uniform(-0.15, 0.15)
        times.append(t)
    beats = {'beats': [{'_triggerTime': x} for x in times], 'native_audio': None, 'sr': None,
             'duration': t + 0.5}
    patch(calls, madmom_available=True,
          beats_by_engine={'librosa': beats, 'madmom': fake_beats(60, 0.5)})
    out = g.analyze_for_generate('finto.mp3', engine_mode='auto')
    check("prova prima librosa", calls[0] == 'librosa')
    check("poi rifa' con madmom", 'madmom' in calls)
    check("engine_used = madmom", out['engine_used'] == 'madmom')
finally:
    restore()

print("\nauto - madmom scelto ma fallisce su QUESTO brano -> ripiega su librosa, non perde l'analisi")
calls = []
fallback_msgs = []
try:
    import random
    random.seed(1)
    times, t = [], 0.0
    for _ in range(60):
        t += 0.5 + random.uniform(-0.15, 0.15)
        times.append(t)
    beats = {'beats': [{'_triggerTime': x} for x in times], 'native_audio': None, 'sr': None,
             'duration': t + 0.5}
    patch(calls, madmom_available=True,
          beats_by_engine={'librosa': beats}, raise_on_madmom=g.MadmomUnavailableError("crash simulato"))
    out = g.analyze_for_generate('finto.mp3', engine_mode='auto', on_fallback=fallback_msgs.append)
    check("il risultato e' comunque presente (l'analisi librosa gia' fatta)", out['analysis'] is beats)
    check("engine_used ripiegato su librosa", out['engine_used'] == 'librosa')
    check("il chiamante viene avvisato del ripiego", len(fallback_msgs) == 1 and "crash simulato" in fallback_msgs[0])
finally:
    restore()

print("\nauto - madmom NON disponibile in questa build -> non lo prova nemmeno")
calls = []
try:
    patch(calls, madmom_available=False, beats_by_engine={'librosa': fake_beats(60, 0.5)})
    out = g.analyze_for_generate('finto.mp3', engine_mode='auto')
    check("chiama solo librosa (madmom manco tentato)", calls == ['librosa'])
    check("engine_used = librosa", out['engine_used'] == 'librosa')
    check("stability_std/suspicious non calcolati (nessuna decisione presa)",
          out['stability_std'] is None and out['suspicious'] is False)
finally:
    restore()

print("\nmanuale - usa il motore scelto dall'utente, nessuna decisione")
calls = []
try:
    patch(calls, madmom_available=True,
          beats_by_engine={'madmom': fake_beats(60, 0.5)})
    out = g.analyze_for_generate('finto.mp3', engine_mode='manual', beat_engine='madmom')
    check("chiama SOLO madmom (nessun pre-check librosa)", calls == ['madmom'])
    check("engine_used = madmom", out['engine_used'] == 'madmom')
    check("stability_std/suspicious non calcolati", out['stability_std'] is None and out['suspicious'] is False)
finally:
    restore()

print("\nmanuale - madmom scelto a mano ma fallisce -> ripiega su librosa")
calls = []
fallback_msgs = []
try:
    patch(calls, madmom_available=True,
          beats_by_engine={'librosa': fake_beats(60, 0.5)},
          raise_on_madmom=g.MadmomUnavailableError("madmom_worker.exe mancante"))
    out = g.analyze_for_generate('finto.mp3', engine_mode='manual', beat_engine='madmom',
                                   on_fallback=fallback_msgs.append)
    check("prova madmom, poi ripiega su librosa", calls == ['madmom', 'librosa'])
    check("engine_used ripiegato su librosa", out['engine_used'] == 'librosa')
    check("il chiamante viene avvisato", len(fallback_msgs) == 1)
finally:
    restore()

print(f"\n{'=' * 50}\n{ok} passati, {fail} falliti")
sys.exit(1 if fail else 0)
