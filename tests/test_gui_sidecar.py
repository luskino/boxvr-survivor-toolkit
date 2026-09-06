"""Verifica funzionale del pannello sidecar appena aggiunto alla GUI (26/08
notte) - non solo che i widget si costruiscano senza eccezioni (gia' verificato
lanciando l'app 15s senza crash), ma che i METODI veri facciano quello che
devono: registrare, marcare, fermare, abilitare, cancellare - pilotati come
farebbe un click reale, senza aprire una finestra interattiva."""
import os
import sys
import time
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
root.withdraw()  # nessuna finestra visibile, ma i widget CTk sono reali

app = gui.BoxVRFixerApp(root, app_mode='generate')
panel = app.generate_panel
assert panel is not None, "generate_panel non costruito"
assert panel.sidecar_frame is not None, "pannello sidecar non costruito in modalita' generate"

mp3 = audio_di_prova('Chop Suey!.mp3')
import numpy as np

errors = []


def check(label, cond):
    print(("  OK   " if cond else "  FAIL ") + label)
    if not cond:
        errors.append(label)


# Bug reale trovato dall'utente il 27/08: il pannello sidecar restava
# "Registra" disabilitato per sempre se il brano veniva selezionato PRIMA che
# l'analisi in background finisse di caricare l'audio - _poll_analysis_queue
# aggiornava play_btn/visual_btn ma non il pannello sidecar. Riprodotto qui
# esattamente nell'ordine sbagliato (selezione PRIMA che play_audio arrivi),
# non impostando play_audio prima come negli altri test di questo file.
panel._add_song(gui.read_generate_item(mp3), "?")
song = panel.songs[0]
panel.select_song(song)   # play_audio ancora None qui, come durante l'analisi vera
check("appena selezionato, senza audio ancora pronto: Registra disabilitato",
      panel.sidecar_record_btn.cget('state') == 'disabled')
check("...e anche l'area grande Marca e' disabilitata",
      panel.sidecar_mark_area.cget('state') == 'disabled')

# l'audio "arriva" (come farebbe _poll_analysis_queue in background) - il
# fix e' che quel punto ora chiama _refresh_sidecar_panel()
song['play_audio'] = np.zeros((44100 * 5, 2), dtype='float32')
song['play_sr'] = 44100
panel._refresh_sidecar_panel()
check("dopo che l'audio e' pronto: Registra si abilita da solo",
      panel.sidecar_record_btn.cget('state') == 'normal')

panel.select_song(song)


check("prima della selezione: 0 marker mostrati", panel.sidecar_count_label.cget('text') == panel.t('sidecar_count', n=0))
check("pulsante Registra abilitato con un brano caricato", panel.sidecar_record_btn.cget('state') == 'normal')
# il pulsante "Marca" piccolo e' stato tolto il 27/08 (ridondante con l'area
# grande) - resta solo quest'ultima da verificare, vedi sotto
check("area grande Marca disabilitata finche' non si registra", panel.sidecar_mark_area.cget('state') == 'disabled')

panel._sidecar_toggle_record()
check("dopo 'Registra': stato di registrazione attivo", panel._sidecar_recording is True)
check("dopo 'Registra': anche l'area grande Marca e' abilitata (27/08)",
      panel.sidecar_mark_area.cget('state') == 'normal')
check("dopo 'Registra': player creato per il brano", panel.player is not None and panel._player_song is song)

# l'area grande deve marcare esattamente come il pulsante piccolo (stesso
# comando, non un secondo percorso separato che potrebbe disallinearsi)
panel.sidecar_mark_area.cget('command')()
check("l'area grande registra un marker come il pulsante piccolo",
      len(song['sidecar_markers']) == 1)

for _ in range(2):
    panel._sidecar_mark()
check(f"3 marker registrati in totale (trovati {len(song['sidecar_markers'])})", len(song['sidecar_markers']) == 3)
check("etichetta conteggio aggiornata a 3", panel.sidecar_count_label.cget('text') == panel.t('sidecar_count', n=3))

panel._sidecar_toggle_record()
check("dopo 'Ferma': registrazione non piu' attiva", panel._sidecar_recording is False)
check("dopo 'Ferma': l'area grande Marca si ridisabilita",
      panel.sidecar_mark_area.cget('state') == 'disabled')
check("dopo 'Ferma': i 3 marker restano (non azzerati)", len(song['sidecar_markers']) == 3)

# nessun interruttore da attivare (tolto il 27/08): se ci sono marker si
# usano, punto - verificato dalla nota informativa, non da uno stato separato
check("con marker presenti, la nota dice che vengono usati",
      panel.sidecar_usage_label.cget('text') == panel.t('sidecar_usage_note_active'))

