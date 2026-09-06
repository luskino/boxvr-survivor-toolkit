"""Verifica la terza famiglia di figure (ritmi euclidei/Bjorklund),
2026-08-24: correttezza dell'algoritmo contro pattern noti, e che il
catalogo _EUCLIDEAN_PATTERNS rispetti DAVVERO i vincoli di giocabilita'
gia' misurati (MIN_GAP_ARM_BEATS), non per supposizione ma calcolato."""
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


print("1. Bjorklund: correttezza contro pattern noti (verificati contro l'implementazione di riferimento)")
KNOWN = {
    (3, 8): [1, 0, 0, 1, 0, 0, 1, 0],   # tresillo
    (5, 8): [1, 0, 1, 1, 0, 1, 1, 0],
    (2, 5): [1, 0, 1, 0, 0],            # shiko
    (2, 3): [1, 1, 0],
    (7, 16): [1, 0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0, 0, 1, 0],
    (2, 4): [1, 0, 1, 0],
}
for (k, n), expected in KNOWN.items():
    got = m._bjorklund(k, n)
    check(f"E({k},{n}) = {expected}", got == expected)

check("E(0,8) = tutto silenzio", m._bjorklund(0, 8) == [0] * 8)
check("E(8,8) = tutto pieno", m._bjorklund(8, 8) == [1] * 8)

print("\n2. Catalogo _EUCLIDEAN_PATTERNS: rispetta DAVVERO MIN_GAP_ARM_BEATS")
for name, spec in m._EUCLIDEAN_PATTERNS.items():
    gap = m._euclidean_pattern_gap_beats(name)
    check(f"'{name}' E({spec['k']},{spec['n']}) @ {spec['beat_per_step']} beat/passo: "
          f"scarto minimo {gap:.2f} beat >= {m.MIN_GAP_ARM_BEATS} (MIN_GAP_ARM_BEATS)",
          gap >= m.MIN_GAP_ARM_BEATS - 1e-9)

print("\n3. _euclidean_figure: forma e aggancio alla griglia")
beats = make_beats(60)
for name, spec in m._EUCLIDEAN_PATTERNS.items():
    fig = m._euclidean_figure(beats, t_start=0.0, pattern_name=name, start_side=0)
    n_expected = spec['k']
    check(f"'{name}': {n_expected} colpi prodotti (trovati {len(fig)})", len(fig) == n_expected)
    check(f"'{name}': tutti marcati _protected", all(a.get('_protected') for a in fig))
    grid = set(round(g, 6) for g in m._grid_times(beats))
    check(f"'{name}': tutti sulla griglia", all(round(a['startTime'], 6) in grid for a in fig))
    # Dal 26/08 l'accento non e' piu' SEMPRE Hook: viene campionato fra i due
    # colpi ampi (Hook/Uppercut, _EUCLIDEAN_ACCENT_PROBS) per dare varieta' e
    # ridurre la sovra-rappresentazione del gancio misurata contro BoxVR vero.
    # L'invariante giusta ora e' "colpo AMPIO sull'accento, Jab sul
    # riempimento", non "Hook sull'accento".
    n_swing = sum(1 for a in fig if a['moveType'] in m.SWING_MOVES)
    n_jabs = sum(1 for a in fig if a['moveType'] == m.MOVE_JAB)
    check(f"'{name}': mix di colpo ampio (accento, {n_swing}) e Jab (riempimento, {n_jabs}), "
          f"non tutto uguale",
          n_swing >= 1 and (n_swing + n_jabs) == len(fig))
    # gli accenti di UNA figura restano tutti dello stesso tipo: e' cio' che
    # la rende riconoscibile come cellula ritmica unitaria (campionamento una
    # volta per figura, non per colpo)
    swing_types = set(a['moveType'] for a in fig if a['moveType'] in m.SWING_MOVES)
    check(f"'{name}': dentro una figura il colpo ampio e' sempre lo stesso "
          f"(trovati {len(swing_types)} tipi diversi)", len(swing_types) <= 1)

print("\n4. _euclidean_figure: sincope come le altre figure (fase segue l'attacco)")
fig_on = m._euclidean_figure(beats, t_start=0.0, pattern_name='tresillo')
fig_off = m._euclidean_figure(beats, t_start=0.26, pattern_name='tresillo')  # vicino al mezzo beat (0.25 a 120bpm)
check("attacco sul beat -> primo colpo sul beat", fig_on[0]['startTime'] == 0.0)
check("attacco vicino al mezzo beat -> primo colpo IN LEVARE",
      abs(fig_off[0]['startTime'] - 0.25) < 1e-6)

print("\n5. Integrazione: enforce_playability non rompe le figure euclidee ne' in mix con le altre")
rng = random.Random(7)
mixed = []
mixed.extend(m._euclidean_figure(beats, 2.0, 'tresillo', start_side=0))
mixed.extend(m._jab_combo(beats, 10.0, 3, start_side=1))
mixed.extend(m._hook_accent(beats, 20.0, 2, start_side=0))
mixed.extend(m._euclidean_figure(beats, 30.0, 'cinquillo_largo', start_side=1))
before = len(mixed)
final = m.enforce_playability(mixed, beats)
check(f"nessuna azione persa nel mix di 4 figure diverse ({before} -> {len(final)})",
      len(final) == before)
grid2 = set(round(g, 6) for g in m._grid_times(beats))
check("tutte restano sulla griglia dopo enforce_playability",
      all(round(a['startTime'], 6) in grid2 for a in final))
all_arms = sorted([a for a in final if a['moveType'] in m.ARM_MOVES], key=lambda a: a['startTime'])
beat_len = 60.0 / 120.0
violations = []
for i in range(len(all_arms) - 1):
    p, c = all_arms[i], all_arms[i + 1]
    need = m._required_gap_beats(p, c)
    gap = (c['startTime'] - p['startTime']) / beat_len
    if gap < need - 1e-6:
        violations.append((p['moveType'], c['moveType'], round(gap, 3), need))
check(f"nessuna violazione di recupero minimo nel mix (trovate {len(violations)}: {violations[:3]})",
      not violations)

print("\n6. Coreografia reale con le figure euclidee agganciate come terza sorgente (test-only qui,"
      " non ancora nella pipeline di produzione)")
import boxvr_generator as gen
import os
MP3 = audio_di_prova('Chop Suey!.mp3')
if os.path.exists(MP3):
    analysis = gen.generate_song_analysis(MP3)
    beats_real = analysis['beats']
    rng2 = random.Random(3)
    events = analysis.get('rhythm_events') or []
    fast_starts = [e['start'] for e in events if e['type'] == 'fast'][:3]
    if fast_starts:
        figs = [m._euclidean_figure(beats_real, t, 'tresillo', start_side=rng2.randint(0, 1))
                for t in fast_starts]
        total = sum(len(f) for f in figs)
        check(f"generate {len(fast_starts)} figure euclidee reali su eventi 'fast' veri ({total} colpi)",
              total > 0)
    else:
        print("  (nessun evento 'fast' su questo brano, test 6 saltato)")
else:
    print("  (mp3 di prova non trovato, test 6 saltato)")

print("\n" + "=" * 52)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
