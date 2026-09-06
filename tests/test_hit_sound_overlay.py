"""Verifica il suono dei colpi sovrapposto al brano nell'anteprima visiva
(30/08, richiesto esplicitamente: "il suono dei colpi sovrapposto, non
troppo forte"). Non il suono vero di BoxVR (copyright) - un campione libero
con licenza compatibile (vedi assets/sfx/SOURCE.md), sommato al buffer audio
del brano prima di crearne il player, non riprodotto in tempo reale."""
import os
import sys
import numpy as np

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boxvr_visual_preview as vp

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


sr = 44100
# il campione dura ~1.1s: i colpi di prova vanno spaziati piu' del doppio di
# quello, altrimenti la CODA di un pugno sconfina nella finestra di verifica
# del colpo successivo, dando un falso "c'e' suono qui" sbagliato.
duration_s = 12.0
silence = np.zeros((int(sr * duration_s), 2), dtype='float32')

actions = [
    {'startTime': 1.0, 'moveType': vp.MOVE_JAB, 'moveChannel': 0},
    {'startTime': 4.0, 'moveType': vp.MOVE_HOOK, 'moveChannel': 4},
    {'startTime': 7.0, 'moveType': vp.MOVE_SQUAT, 'moveChannel': 2},   # NON un pugno
    {'startTime': 10.0, 'moveType': vp.MOVE_BLOCK, 'moveChannel': 2},  # NON un pugno
]

mixed = vp._overlay_hit_sounds(silence, sr, actions)

check("il buffer ORIGINALE non viene toccato (resta silenzio)",
      np.max(np.abs(silence)) == 0.0)
check("il buffer mixato ha la stessa forma dell'originale", mixed.shape == silence.shape)

sfx_samples = int(sr * 1.2)  # tutta la durata del campione (~1.1s) con margine
around_jab = mixed[int(1.0 * sr):int(1.0 * sr) + sfx_samples]
around_hook = mixed[int(4.0 * sr):int(4.0 * sr) + sfx_samples]
around_squat = mixed[int(7.0 * sr):int(7.0 * sr) + sfx_samples]
around_block = mixed[int(10.0 * sr):int(10.0 * sr) + sfx_samples]

check("si sente qualcosa subito dopo il Jab", np.max(np.abs(around_jab)) > 0.0)
check("si sente qualcosa subito dopo l'Hook", np.max(np.abs(around_hook)) > 0.0)
check("NIENTE sovrapposto sullo Squat (non e' un impatto)", np.max(np.abs(around_squat)) == 0.0)
check("NIENTE sovrapposto sul Block (non e' un pugno)", np.max(np.abs(around_block)) == 0.0)

check("il picco del mix non supera mai 1.0 (nessun clipping)",
      float(np.max(np.abs(mixed))) <= 1.0 + 1e-6)

# "non troppo forte" - il picco del suono sovrapposto deve restare sotto al
# picco del campione originale scalato dal guadagno dichiarato, non un
# valore arbitrario diverso
raw_sfx = vp._load_hit_sfx(sr, 2)
expected_peak = float(np.max(np.abs(raw_sfx))) * vp.HIT_SFX_GAIN
check(f"il guadagno dichiarato (HIT_SFX_GAIN={vp.HIT_SFX_GAIN}) e' quello davvero applicato "
      f"(picco atteso ~{expected_peak:.3f}, trovato {float(np.max(np.abs(around_jab))):.3f})",
      abs(float(np.max(np.abs(around_jab))) - expected_peak) < 1e-4)

# nessun colpo nel brano -> nessuna copia inutile, ritorna l'originale cosi' com'e'
no_hits_result = vp._overlay_hit_sounds(silence, sr, [])
check("nessun pugno nella coreografia -> ritorna l'audio invariato",
      no_hits_result is silence)

# un colpo vicinissimo alla fine del brano non deve sforare l'array (IndexError)
tail_actions = [{'startTime': duration_s - 0.01, 'moveType': vp.MOVE_JAB, 'moveChannel': 0}]
try:
    vp._overlay_hit_sounds(silence, sr, tail_actions)
    check("un colpo vicino alla fine del brano non solleva IndexError", True)
except IndexError:
    check("un colpo vicino alla fine del brano non solleva IndexError", False)

print(f"\n{'====================================================' }")
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
