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
Primo vero inizio del port di Correggi (31/08/2026 notte)
=============================================================
A differenza di tutto il resto di web_migration_spike/ (lo spike
timeline+playhead+marker, i mockup HTML/CSS statici in mockups/) - questo
file collega DAVVERO la pagina a `boxvr_fixer.py`: lista brani, forme
d'onda e livelli d'energia sono calcolati per davvero sugli 8 brani di
test reali (`file di test da correggere wav/`), non piu' dati finti in
mock-data.js.

Aggiornamento 31/08/2026 notte: "Avvia correzione" ORA scrive per davvero
(vedi Api.run_correction, riusa process_songs_with_presets - mai in_place,
mai sui brani di test originali, output in
"file di test da correggere wav/corretti/") - verificato con una
run reale (file scritto e riletto con successo). Preset/slider
(Intensità/Margine) ricalcolano dal vivo (vedi Api.recompute) - unica
interpretazione non scontata: "Preset" Leggero/Medio/Aggressivo nel
wireframe non corrisponde a un valore già codificato altrove nel progetto
(il vero punch_ratio in boxvr_fixer_gui.py è uno slider continuo, non tre
bottoni) - trattati qui come scorciatoie che impostano punch_ratio a
20/50/80%, una scelta ragionevole non ancora confermata dall'utente.
Ancora NON fa: integrazione con la libreria live di BoxVR. Primo passo
verticale del port vero, non il port completo - vedi
UI & Warframing/rd_migrazione_framework.md per lo stato completo
(checklist aggiornata lì).

Aggiornamento successivo (stessa notte): "Copia su tutti i brani" fatto
(Api.copy_to_all + impostazioni per-brano in Api._settings). Poi "Svuota"
(Api.clear_list, mai distruttivo: non tocca alcun file) e "Aggiungi
brani +" (Api.add_files, selettore file nativo filtrato su .trackdata.txt,
riusa `fixer.read_correct_item` - stessa validazione della GUI vera). Per
supportarli la lista non e' piu' "tutto cio' che sta in TEST_DIR" ma uno
stato esplicito e mutabile (`_active_ids`/`_song_paths`), popolato da
TEST_DIR all'avvio.