# "Registra" e' ora un punch-in dal punto corrente della timeline (30/08,
# richiesto esplicitamente: "così posso continuare la registrazione se mi
# fermo e voglio registrare sopra un punto che non mi è piaciuto") - non
# azzera piu' tutto e non riparte piu' sempre da zero.
song['sidecar_markers'] = [1.0, 2.0, 5.0, 8.0]
panel.player.seek(4.0)
panel._sidecar_toggle_record()
check(f"Registra da un punto intermedio: i marker PRIMA del punto restano intatti, "
      f"quelli DA QUEL PUNTO IN POI vengono scartati (trovati {sorted(song['sidecar_markers'])})",
      sorted(song['sidecar_markers']) == [1.0, 2.0])
check(f"Registra da un punto intermedio: la riproduzione riparte da LI', non da zero "
      f"(posizione trovata {panel.player.position_seconds():.2f}s)",
      abs(panel.player.position_seconds() - 4.0) < 0.5)
panel._sidecar_toggle_record()  # Ferma, per ripulire lo stato prima di proseguire

# cambio brano: la registrazione in corso (se ce ne fosse una) deve fermarsi,
# e il pannello deve riflettere lo stato del NUOVO brano selezionato
panel._add_song(gui.read_generate_item(mp3), "?")
song2 = panel.songs[1]
song2['play_audio'] = __import__('numpy').zeros((44100 * 5, 2), dtype='float32')
song2['play_sr'] = 44100
panel.select_song(song2)
check("nuovo brano: 0 marker (non eredita quelli del brano precedente)",
      len(song2.get('sidecar_markers') or []) == 0)
check("nuovo brano: area grande Marca disabilitata (nessuna registrazione in corso)",
      panel.sidecar_mark_area.cget('state') == 'disabled')

panel._sidecar_clear()  # sul brano 2, senza marker: non deve sollevare eccezioni
check("Cancella su un brano senza marker non solleva eccezioni", True)

# stessa identica espressione usata dal flusso reale di generazione (vedi
# _run_generate) per costruire gli 'items' passati a generate_songs - verifica
# che il brano CON marker li porti e quello senza no, senza alcun interruttore
# di mezzo (tolto il 27/08: se ci sono si usano, punto).
items = [{'marker_times': s.get('sidecar_markers') or None} for s in panel.songs]
check(f"items: brano 1 (3 marker) porta marker_times (trovato {items[0]['marker_times']})",
      items[0]['marker_times'] == song['sidecar_markers'])
check(f"items: brano 2 (nessun marker) ha marker_times=None (trovato {items[1]['marker_times']})",
      items[1]['marker_times'] is None)

# modalita' e "solo hit marker" (27/08, richiesti esplicitamente)
panel.select_song(song)
check("modalita' di default e' 'harmonize'", song['sidecar_mode'] == 'harmonize')
check("il menu modalita' mostra l'etichetta di 'harmonize'",
      panel.sidecar_mode_menu.get() == panel.t('sidecar_mode_harmonize'))

panel._on_sidecar_mode_change(panel.t('sidecar_mode_markers_only'))
check("cambiare il menu aggiorna song['sidecar_mode']", song['sidecar_mode'] == 'markers_only')

# 'automatic' rimosso il 30/08 dal menu modalita' della sidecar (ridondante
# con lo strumento "Automatica" a se stante); 'extend' aggiunta lo stesso
# giorno (fedele ai marker dove ci sono, automatico pieno dove non ci sono).
check("il menu modalita' ha tre voci (niente piu' 'Automatico', ora c'e' 'Estendi')",
      list(panel.sidecar_mode_menu.cget('values')) ==
      [panel.t('sidecar_mode_markers_only'), panel.t('sidecar_mode_harmonize'),
       panel.t('sidecar_mode_extend')])
check("un'etichetta sconosciuta (residuo di una versione precedente) ricade su 'harmonize'",
      panel._sidecar_mode_from_label("Automatico") == 'harmonize')

panel._on_sidecar_mode_change(panel.t('sidecar_mode_extend'))
check("selezionare 'Estendi' aggiorna song['sidecar_mode']", song['sidecar_mode'] == 'extend')
panel._on_sidecar_mode_change(panel.t('sidecar_mode_markers_only'))

check("'solo hit marker' e' spento di default", song['sidecar_exclude_obstacles'] is False)
panel.sidecar_exclude_switch.select()
panel._on_sidecar_exclude_toggle()
check("accendere lo switch aggiorna song['sidecar_exclude_obstacles']",
      song['sidecar_exclude_obstacles'] is True)

# gli items reali portano anche questi due campi, non solo marker_times
items2 = [{'sidecar_mode': s.get('sidecar_mode'), 'exclude_obstacles': bool(s.get('sidecar_exclude_obstacles'))}
          for s in panel.songs]
check(f"items: modalita' e esclusione ostacoli propagate (trovato {items2[0]})",
      items2[0] == {'sidecar_mode': 'markers_only', 'exclude_obstacles': True})

