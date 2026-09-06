"""Test di boxvr_playlist_manager: gira su cartelle temporanee, non tocca
MAI la libreria vera del gioco - stesso principio di test_install.py."""
import json
import os
import sys
import tempfile

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
        'definition': {'workoutName': workout_name, 'game': 0, 'workoutStyle': 0,
                       'authorName': 'author', 'trackGenre': 0, 'leaderboardId': 'undefined',
                       'sonyLeaderboardId': -1, 'workoutId': '', 'hasSquats': False,
                       'hasJumps': False, 'workoutType': 1, 'duration': duration},
        'songs': [{'trackDataName': tid, 'serialisedActionList': {'actionList': []}}
                  for tid in track_ids],
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return data


print("list_playlists")
with tempfile.TemporaryDirectory() as tmp:
    pdir = os.path.join(tmp, 'playlists'); os.makedirs(pdir)
    make_playlist(os.path.join(pdir, 'Prova A.workoutplaylist.txt'), 'Prova A', ['aaa', 'bbb'], 120.0)
    make_playlist(os.path.join(pdir, 'Prova B.workoutplaylist.txt'), 'Prova B', ['ccc'], 60.0)
    with open(os.path.join(pdir, 'non una playlist.txt'), 'w') as f:
        f.write('ignorami')
    with open(os.path.join(pdir, 'corrotta.workoutplaylist.txt'), 'w') as f:
        f.write('{non e json valido')

    found = pm.list_playlists(pdir)
    check("trova solo i 2 file .workoutplaylist.txt validi (non il .txt normale, "
          "non quello corrotto)", len(found) == 2)
    check("ordine alfabetico per nome file",
          [p['filename'] for p in found] == ['Prova A.workoutplaylist.txt', 'Prova B.workoutplaylist.txt'])
    check("legge workout_name/num_songs/duration correttamente",
          found[0]['workout_name'] == 'Prova A' and found[0]['num_songs'] == 2
          and found[0]['duration'] == 120.0)
    check("cartella inesistente -> lista vuota, non errore",
          pm.list_playlists(os.path.join(tmp, 'non_esiste')) == [])

print("\nload_playlist / save_playlist")
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, 'x.workoutplaylist.txt')
    make_playlist(path, 'X', ['aaa'])
    data = pm.load_playlist(path)
    check("carica correttamente un file valido", data['definition']['workoutName'] == 'X')
    check("file mancante -> None, non eccezione",
          pm.load_playlist(os.path.join(tmp, 'nope.txt')) is None)
    with open(os.path.join(tmp, 'corrotta.txt'), 'w') as f:
        f.write('{rotto')
    check("file corrotto -> None, non eccezione",
          pm.load_playlist(os.path.join(tmp, 'corrotta.txt')) is None)
    data['definition']['workoutName'] = 'X modificata'
    pm.save_playlist(path, data)
    check("round-trip: la modifica e' sul disco dopo save+load",
          pm.load_playlist(path)['definition']['workoutName'] == 'X modificata')

print("\nsongs_with_names")
with tempfile.TemporaryDirectory() as tmp:
    td = os.path.join(tmp, 'TrackData'); os.makedirs(td)
    make_trackdata(td, 'aaa', 'Brano Uno', 'Artista Uno', 100.0)
    make_trackdata(td, 'bbb', 'Brano Due', 'Artista Due', 200.0)
    data = make_playlist(os.path.join(tmp, 'p.workoutplaylist.txt'), 'P', ['aaa', 'bbb'])
    songs = pm.songs_with_names(data, trackdata_dir=td)
    check("ritorna 2 brani nell'ordine della playlist", [s['track_id'] for s in songs] == ['aaa', 'bbb'])
    check("nomi leggibili letti dal trackdata",
          songs[0]['display_name'] == 'Brano Uno — Artista Uno')
    check("durate lette dal trackdata", songs[0]['duration'] == 100.0 and songs[1]['duration'] == 200.0)
    check("indici progressivi", [s['index'] for s in songs] == [0, 1])

print("\nmove_song")
with tempfile.TemporaryDirectory() as tmp:
    data = make_playlist(os.path.join(tmp, 'p.workoutplaylist.txt'), 'P', ['aaa', 'bbb', 'ccc'])
    pm.move_song(data, 0, 2)
    check("sposta il primo brano in ultima posizione",
          [s['trackDataName'] for s in data['songs']] == ['bbb', 'ccc', 'aaa'])
    pm.move_song(data, 2, 0)
    check("e viceversa torna all'ordine originale",
          [s['trackDataName'] for s in data['songs']] == ['aaa', 'bbb', 'ccc'])
    try:
        pm.move_song(data, 5, 0)
        check("indice fuori range solleva IndexError", False)
    except IndexError:
        check("indice fuori range solleva IndexError", True)

