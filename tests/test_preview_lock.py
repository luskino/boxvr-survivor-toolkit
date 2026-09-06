"""Verifica che aprire l'anteprima visiva blocchi i controlli che cambiano la
coreografia (slider intensita'/densita', preset) e che chiuderla li sblocchi -
richiesto 2026-08-24: l'anteprima e' uno scatto dei parametri al momento
dell'apertura, cambiarli mentre e' aperta la renderebbe disallineata."""
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

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


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
print("mp3 aggiunto:", ok)

t0 = time.time()
while time.time() - t0 < 240:
    root.update()
    time.sleep(0.05)
    if p.songs and p.songs[0].get('analysis') is not None:
        break
song = p.songs[0]
p.select_song(song)
for _ in range(20):
    root.update()
    time.sleep(0.01)

def seg_state(w):
    return getattr(w, '_state', None)


print("\nprima dell'apertura (stato di partenza, qualunque esso sia):")
before_ratio = p.punch_ratio_slider.cget('state')
before_density = p.density_slider.cget('state')
before_preset = seg_state(p.choreo_preset_menu)
print(f"  intensita'={before_ratio} densita'={before_density} preset={before_preset}")

p._open_visual_preview()
for _ in range(40):
    root.update()
    time.sleep(0.02)

print("\ncon l'anteprima aperta:")
win = getattr(p, '_visual_win', None)
check("la finestra si e' aperta", win is not None)
check("slider intensita' bloccato", p.punch_ratio_slider.cget('state') == 'disabled')
check("slider densita' bloccato", p.density_slider.cget('state') == 'disabled')
check("menu preset bloccato", seg_state(p.choreo_preset_menu) == 'disabled')

# chiusura come farebbe l'utente (bottone X = WM_DELETE_WINDOW), non un
# distruttore diretto - serve a passare per _on_close e far scattare il
# callback di sblocco
# win.protocol("WM_DELETE_WINDOW") senza secondo argomento RITORNA il nome del
# comando Tcl registrato (una stringa), non lo invoca - va richiamato via tk.call
cmd = win.protocol("WM_DELETE_WINDOW")
win.tk.call(cmd)
for _ in range(20):
    root.update()
    time.sleep(0.01)

print("\ndopo la chiusura (il contratto e' sempre 'normal', non 'torna a prima':")
print("  stesso schema di run_btn/browse_btn altrove nel file):")
check("_visual_win azzerato", getattr(p, '_visual_win', 'MISSING') is None)
check("slider intensita' risbloccato a 'normal'", p.punch_ratio_slider.cget('state') == 'normal')
check("slider densita' risbloccato a 'normal'", p.density_slider.cget('state') == 'normal')
check("menu preset risbloccato a 'normal'", seg_state(p.choreo_preset_menu) == 'normal')

root.destroy()
print("\n" + "=" * 52)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
