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
BoxVR Level Fixer
==================
Corregge l'energyLevel dei segmenti nei file trackdata custom di BoxVR (FitXR),
confrontando quello che il gioco ha calcolato con l'energia REALE dell'audio
(bassi + volume), per rendere i livelli piu' fedeli ai saliscendi della canzone.

Come funziona (stessa logica usata in chat con Claude):
 1. Per ogni brano, cerca la coppia <trackId>.txt (o *_trackdata.txt / *.trackdata.txt) + <trackId>.wav
 2. Analizza l'audio: calcola energia bassi (<250Hz) e RMS per ogni battuta
 3. Divide l'energia del brano in 4 fasce (0=silenzio, 1, 2, 3) usando la distribuzione
    energetica del brano stesso (ogni canzone viene giudicata sulla propria scala)
 4. Corregge l'energyLevel di un segmento SOLO se il punteggio e' chiaramente oltre
    la soglia tra due fasce (margine di confidenza, default 12%) - altrimenti lo
    lascia come l'ha calcolato originariamente il gioco
 5. NON tocca mai i confini/la struttura dei segmenti, solo l'etichetta di energia

USO
---
1. Installa le dipendenze (una volta sola):
   pip install numpy scipy

2. Metti tutte le coppie <trackId>.txt + <trackId>.wav in una cartella, es. C:\BoxVR\da_correggere

3. Esegui da terminale (cmd / PowerShell):
   python boxvr_fixer.py "C:\BoxVR\da_correggere" "C:\BoxVR\corretti"

   Il primo percorso e' la cartella con i file originali, il secondo (opzionale,
   default "corretti" dentro la cartella di input) e' dove salvare i file corretti
   + il report.

4. Parametri opzionali:
   --margin 0.12     Soglia di confidenza minima per accettare una correzione
                      (piu' alta = meno correzioni ma piu' sicure)
   --dry-run         Analizza e stampa solo il log, senza scrivere i file corretti

5. Al termine troverai nella cartella di output gli stessi file .txt corretti
   (stesso nome, pronti da rimettere in TrackData di BoxVR: di solito
   %AppData%/LocalLow/FITXR/BoxVR/Playlists/TrackData). Il riepilogo delle
   correzioni fatte brano per brano resta solo nel log a schermo.

Fai sempre un backup della cartella TrackData originale prima di sovrascrivere.

