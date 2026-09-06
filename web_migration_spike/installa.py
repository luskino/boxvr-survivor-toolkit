# -*- coding: utf-8 -*-
"""Installazione nella libreria live di BoxVR, per il port web.

La logica vera sta gia' in `boxvr_install.py` (la stessa usata dalla GUI
Tkinter): qui c'e' solo il collante per esporla alle pagine, in due passi
separati - **anteprima** e **conferma** - perche' una pagina HTML non puo'
usare i dialoghi modali di Tkinter:

    anteprima_installazione(...)  -> cosa verrebbe scritto, dove, e cosa
                                     andrebbe sovrascritto
    esegui_installazione(...)     -> scrive davvero, saltando i brani che
                                     l'utente ha deciso di non sovrascrivere

Nessuna scrittura avviene senza una chiamata esplicita alla seconda.
"""
import os
import subprocess
import sys

import boxvr_install


def gioco_in_esecuzione():
    """True se BoxVR.exe e' aperto adesso.

    Confronta il nome immagine ESATTO, non una sottostringa: cercare "boxvr"
    dentro l'output di tasklist faceva rilevare come "gioco aperto" lo
    strumento stesso (si chiama BoxVR_Level_Fixer_...exe) - bug reale della
    GUI Tkinter, corretto li' e ripreso qui uguale.
    """
    if sys.platform != 'win32':
        return False
    try:
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'],
                             capture_output=True, text=True, timeout=5,
                             creationflags=flags)
        for riga in out.stdout.splitlines():
            parti = [p.strip('"') for p in riga.split('","')]
            if parti and parti[0].strip().lower() == 'boxvr.exe':
                return True
    except Exception:
        return False
    return False


def anteprima_installazione(output_folder, track_ids, playlist_paths=()):
    """Cosa verrebbe installato, senza scrivere nulla.

    Ritorna anche i CONFLITTI (brani gia' presenti nella libreria), cosi' la
    pagina puo' far scegliere quali sovrascrivere - stessa logica del dialogo
    della GUI Tkinter, che ragiona per BRANO e non per singolo file.
    """
    track_ids = list(track_ids or [])
    playlist_files = [os.path.basename(p) for p in (playlist_paths or [])]
    data_files, wdef_files = boxvr_install.files_for_track_ids(output_folder, track_ids)
    trackdata_dir, trackdefs_dir, playlists_dir = boxvr_install.boxvr_dirs()
    conflitti = [
        {'tid': tid, 'nome': boxvr_install.track_display_name(output_folder, tid)}
        for tid in boxvr_install.find_conflicts(track_ids, trackdata_dir, trackdefs_dir)
    ]
    return {
        'ok': bool(data_files or wdef_files),
        'n_brani': len(track_ids),
        'n_data': len(data_files),
        'n_wdef': len(wdef_files),
        # Le playlist sono PIU' D'UNA quando c'e' un limite di durata: e'
        # esattamente il caso in cui il difetto si notava, perche' il gioco
        # non ne mostrava nessuna.
        'n_playlist': len(playlist_files),
        'playlist': playlist_files,
        'trackdata_dir': trackdata_dir,
        'trackdefs_dir': trackdefs_dir,
        'playlists_dir': playlists_dir,
        'conflitti': conflitti,
        'gioco_aperto': gioco_in_esecuzione(),
        'brani': [{'tid': t, 'nome': boxvr_install.track_display_name(output_folder, t)}
                  for t in track_ids],
    }


def esegui_installazione(output_folder, track_ids, salta=(), fai_backup=True,
                         playlist_paths=()):
    """Copia davvero nella libreria del gioco. `salta` = track id da NON
    installare (i conflitti che l'utente non vuole sovrascrivere).

    Con `fai_backup` (predefinito) le versioni gia' presenti dei brani che
    verranno sovrascritti finiscono in `TrackData/_Backup Toolkit/<data-ora>/`
    PRIMA della copia. E' l'interruttore "Crea backup nella cartella
    Trackdata" dell'interfaccia, che fino al 03/09 era solo grafica.
    """
    salta = set(salta or ())
    track_ids = [t for t in (track_ids or []) if t not in salta]
    if not track_ids:
        return {'ok': False, 'error': 'Nessun brano da installare.'}

    data_files, wdef_files = boxvr_install.files_for_track_ids(output_folder, track_ids)
    if not data_files and not wdef_files:
        return {'ok': False, 'error': 'Nessun file trovato per i brani scelti.'}

    trackdata_dir, trackdefs_dir, playlists_dir = boxvr_install.boxvr_dirs()
    try:
        n, cartella_backup = boxvr_install.install_files_con_backup(
            output_folder, data_files, wdef_files,
            trackdata_dir, trackdefs_dir, fai_backup=fai_backup)
        # E le playlist, che prima restavano nella cartella di output mentre
        # il gioco non ne vedeva nessuna. Vanno DOPO i brani: una playlist
        # che nomina un brano non ancora copiato e' una playlist rotta, e per
        # un istante lo sarebbe stata sul disco del giocatore.
        n_pl, backup_pl = boxvr_install.install_playlists(
            output_folder, [os.path.basename(p) for p in (playlist_paths or [])],
            playlists_dir, fai_backup=fai_backup)
    except OSError as e:
        return {'ok': False, 'error': str(e)}
    return {
        'ok': True, 'n_file': n, 'n_brani': len(track_ids),
        'n_playlist': n_pl,
        'trackdata_dir': trackdata_dir, 'trackdefs_dir': trackdefs_dir,
        'playlists_dir': playlists_dir,
        'backup_dir': cartella_backup or backup_pl,
    }


def cartella_gioco():
    """(TrackData, TrackDefinitions, WorkoutPlaylists) della libreria live."""
    return boxvr_install.boxvr_dirs()


def apri_cartella_gioco():
    """Apre la cartella della libreria nell'esplora file."""
    trackdata_dir, _, _ = boxvr_install.boxvr_dirs()
    if not os.path.isdir(trackdata_dir):
        return {'ok': False, 'error': 'Cartella della libreria non trovata: %s' % trackdata_dir}
    os.startfile(trackdata_dir)
    return {'ok': True, 'path': trackdata_dir}