print("\nremove_song")
with tempfile.TemporaryDirectory() as tmp:
    data = make_playlist(os.path.join(tmp, 'p.workoutplaylist.txt'), 'P', ['aaa', 'bbb', 'ccc'])
    pm.remove_song(data, 1)
    check("toglie esattamente il brano all'indice dato",
          [s['trackDataName'] for s in data['songs']] == ['aaa', 'ccc'])
    try:
        pm.remove_song(data, 99)
        check("indice fuori range solleva IndexError", False)
    except IndexError:
        check("indice fuori range solleva IndexError", True)

print("\nrecompute_duration")
with tempfile.TemporaryDirectory() as tmp:
    td = os.path.join(tmp, 'TrackData'); os.makedirs(td)
    make_trackdata(td, 'aaa', 'A', 'Artista', 90.0)
    make_trackdata(td, 'bbb', 'B', 'Artista', 150.0)
    data = make_playlist(os.path.join(tmp, 'p.workoutplaylist.txt'), 'P', ['aaa', 'bbb'], duration=0.0)
    pm.recompute_duration(data, trackdata_dir=td)
    check("somma le durate reali dei brani rimasti", data['definition']['duration'] == 240.0)
    pm.remove_song(data, 0)
    pm.recompute_duration(data, trackdata_dir=td)
    check("dopo una rimozione la durata si aggiorna di conseguenza",
          data['definition']['duration'] == 150.0)

print("\nrename_playlist")
with tempfile.TemporaryDirectory() as tmp:
    pdir = os.path.join(tmp, 'playlists'); os.makedirs(pdir)
    old_path = os.path.join(pdir, 'Vecchio nome.workoutplaylist.txt')
    make_playlist(old_path, 'Vecchio nome', ['aaa'])
    new_path = pm.rename_playlist(old_path, 'Nuovo nome')
    check("il nuovo file esiste col nome atteso",
          new_path == os.path.join(pdir, 'Nuovo nome.workoutplaylist.txt') and os.path.isfile(new_path))
    check("il vecchio file non esiste piu'", not os.path.isfile(old_path))
    check("il campo workoutName dentro il file e' aggiornato",
          pm.load_playlist(new_path)['definition']['workoutName'] == 'Nuovo nome')

    make_playlist(os.path.join(pdir, 'Occupato.workoutplaylist.txt'), 'Occupato', ['bbb'])
    try:
        pm.rename_playlist(new_path, 'Occupato')
        check("rinominare su un nome gia' esistente solleva FileExistsError, "
              "non sovrascrive in silenzio", False)
    except FileExistsError:
        check("rinominare su un nome gia' esistente solleva FileExistsError, "
              "non sovrascrive in silenzio", True)
    check("dopo il tentativo fallito il file originale e' ancora li' intatto",
          os.path.isfile(new_path) and pm.load_playlist(new_path)['definition']['workoutName'] == 'Nuovo nome')

    try:
        pm.rename_playlist(new_path, '   ')
        check("nome vuoto (solo spazi) solleva ValueError", False)
    except ValueError:
        check("nome vuoto (solo spazi) solleva ValueError", True)

    same_path = pm.rename_playlist(new_path, 'Nuovo nome')
    check("rinominare allo STESSO nome non solleva FileExistsError su se stesso",
          same_path == new_path and os.path.isfile(new_path))

print("\ndelete_playlist")
with tempfile.TemporaryDirectory() as tmp:
    pdir = os.path.join(tmp, 'playlists'); os.makedirs(pdir)
    path = os.path.join(pdir, 'Da cancellare.workoutplaylist.txt')
    make_playlist(path, 'Da cancellare', ['aaa'])
    dest = pm.delete_playlist(path)
    check("il file non e' piu' nella cartella originale", not os.path.isfile(path))
    check("il file e' stato spostato (non cancellato per sempre) nel backup",
          os.path.isfile(dest))
    check("il contenuto e' preservato nel backup",
          pm.load_playlist(dest)['definition']['workoutName'] == 'Da cancellare')

    # cancellarne un'altra con lo STESSO nome file non deve sovrascrivere il backup precedente
    path2 = os.path.join(pdir, 'Da cancellare.workoutplaylist.txt')
    make_playlist(path2, 'Da cancellare (seconda)', ['bbb'])
    dest2 = pm.delete_playlist(path2)
    check("un secondo file con lo stesso nome ottiene un backup con nome distinto",
          dest2 != dest and os.path.isfile(dest) and os.path.isfile(dest2))
    check("il backup precedente non e' stato sovrascritto",
          pm.load_playlist(dest)['definition']['workoutName'] == 'Da cancellare')

print(f"\n{'=' * 52}")
print(f"{ok} passati, {fail} falliti")
sys.exit(1 if fail else 0)
