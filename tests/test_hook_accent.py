"""Verifica il nuovo accento di ganci (_hook_accent / _apply_section_accents),
aggiunto 2026-08-24 come priorita' #1 di DA FARE in STATO E ROADMAP.md: figure
di ganci oltre alle raffiche di diretti, ancorate ai salti di intensita' fra
segmenti invece che agli eventi audio.

Non richiede il visore per la correttezza MECCANICA (griglia, distanza minima,
non-sovrapposizione con le figure di diretti gia' esistenti) - quella e'
verificabile qui. Se "diverte" o no resta un giudizio da dare in VR, come
tutto il resto della coreografia."""
import random
import sys

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
import os
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brano_di_prova import audio_di_prova
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


def make_beats(n, bpm=120.0):
    beat_len = 60.0 / bpm
    return [{'_triggerTime': i * beat_len, '_index': i, '_beatInBar': (i % 4) + 1,
             '_beatLength': beat_len, '_bpm': bpm, '_isLastBeat': False, '_magnitude': 0.5}
            for i in range(n)]


print("1. _hook_accent: forma della figura")
beats = make_beats(40)
fig = m._hook_accent(beats, t_start=0.0, n=3, start_side=0)
check("produce 3 colpi come richiesto", len(fig) == 3)
# Dal 26/08 non piu' SEMPRE Hook: solo il primo (la sua identita', l'accento
# che apre) e' fisso, i successivi sono campionati da ARM_TRANSITION_PROBS -
# vedi la correzione "quale mossa esatta, in che sequenza" in STATO E ROADMAP.md.
check("il primo colpo e' sempre Hook (l'identita' dell'accento)", fig[0]['moveType'] == m.MOVE_HOOK)
check("tutti i colpi sono di braccia (Jab/Hook/Uppercut)",
      all(a['moveType'] in m.ARM_MOVES for a in fig))