Aggiornamento (31/08/2026 notte): "Carica libreria BoxVR reale"
(Api.load_live_library) - collega DAVVERO la cartella vera del gioco
(`boxvr_install.boxvr_dirs()`, UNICA fonte di verita' per quel percorso
in tutto il progetto), non piu' solo la cartella di test. Riusa lo stesso
percorso sicuro di add_files (`_add_txt_paths`, estratto in comune):
copia sempre in una cartella di servizio separata, MAI legge/scrive
l'originale della libreria live. Verificato con chiamata reale: 24 brani
reali trovati e caricati, originale confermato intatto dopo. "Avvia
correzione" scrive comunque sempre in
"file di test da correggere wav/corretti/", MAI nella libreria live -
correggere un brano reale produce un file corretto separato, non
sovrascrive ne' reinstalla nulla in automatico (quel passo, l'installazione
vera con backup/gestione conflitti, e' compito di boxvr_install.py/la GUI
esistente, non ancora collegato qui).
"""
import json
import os
import shutil
import sys
import tempfile
import time

import numpy as np



# I percorsi non sono piu' cablati: li risolve percorsi.py, che funziona sia
# dai sorgenti sia dentro un eseguibile PyInstaller.
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import percorsi
percorsi.prepara_sys_path()

import installa

import boxvr_fixer as fixer
import boxvr_install as install
import boxvr_patch as patch
import version
import webview
import webview2_check


def _settings_path():
    """Stesso file di dashboard_real/boxvr_fixer_gui - sola lettura qui
    (game_dir si sceglie solo dal dashboard, non duplicato)."""
    base = os.environ.get('APPDATA') or os.path.dirname(__file__)
    return os.path.join(base, 'BoxVR Level Fixer', 'settings.json')


def _load_game_dir():
    try:
        with open(_settings_path(), encoding='utf-8') as f:
            return json.load(f).get('game_dir')
    except Exception:
        return None


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


TEST_DIR = percorsi.cartella_brani('correggi')
MOCKUPS_DIR = percorsi.MOCKUPS
# stessi default della GUI vera (boxvr_fixer_gui.py: DEFAULT_SETTINGS['margin'],
# punch_ratio di un brano appena aggiunto) - non inventati.
MARGIN = 0.12
PUNCH_RATIO = 0.5
LEVEL_CLASS = {0: 'silenzio', 1: 'leggero', 2: 'pugni', 3: 'misto'}

_analysis_cache = {}   # tid -> dict di compute_song_analysis, ricalcolare e' lento
_settings = {}          # tid -> (margin_pct, ratio_pct) - impostazioni per-brano
                        # (stessa idea degli slider punch_ratio/density per-song
                        # gia' presenti nella GUI vera), sovrascritte quando
                        # l'utente sposta uno slider o usa "Copia su tutti i brani"
_song_paths = {}   # tid -> (txt_path, wav_path) - puo' includere brani aggiunti
                   # da fuori TEST_DIR via Api.add_files, non solo quelli di test
_active_ids = []   # ordine reale della lista nel pannello - sottoinsieme
                   # mutabile di _song_paths (Api.clear_list/add_files), MAI
                   # il disco: svuotare la lista non cancella nulla
_work_dir = None   # cartella di servizio (build_serving_dir) - impostata da
                   # main(), serve ad add_files per copiarci i file aggiunti


def _preset_name(ratio_pct):
    """Nome del preset per il pallino colorato della riga brano - stessa
    scala dei tre bottoni (20/50/80), non una scala nuova."""
    if ratio_pct <= 35:
        return 'light'
    if ratio_pct <= 65:
        return 'medium'
    return 'aggressive'


def _get_settings(tid):
    return _settings.get(tid, (MARGIN * 100, PUNCH_RATIO * 100))


def discover_songs():
    # cartella assente = nessun brano, non un errore
    if not os.path.isdir(TEST_DIR):
        return []
    ids = []
    for fn in sorted(os.listdir(TEST_DIR)):
        if fn.endswith('.trackdata.txt'):
            tid = fn[:-len('.trackdata.txt')]
            if os.path.isfile(os.path.join(TEST_DIR, tid + '.wav')):
                ids.append(tid)
    return ids


def _init_songs():
    """Popola lo stato mutabile della lista dai brani di test - chiamata
    una sola volta all'avvio. Da qui in poi la lista vive in _active_ids,
    non viene piu' riletta da TEST_DIR ad ogni list_songs()."""
    for tid in discover_songs():
        _song_paths[tid] = (os.path.join(TEST_DIR, tid + '.trackdata.txt'),
                             os.path.join(TEST_DIR, tid + '.wav'))
        _active_ids.append(tid)


def su_trascinamento(percorsi):
    """File o cartelle lasciati cadere sulla pagina Correggi.

    Accetta i .trackdata.txt; la validazione della coppia (.txt + .wav) la
    fa comunque _add_txt_paths, che e' la stessa strada di "Aggiungi brani +".
    """
    import trascina
    file = trascina.espandi(percorsi, ('.trackdata.txt', '.txt'))
    if not file:
        return
    _add_txt_paths(file)
    try:
        webview.windows[0].evaluate_js('loadList && loadList()')
    except Exception:
        pass


def _add_txt_paths(txt_paths):
    """Nucleo condiviso di add_files/load_live_library - valida ogni .txt
    con fixer.read_correct_item (stessa regola della GUI vera: il .wav
    compagno deve esistere), copia la coppia nella cartella di servizio
    (mai l'originale spostato/modificato) e la registra in _song_paths/
    _active_ids. Un solo posto per questa logica evita che le due strade
    (selezione manuale, libreria live) divergano nel tempo."""
    added, errors = [], []
    for txt_path in txt_paths:
        item = fixer.read_correct_item(txt_path)
        if item is None:
            errors.append({'path': txt_path, 'error': 'manca il .wav corrispondente accanto al file'})
            continue
        tid = item['key']
        dest_txt = os.path.join(_work_dir, tid + '.trackdata.txt')
        dest_wav = os.path.join(_work_dir, tid + '.wav')
        shutil.copy2(item['txt_path'], dest_txt)
        shutil.copy2(item['wav_path'], dest_wav)
        _song_paths[tid] = (dest_txt, dest_wav)
        _analysis_cache.pop(tid, None)   # se un tid gia' noto viene riaggiunto da un percorso diverso, ricalcola
        if tid not in _active_ids:
            _active_ids.append(tid)
        added.append(tid)
    return added, errors


