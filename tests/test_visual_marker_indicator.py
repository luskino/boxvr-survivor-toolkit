"""Verifica del nuovo trattamento visivo per i colpi da marker (27/08,
seconda versione dopo il feedback dal vivo dell'utente: non piu' un lampo su
tutte le corsie, ma un anello colorato ATTACCATO al bersaglio vero + un
indicatore pulsante in alto a destra). Pilota render() direttamente su un
Canvas headless, controllando i tag disegnati - non un test visivo a
pixel, ma verifica che il codice giusto scatti nei momenti giusti."""
import os
import sys
import tkinter as tk

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boxvr_visual_preview as vp

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
root.withdraw()
canvas = tk.Canvas(root, width=800, height=600)
preview = vp.ChoreoPreviewCanvas(canvas, 800, 600)

# un colpo NORMALE (non da marker) in arrivo - nessun anello colorato ne'
# indicatore, solo il bersaglio
actions_normal = [{'startTime': 1.0, 'moveType': vp.MOVE_JAB, 'moveChannel': 0, 'hand': 'L', 'sidecar': False}]
preview.render(now_t=0.5, actions_sorted=actions_normal)
items = canvas.find_withtag("marker")
outline_colors = [canvas.itemcget(i, 'outline') for i in items if canvas.type(i) == 'oval']
check("colpo normale in arrivo: nessun anello nel colore marker",
      vp.MARKER_FLASH_COLOR not in outline_colors)
text_items = [canvas.itemcget(i, 'text') for i in items if canvas.type(i) == 'text']
check("colpo normale in arrivo: nessuna etichetta MARKER", "MARKER" not in text_items)

# un colpo DA MARKER in arrivo - deve avere l'anello colorato attaccato E
# l'indicatore in alto a destra
actions_marker = [{'startTime': 1.0, 'moveType': vp.MOVE_JAB, 'moveChannel': 0, 'hand': 'L', 'sidecar': True}]
preview.render(now_t=0.5, actions_sorted=actions_marker)
items = canvas.find_withtag("marker")
outline_colors = [canvas.itemcget(i, 'outline') for i in items if canvas.type(i) == 'oval']
check("colpo da marker in arrivo: anello nel colore marker presente",
      vp.MARKER_FLASH_COLOR in outline_colors)
text_items = [canvas.itemcget(i, 'text') for i in items if canvas.type(i) == 'text']
check("colpo da marker in arrivo: indicatore 'MARKER' mostrato", "MARKER" in text_items)

# subito dopo l'impatto - il lampo deve essere colorato (non piu' bianco)
preview.render(now_t=1.05, actions_sorted=actions_marker)
items = canvas.find_withtag("marker")
found_colored_glow = any(
    canvas.type(i) == 'oval' and canvas.itemcget(i, 'outline') not in ('', '#ffffff')
    for i in items)
check("subito dopo l'impatto di un marker: alone colorato (non bianco)", found_colored_glow)

# molto dopo l'impatto - l'indicatore deve sparire (il colpo non e' piu' 'in vista')
preview.render(now_t=1.5, actions_sorted=actions_marker)
items = canvas.find_withtag("marker")
text_items = [canvas.itemcget(i, 'text') for i in items if canvas.type(i) == 'text']
check("molto dopo l'impatto: l'indicatore MARKER e' sparito", "MARKER" not in text_items)

print(f"\n{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
