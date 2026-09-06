"""Verifica GUI reale (headless, nessuna finestra visibile) del percorso di
aggiunta/ordinamento/rimozione brani in modalita' CORREGGI, dopo aver
tirato fuori read_correct_item/read_generate_item e aver cambiato
_apply_sort per leggere da song['_bpm_text'] invece che dal widget.
"""
import os
import sys
import time

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
# la radice del progetto: questo file sta in tests/
RADICE_PROGETTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boxvr_fixer_gui as m

root = m.tk.Tk()
if m.HAS_DND:
    try:
        m.TkinterDnD._require(root)
    except Exception:
        pass
root.withdraw()
root.configure(bg=m.resolve_color(m.BG))
app = m.BoxVRFixerApp(root, app_mode=m.APP_MODE_FIX)
for _ in range(25):
    root.update()
    time.sleep(0.01)

p = app.correct_panel
folder = os.path.join(RADICE_PROGETTO, 'file di test da correggere wav')
found_valid, saw_wrong = p._add_folder(folder)
for _ in range(15):
    root.update()
    time.sleep(0.01)

print("brani validi trovati:", found_valid)
print("brani in lista:", len(p.songs))
print("righe create:", len(p.song_rows))
assert len(p.songs) == 8, f"attesi 8 brani, trovati {len(p.songs)}"
assert len(p.song_rows) == 8

# _bpm_text presente subito (letto dal JSON, prima ancora dell'analisi in background)
sample = p.songs[0]
print("primo brano:", sample['name'], "|", sample['artist'], "| bpm_text:", sample.get('_bpm_text'))
assert '_bpm_text' in sample

# ordinamento per nome
p._sort_key = 'name'
p._sort_reverse = False
p._apply_sort()
names = [s['name'] for s in p.songs]
assert names == sorted(names, key=str.casefold), "ordinamento per nome non corretto"
print("ordinamento per nome: OK")

# ordinamento per bpm (ora legge da song['_bpm_text'], non dal widget)
p._sort_key = 'bpm'
p._apply_sort()
print("ordine bpm dopo sort:", [s.get('_bpm_text') for s in p.songs])

# rimozione + undo
target = p.songs[3]
key = target['key']
p._remove_song(target)
for _ in range(10):
    root.update()
    time.sleep(0.01)
assert key not in p.song_keys
assert len(p.songs) == 7
print("rimozione: OK (7 rimasti)")

p._undo_remove()
for _ in range(10):
    root.update()
    time.sleep(0.01)
assert key in p.song_keys
assert len(p.songs) == 8
print("undo: OK (8 ripristinati)")

# aggiungere lo stesso file due volte non duplica
found_again, _ = p._add_folder(folder)
assert len(p.songs) == 8, f"attesi ancora 8 dopo re-aggiunta, trovati {len(p.songs)}"
print("dedup su re-aggiunta: OK")

root.destroy()
print("\nTUTTO OK")