Nota sul formato (vedi anche la GUI): il motore del gioco legge SOLO il valore
_energyLevel annidato dentro ogni beat (beat['_segment']['_energyLevel']), non la
_segmentList di primo livello - quindi ogni funzione che scrive una correzione deve
sempre propagare il nuovo livello anche dentro i beat coperti (vedi
_write_levels_into_structure).
"""

import argparse
import datetime
import json
import os
import shutil
import sys
import wave
import glob

try:
    import numpy as np
    from scipy.signal import butter, sosfilt
except ImportError:
    print("Mancano le dipendenze. Esegui prima: pip install numpy scipy")
    sys.exit(1)


# Percentile (tra le fasi attive di una canzone) sopra il quale una fase e' considerata
# un picco/drop "estremo" e viene sempre forzata a pugni puri ad alta ripetizione,
# indipendentemente dal preset scelto.
EXTREME_PERCENTILE = 85

# Durata massima (secondi) di un blocco continuo di fasi consecutive a livello 0
# (silenzio) tollerata dalla correzione - oltre questa soglia le fasi in eccesso in
# coda al blocco vengono promosse a 1 (leggero), cosi' anche i brani importati dal
# gioco stesso (che a volte hanno lunghi tratti a energia 0 non corretti da nessuno)
# non restano "vuoti" troppo a lungo. Vedi _limit_prolonged_silence.
MAX_SILENCE_RUN_SECONDS = 20.0

# I tre preset nominali della correzione: combinazioni dei DUE assi che esistono
# davvero (margine di confidenza + rapporto pugni/misto), non quote fisse per
# livello. La distinzione conta: quanto silenzio/leggero c'e' in un brano lo
# decide l'AUDIO (vedi classify_segments_with_preset - "fascia base 0/1 mai
# influenzata dal preset"), ed e' proprio il senso della correzione. Imporre
# quote per livello riporterebbe il difetto degli originali di BoxVR.
#
# Valori MISURATI sugli 8 brani di test (2026-08-24), non scelti a intuito:
#   preset       margine  pugni%   fasi corrette   pugni puri fra le attive
#   Leggero        0.35     30%          17%                65%
#   Medio          0.20     50%          31%                67%
#   Aggressivo     0.08     75%          40%                77%
#
# ATTENZIONE al rapporto pugni/misto: NON spazia da 0 a 100%. Le fasi sopra
# EXTREME_PERCENTILE diventano pugni puri comunque, quindi il campo reale
# misurato e' 42% (slider a 0) -> 100% (slider a 1). Va detto all'utente:
# "0%" non significa "nessun pugno puro".
CORRECTION_PRESETS = {
    'light':      {'margin': 0.35, 'punch_ratio': 0.30},
    'medium':     {'margin': 0.20, 'punch_ratio': 0.50},
    'aggressive': {'margin': 0.08, 'punch_ratio': 0.75},
}
DEFAULT_CORRECTION_PRESET = 'medium'


def _read_wav_raw(path):
    """Legge un WAV PCM e ritorna (audio float32 in [-1,1] con shape (n,) o (n,nch), sr, nch)."""
    wf = wave.open(path, 'rb')
    nch = wf.getnchannels()
    sw = wf.getsampwidth()
    sr = wf.getframerate()
    nframes = wf.getnframes()
    raw = wf.readframes(nframes)
    wf.close()
    if sw == 3:
        # 24 bit PCM (comune nell'export da DAW/software audio professionali):
        # numpy non ha un dtype nativo a 3 byte, quindi si allineano i 3 byte
        # (little-endian) nei byte ALTI di un int32 e si applica uno shift
        # aritmetico a destra di 8 bit - numpy propaga il bit di segno sugli
        # interi con segno, quindi il risultato e' il valore two's-complement a
        # 24 bit corretto (positivo o negativo), non serve gestirlo a mano.
        raw_bytes = np.frombuffer(raw, dtype=np.uint8)
        n_samples = len(raw_bytes) // 3
        raw_bytes = raw_bytes[:n_samples * 3].reshape(n_samples, 3)
        padded = np.zeros((n_samples, 4), dtype=np.uint8)
        padded[:, 1:] = raw_bytes
        audio = (padded.view('<i4').reshape(-1) >> 8).astype(np.float32)
        audio /= float(2 ** 23)
    else:
        dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sw)
        if dtype is None:
            raise ValueError(f"Formato campioni non supportato (sampwidth={sw}), serve WAV PCM 8/16/24/32 bit")
        audio = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        audio /= float(np.iinfo(dtype).max)
    if nch > 1:
        audio = audio.reshape(-1, nch)
    return audio, sr, nch


def load_wav_mono(path):
    """Audio mono (media dei canali) per l'analisi bassi/RMS."""
    audio, sr, nch = _read_wav_raw(path)
    if nch > 1:
        audio = audio.mean(axis=1)
    return audio, sr


def load_wav_for_playback(path):
    """Audio con i canali originali (non mixati), shape (n_frames, n_channels), per la riproduzione."""
    audio, sr, nch = _read_wav_raw(path)
    if audio.ndim == 1:
        audio = audio.reshape(-1, 1)
    return np.ascontiguousarray(audio, dtype=np.float32), sr


def find_track_id(filename):
    base = os.path.basename(filename)
    for suffix in ('.trackdata.txt', '_trackdata.txt', '.wav', '.txt'):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return os.path.splitext(base)[0]


