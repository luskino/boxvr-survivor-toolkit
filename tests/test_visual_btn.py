"""Verifica il pulsante "Anteprima visiva" nella GUI.
Un processo per modalita': piu' root Tk nello stesso processo rompono la cache
immagini di customtkinter ("image pyimageN doesn't exist") - limite del test,
non del prodotto.
"""
import os
import sys
import time

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boxvr_fixer_gui as m

MODE = sys.argv[1]

# il dialogo che chiede la cartella del gioco e' modale: va neutralizzato PRIMA
# di costruire l'app, non dopo, o il test si blocca lì
m.BoxVRFixerApp._prompt_game_dir_if_needed = lambda self: None
m.BoxVRFixerApp._ask_game_dir = lambda self, initial=None: False


def safe(s):
    return s.encode('ascii', 'backslashreplace').decode('ascii')


root = m.tk.Tk()
if m.HAS_DND:
    try:
        m.TkinterDnD._require(root)
    except Exception:
        pass
root.withdraw()
root.configure(bg=m.resolve_color(m.BG))
app = m.BoxVRFixerApp(root, app_mode=MODE)
for _ in range(30):
    root.update()
    time.sleep(0.01)

panel = app.generate_panel if MODE == m.APP_MODE_MAKE else app.correct_panel
btn = panel.visual_btn

if MODE == m.APP_MODE_FIX:
    print("CORREGGI -> pulsante:", "assente (corretto)" if btn is None else "PRESENTE (errore)")
else:
    print("GENERA -> creato:", "si" if btn else "NO (errore)")
    print("   testo   :", safe(btn.cget('text')))
    print("   stato   :", btn.cget('state'), "(atteso disabled: nessun brano)")
    app._set_language('en')
    for _ in range(10):
        root.update()
        time.sleep(0.01)
    print("   dopo EN :", safe(btn.cget('text')))
    app._set_language('it')
    for _ in range(10):
        root.update()
        time.sleep(0.01)
    print("   dopo IT :", safe(btn.cget('text')))
    # senza brano selezionato il metodo non deve esplodere, solo non fare nulla
    panel._open_visual_preview()
    print("   click senza brano: nessun errore")

root.destroy()