# "Resetta" (30/08, richiesto insieme al nuovo Registra "punch-in" - serve un
# modo esplicito per azzerare TUTTO lo stato sidecar di un brano, non solo i
# marker come "Cancella") - a questo punto il brano ha gia' marker non vuoti,
# modalita' non-default, "solo hit marker" acceso: buono stato di partenza
# per verificare che Resetta li riporti TUTTI ai default in un colpo solo.
panel._on_sidecar_min_gap_slide(90)
check("stato di partenza per il test di Resetta: qualcosa e' gia' cambiato dal default",
      (song['sidecar_markers'], song['sidecar_mode'], song['sidecar_exclude_obstacles'],
       song['sidecar_min_gap_ms']) != ([], 'harmonize', False, None))
check("'Resetta' e' abilitato quando c'e' qualcosa da riportare al default",
      panel.sidecar_reset_btn.cget('state') == 'normal')

panel._sidecar_reset()
check("Resetta: marker azzerati", song['sidecar_markers'] == [])
check("Resetta: modalita' tornata a 'harmonize'", song['sidecar_mode'] == 'harmonize')
check("Resetta: 'solo hit marker' tornato spento", song['sidecar_exclude_obstacles'] is False)
check("Resetta: soglia minima tornata al default (None = 170ms del motore)",
      song['sidecar_min_gap_ms'] is None)
check("dopo Resetta: il pulsante si ridisabilita (niente piu' da resettare)",
      panel.sidecar_reset_btn.cget('state') == 'disabled')

# calibrazione personale (27/08, "il tool impara da come l'utente in
# locale crea i marker") - test diretto su _learn_sidecar_bias, non tramite
# una registrazione reale (audible_position_seconds dipende dal device
# audio vero, non pilotabile in un test headless)
app.settings.pop('sidecar_bias_s', None)
app.settings.pop('sidecar_bias_n', None)

song['analysis'] = None
song['sidecar_markers'] = [1.0, 2.0]
panel._learn_sidecar_bias(song)
check("senza analisi disponibile: nessun crash, nessun bias salvato",
      'sidecar_bias_s' not in app.settings)

song['analysis'] = {'onsets': [1.0, 2.0, 3.0, 4.0]}
song['sidecar_markers'] = [1.05, 2.05, 3.05]
panel._learn_sidecar_bias(song)
check(f"prima sessione: bias appreso vicino a +0.05s (trovato {app.settings.get('sidecar_bias_s')})",
      abs(app.settings.get('sidecar_bias_s', 0) - 0.05) < 1e-6)
check("prima sessione: 3 campioni contati", app.settings.get('sidecar_bias_n') == 3)

# una seconda sessione con offset diverso deve MEDIARE con la precedente
# (pesata per conteggio), non sovrascriverla - e' la stessa idea di
# "tendenza accumulata", non l'ultima sessione isolata
song['sidecar_markers'] = [1.15, 2.15, 3.15]
panel._learn_sidecar_bias(song)
expected = (0.05 * 3 + 0.15 * 3) / 6
check(f"seconda sessione: bias mediato pesato per conteggio (trovato {app.settings.get('sidecar_bias_s')}, atteso {expected})",
      abs(app.settings.get('sidecar_bias_s', 0) - expected) < 1e-6)
check("seconda sessione: conteggio campioni cumulato a 6", app.settings.get('sidecar_bias_n') == 6)

# un marker lontanissimo da qualunque accento reale (fuori dalla finestra di
# apprendimento) non deve sporcare la media - e' probabilmente un colpo
# voluto su un levare, non un tap impreciso
app.settings.pop('sidecar_bias_s', None)
app.settings.pop('sidecar_bias_n', None)
song['sidecar_markers'] = [1.05, 50.0]
panel._learn_sidecar_bias(song)
check(f"outlier fuori finestra escluso dalla media (trovato {app.settings.get('sidecar_bias_s')})",
      abs(app.settings.get('sidecar_bias_s', 0) - 0.05) < 1e-6)
check("outlier fuori finestra: solo 1 campione contato", app.settings.get('sidecar_bias_n') == 1)

# _sidecar_mark deve sottrarre il bias appreso, non solo la latenza hardware
# (nota: 'song' e' gia' panel.current_song da una select_song precedente in
# questo file - qui si evita di richiamare select_song, che creerebbe un
# vero player audio, e si sostituisce solo panel.player con un finto)
real_player, real_recording = panel.player, panel._sidecar_recording
app.settings['sidecar_bias_s'] = 0.05
song['sidecar_markers'] = []
panel._sidecar_recording = True


class _FakePlayer:
    def audible_position_seconds(self):
        return 2.0


