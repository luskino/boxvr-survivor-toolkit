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
Primo vero inizio del port di Genera (31/08/2026 notte)
=========================================================
Come `correggi_real/`, ma per la modalita' Genera: collega DAVVERO la
pagina a `boxvr_generator.py` sull'unico mp3 di test reale presente
(`File di test da correggere mp3/ILIA - run off - (320 Kbps).mp3`), non
`mock-data.js`. Riusa `boxvr_generator.analyze_for_generate` - la STESSA
funzione di decisione motore (librosa/madmom) gia' estratta ed testata
dalla GUI vera (vedi [[boxvr-ui-framework-migration]]) - per l'analisi, e
`boxvr_generator.classify_segments_for_generation` (NON
`boxvr_fixer.classify_segments_with_preset` - quella e' la politica a
soglie percentili di Correggi, per segmenti gia' classificati dal gioco;
qui i segmenti sono generati da zero, senza un livello originale a cui
tornare, e usano una politica diversa a budget di durata - scambiarle dà
un `KeyError` reale su `analysis['silence_thresh']`, scoperto provandole
insieme, non leggendo il codice) per i livelli. `_segment_duration` di
`boxvr_fixer.py` resta condivisa fra i due flussi (il suo stesso docstring
dice che funziona per entrambi i formati di beat).

Aggiornamento (stessa notte): Preset (Leggero/Medio/Aggressivo) e slider
Intensità ora ricalcolano dal vivo per davvero (`Api.recompute`, stessa
idea di `correggi_real` - impostazione per-brano in memoria, l'analisi
lenta resta in cache, solo la classificazione veloce rigira).

Aggiornamento (stessa notte): "Avvia generazione" ORA scrive per davvero
(`Api.run_generation`, riusa `boxvr_generator.generate_track` - trackdata
+wav+wdef+coreografia insieme, non un file solo come in Correggi) in
"File di test da correggere mp3/generati/" (cartella di test separata,
mai nella libreria vera di BoxVR). Riusa `beat_engine`/`boundary_bars`
dell'analisi gia' mostrata in anteprima, non li ricalcola - vedi il
docstring di `run_generation` per il perche' e' necessario, non solo
un'ottimizzazione.

Aggiornamento (stessa notte, dopo un riesport SVG dell'utente - "Anteprima
brano.svg" aveva la matita BPM e il toggle Precisa/Veloce, mai notati
prima nell'export vecchio): BPM manuale (`Api.set_forced_bpm`/
`clear_forced_bpm`, rianalizza da zero - forced_bpm cambia il beat-tracking
vero, non solo l'etichetta) e scelta motore manuale (`Api.set_engine`,
Precisa=madmom/Veloce=librosa, esce da 'auto' verso 'manual') ora reali,
con `Api.open_bpm_search` che riusa `boxvr_generator.bpm_search_url` per
l'icona "cerca online". Nessun controllo densita' - confermato col
wireframe aggiornato che non esiste (solo intensita'/punch_ratio, densita'
resta al default storico del modulo), nessun supporto sidecar/marker.

Aggiornamento (stessa notte): "Aggiungi brani +"/"Svuota"/rimozione
singola replicati da `correggi_real` (`Api.add_files`/`clear_list`/
`remove_song`, stesso pattern: `_active_ids` mutabile, mai distruttivo).
Differenza rispetto a Correggi: qui non serve `fixer.read_correct_item`
(nessun file "compagno" richiesto - `read_generate_item` e' sempre
valido), il selettore filtra su audio (.mp3/.wav) non su .trackdata.txt.
"""
import json
import os
import sys
import tempfile
import threading
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
import boxvr_generator as gen
import boxvr_choreo as _choreo
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

TEST_DIR = percorsi.cartella_brani('genera')
MOCKUPS_DIR = percorsi.MOCKUPS
# nessun "margin" qui (concetto solo di Correggi) - punch_ratio di un
# brano appena analizzato, stesso default usato altrove nel progetto.
PUNCH_RATIO = 0.5
LEVEL_CLASS = {0: 'silenzio', 1: 'leggero', 2: 'pugni', 3: 'misto'}
AUDIO_EXTS = ('.mp3', '.wav')

_analysis_cache = {}   # key -> risultato di analyze_for_generate (lento: beat-tracking + segmentazione)
_song_paths = {}       # key -> percorso file audio originale
_active_ids = []
_work_dir = None
_track_song_key = {}  # track_id -> key del brano sorgente (popolato da run_generation, per risalire ai marker sidecar dal visualizzatore)
_settings = {}   # key -> ratio_pct - impostazione per-brano (stessa idea di correggi_real._settings)
_ratio_undo_snapshot = None  # stato di _settings prima dell'ultima "Unifica playlist" (per "Annulla unificazione")
_forced_bpm = {}     # key -> bpm forzato manualmente (None/assente = rilevato automaticamente)
_engine_choice = {}  # key -> 'librosa'/'madmom' scelto a mano ("Precisa"/"Veloce" nel wireframe), assente = 'auto'

# -- sidecar/marker (31/08 pomeriggio, PRIMA integrazione nel port - porta 1:1
# la logica REALE gia' spedita in boxvr_fixer_gui.py (_sidecar_*), mai
# riscritta. "Registra" e' un punch-in dalla posizione corrente: i marker
# DA QUEL PUNTO IN POI vengono scartati (verranno ri-registrati), quelli
# prima restano intatti - confermato dall'utente ("i marker rossi sono
# quelli dopo la linea centrale del tempo... verranno cancellati man mano
# che la linea del tempo ci va sopra"). "BPM RANGE" nel wireframe e' la
# griglia di beat automatici disegnata accanto ai marker manuali, solo per
# confronto visivo - nessun dato nuovo, riusa analysis['beats'].
_sidecar_markers = {}       # key -> [secondi, ...] marcati a mano
_sidecar_mode = {}          # key -> 'markers_only'|'harmonize'|'extend', assente = 'harmonize' (default motore)
_sidecar_exclude = {}       # key -> bool ("solo hit marker", mai Squat/Dodge)
_sidecar_min_gap_ms = {}    # key -> ms|None, assente = default motore (170ms, MIN_INPUT_GAP_S)
_sidecar_recording_key = None  # quale brano sta registrando ora, None = nessuno (un solo player alla volta, come la GUI vera)


def _get_ratio_pct(key):
    return _settings.get(key, PUNCH_RATIO * 100)


PRESET_RATIO_PCT = {'light': 20, 'medium': 50, 'aggressive': 80}


def _copertura(key):
    """Quanti secondi di brano sono marcati, e se bastano a «Estendi».

    Gli accenti audio servono a contare come conta il motore (i marker
    agganciati a un accento possono fondersi diversamente): se l'analisi
    non e' ancora pronta si conta senza, che e' comunque il numero giusto
    a meno di frazioni di secondo."""
    motore = gen.sidecar_engine()
    pronta = analisi_se_pronta(key)
    onsets = (pronta['analysis'].get('onsets') if pronta else None)
    soglia_ms = _sidecar_min_gap_ms.get(key)
    if soglia_ms is None:
        soglia_ms = 170
    beats = (pronta['analysis'].get('beats') if pronta else None)
    return motore.copertura_marcata(_sidecar_markers.get(key) or [],
                                    onsets, soglia_ms / 1000.0, beats=beats)


def _marker_scartati(key):
    """Marker scartati dalla soglia minima, per il brano dato."""
    soglia_ms = _sidecar_min_gap_ms.get(key)
    if soglia_ms is None:
        soglia_ms = 170          # default del motore (MIN_INPUT_GAP_S)
    return Api._conta_scartati(_sidecar_markers.get(key) or [], soglia_ms / 1000.0)


def _epm_hint(ratio_pct):
    """"61-103 colpi/min (BoxVR ufficiale : 82)" del wireframe (Pannello
    generazione, tab Automatica) - dati REALI, NON stimati qui: stessa
    boxvr_choreo.INTENSITY_PRESETS['epm_range']/OFFICIAL_EPM gia' misurata
    sulla coreografia vera (15 brani ufficiali + 6 di riferimento, vedi
    commento in boxvr_choreo.py) e gia' mostrata identica nella GUI Tkinter
    vera (_refresh_choreo_epm) - stessa fonte, non una seconda stima."""
    import boxvr_choreo as _choreo
    key = _preset_from_ratio_pct(ratio_pct)
    key = {'aggressive': 'high'}.get(key, key)
    lo, hi = _choreo.INTENSITY_PRESETS[key]['epm_range']
    return {'lo': lo, 'hi': hi, 'official': _choreo.OFFICIAL_EPM}


def _preset_from_ratio_pct(ratio_pct):
    """Pallino colorato di 'Pannello brani' (chiarito dall'utente 31/08 sera:
    verde/giallo/rosso = leggero/medio/aggressivo, il preset attualmente in
    uso per quel brano - giallo/medio e' il default, coerente con
    PUNCH_RATIO=0.5). Il preset non e' salvato per se' - si ricava dal
    ratio_pct piu' vicino ai tre bottoni scorciatoia (20/50/80), stessa
    logica gia' usata per evidenziare il bottone attivo in interfaccia."""
    return min(PRESET_RATIO_PCT, key=lambda p: abs(PRESET_RATIO_PCT[p] - ratio_pct))


