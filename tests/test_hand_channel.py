"""Verifica il fix del 2026-08-24: la mano (icona/colore L o R) deve sempre
corrispondere alla colonna reale dove il colpo atterra, mai un'icona "destra"
sulla colonna Sinistra o viceversa - segnalato dall'utente guardando davvero
la finestra di anteprima su "Synchronise - Metrik"."""
import os
import sys

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brano_di_prova import audio_di_prova
import boxvr_choreo as m
import boxvr_visual_preview as vp
import boxvr_generator as gen
import itertools

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


print("1. hand_for_channel: casi diretti")
cyc = itertools.cycle(('L', 'R'))
check("Front (0) -> L", vp.hand_for_channel(m.CH_FRONT, cyc) == 'L')
check("FrontLow (1) -> L", vp.hand_for_channel(m.CH_FRONT_LOW, cyc) == 'L')
check("Back (4) -> R", vp.hand_for_channel(m.CH_BACK, cyc) == 'R')
check("BackLow (5) -> R", vp.hand_for_channel(m.CH_BACK_LOW, cyc) == 'R')

print("\n2. coerenza mano<->colonna su una coreografia reale")
MP3 = audio_di_prova('Chop Suey!.mp3')
analysis = gen.generate_song_analysis(MP3)
actions = m.build_move_actions(analysis, preset='medium')

center_cycle = itertools.cycle(('L', 'R'))
marks = [{'moveType': a['moveType'], 'moveChannel': a['moveChannel'],
          'hand': vp.hand_for_channel(a['moveChannel'], center_cycle) if a['moveType'] in vp.PUNCH_TYPES else None}
         for a in sorted(actions, key=lambda a: a['startTime'])]

mismatches = []
for mk in marks:
    if mk['hand'] is None:
        continue
    col = vp.CHANNEL_CELL.get(mk['moveChannel'], (1, 0))[0]
    if col == 0 and mk['hand'] != 'L':
        mismatches.append(mk)
    if col == 2 and mk['hand'] != 'R':
        mismatches.append(mk)

n_punches = sum(1 for mk in marks if mk['hand'] is not None)
check(f"nessuna icona sulla colonna sbagliata su {n_punches} pugni reali (trovate {len(mismatches)} discrepanze)",
      not mismatches)

n_left = sum(1 for mk in marks if mk['hand'] == 'L')
n_right = sum(1 for mk in marks if mk['hand'] == 'R')
print(f"  (distribuzione: {n_left} sinistra, {n_right} destra)")

print("\n" + "=" * 52)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