def get_analysis(tid):
    if tid not in _analysis_cache:
        txt_path, wav_path = _song_paths[tid]
        _analysis_cache[tid] = fixer.compute_song_analysis(txt_path, wav_path)
    return _analysis_cache[tid]


_ultima_correzione = {}

class Api:
    def get_app_info(self):
        """"Ver X.X.X.X" + pillola patch dell'header (Patch Status Button.svg)
        - sola lettura, stessa `boxvr_patch.state()` economica di
        dashboard_real (mai `find_all_installs`, troppo lenta per l'header).
        `game_dir` si sceglie SOLO dal dashboard - qui solo mostrato."""
        game_dir = _load_game_dir()
        # VERSION_WEB e non VERSION: l'header mostrava 1.29.2, cioe' la
        # numerazione dei due eseguibili Tkinter storici, mentre questo
        # e' il toolkit web, che dalla 1.0 ha una linea sua.
        return {'version': version.VERSION_WEB,
                'patch_state': patch.state(game_dir)}

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

    def list_songs(self):
        """Elenco reale - legge solo l'intestazione del trackdata (veloce,
        niente analisi audio), l'analisi vera parte solo quando un brano
        viene aperto (get_song_detail), esattamente come nella GUI vera
        (analisi in background alla selezione, non tutta in blocco).
        Itera _active_ids (mutabile: clear_list/add_files), non piu' un
        rilancio di discover_songs() ad ogni chiamata."""
        out = []
        for i, tid in enumerate(_active_ids):
            txt_path, _ = _song_paths[tid]
            with open(txt_path, encoding='utf-8') as f:
                outer = json.load(f)
            out.append({
                'id': tid, 'idx': f"{i + 1:02d}",
                'name': outer.get('originalTrackName', '?'),
                'artist': outer.get('originalArtist', '?'),
                'bpm': round(outer.get('bpm', 0)),
                'duration': float(outer.get('duration', 0.0)),
                # pallino del preset nella riga (Song Info Card): stessa
                # mappatura gia' usata dai tre bottoni Leggero/Medio/
                # Aggressivo, letta dalle impostazioni per-brano vere
                'preset': _preset_name(_get_settings(tid)[1]),
                'ratio_pct': _get_settings(tid)[1],
            })
        return out

    def remove_song(self, tid):
        """Rimozione di un singolo brano - dal componente Figma "Song Info
        Card" (stati "On focus"→piccola X in focus sulla riga→"Cancel on
        focus"→barra rossa "Rimuovi"), inizialmente segnata per errore come
        "non esiste nel wireframe" - corretto dopo che l'utente ha
        indicato dove guardare (l'icona compare solo mettendo a fuoco la
        riga, poi bisogna mettere a fuoco la X stessa). Come clear_list,
        MAI distruttivo: rimuove solo da _active_ids, nessun file toccato."""
        if tid in _active_ids:
            _active_ids.remove(tid)
        return {'n_songs': len(_active_ids)}

    def clear_list(self):
        """"Svuota" del wireframe - svuota la lista nel pannello. MAI
        un'operazione distruttiva: nessun file viene toccato, i brani
        restano intatti su disco e la lista si ripopola riavviando l'app
        (o con "Aggiungi brani +" se erano da fuori TEST_DIR)."""
        _active_ids.clear()
        return {'n_songs': 0}

    def add_files(self):
        """"Aggiungi brani +" del wireframe - apre un selettore file nativo
        vero, filtrato sui trackdata (.trackdata.txt). Riusa
        `fixer.read_correct_item`, la STESSA funzione di validazione della
        GUI vera (richiede che il .wav compagno esista accanto al .txt
        scelto) - non una riscrittura. I file scelti vengono COPIATI (mai
        spostati, mai modificati) nella cartella di servizio: l'audio deve
        stare nella stessa cartella della pagina perche' il tag <audio>
        funzioni (stessa regola gia' verificata per gli spike precedenti)."""
        window = webview.windows[0]
        paths = window.create_file_dialog(
            webview.FileDialog.OPEN, allow_multiple=True,
            file_types=('File trackdata (*.trackdata.txt)', 'Tutti i file (*.*)'))
        if not paths:
            return {'added': [], 'errors': []}
        added, errors = _add_txt_paths(paths)
        return {'added': added, 'errors': errors}

    def load_live_library(self):
        """"Libreria live di BoxVR" - carica in blocco i brani REALMENTE
        installati (stessa cartella della GUI vera, `boxvr_install.
        boxvr_dirs()` - UNICA fonte di verita' per quel percorso in tutto
        il progetto, non improvvisata qui). Riusa ESATTAMENTE la stessa
        strada sicura di add_files (`fixer.read_correct_item` per la
        validazione, copia nella cartella di servizio) - non una scansione
        bulk diversa, solo applicata a molti file invece che a una
        selezione manuale. Mai scrive/sposta/modifica gli originali."""
        trackdata_dir, _, _ = install.boxvr_dirs()
        if not os.path.isdir(trackdata_dir):
            return {'added': [], 'errors': [], 'n_found': 0}
        names = sorted(f for f in os.listdir(trackdata_dir) if f.endswith('.trackdata.txt'))
        paths = [os.path.join(trackdata_dir, fn) for fn in names]
        added, errors = _add_txt_paths(paths)
        return {'added': added, 'errors': errors, 'n_found': len(paths)}

    def recompute(self, tid, margin_pct, punch_ratio_pct):
        """Ricalcolo VERO al volo - stessa `classify_segments_with_preset`
        di `get_song_detail`, ma con margin/punch_ratio scelti dall'utente
        invece dei default fissi. Riusa l'analisi audio già in cache (la
        parte lenta, hpss/energia) - solo la classificazione (veloce) gira
        di nuovo, esattamente come fa la GUI vera quando si muove uno
        slider (l'audio non va rianalizzato, solo riclassificato)."""
        analysis = get_analysis(tid)   # cache - mai ricalcolato qui
        margin = max(0.0, min(1.0, margin_pct / 100.0))
        punch_ratio = max(0.0, min(1.0, punch_ratio_pct / 100.0))
        _settings[tid] = (margin_pct, punch_ratio_pct)   # ricordata per il brano finche' resta aperta l'app
        level_map = fixer.classify_segments_with_preset(analysis, margin, punch_ratio, force=False)
        segs = analysis['segs']
        segments, counts = [], {0: 0, 1: 0, 2: 0, 3: 0}
        for i, s in enumerate(segs):
            level = level_map.get(i, s['_energyLevel'])
            counts[level] += 1
            segments.append({
                'level': LEVEL_CLASS.get(level, 'silenzio'),
                'weight': max(0.01, fixer._segment_duration(analysis, s)),
            })
        return {
            'segments': segments,
            'counts': {LEVEL_CLASS[k]: v for k, v in counts.items()},
            'n_segments': len(segs),
        }

    def copy_to_all(self, margin_pct, punch_ratio_pct):
        """"Copia su tutti i brani" del wireframe - applica l'intensita'/il
        margine correnti come impostazione di TUTTI i brani ATTUALMENTE
        nella lista (_active_ids, non l'intero TEST_DIR - coerente con
        "Svuota"/"Aggiungi brani +", che ora la rendono un sottoinsieme
        mutabile). Solo stato in memoria (Api._settings), nessuna
        scrittura su disco - la scrittura resta compito esclusivo di
        run_correction, eseguito brano per brano dall'utente."""
        for t in _active_ids:
            _settings[t] = (margin_pct, punch_ratio_pct)
        return {'n_songs': len(_active_ids)}

    def run_correction(self, tid, margin_pct, punch_ratio_pct):
        """Primo "Avvia correzione" VERO del port - scrive per davvero un
        file corretto, riusando `process_songs_with_presets` (la stessa
        funzione della GUI e della CLI, non una riscrittura). Scrive in
        `file di test da correggere wav/corretti/` (cartella di OUTPUT
        separata, mai in_place - non tocca mai i file di test originali
        né la libreria vera di BoxVR). Un solo brano alla volta, come la
        UI oggi permette di avviare solo sul brano aperto. Il "Log" del
        wireframe non è più testo placeholder: sono le stesse righe che
        la CLI/GUI vera stampano (via il parametro `log=` di
        process_songs_with_presets, qui raccolto invece che stampato)."""
        txt_path, wav_path = _song_paths[tid]
        # NON piu' TEST_DIR/corretti: da quando la sorgente puo' essere
        # la libreria di BoxVR, derivare l'output dalla sorgente
        # significherebbe scrivere dentro l'albero del gioco.
        output_folder = percorsi.cartella_output('correggi', TEST_DIR)
        margin = max(0.0, min(1.0, margin_pct / 100.0))
        punch_ratio = max(0.0, min(1.0, punch_ratio_pct / 100.0))
        item = {'txt_path': txt_path, 'wav_path': wav_path, 'tid': tid, 'ratio': punch_ratio}
        log_lines = []   # "Log" del wireframe - le stesse righe che la CLI/GUI vera stampano
        try:
            result = fixer.process_songs_with_presets(
                [item], output_folder, margin=margin, dry_run=False, log=log_lines.append)
        except Exception as e:
            log_lines.append(f"ERRORE non gestito: {e}")
            return {'ok': False, 'error': str(e), 'log': '\n'.join(log_lines)}
        if result['n_errors'] or not result['n_ok']:
            return {'ok': False, 'error': 'process_songs_with_presets ha segnalato un errore - vedi log',
                    'log': '\n'.join(log_lines)}
        # Ricordo cosa e' stato appena scritto: e' quello che
        # install_preview/install_run installeranno. Un brano alla volta,
        # perche' la correzione si avvia sul brano aperto.
        _ultima_correzione['folder'] = result['output_folder']
        _ultima_correzione['track_ids'] = [tid]
        return {
            'ok': True, 'n_changed': result['n_changed'],
            'n_total_changes': result['n_total_changes'],
            'output_folder': result['output_folder'],
            'log': '\n'.join(log_lines),
        }

    def _ultimo_risultato(self):
        """(cartella di output, track id) dell'ultima correzione riuscita."""
        return _ultima_correzione.get('folder'), _ultima_correzione.get('track_ids') or []

    # ---- installazione nella libreria live di BoxVR ----
    # Due passi separati (anteprima -> conferma) perche' una pagina HTML non
    # ha i dialoghi modali di Tkinter: la prima NON scrive nulla e serve a
    # mostrare conflitti e destinazione, la seconda scrive davvero.

    def install_preview(self):
        """Cosa verrebbe installato dall'ultima esecuzione. Non scrive nulla."""
        cartella, ids = self._ultimo_risultato()
        if not cartella or not ids:
            return {'ok': False, 'error': 'Non c\'e\' ancora nulla da installare: '
                                          'esegui prima l\'operazione.'}
        return installa.anteprima_installazione(cartella, ids)

    def install_run(self, salta=None, fai_backup=True):
        """Installa davvero. `salta` = track id da NON sovrascrivere."""
        cartella, ids = self._ultimo_risultato()
        if not cartella or not ids:
            return {'ok': False, 'error': 'Non c\'e\' nulla da installare.'}
        return installa.esegui_installazione(cartella, ids, salta or [],
                                            fai_backup=bool(fai_backup))

    def open_game_folder(self):
        """Apre la cartella della libreria di BoxVR (era _open_boxvr_folder
        nella GUI Tkinter)."""
        return installa.apri_cartella_gioco()

    def open_folder(self, path):
        """"Apri cartella risultati" - apre Esplora risorse sulla cartella
        di output vera (solo quella scritta da run_correction, mai un
        percorso arbitrario passato da fuori)."""
        if os.path.isdir(path):
            os.startfile(path)

    def get_song_detail(self, tid):
        """Analisi VERA (compute_song_analysis + classify_segments_with_preset,
        stessi margin/punch_ratio di default della GUI) - non dati finti.
        Ritorna anche il nome del file wav copiato nella cartella di
        servizio (vedi main()), per il tag <audio>."""
        analysis = get_analysis(tid)
        margin_pct, ratio_pct = _get_settings(tid)
        level_map = fixer.classify_segments_with_preset(
            analysis, margin_pct / 100.0, ratio_pct / 100.0, force=False)
        segs = analysis['segs']
        segments, counts = [], {0: 0, 1: 0, 2: 0, 3: 0}
        original_segments = []
        for i, s in enumerate(segs):
            level = level_map.get(i, s['_energyLevel'])
            counts[level] += 1
            weight = max(0.01, fixer._segment_duration(analysis, s))
            segments.append({'level': LEVEL_CLASS.get(level, 'silenzio'), 'weight': weight})
            # "Struttura BoxVR di partenza" (wireframe) - il livello ORIGINALE
            # del gioco per ogni segmento, mai passato da classify_segments_with_preset
            # (quello e' il risultato ipotetico coi preset correnti, questo e'
            # quello che il trackdata aveva scritto prima di qualunque correzione)
            original_segments.append({'level': LEVEL_CLASS.get(s['_energyLevel'], 'silenzio'), 'weight': weight})
        return {
            'id': tid, 'wav': tid + '.wav',
            'name': analysis['name'], 'artist': analysis['artist'],
            'bpm': round(get_bpm(analysis)), 'duration': analysis['duration'],
            'segments': segments, 'original_segments': original_segments,
            'counts': {LEVEL_CLASS[k]: v for k, v in counts.items()},
            'n_segments': len(segs),
            'margin_pct': margin_pct, 'ratio_pct': ratio_pct,
            # toggle "Base beat"/"Curva di carica" della waveform - stessi dati
            # di genera_real/app.py (vedi li' per il dettaglio), analysis['beats']/
            # bar_score sono gia' calcolati da compute_song_analysis, nessun
            # ricalcolo qui
            'beat_times': [b['_triggerTime'] for b in analysis['beats']],
            'energy_curve': _energy_curve(analysis),
            # forma d'onda reale, come in genera_real (vedi _waveform_peaks)
            'waveform_peaks': _waveform_peaks(tid),
        }


