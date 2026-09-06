import sys, time
# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
import os
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tkinter as tk
import boxvr_visual_preview as vp

song = vp.load_song(0)
print("brano:", song['label'], "azioni:", len(song['actions']), "durata:",
      len(song['audio']) / song['sr'])

root = tk.Tk()
root.withdraw()
canvas = tk.Canvas(root, width=1000, height=620)
preview = vp.ChoreoPreviewCanvas(canvas, 1000, 620)

dur = len(song['audio']) / song['sr']
idx = 0
max_markers = 0
t = 0.0
step = 1.0 / 30
errors = 0
while t < dur:
    try:
        idx = preview.render(t, song['actions'], idx)
    except Exception as e:
        print("ERRORE a t=", t, e)
        errors += 1
        if errors > 5:
            break
    n = len(canvas.find_withtag("marker"))
    max_markers = max(max_markers, n)
    t += step

print("percorse", dur, "secondi senza crash. massimo bersagli simultanei disegnati:", max_markers)
print("indice finale marker_idx:", idx, "su", len(song['actions']), "azioni")

# vai a un istante preciso con azioni note e controlla che ci siano marker
first_action_t = song['actions'][0]['startTime']
preview.render(first_action_t - 0.5, song['actions'], 0)
n_before = len(canvas.find_withtag("marker"))
preview.render(first_action_t, song['actions'], 0)
n_at = len(canvas.find_withtag("marker"))
print(f"marker 0.5s prima del primo colpo: {n_before}, esattamente al colpo: {n_at}")

root.destroy()
print("OK")
