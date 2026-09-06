"""Verifica il fix al campo BPM (30/08, difetto reale segnalato: "il
textfield per aggiungere i bpm e' lockato finche' non finisce l'analisi...
magari conosco gia' i bpm e non ha senso aspettare"). Il campo ora si puo'
compilare anche PRIMA che l'analisi automatica sia finita:
- se il brano e' ancora in coda, il valore scritto viene letto dal worker
  al momento in cui lo estrae (nessuna azione speciale necessaria);
- se l'analisi e' GIA' in corso, il risultato che sta per arrivare riflette
  ancora il vecchio valore - va segnato per una ri-analisi automatica
  appena arriva, invece di mostrare all'utente un risultato gia' superato."""
import os
import sys
import tkinter as tk

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brano_di_prova import audio_di_prova
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

errors = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        errors.append(label)


mp3 = audio_di_prova('Chop Suey!.mp3')
panel._add_song(gui.read_generate_item(mp3), "?")
song = panel.songs[0]
song['play_audio'] = __import__('numpy').zeros((44100 * 5, 2), dtype='float32')
song['play_sr'] = 44100
panel.select_song(song)
root.update()

# --- scenario 1: brano ancora in coda (analisi non ancora presa in carico) ---
song['_status'] = 'queued'
song['analysis'] = None
song['forced_bpm'] = None
panel._update_bpm_panel()
check("brano in coda: il campo BPM e' scrivibile (non piu' disabilitato)",
      panel.bpm_entry.cget('state') == 'normal')
check("brano in coda: le frecce +-1 restano disabilitate (nessun valore rilevato da cui partire)",
      panel.bpm_up_btn.cget('state') == 'disabled')

panel.bpm_entry_var.set("140")
panel._on_bpm_entry_commit()
check(f"brano in coda: scrivere e confermare imposta forced_bpm (trovato {song.get('forced_bpm')})",
      song.get('forced_bpm') == 140.0)
check("brano in coda: NESSUna richiesta di ri-analisi (non stava ancora analizzando nulla)",
      not song.get('_bpm_pending_requeue'))

# riselezionando il brano il valore scritto resta visibile (non si perde)
panel._update_bpm_panel()
check(f"il valore forzato resta mostrato nel campo (trovato '{panel.bpm_entry_var.get()}')",
      panel.bpm_entry_var.get() == "140.0")

# --- scenario 2: analisi GIA' in corso quando l'utente scrive il BPM ---
song['_status'] = 'analyzing'
song['analysis'] = None
song['forced_bpm'] = None
panel.bpm_entry_var.set("172")
panel._on_bpm_entry_commit()
check(f"analisi in corso: forced_bpm impostato comunque (trovato {song.get('forced_bpm')})",
      song.get('forced_bpm') == 172.0)
check("analisi in corso: segnato per ri-analisi automatica quando arriva il risultato superato",
      song.get('_bpm_pending_requeue') is True)

# arriva il risultato ORMAI SUPERATO (calcolato prima che l'utente scrivesse
# 172) - non deve essere accettato come definitivo, va rimandato in coda
fake_stale_analysis = {
    'bpm': 100.0, 'name': song['name'], 'artist': song['artist'],
    'bar_score': [0.1, 0.2], 'tempo_corrected': False, 'duration': 180.0,
}
panel.analysis_queue.put(('done', song, fake_stale_analysis, None, None))
panel._poll_analysis_queue()
check("il risultato superato NON viene accettato come analisi finale (torna a None)",
      song.get('analysis') is None)
check("il brano torna 'queued' per la ri-analisi con il BPM corretto",
      song.get('_status') == 'queued')
check("forced_bpm resta quello scritto dall'utente (172), non quello del risultato scartato",
      song.get('forced_bpm') == 172.0)
check("il flag di richiesta ri-analisi e' stato consumato", not song.get('_bpm_pending_requeue'))

# --- testo non numerico: non solleva eccezioni, ripristina un valore sensato ---
song['_status'] = 'queued'
song['analysis'] = None
song['forced_bpm'] = 172.0
panel.bpm_entry_var.set("abc")
panel._on_bpm_entry_commit()
check(f"testo non numerico prima dell'analisi: nessuna eccezione, campo ripristinato "
      f"(trovato '{panel.bpm_entry_var.get()}')", panel.bpm_entry_var.get() == "172.0")

print(f"\n{'TUTTO OK' if not errors else f'{len(errors)} FALLITI'}")
sys.exit(1 if errors else 0)