check("tutti marcati _protected", all(a.get('_protected') for a in fig))
# Il LATO, non la corsia esatta: da quando un gancio puo' essere basso
# lo stesso lato si scrive 0 oppure 1, e i canali vanno a coppie (0/1 un
# lato, 4/5 l'altro) - la stessa divisione per due che fa _same_side.
lati = [a['moveChannel'] // 2 for a in fig]
corsie = [a['moveChannel'] for a in fig]
check(f"lati alternati (lati {lati}, corsie {corsie})",
      lati == [m.CH_FRONT // 2, m.CH_BACK // 2, m.CH_FRONT // 2])
check("e le corsie sono quelle ammesse per quel lato",
      all(a['moveChannel'] // 2 == l for a, l in zip(fig, lati)))
gaps = [round((fig[i + 1]['startTime'] - fig[i]['startTime']) / (60.0 / 120.0), 3)
        for i in range(len(fig) - 1)]
check(f"distanza di {m._HOOK_ACCENT_GAP_BEATS} beat fra un gancio e il successivo (misurato {gaps})",
      all(g == m._HOOK_ACCENT_GAP_BEATS for g in gaps))

print("\n2. _hook_accent: aggancio alla griglia (attacco fuori tempo)")
fig2 = m._hook_accent(beats, t_start=0.13, n=2, start_side=0)  # vicino al mezzo beat (0.125)
grid = set(round(g, 6) for g in m._grid_times(beats))
check("primo gancio agganciato a un punto di griglia valido",
      round(fig2[0]['startTime'], 6) in grid)
check("secondo gancio agganciato a un punto di griglia valido",
      round(fig2[1]['startTime'], 6) in grid)

print("\n3. _apply_section_accents: si innesca sulle SALITE di intensita'")
segs = [
    {'_index': 0, '_startBeatIndex': 0, '_numBeats': 8},
    {'_index': 1, '_startBeatIndex': 8, '_numBeats': 8},   # sale -> accento atteso
    {'_index': 2, '_startBeatIndex': 16, '_numBeats': 8},  # scende -> nessun accento
    {'_index': 3, '_startBeatIndex': 24, '_numBeats': 8},  # risale -> accento atteso
]
intensities = [2, 4, 1, 3]
beats2 = make_beats(40)
rng = random.Random(1)
out = m._apply_section_accents([], segs, intensities, beats2, preset='medium', rng=rng)
# Dal 26/08 i colpi dell'accento non sono piu' tutti Hook (vedi test 1) -
# si identificano per tag di provenienza, non per tipo.
hooks = [a for a in out if a.get('_figure') == 'hook_accent']
n_expected_accents = 3  # segmento 0 (prima sezione attiva) + segmento 1 (salita) + segmento 3 (risalita)
check(f"un accento sulla prima sezione attiva e su ogni salita ({n_expected_accents} accenti x "
      f"{m._HOOK_ACCENT_LENGTH['medium']} colpi = {n_expected_accents * m._HOOK_ACCENT_LENGTH['medium']} attesi, trovati {len(hooks)})",
      len(hooks) == n_expected_accents * m._HOOK_ACCENT_LENGTH['medium'])
starts = sorted(set(round(h['startTime'], 3) for h in hooks))
seg2_start_t = beats2[16]['_triggerTime']
check("nessun gancio ancorato al segmento 2 (che SCENDE di intensita')",
      not any(abs(s - seg2_start_t) < 0.01 for s in starts))

print("\n4. _apply_section_accents: rispetta il limite di preset senza ganci (ipotetico)")
out_none = m._apply_section_accents([], segs, intensities, beats2, preset='nonexistent_preset', rng=random.Random(1))
check("preset sconosciuto (nessuna mossa ammessa risolta) non inietta nulla",
      not any(a.get('_figure') == 'hook_accent' for a in out_none))

print("\n5. Integrazione end-to-end: enforce_playability non rompe gli accenti")
base_actions = out  # dal test 3, gia' con gli accenti iniettati
final = m.enforce_playability(base_actions, beats2)
final_hooks = sorted([a for a in final if a.get('_figure') == 'hook_accent'], key=lambda a: a['startTime'])
check("tutti i colpi dell'accento sopravvivono a enforce_playability (nessuno scartato)",
      len(final_hooks) == len(hooks))
grid2 = set(round(g, 6) for g in m._grid_times(beats2))
check("tutti i ganci restano sulla griglia dopo enforce_playability",
      all(round(h['startTime'], 6) in grid2 for h in final_hooks))
# verifica distanza minima rispettata fra OGNI coppia consecutiva di braccia nel risultato finale
all_arms = sorted([a for a in final if a['moveType'] in m.ARM_MOVES], key=lambda a: a['startTime'])
beat_len = 60.0 / 120.0
violations = []
for i in range(len(all_arms) - 1):
    p, c = all_arms[i], all_arms[i + 1]
    need = m._required_gap_beats(p, c)
    gap = (c['startTime'] - p['startTime']) / beat_len
    if gap < need - 1e-6:
        violations.append((p['moveType'], c['moveType'], gap, need))
check(f"nessuna violazione di recupero minimo nel risultato finale misto (trovate {len(violations)}: {violations[:3]})",
      not violations)

print("\n6. Coreografia reale (build_move_actions) con gli accenti attivi")
import boxvr_generator as gen
mp3_candidates = [
    audio_di_prova('Chop Suey!.mp3'),
]
import os
mp3 = next((p for p in mp3_candidates if os.path.exists(p)), None)
if mp3:
    analysis = gen.generate_song_analysis(mp3)
    actions = m.build_move_actions(analysis, preset='medium')
    hooks_real = [a for a in actions if a['moveType'] == m.MOVE_HOOK]
    check(f"la coreografia reale contiene ganci (trovati {len(hooks_real)} su {len(actions)} azioni totali)",
          len(hooks_real) > 0)
    # Dal 25/08 sera NON e' piu' vero che ogni azione finale sta sulla griglia
    # per costruzione: quelle ancorate a un accento reale (_place_moves_on_onsets
    # / _snap_to_onsets) restano di proposito sull'istante vero, altrimenti
    # enforce_playability le rimetterebbe silenziosamente sulla griglia - il
    # bug appena corretto. L'invariante giusta ora e' piu' ampia: ogni azione
    # sta O sulla griglia O su un accento reale rilevato, mai a un istante
    # campato in aria.
    grid3 = set(round(g, 6) for g in m._grid_times(analysis['beats']))
    onsets3 = set(round(t, 6) for t in (analysis.get('onsets') or []))
    fuori_da_entrambi = [a for a in actions
                         if round(a['startTime'], 6) not in grid3
                         and round(a['startTime'], 6) not in onsets3]
    check(f"ogni azione sta sulla griglia o su un accento reale "
          f"(fuori da entrambi: {len(fuori_da_entrambi)})",
          not fuori_da_entrambi)
    fuori_griglia = [a for a in actions if round(a['startTime'], 6) not in grid3]
    print(f"      (per riferimento: {len(fuori_griglia)}/{len(actions)} azioni "
          f"ancorate a un accento reale invece che alla griglia)")
else:
    print("  (saltato: mp3 di prova non trovato)")

print("\n7. Figura di CHIUSURA sezione (26/08, DA FARE #2 della roadmap)")
segs7 = [
    {'_index': 0, '_startBeatIndex': 0, '_numBeats': 16},   # sale (prima sezione) -> apertura
    {'_index': 1, '_startBeatIndex': 16, '_numBeats': 16},  # scende -> chiusura sul segmento 0
    {'_index': 2, '_startBeatIndex': 32, '_numBeats': 16},  # silenzio vero -> interrompe la sequenza
    {'_index': 3, '_startBeatIndex': 48, '_numBeats': 8},   # riparte dopo il silenzio -> apertura, non chiusura
]
intensities7 = [3, 2, 0, 4]
beats7 = make_beats(60)
out7 = m._apply_section_accents([], segs7, intensities7, beats7, preset='medium', rng=random.Random(1))
opens7 = [a for a in out7 if a.get('_figure') == 'hook_accent']
closes7 = [a for a in out7 if a.get('_figure') == 'section_close']
check(f"la chiusura punteggia la FINE della sezione 0 (intensita' in calo), non l'inizio "
      f"della sezione 1 (trovati {sorted(round(a['startTime'],2) for a in closes7)}, attesi [6.0, 8.0])",
      sorted(round(a['startTime'], 2) for a in closes7) == [6.0, 8.0])
check(f"l'ultimo colpo della chiusura arriva ESATTAMENTE al confine (beat 16 = 8.0s, "
      f"l'inizio della sezione che sta scendendo)",
      max(a['startTime'] for a in closes7) == beats7[16]['_triggerTime'])
check("nessuna chiusura per la sezione 1 quando sfuma nel silenzio vero (segmento 1->2, "
      f"si aspetterebbe vicino a t=16.0s se ci fosse, trovate chiusure a {sorted(round(a['startTime'],2) for a in closes7)})",
      not any(13.0 <= s <= 19.0 for s in [round(a['startTime'], 2) for a in closes7]))
check(f"dopo il silenzio, la sezione 3 riceve un'APERTURA (prima sezione attiva 'nuova'), "
      f"non una chiusura (trovate {sorted(round(a['startTime'],2) for a in opens7)})",
      24.0 in [round(a['startTime'], 2) for a in opens7])
check("le figure di chiusura sono marcate _protected come le altre",
      all(a.get('_protected') for a in closes7))
final7 = m.enforce_playability(list(out7), beats7)
n_accents_before = len(opens7) + len(closes7)
n_accents_after = len([a for a in final7 if a.get('_figure') in ('hook_accent', 'section_close')])
check(f"apertura e chiusura sopravvivono entrambe a enforce_playability "
      f"(prima {n_accents_before}, dopo {n_accents_after})",
      n_accents_after == n_accents_before)

print("\n" + "=" * 52)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
