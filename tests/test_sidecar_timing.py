"""Verifica della correzione di latenza audio per la sidecar (27/08, difetto
reale segnalato: "fuori tempo anche premendo al momento esatto del beat").
Misurato: sd.OutputStream senza latency esplicita negozia ~180ms su questa
macchina, con latency='low' ~90ms - abbastanza da percepirsi come "fuori
tempo" in un contesto sensibile al ritmo. audible_position_seconds() deve
sottrarre la latenza REALE negoziata (qualunque essa sia, non un numero
fisso), non solo chiedere 'low' e sperare che basti."""
import os
import sys

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import boxvr_fixer_gui as gui

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


audio = np.zeros((44100 * 5, 2), dtype='float32')
player = gui.SongPlayer(audio, 44100)

check("lo stream chiede esplicitamente latenza 'low'",
      player.stream.latency <= 0.15)  # 'low' su questa macchina misura ~0.09s;
                                       # margine largo per non dipendere dall'hardware esatto

player.pos = int(1.0 * 44100)   # 1.0s di posizione "consegnata al buffer"
raw = player.position_seconds()
audible = player.audible_position_seconds()
check(f"position_seconds() resta quello grezzo (trovato {raw:.3f}s)", abs(raw - 1.0) < 1e-6)
check(f"audible_position_seconds() e' PIU' INDIETRO della latenza reale "
      f"(grezzo {raw:.3f}s, udibile {audible:.3f}s, differenza {raw-audible:.3f}s "
      f"contro latenza dichiarata {player.stream.latency:.3f}s)",
      abs((raw - audible) - player.stream.latency) < 1e-6)

# vicino all'inizio del brano, non deve mai andare sotto zero
player.pos = int(0.01 * 44100)
check("vicino all'inizio: audible_position_seconds non va mai sotto zero",
      player.audible_position_seconds() >= 0.0)

player.close()
print(f"\n{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
