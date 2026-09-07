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
Port reale del Dashboard/rilevamento patch (31/08/2026 notte)
=============================================================
Come `correggi_real/`, collega DAVVERO `dashboard.html` a `boxvr_patch.py`
(la stessa GUI vera usa - `boxvr_patch.state`/`apply`/`revert`, non una
riscrittura) invece del checkbox "Simula patch installata" del mockup.
Legge/scrive lo STESSO `settings.json` della GUI vera
(`%APPDATA%/BoxVR Level Fixer/settings.json`, chiave `game_dir`) - non un
file separato per questo spike, cosi' scegliere la cartella qui o nella
GUI vera resta coerente.

Deliberatamente NON fa: la scansione automatica di tutto il disco
(`boxvr_patch.find_all_installs`/`find_the_patched_install`) - quelle
funzioni sono esplicitamente segnalate come lente nel loro stesso
docstring ("va usato come controllo esplicito... non in un ciclo caldo o
all'avvio dell'app"). Qui si usa `state(game_dir)` (economico, una sola
cartella) con un `game_dir` scelto a mano, esattamente come fa
`_ask_game_dir` nella GUI vera - non un'invenzione.

Nota di cautela: `apply`/`revert` scrivono davvero nel DLL del gioco
installato sulla macchina (con backup automatico, la stessa logica gia'
spedita nel tool oggi) - un'azione diversa da tutto il resto degli spike
"_real" finora, che scrivevano solo dentro il progetto. Wired ma MAI
eseguito automaticamente in fase di verifica di questo modulo - solo
`get_status()` (sola lettura) e' stato chiamato per test.

Aggiornamento (stessa notte): "Vai al tool" per Correggi ora naviga
DAVVERO verso la pagina di `correggi_real` nella STESSA finestra/sessione
pywebview, invece del mockup statico - prima vera navigazione a router
singolo di questa migrazione (Genera resta il mockup, perche' non esiste
ancora un port reale di quella pagina). Fatto riusando `correggi_real.app`
per import (stesso `Api`, nessuna riscrittura) invece di duplicarne la
logica - vedi `Api.__init__`/`build_serving_dir` sotto.
"""
import importlib.util
import json
import os
import sys

# I percorsi non sono piu' cablati: li risolve percorsi.py, che funziona sia
# dai sorgenti sia dentro un eseguibile PyInstaller.
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import percorsi
percorsi.prepara_sys_path()

import boxvr_patch as patch
import version
import webview
import webview2_check



MOCKUPS_DIR = percorsi.MOCKUPS
CORREGGI_REAL_DIR = percorsi.CORREGGI_DIR
GENERA_REAL_DIR = percorsi.GENERA_DIR
PLAYLIST_REAL_DIR = percorsi.PLAYLIST_DIR


def _load_app_module(name, directory):
    """Import di un app.py "gemello" via importlib invece di sys.path+import
    semplice: correggi_real/genera_real/dashboard_real hanno TUTTI un file
    chiamato "app.py" - un `import app` normale sarebbe ambiguo su quale
    trovare per primo."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(directory, "app.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


correggi_app = _load_app_module("correggi_real_app", CORREGGI_REAL_DIR)
genera_app = _load_app_module("genera_real_app", GENERA_REAL_DIR)
playlist_app = _load_app_module("playlist_real_app", PLAYLIST_REAL_DIR)


def _settings_path():
    """Stesso percorso di boxvr_fixer_gui._settings_path() - non duplicato
    per valore, ricalcolato identico apposta per non dover importare
    l'intero modulo Tkinter solo per due funzioni di I/O su un json."""
    base = os.environ.get('APPDATA') or os.path.dirname(__file__)
    d = os.path.join(base, 'BoxVR Level Fixer')
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return os.path.join(d, 'settings.json')


