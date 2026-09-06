"""Verifica che la barra di avanzamento (parsing di "[i/n]" nel log, vedi
boxvr_fixer_gui._log) avanzi ANCHE nel caso di successo normale in modalita'
Genera - prima mancava, segnalato 2026-08-24 leggendo il codice: solo
DRY-RUN/ERRORE scrivevano quel prefisso, il successo normale no."""
import re
import sys
import tempfile
import os

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
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


MP3 = audio_di_prova('Chop Suey!.mp3')
lines = []


def capture_log(msg):
    lines.append(msg)


with tempfile.TemporaryDirectory() as out:
    items = [{'audio_path': MP3, 'ratio': 0.5, 'preset': 'medium'}]
    result = gen.generate_songs(items, out, dry_run=False, log=capture_log)

progress_lines = [l for l in lines if re.match(r"\[(\d+)/(\d+)\]", l)]
print("righe di log con prefisso [i/n]:")
for l in progress_lines:
    print("   ", l)

check("almeno una riga di progresso emessa nel caso di successo (non solo errore/dry-run)",
      len(progress_lines) >= 1)
check("n_ok = 1 (la generazione e' andata a buon fine)", result.get('n_ok') == 1)
if progress_lines:
    m = re.match(r"\[(\d+)/(\d+)\]", progress_lines[-1])
    i, n = int(m.group(1)), int(m.group(2))
    check(f"l'ultima riga di progresso e' [{i}/{n}] cioe' 100% (i==n)", i == n)
    check("la riga e' quella di successo (OK), non ERRORE", "OK" in progress_lines[-1])

print("\n" + "=" * 52)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
