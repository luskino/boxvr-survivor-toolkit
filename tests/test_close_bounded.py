"""Verifica il meccanismo di attesa limitata usato in _on_close (25/08).

NON testa _on_close per intero: quella funzione ha un timer di sicurezza che
chiama os._exit(0) dopo 4s SEMPRE, che ucciderebbe questo stesso processo di
test. Qui si isola solo il pattern (_run_bounded), che e' la parte
verificabile senza rischiare di terminare il processo di test."""
import os
import sys
import threading
import time

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


def _run_bounded(fn, timeout=1.5):
    t = threading.Thread(target=fn, daemon=True)
    t.start()
    t.join(timeout)


print("1. Un passaggio VELOCE completa normalmente")
eseguito = []
t0 = time.time()
_run_bounded(lambda: eseguito.append(1), timeout=1.5)
dt = time.time() - t0
check(f"eseguito ({eseguito})", eseguito == [1])
check(f"tempo trascurabile ({dt:.2f}s)", dt < 0.5)

print("\n2. Un passaggio BLOCCATO non impedisce il ritorno oltre il timeout")
def blocca_per_sempre():
    time.sleep(30)  # simula un hang reale (es. PortAudio stream.stop())

t0 = time.time()
_run_bounded(blocca_per_sempre, timeout=1.0)
dt = time.time() - t0
check(f"ritorna comunque entro il timeout (impiegato {dt:.2f}s, atteso ~1.0s)",
      0.9 <= dt <= 2.0)

print("\n3. Il thread bloccato resta appeso ma e' DAEMON: non impedisce l'uscita")
# se non fosse daemon, il processo Python non terminerebbe mai da solo -
# verifichiamo che il thread creato sopra sia effettivamente daemon
threads_attivi = [t for t in threading.enumerate() if t.name != 'MainThread']
check(f"i thread bloccati residui sono tutti daemon ({len(threads_attivi)} residui)",
      all(t.daemon for t in threads_attivi))

print("\n" + "=" * 56)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
