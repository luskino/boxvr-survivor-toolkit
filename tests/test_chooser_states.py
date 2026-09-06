"""Verifica lo stato delle card della schermata di scelta al variare dello
stato della patch. Un processo per stato: la cache icone di customtkinter
lega le PhotoImage al primo root Tk, quindi piu' root nello stesso processo
falliscono con "image pyimageN doesn't exist" (limite del test, non del
prodotto - l'app vera ha un solo root).
"""
import os
import sys
import time

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STATE_ARG = sys.argv[1]

import boxvr_patch
import boxvr_fixer_gui as m

forced = {
    'patched': boxvr_patch.STATE_PATCHED,
    'original': boxvr_patch.STATE_ORIGINAL,
    'missing': boxvr_patch.STATE_MISSING,
}[STATE_ARG]

m.boxvr_patch.state = lambda *a, **k: forced

root = m.tk.Tk()
root.withdraw()
root.configure(bg=m.resolve_color(m.BG))
app = m.BoxVRFixerApp(root, app_mode=None)
for _ in range(25):
    root.update()
    time.sleep(0.01)

buttons, labels = [], []


def walk(w):
    for c in w.winfo_children():
        if isinstance(c, m.ctk.CTkButton):
            buttons.append(c)
        if isinstance(c, m.ctk.CTkLabel):
            try:
                txt = c.cget('text')
            except Exception:
                txt = ''
            if txt:
                labels.append(txt)
        walk(c)


walk(root)

def safe(s):
    # la console Windows e' cp1252: le emoji nei testi dei pulsanti (es. il
    # lucchetto dello stato disabilitato) farebbero fallire la stampa
    return s.encode('ascii', 'backslashreplace').decode('ascii')


print(f"stato patch simulato: {STATE_ARG}")
for b in buttons:
    print(f"   pulsante {safe(repr(b.cget('text'))):32s} state={b.cget('state')}")
notes = [safe(l) for l in labels if 'Patch' in l or 'Disabil' in l]
print(f"   avvisi: {notes or 'nessuno'}")
root.destroy()
