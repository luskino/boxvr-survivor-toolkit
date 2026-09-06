"""Verifica del controllo 'durata massima playlist' aggiunto alla scheda
Genera (27/08): generate_songs() supportava gia' max_playlist_minutes da
tempo, mancava solo il controllo vero in interfaccia. Pilota i metodi veri
(non solo la costruzione dei widget), come test_gui_sidecar.py."""
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

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


root = tk.Tk()
if gui.HAS_DND:
    try:
        gui.TkinterDnD._require(root)
    except Exception:
        pass
root.withdraw()

app = gui.BoxVRFixerApp(root, app_mode='make')
panel = app.generate_panel
# CTkEntry attiva il segnaposto ("nessun limite") con una chiamata differita,
# che in una finestra mai disegnata (root.withdraw(), nessun mainloop vero)
# non e' ancora scattata subito dopo la costruzione - un pompaggio esplicito
# della coda eventi la fa scattare, cosi' i controlli sotto non trovano il
# widget in uno stato intermedio che nell'uso reale (mainloop sempre attivo)
# non esiste mai.
root.update()
check("il campo esiste in modalita' Genera", panel.max_playlist_minutes_entry is not None)
# in modalita' Correggi il campo non ha senso (non genera nessuna playlist
# nuova): il codice lo costruisce solo "if self.mode == 'generate'", e in
# app_mode='make' non esiste nemmeno il pannello Correggi - verificato per
# lettura del codice, non con un secondo processo/root Tk: piu' root CTk
# nello stesso processo rompono la cache immagini (limite gia' noto di
# questi test, vedi test_visual_btn.py/test_chooser_states.py).
check("in modalita' Genera pura non esiste nemmeno il pannello Correggi",
      app.correct_panel is None)

check("vuoto -> nessun limite (None)", panel._get_max_playlist_minutes() is None)

panel.max_playlist_minutes_entry.insert(0, "30")
check("valore numerico valido -> letto correttamente", panel._get_max_playlist_minutes() == 30.0)

panel.max_playlist_minutes_entry.delete(0, "end")
panel.max_playlist_minutes_entry.insert(0, "0")
check("zero -> trattato come nessun limite (non un limite assurdo di 0 minuti)",
      panel._get_max_playlist_minutes() is None)

panel.max_playlist_minutes_entry.delete(0, "end")
panel.max_playlist_minutes_entry.insert(0, "-5")
check("negativo -> trattato come nessun limite", panel._get_max_playlist_minutes() is None)

panel.max_playlist_minutes_entry.delete(0, "end")
panel.max_playlist_minutes_entry.insert(0, "abc")
check("testo non numerico -> nessun limite, non un'eccezione", panel._get_max_playlist_minutes() is None)

panel.max_playlist_minutes_entry.delete(0, "end")
panel.max_playlist_minutes_entry.insert(0, "45")
panel._on_playlist_duration_change()
check("il valore viene persistito nelle impostazioni", panel.app.settings.get('max_playlist_minutes') == 45.0)

# NOTA: la ri-popolazione del campo alla ricostruzione del pannello (es. dopo
# un riavvio) userebbe un secondo processo BoxVRFixerApp con una seconda root
# Tk - non testata qui perche' piu' root CTk nello stesso processo rompono la
# cache immagini (limite gia' noto di questi test, vedi
# test_visual_btn.py/test_chooser_states.py, "un processo per modalita'").
# Il codice di lettura (`saved = self.app.settings.get(...); if saved:
# entry.insert(...)`) e' lo stesso pattern gia' usato per choreo_preset/
# density altrove in questo file, non giustifica un processo dedicato solo
# per questo controllo.

print(f"\n{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