_peaks_cache = {}


def _waveform_peaks(tid, n_bins=1400):
    """Ampiezza REALE del brano per la forma d'onda dell'anteprima - stesso
    calcolo di genera_real/_waveform_peaks e della GUI Tkinter
    (_get_waveform_peaks): picco assoluto per bin, normalizzato sul massimo
    di QUESTO brano. Qui l'audio non e' gia' in memoria come in genera_real
    (compute_song_analysis non lo conserva), quindi si rilegge il wav una
    volta sola e si mette in cache - la forma d'onda non cambia mai per un
    dato brano, mentre la pagina la ridisegna a ogni cambio preset/slider."""
    if tid in _peaks_cache:
        return _peaks_cache[tid]
    # _song_paths[tid] e' la tupla (txt_path, wav_path) gia' usata da
    # get_analysis: stessa fonte, cosi' funziona anche per i brani aggiunti
    # a mano o importati dalla libreria live, non solo per quelli di TEST_DIR
    paths = _song_paths.get(tid)
    wav = paths[1] if paths else os.path.join(TEST_DIR, tid + '.wav')
    try:
        mono, _sr = fixer.load_wav_mono(wav)
    except Exception:
        _peaks_cache[tid] = []
        return []
    mono_abs = np.abs(mono)
    n = len(mono_abs)
    if n == 0:
        _peaks_cache[tid] = []
        return []
    bins = min(n_bins, n) or 1
    bin_size = n // bins
    if bin_size:
        peaks = mono_abs[:bin_size * bins].reshape(bins, bin_size).max(axis=1)
    else:
        peaks = mono_abs
    peak_max = float(peaks.max()) or 1.0
    out = [round(float(p) / peak_max, 4) for p in peaks]
    _peaks_cache[tid] = out
    return out