def read_correct_item(txt_path):
    """Dato un .txt candidato per la modalita' Correggi, decide se e' una
    coppia valida e ne ricava l'identita' per la lista - tirato fuori da
    SongBrowserPanel._add_correct_item (boxvr_fixer_gui.py) perche' e' una
    vera decisione (valido o no? con quale nome mostrarlo?) prima
    verificabile solo aprendo la finestra e trascinandoci dentro un file.

    Ritorna None se manca il .wav corrispondente (l'unico motivo di
    invalidita': non basta un .txt, serve la coppia completa). Altrimenti un
    dict {'key', 'txt_path', 'wav_path', 'name', 'artist', 'bpm_text'} -
    nome/artista/bpm ripiegano su valori segnaposto se il JSON non e'
    leggibile o non ha quei campi, perche' un trackdata non canonico deve
    comunque comparire in lista (magari e' proprio quello da correggere),
    non sparire silenziosamente.
    """
    tid = find_track_id(os.path.basename(txt_path))
    wav_path = os.path.join(os.path.dirname(txt_path), tid + '.wav')
    if not os.path.exists(wav_path):
        return None
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            outer = json.load(f)
        name = outer.get('originalTrackName') or tid
        artist = outer.get('originalArtist') or '?'
        bpm = outer.get('bpm')
        bpm_text = f"{bpm:.0f}" if isinstance(bpm, (int, float)) else "?"
    except Exception:
        name, artist, bpm_text = tid, '?', '?'
    return {'key': tid, 'txt_path': txt_path, 'wav_path': wav_path, 'name': name, 'artist': artist,
            'bpm_text': bpm_text}


def bars_in_range(bar_start_idx, nb, start_beat, num_beats):
    end_beat = start_beat + num_beats
    return [i for i in range(nb) if start_beat <= bar_start_idx[i] < end_beat]


def bucket_energy_level(score, silence_thresh, t33, t66):
    if score <= silence_thresh:
        lvl = 0
        dist = (silence_thresh - score) / max(silence_thresh, 1e-6)
    elif score <= t33:
        lvl = 1
        dist = min(score - silence_thresh, t33 - score) / max(t33 - silence_thresh, 1e-6)
    elif score <= t66:
        lvl = 2
        dist = min(score - t33, t66 - score) / max(t66 - t33, 1e-6)
    else:
        lvl = 3
        dist = (score - t66) / max(t66 - t33, 1e-6)
    return lvl, dist


def compute_bar_score(mono_audio, sr, bar_spans):
    """Punteggio energetico (bassi+RMS) per ciascun intervallo (t0, t1) in bar_spans.

    Condiviso tra la correzione (bar_spans dai bar del trackdata originale) e la
    generazione da zero (bar_spans dai bar rilevati da librosa) - stessa identica
    formula per entrambi i percorsi.
    """
    sos_bass = butter(4, 250, btype='low', fs=sr, output='sos')
    bass_audio = sosfilt(sos_bass, mono_audio)
    nb = len(bar_spans)
    bar_rms = np.zeros(nb)
    bar_bass = np.zeros(nb)
    for i, (t0, t1) in enumerate(bar_spans):
        i0 = max(0, int(t0 * sr))
        i1 = min(len(mono_audio), int(t1 * sr))
        if i1 > i0:
            bar_rms[i] = np.sqrt(np.mean(mono_audio[i0:i1] ** 2))
            bar_bass[i] = np.sqrt(np.mean(bass_audio[i0:i1] ** 2))
    return 0.6 * bar_bass + 0.4 * bar_rms


def compute_energy_thresholds(bar_score):
    """Soglie silenzio/33simo/66simo percentile usate per bucketizzare l'energia in 4 fasce."""
    nb = len(bar_score)
    median_score = float(np.median(bar_score)) if nb else 0.0
    silence_thresh = median_score * 0.22
    nonsilent = bar_score[bar_score > silence_thresh]
    if len(nonsilent) < 6:
        nonsilent = bar_score
    if len(nonsilent) == 0:
        t33, t66 = 0.0, 0.0
    else:
        t33, t66 = np.percentile(nonsilent, [33, 66])
    return silence_thresh, t33, t66