def _load_settings():
    try:
        with open(_settings_path(), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_setting_value(key, value):
    """Scrittura generica su settings.json (STESSO file/schema di
    game_dir/sidecar_bias) - riusata per 'theme' cosi' la preferenza tema
    e' condivisa fra dashboard/genera/correggi invece di 3 copie separate."""
    p = _settings_path()
    data = _load_settings()
    data[key] = value
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def _save_sidecar_bias(bias_s, bias_n):
    """STESSA chiave/file di boxvr_fixer_gui.py (app.settings['sidecar_bias_s'/'sidecar_bias_n'],
    %APPDATA%/BoxVR Level Fixer/settings.json) - la calibrazione personale e'
    dell'UTENTE su questa macchina, non del singolo brano/sessione: se vive in
    due file diversi (GUI Tkinter vs port web) smettono di imparare insieme."""
    p = _settings_path()
    data = _load_settings()
    data['sidecar_bias_s'] = bias_s
    data['sidecar_bias_n'] = bias_n
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f)


SIDECAR_BIAS_LEARN_WINDOW_S = 0.15  # STESSO valore di boxvr_fixer_gui.py - non ridefinito a occhio
SIDECAR_BIAS_MAX_N = 200


def _learn_sidecar_bias(key):
    """Porta 1:1 di boxvr_fixer_gui._learn_sidecar_bias - media mobile pesata
    per conteggio tra lo scostamento dei marker appena piazzati e l'accento
    audio reale piu' vicino (analysis['onsets'], gia' calcolato, mai
    ricalcolato qui). Chiamata a fine registrazione, non per singolo marker
    (un tap isolato puo' essere un errore, una decina nella stessa sessione
    da' un segnale piu' solido sulla tendenza reale dell'utente)."""
    import bisect
    markers = _sidecar_markers.get(key) or []
    if not markers:
        return
    analysis = get_analysis(key)['analysis']
    onsets = sorted(analysis.get('onsets') or [])
    if not onsets:
        return
    deltas = []
    for t in markers:
        i = bisect.bisect_left(onsets, t)
        candidates = [onsets[j] for j in (i - 1, i) if 0 <= j < len(onsets)]
        if not candidates:
            continue
        nearest = min(candidates, key=lambda o: abs(o - t))
        delta = t - nearest
        if abs(delta) <= SIDECAR_BIAS_LEARN_WINDOW_S:
            deltas.append(delta)
    if not deltas:
        return
    session_bias = sum(deltas) / len(deltas)
    session_n = len(deltas)
    data = _load_settings()
    prev_bias = data.get('sidecar_bias_s', 0.0)
    prev_n = data.get('sidecar_bias_n', 0)
    total_n = min(prev_n + session_n, SIDECAR_BIAS_MAX_N)
    if prev_n <= 0:
        new_bias = session_bias
    else:
        weight_prev = prev_n / (prev_n + session_n)
        new_bias = prev_bias * weight_prev + session_bias * (1.0 - weight_prev)
    _save_sidecar_bias(new_bias, total_n)


def _run_analysis(key):
    """Un solo punto che decide come chiamare analyze_for_generate, in modo
    che get_analysis/invalidate restino semplici indipendentemente da quante
    sovrascritture manuali (BPM/motore) sono attive per questo brano."""
    kwargs = {'forced_bpm': _forced_bpm.get(key)}
    engine = _engine_choice.get(key)
    if engine:
        kwargs['engine_mode'] = 'manual'
        kwargs['beat_engine'] = engine
    return gen.analyze_for_generate(_song_paths[key], **kwargs)


def _invalidate_analysis(key):
    """Butta via l'analisi in cache E la sua contabilita', poi rilancia
    subito il calcolo in background.

    Svuotare la sola cache lasciava _analysis_status a 'done' con la
    cache vuota: stato_analisi rispondeva 'pending' per sempre (il ramo
    che riavvia il thread scatta solo quando lo stato e' assente) e la
    rianalisi dopo un BPM o un motore forzati non partiva mai.
    """
    _analysis_cache.pop(key, None)
    _analysis_status.pop(key, None)
    _start_background_analysis(key)


def discover_songs():
    # cartella assente = nessun brano, non un errore
    if not os.path.isdir(TEST_DIR):
        return []
    return [fn for fn in sorted(os.listdir(TEST_DIR))
            if fn.lower().endswith(AUDIO_EXTS) and os.path.isfile(os.path.join(TEST_DIR, fn))]


def _init_songs():
    for fn in discover_songs():
        _song_paths[fn] = os.path.join(TEST_DIR, fn)
        _active_ids.append(fn)
        _start_background_analysis(fn)


def _energy_curve(analysis):
    """"Curva di carica" del wireframe - bar_score normalizzato 0-1 su
    QUESTO brano (min-max, stessa idea gia' usata altrove nel progetto per
    non confrontare scale assolute diverse fra brani), un punto per bar con
    il suo tempo reale. cast a float python esplicito - bar_score e' un
    array numpy, il bridge pywebview non serializza i suoi scalari."""
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


def _waveform_peaks(analysis, n_bins=1400):
    """Ampiezza REALE del brano (spettro/waveform del wireframe, segnalato
    mancante) - non simulata: picco assoluto per bin da 'native_audio' gia'
    decodificato da decode_audio per il wav di output (mai un secondo
    decode). Un canale solo (max fra i canali se stereo), normalizzata
    0-1 sul MASSIMO REALE di questo brano - stessa idea gia' usata da
    _energy_curve per bar_score."""
    native = analysis['native_audio']
    if native.size == 0:
        return []
    mono_abs = np.abs(native).max(axis=1) if native.ndim == 2 else np.abs(native)
    n = len(mono_abs)
    n_bins = min(n_bins, n) or 1
    bin_size = n // n_bins
    trimmed = mono_abs[:bin_size * n_bins]
    peaks = trimmed.reshape(n_bins, bin_size).max(axis=1) if bin_size else mono_abs
    peak_max = float(peaks.max()) or 1.0
    return [round(float(p) / peak_max, 4) for p in peaks]


def get_analysis(key):
    if key not in _analysis_cache:
        _analysis_cache[key] = _run_analysis(key)
    return _analysis_cache[key]


def analisi_se_pronta(key):
    """L'analisi SOLO se e' gia' in cache, altrimenti None. Non la calcola mai.

    get_analysis, sopra, e' bloccante: se il brano non e' stato ancora
    analizzato lo analizza li' per li' e ritorna solo a lavoro finito. Va
    bene per chi puo' aspettare (la generazione), non per chi risponde a un
    clic: selezionare un brano non pronto congelava l'interfaccia, e con il
    motore Preciso (madmom) sono minuti, non secondi.

    Chi chiama questa versione deve saper rispondere "non pronta" - ed e'
    quel "non pronta" che accende lo stato disabilitato in interfaccia.
    """
    return _analysis_cache.get(key)


def stato_analisi(key):
    """'done' | 'error' | 'pending', con la CACHE come fatto.

    Vale la stessa regola di list_songs: se l'analisi c'e', il brano e'
    pronto, chiunque l'abbia calcolata. Lo stato registrato conta solo
    quando la cache e' vuota.
    """
    if key in _analysis_cache:
        return 'done'
    registrato = _analysis_status.get(key)
    if registrato == 'error':
        return 'error'
    if registrato is None:
        _start_background_analysis(key)
    return 'pending' 


# Analisi in background per riga della lista brani (dati REALI da
# get_design_context su "Pannello brani": ogni riga nel reale mostra BPM +
# stato per OGNI brano, non solo quello selezionato - scelta confermata
# esplicitamente dall'utente, consapevole del costo prestazionale reale
# rispetto all'analisi solo-alla-selezione usata finora). Un thread per
# brano, mai bloccante per la UI/pywebview - _analysis_status e'
# l'unica fonte di verita' per songRowHtml lato frontend (list_songs le
# espone), get_song_detail continua a passare da get_analysis/_analysis_cache
# come prima (nessuna duplicazione di logica di analisi).
_analysis_status = {}   # key -> 'pending' | 'done' | 'error'
_analysis_lock = threading.Lock()


def _analysis_worker(key):
    try:
        get_analysis(key)
        _analysis_status[key] = 'done'
    except Exception:
        _analysis_status[key] = 'error'


def _start_background_analysis(key):
    with _analysis_lock:
        if _analysis_status.get(key) == 'pending':
            return
        if key in _analysis_cache:
            _analysis_status[key] = 'done'
            return
        _analysis_status[key] = 'pending'
    threading.Thread(target=_analysis_worker, args=(key,), daemon=True).start()


_ultima_generazione = {}

# Coreografie d'anteprima: costruite al volo, mai scritte su disco.
# chiave brano -> (firma, action_list). La firma contiene tutto cio' che
# cambierebbe il risultato; se cambia, l'anteprima si ricostruisce.
_anteprima_choreo = {}


def _firma_anteprima(key):
    # Il TUNING fa parte della firma, e per un motivo trovato sul campo:
    # senza, muovendo uno slider la firma restava identica e questa cache
    # restituiva la coreografia di prima. Il `rigenera=True` del pannello
    # arrivava fin qui e veniva annullato un livello sotto - riprodotto il
    # 08/09: respiro da 1.0 a 2.0, 279 colpi prima e 279 dopo, agli stessi
    # istanti. Non riguardava un valore: riguardava tutti.
    try:
        import tuning
        stato_tuning = tuning.firma()
    except Exception:                      # noqa: BLE001
        stato_tuning = ()
    return (
        tuple(_sidecar_markers.get(key) or ()),
        _sidecar_mode.get(key),
        _sidecar_min_gap_ms.get(key),
        _sidecar_exclude.get(key, False),
        stato_tuning,
    )


def _scarta_anteprima(key=None):
    """Butta l'anteprima in cache: da chiamare quando cambiano i marker."""
    if key is None:
        _anteprima_choreo.clear()
    else:
        _anteprima_choreo.pop(key, None)


