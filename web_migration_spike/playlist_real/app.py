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
Primo port reale di Playlist Manager (31/08/2026 notte)
=========================================================
Come `correggi_real`/`genera_real`: collega DAVVERO la pagina a
`boxvr_playlist_manager.py` (il modulo di logica pura gia' esistente e
gia' testato - 49 test - dietro l'exe `BoxVR_Playlist_Manager` gia'
spedito), non dati finti. A differenza degli altri due port, questo
lavora SEMPRE sulla libreria live vera (`boxvr_install.boxvr_dirs()`) -
non ha senso un "brano di test" per la gestione playlist, dato che il suo
intero scopo e' modificare le playlist gia' installate.

Nessuna pagina Figma esiste per questo strumento (mai stato progettato
li' - e' nato direttamente come tool Tkinter separato il 30/08). Pagina
qui deliberatamente MINIMALE/UTILITARIA (lista, riordino, rinomina,
elimina-con-backup), non un design nuovo - la rifinitura visiva resta un
passo separato, da fare quando ha senso farlo, non improvvisata ora.

Sicurezza: le operazioni di SCRITTURA (rinomina/riordino/rimozione brano/
eliminazione) sono le STESSE identiche funzioni gia' spedite nell'exe
Playlist Manager, non riscritte - `delete_playlist` sposta in una
sottocartella di backup invece di cancellare (mai distruttivo),
`rename_playlist` non sovrascrive mai una playlist esistente in
silenzio (solleva FileExistsError). Verificate in questa sessione con
chiamate dirette su un file SINTETICO di prova, non sulle playlist reali
dell'utente - le operazioni di lettura invece sono state verificate
direttamente sulla libreria vera (sola lettura, nessun rischio).
"""
import os
import sys

import json as _json

# I percorsi non sono piu' cablati: li risolve percorsi.py, che funziona sia
# dai sorgenti sia dentro un eseguibile PyInstaller.
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import percorsi
percorsi.prepara_sys_path()

import boxvr_install as install
import boxvr_playlist_manager as pm
import webview
import webview2_check



MOCKUPS_DIR = percorsi.MOCKUPS


def _settings_path():
    """Stesso file delle altre pagine e della GUI Tkinter."""
    base = os.environ.get('APPDATA') or os.path.dirname(__file__)
    return os.path.join(base, 'BoxVR Level Fixer', 'settings.json')


def _load_settings():
    try:
        with open(_settings_path(), encoding='utf-8') as f:
            return _json.load(f)
    except Exception:
        return {}


def _save_setting_value(key, value):
    p = _settings_path()
    data = _load_settings()
    data[key] = value
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            _json.dump(data, f, indent=2)
    except Exception:
        pass


class Api:
    def get_app_info(self):
        """Versione e stato patch per l'intestazione condivisa - sola
        lettura, come nelle altre pagine."""
        try:
            import version
            import boxvr_patch as patch
            game_dir = _load_settings().get('game_dir')
            # VERSION_WEB e non VERSION: l'header mostrava 1.29.2, cioe'
            # la numerazione dei due eseguibili Tkinter storici, mentre
            # questo e' il toolkit web, che dalla 1.0 ha una linea sua.
            return {'version': version.VERSION_WEB,
                    'patch_state': patch.state(game_dir)}
        except Exception:
            return {'version': '?', 'patch_state': 'unknown'}

    def get_theme(self):
        return _load_settings().get('theme', 'light')

    def set_theme(self, theme):
        if theme not in ('light', 'dark'):
            return {'ok': False, 'error': 'Tema non valido.'}
        _save_setting_value('theme', theme)
        return {'ok': True, 'theme': theme}

    def get_lang(self):
        return _load_settings().get('lang', 'it')

    def set_lang(self, code):
        if code not in ('it', 'en'):
            return {'ok': False, 'error': 'Lingua non valida.'}
        _save_setting_value('lang', code)
        return {'ok': True, 'lang': code}

    def list_playlists(self):
        """Sola lettura - elenco reale delle playlist gia' installate."""
        return pm.list_playlists()

    def get_playlist(self, path):
        """Sola lettura - brani di UNA playlist, con nomi/durate reali."""
        data = pm.load_playlist(path)
        if data is None:
            return {'ok': False, 'error': 'File non leggibile o corrotto.'}
        defn = data.get('definition') or {}
        return {
            'ok': True, 'path': path,
            'workout_name': defn.get('workoutName', ''),
            'duration': defn.get('duration', 0.0),
            'songs': pm.songs_with_names(data),
            # composizione delle fasi, pesata sul tempo: serve alla striscia
            # al centro della pagina per dire com'e' fatta la playlist senza
            # doverla aprire brano per brano
            'phase_mix': pm.playlist_phase_mix(data),
        }

    def get_track_audio(self, track_id):
        """Prepara il .wav di UN brano per l'ascolto e ne ritorna il nome da
        usare nella pagina.

        Copiato nella cartella di servizio solo quando serve: la libreria di
        BoxVR puo' contenere decine di wav da qualche decina di MB l'uno, e
        copiarli tutti all'avvio per farne ascoltare uno sarebbe assurdo.
        La libreria non viene mai modificata - qui si legge soltanto.
        """
        import shutil
        sorgente = pm.track_audio_path(track_id)
        if not sorgente:
            return {'ok': False, 'error': 'Audio non trovato per questo brano.'}
        if not _work_dir:
            return {'ok': False, 'error': 'Cartella di servizio non pronta.'}
        nome = track_id + '.wav'
        destinazione = os.path.join(_work_dir, nome)
        if not os.path.isfile(destinazione):
            try:
                shutil.copy2(sorgente, destinazione)
            except OSError as e:
                return {'ok': False, 'error': 'Copia non riuscita: %s' % e}
        return {'ok': True, 'file': nome}

    def move_song(self, path, from_index, to_index):
        """Riordina e salva per davvero - STESSA pm.move_song della GUI/exe
        gia' spedita. Nessun ricalcolo di durata (riordinare non cambia
        quali brani ci sono, per costruzione di move_song)."""
        data = pm.load_playlist(path)
        if data is None:
            return {'ok': False, 'error': 'File non leggibile o corrotto.'}
        try:
            pm.move_song(data, from_index, to_index)
        except IndexError as e:
            return {'ok': False, 'error': str(e)}
        pm.save_playlist(path, data)
        return {'ok': True, 'songs': pm.songs_with_names(data)}

    def remove_song(self, path, index):
        """Rimuove un brano dalla playlist e salva per davvero - la
        rimozione tocca SOLO il file playlist (un indice), mai il brano
        stesso (trackdata/wav/wdef), che resta installato e riusabile
        altrove - stessa garanzia di pm.delete_playlist per il file intero."""
        data = pm.load_playlist(path)
        if data is None:
            return {'ok': False, 'error': 'File non leggibile o corrotto.'}
        try:
            pm.remove_song(data, index)
        except IndexError as e:
            return {'ok': False, 'error': str(e)}
        pm.recompute_duration(data)
        pm.save_playlist(path, data)
        defn = data.get('definition') or {}
        return {'ok': True, 'songs': pm.songs_with_names(data), 'duration': defn.get('duration', 0.0)}

    def rename_playlist(self, path, new_name):
        """Rinomina per davvero - STESSA pm.rename_playlist gia' spedita:
        mai sovrascrive un'altra playlist in silenzio (FileExistsError se
        il nome e' gia' usato)."""
        try:
            new_path = pm.rename_playlist(path, new_name)
        except FileExistsError as e:
            return {'ok': False, 'error': str(e)}
        except (FileNotFoundError, ValueError) as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True, 'path': new_path}

    def delete_playlist(self, path):
        """Elimina per davvero, ma MAI distruttivo - pm.delete_playlist
        sposta in una sottocartella di backup (`_playlist_eliminate_backup`),
        non cancella. I brani installati (trackdata/wav/wdef) non vengono
        mai toccati, solo l'indice della playlist."""
        dest = pm.delete_playlist(path)
        return {'ok': True, 'backup_path': dest}

    def open_backup_folder(self):
        """Apre Esplora risorse sulla cartella di backup delle playlist
        eliminate, se esiste - stesso pattern di open_folder negli altri
        port, mai un percorso arbitrario passato da fuori."""
        _, _, playlists_dir = install.boxvr_dirs()
        backup_dir = os.path.join(playlists_dir, '_playlist_eliminate_backup')
        if os.path.isdir(backup_dir):
            os.startfile(backup_dir)