def compute_song_analysis(txt_path, wav_path):
    """Parsa il trackdata e calcola il punteggio energetico reale per bar.

    Ritorna un dict riutilizzabile sia dalla correzione "classica" a margine singolo
    (analyze_and_fix) sia dal motore a preset (classify_segments_with_preset), cosi'
    l'analisi audio (la parte piu' lenta, per via del filtro bassi) va fatta una volta
    sola per canzone anche quando si generano piu' preset o si ricalcola dopo un cambio
    di preferenza nella GUI.
    """
    with open(txt_path, 'r', encoding='utf-8') as f:
        outer = json.load(f)
    inner = json.loads(outer['beatStrucureJSON'])
    bars = inner['_barList']['_bars']
    beats = inner['_beatList']['_beats']
    segs = inner['_segmentList']['_segments']

    audio, sr = load_wav_mono(wav_path)
    bar_spans = []
    nb = len(bars)
    bar_start_idx = np.zeros(nb, dtype=int)
    for i, b in enumerate(bars):
        t0 = b['_startTime']
        t1 = bars[i + 1]['_startTime'] if i + 1 < nb else t0 + b['_duration'] * 4
        bar_spans.append((t0, t1))
        bar_start_idx[i] = b['_beatIndex']

    bar_score = compute_bar_score(audio, sr, bar_spans)
    silence_thresh, t33, t66 = compute_energy_thresholds(bar_score)

    return {
        'outer': outer, 'inner': inner, 'bars': bars, 'beats': beats, 'segs': segs,
        'bar_score': bar_score, 'bar_start_idx': bar_start_idx, 'nb': nb,
        'silence_thresh': silence_thresh, 't33': t33, 't66': t66,
        'sr': sr, 'duration': float(outer.get('duration', 0.0)),
        'name': outer.get('originalTrackName', '?'), 'artist': outer.get('originalArtist', '?'),
    }


def _segment_duration(analysis, seg):
    """Durata (secondi) di una fase, dedotta dai beat che copre (funziona sia per i
    trackdata del gioco sia per quelli generati da zero, che condividono lo stesso
    formato di beat con _triggerTime/_beatLength)."""
    beats = analysis['beats']
    start = seg['_startBeatIndex']
    end = min(start + seg['_numBeats'], len(beats)) - 1
    if end < start or start < 0 or end >= len(beats):
        return 0.0
    b0, b1 = beats[start], beats[end]
    return max(0.0, (b1['_triggerTime'] + b1['_beatLength']) - b0['_triggerTime'])


def _limit_prolonged_silence(analysis, level_map, max_run_seconds=MAX_SILENCE_RUN_SECONDS):
    """Evita blocchi troppo lunghi di fasi consecutive a livello 0 (silenzio).

    Guarda il livello EFFETTIVO di ogni fase (quello scelto dalla correzione se
    presente in level_map, altrimenti quello gia' scritto dal gioco) - una serie di
    silenzi puo' formarsi anche da fasi che non abbiamo toccato per bassa confidenza.
    Quando un blocco consecutivo supera max_run_seconds, promuove a 1 (leggero) le
    fasi in coda al blocco finche' non rientra nel limite, aggiungendole a level_map
    anche se non erano gia' presenti. Modifica level_map in place e lo ritorna."""
    segs = analysis['segs']
    n = len(segs)
    i = 0
    while i < n:
        eff = level_map.get(i, segs[i]['_energyLevel'])
        if eff != 0:
            i += 1
            continue
        run_indices = []
        run_duration = 0.0
        j = i
        while j < n and level_map.get(j, segs[j]['_energyLevel']) == 0:
            run_indices.append(j)
            run_duration += _segment_duration(analysis, segs[j])
            j += 1
        if run_duration > max_run_seconds:
            remaining = run_duration
            for idx in reversed(run_indices):
                if remaining <= max_run_seconds:
                    break
                level_map[idx] = 1
                remaining -= _segment_duration(analysis, segs[idx])
        i = j
    return level_map


def _segment_score_and_level(analysis, seg):
    idxs = bars_in_range(analysis['bar_start_idx'], analysis['nb'], seg['_startBeatIndex'], seg['_numBeats'])
    seg_score = float(np.mean(analysis['bar_score'][idxs])) if idxs else 0.0
    proposed_level, confidence = bucket_energy_level(
        seg_score, analysis['silence_thresh'], analysis['t33'], analysis['t66'])
    return seg_score, proposed_level, confidence


