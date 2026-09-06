"""Verifica il fix alla progress bar (30/08): segnalato durante un test live
su Master of Puppets (~8 minuti, analisi pesante) che restava ferma a 0% per
tutta l'elaborazione. Causa: la barra passava a determinate solo quando
arrivava una riga di log "[i/n]" (una per BRANO completato) - fra una riga e
la prossima, su un brano singolo lungo, restava ferma senza nessun segno di
attivita'. Fix: animazione indeterminate mentre un brano e' in lavorazione,
determinate reale appena arriva la prossima riga [i/n]."""
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

root = tk.Tk()
if gui.HAS_DND:
    try:
        gui.TkinterDnD._require(root)
    except Exception:
        pass
root.withdraw()

app = gui.BoxVRFixerApp(root, app_mode='generate')
panel = app.generate_panel

# _on_finished/_on_error mostrano un messagebox reale (bloccante in un test
# headless) - si sostituisce con un no-op, stesso pattern gia' usato altrove
# in questo file di test (vedi test_risky_playlist_warning.py).
gui.messagebox.showwarning = lambda *a, **k: None
gui.messagebox.showinfo = lambda *a, **k: None
gui.messagebox.showerror = lambda *a, **k: None

errors = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        errors.append(label)


# 1 solo brano nel batch: nessuna riga [i/n] arriva finche' non finisce -
# durante tutta l'elaborazione la barra deve restare animata (indeterminate),
# non ferma a 0.
panel.progress.configure(mode="determinate")
panel.progress.set(0)
panel.progress.configure(mode="indeterminate")
panel.progress.start()
check("durante l'elaborazione (nessuna riga [i/n] ancora arrivata): modalita' indeterminate",
      panel.progress.cget('mode') == 'indeterminate')

# arriva la riga di completamento dell'UNICO brano del batch: [1/1]
panel._log("[1/1] OK Master of Puppets: 8 minuti, 900 beat")
check("dopo [1/1]: torna a determinate", panel.progress.cget('mode') == 'determinate')
check("dopo [1/1]: valore reale 1.0", abs(panel.progress.get() - 1.0) < 1e-9)

# batch di piu' brani: dopo [1/3] la barra deve mostrare il valore reale E
# poi tornare ad animarsi per il brano successivo (ancora in lavorazione)
panel.progress.configure(mode="determinate")
panel.progress.set(0)
panel.progress.configure(mode="indeterminate")
panel.progress.start()
panel._log("[1/3] OK Brano Uno: qualcosa")
check("batch di 3, dopo [1/3]: valore reale 1/3", abs(panel.progress.get() - (1 / 3)) < 1e-9)
check("batch di 3, dopo [1/3] (i<n): torna ad animarsi per il prossimo brano",
      panel.progress.cget('mode') == 'indeterminate')

panel._log("[3/3] OK Brano Tre: qualcosa")
check("batch di 3, dopo [3/3] (i==n, ultimo): resta determinate",
      panel.progress.cget('mode') == 'determinate')
check("batch di 3, dopo [3/3]: valore reale 1.0", abs(panel.progress.get() - 1.0) < 1e-9)

# _on_finished/_on_error devono fermare l'animazione e riportare a determinate,
# non lasciarla girare all'infinito dopo la fine reale del lavoro
panel.progress.configure(mode="indeterminate")
panel.progress.start()
panel._on_finished({'output_folder': None, 'n_ok': 0, 'n_errors': 0})
check("_on_finished: ferma l'animazione e torna a determinate a 1.0",
      panel.progress.cget('mode') == 'determinate' and abs(panel.progress.get() - 1.0) < 1e-9)

panel.progress.configure(mode="indeterminate")
panel.progress.start()
panel._on_error("errore di prova")
check("_on_error: ferma l'animazione e torna a determinate a 0",
      panel.progress.cget('mode') == 'determinate' and abs(panel.progress.get() - 0.0) < 1e-9)

print(f"\n{'TUTTO OK' if not errors else f'{len(errors)} FALLITI'}")
sys.exit(1 if errors else 0)