def get_bpm(analysis):
    beats = analysis['beats']
    return beats[0]['_bpm'] if beats else 0.0


def _energy_curve(analysis):
    """Vedi genera_real/app.py per lo stesso identico calcolo/motivazione -
    bar_score normalizzato 0-1 su QUESTO brano, cast a float python esplicito."""
    bar_score = analysis['bar_score']
    bars = analysis['bars']
    if len(bar_score) == 0:
        return []
    lo, hi = float(bar_score.min()), float(bar_score.max())
    span = (hi - lo) or 1.0
    punti = [{'t': b['_startTime'], 'v': (float(s) - lo) / span}
             for b, s in zip(bars, bar_score)]
    # Gli estremi. Il punto di una battuta sta al suo INIZIO, quindi
    # l'ultimo cade sull'inizio dell'ultima battuta e non sulla fine del
    # brano: la curva si fermava prima del bordo destro dell'anteprima -
    # sempre di una battuta, e di parecchi secondi quando il rilevamento
    # del ritmo si ferma in anticipo (sono gli stessi vuoti di coda che
    # questo tool esiste per riempire). Stesso discorso a sinistra, dove
    # la prima battuta comincia dopo l'attacco.
    #
    # Si prolunga PIATTO il valore misurato piu' vicino: dice "qui non
    # c'e' una misura nuova". Farlo scendere a zero racconterebbe un calo
    # di energia che nessuno ha misurato.
    durata = float(analysis.get('duration') or 0.0)
    if punti:
        if punti[0]['t'] > 0.0:
            punti.insert(0, {'t': 0.0, 'v': punti[0]['v']})
        if durata > punti[-1]['t']:
            punti.append({'t': durata, 'v': punti[-1]['v']})
    return punti