def _write_levels_into_structure(inner, segs, level_map):
    """Scrive level_map ({indice_segmento: nuovo_energyLevel}) in _segmentList e la
    propaga in ogni beat coperto - il gioco legge solo la copia annidata nel beat."""
    beats = inner['_beatList']['_beats']
    beat_by_index = {b['_index']: b for b in beats}
    new_segments = []
    for i, s in enumerate(segs):
        news = dict(s)
        if i in level_map:
            news['_energyLevel'] = level_map[i]
        new_segments.append(news)
        start = s['_startBeatIndex']
        num = s['_numBeats']
        for bi in range(start, min(start + num, len(beats))):
            if bi in beat_by_index:
                beat_by_index[bi]['_segment'] = dict(news)
    inner['_segmentList']['_segments'] = new_segments
    return new_segments


def classify_segments_with_preset(analysis, margin, punch_ratio, force=False):
    """Ritorna {indice_segmento: energyLevel} per un dato rapporto pugni/misto.

    - Fasi con confidenza < margin: non toccate (nessuna voce nella mappa, il chiamante
      dovra' tenere il livello originale del gioco) - A MENO CHE force=True, nel qual
      caso si usa comunque proposed_level. force va usato quando non esiste un livello
      "originale" sensato a cui tornare (es. generazione da zero in boxvr_generator.py,
      dove il placeholder e' 0/silenzio e lasciarlo tale sui segmenti a bassa confidenza
      farebbe apparire silenziose zone con energia reale non ambigua sulla propria scala).
      Per la correzione di file esistenti (force=False, default) il comportamento resta
      invariato: preserva il valore calcolato dal gioco quando non siamo abbastanza sicuri.
    - Fasi con fascia base 0/1 (silenzio/leggero): livello base, mai influenzato dal preset.
    - Fasi con fascia base 2/3 ("attive"): entrano nel pool pugni/misto.
      - Quelle sopra l'EXTREME_PERCENTILE del punteggio energetico (i veri picchi/drop
        della canzone) diventano sempre 2 (pugni puri ad alta ripetizione).
      - Le restanti fasi attive, in ordine cronologico, vengono assegnate con uno
        scheduler proporzionale che converge a punch_ratio (frazione di 2 tra loro),
        alternando in modo fluido invece che a blocchi o casualmente.
    """
    margin = max(0.0, min(1.0, margin))
    segs = analysis['segs']

    base = []  # (indice, seg_score, proposed_level, confidence)
    for i, s in enumerate(segs):
        seg_score, proposed_level, confidence = _segment_score_and_level(analysis, s)
        base.append((i, seg_score, proposed_level, confidence))

    level_map = {}
    active = []  # (indice, seg_score) in ordine cronologico
    for i, seg_score, proposed_level, confidence in base:
        if not force and confidence < margin:
            continue
        if proposed_level in (0, 1):
            level_map[i] = proposed_level
        else:
            active.append((i, seg_score))

    level_map.update(assign_punch_misto(active, punch_ratio))
    if not force:
        # Solo in correzione (non in generazione, che ha gia' il suo budget dedicato
        # in classify_segments_for_generation): evita che restino tratti troppo lunghi
        # a energia 0, anche quando derivano da fasi lasciate intatte per bassa confidenza.
        _limit_prolonged_silence(analysis, level_map)
    return level_map


