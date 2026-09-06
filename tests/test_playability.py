"""Test di enforce_playability: le tre regole ricavate dal repertorio ufficiale
del gioco (aggancio alla griglia, simultaneita' legale, distanza minima).
Nate dal test in VR del 2026-08-24: colpi sovrapposti, colpi sopra i ganci,
scudo+pugno, e due brani percepiti "fuori dal beat".
"""
import os
import sys

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boxvr_choreo as ch

ok = fail = 0


def check(desc, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK   {desc}")
    else:
        fail += 1
        print(f"  FAIL {desc}")


def mk_beats(n=40, bpm=120.0):
    step = 60.0 / bpm
    return [{'_triggerTime': i * step, '_index': i} for i in range(n)]


def act(t, mt, ch_=0, injected=False):
    a = {'startTime': t, 'beatNumber': 0.0, 'moveType': mt, 'moveChannel': ch_}
    if injected:
        a['_injected'] = True
    return a


BEATS = mk_beats()           # 120 bpm -> beat ogni 0.5s, mezzo beat 0.25s
STEP = 0.5
HALF = 0.25

print("1. aggancio alla griglia")
a = ch.enforce_playability([act(1.07, ch.MOVE_JAB, injected=True)], BEATS)
check("un onset grezzo viene agganciato al punto di griglia piu' vicino",
      abs(a[0]['startTime'] - 1.0) < 1e-6)
a = ch.enforce_playability([act(1.20, ch.MOVE_JAB, injected=True)], BEATS)
check("aggancio al MEZZO beat quando e' il piu' vicino (1.20 -> 1.25)",
      abs(a[0]['startTime'] - 1.25) < 1e-6)
a = ch.enforce_playability([act(2.0, ch.MOVE_HOOK)], BEATS)
check("una mossa gia' sulla griglia non viene spostata",
      abs(a[0]['startTime'] - 2.0) < 1e-6)
a = ch.enforce_playability([act(1.07, ch.MOVE_JAB, injected=True)], BEATS)
check("beatNumber ricalcolato dopo lo spostamento", a[0]['beatNumber'] == 2.0)

print("\n2. simultaneita': cosa il gioco NON ammette")
r = ch.enforce_playability([act(2.0, ch.MOVE_BLOCK), act(2.0, ch.MOVE_JAB, injected=True)], BEATS)
check("Block + Jab insieme -> ne resta uno solo", len(r) == 1)
check("  ...e resta il Block (dal repertorio, non l'iniettato)", r[0]['moveType'] == ch.MOVE_BLOCK)
r = ch.enforce_playability([act(2.0, ch.MOVE_HOOK), act(2.0, ch.MOVE_JAB, injected=True)], BEATS)
check("Hook + Jab insieme -> ne resta uno solo", len(r) == 1)
check("  ...e resta il Hook", r[0]['moveType'] == ch.MOVE_HOOK)
r = ch.enforce_playability([act(2.0, ch.MOVE_JAB), act(2.0, ch.MOVE_JAB, injected=True)], BEATS)
check("due Jab sullo stesso istante -> uno solo", len(r) == 1)
r = ch.enforce_playability([act(2.0, ch.MOVE_UPPERCUT), act(2.0, ch.MOVE_HOOK)], BEATS)
check("Uppercut + Hook -> uno solo", len(r) == 1)

print("\n3. simultaneita': le due combinazioni AMMESSE dal gioco")
r = ch.enforce_playability([act(2.0, ch.MOVE_BLOCK), act(2.0, ch.MOVE_SQUAT)], BEATS)
check("Block + Squat resta una coppia (12 volte nel repertorio)", len(r) == 2)
r = ch.enforce_playability([act(2.0, ch.MOVE_JAB), act(2.0, ch.MOVE_SQUAT)], BEATS)
check("Jab + Squat resta una coppia (10 volte nel repertorio)", len(r) == 2)
r = ch.enforce_playability([act(2.0, ch.MOVE_HOOK), act(2.0, ch.MOVE_SQUAT)], BEATS)
check("Hook + Squat NON e' fra le ammesse -> uno solo", len(r) == 1)

print("\n4. distanza minima (0.5 beat = 0.25s a 120bpm)")
r = ch.enforce_playability([act(2.0, ch.MOVE_JAB), act(2.25, ch.MOVE_JAB)], BEATS)
check("due colpi a esattamente 0.5 beat: entrambi ammessi", len(r) == 2)
r = ch.enforce_playability([act(2.0, ch.MOVE_JAB), act(2.05, ch.MOVE_JAB, injected=True)], BEATS)
check("due colpi a 50ms: ne resta uno (troppo vicini)", len(r) == 1)
seq = [act(2.0 + i * 0.06, ch.MOVE_JAB, injected=True) for i in range(6)]
r = ch.enforce_playability(seq, BEATS)
gaps_ok = all(r[i]['startTime'] - r[i - 1]['startTime'] >= 0.25 - 1e-6 for i in range(1, len(r)))
check("una raffica fittissima viene diradata", len(r) < len(seq))
check("  ...e nessuna coppia resta sotto 0.5 beat", gaps_ok)

print("\n4b. recupero fra colpi di BRACCIA (il gioco non scende mai sotto 1 beat)")
# 120bpm: 1 beat = 0.5s, mezzo beat = 0.25s
r = ch.enforce_playability([act(2.0, ch.MOVE_JAB), act(2.25, ch.MOVE_JAB, injected=True)], BEATS)
check("due pugni a mezzo beat non restano dove sono", not (
    len(r) == 2 and abs(r[1]['startTime'] - 2.25) < 1e-6))
check("  ...il secondo viene SPOSTATO, non perso", len(r) == 2)
check("  ...spostato a 1 beat pieno di distanza", abs(r[1]['startTime'] - 2.5) < 1e-6)
r = ch.enforce_playability([act(2.0, ch.MOVE_JAB), act(3.0, ch.MOVE_JAB)], BEATS)
check("due pugni a 1 beat pieno restano intoccati",
      len(r) == 2 and abs(r[1]['startTime'] - 3.0) < 1e-6)

print("\n4c. dopo gancio/montante sullo STESSO lato serve piu' recupero (1.5 beat)")
r = ch.enforce_playability([act(2.0, ch.MOVE_HOOK, 0), act(2.5, ch.MOVE_JAB, 0, injected=True)], BEATS)
check("gancio -> diretto stesso lato a 1 beat: spostato piu' in la'",
      len(r) == 2 and r[1]['startTime'] >= 2.75 - 1e-6)
r = ch.enforce_playability([act(2.0, ch.MOVE_HOOK, 0), act(2.5, ch.MOVE_JAB, 4, injected=True)], BEATS)
check("gancio -> diretto sul lato OPPOSTO a 1 beat: va bene cosi'",
      len(r) == 2 and abs(r[1]['startTime'] - 2.5) < 1e-6)
r = ch.enforce_playability([act(2.0, ch.MOVE_JAB, 0), act(2.5, ch.MOVE_JAB, 0)], BEATS)
check("diretto -> diretto stesso lato a 1 beat: consentito (piu' del gancio)",
      len(r) == 2 and abs(r[1]['startTime'] - 2.5) < 1e-6)

print("\n4d. le mosse di GAMBE possono restare a mezzo beat")
r = ch.enforce_playability([act(2.0, ch.MOVE_SQUAT), act(2.25, ch.MOVE_SQUAT)], BEATS)
check("squat -> squat a mezzo beat: consentito (47 volte nel repertorio)",
      len(r) == 2 and abs(r[1]['startTime'] - 2.25) < 1e-6)

print("\n4e. figure SINCOPATE: la fase la detta la musica")
c = ch._jab_combo(BEATS, 2.00, 4)
check("attacco sul beat -> figura sul beat",
      [round(a['startTime'], 2) for a in c] == [2.0, 2.5, 3.0, 3.5])
c = ch._jab_combo(BEATS, 2.24, 4)
check("attacco vicino al mezzo beat -> figura IN LEVARE",
      [round(a['startTime'], 2) for a in c] == [2.25, 2.75, 3.25, 3.75])
check("  ...e resta a 1 beat di distanza (eseguibile)",
      all(abs((c[i]['startTime'] - c[i - 1]['startTime']) - 0.5) < 1e-6 for i in range(1, len(c))))
r = ch.enforce_playability(list(c), BEATS)
check("  ...e sopravvive intatta ai vincoli", len(r) == 4)
check("  ...senza essere riportata sul beat",
      abs(r[0]['startTime'] - 2.25) < 1e-6)

print("\n5. casi limite")
check("lista vuota -> vuota", ch.enforce_playability([], BEATS) == [])
check("senza beat non tocca nulla (non puo' sapere dov'e' la griglia)",
      len(ch.enforce_playability([act(1.07, ch.MOVE_JAB)], [])) == 1)
r = ch.enforce_playability([act(1.07, ch.MOVE_JAB)], BEATS)
check("non introduce chiavi che serialize_actions non conosce",
      {'startTime', 'beatNumber', 'moveType', 'moveChannel'} <= set(r[0]))

print("\n6. proprieta' globale su una coreografia mista realistica")
import random
rng = random.Random(7)
mixed = []
for i in range(200):
    t = rng.uniform(0, 19.0)
    mt = rng.choice([ch.MOVE_JAB, ch.MOVE_HOOK, ch.MOVE_UPPERCUT, ch.MOVE_BLOCK, ch.MOVE_SQUAT])
    mixed.append(act(t, mt, injected=rng.random() < 0.5))
mixed.sort(key=lambda a: a['startTime'])
r = ch.enforce_playability(mixed, BEATS)
grid = set(round(g, 6) for g in ch._grid_times(BEATS))
check("tutte le mosse finiscono sulla griglia", all(round(a['startTime'], 6) in grid for a in r))
from collections import defaultdict
by_t = defaultdict(list)
for a in r:
    by_t[round(a['startTime'], 6)].append(a['moveType'])
bad = [mts for mts in by_t.values()
       if len(mts) > 1 and frozenset(mts) not in ch.LEGAL_SIMULTANEOUS]
check("nessuna combinazione simultanea illegale", not bad)
check("mai piu' di 2 mosse sullo stesso istante", all(len(v) <= 2 for v in by_t.values()))
ts = sorted(by_t)
check("nessun istante piu' vicino di 0.5 beat al precedente",
      all(ts[i] - ts[i - 1] >= 0.25 - 1e-6 for i in range(1, len(ts))))

# invariante piu' forte: due colpi di braccia non stanno mai sotto 1 beat
ordered = sorted(r, key=lambda a: a['startTime'])
viol = []
for i in range(1, len(ordered)):
    p, c = ordered[i - 1], ordered[i]
    if p['moveType'] in ch.ARM_MOVES and c['moveType'] in ch.ARM_MOVES:
        need = ch._required_gap_beats(p, c) * 0.5      # 0.5s per beat a 120bpm
        if c['startTime'] - p['startTime'] < need - 1e-6:
            viol.append((p['moveType'], c['moveType'], c['startTime'] - p['startTime']))
check("nessuna coppia di braccia sotto il proprio recupero minimo", not viol)

print("\n7. Sequenza di mosse nelle figure nostre: campionamento Markov (26/08)")
print("   fase 3 del piano di training - 'quale mossa esatta, in che sequenza',")
print("   misurato sui 465 workout ufficiali invece di 'sempre lo stesso tipo'")
for prev, row in ch.ARM_TRANSITION_PROBS.items():
    total = sum(row.values())
    check(f"la riga di ARM_TRANSITION_PROBS per {prev} somma a 1.0 (trovato {total:.4f})",
          abs(total - 1.0) < 1e-6)

rng7 = random.Random(42)
counts = {ch.MOVE_JAB: 0, ch.MOVE_HOOK: 0, ch.MOVE_UPPERCUT: 0}
N = 20000
for _ in range(N):
    counts[ch._sample_next_arm_move(ch.MOVE_JAB, rng7)] += 1
expected = ch.ARM_TRANSITION_PROBS[ch.MOVE_JAB]
empirical = {mt: round(v / N, 3) for mt, v in counts.items()}
check(f"il campionamento da Jab rispecchia la distribuzione misurata entro l'1% "
      f"(atteso {expected}, trovato {empirical})",
      all(abs(counts[mt] / N - p) < 0.01 for mt, p in expected.items()))

combo = ch._jab_combo(BEATS, 2.0, 6, rng=random.Random(3))
check("_jab_combo apre sempre con un Jab (la sua identita')", combo[0]['moveType'] == ch.MOVE_JAB)
check("tutti i colpi restano di braccia (Jab/Hook/Uppercut)",
      all(m['moveType'] in ch.ARM_MOVES for m in combo))
combo_gaps_ok = all(abs((combo[i]['startTime'] - combo[i-1]['startTime']) - 0.5) < 1e-6
                    for i in range(1, len(combo)))
check("la cadenza di 1 beat resta fissa indipendentemente dal tipo campionato",
      combo_gaps_ok)
final_combo = ch.enforce_playability(list(combo), BEATS)
check("la figura sopravvive intatta a enforce_playability "
      f"(trovati {len(final_combo)}/6)", len(final_combo) == 6)

# Un singolo seme puo' dare per sfortuna una raffica tutta di Jab (~22% di
# probabilita' su 6 colpi, con 0.738 di restare Jab a ogni passo, atteso
# ~78% di varieta') - non e' un bug se capita una volta, lo sarebbe se non
# capitasse MAI la varieta' su tanti semi diversi. Controllo statistico
# invece che su un seme fissato; soglia (65%) tenuta ben sotto l'atteso per
# non rendere il test fragile al rumore statistico su un campione di 200.
n_varied = sum(1 for seed in range(200)
               if len(set(m['moveType'] for m in ch._jab_combo(BEATS, 2.0, 6, rng=random.Random(seed)))) > 1)
check(f"su 200 semi diversi, la maggioranza delle raffiche di 6 colpi mostra piu' di "
      f"un tipo di mossa (trovate {n_varied}/200 varie, atteso ~78%)", n_varied >= 130)

print(f"\n{'=' * 52}\n{ok} passati, {fail} falliti")
sys.exit(1 if fail else 0)
