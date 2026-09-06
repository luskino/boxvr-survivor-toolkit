#!/usr/bin/env python3
# BoxVR Survivor Toolkit - Copyright (C) 2026 Luca Giuseppe Buttacavoli
#
# Questo programma e' software libero: puoi ridistribuirlo e/o modificarlo
# secondo i termini della GNU General Public License come pubblicata dalla
# Free Software Foundation, versione 3 o (a tua scelta) successiva.
#
# E' distribuito nella speranza che sia utile, ma SENZA ALCUNA GARANZIA;
# senza neppure la garanzia implicita di COMMERCIABILITA' o IDONEITA' PER UNO
# SCOPO PARTICOLARE. Vedi la GNU General Public License per i dettagli.
#
# Dovresti aver ricevuto una copia della licenza insieme a questo programma
# (file LICENSE). Altrimenti: <https://www.gnu.org/licenses/>.

r"""
Gestione delle playlist esistenti nella libreria live di BoxVR
================================================================
Tool separato (non integrato nella GUI principale) per vedere, rinominare,
riordinare/rimuovere brani e cancellare le `.workoutplaylist.txt` gia'
installate — l'alternativa a modificarle a mano con un editor di testo.

Ambito deciso esplicitamente il 30/08/2026 notte ("Gestione base"): SOLO
operazioni sulla struttura della playlist (nome, ordine, presenza dei
brani). Non unione playlist, non rilevamento duplicati fra playlist diverse
— rimandato a una eventuale "gestione avanzata" futura, non ambito di
questo modulo.

Come `boxvr_install.py`, la logica qui non sa nulla di interfaccia: decide,
non chiede. Le conferme restano a chi chiama (la GUI). Riusa `boxvr_dirs`/
`track_display_name`/`track_duration` da `boxvr_install.py` invece di
duplicare i percorsi o lo schema del file per la terza volta nel progetto.
"""
import json
import os
import shutil

import boxvr_install as install

PLAYLIST_SUFFIX = '.workoutplaylist.txt'


def list_playlists(playlists_dir=None):
    """Le playlist presenti nella libreria live, con nome/numero
    brani/durata gia' letti — pronte per un elenco in interfaccia senza che
    chi chiama debba aprire ogni file da solo."""
    playlists_dir = playlists_dir or install.boxvr_dirs()[2]
    out = []
    if not os.path.isdir(playlists_dir):
        return out
    for fn in sorted(os.listdir(playlists_dir)):
        if not fn.endswith(PLAYLIST_SUFFIX):
            continue
        path = os.path.join(playlists_dir, fn)
        data = load_playlist(path)
        if data is None:
            continue   # file illeggibile/corrotto - non blocca il resto dell'elenco
        defn = data.get('definition') or {}
        out.append({
            'filename': fn,
            'path': path,
            'workout_name': defn.get('workoutName', fn[:-len(PLAYLIST_SUFFIX)]),
            'num_songs': len(data.get('songs') or []),
            'duration': defn.get('duration', 0.0),
        })
    return out


def load_playlist(path):
    """None su file mancante/corrotto — mai un'eccezione: una playlist
    illeggibile non deve impedire di vedere le altre (stessa scelta gia'
    fatta in boxvr_install.playlists_without_choreography)."""
    try:
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def save_playlist(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def songs_with_names(data, trackdata_dir=None):
    """I brani di una playlist gia' caricata, con nome leggibile e durata -
    per popolare la lista in interfaccia senza altre letture da chi chiama."""
    trackdata_dir = trackdata_dir or install.boxvr_dirs()[0]
    out = []
    for i, s in enumerate((data or {}).get('songs') or []):
        tid = s.get('trackDataName')
        out.append({
            'index': i,
            'track_id': tid,
            'display_name': install.track_display_name(trackdata_dir, tid),
            'duration': install.track_duration(trackdata_dir, tid),
        })
    return out


def move_song(data, from_index, to_index):
    """Sposta un brano in una nuova posizione (riordino) - muta `data` sul
    posto e lo ritorna anche, comodo per un'unica riga da chi chiama.
    Nessun ricalcolo di durata: riordinare non cambia quali brani ci sono."""
    songs = data.get('songs') or []
    if not (0 <= from_index < len(songs)):
        raise IndexError(f"from_index {from_index} fuori range (0-{len(songs) - 1})")
    if not (0 <= to_index < len(songs)):
        raise IndexError(f"to_index {to_index} fuori range (0-{len(songs) - 1})")
    song = songs.pop(from_index)
    songs.insert(to_index, song)
    return data


def remove_song(data, index):
    """Toglie un brano dalla playlist - muta `data` sul posto. Chi chiama
    deve poi richiamare `recompute_duration` prima di salvare, la durata
    totale e' cambiata."""
    songs = data.get('songs') or []
    if not (0 <= index < len(songs)):
        raise IndexError(f"index {index} fuori range (0-{len(songs) - 1})")
    del songs[index]
    return data


def recompute_duration(data, trackdata_dir=None):
    """Ricalcola `definition.duration` sommando la durata reale di ogni
    brano rimasto - stessa fonte (il trackdata installato) gia' usata da
    `boxvr_install.add_to_playlist`, cosi' le due strade restano coerenti."""
    trackdata_dir = trackdata_dir or install.boxvr_dirs()[0]
    total = sum(install.track_duration(trackdata_dir, s.get('trackDataName'))
                for s in (data.get('songs') or []))
    data.setdefault('definition', {})['duration'] = total
    return data


def rename_playlist(path, new_name, playlists_dir=None):
    """Rinomina una playlist: aggiorna `definition.workoutName` E il file su
    disco. Il nome file rispecchia sempre esattamente `workoutName` nei
    file reali della libreria (verificato sulle playlist gia' installate:
    "nice workout" -> "nice workout.workoutplaylist.txt") - tenerli
    disallineati confonderebbe qualunque cosa legga l'uno o l'altro.

    Ritorna il nuovo path. Solleva FileExistsError se una playlist con quel
    nome esiste gia' (mai sovrascrivere un'altra playlist dell'utente in
    silenzio)."""
    data = load_playlist(path)
    if data is None:
        raise FileNotFoundError(path)
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("il nome della playlist non puo' essere vuoto")
    data.setdefault('definition', {})['workoutName'] = new_name

    playlists_dir = playlists_dir or os.path.dirname(path)
    new_path = os.path.join(playlists_dir, new_name + PLAYLIST_SUFFIX)
    same_file = os.path.normcase(os.path.abspath(new_path)) == os.path.normcase(os.path.abspath(path))
    if not same_file and os.path.isfile(new_path):
        raise FileExistsError(f"esiste gia' una playlist chiamata '{new_name}'")

    save_playlist(new_path, data)
    if not same_file:
        os.remove(path)
    return new_path


def delete_playlist(path, backup_dir=None):
    """Sposta la playlist in una sottocartella di backup invece di
    cancellarla definitivamente - coerente con la disciplina del progetto
    di preferire sempre un'azione reversibile su dati reali dell'utente
    (stesso principio di `OLD Ver.zip` per gli eseguibili superati, qui
    applicato ai dati dell'utente invece che alle build). Non tocca i
    brani stessi (trackdata/wav/wdef) - solo il file playlist, che e' solo
    un indice: i brani restano installati e riusabili in un'altra playlist.

    Ritorna il percorso del file spostato."""
    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(path), '_playlist_eliminate_backup')
    os.makedirs(backup_dir, exist_ok=True)
    dest = os.path.join(backup_dir, os.path.basename(path))
    if os.path.exists(dest):
        base, ext = os.path.splitext(os.path.basename(path))
        i = 1
        while os.path.exists(dest):
            dest = os.path.join(backup_dir, f"{base}_{i}{ext}")
            i += 1
    shutil.move(path, dest)
    return dest

