"""Prova end-to-end: app in modalita' Genera, mp3 vero caricato, si aspetta
l'analisi in background, poi si apre l'anteprima visiva dal pulsante come
farebbe l'utente."""
import os
import sys
import time

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brano_di_prova import audio_di_prova
import boxvr_fixer_gui as m

m.BoxVRFixerApp._prompt_game_dir_if_needed = lambda self: None
m.BoxVRFixerApp._ask_game_dir = lambda self, initial=None: False

MP3 = audio_di_prova('Chop Suey!.mp3')

root = m.tk.Tk()
if m.HAS_DND:
    try:
        m.TkinterDnD._require(root)
    except Exception:
        pass
root.withdraw()
root.configure(bg=m.resolve_color(m.BG))
app = m.BoxVRFixerApp(root, app_mode=m.APP_MODE_MAKE)
for _ in range(30):
    root.update()
    time.sleep(0.01)

p = app.generate_panel
ok, _ = p._add_file(MP3)
print("mp3 aggiunto:", ok, "| brani in elenco:", len(p.songs))

print("attendo l'analisi in background (puo' richiedere un minuto)...")
t0 = time.time()
while time.time() - t0 < 240:
    root.update()
    time.sleep(0.05)
    if p.songs and p.songs[0].get('analysis') is not None:
        break
song = p.songs[0]
print(f"analisi completata in {time.time()-t0:.0f}s | bpm={song['analysis']['bpm']:.1f}")

p.select_song(song)
for _ in range(30):
    root.update()
    time.sleep(0.01)
print("pulsante anteprima ora:", p.visual_btn.cget('state'), "(atteso normal)")

p._open_visual_preview()
for _ in range(40):
    root.update()
    time.sleep(0.02)
win = getattr(p, '_visual_win', None)
print("finestra anteprima aperta:", "si" if win is not None else "NO")
if win is not None:
    kids = win.winfo_children()
    print("   contiene", len(kids), "widget (canvas + barra controlli)")
    canvases = [w for w in kids if isinstance(w, m.tk.Canvas)]
    print("   canvas presente:", "si" if canvases else "no")
    win.destroy()
root.destroy()
print("OK")
