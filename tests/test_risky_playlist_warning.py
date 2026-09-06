"""Verifica del collegamento GUI dell'avviso 'playlist a rischio' (26/08,
residuo tecnico - la funzione playlists_without_choreography esisteva gia',
mancava solo il collegamento). Il messagebox reale e' sostituito con uno
finto per non bloccare il test in attesa di un click."""
import os
import sys
import tkinter as tk

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boxvr_fixer_gui as gui
import boxvr_install

calls = []
gui.messagebox.showwarning = lambda title, msg: calls.append(msg)

root = tk.Tk()
if gui.HAS_DND:
    try:
        gui.TkinterDnD._require(root)
    except Exception:
        pass
root.withdraw()

app = gui.BoxVRFixerApp(root, app_mode='make')

errors = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        errors.append(label)


# nessuna playlist a rischio davvero installata (caso normale): nessun avviso
boxvr_install.playlists_without_choreography = lambda *a, **k: []
import boxvr_patch
orig_state = boxvr_patch.state
boxvr_patch.state = lambda *a, **k: boxvr_patch.STATE_PATCHED
app._refresh_patch_button()
check("nessuna playlist a rischio -> nessun avviso mostrato", len(calls) == 0)

# ora simuliamo 2 playlist a rischio
boxvr_install.playlists_without_choreography = lambda *a, **k: [
    ("Media.workoutplaylist.txt", 13, 13), ("Test.workoutplaylist.txt", 2, 5)]
app._refresh_patch_button()
check(f"con playlist a rischio -> un avviso mostrato (trovate {len(calls)} chiamate)", len(calls) == 1)
check("il testo elenca entrambe le playlist",
      "Media.workoutplaylist.txt" in calls[0] and "Test.workoutplaylist.txt" in calls[0])

# richiamare di nuovo _refresh_patch_button (es. altro giro di stato) non deve
# ripetere l'avviso nella stessa sessione
app._refresh_patch_button()
app._refresh_patch_button()
check(f"lo stesso avviso non si ripete nella sessione (trovate {len(calls)} chiamate totali)", len(calls) == 1)

boxvr_patch.state = orig_state
root.destroy()
print(f"\n{'TUTTO OK' if not errors else f'{len(errors)} FALLITI'}")
sys.exit(1 if errors else 0)
