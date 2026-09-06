"""Verifica il pulsante timeline "Colpi" -> "Marker" (30/08, richiesto: la
vecchia vista a tacche per beat era illeggibile, sostituita con stanghette
gialle nei punti esatti dove l'utente ha marcato). Solo in modalita' Genera:
in Correggi non esiste il concetto di marker, resta la vecchia vista Colpi."""
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

def new_root():
    r = tk.Tk()
    if gui.HAS_DND:
        try:
            gui.TkinterDnD._require(r)
        except Exception:
            pass
    r.withdraw()
    return r


root = new_root()

errors = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        errors.append(label)


# --- modalita' Genera: l'etichetta del secondo pulsante e' "Marker" ---
app = gui.BoxVRFixerApp(root, app_mode='generate')
panel = app.generate_panel
check("in modalita' Genera, il secondo pulsante dice 'Marker'",
      panel.timeline_mode_buttons['beats'].cget('text') == panel.t('timeline_mode_markers'))

mp3 = audio_di_prova('Chop Suey!.mp3')
import boxvr_generator as gen
panel._add_song(gui.read_generate_item(mp3), "?")
song = panel.songs[0]
song['analysis'] = gen.generate_song_analysis(mp3)
panel.select_song(song)
panel._set_timeline_mode('beats')
song['sidecar_markers'] = [1.0, 3.0, 6.5]
panel._refresh_sidecar_panel()

marker_lines = [i for i in panel.canvas.find_all()
                if panel.canvas.type(i) == 'line' and panel.canvas.itemcget(i, 'fill') == gui.MARKER_TICK_COLOR]
check(f"3 marker piazzati -> 3 stanghette gialle disegnate (trovate {len(marker_lines)})",
      len(marker_lines) == 3)

song['sidecar_markers'] = []
panel._refresh_sidecar_panel()
marker_lines_after_clear = [i for i in panel.canvas.find_all()
                             if panel.canvas.type(i) == 'line' and panel.canvas.itemcget(i, 'fill') == gui.MARKER_TICK_COLOR]
check("nessun marker -> nessuna stanghetta gialla", len(marker_lines_after_clear) == 0)

# tornando alla vista "Curva" non deve disegnare stanghette anche con marker presenti
song['sidecar_markers'] = [1.0]
panel._set_timeline_mode('curve')
marker_lines_curve = [i for i in panel.canvas.find_all()
                       if panel.canvas.type(i) == 'line' and panel.canvas.itemcget(i, 'fill') == gui.MARKER_TICK_COLOR]
check("vista 'Curva': nessuna stanghetta gialla anche con marker presenti", len(marker_lines_curve) == 0)

if panel.player is not None:
    panel.player.close()

print(f"\n{'TUTTO OK (parte Genera)' if not errors else f'{len(errors)} FALLITI'}")

# --- modalita' Correggi: il secondo pulsante resta "Colpi" (nessun marker li') ---
# eseguito in un PROCESSO SEPARATO: un secondo root Tk() nello stesso processo
# del primo manda in confusione la cache immagini globale di customtkinter
# ("image pyimage1 doesn't exist"), anche dopo aver distrutto il primo root -
# e' un limite noto di customtkinter con piu' interpreti Tcl nello stesso
# processo, non qualcosa legato a questa feature.
import subprocess
check2 = subprocess.run([sys.executable, "-c", f"""
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brano_di_prova import audio_di_prova
import tkinter as tk
import boxvr_fixer_gui as gui
root = tk.Tk()
if gui.HAS_DND:
    try:
        gui.TkinterDnD._require(root)
    except Exception:
        pass
root.withdraw()
app = gui.BoxVRFixerApp(root, app_mode=gui.APP_MODE_FIX)
panel = app.correct_panel
ok = panel.timeline_mode_buttons['beats'].cget('text') == panel.t('timeline_mode_beats')
print("OK" if ok else "FAIL")
sys.exit(0 if ok else 1)
"""], capture_output=True, text=True)
check("in modalita' Correggi, il secondo pulsante resta 'Colpi'", check2.returncode == 0)
if check2.returncode != 0:
    print(check2.stdout, check2.stderr)

print(f"\n{'TUTTO OK' if not errors else f'{len(errors)} FALLITI'}")
sys.exit(1 if errors else 0)