WIREFRAME_W, WIREFRAME_H = 1920, 1080


def _fit_client_to_wireframe(window):
    """Avvicina l'area di CONTENUTO a 1920x1080 senza mai uscire dall'area di
    lavoro dello schermo.

    La versione precedente confrontava le dimensioni della finestra con
    GetSystemMetrics, cioe' pixel FISICI: due sistemi di misura diversi. Con
    lo scaling di Windows al 125% - la condizione piu' comune sui portatili -
    uno schermo 1920x1080 ha un desktop logico di 1536x864 e un'area di lavoro
    di 1536x824, ma il confronto con "1920x1080" non se ne accorgeva. Il test
    su macchina pulita ha misurato il risultato: finestra 1554x882 in
    posizione (-11, 6), quindi fuori schermo a sinistra e infilata sotto la
    barra delle applicazioni.

    Qui si misura tutto DENTRO la pagina e nella stessa unita' (px CSS):
    innerWidth/innerHeight per l'area di contenuto, screen.availWidth/
    availHeight per l'area di lavoro - che esclude gia' la barra delle
    applicazioni. Il ridimensionamento procede per RAPPORTI fra misurato e
    voluto, quindi non serve sapere in che unita' ragioni pywebview ne'
    quanto misurino bordi e barra del titolo: converge in due o tre passi da
    solo, e continua a funzionare a qualunque DPI.
    """
    MARGINE = 16          # respiro fra la finestra e il bordo dell'area utile

    def misura():
        for _ in range(40):
            try:
                m = window.evaluate_js(
                    '[window.innerWidth, window.innerHeight,'
                    ' window.screen.availWidth, window.screen.availHeight]')
            except Exception:
                m = None
            if m and m[0] and m[1] and m[2] and m[3]:
                return m
            time.sleep(0.25)
        return None

    ultimo = None
    for _ in range(4):
        m = misura()
        if not m:
            return
        ultimo = m
        iw, ih, aw, ah = m
        voluto_w = min(WIREFRAME_W, max(800, aw - MARGINE))
        voluto_h = min(WIREFRAME_H, max(600, ah - MARGINE))
        if abs(iw - voluto_w) <= 2 and abs(ih - voluto_h) <= 2:
            break
        nuovo_w = max(800, int(round(window.width * voluto_w / float(iw))))
        nuovo_h = max(600, int(round(window.height * voluto_h / float(ih))))
        if (nuovo_w, nuovo_h) == (window.width, window.height):
            break
        try:
            window.resize(nuovo_w, nuovo_h)
        except Exception:
            break
        time.sleep(0.35)

    # Centrata nell'area di lavoro. Le coordinate di move() sono nelle unita'
    # della finestra, non in px CSS: il fattore di conversione lo si RICAVA
    # dal rapporto gia' misurato, invece di ipotizzarlo.
    if ultimo:
        try:
            iw, ih, aw, ah = misura() or ultimo
            k = window.width / float(iw) if iw else 1.0
            x = int(max(0, (aw * k - window.width) / 2))
            y = int(max(0, (ah * k - window.height) / 2))
            window.move(x, y)
        except Exception:
            pass
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