def assign_punch_misto(active, punch_ratio, extreme_percentile=EXTREME_PERCENTILE):
    """Assegna 2 (pugni) o 3 (misto) a un pool di fasi "attive" (indice, seg_score) in
    ordine cronologico. Condiviso tra la correzione (classify_segments_with_preset) e
    la generazione da zero (boxvr_generator.classify_segments_for_generation), che
    arrivano al pool "attivo" con criteri diversi ma lo trattano allo stesso modo una
    volta lì: i picchi/drop veri (sopra extreme_percentile) diventano sempre pugni puri
    ad alta ripetizione, il resto alterna in modo fluido verso punch_ratio."""
    level_map = {}
    if not active:
        return level_map
    punch_ratio = max(0.0, min(1.0, punch_ratio))
    scores = np.array([s for _, s in active])
    extreme_cut = float(np.percentile(scores, extreme_percentile))
    two_count = 0
    total = 0
    for i, seg_score in active:
        if seg_score >= extreme_cut:
            level_map[i] = 2
            continue
        if total == 0 or (two_count / total) <= punch_ratio:
            level_map[i] = 2
            two_count += 1
        else:
            level_map[i] = 3
        total += 1
    return level_map


def process_folder(input_folder, output_folder=None, margin=0.12, dry_run=False, log=print):
    """Corregge tutte le coppie <trackId>.txt + <trackId>.wav in input_folder.

    Thin wrapper attorno a process_songs_with_presets (rapporto pugni/misto di
    default 0.5, lo stesso "Equilibrato" della GUI) - CLI e GUI passano cosi'
    dallo stesso identico motore, incluso il tetto ai silenzi prolungati
    (_limit_prolonged_silence) che in precedenza veniva applicato solo dal
    percorso GUI: prima questa funzione duplicava la classificazione con la sua
    stessa logica ma senza quel tetto, producendo risultati leggermente diversi
    da CLI a GUI sulla stessa identica azione "correggi". `log` viene chiamato
    con una riga di testo per ogni evento, cosi' sia la CLI che una GUI possono
    mostrare i progressi. Ritorna un dict di riepilogo.
    """
    output_folder = output_folder or os.path.join(input_folder, 'corretti')

    txts = sorted(glob.glob(os.path.join(input_folder, '*.txt')))
    if not txts:
        os.makedirs(output_folder, exist_ok=True)
        log(f"Nessun file .txt trovato in {input_folder}")
        return {'n_ok': 0, 'n_changed': 0, 'n_total_changes': 0, 'n_errors': 0,
                'n_skipped': 0, 'output_folder': output_folder}

    items = [{'txt_path': p, 'wav_path': os.path.join(input_folder, find_track_id(os.path.basename(p)) + '.wav'),
              'tid': find_track_id(os.path.basename(p))} for p in txts]
    return process_songs_with_presets(items, output_folder, margin, dry_run, log)