def _actionlist_anteprima(key, calcola_analisi=False):
    """La coreografia del brano, costruita ora se serve.

    None se l'analisi non e' ancora pronta: la pagina ha gia' lo stato
    "Analisi in corso" da mostrare, meglio quello di un errore.

    `calcola_analisi` ribalta quella scelta, e serve a un caso preciso: il
    pannello di tuning. La tendina dell'anteprima elenca i brani GIA'
    GENERATI, che all'avvio non hanno nessuna analisi in memoria - la
    cartella di servizio e' temporanea e la cache parte vuota. Rifiutare
    li' significa che muovendo uno slider non succede niente, che e'
    esattamente cio' che e' stato segnalato l'08/09 dopo due correzioni che
    nei test risultavano a posto: i test mettevano l'analisi in cache a
    mano, cioe' provavano il caso raro.

    Il rifiuto ha senso mentre la pagina disegna. Non ha senso quando
    qualcuno ha appena mosso uno slider e aspetta di vedere l'effetto: li'
    l'analisi si calcola, anche se costa qualche secondo, e si calcola una
    volta sola perche' poi resta in cache.
    """
    if key not in _analysis_cache:
        if not calcola_analisi or not _song_paths.get(key):
            return None
        try:
            get_analysis(key)
        except Exception:                  # noqa: BLE001
            return None
    firma = _firma_anteprima(key)
    salvata = _anteprima_choreo.get(key)
    if salvata and salvata[0] == firma:
        return salvata[1]

    analysis = _analysis_cache[key]['analysis']
    marker_times = list(_sidecar_markers.get(key) or ())
    if marker_times:
        motore = gen.sidecar_engine()
        azioni = motore.build_choreography(
            analysis, marker_times, preset=_choreo.DEFAULT_PRESET,
            mode=_sidecar_mode.get(key) or motore.MODE_HARMONIZE,
            exclude_obstacles=bool(_sidecar_exclude.get(key, False)),
            correct_imprecision=True,
            min_gap_s=((_sidecar_min_gap_ms.get(key) or 170) / 1000.0))
    else:
        azioni = _choreo.build_move_actions(analysis, preset=_choreo.DEFAULT_PRESET)

    # Il file servito conserva l'ESTENSIONE ORIGINALE (_aggiungi_audio copia
    # "nome.mp3" come "nome.mp3"): forzare ".wav" qui produceva un percorso
    # a un file inesistente, e nel visualizzatore premere play non faceva
    # partire nulla - senza errori, perche' l'audio semplicemente non c'era.
    servito = _song_paths.get(key)
    nome_audio = os.path.basename(servito) if servito else (key + '.wav')
    wav = os.path.join(_work_dir or '', nome_audio).replace(chr(92), '/')
    action_list = _choreo.serialize_actions(azioni, key, analysis['bpm'], wav)
    _anteprima_choreo[key] = (firma, action_list)
    return action_list


def _aggiungi_audio(percorsi):
    """Copia nella cartella di servizio gli audio indicati e li registra.

    Nucleo condiviso fra "Aggiungi brani +" e il trascinamento: l'originale
    non viene mai spostato ne' modificato, si copia e basta.
    """
    import shutil
    aggiunti = []
    for src in percorsi or []:
        if not src.lower().endswith(AUDIO_EXTS):
            continue
        fn = os.path.basename(src)
        dest = os.path.join(_work_dir, fn)
        try:
            if os.path.abspath(src) != os.path.abspath(dest):
                shutil.copy2(src, dest)
        except OSError:
            continue
        key = os.path.splitext(fn)[0]
        _song_paths[key] = dest
        if key not in _active_ids:
            _active_ids.append(key)
        aggiunti.append(key)
    return aggiunti


def su_trascinamento(percorsi):
    """Chiamata da pywebview quando si lasciano cadere file sulla pagina."""
    import trascina
    file = trascina.espandi(percorsi, AUDIO_EXTS)
    if not file:
        return
    _aggiungi_audio(file)
    try:
        webview.windows[0].evaluate_js('loadList && loadList()')
    except Exception:
        pass



def _cartelle_audio(extra=None):
    """Tutte le cartelle dove il wav di un brano puo' trovarsi.

    Non basta `TEST_DIR/generati`: la generazione scrive nella cartella
    scelta in quel momento, registrata in `_ultima_generazione['folder']`.
    Cercare in una sola faceva dire "audio non disponibile" per un file che
    esisteva - solo altrove.
    """
    fuori = []
    if extra:
        fuori.append(extra)
    ultima = _ultima_generazione.get('folder')
    if ultima:
        fuori.append(ultima)
    try:
        fuori.append(os.path.join(TEST_DIR, 'generati'))
    except Exception:
        pass
    if _work_dir:
        fuori.append(_work_dir)
    # senza doppioni, mantenendo l'ordine
    viste, ordinate = set(), []
    for c in fuori:
        if c and c not in viste and os.path.isdir(c):
            viste.add(c)
            ordinate.append(c)
    return ordinate


def _percorso_audio(track_id, cartella_generati=None):
    """Dove sta il wav di questo brano, se esiste ancora.

    Si guarda in tre posti, nell'ordine in cui e' ragionevole trovarlo:
    accanto alla coreografia generata, nella cartella di servizio (dove
    l'anteprima lo copia), e infine fra i brani in elenco - un brano
    analizzato ma non ancora generato suona dal proprio file di partenza.
    """
    candidati = []
    for cartella in _cartelle_audio(cartella_generati):
        # l'id puo' gia' portare l'estensione (per un brano solo analizzato
        # e' il nome del file), oppure essere un hash a cui aggiungerla
        candidati.append(os.path.join(cartella, track_id))
        for est in ('.wav', '.mp3', '.flac', '.ogg', '.m4a'):
            if not track_id.lower().endswith(est):
                candidati.append(os.path.join(cartella, track_id + est))
    sorgente = _song_paths.get(track_id)
    if sorgente:
        candidati.append(sorgente)
    for p in candidati:
        if p and os.path.isfile(p):
            return p
    return None


def _audio_disponibile(track_id, cartella_generati=None):
    return _percorso_audio(track_id, cartella_generati) is not None



def _chiedi_cartella_gioco():
    """Apre il selettore di cartelle su BoxVR e ricorda la scelta.

    Ritorna il percorso scelto (valido) o None. Non solleva mai: se non
    c'e' una finestra aperta - per esempio durante un test - si limita a
    rispondere None.
    """
    try:
        import boxvr_patch
        import percorsi
        if not webview.windows:
            return None
        scelta = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        if not scelta:
            return None
        cartella = scelta[0] if isinstance(scelta, (list, tuple)) else scelta
        if not boxvr_patch.looks_like_game_dir(cartella):
            return None
        percorsi.salva_impostazione('game_dir', cartella)
        return cartella
    except Exception:
        return None