def build_serving_dir(work_dir=None, page_name='index.html'):
    """Copia wav reali + styles.css in una cartella di lavoro - stessa
    combinazione "pagina+audio nella stessa cartella" gia' verificata
    necessaria negli spike precedenti per far funzionare file:///.

    `work_dir`/`page_name` opzionali (default: nuova cartella temporanea,
    'index.html') - permettono a `dashboard_real` di riusare la STESSA
    cartella di servizio invece di aprirne una seconda, per avere una vera
    navigazione Dashboard->Correggi in un'unica finestra/sessione pywebview."""
    if work_dir is None:
        _pulisci()
        # e i risultati delle sessioni precedenti (vedi svuota_risultati):
        # qui solo quando la pagina gira da sola, perche' aperta dalla
        # Dashboard ci ha gia' pensato lei
        _svuota_risultati()
        work_dir = tempfile.mkdtemp(prefix="boxvr_correggi_real_")
    # il PID di chi la usa: cosi' il prossimo avvio sa se e'
    # abbandonata, invece di aspettare sei ore
    _marca_pid(work_dir)
    for tid in discover_songs():
        shutil.copy2(os.path.join(TEST_DIR, tid + '.wav'), os.path.join(work_dir, tid + '.wav'))
    shutil.copy2(os.path.join(MOCKUPS_DIR, 'styles.css'), os.path.join(work_dir, 'styles.css'))
    # STESSI assets di genera_real (icone del pattern di sfondo, icone dei
    # tooltip, cartella vuota): la pagina li usa via CSS mask-image, quindi
    # devono esistere come file accanto alla pagina
    assets_src = os.path.join(MOCKUPS_DIR, 'assets')
    if os.path.isdir(assets_src):
        dest = os.path.join(work_dir, 'assets')
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(assets_src, dest)
    shutil.copy2(os.path.join(os.path.dirname(__file__), 'index.html'), os.path.join(work_dir, page_name))
    return work_dir


def main():
    global _work_dir
    if not webview2_check.ensure_webview2_or_exit():
        return
    _work_dir = build_serving_dir()
    _init_songs()
    index_path = os.path.join(_work_dir, 'index.html')
    print(f"[correggi_real] {len(_active_ids)} brani reali trovati, pagina in {index_path}")
    # 1920x1080: STESSO canvas del wireframe - vedi il commento gemello in
    # genera_real/app.py (1400x900 faceva apparire il layout "allungato",
    # segnalato dall'utente 31/08 sera)
    window = webview.create_window("Correggi (dati reali)", index_path, js_api=Api(), width=1280, height=800)
    def _avvio(w):
        import trascina
        # il pannello brani e' l'elemento stabile: le righe dentro vengono
        # ridisegnate di continuo, il contenitore no
        trascina.collega(w, '#song-panel', su_trascinamento)
        _fit_client_to_wireframe(w)

    webview.start(_avvio, window)
    # chiusa la finestra: via le copie di lavoro e via i risultati gia'
    # generati, che sono file di passaggio (vedi svuota_risultati)
    shutil.rmtree(_work_dir, ignore_errors=True)
    _svuota_risultati()


if __name__ == '__main__':
    main()