def process_songs_with_presets(items, output_folder, margin=0.12, dry_run=False, log=print, in_place=False):
    """Come process_folder_with_presets, ma su una lista esplicita di brani invece di
    scansionare una singola cartella - permette alla GUI di aggregare brani trascinati
    da cartelle diverse in un'unica sessione. `items`: lista di dict con almeno
    txt_path/wav_path/tid; 'ratio' opzionale (default 0.5).

    `in_place=True`: invece di scrivere i file corretti in output_folder (che poi
    l'utente doveva spostare a mano dentro TrackData, un passaggio spaesante
    quando la cartella di partenza era gia' TrackData stessa), sovrascrive
    direttamente il file .txt originale nella sua posizione - ma solo DOPO averne
    fatto una copia di backup in "backup_correzioni/<timestamp>/" accanto
    all'originale (una sola cartella di backup con timestamp per l'intera
    sessione di correzione, non una per file, cosi' e' facile ritrovare "lo stato
    di prima di quella correzione" come unico blocco). Il wav non viene mai
    toccato dalla correzione (cambia solo l'energyLevel nel .txt), quindi non
    serve backup per quello."""
    if not in_place:
        os.makedirs(output_folder, exist_ok=True)

    if not items:
        log("Nessun brano da correggere.")
        return {'n_ok': 0, 'n_changed': 0, 'n_total_changes': 0, 'n_errors': 0,
                'n_skipped': 0, 'output_folder': output_folder, 'track_ids': []}

    n_ok = 0
    n_changed = 0
    track_ids = []
    n_total_changes = 0
    n_errors = 0
    n_skipped = 0
    backup_timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    first_backup_folder = None

    for i, item in enumerate(items, 1):
        txt_path, wav_path, tid = item['txt_path'], item['wav_path'], item['tid']
        base = os.path.basename(txt_path)
        if not os.path.exists(wav_path):
            n_skipped += 1
            log(f"[{i}/{len(items)}] SKIP {base}: wav mancante ({tid}.wav)")
            continue
        try:
            punch_ratio = item.get('ratio', 0.5)
            analysis = compute_song_analysis(txt_path, wav_path)
            segs = analysis['segs']
            level_map = classify_segments_with_preset(analysis, margin, punch_ratio)

            changes = []
            for j, s in enumerate(segs):
                new_level = level_map.get(j, s['_energyLevel'])
                if new_level != s['_energyLevel']:
                    changes.append({
                        'start_beat': s['_startBeatIndex'], 'end_beat': s['_startBeatIndex'] + s['_numBeats'] - 1,
                        'old': s['_energyLevel'], 'new': new_level,
                    })

            _write_levels_into_structure(analysis['inner'], segs, level_map)
            outer = analysis['outer']
            outer['beatStrucureJSON'] = json.dumps(analysis['inner'])
            name, artist = analysis['name'], analysis['artist']

            n_ok += 1
            if changes:
                n_changed += 1
                n_total_changes += len(changes)
            if not dry_run:
                if in_place:
                    backup_folder = os.path.join(os.path.dirname(txt_path), 'backup_correzioni', backup_timestamp)
                    os.makedirs(backup_folder, exist_ok=True)
                    if first_backup_folder is None:
                        first_backup_folder = backup_folder
                    shutil.copy2(txt_path, os.path.join(backup_folder, base))
                    dest_path = txt_path
                else:
                    dest_path = os.path.join(output_folder, base)
                track_ids.append(tid)
                with open(dest_path, 'w', encoding='utf-8') as f:
                    json.dump(outer, f)
            log(f"[{i}/{len(items)}] OK {name} - {artist} (preset {punch_ratio:.0%} pugni): {len(changes)} correzioni")
        except Exception as e:
            n_errors += 1
            log(f"[{i}/{len(items)}] ERRORE {base}: {e}")

    log(f"\nFATTO. Brani processati: {n_ok}  |  con correzioni: {n_changed}  |  "
        f"correzioni totali: {n_total_changes}  |  errori: {n_errors}  |  saltati: {n_skipped}")
    result_folder = output_folder
    if not dry_run:
        if in_place:
            log(f"File originali sostituiti sul posto. Backup dei file precedenti in: "
                f"<cartella del brano>/backup_correzioni/{backup_timestamp}/")
            result_folder = first_backup_folder or output_folder
        else:
            log(f"File corretti salvati in: {output_folder}")

    return {'n_ok': n_ok, 'n_changed': n_changed, 'n_total_changes': n_total_changes,
            'n_errors': n_errors, 'n_skipped': n_skipped, 'output_folder': result_folder,
            'track_ids': track_ids}


def main():
    parser = argparse.ArgumentParser(description="Corregge l'energyLevel dei livelli custom BoxVR in base all'audio reale.")
    parser.add_argument('input_folder', help='Cartella con le coppie <trackId>.txt + <trackId>.wav')
    parser.add_argument('output_folder', nargs='?', default=None, help='Cartella di destinazione (default: <input_folder>/corretti)')
    parser.add_argument('--margin', type=float, default=0.12, help='Confidenza minima per accettare una correzione (default 0.12)')
    parser.add_argument('--dry-run', action='store_true', help='Solo report, non scrive i file corretti')
    args = parser.parse_args()

    result = process_folder(args.input_folder, args.output_folder, args.margin, args.dry_run)
    if result['n_ok'] == 0 and result['n_skipped'] == 0 and result['n_errors'] == 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
    # Pausa finale: se lo script e' lanciato con drag&drop (o doppio click su un .bat)
    # la finestra si chiuderebbe subito dopo, senza dare tempo di leggere l'output.
    try:
        input("\nPremi INVIO per chiudere...")
    except EOFError:
        pass