# Prima di crearne una nuova, si tolgono di mezzo quelle vecchie: senza,
# ogni avvio lasciava indietro una copia completa dei brani (misurati 117 GB
# in 596 cartelle). Non blocca mai l'avvio - vedi pulizia_temp.py.
try:
    from pulizia_temp import pulisci_vecchie_cartelle as _pulisci
    from pulizia_temp import marca as _marca_pid
except Exception:                      # noqa: BLE001
    def _pulisci():
        return (0, 0)

    def _marca_pid(_cartella):
        return None


def build_serving_dir(work_dir=None, page_name='index.html'):
    import shutil
    import tempfile
    if work_dir is None:
        _pulisci()
        work_dir = tempfile.mkdtemp(prefix="boxvr_playlist_real_")
    # il PID di chi la usa: cosi' il prossimo avvio sa se e'
    # abbandonata, invece di aspettare sei ore
    _marca_pid(work_dir)
    shutil.copy2(os.path.join(MOCKUPS_DIR, 'styles.css'), os.path.join(work_dir, 'styles.css'))
    shutil.copy2(os.path.join(os.path.dirname(__file__), 'index.html'), os.path.join(work_dir, page_name))
    return work_dir


def main():
    if not webview2_check.ensure_webview2_or_exit():
        return
    import shutil
    work_dir = build_serving_dir()
    index_path = os.path.join(work_dir, 'index.html')
    webview.create_window("Gestione playlist (dati reali)", index_path, js_api=Api(), width=1100, height=750)
    webview.start()
    shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
