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
Installazione nella libreria live di BoxVR
==========================================
Tutto cio' che riguarda lo SCRIVERE dentro la cartella reale del gioco:
dove si trova, cosa c'e' gia', e come copiarci i file appena generati senza
lasciare tracce a meta' se qualcosa va storto.

PERCHE' UN MODULO A SE'
-----------------------
Questa logica viveva dentro SongBrowserPanel (boxvr_fixer_gui.py), mescolata
ai dialoghi di conferma. Due problemi concreti:

1. Non era verificabile senza aprire una finestra - e stiamo parlando del
   codice che tocca i DATI REALI del gioco dell'utente, cioe' esattamente
   quello che piu' merita di essere testato.
2. I percorsi della libreria erano duplicati per la TERZA volta nel progetto
   (boxvr_choreo.boxvr_dirs, _boxvr_track_dirs, _boxvr_playlists_dir).

Qui la parte di logica non sa nulla di interfaccia: decide, non chiede. Le
conferme all'utente restano nella GUI, che orchestra chiamando queste
funzioni - cosi' le stesse regole valgono identiche da GUI, da script o da
un'eventuale interfaccia diversa in futuro.
"""
import json
import os
import shutil

TRACKDATA_SUFFIX = '.trackdata.txt'
WDEF_SUFFIX = '.wdef.txt'
WAV_SUFFIX = '.wav'


def boxvr_dirs():
    """(TrackData, TrackDefinitions, WorkoutPlaylists/BoxVR) della libreria live.

    UNICA fonte di verita' per questi percorsi in tutto il progetto. Non e'
    un percorso "di questo PC": e' la convenzione fissa di Unity per i dati
    utente, quindi si espande correttamente su qualunque account Windows.
    "BoxVR" e' il sottonome usato dal gioco stesso, verificato su
    un'installazione reale.
    """
    base = os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow\FITXR\BoxVR\Playlists")
    return (os.path.join(base, 'TrackData'),
            os.path.join(base, 'TrackDefinitions'),
            os.path.join(base, 'WorkoutPlaylists', 'BoxVR'))


def scan_generated(folder):
    """Cosa c'e' da installare in una cartella di output.

    Ritorna (data_files, wdef_files, track_ids): i primi due sono nomi di
    file (non percorsi), track_ids l'insieme ordinato degli id coinvolti.
    Cartella inesistente o vuota -> tre risultati vuoti, non un errore: e'
    una condizione normale, non un guasto.
    """
    if not folder or not os.path.isdir(folder):
        return [], [], []
    names = os.listdir(folder)
    data_files = [f for f in names if f.endswith(TRACKDATA_SUFFIX) or f.endswith(WAV_SUFFIX)]
    wdef_files = [f for f in names if f.endswith(WDEF_SUFFIX)]
    track_ids = sorted({f[:-len(TRACKDATA_SUFFIX)] for f in data_files if f.endswith(TRACKDATA_SUFFIX)}
                       | {f[:-len(WDEF_SUFFIX)] for f in wdef_files})
    return data_files, wdef_files, track_ids


def files_for_track_ids(folder, track_ids):
    """Come scan_generated, ma ristretto agli `track_ids` passati esplicitamente
    invece di elencare l'intera cartella.

    Bug reale segnalato dall'utente il 25/08: `output_folder` per la
    generazione e' una cartella FISSA ("generati" dentro la cartella di
    partenza), riusata identica a ogni sessione - non viene mai ripulita ne'
    versionata. `scan_generated`, con un semplice `os.listdir`, vedeva quindi
    OGNI file mai generato li' dentro nel tempo, non solo quelli della sessione
    appena finita: "Installa su BoxVR" installava anche brani di giorni prima,
    magari costruiti con una versione precedente del generatore (senza il
    `.actionlist.json` introdotto oggi, per esempio) - mischiati a quelli
    freschi in una playlist unica.

    Qui si costruiscono i nomi file direttamente dagli id passati (il
    formato e' deterministico: `<id>.trackdata.txt` ecc.) invece di scoprirli
    ascoltando la cartella - non importa cos'altro c'e' li' dentro."""
    if not folder or not track_ids:
        return [], []
    data_files, wdef_files = [], []
    for tid in track_ids:
        for suf in (TRACKDATA_SUFFIX, WAV_SUFFIX):
            fn = f"{tid}{suf}"
            if os.path.isfile(os.path.join(folder, fn)):
                data_files.append(fn)
        fn = f"{tid}{WDEF_SUFFIX}"
        if os.path.isfile(os.path.join(folder, fn)):
            wdef_files.append(fn)
    return data_files, wdef_files


def action_lists_from_playlist(playlist_path):
    """Legge una .workoutplaylist.txt gia' scritta e ritorna
    {trackDataName: serialisedActionList}.

    Serve a installare i brani GENERATI riusando la coreografia gia' vera che
    `generate_songs` ha scritto a fine sessione (`write_playlist`, con le
    azioni reali gia' dentro), invece di ricostruirla da capo tramite
    `_action_list_for` cercando `.actionlist.json` accanto ai file - due
    percorsi diversi che calcolano la stessa cosa sono un modo comodo per
    farli divergere in silenzio. Questo e' il percorso primario quando si
    conosce il playlist_path della sessione appena fatta; `_action_list_for`
    resta il ripiego per i casi in cui non lo si conosce (installazione da
    una cartella preparata a mano, sessioni precedenti a questo meccanismo)."""
    if not playlist_path or not os.path.isfile(playlist_path):
        return {}
    try:
        with open(playlist_path, encoding='utf-8-sig') as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    out = {}
    for s in d.get('songs', []):
        tid = s.get('trackDataName')
        al = s.get('serialisedActionList')
        if isinstance(al, str):
            try:
                al = json.loads(al)
            except json.JSONDecodeError:
                al = None
        if tid and isinstance(al, dict) and al.get('actionList'):
            out[tid] = al
    return out


def track_id_of(fname, suffixes):
    for suf in suffixes:
        if fname.endswith(suf):
            return fname[:-len(suf)]
    return fname


def find_conflicts(track_ids, trackdata_dir=None, trackdefs_dir=None):
    """Quali degli id passati esistono GIA' nella libreria live.

    Basta un solo file presente (trackdata, wav o wdef) perche' l'id conti
    come conflitto: installare sopra rimpiazzerebbe comunque qualcosa.
    """
    if trackdata_dir is None or trackdefs_dir is None:
        td, tdef, _ = boxvr_dirs()
        trackdata_dir = trackdata_dir or td
        trackdefs_dir = trackdefs_dir or tdef
    out = []
    for tid in track_ids:
        if (os.path.isfile(os.path.join(trackdata_dir, tid + TRACKDATA_SUFFIX))
                or os.path.isfile(os.path.join(trackdata_dir, tid + WAV_SUFFIX))
                or os.path.isfile(os.path.join(trackdefs_dir, tid + WDEF_SUFFIX))):
            out.append(tid)
    return out


def track_display_name(folder, tid):
    """Nome leggibile di un brano, letto dal trackdata APPENA GENERATO in
    `folder` - non da quello eventualmente gia' installato, che potrebbe
    essere un file vecchio o rinominato senza piu' un nome comprensibile.
    Ripiega sull'id se il file non e' leggibile: serve a far riconoscere un
    brano all'utente, non vale un errore."""
    try:
        with open(os.path.join(folder, tid + TRACKDATA_SUFFIX), encoding='utf-8') as f:
            outer = json.load(f)
        return f"{outer.get('originalTrackName', tid)} — {outer.get('originalArtist', '?')}"
    except Exception:
        return tid


def track_duration(folder, tid):
    """Durata (secondi) di un brano, letta dal suo trackdata.txt in `folder`.
    0.0 se il file manca o non e' leggibile - una durata sbagliata nella
    somma di una playlist e' un fastidio, non vale interrompere l'utente."""
    try:
        with open(os.path.join(folder, tid + TRACKDATA_SUFFIX), encoding='utf-8') as f:
            return float(json.load(f).get('duration', 0.0))
    except Exception:
        return 0.0


def _action_list_for(folder, track_id):
    """La coreografia scritta da boxvr_generator accanto al brano, se c'e'.

    Bug reale corretto il 25/08: qui si scriveva SEMPRE `{'actionList': []}`.
    Va bene per i brani CORRETTI (il gioco non patchato se la genera da solo),
    ma per i brani GENERATI a patch attiva significa brani muti - la
    generazione procedurale del gioco e' disattivata, quindi una lista vuota
    resta vuota. Peggio: la schermata delle playlist va in
    NullReferenceException e non ne mostra NESSUNA, nemmeno quelle sane
    (osservato sul PC dell'utente, playlist "Media", 25/08).

    `generate_track` salva ora `<hash>.actionlist.json` accanto ai file del
    brano: se e' presente si usa quella, altrimenti si torna alla lista vuota,
    che resta il comportamento giusto per i brani corretti."""
    p = os.path.join(folder or '', f"{track_id}.actionlist.json")
    if os.path.isfile(p):
        try:
            with open(p, encoding='utf-8') as f:
                al = json.load(f)
            if isinstance(al, dict) and al.get('actionList'):
                return al
        except (OSError, json.JSONDecodeError):
            pass   # meglio una playlist muta che un'installazione fallita
    return {'actionList': []}


def playlists_without_choreography(playlists_dir=None):
    """Playlist installate che hanno brani con coreografia vuota.

    A patch attiva sono ingiocabili (mute) e possono impedire al gioco di
    mostrare l'intera lista delle playlist. Serve a segnalarlo all'utente
    invece di lasciarglielo scoprire col visore in testa."""
    playlists_dir = playlists_dir or boxvr_dirs()[2]
    fuori = []
    if not os.path.isdir(playlists_dir):
        return fuori
    for fn in os.listdir(playlists_dir):
        if not fn.endswith('.workoutplaylist.txt'):
            continue
        try:
            with open(os.path.join(playlists_dir, fn), encoding='utf-8-sig') as f:
                d = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        vuote = 0
        for s in d.get('songs', []):
            al = s.get('serialisedActionList')
            if isinstance(al, str):
                try:
                    al = json.loads(al)
                except json.JSONDecodeError:
                    al = None
            if not (isinstance(al, dict) and al.get('actionList')):
                vuote += 1
        if vuote:
            fuori.append((fn, vuote, len(d.get('songs', []))))
    return fuori


def add_to_playlist(playlist_path, track_ids, name, new_folder, trackdata_dir=None,
                    action_lists=None):
    """Aggiunge `track_ids` a una playlist .workoutplaylist.txt esistente (o ne
    crea una nuova se non c'e'), senza toccare le voci gia' presenti, e la
    riscrive su disco. Ritorna il dict playlist scritto.

    Usata quando si installano brani dalla cartella di output. Ogni nuova voce
    prende la coreografia, in ordine di preferenza:
      1. `action_lists[tid]`, se il chiamante la passa - la coreografia GIA'
         VERA scritta da `generate_songs` a fine sessione (vedi
         `action_lists_from_playlist`), da preferire perche' e' la stessa
         identica cosa che il brano ha davvero, non una ricostruzione;
      2. `<hash>.actionlist.json` accanto al brano, se esiste (ripiego per
         quando non si conosce il playlist_path della sessione);
      3. altrimenti resta con actionList vuota, come le playlist native del
         gioco (brani CORRETTI, dove la coreografia la fa il gioco stesso) -
         vedi `_action_list_for` per il perche' la distinzione conta.

    `new_folder` e' dove stanno i trackdata dei brani NUOVI (la cartella di
    output appena generata); `trackdata_dir` (default: la libreria live) e'
    dove stanno quelli GIA' in playlist, per ricalcolare la durata totale -
    sono cartelle diverse perche' un brano preesistente non e' piu' nella
    cartella di output di questa sessione.

    Schema scoperto ispezionando i file .workoutplaylist.txt reali di BoxVR:
    {"definition": {..., "duration": <somma secondi>},
     "songs": [{"trackDataName": "<hash>", "serialisedActionList": {"actionList": []}}, ...]}.
    """
    if trackdata_dir is None:
        trackdata_dir = boxvr_dirs()[0]

    songs = []
    if os.path.isfile(playlist_path):
        try:
            with open(playlist_path, encoding='utf-8') as f:
                songs = json.load(f).get('songs', [])
        except Exception:
            songs = []
    existing_ids = {s.get('trackDataName') for s in songs}

    total_duration = sum(track_duration(new_folder, tid) for tid in track_ids)
    for s in songs:
        tid = s.get('trackDataName')
        if tid not in track_ids:  # gia' contato sopra se e' uno dei nuovi
            total_duration += track_duration(trackdata_dir, tid)

    for tid in track_ids:
        if tid not in existing_ids:
            al = (action_lists or {}).get(tid) or _action_list_for(new_folder, tid)
            songs.append({'trackDataName': tid, 'serialisedActionList': al})
            existing_ids.add(tid)

    playlist = {
        'definition': {
            'workoutName': name, 'game': 0, 'workoutStyle': 0, 'authorName': 'author',
            'trackGenre': 0, 'leaderboardId': 'undefined', 'sonyLeaderboardId': -1,
            'workoutId': '', 'hasSquats': False, 'hasJumps': False, 'workoutType': 1,
            'duration': total_duration,
        },
        'songs': songs,
    }
    os.makedirs(os.path.dirname(playlist_path), exist_ok=True)
    with open(playlist_path, 'w', encoding='utf-8') as f:
        json.dump(playlist, f)
    return playlist


BACKUP_DIRNAME = '_Backup Toolkit'
ISTRUZIONI_RIPRISTINO = """Backup creato da BoxVR Survivor Toolkit prima di sovrascrivere.

Ogni file qui dentro e' la versione ORIGINALE di un brano della tua libreria,
salvata subito prima che il tool la sostituisse.

COME RIPRISTINARE UN BRANO
1. prendi il file che ti interessa, per esempio
      abc123.trackdata.txt.bak
2. copialo nella cartella TrackData (due livelli piu' su);
3. togli il ".bak" finale dal nome.

Il ".bak" c'e' apposta: senza, questi file avrebbero lo stesso nome di
tracce vere, e non vogliamo che il gioco possa leggerli per sbaglio se un
giorno guardasse anche dentro le sottocartelle.
"""


def backup_esistenti(nomi_file, cartelle, quando=None):
    """Copia da parte i file che stanno per essere sovrascritti.

    Salva SOLO quelli che esistono davvero: un brano nuovo non ha niente da
    salvare, e una cartella di backup vuota confonderebbe e basta.

    Ritorna (cartella_di_backup, n_file). La cartella e' None se non c'era
    niente da salvare.
    """
    import datetime
    esistenti = []
    for cartella in cartelle:
        if not cartella or not os.path.isdir(cartella):
            continue
        for nome in nomi_file:
            p = os.path.join(cartella, nome)
            if os.path.isfile(p):
                esistenti.append((cartella, p))
    if not esistenti:
        return None, 0

    quando = quando or datetime.datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    radice = os.path.join(esistenti[0][0], BACKUP_DIRNAME)
    dest = os.path.join(radice, quando)
    os.makedirs(dest, exist_ok=True)
    lettimi = os.path.join(radice, 'COME RIPRISTINARE.txt')
    if not os.path.isfile(lettimi):
        with open(lettimi, 'w', encoding='utf-8') as f:
            f.write(ISTRUZIONI_RIPRISTINO)

    n = 0
    for _, p in esistenti:
        shutil.copy2(p, os.path.join(dest, os.path.basename(p) + '.bak'))
        n += 1
    return dest, n


def install_files_con_backup(folder, data_files, wdef_files, trackdata_dir=None,
                             trackdefs_dir=None, fai_backup=True):
    """`install_files` preceduta dal backup delle versioni gia' presenti.

    Ritorna (n_copiati, cartella_di_backup). Funzione separata apposta:
    `install_files` ha chiamanti che si aspettano un intero, e non si cambia
    il contratto di una funzione gia' in uso per aggiungerci sopra qualcosa.
    """
    if trackdata_dir is None or trackdefs_dir is None:
        td, tdef, _ = boxvr_dirs()
        trackdata_dir = trackdata_dir or td
        trackdefs_dir = trackdefs_dir or tdef

    cartella_backup = None
    if fai_backup:
        cartella_backup, _ = backup_esistenti(list(data_files), [trackdata_dir])
        quando = os.path.basename(cartella_backup) if cartella_backup else None
        b2, _ = backup_esistenti(list(wdef_files), [trackdefs_dir], quando=quando)
        cartella_backup = cartella_backup or b2

    n = install_files(folder, data_files, wdef_files, trackdata_dir, trackdefs_dir)
    return n, cartella_backup


def install_playlists(folder, playlist_files, playlists_dir=None,
                      fai_backup=True):
    """Copia i `.workoutplaylist.txt` nella libreria live. Ritorna
    (n_copiati, cartella_di_backup).

    Esiste perche' non c'era: `install_files` copiava trackdata/wav/wdef e la
    playlist restava nella cartella di output, con il log che diceva
    all'utente di spostarla a mano. Era vero prima che «Installa in BoxVR»
    automatizzasse il resto, ed e' rimasto li'. Risultato misurato il
    06/09: TrackData e TrackDefinitions aggiornati, WorkoutPlaylists ferma a
    una settimana prima - i brani in gioco c'erano, le playlist no.

    I nomi arrivano da chi ha appena generato, non da un listdir: la cartella
    di output non viene mai ripulita, e un listdir porterebbe in gioco anche
    le playlist di giorni fa (stesso motivo di `files_for_track_ids`).
    """
    playlist_files = [f for f in (playlist_files or [])]
    if not playlist_files:
        return 0, None
    if playlists_dir is None:
        _td, _tdef, playlists_dir = boxvr_dirs()
    os.makedirs(playlists_dir, exist_ok=True)

    cartella_backup = None
    if fai_backup:
        cartella_backup, _ = backup_esistenti(playlist_files, [playlists_dir])

    n = 0
    for fname in playlist_files:
        src = os.path.join(folder, fname)
        if not os.path.isfile(src):
            continue
        shutil.copy2(src, os.path.join(playlists_dir, fname))
        n += 1
    return n, cartella_backup


def install_files(folder, data_files, wdef_files, trackdata_dir=None, trackdefs_dir=None):
    """Copia i file nella libreria live. Ritorna il numero di file copiati.

    Se una copia fallisce a meta', i file DAVVERO NUOVI appena scritti
    vengono rimossi prima di rilanciare l'errore: senza, una traccia nuova
    poteva restare monca (es. il wav senza il suo trackdata) dentro la
    libreria del gioco. I file SOVRASCRITTI non si toccano - quella
    sovrascrittura era gia' stata approvata dall'utente e non ne abbiamo un
    backup da ripristinare, quindi rimuoverli farebbe piu' danno che bene.
    """
    if trackdata_dir is None or trackdefs_dir is None:
        td, tdef, _ = boxvr_dirs()
        trackdata_dir = trackdata_dir or td
        trackdefs_dir = trackdefs_dir or tdef

    os.makedirs(trackdata_dir, exist_ok=True)
    os.makedirs(trackdefs_dir, exist_ok=True)

    newly_created = []
    n_copied = 0
    try:
        for fname, dest_dir in ([(f, trackdata_dir) for f in data_files]
                                 + [(f, trackdefs_dir) for f in wdef_files]):
            dest = os.path.join(dest_dir, fname)
            was_new = not os.path.isfile(dest)
            shutil.copy2(os.path.join(folder, fname), dest)
            if was_new:
                newly_created.append(dest)
            n_copied += 1
    except OSError:
        for path in newly_created:
            try:
                os.remove(path)
            except OSError:
                pass
        raise
    return n_copied