# Livelli di intensita' come li scrive il gioco. Stessa mappa di
# genera_real/app.py (LEVEL_CLASS) - un solo vocabolario in tutto il tool.
LIVELLI = {0: 'silenzio', 1: 'leggero', 2: 'pugni', 3: 'misto'}


def playlist_phase_mix(data, trackdata_dir=None):
    """Quanta parte della playlist e' silenzio, leggero, solo pugni, misto.

    Pesata sul TEMPO, non sul numero di segmenti: un segmento di trenta
    secondi e uno di quattro non contano uguale, e il numero di segmenti non
    direbbe niente su come ci si sente a giocarla.

    Il tempo NON coperto da nessun segmento viene contato a parte. Non e' un
    dettaglio da nascondere dentro "silenzio": e' esattamente il difetto da
    cui e' nato questo strumento - nei workout originali di BoxVR ci sono
    buchi di parecchi secondi in cui non succede niente perche' non esiste
    alcun segmento, e in gioco suonano come silenzio pur essendo un'altra
    cosa. Tenerli distinti permette di vedere a colpo d'occhio se una
    playlist ne soffre.

    Ritorna percentuali che sommano a 100 (o un dict vuoto se non si e'
    potuto leggere niente).
    """
    import json
    import os
    from boxvr_install import boxvr_dirs

    trackdata_dir = trackdata_dir or boxvr_dirs()[0]
    tempo = {n: 0.0 for n in LIVELLI.values()}
    tempo['non_coperto'] = 0.0
    totale = 0.0

    for s in (data or {}).get('songs') or []:
        tid = s.get('trackDataName')
        if not tid:
            continue
        percorso = os.path.join(trackdata_dir, tid + '.trackdata.txt')
        try:
            with open(percorso, encoding='utf-8') as f:
                outer = json.load(f)
            inner = json.loads(outer['beatStrucureJSON'])
            segmenti = inner['_segmentList']['_segments']
            durata = float(outer.get('duration') or 0.0)
        except (OSError, ValueError, KeyError):
            continue          # un brano illeggibile non deve azzerare il resto
        coperto = 0.0
        for seg in segmenti:
            lung = float(seg.get('_length') or 0.0)
            if lung <= 0:
                continue
            tempo[LIVELLI.get(seg.get('_energyLevel'), 'silenzio')] += lung
            coperto += lung
        if durata > 0:
            totale += durata
            tempo['non_coperto'] += max(0.0, durata - coperto)
        else:
            totale += coperto

    if totale <= 0:
        return {}
    return {k: round(v / totale * 100, 1) for k, v in tempo.items()}


def track_audio_path(track_id, trackdata_dir=None):
    """Il .wav di un brano dentro la libreria, se c'e'. Serve per farlo
    ascoltare dalla pagina senza copiare l'intera libreria."""
    import os
    from boxvr_install import boxvr_dirs
    trackdata_dir = trackdata_dir or boxvr_dirs()[0]
    p = os.path.join(trackdata_dir, (track_id or '') + '.wav')
    return p if os.path.isfile(p) else None