def _load_game_dir():
    """Cartella di gioco: prima quella scelta dall'utente, poi il
    rilevamento automatico.

    Prima leggeva SOLO settings.json. Su una macchina appena installata
    quella chiave non esiste, quindi la barra diceva "Nessuna cartella di
    gioco impostata" anche con BoxVR installato nel percorso Steam piu'
    standard che ci sia - e' esattamente quello che ha visto il test su
    macchina pulita. patch.autodetect_game_dir() esisteva gia' ed era
    perfettamente in grado di trovarlo: semplicemente non la chiamava
    nessuno.

    Il risultato del rilevamento viene salvato, cosi' la ricerca si fa una
    volta sola e da li' in poi l'utente puo' comunque cambiarlo a mano.
    """
    try:
        with open(_settings_path(), encoding='utf-8') as f:
            salvato = json.load(f).get('game_dir')
    except Exception:
        salvato = None
    if salvato and patch.looks_like_game_dir(salvato):
        return salvato
    try:
        trovato = patch.autodetect_game_dir()
    except Exception:
        trovato = None
    if trovato:
        try:
            _save_game_dir(trovato)
        except Exception:
            pass          # non poter salvare non deve impedire di usarlo
        return trovato
    return salvato        # puo' essere un percorso non piu' valido: lo si
                          # mostra comunque, e' un'informazione utile


def _cartella_di_partenza():
    """Da dove far partire il selettore di cartella. Stringa vuota = lascia
    decidere a Windows (nessun percorso sensato trovato)."""
    noto = None
    try:
        with open(_settings_path(), encoding='utf-8') as f:
            noto = json.load(f).get('game_dir')
    except Exception:
        pass
    if noto and os.path.isdir(noto):
        return noto
    try:
        auto = patch.autodetect_game_dir()
    except Exception:
        auto = None
    if auto and os.path.isdir(auto):
        return auto
    # nessuna installazione trovata: almeno portarlo dentro le librerie Steam
    for base in (os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
                 os.environ.get('ProgramFiles', r'C:\Program Files')):
        comune = os.path.join(base, 'Steam', 'steamapps', 'common')
        if os.path.isdir(comune):
            return comune
    return ''