def assicura_repertorio(chiedi=False):
    """Il repertorio di pattern, estratto dal gioco dell'utente se manca.

    Non e' spedito dentro l'eseguibile - e' contenuto di FitXR - e va
    ricavato dalla propria copia installata. Il codice per farlo esisteva
    gia', ma girava SOLO applicando la patch: chi l'aveva applicata prima
    non aveva mai ottenuto il file, e senza quel file la coreografia non si
    costruisce. Ritorna (True, '') se c'e' o e' stato estratto, altrimenti
    (False, motivo).
    """
    try:
        import boxvr_choreo as _ch
        percorso = _ch._find_vocabulary()
        if percorso and os.path.isfile(percorso):
            return True, ''
    except Exception:
        pass
    try:
        import boxvr_extract
        import boxvr_patch
        # PRIMA la cartella che l'utente ha gia' indicato (Dashboard ->
        # "Scegli cartella..."), salvata in settings.json: e' una scelta
        # esplicita, e vale piu' di una scansione. Solo dopo si prova a
        # rilevare il gioco fra le librerie Steam. Guardando solo
        # l'autorilevamento, chi ha BoxVR fuori da Steam risultava "senza
        # gioco" pur avendocelo indicato.
        gioco = None
        try:
            import percorsi
            scelta = percorsi._settings().get('game_dir')
            if scelta and boxvr_patch.looks_like_game_dir(scelta):
                gioco = scelta
        except Exception:
            pass
        if not gioco:
            gioco = boxvr_patch.autodetect_game_dir()
        if not gioco and chiedi:
            # Non si trova: lo si CHIEDE, invece di rimandare l'utente a
            # cercare un comando in un'altra schermata. La scelta si salva,
            # cosi' la domanda si fa una volta sola.
            gioco = _chiedi_cartella_gioco()
        if not gioco:
            return False, ('BoxVR non e\' stato trovato sul computer. Il '
                           'repertorio di pattern si ricava dalla tua copia '
                           'del gioco: indica la cartella di installazione di '
                           'BoxVR dalla Dashboard, con "Scegli cartella".')
        ok, msg = boxvr_extract.write_training_sequences(gioco)
        if not ok:
            return False, (str(msg) + ' Controlla che la cartella indicata '
                           'sia davvero quella di BoxVR.')
        return True, ''
    except Exception as e:
        return False, '%s: %s' % (type(e).__name__, e)


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
        """STESSA chiave/default della GUI Tkinter vera (DEFAULT_SETTINGS['theme']
        = 'dark' in boxvr_fixer_gui.py, letta via ctk.set_appearance_mode) -
        non un default separato inventato per il port. STESSO settings.json
        di game_dir/sidecar_bias, condiviso fra le 3 pagine (un cambio da
        una si riflette sulle altre, come nella GUI vera)."""
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

    # -- sidecar/marker ("Blocco Marker" del wireframe) - vedi il blocco di
    # commenti sopra _sidecar_markers per il contesto. Un solo brano alla
    # volta puo' registrare (_sidecar_recording_key globale), stessa
    # limitazione della GUI vera (un solo SongPlayer alla volta).
    @staticmethod
    def _conta_scartati(marker, soglia_s):
        """Quanti marker cadono entro la soglia dal precedente sopravvissuto.

        Stessa regola del motore (`min_gap_s`): si scorre in ordine e si
        tiene il primo, poi si scarta tutto cio' che gli sta troppo vicino;
        il confronto riparte dall'ultimo TENUTO, non dall'ultimo visto -
        altrimenti tre marker ravvicinati ne perderebbero uno solo invece
        di due.
        """
        if not marker or soglia_s <= 0:
            return 0
        ordinati = sorted(marker)
        tenuto = ordinati[0]
        scartati = 0
        for t in ordinati[1:]:
            if t - tenuto < soglia_s:
                scartati += 1
            else:
                tenuto = t
        return scartati

    def get_sidecar_state(self, key):
        data = _load_settings()
        return {
            'markers': list(_sidecar_markers.get(key) or []),
            'mode': _sidecar_mode.get(key, 'harmonize'),
            'exclude_obstacles': _sidecar_exclude.get(key, False),
            'min_gap_ms': _sidecar_min_gap_ms.get(key),
            # Quanti marker la soglia sta scartando ADESSO. La regola e'
            # quella del motore: due marker piu' vicini della soglia si
            # fondono e sopravvive il primo. Finora il numero non si vedeva
            # da nessuna parte: si spostava il cursore senza sapere quanto
            # costava, e a soglia alta si perdevano colpi in silenzio.
            'scartati': _marker_scartati(key),
            # Quanto brano e' stato marcato davvero, e se basta a «Estendi»
            # per imparare qualcosa (engine.EXTEND_MIN_COVERAGE_S). Senza
            # questo la soglia sarebbe una regola invisibile: si marca meno
            # del minimo, si sceglie «Estendi» e si ottiene una coreografia
            # normale senza capire perche'.
            'copertura': _copertura(key),
            'bias_s': data.get('sidecar_bias_s', 0.0),
            'bias_n': data.get('sidecar_bias_n', 0),
            'recording': _sidecar_recording_key == key,
        }

    def sidecar_start_record(self, key, position_s):
        """'Registra' - punch-in dalla posizione corrente: i marker DA
        QUEL PUNTO IN POI (istante corrente incluso) vengono scartati - si
        sta per ri-registrarli - quelli PRIMA restano intatti. Porta 1:1
        boxvr_fixer_gui._sidecar_toggle_record (ramo 'start')."""
        global _sidecar_recording_key
        cutoff = max(0.0, float(position_s))
        _sidecar_markers[key] = [t for t in (_sidecar_markers.get(key) or []) if t < cutoff]
        _sidecar_recording_key = key
        return self.get_sidecar_state(key)

    def sidecar_stop_record(self, key):
        """'Ferma' - mette in pausa la registrazione E impara la
        calibrazione personale (_learn_sidecar_bias) su quanto appena
        marcato, esattamente come la GUI vera (a fine registrazione, non
        per singolo marker)."""
        _scarta_anteprima()   # i marker cambiano la coreografia
        global _sidecar_recording_key
        if _sidecar_recording_key == key:
            _sidecar_recording_key = None
        _learn_sidecar_bias(key)
        return self.get_sidecar_state(key)

    def sidecar_mark(self, key, raw_position_s):
        """'Marca' (bottone o scorciatoia F/K) - registra SOLO l'istante,
        mai corsia/tipo di colpo (li decide il motore). `raw_position_s` e'
        `audio.currentTime` del browser (posizione grezza, non ancora
        compensata) - la compensazione (bias, appreso da sessioni precedenti
        su QUESTA macchina, mai un numero fisso inventato qui) si applica
        qui, stessa idea di audible_position_seconds()/bias della GUI vera
        adattata alla pipeline audio del browser."""
        _scarta_anteprima()   # i marker cambiano la coreografia
        if _sidecar_recording_key != key:
            return {'ok': False, 'error': 'Registrazione non attiva per questo brano.'}
        bias = _load_settings().get('sidecar_bias_s', 0.0)
        t = max(0.0, float(raw_position_s) - bias)
        _sidecar_markers.setdefault(key, []).append(t)
        return {'ok': True, **self.get_sidecar_state(key)}

    def sidecar_clear(self, key):
        """'Cancella' - solo i marker, non le altre impostazioni sidecar."""
        _scarta_anteprima()   # i marker cambiano la coreografia
        global _sidecar_recording_key
        _sidecar_markers[key] = []
        if _sidecar_recording_key == key:
            _sidecar_recording_key = None
        return self.get_sidecar_state(key)

    def sidecar_reset(self, key):
        """'Resetta' - torna ai default dell'intera sezione sidecar per
        questo brano (marker, modalita', esclusione ostacoli, gap minimo),
        non solo i marker come 'Cancella'."""
        _scarta_anteprima()   # i marker cambiano la coreografia
        global _sidecar_recording_key
        _sidecar_markers[key] = []
        _sidecar_mode.pop(key, None)
        _sidecar_exclude.pop(key, None)
        _sidecar_min_gap_ms.pop(key, None)
        if _sidecar_recording_key == key:
            _sidecar_recording_key = None
        return self.get_sidecar_state(key)

    def sidecar_set_mode(self, key, mode):
        _scarta_anteprima()   # i marker cambiano la coreografia
        if mode not in ('markers_only', 'harmonize', 'extend'):
            return {'ok': False, 'error': 'Modalita non valida.'}
        _sidecar_mode[key] = mode
        return {'ok': True, **self.get_sidecar_state(key)}

    def sidecar_set_exclude_obstacles(self, key, value):
        _scarta_anteprima()   # i marker cambiano la coreografia
        _sidecar_exclude[key] = bool(value)
        return self.get_sidecar_state(key)

    def sidecar_set_min_gap_ms(self, key, ms):
        _scarta_anteprima()   # i marker cambiano la coreografia
        _sidecar_min_gap_ms[key] = float(ms) if ms not in (None, '') else None
        return self.get_sidecar_state(key)

    def list_songs(self):
        """Come correggi_real.list_songs: l'identita' (tag ID3, veloce) piu'
        `analysis_status`/`bpm` (dati REALI da get_design_context su
        "Pannello brani": nel reale ogni riga mostra BPM/stato analisi, non
        solo quella selezionata - scelta esplicita dell'utente 31/08 sera,
        consapevole che significa analizzare TUTTI i brani in background
        appena entrano in lista, non solo alla selezione come prima).
        `analysis_status` e' 'pending'/'done'/'error' da _analysis_status
        (thread avviato da _start_background_analysis in _init_songs/
        add_files) - questa funzione stessa resta leggera, non aspetta né
        avvia analisi. `preset`/`has_sidecar` per il pallino colorato della
        riga (vedi _preset_from_ratio_pct) - il pallino si spegne quando il
        brano ha marker sidecar attivi (chiarito dall'utente: "non
        comunicano nulla" in quel caso, il preset non guida piu' la
        coreografia)."""
        out = []
        for i, key in enumerate(_active_ids):
            item = gen.read_generate_item(_song_paths[key])
            # La CACHE e' il fatto; _analysis_status e' solo contabilita'.
            #
            # Prima si leggeva solo _analysis_status, con 'pending' come
            # valore di scorta: un brano analizzato per la selezione
            # (get_song_detail -> get_analysis, che riempie _analysis_cache
            # ma non scrive lo stato) restava 'pending' PER SEMPRE. In
            # interfaccia si vedeva il BPM nell'anteprima e insieme la
            # rotella dell'analisi sulla sua riga, che girava all'infinito -
            # e il frontend continuava a interrogare l'API ogni 1.5s senza
            # che quel giro potesse mai finire.
            #
            # Stessa cosa per una chiave mai registrata: valeva 'pending'
            # anche se nessuno aveva avviato niente. Ora, se manca, l'analisi
            # si avvia davvero, cosi' la rotella dice la verita'.
            if key in _analysis_cache:
                status = 'done'
            else:
                status = _analysis_status.get(key)
                if status is None:
                    _start_background_analysis(key)
                    status = 'pending'
            bpm = None
            if status == 'done' and key in _analysis_cache:
                beats = _analysis_cache[key]['analysis']['beats']
                bpm = round(beats[0]['_bpm']) if beats else 0
            out.append({
                'id': key, 'idx': f"{i + 1:02d}", 'name': item['name'], 'artist': item['artist'],
                'preset': _preset_from_ratio_pct(_get_ratio_pct(key)),
                'ratio_pct': _get_ratio_pct(key),
                'has_sidecar': bool(_sidecar_markers.get(key)),
                'analysis_status': status, 'bpm': bpm,
            })
        return out

    def retry_analysis(self, key):
        """"Riprova" della riga (Song Info Card, stato "Analisi fallita" -
        dati REALI da get_design_context su Pannello brani). Invalida SOLO
        lo stato/cache di questo brano e riavvia il thread - stesso
        meccanismo di _start_background_analysis, non una funzione diversa."""
        _analysis_cache.pop(key, None)
        _analysis_status.pop(key, None)
        _start_background_analysis(key)
        return {'ok': True}

    def clear_list(self):
        """Come correggi_real.clear_list - MAI distruttivo, nessun file toccato."""
        _active_ids.clear()
        return {'n_songs': 0}

    def remove_song(self, key):
        """Come correggi_real.remove_song - rimuove solo da _active_ids."""
        if key in _active_ids:
            _active_ids.remove(key)
        return {'n_songs': len(_active_ids)}

    def add_files(self):
        """"Aggiungi brani +" - selettore file nativo su audio (.mp3/.wav),
        non su .trackdata.txt come in Correggi: in modalita' Genera non
        serve un file "compagno" (read_generate_item e' sempre valido,
        a differenza di read_correct_item). File copiati (mai spostati)
        nella cartella di servizio, come in correggi_real."""
        window = webview.windows[0]
        paths = window.create_file_dialog(
            webview.FileDialog.OPEN, allow_multiple=True,
            file_types=('File audio (*.mp3;*.wav)', 'Tutti i file (*.*)'))
        if not paths:
            return {'added': [], 'errors': []}
        import shutil
        added = []
        for src_path in paths:
            if not src_path.lower().endswith(AUDIO_EXTS):
                continue
            fn = os.path.basename(src_path)
            dest = os.path.join(_work_dir, fn)
            shutil.copy2(src_path, dest)
            _song_paths[fn] = dest
            _analysis_cache.pop(fn, None)
            _analysis_status.pop(fn, None)
            if fn not in _active_ids:
                _active_ids.append(fn)
            _start_background_analysis(fn)
            added.append(fn)
        return {'added': added, 'errors': []}

    def get_song_detail(self, key):
        """Analisi VERA da zero (analyze_for_generate: sceglie librosa/madmom
        come la GUI vera) + classificazione VERA (classify_segments_for_generation,
        vedi nota sopra sul perche' non e' quella di Correggi) - non dati finti.
        `engine_used`/`suspicious` esposti perche' sono un'informazione reale
        gia' calcolata, non solo un dettaglio interno."""
        # Non si aspetta piu' l'analisi: se non c'e' si risponde subito
        # "non pronta", e l'interfaccia si mette nello stato disabilitato
        # invece di congelarsi. L'identita' del brano (nome, artista,
        # impostazioni) si puo' dare comunque - e' cio' che serve per
        # popolare l'intestazione mentre si aspetta.
        result = analisi_se_pronta(key)
        if result is None:
            item = gen.read_generate_item(_song_paths[key])
            return {
                'id': key, 'audio_file': os.path.basename(_song_paths[key]),
                'name': item['name'], 'artist': item['artist'],
                'analisi': stato_analisi(key),
                'ratio_pct': _get_ratio_pct(key),
                'epm_hint': _epm_hint(_get_ratio_pct(key)),
                'engine_choice': _engine_choice.get(key),
                'forced_bpm': _forced_bpm.get(key),
            }
        ratio_pct = _get_ratio_pct(key)
        segments, counts = self._classify(result['analysis'], ratio_pct)
        analysis = result['analysis']
        beats = analysis['beats']
        bpm = beats[0]['_bpm'] if beats else 0.0
        return {
            'id': key, 'audio_file': os.path.basename(_song_paths[key]),
            'analisi': 'done',
            'name': analysis['name'], 'artist': analysis['artist'],
            'bpm': round(bpm), 'duration': analysis['duration'],
            'segments': segments,
            'counts': {LEVEL_CLASS[k]: v for k, v in counts.items()},
            'n_segments': len(analysis['segs']),
            'engine_used': result['engine_used'], 'suspicious': result['suspicious'],
            'ratio_pct': ratio_pct, 'epm_hint': _epm_hint(ratio_pct),
            # BPM/motore manuali ("matita"/"Precisa-Veloce" nel wireframe) -
            # None/assente = rilevato automaticamente, non ancora forzato
            'forced_bpm': _forced_bpm.get(key),
            'engine_choice': _engine_choice.get(key),
            # tempi reali dei beat automatici (secondi) - solo per disegnare la
            # griglia "BPM RANGE" di riferimento nel pannello sidecar/marker,
            # confronto visivo, nessun dato nuovo (gia' in analysis['beats'])
            'beat_times': [b['_triggerTime'] for b in beats],
            # toggle "Base beat"/"Curva di carica" della waveform (Genera.svg/
            # Correggi.svg) - stessi beat_times sopra per "Base beat";
            # "Curva di carica" e' bar_score (curva di energia continua,
            # gia' calcolata battuta per battuta - vedi boxvr_choreo.py:
            # "la coreografia si decide direttamente dalla CURVA DI ENERGIA
            # CONTINUA del brano"), normalizzata 0-1 su questo brano, mai
            # ricalcolata qui
            'energy_curve': _energy_curve(analysis),
            # Spettro/waveform reale (segnalato mancante) - vedi _waveform_peaks
            'waveform_peaks': _waveform_peaks(analysis),
            # "Struttura BoxVR di partenza" (striscia in fondo alla waveform,
            # presente anche in Genera.svg - stesso componente/etichetta di
            # Correggi, dove mostra il livello ORIGINALE del gioco. Qui un
            # brano nuovo non ha un "originale" da mostrare: interpretazione
            # ragionevole, non confermata dall'utente - il "punto di
            # partenza" e' la classificazione al default (50%, PUNCH_RATIO),
            # calcolata una volta sola come in Correggi (mai ricalcolata
            # quando l'utente muove lo slider), cosi' resta un vero confronto
            # prima/dopo invece di duplicare la waveform principale.
            'default_segments': self._classify(analysis, PUNCH_RATIO * 100)[0],
        }

    def set_forced_bpm(self, key, bpm):
        """Matita accanto al BPM nel wireframe ("Inserire BPM") - forza il
        BPM invece di quello rilevato, invalida la cache e RIANALIZZA da
        zero (generate_song_analysis lo passa a detect_beats_and_bars, che
        ricalcola la griglia di beat da quel tempo - non e' solo
        un'etichetta, cambia il beat-tracking vero)."""
        try:
            bpm = float(bpm)
        except (TypeError, ValueError):
            return {'ok': False, 'error': 'BPM non valido.'}
        if bpm <= 0:
            return {'ok': False, 'error': 'Il BPM deve essere un numero positivo.'}
        _forced_bpm[key] = bpm
        _invalidate_analysis(key)
        return {'ok': True, 'detail': self.get_song_detail(key)}

    def clear_forced_bpm(self, key):
        """Torna al BPM rilevato automaticamente (rimuove la sovrascrittura)."""
        _forced_bpm.pop(key, None)
        _invalidate_analysis(key)
        return {'ok': True, 'detail': self.get_song_detail(key)}

    def set_engine(self, key, engine):
        """Toggle "Analisi: Precisa/Veloce" del wireframe - Precisa=madmom,
        Veloce=librosa. Sceglierlo passa a engine_mode='manual' (niente piu'
        auto-escalation), invalida la cache e rianalizza."""
        if engine not in ('librosa', 'madmom'):
            return {'ok': False, 'error': 'Motore non valido.'}
        _engine_choice[key] = engine
        _invalidate_analysis(key)
        return {'ok': True, 'detail': self.get_song_detail(key)}

    def open_bpm_search(self, key):
        """Icona "globo" del wireframe - riusa boxvr_generator.bpm_search_url
        (ricerca Google pre-compilata gia' esistente, non uno scraping) e
        apre il browser di sistema dell'utente, mai un browser interno."""
        import webbrowser
        # non blocca: senza analisi non c'e' niente da cercare
        pronta = analisi_se_pronta(key)
        if pronta is None:
            return {'ok': False, 'analisi': stato_analisi(key),
                    'error': 'Analisi del brano non ancora pronta.'}
        analysis = pronta['analysis']
        url = gen.bpm_search_url(analysis['name'], analysis['artist'])
        webbrowser.open(url)
        return {'ok': True, 'url': url}

    @staticmethod
    def _classify(analysis, ratio_pct):
        # NON fixer.classify_segments_with_preset (quella e' la politica a soglie
        # percentili di Correggi, pensata per segmenti gia' classificati dal
        # gioco) - qui i segmenti sono generati da zero e non hanno un livello
        # originale a cui tornare, quindi serve la politica dedicata a budget
        # di durata (vedi il suo docstring) - trovato SOLO provando a
        # riusare quella sbagliata su un'analisi vera e vedendo un KeyError
        # reale (mancano silence_thresh/t33/t66, mai presenti in questo
        # percorso), non per lettura del codice.
        punch_ratio = max(0.0, min(1.0, ratio_pct / 100.0))
        level_map = gen.classify_segments_for_generation(analysis, punch_ratio)
        segs = analysis['segs']
        segments, counts = [], {0: 0, 1: 0, 2: 0, 3: 0}
        for i, s in enumerate(segs):
            level = level_map.get(i, s['_energyLevel'])
            counts[level] += 1
            segments.append({
                'level': LEVEL_CLASS.get(level, 'silenzio'),
                'weight': max(0.01, fixer._segment_duration(analysis, s)),
            })
        return segments, counts

    def run_generation(self, name, max_minutes=None):
        """"Avvia generazione" VERO del port - **CORREZIONE ARCHITETTURALE**
        (31/08 pomeriggio, dopo chiarimento esplicito dell'utente): la vera
        GUI Tkinter (`_run_worker`, boxvr_fixer_gui.py ~4830) non genera un
        brano alla volta - un solo click processa TUTTA la lista in un solo
        `boxvr_generator.generate_songs(items, ...)`, che scrive SEMPRE
        almeno una playlist (spezzata in piu' file numerati solo se
        `max_playlist_minutes` e' valorizzato - MAI un'azione separata).
        La versione precedente di questo metodo genera-va un solo brano
        selezionato e delegava l'unione ad un bottone "Unifica playlist" a
        parte - sbagliato, quel bottone nella vera UX serve invece ad
        allineare le impostazioni fra i brani (vedi `apply_ratio_to_all`).

        Riusa `beat_engine`/`boundary_bars` dall'analisi gia' in cache per
        OGNI brano (stesso motivo di sempre: il segmentatore strutturale non
        e' deterministico, senza boundary_bars il file scritto differirebbe
        da quanto visto in anteprima) - per un brano mai aperto in anteprima
        l'analisi parte qui per la prima volta (stesso costo che avrebbe
        comunque avuto, solo posticipato)."""
        name = (name or '').strip()
        if not name:
            return {'ok': False, 'error': 'Nome playlist necessario.'}
        if not _active_ids:
            return {'ok': False, 'error': 'Nessun brano nell\'elenco.'}
        output_folder = os.path.join(TEST_DIR, 'generati')
        log_lines = []
        items = []
        for key in _active_ids:
            result = get_analysis(key)
            analysis = result['analysis']
            items.append({
                'audio_path': _song_paths[key],
                'ratio': max(0.0, min(1.0, _get_ratio_pct(key) / 100.0)),
                'forced_bpm': _forced_bpm.get(key),
                'beat_engine': result['engine_used'],
                'boundary_bars': analysis.get('seg_boundary_bars'),
                # sidecar/marker (vedi Api.sidecar_*) - marker_times vuoto/assente
                # non attiva nulla in generate_track (mai marker->None->build_move_actions
                # normale), esattamente come per un brano mai marcato a mano
                'marker_times': _sidecar_markers.get(key) or None,
                'sidecar_mode': _sidecar_mode.get(key),
                'exclude_obstacles': _sidecar_exclude.get(key, False),
                'min_gap_ms': _sidecar_min_gap_ms.get(key),
            })
        try:
            out = gen.generate_songs(
                items, output_folder, playlist_name=name, max_playlist_minutes=max_minutes,
                log=log_lines.append)
        except Exception as e:
            log_lines.append(f"ERRORE non gestito: {e}")
            return {'ok': False, 'error': str(e), 'log': '\n'.join(log_lines)}
        # track_ids <-> _active_ids si corrispondono per ordine SOLO se
        # nessun brano e' fallito (generate_songs salta i falliti senza
        # dire quale indice era) - senza questa garanzia costruire la mappa
        # sarebbe un abbinamento indovinato, non un dato reale
        if out['n_errors'] == 0:
            for key, track_id in zip(_active_ids, out['track_ids']):
                _track_song_key[track_id] = key
        # Ricordo cosa e' stato appena scritto: e' quello che
        # install_preview/install_run installeranno. Solo i brani di QUESTA
        # sessione, non tutta la cartella di output (che non viene mai
        # ripulita) - stesso accorgimento della GUI Tkinter, dove installare
        # l'intera cartella pescava anche brani di giorni prima.
        _ultima_generazione['folder'] = out['output_folder']
        _ultima_generazione['track_ids'] = list(out['track_ids'])
        # TUTTE le playlist scritte, non solo la prima: con un limite di
        # durata sono piu' d'una, ed erano proprio quelle che non arrivavano
        # in gioco.
        _ultima_generazione['playlist_paths'] = list(
            out.get('playlist_paths') or ([out['playlist_path']] if out.get('playlist_path') else []))
        return {
            'ok': out['n_errors'] == 0, 'n_ok': out['n_ok'], 'n_errors': out['n_errors'],
            'output_folder': out['output_folder'], 'playlist_path': out['playlist_path'],
            'track_ids': out['track_ids'], 'log': '\n'.join(log_lines),
        }

    def list_generated_tracks(self):
        """"Anteprima workout" del wireframe - elenca i brani DAVVERO scritti
        su disco in questa cartella di test (scansione reale della cartella,
        non uno stato di sessione a parte - stesso principio di
        open_folder/discover_songs: la cartella e' la fonte di verita'),
        piu' recenti prima. Un brano compare qui solo se ha una vera
        coreografia scritta (`generate_track` scrive SEMPRE anche
        l'actionlist accanto al trackdata, vedi il commento nel generatore
        sul bug della playlist vuota del 25/08)."""
        # I brani ANALIZZATI ma non ancora generati compaiono comunque:
        # la loro coreografia si costruisce al volo (_actionlist_anteprima),
        # ed e' la stessa che uscirebbe dalla generazione. Prima l'elenco
        # restava vuoto finche' non si generava, e per generare serviva un
        # nome playlist: l'utente non poteva vedere niente senza aver gia'
        # scritto i file.
        # Il NOME, non solo l'identificativo: nella tendina del
        # visualizzatore compariva l'hash del brano
        # ("ba9b3faf5976483a8b729c6cf7b2a...") invece del titolo, che non
        # dice niente a chi guarda.
        def _nome_di(chiave):
            percorso = _song_paths.get(chiave)
            if percorso:
                try:
                    item = gen.read_generate_item(percorso)
                    artista = (item.get('artist') or '').strip()
                    titolo = (item.get('name') or '').strip()
                    return ('%s - %s' % (artista, titolo)) if artista else titolo
                except Exception:
                    pass
            return None

        anteprime = [
            {'track_id': k, 'mtime': 0, 'anteprima': True,
             'name': _nome_di(k) or k}
            for k in _active_ids if k in _analysis_cache
        ]
        output_folder = os.path.join(TEST_DIR, 'generati')
        if not os.path.isdir(output_folder):
            return anteprime
        # SOLO i brani generati in questa sessione, non tutto cio' che la
        # cartella conserva dalle volte precedenti. Prima una generazione
        # ripetuta dello stesso brano lasciava tre voci identiche in tendina
        # e la prima proposta era un file di settimane prima, che con il
        # lavoro in corso non c'entra nulla (segnalato dall'utente). La
        # cartella non si tocca: cambia solo cosa si offre di guardare.
        di_questa_sessione = set(_ultima_generazione.get('track_ids') or [])
        out = []
        for fn in os.listdir(output_folder):
            if fn.endswith('.actionlist.json'):
                track_id = fn[:-len('.actionlist.json')]
                mtime = os.path.getmtime(os.path.join(output_folder, fn))
                # per un brano gia' generato il nome si ricava dal trackdata
                # scritto accanto, che porta originalArtist/originalTrackName
                nome = _nome_di(track_id)
                if not nome:
                    td = os.path.join(output_folder, track_id + '.trackdata.txt')
                    if os.path.isfile(td):
                        try:
                            with open(td, encoding='utf-8') as f:
                                dati = json.load(f)
                            artista = (dati.get('originalArtist') or '').strip()
                            titolo = (dati.get('originalTrackName') or '').strip()
                            nome = ('%s - %s' % (artista, titolo)) if artista else titolo
                        except Exception:
                            nome = None
                # Un brano il cui audio non esiste piu' non e'
                # un'anteprima: e' una voce morta. Restava in elenco dalle
                # sessioni precedenti, e premendo play dava "audio non
                # disponibile" - segnalato dall'utente. Si controlla PRIMA
                # di elencarlo, invece di lasciarlo scoprire a lui.
                if track_id not in di_questa_sessione:
                    continue
                if not _audio_disponibile(track_id, output_folder):
                    continue
                out.append({'track_id': track_id, 'mtime': mtime,
                            'name': nome or track_id})
        out.sort(key=lambda x: -x['mtime'])
        # generati prima (hanno un file vero), poi le anteprime dei
        # brani che non sono ancora stati generati
        gia = {o['track_id'] for o in out}
        out += [a for a in anteprime if a['track_id'] not in gia]
        return out

    # ---- pannello di tuning (pulsante Avanzate, o Ctrl+Shift+T) ----
    #
    # I valori si provano DAL VIVO, senza toccare `tuning.json`: si cambia
    # uno slider, si rigenera la coreografia (33 ms misurati) e la si vede
    # subito nel visualizzatore. Il file si scrive solo premendo Salva.
    #
    # E' l'unico modo per cercare un valore a occhio: il contratto normale
    # della tabella ("cambia il file, riavvia") va bene per una regolazione
    # ogni tanto, non per venti tentativi di fila.

    def tuning_valori(self):
        """Tutto cio' che serve al pannello: valori, limiti, provenienza."""
        try:
            import tuning
            return {'ok': True, **tuning.per_il_pannello()}
        except Exception as e:                 # noqa: BLE001
            return {'ok': False, 'error': str(e)}

    def tuning_applica(self, valori):
        """Prova dei valori senza scriverli. Ritorna cosa e' stato rifiutato."""
        try:
            import tuning
            messaggi = tuning.imposta_dal_vivo(valori or {})
            gen.sidecar_engine().rileggi_tuning()
            return {'ok': True, 'problemi': messaggi}
        except Exception as e:                 # noqa: BLE001
            return {'ok': False, 'error': str(e)}

    def tuning_azzera(self):
        """Torna a cio' che dice il file (o alla fabbrica)."""
        try:
            import tuning
            tuning.azzera_dal_vivo()
            gen.sidecar_engine().rileggi_tuning()
            return {'ok': True, **tuning.per_il_pannello()}
        except Exception as e:                 # noqa: BLE001
            return {'ok': False, 'error': str(e)}

    def tuning_salva(self):
        """Scrive su tuning.json cio' che si sta provando."""
        try:
            import tuning
            percorso = tuning.salva_su_file()
            return {'ok': True, 'percorso': percorso,
                    'messaggio': ('salvato in %s' % percorso) if percorso
                                 else 'tutti i valori sono di fabbrica: '
                                      'tuning.json rimosso'}
        except Exception as e:                 # noqa: BLE001
            return {'ok': False, 'error': str(e)}

    # ---- metodi: un assetto salvato, con un nome, che si puo' dare via ----
    #
    # Un `tuning.json` solo basta finche' si cerca UN assetto. Ma cercando
    # se ne trovano di diversi buoni per cose diverse - uno rado per i brani
    # lenti, uno fitto per i pezzi tirati - e con un file solo il secondo
    # cancella il primo.
    #
    # E servono a girare: un metodo fatto bene lo si manda a qualcuno, e se
    # regge finisce in una release. Per questo import ed export passano dal
    # selettore di file del sistema e non da una cartella nascosta: un file
    # che si sa dov'e' e' un file che si puo' allegare a un messaggio.

    def tuning_metodi(self):
        """L'elenco dei metodi e quale e' in uso."""
        try:
            import tuning
            return {'ok': True, 'metodi': tuning.elenco_metodi(),
                    'metodo': tuning.metodo_corrente()}
        except Exception as e:                 # noqa: BLE001
            return {'ok': False, 'error': str(e)}

    def tuning_carica_metodo(self, nome):
        """Applica un metodo. «Predefinito» torna ai valori di fabbrica."""
        try:
            import tuning
            problemi = tuning.carica_metodo(nome)
            gen.sidecar_engine().rileggi_tuning()
            fuori = {'ok': True, 'problemi': problemi}
            fuori.update(tuning.per_il_pannello())
            testa = tuning.intestazione_metodo(nome)
            if testa:
                fuori['intestazione'] = testa
            return fuori
        except Exception as e:                 # noqa: BLE001
            return {'ok': False, 'error': str(e)}

    def tuning_salva_metodo(self, nome, autore='', descrizione=''):
        """Scrive cio' che si sta provando come metodo con questo nome."""
        try:
            import tuning
            percorso = tuning.salva_metodo(nome, autore=autore,
                                           descrizione=descrizione)
            fuori = {'ok': True, 'percorso': percorso,
                     'messaggio': 'metodo «%s» salvato' % nome}
            fuori.update(tuning.per_il_pannello())
            return fuori
        except Exception as e:                 # noqa: BLE001
            return {'ok': False, 'error': str(e)}

    def tuning_elimina_metodo(self, nome):
        try:
            import tuning
            tolto = tuning.elimina_metodo(nome)
            gen.sidecar_engine().rileggi_tuning()
            fuori = {'ok': True,
                     'messaggio': ('metodo «%s» eliminato' % nome) if tolto
                                  else "non c'era niente da eliminare"}
            fuori.update(tuning.per_il_pannello())
            return fuori
        except Exception as e:                 # noqa: BLE001
            return {'ok': False, 'error': str(e)}

    def tuning_importa_metodo(self):
        """Prende un metodo da un file scelto col selettore del sistema."""
        try:
            import tuning
            window = webview.windows[0]
            scelti = window.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=False,
                file_types=('Metodo di tuning (*.json)', 'Tutti i file (*.*)'))
            if not scelti:
                return {'ok': True, 'annullato': True}
            percorso = scelti[0] if isinstance(scelti, (list, tuple)) else scelti
            nome, avvisi = tuning.importa_metodo(percorso)
            if nome is None:
                return {'ok': False, 'error': ' · '.join(avvisi)}
            # importato E applicato: chi apre un metodo lo vuole vedere
            # all'opera, non trovarselo in un elenco da scegliere di nuovo
            tuning.carica_metodo(nome)
            gen.sidecar_engine().rileggi_tuning()
            fuori = {'ok': True, 'nome': nome, 'avvisi': avvisi,
                     'messaggio': 'importato «%s»' % nome}
            fuori.update(tuning.per_il_pannello())
            return fuori
        except Exception as e:                 # noqa: BLE001
            return {'ok': False, 'error': str(e)}

    def tuning_esporta_metodo(self, nome):
        """Salva un metodo dove dice l'utente, per mandarlo a qualcuno."""
        try:
            import tuning
            window = webview.windows[0]
            dove = window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename='%s.json' % nome,
                file_types=('Metodo di tuning (*.json)',))
            if not dove:
                return {'ok': True, 'annullato': True}
            percorso = dove[0] if isinstance(dove, (list, tuple)) else dove
            tuning.esporta_metodo(nome, percorso)
            return {'ok': True, 'percorso': percorso,
                    'messaggio': 'esportato in %s' % percorso}
        except Exception as e:                 # noqa: BLE001
            return {'ok': False, 'error': str(e)}

    def get_action_list(self, track_id, rigenera=False):
        """Dati REALI per il visualizzatore - legge `<track_id>.actionlist.json`
        (scritto da generate_track, formato `serialize_actions`: ogni voce ha
        `musicActionJSON` come STRINGA json annidata, non un oggetto diretto -
        va deserializzata due volte) e lo riduce a una lista piatta di eventi
        colpo/ostacolo con tempo/tipo/canale, gli stessi MoveType/MoveChannel
        REALI del gioco (MOVE_JAB=101 ecc., vedi boxvr_choreo.py) - nessuna
        rietichettatura qui, il frontend mappa direttamente quei numeri."""
        # Senza il repertorio di pattern la coreografia non si puo'
        # costruire: si prova a estrarlo dal gioco, e se non si puo' lo si
        # DICE. Prima l'anteprima restava vuota e il primo sintomo era
        # "audio non disponibile" premendo play - un messaggio che parla
        # d'altro, e che ha fatto cercare il guasto nel posto sbagliato.
        pronto, motivo = assicura_repertorio()
        if not pronto:
            return {'ok': False,
                    'error': 'Repertorio dei pattern non disponibile. '
                             + motivo}
        output_folder = os.path.join(TEST_DIR, 'generati')
        path = os.path.join(output_folder, f"{track_id}.actionlist.json")
        # `rigenera` salta il file gia' scritto e ricostruisce al volo: senza,
        # il pannello di tuning muoverebbe gli slider su una coreografia
        # congelata su disco, e non si vedrebbe cambiare niente.
        if os.path.isfile(path) and not rigenera:
            with open(path, encoding='utf-8') as f:
                raw = json.load(f)
        else:
            # Non ancora generato: si costruisce la coreografia al volo, con
            # le stesse funzioni della generazione vera. Niente file scritti.
            # `rigenera` arriva dal pannello di tuning, e li' l'attesa e'
            # di vedere l'effetto dello slider: se l'analisi manca la si
            # calcola invece di rifiutare. Senza questo, sui brani gia'
            # generati - cioe' quelli che la tendina elenca - nessuno
            # slider faceva niente.
            raw = _actionlist_anteprima(track_id, calcola_analisi=bool(rigenera))
            if raw is None:
                return {'ok': False,
                        'error': 'Analisi del brano non disponibile: '
                                 'aggiungi il brano nella pagina Genera '
                                 'per poterne regolare la coreografia.'}
        events = []
        bpm, wav_path, duration = 0.0, None, 0.0
        for action in raw.get('actionList', []):
            payload = json.loads(action['musicActionJSON'])
            atype = payload.get('musicActiontype')
            if atype == 2:  # ACT_BPM
                bpm = payload.get('segmentBPM', 0.0)
            elif atype == 3:  # ACT_AUDIO
                wav_path = payload.get('wavFilePath')
            elif atype == 0:  # ACT_MOVECUE
                move = payload.get('moveAction', {})
                t = payload.get('startTime', 0.0)
                duration = max(duration, t)
                events.append({
                    'time': t, 'moveType': move.get('moveType'), 'moveChannel': move.get('moveChannel'),
                })
        # "tutti quelli marcati devono essere viola" (chiarito dall'utente
        # 31/08 sera sul nuovo export del visualizzatore) - un evento e'
        # "marcato" se cade vicino (entro min_gap_ms, o il default motore
        # 170ms se non impostato) a uno dei marker sidecar REALI del brano
        # sorgente. Solo una vicinanza temporale, non un dato salvato
        # altrove - l'actionlist scritta su disco non porta la provenienza
        # di ogni singolo evento, quindi va dedotta cosi'.
        # _track_song_key lo popola solo run_generation. Per un brano in
        # ANTEPRIMA (coreografia costruita al volo, mai scritta su disco) il
        # track_id E' GIA' la chiave del brano: senza questo ripiego la
        # mappa non trovava nulla, song_key restava None e TUTTI i colpi
        # risultavano non marcati - nel visualizzatore i colpi segnati a
        # mano si vedevano, ma del colore sbagliato.
        song_key = _track_song_key.get(track_id)
        if song_key is None and track_id in _active_ids:
            song_key = track_id
        if song_key is not None:
            markers = _sidecar_markers.get(song_key) or []
            tolerance_s = (_sidecar_min_gap_ms.get(song_key) or 170) / 1000.0
            for e in events:
                e['marked'] = any(abs(e['time'] - m) <= tolerance_s for m in markers)
        else:
            for e in events:
                e['marked'] = False
        # audio.src del browser legge dalla cartella di servizio (_work_dir),
        # mai un percorso assoluto sul filesystem - stessa disciplina di
        # add_files/load_live_library: copia (mai sposta), qui verso la
        # cartella gia' servita invece che da essa
        # L'ESTENSIONE VERA del file, non ".wav" appiccicato all'id.
        # Per un brano solo analizzato l'id e' il nome del file di partenza
        # (".../ILIA - run off.mp3"), e comporre id + ".wav" produceva
        # "ILIA - run off.mp3.wav": un mp3 servito col nome di un wav, che
        # il browser rifiuta di riprodurre. E' il motivo per cui i brani
        # nuovi non partivano.
        _sorgente = _percorso_audio(track_id, os.path.join(TEST_DIR, 'generati'))
        _est = os.path.splitext(_sorgente)[1].lower() if _sorgente else '.wav'
        if not _est:
            _est = '.wav'
        wav_name = track_id + ('' if track_id.lower().endswith(_est) else _est)
        if not _work_dir:
            # senza cartella di servizio non c'e' dove servire l'audio: gli
            # eventi si possono comunque restituire
            return {'ok': True, 'events': events, 'bpm': bpm,
                    'wav_file': None, 'duration': duration}
        served_path = os.path.join(_work_dir, wav_name)
        if not (wav_path and os.path.isfile(wav_path)):
            # il percorso scritto nella coreografia puo' non esistere piu':
            # una cartella temporanea di una sessione finita, o un file
            # cancellato. Si cerca altrove prima di rinunciare.
            wav_path = _percorso_audio(track_id,
                                       os.path.join(TEST_DIR, 'generati'))
        if wav_path and os.path.isfile(wav_path) and not os.path.isfile(served_path):
            import shutil
            shutil.copy2(wav_path, served_path)
        if not os.path.isfile(served_path):
            # Meglio dirlo adesso che far premere play per scoprirlo: prima
            # si restituiva comunque il nome del file, il browser dava 404 e
            # play() veniva rifiutata con "audio non disponibile".
            return {'ok': True, 'events': events, 'bpm': bpm,
                    'wav_file': None, 'duration': duration,
                    'audio_mancante': True,
                    # dove si e' guardato: senza questo l'unica cosa che
                    # arriva e' "audio non disponibile", che non permette a
                    # nessuno di capire dov'e' il problema
                    'cercato_in': _cartelle_audio(),
                    'cercato_come': wav_name}
        # Se la coreografia e' stata costruita al volo puo' non avere una
        # voce ACT_BPM, e nella barra usciva "— BPM". Il numero c'e' gia'
        # nell'analisi del brano: si prende da li' invece di non dirlo.
        if not bpm and track_id in _analysis_cache:
            battute = _analysis_cache[track_id]['analysis'].get('beats') or []
            if battute:
                bpm = round(battute[0]['_bpm'])
        return {'ok': True, 'events': events, 'bpm': bpm, 'wav_file': wav_name, 'duration': duration}

    def apply_ratio_to_all(self, key):
        """"Unifica playlist" del wireframe (chiarito dall'utente 31/08
        pomeriggio: NON scrive file, allinea le impostazioni "unificabili"
        di tutti i brani caricati a quelle del brano selezionato - stessa
        cosa che fa gia' `_apply_preset_to_all` nella GUI Tkinter vera per
        Correggi/Genera, qui riportata 1:1 per Genera: solo punch_ratio,
        la densita' non esiste in questo wireframe (vedi nota altrove).

        "Annulla unificazione" ESISTE nel wireframe (44:4992/44:5655) e ora
        e' reale, non decorativo: prima di sovrascrivere si salva lo stato
        precedente di _settings, cosi' undo_apply_ratio puo' rimetterlo
        esattamente com'era. E' un annullamento vero e completo perche'
        questa funzione tocca SOLO _settings in memoria e non scrive nulla
        su disco - non sta inventando un undo di qualcosa di irreversibile."""
        global _ratio_undo_snapshot
        if key not in _active_ids:
            return {'ok': False, 'error': 'Brano non trovato.'}
        ratio_pct = _get_ratio_pct(key)
        _ratio_undo_snapshot = {k: _settings.get(k) for k in _active_ids}
        for k in _active_ids:
            _settings[k] = ratio_pct
        return {'ok': True, 'ratio_pct': ratio_pct, 'n_songs': len(_active_ids)}

    def undo_apply_ratio(self):
        """"Annulla unificazione" - rimette a ogni brano l'intensita' che
        aveva PRIMA dell'ultima "Unifica playlist". I brani che non avevano
        un'impostazione esplicita tornano a non averla (default), non a un
        valore inventato."""
        global _ratio_undo_snapshot
        if not _ratio_undo_snapshot:
            return {'ok': False, 'error': 'Nessuna unificazione da annullare.'}
        for k, prev in _ratio_undo_snapshot.items():
            if prev is None:
                _settings.pop(k, None)
            else:
                _settings[k] = prev
        n = len(_ratio_undo_snapshot)
        _ratio_undo_snapshot = None
        return {'ok': True, 'n_songs': n}

    def _ultimo_risultato(self):
        """(cartella di output, track id, playlist) dell'ultima generazione."""
        return (_ultima_generazione.get('folder'),
                _ultima_generazione.get('track_ids') or [],
                _ultima_generazione.get('playlist_paths') or [])

    # ---- installazione nella libreria live di BoxVR ----
    # Due passi separati (anteprima -> conferma) perche' una pagina HTML non
    # ha i dialoghi modali di Tkinter: la prima NON scrive nulla e serve a
    # mostrare conflitti e destinazione, la seconda scrive davvero.

    def install_preview(self):
        """Cosa verrebbe installato dall'ultima esecuzione. Non scrive nulla."""
        cartella, ids, playlist = self._ultimo_risultato()
        if not cartella or not ids:
            return {'ok': False, 'error': 'Non c\'e\' ancora nulla da installare: '
                                          'esegui prima l\'operazione.'}
        return installa.anteprima_installazione(cartella, ids, playlist)

    def install_run(self, salta=None, fai_backup=True):
        """Installa davvero. `salta` = track id da NON sovrascrivere."""
        cartella, ids, playlist = self._ultimo_risultato()
        if not cartella or not ids:
            return {'ok': False, 'error': 'Non c\'e\' nulla da installare.'}
        return installa.esegui_installazione(cartella, ids, salta or [],
                                            fai_backup=bool(fai_backup),
                                            playlist_paths=playlist)

    def open_game_folder(self):
        """Apre la cartella della libreria di BoxVR (era _open_boxvr_folder
        nella GUI Tkinter)."""
        return installa.apri_cartella_gioco()

    def open_folder(self, path):
        """Come correggi_real.open_folder - apre Esplora risorse solo sulla
        cartella di output vera scritta da run_generation."""
        if os.path.isdir(path):
            os.startfile(path)

    def recompute(self, key, ratio_pct):
        """Ricalcolo VERO al volo - stessa idea di correggi_real.recompute:
        l'analisi audio (lenta) resta in cache, solo la classificazione
        (veloce) rigira con l'intensita' scelta dall'utente."""
        _settings[key] = ratio_pct
        # L'impostazione si salva SEMPRE (e' una preferenza dell'utente,
        # valida anche prima dell'analisi), ma il ricalcolo dei segmenti si
        # puo' fare solo con l'analisi in mano.
        pronta = analisi_se_pronta(key)
        if pronta is None:
            return {'analisi': stato_analisi(key), 'ratio_pct': ratio_pct,
                    'epm_hint': _epm_hint(ratio_pct)}
        analysis = pronta['analysis']
        segments, counts = self._classify(analysis, ratio_pct)
        return {
            'segments': segments,
            'counts': {LEVEL_CLASS[k]: v for k, v in counts.items()},
            'n_segments': len(analysis['segs']),
            'epm_hint': _epm_hint(ratio_pct),
        }


