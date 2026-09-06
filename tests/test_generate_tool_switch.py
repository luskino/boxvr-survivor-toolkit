"""Verifica la riorganizzazione UI Automatica/Sidecar (30/08, richiesta
esplicita con schizzo a corredo): "Automatico" non e' piu' una delle tre
voci DENTRO il menu modalita' della sidecar, ma uno strumento di
generazione a se stante (regolatori pugni/densita'/intensita', quelli che
il tool ha sempre avuto), scelto con uno switch dedicato allo stesso
livello della sidecar - mai entrambi visibili insieme."""
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


def is_visible(widget):
    # winfo_ismapped() dipende dal toplevel essere davvero disegnato -
    # sempre False sotto root.withdraw() anche per un widget correttamente
    # impacchettato (verificato a parte). winfo_manager() invece riflette
    # solo se pack()/pack_forget() e' stato chiamato, indipendentemente
    # dalla mappatura reale della finestra - corretto per un test headless.
    return widget.winfo_manager() == 'pack'


mp3 = audio_di_prova('Chop Suey!.mp3')
panel._add_song(gui.read_generate_item(mp3), "?")
song = panel.songs[0]
song['play_audio'] = __import__('numpy').zeros((44100 * 5, 2), dtype='float32')
song['play_sr'] = 44100
panel.select_song(song)
root.update()

check("il campo generate_tool esiste per default a 'automatic'", song['generate_tool'] == 'automatic')
check("lo switch mostra 'Automatica' di default",
      panel.generate_tool_switch.get() == panel.t('generate_tool_automatic'))
check("di default il contenitore Automatica e' visibile", is_visible(panel.automatic_tools_frame))
check("di default il contenitore Sidecar NON e' visibile", not is_visible(panel.sidecar_frame))
check("il pannello BPM e' visibile su 'Automatica' (non e' un suo figlio, ma e' comunque li')",
      is_visible(panel.bpm_panel))
check("il pannello BPM NON e' figlio di automatic_tools_frame",
      panel.bpm_panel.master is not panel.automatic_tools_frame)

# passare a Sidecar: si scambiano, non convivono
panel._on_generate_tool_change(panel.t('generate_tool_sidecar'))
root.update()
check("song['generate_tool'] aggiornato a 'sidecar'", song['generate_tool'] == 'sidecar')
check("dopo il cambio: Sidecar visibile", is_visible(panel.sidecar_frame))
check("dopo il cambio: Automatica NON piu' visibile", not is_visible(panel.automatic_tools_frame))

# i widget della sidecar restano PIENAMENTE funzionanti indipendentemente
# dalla visibilita' (interazioni via codice, come farebbe il resto della
# suite - vedi test_gui_sidecar.py, gia' verde anche con lo strumento su
# 'automatic' di default)
check("il pulsante Registra e' comunque abilitato (non dipende dalla visibilita')",
      panel.sidecar_record_btn.cget('state') == 'normal')

# BPM (30/08, osservazione dell'utente confermata): la griglia di beat che ne
# deriva serve anche a _place_on_markers (beatInBar, gap in beat) e a
# enforce_playability (vincoli di spaziatura in beat) - un BPM sbagliato
# sposta quella griglia per ENTRAMBI gli strumenti, quindi il pannello BPM
# resta visibile su "Sidecar" tanto quanto su "Automatica", non nascosto
# dietro lo switch.
check("il pannello BPM resta visibile anche con lo strumento su 'Sidecar'",
      is_visible(panel.bpm_panel))

# tornando ad Automatica dallo stesso switch
panel._on_generate_tool_change(panel.t('generate_tool_automatic'))
root.update()
check("tornati ad Automatica: visibile di nuovo", is_visible(panel.automatic_tools_frame))
check("tornati ad Automatica: Sidecar di nuovo nascosta", not is_visible(panel.sidecar_frame))

# un SECONDO brano parte anch'esso da 'automatic', indipendentemente da cosa
# e' stato scelto sul primo - lo strumento e' per-brano, come sidecar_mode
panel._on_generate_tool_change(panel.t('generate_tool_sidecar'))  # brano 1 -> sidecar
panel._add_song(gui.read_generate_item(mp3), "?")
song2 = panel.songs[1]
song2['play_audio'] = __import__('numpy').zeros((44100 * 5, 2), dtype='float32')
song2['play_sr'] = 44100
panel.select_song(song2)
root.update()
check("nuovo brano: parte da 'automatic' a prescindere dal brano 1", song2['generate_tool'] == 'automatic')
check("nuovo brano: contenitore Automatica visibile", is_visible(panel.automatic_tools_frame))

# riselezionando il brano 1: lo switch torna a riflettere 'sidecar', la
# scelta fatta su di lui - non resta fermo su 'automatic' del brano 2
panel.select_song(song)
root.update()
check("riselezionando il brano 1: lo switch torna su 'sidecar'",
      panel.generate_tool_switch.get() == panel.t('generate_tool_sidecar'))
check("riselezionando il brano 1: Sidecar visibile di nuovo", is_visible(panel.sidecar_frame))

# il blocco di generazione (Genera/dry-run/progress) resta SEMPRE visibile,
# non e' parte dello switch - e' un fratello di preview_frame in self.scroll
check("il pulsante Genera esiste indipendentemente dallo strumento scelto",
      panel.run_btn is not None)

if panel.player is not None:
    panel.player.close()

print(f"\n{'TUTTO OK' if not errors else f'{len(errors)} FALLITI'}")
sys.exit(1 if errors else 0)