panel.player = _FakePlayer()
panel._sidecar_mark()
check(f"_sidecar_mark sottrae il bias appreso (trovato {song['sidecar_markers']})",
      song['sidecar_markers'] == [1.95])
panel._sidecar_recording = real_recording
panel.player = real_player
app.settings.pop('sidecar_bias_s', None)
app.settings.pop('sidecar_bias_n', None)

# visibilita' + controllo sui marker scartati dal limite fisico (30/08,
# trovato analizzando un test reale su Master of Puppets: 119 marker
# piazzati, solo 78 mosse reali nella sezione marcata - il resto scartato IN
# SILENZIO da MIN_INPUT_GAP_S senza che l'utente potesse saperlo). Prima
# richiesta la sola visibilita', poi esplicitamente uno slider per la soglia
# con indicatore live di quanti marker verrebbero rimossi.
check(f"slider soglia: parte dal default 170ms (trovato {panel.sidecar_min_gap_slider.get()})",
      abs(panel.sidecar_min_gap_slider.get() - gui.SIDECAR_MIN_GAP_DEFAULT_MS) < 1e-6)

song['sidecar_markers'] = [1.00, 2.00, 3.00]  # ben distanziati, nessuno scartato alla soglia di default
panel._refresh_sidecar_panel()
check(f"marker ben distanziati: nessuno scartato (trovato '{panel.sidecar_min_gap_dropped_label.cget('text')}')",
      panel.sidecar_min_gap_dropped_label.cget('text') == panel.t('sidecar_min_gap_none_dropped'))

song['sidecar_markers'] = [1.000, 1.050, 1.100, 3.000]  # i primi 3 entro 170ms fra loro
panel._refresh_sidecar_panel()
check(f"marker troppo ravvicinati alla soglia di default: l'etichetta dedicata avvisa quanti "
      f"(trovato '{panel.sidecar_min_gap_dropped_label.cget('text')}')",
      panel.sidecar_min_gap_dropped_label.cget('text') == panel.t('sidecar_min_gap_dropped', dropped=2, n=4))
check("il conteggio marker resta il conteggio grezzo (non duplica l'avviso)",
      panel.sidecar_count_label.cget('text') == panel.t('sidecar_count', n=4))

# abbassare la soglia sotto 100ms fa sopravvivere anche il marker a 1.100
# (100ms dal precedente sopravvissuto 1.000) - l'indicatore deve seguire lo
# slider in diretta, non restare fermo al valore calcolato all'apertura
panel._on_sidecar_min_gap_slide(90)
check(f"soglia abbassata a 90ms: solo il marker a 50ms dal precedente resta scartato "
      f"(trovato '{panel.sidecar_min_gap_dropped_label.cget('text')}')",
      panel.sidecar_min_gap_dropped_label.cget('text') == panel.t('sidecar_min_gap_dropped', dropped=1, n=4))
check("song['sidecar_min_gap_ms'] aggiornato dallo slider", song['sidecar_min_gap_ms'] == 90)

song['analysis'] = None
panel._refresh_sidecar_panel()
check("senza analisi pronta: l'aggancio agli accenti e' saltato ma il conteggio dei "
      "troppo-vicini resta calcolabile (non dipende dagli onset)",
      panel.sidecar_min_gap_dropped_label.cget('text') == panel.t('sidecar_min_gap_dropped', dropped=1, n=4))

# cambiare brano deve ripristinare la soglia del NUOVO brano (default, se mai
# toccata), non trascinarsi dietro quella appena impostata sul brano 1
panel.select_song(song2)
check(f"nuovo brano: slider torna al default 170ms (trovato {panel.sidecar_min_gap_slider.get()})",
      abs(panel.sidecar_min_gap_slider.get() - gui.SIDECAR_MIN_GAP_DEFAULT_MS) < 1e-6)
panel.select_song(song)

if panel.player is not None:
    panel.player.close()
# il thread nativo di PortAudio impiega un istante a fermarsi davvero dopo
# stream.close() - distruggere subito la radice Tk rischia una corsa con
# quella chiusura e un segfault all'uscita dell'interprete (visto qui: tutte
# le verifiche sopra passano, "TUTTO OK" viene stampato, poi crash - quindi
# non e' un difetto della sidecar, e' solo l'ordine di spegnimento in questo
# script). La pausa serve SEMPRE prima di root.destroy(), non solo quando
# panel.player e' ancora valorizzato qui: select_song(song2) sopra ha gia'
# chiuso e azzerato lo stream del primo brano internamente, quindi la corsa
# esiste anche se questo script non vede piu' nessun player da chiudere.
# Non serve nella GUI vera, che resta viva nel mainloop invece di chiudere
# tutto subito dopo.
time.sleep(0.3)
root.destroy()
print(f"\n{'TUTTO OK' if not errors else f'{len(errors)} FALLITI'}")
sys.exit(1 if errors else 0)