# Il wireframe e' un canvas di 1920x1080: quella misura vale per l'AREA DI
# CONTENUTO, non per la finestra esterna, che comprende bordo e barra del
# titolo. Ma e' un OBIETTIVO, non un obbligo: se lo schermo non lo consente
# si prende quello che c'e' e la pagina si scala da sola (fitPage in
# index.html). La finestra nasce piccola e cresce fino all'area utile -
# crescere e' sicuro su qualunque schermo, nascere a 1920x1080 no.
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
    import shutil
    if work_dir is None:
        _pulisci()
        # e i risultati delle sessioni precedenti (vedi svuota_risultati):
        # qui solo quando la pagina gira da sola, perche' aperta dalla
        # Dashboard ci ha gia' pensato lei
        _svuota_risultati()
        work_dir = tempfile.mkdtemp(prefix="boxvr_genera_real_")
    # il PID di chi la usa: cosi' il prossimo avvio sa se e'
    # abbandonata, invece di aspettare sei ore
    _marca_pid(work_dir)
    for fn in discover_songs():
        shutil.copy2(os.path.join(TEST_DIR, fn), os.path.join(work_dir, fn))
    shutil.copy2(os.path.join(MOCKUPS_DIR, 'styles.css'), os.path.join(work_dir, 'styles.css'))
    # icone del "Pattern Scacchiera" di sfondo: servono come file, la pagina
    # le colora via CSS mask-image (gli SVG hanno fill="currentColor")
    assets_src = os.path.join(MOCKUPS_DIR, 'assets')
    if os.path.isdir(assets_src):
        dest = os.path.join(work_dir, 'assets')
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(assets_src, dest)
    # Suono d'impatto: lo STESSO file gia' usato dall'anteprima della GUI
    # Tkinter (assets/sfx/hit_punch.wav, campione libero Mixkit - vedi
    # assets/sfx/SOURCE.md). Copiato da li', non duplicato nel progetto:
    # una sola fonte di verita' per il campione e la sua licenza.
    sfx_src = percorsi.ASSETS_SFX
    if os.path.isdir(sfx_src):
        shutil.copytree(sfx_src, os.path.join(work_dir, 'assets', 'sfx'), dirs_exist_ok=True)
    shutil.copy2(os.path.join(os.path.dirname(__file__), 'index.html'), os.path.join(work_dir, page_name))
    return work_dir


def main():
    import shutil
    global _work_dir
    if not webview2_check.ensure_webview2_or_exit():
        return
    _work_dir = build_serving_dir()
    _init_songs()
    index_path = os.path.join(_work_dir, 'index.html')
    print(f"[genera_real] {len(_active_ids)} brani reali trovati, pagina in {index_path}")
    # Dimensione di PARTENZA volutamente prudente: _fit_client_to_wireframe
    # la porta subito dopo all'area di lavoro reale dello schermo. Nascere a
    # 1920x1080 faceva sbordare la finestra su ogni schermo piu' piccolo del
    # disegno (misurato sul test a macchina pulita: 1554x882 su un'area utile
    # di 1536x824, con la finestra sotto la barra delle applicazioni).
    window = webview.create_window("Genera (dati reali)", index_path, js_api=Api(),
                                   width=1280, height=800)
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
