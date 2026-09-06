# -*- coding: utf-8 -*-
"""Parita' funzionale: cosa sapeva fare la GUI Tkinter e cosa e' arrivato.

La domanda che risponde e' quella dell'utente: "manca qualcosa o hai perso
pezzi per strada rispetto a quello che poteva fare il tool?".

Metodo: si prendono i COMANDI della GUI vecchia (i metodi collegati a
pulsanti, cursori e interruttori - `command=self._...`), e per ognuno si
cerca il corrispondente nel port. Il corrispondente puo' essere un metodo
dell'Api, una funzione della pagina o un elemento del markup: la GUI vecchia
e il port non hanno gli stessi nomi, quindi la mappa e' scritta a mano una
volta e resta qui come documento vivo.

Un comando senza corrispondente NON e' per forza un difetto: alcuni non
hanno senso nel port (la GUI vecchia aveva un selettore di strumento perche'
era una finestra sola). Quelli stanno in ESCLUSI, con il motivo.

    python audit_parita.py
"""
import io
import os
import re
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# comando della GUI -> come si riconosce nel port (sottostringa da cercare)
MAPPA = {
    '_browse_folder':            'add_files',
    '_clear_songs':              'clear_list',
    '_on_remove':                'remove_song',
    '_start_processing':         ['run_correction', 'run_generation'],
    '_install_to_boxvr':         'install_run',
    '_open_boxvr_folder':        'open_game_folder',
    '_open_output_folder':       'open_folder',
    '_open_patch_dialog':        'toggle_patch',
    '_open_visual_preview':      'openVisualizer',
    # nel port la riproduzione principale non e' una funzione con un nome:
    # e' un ascoltatore sul pulsante #play-btn
    '_toggle_play':              "getElementById('play-btn').addEventListener",
    '_on_volume_slide':          'setVolume',
    '_on_zoom_slide':            'setZoomLevel',
    '_on_margin_slide':          'recompute',
    '_on_punch_ratio_slide':     'recompute',
    '_apply_preset_to_all':      ['apply_ratio_to_all', 'copyToAll'],
    '_on_theme_switch':          'toggleTheme',
    '_set_language':             'setLang',
    '_on_beat_engine_toggle':    'set_engine',
    '_on_click_track_toggle':    'toggle-base-beat',
    '_step_bpm':                 'set_forced_bpm',
    '_sidecar_mark':             'sidecar_mark',
    '_sidecar_clear':            'sidecar_clear',
    '_sidecar_reset':            'sidecar_reset',
    '_sidecar_toggle_record':    'sidecar_start_record',
    '_on_sidecar_mode_change':   'sidecar_set_mode',
    '_on_sidecar_exclude_toggle': 'sidecar_set_exclude_obstacles',
    '_on_sidecar_min_gap_slide': 'sidecar_set_min_gap_ms',
    '_on_choreo_preset_change':  'setPreset',
    '_set_timeline_mode':        'mini-structure',
    '_show_generate_info':       'showInfoPopover',
    '_undo_remove':              None,       # non portato: vedi sotto
    '_on_dry_run_toggle':        None,       # non portato: vedi sotto
    '_on_density_slide':         None,       # deliberatamente tolto
}

ESCLUSI = {
    '_pick_mode': 'la scelta Correggi/Genera ora e\' la Dashboard, non un '
                  'selettore dentro una finestra sola',
    '_on_generate_tool_change': 'stesso motivo: le due modalita\' sono due pagine',
}

# Non "mancanti per dimenticanza": mancanti e DECISI. La distinzione serve a
# non ritrovarsi fra sei mesi a chiedersi se erano rimasti indietro.
MANCANTI_NOTI = {
    '_undo_remove': 'RINUNCIATA (scelta dell\'utente, 03/09). Nel port la '
                    'rimozione non cancella nulla - toglie solo dall\'elenco - '
                    'e si rimedia con "Aggiungi brani +".',
    '_on_dry_run_toggle': 'RINUNCIATA (scelta dell\'utente, 03/09). Era la '
                          'modalita\' "solo report": eseguiva senza scrivere.',
    '_on_density_slide': 'Cursore densita\': tolto di proposito quando si e\' '
                         'scoperto che con la patch attiva non ha effetto '
                         '(vedi audit v1.25.0).',
}


def testo_del_port():
    pezzi = []
    for c in ('genera_real', 'correggi_real', 'dashboard_real', 'playlist_real'):
        for f in ('index.html', 'app.py'):
            p = os.path.join(QUI, c, f)
            if os.path.isfile(p):
                pezzi.append(io.open(p, encoding='utf-8').read())
    return '\n'.join(pezzi)


def main():
    gui = os.path.join(RADICE, 'boxvr_fixer_gui.py')
    if not os.path.isfile(gui):
        print('GUI Tkinter non trovata: niente da confrontare')
        return 0
    sorgente = io.open(gui, encoding='utf-8').read()
    comandi = sorted(set(re.findall(r'command=self\.(_\w+)', sorgente)))
    port = testo_del_port()

    presenti, mancanti, esclusi, non_mappati = [], [], [], []
    for c in comandi:
        if c in ESCLUSI:
            esclusi.append(c)
            continue
        if c not in MAPPA:
            non_mappati.append(c)
            continue
        atteso = MAPPA[c]
        if atteso is None:
            mancanti.append(c)
            continue
        chiavi = atteso if isinstance(atteso, list) else [atteso]
        if any(k in port for k in chiavi):
            presenti.append(c)
        else:
            mancanti.append(c)

    print('===== PARITA\' CON LA GUI TKINTER =====')
    print('  comandi della GUI esaminati: %d' % len(comandi))
    print('  presenti nel port          : %d' % len(presenti))
    for c in esclusi:
        print('  non applicabile  %-28s %s' % (c, ESCLUSI[c]))
    for c in mancanti:
        print('  MANCA            %-28s %s' % (c, MANCANTI_NOTI.get(c, '')))
    for c in non_mappati:
        print('  DA MAPPARE       %-28s (comando nuovo nella GUI: aggiungerlo a MAPPA)' % c)

    problemi = [c for c in mancanti if c not in MANCANTI_NOTI] + non_mappati
    if problemi:
        print('  %d comandi senza corrispondente e senza spiegazione' % len(problemi))
        return 1
    print('  nessuna perdita non spiegata')
    return 0


if __name__ == '__main__':
    sys.exit(main())
