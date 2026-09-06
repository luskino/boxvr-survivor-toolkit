"""Test headless della GUI di gestione playlist: nessuna finestra visibile
(root.withdraw()), e soprattutto MAI la libreria vera del gioco - boxvr_dirs
viene rimpiazzata con cartelle temporanee per l'intera durata del test."""
import json
import os
import sys
import tempfile

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boxvr_install as install
import boxvr_playlist_manager as pm

ok = fail = 0


def check(desc, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK   {desc}")
    else:
        fail += 1
        print(f"  FAIL {desc}")


def make_trackdata(td_dir, tid, name, artist, duration):
    with open(os.path.join(td_dir, tid + '.trackdata.txt'), 'w', encoding='utf-8') as f:
        json.dump({'originalTrackName': name, 'originalArtist': artist, 'duration': duration}, f)


def make_playlist(path, workout_name, track_ids, duration=0.0):
    data = {
        'definition': {'workoutName': workout_name, 'duration': duration},
        'songs': [{'trackDataName': tid, 'serialisedActionList': {'actionList': []}}
                  for tid in track_ids],
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)


tmp = tempfile.mkdtemp()
td = os.path.join(tmp, 'TrackData'); os.makedirs(td)
tdef = os.path.join(tmp, 'TrackDefinitions'); os.makedirs(tdef)
pdir = os.path.join(tmp, 'WorkoutPlaylists', 'BoxVR'); os.makedirs(pdir)

make_trackdata(td, 'aaa', 'Uno', 'Artista', 100.0)
make_trackdata(td, 'bbb', 'Due', 'Artista', 150.0)
make_playlist(os.path.join(pdir, 'Test.workoutplaylist.txt'), 'Test', ['aaa', 'bbb'], 250.0)

_real_boxvr_dirs = install.boxvr_dirs
install.boxvr_dirs = lambda: (td, tdef, pdir)   # mai la libreria vera durante il test

try:
    import boxvr_playlist_manager_gui as gui

    app = gui.PlaylistManagerApp()
    app.root.withdraw()

    check("all'avvio trova la playlist di test", len(app.playlists) == 1)
    check("nessuna playlist selezionata all'avvio -> pannello brani vuoto",
          app.current_data is None)

    entry = app.playlists[0]
    app._select_playlist(entry['path'])
    check("dopo la selezione i dati sono caricati", app.current_data is not None)
    check("non ci sono modifiche non salvate appena selezionata", not app.dirty)

    songs = pm.songs_with_names(app.current_data, trackdata_dir=td)
    check("mostra i 2 brani nell'ordine della playlist",
          [s['track_id'] for s in songs] == ['aaa', 'bbb'])

    app._move_song(0, 1)
    check("dopo lo spostamento diventa 'sporca' (modifiche non salvate)", app.dirty)
    check("l'ordine in memoria e' cambiato",
          [s['trackDataName'] for s in app.current_data['songs']] == ['bbb', 'aaa'])
    check("il file su disco NON e' ancora cambiato (nessun salvataggio automatico)",
          [s['trackDataName'] for s in pm.load_playlist(entry['path'])['songs']] == ['aaa', 'bbb'])

    app._discard_changes()
    check("annulla modifiche: torna all'ordine salvato", not app.dirty)
    check("annulla modifiche: l'ordine in memoria torna quello su disco",
          [s['trackDataName'] for s in app.current_data['songs']] == ['aaa', 'bbb'])

    app._remove_song(0)
    app._save_changes()
    check("dopo salva, il file su disco riflette la rimozione",
          [s['trackDataName'] for s in pm.load_playlist(entry['path'])['songs']] == ['bbb'])
    check("dopo salva, la durata e' stata ricalcolata sui brani rimasti",
          pm.load_playlist(entry['path'])['definition']['duration'] == 150.0)
    check("dopo salva, non e' piu' 'sporca'", not app.dirty)

    app.refresh_playlists()
    check("l'elenco a sinistra riflette il nuovo conteggio brani dopo il salvataggio",
          app.playlists[0]['num_songs'] == 1)

    # rinomina tramite la funzione di supporto (senza passare dal dialogo modale)
    new_path = pm.rename_playlist(entry['path'], 'Rinominata')
    app.refresh_playlists()
    check("dopo la rinomina esterna, l'elenco la trova col nuovo nome",
          any(p['workout_name'] == 'Rinominata' for p in app.playlists))

    pm.delete_playlist(new_path)
    app.refresh_playlists()
    check("dopo l'eliminazione l'elenco risulta vuoto", app.playlists == [])

    app._toggle_lang()
    check("il cambio lingua non solleva eccezioni e aggiorna lo stato interno",
          app.lang == 'en')
    app._toggle_lang()
    check("torna alla lingua originale", app.lang == 'it')

    app.root.destroy()
finally:
    install.boxvr_dirs = _real_boxvr_dirs

print(f"\n{'=' * 52}")
print(f"{ok} passati, {fail} falliti")
sys.exit(1 if fail else 0)