def _load_settings():
    try:
        with open(_settings_path(), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_setting_value(key, value):
    """Scrittura generica su settings.json - vedi genera_real/app.py per
    la stessa funzione, riusata identica per 'theme'."""
    p = _settings_path()
    data = _load_settings()
    data[key] = value
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def _save_game_dir(path):
    p = _settings_path()
    data = {}
    if os.path.isfile(p):
        try:
            with open(p, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {}
    data['game_dir'] = path
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f)


class Api:
    """Un solo oggetto js_api espone sia i metodi del Dashboard (sotto) sia
    quelli di Correggi (delegati a `correggi_app.Api`, riusata cosi' com'e' -
    nessuna riscrittura) - necessario perche' pywebview lega UN js_api per
    finestra: per navigare da dashboard a Correggi nella STESSA finestra
    serve che entrambe le pagine trovino i propri metodi sullo stesso
    `window.pywebview.api`."""

    def __init__(self):
        self._correggi = correggi_app.Api()
        self._genera = genera_app.Api()
        self._playlist = playlist_app.Api()

    # -- delegati a correggi_real, nomi INVARIATI (ha reclamato per prima lo
    # spazio dei nomi piatto - vedi genera_* sotto per il motivo del prefisso) --
    def list_songs(self):
        return self._correggi.list_songs()

    def get_song_detail(self, tid):
        return self._correggi.get_song_detail(tid)

    def recompute(self, tid, margin_pct, punch_ratio_pct):
        return self._correggi.recompute(tid, margin_pct, punch_ratio_pct)

    def copy_to_all(self, margin_pct, punch_ratio_pct):
        return self._correggi.copy_to_all(margin_pct, punch_ratio_pct)

    def run_correction(self, tid, margin_pct, punch_ratio_pct):
        return self._correggi.run_correction(tid, margin_pct, punch_ratio_pct)

    def open_folder(self, path):
        return self._correggi.open_folder(path)

    def clear_list(self):
        return self._correggi.clear_list()

    def add_files(self):
        return self._correggi.add_files()

    def load_live_library(self):
        return self._correggi.load_live_library()

    def remove_song(self, tid):
        return self._correggi.remove_song(tid)

    def get_app_info(self):
        return self._correggi.get_app_info()

    # -- delegati a genera_real, TUTTI col prefisso "genera_" - genera_real.Api
    # e correggi_real.Api condividono diversi nomi di metodo (list_songs,
    # recompute, ...) con backend diversi: su UN solo js_api per finestra
    # andrebbero in collisione. Prefissati tutti uniformemente (anche quelli
    # senza un vero omonimo oggi, es. run_generation) cosi' la regola resta
    # semplice e prevedibile invece di "prefissa solo quelli che collidono
    # oggi" - genera_real/index.html (il suo proxy api()) si aspetta
    # esattamente questa convenzione.
    def genera_list_songs(self):
        return self._genera.list_songs()

    def genera_get_song_detail(self, key):
        return self._genera.get_song_detail(key)

    def genera_recompute(self, key, ratio_pct):
        return self._genera.recompute(key, ratio_pct)

    def genera_clear_list(self):
        return self._genera.clear_list()

    def genera_add_files(self):
        return self._genera.add_files()

    def genera_remove_song(self, key):
        return self._genera.remove_song(key)

    def genera_run_generation(self, name, max_minutes=None):
        return self._genera.run_generation(name, max_minutes)

    # Queste cinque mancavano, e la conseguenza non era un errore visibile ma
    # due funzioni MORTE quando ci si arriva dalla Dashboard - cioe' sempre,
    # nell'app vera. Il proxy della pagina cerca prima "genera_<nome>" e poi
    # "<nome>" senza prefisso: non trovando ne' l'uno ne' l'altro, la
    # promessa veniva rifiutata e la modale restava li' vuota.
    #   list_generated_tracks / get_action_list  -> "Anteprima workout"
    #   install_preview / install_run            -> "Installa in BoxVR"
    #   open_game_folder                         -> apertura della libreria
    # Segnalato dall'utente il 03/09 come "l'anteprima del workout non sta
    # andando"; l'installazione era rotta allo stesso modo, e nessuno se
    # n'era ancora accorto.
    # Correggi e' delegata SENZA prefisso, quindi bastano i nomi nudi. Anche
    # qui mancavano, e "Installa in BoxVR" era morta esattamente come su
    # Genera: trovate dal controllo delle deleghe aggiunto lo stesso giorno.
    def install_preview(self):
        return self._correggi.install_preview()

    def install_run(self, salta=None, fai_backup=True):
        return self._correggi.install_run(salta, fai_backup)

    def open_game_folder(self):
        return self._correggi.open_game_folder()

    def genera_list_generated_tracks(self):
        return self._genera.list_generated_tracks()

    def genera_get_action_list(self, track_id):
        return self._genera.get_action_list(track_id)

    def genera_install_preview(self):
        return self._genera.install_preview()

    def genera_install_run(self, salta=None, fai_backup=True):
        return self._genera.install_run(salta, fai_backup)

    def genera_open_game_folder(self):
        return self._genera.open_game_folder()

    def genera_apply_ratio_to_all(self, key):
        return self._genera.apply_ratio_to_all(key)

    def genera_open_folder(self, path):
        return self._genera.open_folder(path)

    def genera_set_forced_bpm(self, key, bpm):
        return self._genera.set_forced_bpm(key, bpm)

    def genera_clear_forced_bpm(self, key):
        return self._genera.clear_forced_bpm(key)

    def genera_get_app_info(self):
        return self._genera.get_app_info()

    def genera_set_engine(self, key, engine):
        return self._genera.set_engine(key, engine)

    def genera_get_sidecar_state(self, key):
        return self._genera.get_sidecar_state(key)

    def genera_sidecar_start_record(self, key, position_s):
        return self._genera.sidecar_start_record(key, position_s)

    def genera_sidecar_stop_record(self, key):
        return self._genera.sidecar_stop_record(key)

    def genera_sidecar_mark(self, key, raw_position_s):
        return self._genera.sidecar_mark(key, raw_position_s)

    def genera_sidecar_clear(self, key):
        return self._genera.sidecar_clear(key)

    def genera_sidecar_reset(self, key):
        return self._genera.sidecar_reset(key)

    def genera_sidecar_set_mode(self, key, mode):
        return self._genera.sidecar_set_mode(key, mode)

    def genera_sidecar_set_exclude_obstacles(self, key, value):
        return self._genera.sidecar_set_exclude_obstacles(key, value)

    def genera_sidecar_set_min_gap_ms(self, key, ms):
        return self._genera.sidecar_set_min_gap_ms(key, ms)

    def genera_open_bpm_search(self, key):
        return self._genera.open_bpm_search(key)

    def genera_retry_analysis(self, key):
        return self._genera.retry_analysis(key)

    def genera_undo_apply_ratio(self):
        return self._genera.undo_apply_ratio()

    # -- delegati a playlist_real, TUTTI col prefisso "playlist_" - stessa
    # convenzione uniforme di genera_*, anche se qui nessun nome collide
    # davvero con Correggi/Genera - coerenza sulla regola, non sul caso
    # per caso.
    def playlist_get_track_audio(self, track_id):
        return self._playlist.get_track_audio(track_id)

    def playlist_list_playlists(self):
        return self._playlist.list_playlists()

    def playlist_get_playlist(self, path):
        return self._playlist.get_playlist(path)

    def playlist_move_song(self, path, from_index, to_index):
        return self._playlist.move_song(path, from_index, to_index)

    def playlist_remove_song(self, path, index):
        return self._playlist.remove_song(path, index)

    def playlist_rename_playlist(self, path, new_name):
        return self._playlist.rename_playlist(path, new_name)

    def playlist_delete_playlist(self, path):
        return self._playlist.delete_playlist(path)

    def playlist_open_backup_folder(self):
        return self._playlist.open_backup_folder()

    # -- proprie del dashboard ----------------------------------------------
    def get_status(self):
        """Stato reale della patch - sola lettura, mai scrive nulla."""
        game_dir = _load_game_dir()
        return {'state': patch.state(game_dir), 'game_dir': game_dir, # VERSION_WEB: questo e' il toolkit web, che dalla 1.0 ha una
        # numerazione sua, non quella dei due exe Tkinter storici.
        'version': version.VERSION_WEB}

    def get_disclaimer_seen(self):
        """Le due schermate di disclaimer ("Start page | Disclaimer 1" e
        "| Disclaimer 2") si mostrano finche' non vengono accettate. Il
        consenso e' registrato in settings.json, lo stesso file gia' usato
        per tema e cartella di gioco - non un file nuovo."""
        return bool(_load_settings().get('disclaimer_accepted'))

    def set_disclaimer_seen(self):
        _save_setting_value('disclaimer_accepted', True)
        return {'ok': True}

    def close_app(self):
        """La X in alto a destra della modale (frame 7:320): su una start page
        chiude l'applicazione. Nessuna scrittura, nessun effetto sui file."""
        for w in webview.windows:
            w.destroy()
        return {'ok': True}

    def get_lang(self):
        """Lingua dell'interfaccia. Stessa settings.json gia' usata per tema e
        cartella di gioco, condivisa fra le pagine."""
        return _load_settings().get('lang', 'it')

    def set_lang(self, code):
        if code not in ('it', 'en'):
            return {'ok': False, 'error': 'Lingua non valida.'}
        _save_setting_value('lang', code)
        return {'ok': True, 'lang': code}

    def get_theme(self):
        """STESSA chiave/default della GUI Tkinter vera ('dark', vedi
        genera_real/app.py per il dettaglio) - condivisa fra le pagine."""
        # default CHIARO: il wireframe Figma e' disegnato in tema chiaro,
        # quindi e' quello il riferimento per il confronto 1:1 (richiesta
        # esplicita dell'utente). Resta solo un DEFAULT: la scelta salvata
        # in settings.json, condivisa con la GUI Tkinter, vince comunque.
        return _load_settings().get('theme', 'light')

    def set_theme(self, theme):
        if theme not in ('light', 'dark'):
            return {'ok': False, 'error': 'Tema non valido.'}
        _save_setting_value('theme', theme)
        return {'ok': True, 'theme': theme}

    def choose_game_dir(self):
        """Selettore cartella nativo - stessa validazione della GUI vera
        (patch.looks_like_game_dir), stesso settings.json.

        Si apre gia' vicino al bersaglio. Il tester ha fatto notare il
        problema con parole giuste: il percorso e'
        `...\\steamapps\\common\\BOXVR`, che chi usa il tool non ha nessun
        motivo di sapere a memoria - Steam lo nasconde dietro "Sfoglia file
        locali" e con piu' librerie puo' stare su un altro disco. Si prova
        nell'ordine: la cartella gia' nota, poi il rilevamento automatico,
        poi la cartella `steamapps\\common` di una libreria Steam esistente.
        """
        window = webview.windows[0]
        paths = window.create_file_dialog(webview.FileDialog.FOLDER,
                                          directory=_cartella_di_partenza())
        if not paths:
            return self.get_status()
        chosen = os.path.normpath(paths[0])
        if not patch.looks_like_game_dir(chosen):
            return {'state': 'invalid_dir', 'game_dir': None}
        _save_game_dir(chosen)
        return self.get_status()

    def toggle_patch(self):
        """"Disabilita" (patch attiva) o "Applica" (non ancora patchato) -
        STESSE boxvr_patch.revert/apply della GUI vera spedita, non una
        riscrittura. Scrive per davvero nel DLL del gioco (con backup
        automatico, gia' verificato dalla GUI vera in produzione) - per
        questo la pagina chiede conferma prima di chiamare questo metodo,
        non solo un click diretto."""
        game_dir = _load_game_dir()
        st = patch.state(game_dir)
        if st == patch.STATE_MISSING:
            return {'ok': False, 'message': 'Cartella di gioco non impostata o Assembly-CSharp.dll non trovata.'}
        if st == patch.STATE_UNKNOWN:
            return {'ok': False, 'message': 'Byte della DLL non riconosciuti - build diversa da quella attesa, non tocco nulla.'}
        if st == patch.STATE_PATCHED:
            ok, msg = patch.revert(game_dir)
        else:
            ok, msg = patch.apply(game_dir)
        return {'ok': ok, 'message': msg, 'status': self.get_status()}


# Prima di crearne una nuova, si tolgono di mezzo quelle vecchie: senza,
# ogni avvio lasciava indietro una copia completa dei brani (misurati 117 GB
# in 596 cartelle). Non blocca mai l'avvio - vedi pulizia_temp.py.
try:
    from pulizia_temp import pulisci_vecchie_cartelle as _pulisci
    from pulizia_temp import marca as _marca_pid
    from pulizia_temp import svuota_risultati as _svuota_risultati
except Exception:                      # noqa: BLE001
    def _pulisci():
        return (0, 0)

    def _marca_pid(_cartella):
        return None

    def _svuota_risultati():
        return (0, 0)


def build_serving_dir():
    """Una SOLA cartella di servizio per dashboard+Correggi+Genera (non una a
    testa): `<modulo>.build_serving_dir(work_dir=..., page_name=...)` copia i
    file audio reali + la propria pagina come "correggi.html"/"genera.html"
    nella STESSA cartella che serve anche "index.html" del dashboard - cosi'
    un `location.href = 'correggi.html'`/`'genera.html'` lato pagina resta
    dentro la stessa finestra/sessione pywebview invece di aprirne una
    seconda."""
    import shutil
    import tempfile
    _pulisci()
    # E i RISULTATI delle sessioni precedenti, che sono un'altra cosa dalle
    # cartelle temporanee di sopra: quelli si tolgono alla chiusura (vedi
    # main()), ma se il programma viene ucciso la chiusura non arriva mai -
    # e senza questa riga si tornerebbe ad accumulare come prima.
    _svuota_risultati()
    work_dir = tempfile.mkdtemp(prefix="boxvr_dashboard_real_")
    # il PID di chi la usa: cosi' il prossimo avvio sa se e'
    # abbandonata, invece di aspettare sei ore
    _marca_pid(work_dir)
    shutil.copy2(os.path.join(MOCKUPS_DIR, 'styles.css'), os.path.join(work_dir, 'styles.css'))
    shutil.copy2(os.path.join(os.path.dirname(__file__), 'index.html'), os.path.join(work_dir, 'index.html'))
    correggi_app.build_serving_dir(work_dir=work_dir, page_name='correggi.html')
    genera_app.build_serving_dir(work_dir=work_dir, page_name='genera.html')
    playlist_app.build_serving_dir(work_dir=work_dir, page_name='playlist.html')
    return work_dir


def main():
    import shutil
    if not webview2_check.ensure_webview2_or_exit():
        return

    # La tabella di tuning: si scrive il file di esempio (l'unico posto in
    # cui i valori stanno tutti insieme con limiti e provenienza) e si dice
    # cosa e' stato regolato o rifiutato. Regolare al buio, credendo di aver
    # cambiato un valore che invece e' stato scartato, e' peggio che non
    # poterlo regolare affatto.
    try:
        import tuning
        tuning.scrivi_esempio()
        _riepilogo = tuning.riepilogo()
        if _riepilogo:
            print(_riepilogo)
    except Exception as e:                 # noqa: BLE001
        print('tuning non disponibile (%s): valori di fabbrica' % e)
    # Il repertorio di pattern non e' dentro l'eseguibile - e' contenuto di
    # FitXR - e va estratto dalla copia del gioco dell'utente. Si fa qui,
    # all'apertura: serve sia alla generazione della coreografia sia
    # all'anteprima, ed e' materiale di base. Farlo solo alla prima
    # richiesta lasciava il tool in uno stato in cui la prima cosa che si
    # prova fallisce senza spiegare perche' (successo davvero: l'anteprima
    # restava vuota e accusava l'audio).
    try:
        ok, motivo = genera_app.assicura_repertorio(chiedi=True)
        if not ok:
            print('repertorio dei pattern non disponibile: %s' % motivo)
    except Exception as e:
        print('repertorio dei pattern: %s: %s' % (type(e).__name__, e))

    work_dir = build_serving_dir()
    correggi_app._work_dir = work_dir   # add_files copia i nuovi file qui, non nel suo tempdir separato
    correggi_app._init_songs()
    genera_app._work_dir = work_dir
    genera_app._init_songs()
    index_path = os.path.join(work_dir, 'index.html')
    # 1920x1080: STESSO canvas del wireframe ("Start page _ Dashboard
    # selection.svg", viewBox="0 0 1920 1080") - vedi il commento gemello in
    # genera_real/app.py per il perche' (1100x750 faceva apparire il layout
    # "allungato", segnalato dall'utente 31/08 sera)
    window = webview.create_window("Dashboard (dati reali)", index_path, js_api=Api(), width=1280, height=800)
    # stessa funzione gia' usata da Genera e Correggi: porta il contenuto a
    # 1920x1080 solo se ci sta davvero nello schermo, altrimenti e' la pagina
    # a scalarsi (fitPage) mantenendo le proporzioni del wireframe
    def _avvio(w):
        import trascina
        # Dentro la Dashboard le pagine cambiano con location.href nella
        # STESSA finestra: quale delle due funzioni serva dipende da dove si
        # e' arrivati, quindi si smista al momento del drop guardando la
        # pagina aperta.
        def _smista(percorsi):
            try:
                dove = w.evaluate_js('location.pathname') or ''
            except Exception:
                dove = ''
            if 'correggi' in dove:
                correggi_app.su_trascinamento(percorsi)
            elif 'genera' in dove:
                genera_app.su_trascinamento(percorsi)

        trascina.collega(w, '#song-panel', _smista)
        genera_app._fit_client_to_wireframe(w)

    webview.start(_avvio, window)
    # Da qui in poi la finestra e' chiusa. Si toglie la cartella di servizio
    # (le copie di lavoro) e anche i risultati gia' generati: sono file di
    # passaggio, e chi li voleva in gioco li ha gia' installati con
    # «Installa in BoxVR». Richiesto esplicitamente di farlo alla chiusura
    # oltre che all'avvio, "per essere certi".
    shutil.rmtree(work_dir, ignore_errors=True)
    quanti, byte = _svuota_risultati()
    if quanti:
        print('tolti %d file gia\' generati (%.0f MB)' % (quanti, byte / 1048576))


if __name__ == '__main__':
    main()
