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
BoxVR Trackdata Generator
==========================
Genera da zero un trackdata.txt + wav + wdef.txt per BoxVR (FitXR) a partire
da un file audio mp3 o wav. Beat-tracking con librosa di default (veloce);
madmom (la libreria che usa BoxVR stesso) e' disponibile come motore
alternativo opzionale, piu' lento ma piu' robusto ai cambi di tempo locali -
gira come sottoprocesso esterno (madmom_worker.exe) perche' non supporta
Python 3.14, vedi detect_beats_and_bars/is_madmom_available. Stessa logica di
classificazione energia/preset gia' usata da boxvr_fixer.py per correggere
i file esistenti.

A differenza della correzione, qui i segmenti non esistono ancora: vengono
creati a blocchi contigui che coprono l'intera canzone dall'inizio alla fine,
cosi' da non lasciare buchi (il problema che BoxVR stesso a volte introduce,
lasciando intere porzioni di un brano senza nessun segmento definito).

Schema dei file scoperto ispezionando file reali generati da BoxVR su
%AppData%/LocalLow/FITXR/BoxVR/Playlists (TrackData e TrackDefinitions).
"""

import glob
import json
import os
import re
import sys
import uuid

import numpy as np
import librosa
import soundfile as sf
from scipy.signal import butter, sosfilt

from boxvr_fixer import (
    _write_levels_into_structure, compute_bar_score, bars_in_range, assign_punch_misto,
)

try:
    import mutagen
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

BEATS_PER_BAR = 4
BARS_PER_SEGMENT = 4
DATA_VERSION = 3
AUDIO_EXTENSIONS = ('.mp3', '.wav')


def decode_audio(path):
    """Legge mp3 o wav (via librosa/soundfile, nessun ffmpeg richiesto).

    Ritorna (audio_native shape (n, canali) float32 per il wav di output,
    audio_mono shape (n,) float32 per l'analisi/beat-tracking, sample rate).
    """
    native, sr = librosa.load(path, sr=None, mono=False)
    if native.ndim == 1:
        mono = native
        native_out = native.reshape(-1, 1)
    else:
        mono = librosa.to_mono(native)
        native_out = native.T
    return np.ascontiguousarray(native_out, dtype=np.float32), np.ascontiguousarray(mono, dtype=np.float32), sr


def read_tags(path):
    """Artista/titolo da tag ID3 (mutagen); fallback al nome del file."""
    fallback_title = os.path.splitext(os.path.basename(path))[0]
    artist, title = '?', fallback_title
    if HAS_MUTAGEN:
        try:
            tags = mutagen.File(path, easy=True)
            if tags is not None:
                artist = (tags.get('artist') or [artist])[0]
                title = (tags.get('title') or [title])[0]
        except Exception:
            pass
    return artist, title


def read_generate_item(audio_path):
    """Identita' per la lista di un file audio candidato per la modalita'
    Genera - tirato fuori da SongBrowserPanel._add_generate_item
    (boxvr_fixer_gui.py), stesso motivo di read_correct_item in
    boxvr_fixer.py: e' una decisione (con quale nome mostrarlo?), non
    wiring, e prima era verificabile solo trascinando un file nella finestra.

    A differenza della correzione, qui non c'e' un requisito di validita' da
    controllare (nessun file "compagno" richiesto) - ritorna sempre un dict
    {'key', 'audio_path', 'name', 'artist'}, mai None."""
    try:
        artist, title = read_tags(audio_path)
    except Exception:
        artist, title = '?', os.path.splitext(os.path.basename(audio_path))[0]
    return {'key': audio_path, 'audio_path': audio_path, 'name': title, 'artist': artist}


# Range di BPM plausibile per un brano da allenamento: sotto MIN_PLAUSIBLE_BPM il
# tempo rilevato e' quasi certamente un errore di "ottava" (vedi _correct_tempo_octave).
MIN_PLAUSIBLE_BPM = 95.0
MAX_PLAUSIBLE_BPM = 200.0


def _correct_tempo_octave(mono_audio, sr, tempo_val, beat_frames):
    """Corregge l'errore di ottava del tempo (rilevare il doppio o la meta' del
    BPM reale) in entrambe le direzioni.

    Il caso "troppo lento" e' stato scoperto confrontando un brano drum & bass
    ("Immortal") generato da questo tool con lo stesso brano importato
    direttamente da BoxVR: il nostro rilevamento dava 87.6 BPM, BoxVR stesso
    (che usa madmom, non librosa) dava 174 - esattamente il doppio. Il motivo
    e' che generi come D&B/breakbeat hanno spesso una componente ritmica "a
    meta' tempo" (halftime) cosi' forte che l'algoritmo di beat-tracking si
    aggancia a quella invece che al battito reale su cui si balla/si boxa,
    dimezzando il BPM rilevato - il risultato in gioco erano vuoti dilatati e
    colpi radi, esattamente il sintomo riportato.

    Il caso "troppo veloce" (>MAX_PLAUSIBLE_BPM) e' l'errore opposto e
    simmetrico - capita su generi molto sincopati (es. gabber/hardcore) dove
    l'algoritmo si aggancia a una sottodivisione del beat invece del beat
    stesso, raddoppiando il BPM rilevato invece di dimezzarlo - non era mai
    stato corretto prima (solo la direzione "lento" era gestita), lasciando
    quei brani con beat il doppio del reale e quindi il doppio degli eventi
    attesi.

    In entrambi i casi ritenta il beat-tracking forzando la ricerca nella
    direzione opposta (start_bpm=150 se troppo lento, start_bpm=90 se troppo
    veloce) e adotta il nuovo risultato solo se e' plausibilmente il doppio (o
    la meta') di quello originale - la direzione "lento" resta validata sugli 8
    brani di test a BPM gia' noto e corretto (tutti gia' sopra la soglia,
    quindi non toccati) piu' il caso reale di Immortal (87.6 -> 172.3, contro i
    174 di BoxVR)."""
    if MIN_PLAUSIBLE_BPM <= tempo_val <= MAX_PLAUSIBLE_BPM:
        return tempo_val, beat_frames, False
    retry_start_bpm = 150.0 if tempo_val < MIN_PLAUSIBLE_BPM else 90.0
    tempo2, beat_frames2 = librosa.beat.beat_track(y=mono_audio, sr=sr, start_bpm=retry_start_bpm)
    tempo2_val = float(tempo2) if np.isscalar(tempo2) else float(tempo2[0])
    ratio = tempo2_val / tempo_val if tempo_val > 0 else 0.0
    plausible_double = 1.7 <= ratio <= 2.3
    plausible_half = 0.435 <= ratio <= 0.59
    if MIN_PLAUSIBLE_BPM <= tempo2_val <= MAX_PLAUSIBLE_BPM and (plausible_double or plausible_half):
        return tempo2_val, beat_frames2, True
    return tempo_val, beat_frames, False


def _beats_bars_from_times(beat_times, tempo_val):
    """Costruisce le strutture _beats/_bars (stesso schema dei trackdata reali
    di BoxVR) a partire da una lista di istanti di beat gia' pronta, qualunque
    sia il motore che li ha prodotti (librosa o madmom - vedi detect_beats_and_bars).
    Fattorizzato fuori da detect_beats_and_bars perche' entrambi i motori
    arrivano a questo stesso punto (una sequenza di tempi in secondi) e da qui
    in poi il resto della pipeline non deve sapere quale motore e' stato usato."""
    if len(beat_times) < BEATS_PER_BAR:
        # Meno di una bar intera di beat rilevati (audio troppo corto, silenzioso
        # o senza un ritmo riconoscibile) produrrebbe piu' a valle bar/segmenti
        # degeneri invece di un trackdata valido - meglio fermarsi qui con un
        # errore chiaro (gia' gestito per-brano da generate_songs/_background_
        # analysis_loop, non fa cadere il resto del batch) che generare un file
        # quasi vuoto in silenzio.
        raise ValueError(
            f"Rilevati solo {len(beat_times)} beat (< {BEATS_PER_BAR}, meno di una battuta): "
            "audio troppo corto o senza un ritmo riconoscibile per generare un trackdata")

    beats = []
    for i, t in enumerate(beat_times):
        if i + 1 < len(beat_times):
            length = float(beat_times[i + 1] - t)
        else:
            length = float(beat_times[i] - beat_times[i - 1]) if i > 0 else 60.0 / tempo_val
        beats.append({
            '_index': i, '_beatInBar': (i % BEATS_PER_BAR) + 1,
            '_magnitude': 0.0, '_triggerTime': float(t), '_beatLength': length,
            '_bpm': tempo_val, '_isLastBeat': False, '_segment': None,
        })

    bars = []
    for start_beat in range(0, len(beats), BEATS_PER_BAR):
        end_beat = min(start_beat + BEATS_PER_BAR, len(beats))
        t0 = beats[start_beat]['_triggerTime']
        if end_beat < len(beats):
            t1 = beats[end_beat]['_triggerTime']
        else:
            last = beats[-1]
            t1 = last['_triggerTime'] + last['_beatLength']
        bars.append({
            '_avgEnergy': 0.0, '_duration': t1 - t0, '_startTime': t0, '_beatIndex': start_beat,
        })
    return beats, bars


# madmom (usato da BoxVR stesso, vedi il post r/vrfit citato altrove) non supporta
# Python 3.14 (questo progetto gira su 3.14, madmom si ferma a 3.12) e richiede
# Cython + un compilatore C++ per la build - impossibile importarlo direttamente
# nel processo principale. Gira invece come sottoprocesso esterno, un exe a se'
# stante compilato da un venv Python 3.10 separato (vedi madmom_worker.py e
# madmom_worker/BUILD.md) - comunica via un singolo argomento (percorso audio)
# e uno stdout JSON, cosi' i due processi non condividono nessuna dipendenza
# Python. Validato empiricamente (non solo per intuito): su 3 brani reali
# confermati "fuori sincro" ad orecchio dall'utente, il DBNBeatTrackingProcessor
# di madmom riduce lo scarto locale nei punti del problema dal 10-21% al 3-9%,
# a fronte di un costo di ~15-200x piu' lento di librosa (rete neurale su CPU) -
# vedi boxvr_generator.md in memoria per la tabella completa. Per questo resta
# un motore OPZIONALE selezionato dall'utente per singola canzone, non il default.
MADMOM_WORKER_TIMEOUT_S = 600
_MADMOM_WORKER_CACHE = {}


class MadmomUnavailableError(RuntimeError):
    """madmom_worker.exe non trovato o fallito - va sempre gestita a monte
    (GUI/CLI) ripiegando su librosa con un avviso chiaro, mai lasciata risalire
    come crash puro: l'utente ha scelto "madmom" ma il file mancante non e' un
    suo errore, ne' motivo per perdere l'intera generazione del brano."""


def _find_madmom_worker():
    """Cerca madmom_worker.exe accanto all'eseguibile principale (build
    compilata, sys.frozen) o nella cartella del progetto (esecuzione da
    sorgente) - ritorna None se non trovato, mai solleva: chi chiama decide se
    quello e' un errore fatale o un'occasione per ripiegare su librosa."""
    if 'path' in _MADMOM_WORKER_CACHE:
        return _MADMOM_WORKER_CACHE['path']
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    if getattr(sys, 'frozen', False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), 'madmom_worker.exe'))
    candidates.append(os.path.join(here, 'madmom_worker.exe'))
    candidates.append(os.path.join(here, 'madmom_worker', 'dist', 'madmom_worker.exe'))
    found = next((c for c in candidates if os.path.isfile(c)), None)
    _MADMOM_WORKER_CACHE['path'] = found
    return found


def is_madmom_available():
    return _find_madmom_worker() is not None


# -- scelta automatica del motore + verifica BPM online -------------------
#
# madmom e' il motore DI RIFERIMENTO, non un'eccezione: e' quello che usa BoxVR
# stesso (il gioco spedisce DBNDownBeatTracker.exe, cioe' madmom con modello
# DBN - vedi [[boxvr-internals]]), ed e' quello che ha superato il playtest
# reale in VR su un'intera playlist. Il punto NON e' scegliere il "migliore in
# assoluto" ma evitare di pagarne il costo (decine di secondi a brano invece di
# pochi) quando non serve: si gira sempre prima librosa, e la STABILITA' della
# griglia che produce dice se ci si puo' fidare del risultato veloce o se vale
# la pena rifare il brano con madmom.
#
# Sbagliare per eccesso di prudenza costa solo tempo, mai qualita': se la
# soglia manda a madmom un brano che librosa avrebbe gestito bene, il risultato
# resta buono. Per questo la soglia e' volutamente BASSA - la corsia veloce
# scatta solo quando la griglia di librosa e' eccezionalmente pulita, non
# semplicemente "accettabile".

FAST_PATH_STABILITY_THRESHOLD = 3.0
# Tarato su un confronto madmom-vs-librosa su 11 brani reali, poi VALIDATO in
# VR dall'utente: con questa soglia solo Long Gone (2.69) e Synchronise (2.96)
# restano su librosa, ed entrambi hanno superato il playtest. Erano anche gli
# unici due dove madmom faceva peggio (su Synchronise molto peggio: std 24.98
# contro 2.96). Con la soglia precedente a 5.0 finivano nella corsia veloce
# anche brani dove madmom dava un risultato migliore (Tokyo Drift 4.03, Black
# Carl 4.23, Hackers 4.40), mentre due brani sopra soglia (Baddadan 5.65, Get
# It On 5.83) venivano mandati a madmom che li gestiva peggio - cioe' sbagliava
# in entrambe le direzioni.
#
# ATTENZIONE se un giorno si ritocca: il campione e' di 11 brani di UN SOLO
# genere (drum&bass/breakbeat). Il numero esatto non e' detto valga per generi
# molto diversi; la logica invece regge a prescindere, perche' il caso peggiore
# di una soglia troppo bassa e' solo "piu' lento del necessario". Ritararla
# richiede lo stesso metodo: confronto misurato + playtest reale, mai i soli
# numeri (vedi [[feedback-beatgrid-stability-vs-realplay]] - la metrica non
# predice in modo affidabile la qualita' percepita in gioco).

SUSPECT_STABILITY_THRESHOLD = 5.5
# Soglia SEPARATA e piu' alta, con uno scopo diverso: non decide il motore
# (sopra la soglia veloce si usa comunque madmom), segnala all'utente i brani
# in cui il rilevamento e' abbastanza ballerino da meritare un controllo umano
# del BPM - accende l'icona di ricerca online nell'anteprima. Tenerla distinta
# evita di marcare come "sospetti" i tanti brani che semplicemente non stanno
# nella corsia veloce ma vengono comunque elaborati benissimo da madmom.

COVERAGE_GAP_THRESHOLD_S = 8.0
# Trovato il 25/08 confrontando la nostra coreografia con una mappa BeatSaver
# reale (Believer): librosa.beat.beat_track puo' fermarsi PRIMA della fine del
# brano - non un'ottava sbagliata o un tempo instabile (beat_grid_stability lo
# avrebbe preso), proprio smette di produrre beat, anche durante il passaggio
# piu' energico dell'intero brano (misurato: RMS piu' alto nel tratto perso
# che in quello prima, non un fade-out). Verificato chiamando
# librosa.beat.beat_track() grezzo, senza nostro codice in mezzo: e' un limite
# noto del tracker a programmazione dinamica su tracce lunghe/dinamicamente
# varie, non un bug nostro. Madmom sulla stessa canzone copre fino a 0.5s dalla
# fine - per questo diventa un TERZO motivo (oltre alla griglia instabile) per
# scegliere madmom nel percorso automatico. Soglia alta apposta: una canzone
# puo' legittimamente avere qualche secondo di coda silenziosa/dissolvenza,
# quello non e' un bug e non deve far scattare nulla.


def beat_grid_stability(beat_times):
    """Deviazione standard del BPM istantaneo beat-a-beat (60/intervallo) - un
    beat-grid stabile ha intervalli quasi costanti; un tracker che perde il
    tempo durante una transizione produce picchi/cali visibili in questa
    serie. None se ci sono troppo pochi beat per un calcolo sensato."""
    if not beat_times or len(beat_times) < 3:
        return None
    intervals = np.diff(beat_times)
    intervals = intervals[intervals > 0]
    if len(intervals) < 2:
        return None
    inst_bpm = 60.0 / intervals
    return float(np.std(inst_bpm))


def recommend_engine_from_beats(beat_times,
                                 fast_threshold=FAST_PATH_STABILITY_THRESHOLD,
                                 suspect_threshold=SUSPECT_STABILITY_THRESHOLD):
    """Dato un beat-grid gia' calcolato con librosa (il motore veloce, provato
    sempre per primo), decide se tenerlo o rifare il brano con madmom.

    Ritorna (engine_consigliato, std, sospetto):
      - engine: 'librosa' solo se la griglia e' ECCEZIONALMENTE pulita
        (std < fast_threshold), altrimenti 'madmom' - che resta il default.
      - sospetto: griglia molto instabile (std >= suspect_threshold), da far
        controllare all'utente; e' indipendente dalla scelta del motore.
    Con troppo pochi beat per un giudizio (std None) si usa comunque madmom,
    il piu' prudente dei due, e non si segnala nulla."""
    std = beat_grid_stability(beat_times)
    if std is None:
        return 'madmom', None, False
    engine = 'librosa' if std < fast_threshold else 'madmom'
    return engine, std, std >= suspect_threshold


def bpm_search_url(title, artist):
    """URL di una ricerca Google pre-compilata per verificare il BPM a
    orecchio/da fonti terze - deliberatamente NON uno scraping automatico:
    un sito come songbpm.com renderizza il BPM lato client (verificato in
    questa sessione, non e' nell'HTML grezzo) e le API gratuite con dati
    affidabili (es. getsongbpm.com) richiedono un account + backlink
    pubblico, impraticabile per un tool desktop personale. Aprire una
    ricerca gia' pronta nel browser dell'utente e' l'equivalente automatizzato
    di quello che farebbe a mano, senza scraping fragile ne' account."""
    import urllib.parse
    q = f"{title} {artist} bpm"
    return "https://www.google.com/search?q=" + urllib.parse.quote(q)


def _detect_beats_madmom(audio_path, forced_bpm=None):
    """Beat-tracking via il sottoprocesso madmom_worker.exe (DBNBeatTrackingProcessor -
    vedi il commento sopra per il perche' e la validazione). Ritorna (beat_times,
    tempo_val); solleva MadmomUnavailableError se l'exe manca o fallisce."""
    import subprocess
    worker = _find_madmom_worker()
    if worker is None:
        raise MadmomUnavailableError("madmom_worker.exe non trovato - vedi madmom_worker/BUILD.md")
    args = [worker, audio_path]
    if forced_bpm is not None:
        args.append(f"--forced-bpm={float(forced_bpm)}")
    # CREATE_NO_WINDOW (27/08, segnalato dall'utente: una finestra nera si
    # apriva e chiudeva ripetutamente durante le analisi) - senza, un
    # sottoprocesso da riga di comando apre comunque una sua console visibile
    # anche se il chiamante e' un'app windowed come questa. madmom_worker.exe
    # gira per il 51% dei brani (griglia instabile, vedi
    # recommend_engine_from_beats) - era la fonte piu' frequente.
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
    try:
        result = subprocess.run(args, capture_output=True, text=True,
                                timeout=MADMOM_WORKER_TIMEOUT_S, creationflags=flags)
    except subprocess.TimeoutExpired:
        raise MadmomUnavailableError(f"madmom_worker.exe oltre {MADMOM_WORKER_TIMEOUT_S}s, interrotto")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise MadmomUnavailableError(
            f"madmom_worker.exe: output non valido (stderr: {result.stderr[:300] if result.stderr else 'vuoto'})")
    if 'error' in data:
        raise MadmomUnavailableError(f"madmom_worker.exe: {data['error']}")
    return np.array(data['beat_times'], dtype=float), float(data['tempo'])


def detect_beats_and_bars(mono_audio, sr, forced_bpm=None, beat_engine='librosa', audio_path=None):
    """Beat-tracking; raggruppa i beat in bar da BEATS_PER_BAR.

    `beat_engine`: 'librosa' (default, veloce) o 'madmom' (piu' lento, piu'
    robusto ai cambi di tempo locali - vedi il commento sopra
    _find_madmom_worker per la validazione). Con 'madmom' serve anche
    `audio_path` (il worker esterno legge il file da se', non l'array gia'
    decodificato in memoria).

    `forced_bpm`: se valorizzato (correzione manuale dell'utente dalla GUI dopo
    aver ascoltato la base a click e giudicato il BPM rilevato sbagliato), il
    tempo viene bloccato ESATTAMENTE a quel valore (`bpm=`, non `start_bpm=` -
    quest'ultimo e' solo un punto di partenza per la stima del tempo e la ricerca
    puo' comunque riconvergere altrove, verificato non fare nulla su un aggiustamento
    fine di pochi BPM; `bpm=` invece salta del tutto la stima e forza il tempo dato,
    lasciando solo le POSIZIONI dei beat libere di agganciarsi ai transienti reali
    dell'audio a quel tempo). In questo caso la correzione automatica dell'ottava
    (_correct_tempo_octave, solo ramo librosa) viene saltata: e' l'utente stesso
    ad aver gia' arbitrato quale tempo e' quello giusto."""
    if beat_engine == 'madmom':
        if audio_path is None:
            raise ValueError("beat_engine='madmom' richiede audio_path")
        beat_times, tempo_val = _detect_beats_madmom(audio_path, forced_bpm=forced_bpm)
        tempo_corrected = False  # il DBN vincola gia' l'ottava tramite min/max_bpm quando forced_bpm e' dato
    elif forced_bpm is not None:
        tempo, beat_frames = librosa.beat.beat_track(y=mono_audio, sr=sr, bpm=float(forced_bpm))
        tempo_val = float(tempo) if np.isscalar(tempo) else float(tempo[0])
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        tempo_corrected = False
    else:
        tempo, beat_frames = librosa.beat.beat_track(y=mono_audio, sr=sr)
        tempo_val = float(tempo) if np.isscalar(tempo) else float(tempo[0])
        tempo_val, beat_frames, tempo_corrected = _correct_tempo_octave(mono_audio, sr, tempo_val, beat_frames)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    beats, bars = _beats_bars_from_times(beat_times, tempo_val)
    return beats, bars, tempo_val, tempo_corrected


# -- segmentazione strutturale (come fa BoxVR) ----------------------------
#
# BoxVR non taglia i segmenti a blocchi regolari: usa sonic-annotator con il
# plugin Vamp qm-segmenter per trovare i confini MUSICALI reali (strofa,
# ritornello, drop), che hanno durata variabile e la cui etichetta si ripete
# quando la sezione ritorna. Verificato leggendo l'output che il gioco stesso
# lascia in %AppData%/LocalLow/FITXR/BoxVR/Temp/vampOutput.txt, i cui confini
# coincidono esattamente con quelli del trackdata che poi produce.
# Vedi [[boxvr-internals]].
#
# Usiamo gli stessi identici binari e plugin che il gioco spedisce, quando
# BoxVR e' installato su questa macchina - non una reimplementazione.
#
# ATTENZIONE, verificato sperimentalmente: qm-segmenter NON e' deterministico.
# A parita' di file e parametri restituisce ogni volta una segmentazione
# leggermente diversa (in tre prove: 18, 18 e 13 segmenti), perche' il
# clustering delle sezioni parte da un'inizializzazione casuale. Non si puo'
# quindi riprodurre "il" risultato del gioco - nemmeno il gioco potrebbe
# rifarlo uguale. Quello che si riproduce, in modo stabile, e' il CARATTERE
# della segmentazione: confini sulle transizioni musicali vere invece che ogni
# N battute. Sui parametri sotto, il confronto con l'output reale del gioco
# azzeccava 9 confini su 18 entro mezzo secondo, con errore medio ~1.1s.
SEG_FEATURE_TYPE = 1     # 1 = "Chromatic (Chroma)" - il default del plugin
SEG_N_TYPES = 8          # il gioco produce 8 tipi di sezione (etichette A-H)
SEG_NEIGHBOURHOOD = 4.0
def _seg_step_block(sr):
    """Passo e blocco per qm-segmenter, in campioni. NON sono costanti: il
    plugin li pretende pari a 0.2s e 0.6s al sample rate del file, e li'
    rifiuta di inizializzarsi se non tornano ("supplied step size 8820 differs
    from required step size 9600" su un wav a 48kHz - e' cosi' che questo bug
    e' venuto fuori, con la segmentazione che falliva in silenzio su un brano
    solo). I default del plugin, 8820/26460, sono esattamente questo calcolo a
    44100 Hz."""
    step = int(round(sr / 5.0))
    return step, step * 3
VAMP_TIMEOUT_S = 900

_SEG_N3_TEMPLATE = """@prefix xsd:      <http://www.w3.org/2001/XMLSchema#> .
@prefix vamp:     <http://purl.org/ontology/vamp/> .
@prefix :         <#> .

:transform a vamp:Transform ;
    vamp:plugin <http://vamp-plugins.org/rdf/plugins/qm-vamp-plugins#qm-segmenter> ;
    vamp:step_size "{step}"^^xsd:int ;
    vamp:block_size "{block}"^^xsd:int ;
    vamp:plugin_version \"\"\"3\"\"\" ;
    vamp:parameter_binding [
        vamp:parameter [ vamp:identifier "featureType" ] ;
        vamp:value "{ft}"^^xsd:float ;
    ] ;
    vamp:parameter_binding [
        vamp:parameter [ vamp:identifier "nSegmentTypes" ] ;
        vamp:value "{nst}"^^xsd:float ;
    ] ;
    vamp:parameter_binding [
        vamp:parameter [ vamp:identifier "neighbourhoodLimit" ] ;
        vamp:value "{nl}"^^xsd:float ;
    ] ;
    vamp:output <http://vamp-plugins.org/rdf/plugins/qm-vamp-plugins#qm-segmenter_output_segmentation> .
"""

_VAMP_TOOLS_CACHE = {}


def _steam_library_roots():
    """Legge le librerie Steam da libraryfolders.vdf invece di indovinare i
    percorsi: su questa macchina BoxVR sta su E:, ma su un'altra puo' stare
    ovunque."""
    roots = []
    for base in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
        vdf = os.path.join(base, 'steamapps', 'libraryfolders.vdf')
        if not os.path.isfile(vdf):
            continue
        try:
            with open(vdf, encoding='utf-8', errors='ignore') as f:
                text = f.read()
        except OSError:
            continue
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            roots.append(m.group(1).replace('\\\\', '\\'))
    return roots


def set_game_dir(path):
    """Imposta la cartella di BoxVR scelta dall'utente (vedi la richiesta al
    primo avvio nella GUI). Ha la precedenza su qualunque rilevamento
    automatico: le edizioni Oculus/Viveport non stanno nelle librerie Steam e
    solo l'utente sa dove sono."""
    _VAMP_TOOLS_CACHE.pop('tools', None)
    _VAMP_TOOLS_CACHE['game_dir'] = path or None


def find_vamp_tools():
    """Ritorna (sonic_annotator_exe, cartella_plugin) presi dall'installazione
    di BoxVR, oppure (None, None) se il gioco non e' installato qui - in quel
    caso la generazione ripiega sui segmenti a blocchi fissi, senza errori."""
    if 'tools' in _VAMP_TOOLS_CACHE:
        return _VAMP_TOOLS_CACHE['tools']
    candidates = []
    chosen = _VAMP_TOOLS_CACHE.get('game_dir')
    if chosen:
        candidates.append(chosen)
    env_root = os.environ.get('BOXVR_INSTALL_DIR')
    if env_root:
        candidates.append(env_root)
    for root in _steam_library_roots():
        candidates.append(os.path.join(root, 'steamapps', 'common', 'BOXVR'))
    found = (None, None)
    for root in candidates:
        vamp_dir = os.path.join(root, 'BoxVR_Data', 'StreamingAssets', 'Vamp')
        exe = os.path.join(vamp_dir, 'sonic-annotator-v1.5-win32', 'sonic-annotator.exe')
        plugins = os.path.join(vamp_dir, 'Vamp Plugins')
        if os.path.isfile(exe) and os.path.isdir(plugins):
            found = (exe, plugins)
            break
    _VAMP_TOOLS_CACHE['tools'] = found
    return found


def sections_cache_dir():
    """Cartella dove si conserva la segmentazione gia' calcolata. Sta accanto a
    settings.json in %APPDATA%, non nella cartella del gioco (che non e' nostra)
    ne' in quella dell'exe (che con --onefile e' temporanea)."""
    base = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')),
                        'BoxVR Level Fixer', 'sections')
    os.makedirs(base, exist_ok=True)
    return base


def audio_cache_key(path):
    """Chiave stabile per un file audio: dimensione + hash del primo mega.
    Non usa il percorso, cosi' lo stesso brano spostato o rinominato riusa la
    segmentazione gia' calcolata."""
    import hashlib
    h = hashlib.sha1()
    try:
        size = os.path.getsize(path)
        h.update(str(size).encode())
        with open(path, 'rb') as f:
            h.update(f.read(1024 * 1024))
    except OSError:
        h.update(os.path.abspath(path).encode())
    return h.hexdigest()[:24]


def load_cached_sections(key):
    if not key:
        return None
    p = os.path.join(sections_cache_dir(), f"{key}.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding='utf-8') as f:
            return [(float(t), str(l)) for t, l in json.load(f)]
    except Exception:
        return None


def save_cached_sections(key, rows):
    if not key or not rows:
        return
    try:
        with open(os.path.join(sections_cache_dir(), f"{key}.json"), 'w', encoding='utf-8') as f:
            json.dump([[t, l] for t, l in rows], f)
    except OSError:
        pass


# Cache di detect_breath_and_bursts (30/08, ottimizzazione trovata cercando
# di velocizzare l'analisi): a differenza della segmentazione strutturale
# sopra, QUESTA non e' un compromesso qualita'/velocita' - e' lavoro
# ripetuto inutilmente. detect_breath_and_bursts dipende SOLO da
# (mono_audio, sr), MAI da BPM/beat_engine - eppure _apply_forced_bpm e
# _on_beat_engine_toggle invalidano l'intera analisi e la rifanno da zero,
# ricalcolando anche hpss (l'80% del tempo di analisi misurato su brani
# lunghi, vedi STATO E ROADMAP.md) anche se il suo risultato sarebbe
# IDENTICO. Stessa chiave (audio_cache_key, dimensione+hash del primo mega)
# e stessa cartella gia' usate per le sezioni strutturali sopra - se in
# futuro cambiano i parametri di default di detect_breath_and_bursts, la
# cache va svuotata a mano (stesso limite gia' accettato per quella sopra:
# nessuna delle due si autoinvalida su un cambio di configurazione).
def load_cached_breath_bursts(key):
    if not key:
        return None
    p = os.path.join(sections_cache_dir(), f"breath_{key}.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        return d['events'], np.array(d['centers'], dtype=float), np.array(d['density'], dtype=float), d['onsets']
    except Exception:
        return None


def save_cached_breath_bursts(key, events, centers, density, onsets):
    if not key:
        return
    try:
        with open(os.path.join(sections_cache_dir(), f"breath_{key}.json"), 'w', encoding='utf-8') as f:
            json.dump({'events': events, 'centers': list(map(float, centers)),
                       'density': list(map(float, density)), 'onsets': list(map(float, onsets))}, f)
    except OSError:
        pass


def structural_segment_times(mono_audio, sr, log=None, with_labels=False, cache_key=None):
    """Confini delle sezioni musicali (in secondi) via qm-segmenter, o None se
    i tool del gioco non sono disponibili o l'analisi fallisce - il chiamante
    deve sempre poter proseguire senza.

    `with_labels=True` ritorna [(inizio, etichetta), ...] invece dei soli
    tempi. Le etichette (A, B, C...) SI RIPETONO quando la stessa sezione
    musicale torna nel brano: e' l'informazione che permette di dare al
    ritornello la stessa coreografia ogni volta che ricompare, invece di
    ricominciare da capo a caso (vedi boxvr_choreo.py).

    `cache_key`: qm-segmenter NON e' deterministico (vedi sopra), quindi
    rieseguirlo darebbe ogni volta confini ed etichette diversi, e con essi una
    coreografia diversa per lo stesso brano. Con una chiave il risultato viene
    salvato al primo calcolo e poi riutilizzato: e' cio' che rende la
    generazione ripetibile TRA sessioni, non solo dentro la stessa."""
    import subprocess, tempfile, shutil
    cached = load_cached_sections(cache_key)
    if cached:
        return cached if with_labels else sorted({t for t, _ in cached})
    exe, plugins = find_vamp_tools()
    if not exe:
        return None
    tmpdir = tempfile.mkdtemp(prefix='boxvr_seg_')
    try:
        wav_path = os.path.join(tmpdir, 'seg_input.wav')
        sf.write(wav_path, mono_audio, sr)
        n3_path = os.path.join(tmpdir, 'seg.n3')
        step, block = _seg_step_block(sr)
        with open(n3_path, 'w', encoding='utf-8') as f:
            f.write(_SEG_N3_TEMPLATE.format(step=step, block=block, ft=SEG_FEATURE_TYPE,
                                            nst=SEG_N_TYPES, nl=SEG_NEIGHBOURHOOD))
        env = dict(os.environ, VAMP_PATH=plugins)
        # CREATE_NO_WINDOW (27/08, vedi _detect_beats_madmom sopra per il
        # perche') - sonic-annotator gira su OGNI brano analizzato (non solo
        # quelli con griglia instabile), quindi era la fonte piu' frequente
        # di tutte delle finestre nere segnalate dall'utente.
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        proc = subprocess.run([exe, '-t', n3_path, '-w', 'csv', '--csv-stdout', wav_path],
                              capture_output=True, text=True, env=env, timeout=VAMP_TIMEOUT_S,
                              creationflags=flags)
        rows = []
        for line in proc.stdout.splitlines():
            parts = line.split(',')
            # "file",inizio,durata,tipo,"etichetta" - nelle righe successive alla
            # prima il nome file e' vuoto ma il numero di campi non cambia.
            if len(parts) < 5:
                continue
            try:
                rows.append((float(parts[-4]), parts[-1].strip().strip('"')))
            except ValueError:
                continue
        if len(rows) < 2:
            if log:
                log("Segmentazione strutturale non riuscita, uso i blocchi fissi.")
            return None
        rows.sort(key=lambda r: r[0])
        save_cached_sections(cache_key, rows)
        if with_labels:
            return rows
        return sorted({t for t, _ in rows})
    except Exception as e:
        if log:
            log(f"Segmentazione strutturale saltata ({e}) - uso i blocchi fissi.")
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def detect_breath_and_bursts(mono_audio, sr, min_breath_s=0.3, quiet_win_s=1.0,
                              burst_max_gap_s=0.35, burst_max_span_s=0.7,
                              burst_min_events=2, burst_max_events=4,
                              fast_percentile=88, fast_min_density=5, fast_min_s=0.6,
                              max_punch_rate_hz=3.0):
    """Trova momenti musicali che l'assegnazione a battuta/sezione intera non
    riesce a cogliere - vedi [[boxvr-roadmap]] per i casi reali (Act A Fool)
    su cui questo e' stato tarato e verificato. Generalizza sullo stesso
    segnale (densita' di onset nel tempo) a tutta la gamma, non solo agli
    estremi bassi - deve valere per qualunque canzone, non solo per quella
    con cui e' stato messo a punto.

    - "respiro": la densita' di attacchi ritmici crolla quasi a zero per un
      momento - es. il drop che si interrompe un istante prima di ripartire.
      Il segnale giusto e' la densita' di onset (eventi al secondo), NON
      l'energia RMS: un respiro puo' restare comunque "rumoroso" (synth
      sostenuto, basso tenuto) pur avendo zero ATTACCHI distinti.
    - "raffica": un piccolo gruppo isolato di 2-4 colpi ravvicinati DENTRO
      un respiro - eventi che risaltano perche' il resto tace intorno a loro
      (es. tre "spari" consecutivi), non perche' sono i piu' forti del brano.
    - "veloce": l'opposto del respiro - una sezione dove la densita' resta
      SOSTENUTA e alta (un tratto di drop che corre rapidissimo), non un
      picco isolato. Qui il posizionamento giusto non e' un pattern del
      repertorio a tempo fisso, ma dritti alternati agganciati agli attacchi
      REALI, con un tetto di cadenza (`max_punch_rate_hz`) perche' un corpo
      vero non puo' seguire ogni singolo attacco se la sezione e' piu' densa
      di quanto sia fisicamente sostenibile colpire.

    Ritorna una lista di dict ordinati per tempo, i tipi possono sovrapporsi
    (un respiro con una raffica dentro produce un evento di ciascun tipo):
      {'type': 'breath', 'start': t0, 'end': t1}
      {'type': 'burst', 'start': t0, 'end': t1, 'onsets': [t, ...]}
      {'type': 'fast', 'start': t0, 'end': t1, 'onsets': [t, ...]}
    """
    duration = len(mono_audio) / sr
    if duration <= 0:
        return []

    # Due sensibilita' diverse per due domande diverse - verificato che una
    # sola non basta per entrambe:
    # 1) "quant'e' densa questa zona, in generale?" (per trovare respiri e
    #    sezioni veloci) vuole un rilevatore PRUDENTE (solo eventi
    #    chiaramente udibili) - un rilevatore troppo sensibile alza il
    #    pavimento ovunque e la densita' non scende mai abbastanza da
    #    segnalare silenzio, nemmeno dove c'e' davvero.
    # 2) "quali sono gli attacchi ESATTI in questa zona?" (per posizionare i
    #    colpi dentro una raffica o una sezione veloce) vuole un rilevatore
    #    SENSIBILE, capace di risolvere colpi ravvicinati (150-200ms) - lo
    #    stesso rilevatore prudente li fonde in un solo evento.
    quiet_onsets = librosa.onset.onset_detect(y=mono_audio, sr=sr, hop_length=128,
                                               backtrack=False, units='time')

    from scipy.ndimage import median_filter
    from scipy.signal import find_peaks
    _, perc = librosa.effects.hpss(mono_audio, margin=(1.0, 3.0))
    hop, frame = 64, 256
    rms = librosa.feature.rms(y=perc, frame_length=frame, hop_length=hop)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    baseline = median_filter(rms, size=max(1, int(1.0 * sr / hop)))
    ratio = rms / (baseline + 1e-6)
    peak_idx, _ = find_peaks(ratio, height=3.0, distance=max(1, int(0.08 * sr / hop)))
    fine_onsets = rms_times[peak_idx]

    step = 0.1
    centers = np.arange(0, duration, step)
    if len(quiet_onsets):
        density = np.array([
            np.sum((quiet_onsets >= c - quiet_win_s / 2) & (quiet_onsets < c + quiet_win_s / 2))
            for c in centers
        ])
    else:
        density = np.zeros(len(centers))
    n = len(centers)

    def _contiguous_runs(mask, min_len_s):
        runs = []
        i = 0
        while i < n:
            if not mask[i]:
                i += 1
                continue
            j = i
            while j < n and mask[j]:
                j += 1
            t0, t1 = float(centers[i]), float(centers[j - 1] + step)
            if t1 - t0 >= min_len_s:
                runs.append((t0, t1))
            i = j
        return runs

    breaths = [{'type': 'breath', 'start': t0, 'end': t1}
               for t0, t1 in _contiguous_runs(density <= 1, min_breath_s)]

    bursts = []
    for b in breaths:
        inside = [t for t in fine_onsets if b['start'] <= t < b['end']]
        if not inside:
            continue
        # incatena per gap ravvicinato MA con un tetto sulla durata totale
        # del gruppo - senza il tetto una serie di gap tutti piccoli ma
        # continui incatena l'intera ripresa di densita' dopo il respiro in
        # un solo blocco enorme, perdendo la raffica vera e propria (il
        # primo gruppo compatto), verificato su un caso reale.
        groups, cur = [], [inside[0]]
        for t in inside[1:]:
            if t - cur[-1] <= burst_max_gap_s and t - cur[0] <= burst_max_span_s:
                cur.append(t)
            else:
                groups.append(cur)
                cur = [t]
        groups.append(cur)
        for g in groups:
            if burst_min_events <= len(g) <= burst_max_events:
                bursts.append({'type': 'burst', 'start': float(g[0]), 'end': float(g[-1]),
                                'onsets': [float(t) for t in g]})

    # sezioni "veloci": densita' sostenuta sopra la propria norma - percentile
    # relativo al brano stesso (non un numero assoluto fisso), cosi' vale
    # sia per un brano generalmente denso sia per uno generalmente scarno;
    # `fast_min_density` e' solo un pavimento minimo assoluto, per non
    # segnalare come "veloce" un brano dove anche il picco e' comunque rado.
    fast_thresh = max(float(np.percentile(density, fast_percentile)), fast_min_density)
    min_gap = 1.0 / max_punch_rate_hz
    fasts = []
    for t0, t1 in _contiguous_runs(density >= fast_thresh, fast_min_s):
        inside = sorted(t for t in fine_onsets if t0 <= t < t1)
        chosen = []
        for t in inside:
            if not chosen or t - chosen[-1] >= min_gap:
                chosen.append(t)
        if len(chosen) >= 2:
            fasts.append({'type': 'fast', 'start': t0, 'end': t1, 'onsets': chosen})

    events = breaths + bursts + fasts
    events.sort(key=lambda e: e['start'])
    # la curva di densita' grezza viaggia insieme agli eventi (non solo gli
    # eventi discreti respiro/raffica/veloce) - serve al chiamante per
    # applicare il segnale in modo continuo/sfumato invece che con un taglio
    # netto sì/no, vedi [[boxvr-roadmap]] 2026-08-23: su 20 brani reali la
    # soglia binaria perdeva un segnale debole ma vero presente su 16/20.
    #
    # `quiet_onsets` (gli attacchi ESATTI dell'audio, dal rilevatore sensibile)
    # esce ora insieme al resto: fino al 25/08 restava dentro questa funzione,
    # usato solo per rifinire raffiche e sezioni veloci. Serve al piazzamento
    # VERO dei colpi - vedi boxvr_choreo._snap_to_onsets e il verdetto VR del
    # 25/08 sera: i pattern del repertorio hanno posizioni fisse rispetto al
    # beat, quindi su un riff sincopato (Master Of Puppets) i colpi cadevano
    # sui quarti mentre la musica accentava le mezze battute.
    return events, centers, density, list(map(float, quiet_onsets))


def density_rank_lookup(centers, density):
    """Costruisce una funzione rank(t) -> percentile (0-1) della densita' di
    onset in quell'istante, rispetto a tutto il brano - il segnale continuo
    dietro respiro/veloce, prima che venga tagliato a soglia netta."""
    order = np.argsort(density)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(len(density)) / max(1, len(density) - 1)

    def rank_at(t):
        idx = int(np.clip(np.searchsorted(centers, t), 0, len(centers) - 1))
        return float(ranks[idx])

    return rank_at


def _bar_bounds_from_times(bars, times, min_bars=2):
    """Traduce confini in secondi negli INDICI DI BAR piu' vicini: un segmento
    deve comunque iniziare su una battuta (i campi _startBeatIndex/_numBeats del
    formato lo richiedono), e far partire una sezione a meta' battuta si
    sentirebbe. Scarta i confini troppo ravvicinati per non produrre segmenti
    di una battuta sola."""
    nb = len(bars)
    if nb == 0:
        return []
    bar_starts = [b['_startTime'] for b in bars]
    idxs = []
    for t in times:
        # bar la cui partenza e' piu' vicina a t
        best = min(range(nb), key=lambda i: abs(bar_starts[i] - t))
        idxs.append(best)
    out = []
    for i in sorted(set(idxs)):
        if not out:
            out.append(i)
        elif i - out[-1] >= min_bars:
            out.append(i)
    if out and out[0] != 0:
        out.insert(0, 0)
    return out


def _tag_segments_with_sections(segs, section_rows):
    """Annota ogni segmento con l'etichetta della sezione musicale in cui cade
    (`_sectionLabel`). Chiave sotto: le etichette si RIPETONO, quindi due
    ritornelli distanti nel brano portano la stessa etichetta - ed e' cosi' che
    il generatore di coreografie puo' dar loro la stessa combinazione.

    NB: la chiave inizia con "_" come i campi del formato BoxVR ma NON fa parte
    del formato - viene rimossa prima di scrivere il trackdata (vedi
    build_trackdata_json), serve solo a noi in memoria."""
    if not section_rows:
        for s in segs:
            s['_sectionLabel'] = None
        return
    for s in segs:
        t = s['_startTime']
        label = section_rows[0][1]
        for start, lab in section_rows:
            if start <= t + 0.01:
                label = lab
            else:
                break
        s['_sectionLabel'] = label


def build_segments(bars, beats, bar_score, duration, boundary_bars=None):
    """Costruisce i segmenti, senza buchi: coprono per costruzione l'intera
    canzone da 0 a duration (il primo/ultimo segmento vengono estesi fino ai
    bordi, dato che il primo/ultimo beat rilevato di solito non coincide
    esattamente con inizio/fine del file).

    `boundary_bars`: indici di bar dove far iniziare un nuovo segmento, presi
    dalla segmentazione strutturale (vedi structural_segment_times). Se None,
    si torna al comportamento storico a blocchi di BARS_PER_SEGMENT bar."""
    nb = len(bars)
    n_beats = len(beats)
    if boundary_bars:
        ranges = [(boundary_bars[i], boundary_bars[i + 1] if i + 1 < len(boundary_bars) else nb)
                  for i in range(len(boundary_bars))]
    else:
        ranges = [(s, min(s + BARS_PER_SEGMENT, nb)) for s in range(0, nb, BARS_PER_SEGMENT)]
    segs = []
    for start_bar, end_bar in ranges:
        start_beat = bars[start_bar]['_beatIndex']
        end_beat = bars[end_bar]['_beatIndex'] if end_bar < nb else n_beats
        num_beats = end_beat - start_beat
        if num_beats <= 0:
            continue
        seg_bar_scores = bar_score[start_bar:end_bar]
        avg_energy = float(np.mean(seg_bar_scores)) if len(seg_bar_scores) else 0.0
        segs.append({
            '_startTime': bars[start_bar]['_startTime'],
            '_startBeatIndex': start_beat,
            '_length': (beats[end_beat - 1]['_triggerTime'] + beats[end_beat - 1]['_beatLength']
                        - bars[start_bar]['_startTime']),
            '_numBeats': num_beats,
            '_averageEnergy': avg_energy,
            # numerato sui segmenti EFFETTIVAMENTE prodotti, non sull'indice del
            # ciclo: un range vuoto viene saltato, e con i confini strutturali
            # (di lunghezza irregolare) capita piu' spesso che coi blocchi fissi -
            # con enumerate() la numerazione avrebbe dei buchi.
            '_index': len(segs),
            '_energyLevel': 0,
        })

    if segs:
        first = segs[0]
        if first['_startTime'] > 0:
            first['_length'] += first['_startTime']
            first['_startTime'] = 0.0
        last = segs[-1]
        end = last['_startTime'] + last['_length']
        if duration - end > 0:
            last['_length'] += (duration - end)
            # bug reale trovato il 25/08 confrontando con una mappa BeatSaver
            # (Believer, ultimi 39s del brano completamente senza coreografia
            # nonostante find_no_coverage_gaps dicesse "nessun buco"): estendere
            # SOLO _length copre il controllo di copertura (che legge _length),
            # ma build_move_actions itera per _numBeats, non per _length - senza
            # aggiornare anche questo, la coreografia si fermava comunque dove si
            # fermava l'ultimo confine strutturale rilevato, silenziosamente.
            # Portare _numBeats fino all'ultimo beat disponibile del brano
            # allinea le due letture della stessa fine di segmento.
            last['_numBeats'] = n_beats - last['_startBeatIndex']
    return segs


# Politica di classificazione per la generazione da zero: qui ogni segmento DEVE
# ricevere un livello (non c'e' un originale del gioco a cui tornare come nella
# correzione), quindi invece di soglie fisse sulla distribuzione di energia si usa
# un budget sulla durata totale dell'allenamento.
MAX_SILENCE_FRACTION = 0.05          # default storico: il silenzio non supera mai il 5% del brano
MAX_LIGHT_OR_SILENCE_FRACTION = 0.20  # default storico: silenzio + leggero insieme non superano il 20%
SILENCE_SCORE_FRACTION = 0.35         # un segmento e' "abbastanza soffice" solo sotto il 35% della mediana
MIN_SILENCE_SEGMENT_GAP = 2           # mai due segmenti di silenzio a meno di questa distanza (niente blocchi lunghi)

# Range dello slider "densita' colpi" della GUI: densita'=1.0 e' il comportamento
# storico (20%/5%, il piu' ddi pugni), densita'=0.0 e' il piu' vicino alla MEDIA
# misurata sugli 8 trackdata reali di BoxVR gia' in dotazione (~50% silenzio+leggero,
# ~15% di solo silenzio - vedi boxvr_gui_tool.md in memoria per i dati completi per
# brano). Tenuto qui, non nella GUI, cosi' resta lo stesso anche per un uso da CLI.
# Tre punti (non piu' due) su cui interpolare lo slider densita' - misurati
# direttamente sui 9 trackdata reali di BoxVR disponibili nel progetto (gli 8
# storici + Immortal, confrontato beat-per-beat con la nostra generazione nella
# sessione del 2026-08-21): media reale 52.5% silenzio+leggero, 16.9% solo
# silenzio (range 40.3-66.9% / 11.1-26.6% sugli 8+1 brani). DENSITA'=0.5 e'
# ancorato esattamente su questa media misurata, non piu' un punto intermedio
# qualsiasi di un'unica retta - prima (interpolazione a due soli punti,
# 1.0->20%/5%, 0.0->60%/20%) il valore che avvicinava davvero l'autenticita' di
# BoxVR era ~35-38%, non il 50% che l'etichetta dello slider farebbe pensare;
# ora e' esplicitamente vero. 1.0 resta il default storico invariato (l'utente
# lo preferisce per il proprio stile di allenamento, mai un attimo di calo);
# 0.0 resta piu' rado perfino della media reale, per chi la vuole ancora piu'
# leggera. Vedi anche il marcatore visivo sullo slider nella GUI.
DENSITY_ANCHORS = (
    (0.0, 0.20, 0.60),   # piu' rado della media reale
    (0.5, 0.169, 0.525),  # media reale misurata su 9 brani BoxVR
    (1.0, 0.05, 0.20),   # storico/denso (default, stile di allenamento dell'utente)
)


def density_to_fractions(density):
    """Converte lo slider densita' (0=rado, 0.5=come la media reale di BoxVR,
    1=denso/storico) nei due tetti di classify_segments_for_generation.
    Interpolazione lineare a tratti tra i tre punti di DENSITY_ANCHORS (non piu'
    una singola retta) cosi' il punto medio dello slider e' ancorato a un dato
    reale misurato, non a un semplice punto medio aritmetico tra gli estremi."""
    density = max(0.0, min(1.0, density))
    for (d0, s0, ls0), (d1, s1, ls1) in zip(DENSITY_ANCHORS, DENSITY_ANCHORS[1:]):
        if d0 <= density <= d1:
            t = (density - d0) / (d1 - d0) if d1 > d0 else 0.0
            max_silence = s0 + (s1 - s0) * t
            max_light_or_silence = ls0 + (ls1 - ls0) * t
            return max_silence, max_light_or_silence
    # non dovrebbe mai arrivare qui (density e' clampato sopra tra il primo e
    # l'ultimo ancoraggio), ma per sicurezza ritorna l'ultimo punto noto.
    _, s_last, ls_last = DENSITY_ANCHORS[-1]
    return s_last, ls_last


def classify_segments_for_generation(analysis, punch_ratio, max_silence_fraction=MAX_SILENCE_FRACTION,
                                      max_light_or_silence_fraction=MAX_LIGHT_OR_SILENCE_FRACTION):
    """Assegna un energyLevel a ogni segmento generato da zero, rispettando i tetti
    passati (default storici se non specificati - vedi anche density_to_fractions
    per come la GUI li ricava dallo slider densita'). Il silenzio va solo alle fasi
    genuinamente piu' soffici del brano (punteggio ben sotto la propria mediana),
    mai a due fasi consecutive - cosi' restano brevi pause per respirare, non
    lunghi blocchi morti. Il resto passa dal pool "attivo" e usa la stessa logica
    pugni/misto della correzione (assign_punch_misto, condivisa via boxvr_fixer.py)."""
    segs = analysis['segs']
    n = len(segs)
    if n == 0:
        return {}
    max_silence_fraction = max(0.0, min(1.0, max_silence_fraction))
    max_light_or_silence_fraction = max(max_silence_fraction, min(1.0, max_light_or_silence_fraction))

    scores = []
    for s in segs:
        idxs = bars_in_range(analysis['bar_start_idx'], analysis['nb'], s['_startBeatIndex'], s['_numBeats'])
        scores.append(float(np.mean(analysis['bar_score'][idxs])) if idxs else 0.0)

    durations = [s['_length'] for s in segs]
    total_duration = sum(durations) or 1.0
    median_score = float(np.median(scores)) if scores else 0.0
    silence_cutoff = median_score * SILENCE_SCORE_FRACTION

    order = sorted(range(n), key=lambda i: scores[i])  # dal piu' silenzioso al piu' carico

    level_map = {}
    cum_silence = 0.0
    last_silence_idx = None
    for i in order:
        if scores[i] > silence_cutoff:
            break  # oltre questo punto, in ordine crescente, nessuno e' abbastanza soffice
        if cum_silence + durations[i] > max_silence_fraction * total_duration:
            continue
        if last_silence_idx is not None and abs(i - last_silence_idx) < MIN_SILENCE_SEGMENT_GAP:
            continue
        level_map[i] = 0
        cum_silence += durations[i]
        last_silence_idx = i

    cum_light_or_silence = cum_silence
    for i in order:
        if i in level_map:
            continue
        if cum_light_or_silence + durations[i] > max_light_or_silence_fraction * total_duration:
            break
        level_map[i] = 1
        cum_light_or_silence += durations[i]

    active = [(i, scores[i]) for i in range(n) if i not in level_map]
    level_map.update(assign_punch_misto(active, punch_ratio))
    return level_map


def generate_song_analysis(audio_path, forced_bpm=None, beat_engine='librosa',
                            structural_segments=True, boundary_bars=None, log=None):
    """Analizza un mp3/wav da zero e ritorna un dict con le stesse chiavi di
    compute_song_analysis (boxvr_fixer.py), cosi' la GUI puo' riusare invariati
    timeline/preset/anteprima gia' costruiti per il flusso di correzione.

    `forced_bpm`: passato a detect_beats_and_bars per rigenerare con un tempo
    scelto manualmente dall'utente invece di quello rilevato automaticamente
    (vedi il suo docstring). `beat_engine`: 'librosa' (default) o 'madmom'.
    `structural_segments`: se True (e i tool di BoxVR sono installati qui) i
    confini dei segmenti seguono le sezioni musicali reali invece dei blocchi
    fissi - vedi structural_segment_times.

    `boundary_bars`: confini gia' calcolati in una passata precedente, da
    riusare invece di ricalcolarli. Serve a due cose insieme: non ripagare il
    costo del segmentatore in fase di generazione dopo averlo gia' pagato in
    anteprima, e soprattutto garantire che il file generato corrisponda a cio'
    che l'utente ha VISTO nell'anteprima - qm-segmenter non e' deterministico,
    quindi ricalcolare darebbe una segmentazione diversa a parita' di tutto."""
    native_audio, mono_audio, sr = decode_audio(audio_path)
    artist, title = read_tags(audio_path)
    duration = len(mono_audio) / sr

    beats, bars, tempo_val, tempo_corrected = detect_beats_and_bars(
        mono_audio, sr, forced_bpm=forced_bpm, beat_engine=beat_engine, audio_path=audio_path)
    bar_spans = [(b['_startTime'], b['_startTime'] + b['_duration']) for b in bars]
    bar_score = compute_bar_score(mono_audio, sr, bar_spans)
    bar_start_idx = np.array([b['_beatIndex'] for b in bars], dtype=int)

    seg_mode = 'fixed'
    section_rows = None
    if boundary_bars:
        # confini gia' noti (riusati dall'anteprima): niente ricalcolo dei
        # CONFINI (qm-segmenter non e' deterministico, ricalcolare darebbe
        # bar diversi da quelli gia' mostrati). Le ETICHETTE pero' vanno
        # comunque recuperate (30/08, bug reale trovato analizzando la
        # richiesta di ripetizione ritornelli): senza questo, _sectionLabel
        # restava SEMPRE None nella generazione vera (mai nell'anteprima),
        # perche' nessuno la rileggeva qui - e con essa None, ogni segmento
        # sembra unico a chi in boxvr_choreo.py cerca sezioni ricorrenti
        # (es. per dare la stessa combo a un ritornello che si ripete),
        # anche se la label era gia' calcolata e su disco. La cache e' quasi
        # sempre gia' calda (la stessa chiave l'ha appena scritta l'anteprima
        # che ha prodotto questi stessi boundary_bars), quindi il costo qui
        # e' una lettura di file, non un ricalcolo di sonic-annotator.
        section_rows = load_cached_sections(audio_cache_key(audio_path))
        boundary_bars = [i for i in boundary_bars if 0 <= i < len(bars)]
        seg_mode = 'structural' if len(boundary_bars) >= 2 else 'fixed'
        if seg_mode == 'fixed':
            boundary_bars = None
            section_rows = None
    elif structural_segments:
        section_rows = structural_segment_times(mono_audio, sr, log=log, with_labels=True,
                                                 cache_key=audio_cache_key(audio_path))
        if section_rows:
            boundary_bars = _bar_bounds_from_times(bars, [t for t, _ in section_rows])
            if len(boundary_bars) >= 2:
                seg_mode = 'structural'
            else:
                boundary_bars = None
    segs = build_segments(bars, beats, bar_score, duration, boundary_bars=boundary_bars)
    _tag_segments_with_sections(segs, section_rows)

    # respiro/raffica/veloce (vedi detect_breath_and_bursts) - stesso identico
    # calcolo gia' fatto per i brani installati in
    # boxvr_choreo.analysis_from_installed, qui riusa l'audio gia' decodificato
    # sopra invece di ricaricarlo. Deterministico (a differenza della
    # segmentazione strutturale sopra, non serve una cache per la
    # RIPETIBILITA'), ma dipende SOLO da (mono_audio, sr) - MAI da BPM/
    # beat_engine - quindi una correzione di BPM/motore beat (che invalida
    # l'intera analisi e la rifa' da zero) lo ricalcolava comunque, pagando
    # di nuovo hpss (30/08, trovato cercando di velocizzare l'analisi:
    # l'80% del tempo su un brano lungo) per un risultato IDENTICO. Cache
    # per VELOCITA', non per ripetibilita' - vedi load/save_cached_breath_bursts.
    rhythm_events, dens_centers, dens_values, onsets = [], None, None, []
    breath_cache_key = audio_cache_key(audio_path)
    cached_breath = load_cached_breath_bursts(breath_cache_key)
    try:
        if cached_breath is not None:
            rhythm_events, dens_centers, dens_values, onsets = cached_breath
        else:
            rhythm_events, dens_centers, dens_values, onsets = detect_breath_and_bursts(mono_audio, sr)
            save_cached_breath_bursts(breath_cache_key, rhythm_events, dens_centers, dens_values, onsets)
    except Exception as e:
        if log:
            log(f"Respiro/raffica/veloce non rilevati ({e}) - la coreografia seguira' solo i pattern.")

    return {
        'audio_path': audio_path, 'native_audio': native_audio, 'sr': sr,
        'bars': bars, 'beats': beats, 'segs': segs,
        'bar_score': bar_score, 'bar_start_idx': bar_start_idx, 'nb': len(bars),
        'duration': duration, 'bpm': tempo_val, 'tempo_corrected': tempo_corrected,
        'beat_engine': beat_engine, 'seg_mode': seg_mode, 'name': title, 'artist': artist,
        'seg_boundary_bars': boundary_bars,
        'rhythm_events': rhythm_events,
        'rhythm_density': (dens_centers, dens_values) if dens_centers is not None else None,
        # gli attacchi esatti dell'audio: e' su questi che i colpi vengono
        # agganciati, invece che sulle posizioni fisse dei pattern
        'onsets': onsets,
    }


def analyze_for_generate(audio_path, forced_bpm=None, engine_mode='auto', beat_engine='librosa',
                          on_fallback=None):
    """Decide QUALE motore usare per un brano da generare e produce l'analisi
    finita - la parte decisionale di quello che prima era il worker in
    background della GUI (_background_analysis_loop in boxvr_fixer_gui.py),
    tirata fuori perche' e' logica vera (non wiring di thread/code) e prima
    non era testabile senza aprire una finestra.

    `engine_mode`:
      - 'auto': pre-check economico con librosa (sempre provato per primo),
        poi si rifa' con madmom SOLO se la griglia non e' eccezionalmente
        pulita (vedi recommend_engine_from_beats) - sbagliare per prudenza
        costa solo tempo, mai qualita'. Se madmom non e' disponibile in
        questa build non ha senso nemmeno raccomandarlo: si resta su librosa.
      - 'manual': usa `beat_engine` cosi' com'e', nessuna decisione.
    In entrambi i casi, se madmom viene scelto (auto o manuale) ma fallisce
    per QUESTO brano specifico (MadmomUnavailableError - es. crash del
    sottoprocesso, anche se is_madmom_available() aveva detto di si'), si
    ripiega su librosa invece di perdere l'intera analisi: non e' colpa
    dell'utente. `on_fallback(msg)`, se dato, viene chiamato con una riga di
    log leggibile in quel caso - il chiamante decide dove mostrarla.

    Ritorna un dict: {'analysis', 'engine_used', 'stability_std', 'suspicious'}
    - stability_std/suspicious sono None/False quando la decisione non e'
    passata da 'auto' (nel ramo 'manual' non c'e' nulla su cui giudicare).
    """
    stability_std, suspicious = None, False

    # BPM scritto a mano => si passa da librosa, sempre. madmom non sa
    # bloccare un tempo: il worker lo trasforma in una finestra del +-10%
    # (min_bpm/max_bpm), e se il tempo che aveva gia' trovato ci sta dentro
    # non si muove - misurato, forzare 123 su un brano rilevato a 127.66
    # lasciava l'analisi IDENTICA. librosa accetta `bpm=` e blocca il tempo
    # esattamente. Quando l'utente ha gia' deciso qual e' il tempo giusto non
    # c'e' piu' niente da indovinare, ed e' proprio indovinarlo il mestiere
    # per cui si sceglie madmom.
    if forced_bpm is not None:
        engine_mode, beat_engine = 'manual', 'librosa'

    if engine_mode == 'auto' and is_madmom_available():
        analysis = generate_song_analysis(audio_path, forced_bpm=forced_bpm, beat_engine='librosa')
        beat_times = [b['_triggerTime'] for b in analysis['beats']]
        recommended, stability_std, suspicious = recommend_engine_from_beats(beat_times)
        # terzo motivo per scegliere madmom, indipendente dalla stabilita' della
        # griglia: librosa puo' semplicemente smettere di produrre beat prima
        # della fine del brano (vedi COVERAGE_GAP_THRESHOLD_S) - una griglia
        # "stabile" ma incompleta supererebbe comunque il controllo sopra.
        tail_gap = analysis['duration'] - beat_times[-1] if beat_times else analysis['duration']
        if tail_gap > COVERAGE_GAP_THRESHOLD_S:
            recommended = 'madmom'
        engine_used = 'librosa'
        if recommended == 'madmom':
            try:
                analysis = generate_song_analysis(audio_path, forced_bpm=forced_bpm, beat_engine='madmom')
                engine_used = 'madmom'
            except MadmomUnavailableError as e:
                if on_fallback:
                    on_fallback(str(e))
    else:
        engine_used = beat_engine
        try:
            analysis = generate_song_analysis(audio_path, forced_bpm=forced_bpm, beat_engine=beat_engine)
        except MadmomUnavailableError as e:
            engine_used = 'librosa'
            if on_fallback:
                on_fallback(str(e))
            analysis = generate_song_analysis(audio_path, forced_bpm=forced_bpm)

    return {'analysis': analysis, 'engine_used': engine_used,
            'stability_std': stability_std, 'suspicious': suspicious}


def build_trackdata_json(analysis, level_map, track_id, wav_relpath):
    """Assembla l'outer/inner esattamente come un trackdata.txt reale di BoxVR."""
    beats = analysis['beats']
    first_beat_offset = beats[0]['_triggerTime'] if beats else 0.0
    # _sectionLabel e' un'annotazione NOSTRA (vedi _tag_segments_with_sections),
    # non un campo del formato: va tolta prima di serializzare, altrimenti
    # comparirebbe in un file che deve restare identico a quelli del gioco.
    for s in analysis['segs']:
        s.pop('_sectionLabel', None)

    inner = {
        '_buildCompleteEvent': {'m_PersistentCalls': {'m_Calls': []}},
        '_isBuilt': True,
        '_dataVersion': DATA_VERSION,
        '_barList': {'_bars': analysis['bars']},
        '_beatList': {'_beats': beats},
        '_segmentList': {'_segments': analysis['segs']},
    }
    _write_levels_into_structure(inner, analysis['segs'], level_map)

    outer = {
        'trackId': {'trackId': track_id},
        'originalFilePath': wav_relpath,
        'originalTrackName': analysis['name'],
        'originalArtist': analysis['artist'],
        'duration': analysis['duration'],
        'bpm': analysis['bpm'],
        'firstBeatOffset': first_beat_offset,
        'locationMode': 0,
        'beatStrucureJSON': json.dumps(inner),
    }
    return outer


def build_wdef_json(track_id, analysis):
    return {
        'trackId': {'trackId': track_id},
        'firstBeatStartDelay': 0.0,
        'tagLibArtist': analysis['artist'],
        'tagLibTitle': analysis['name'],
        'duration': analysis['duration'],
        'bpm': analysis['bpm'],
        'genreMask': 0,
        'audioClipStatus': 0,
    }


def find_no_coverage_gaps(segs, duration, tolerance=0.05):
    """Ritorna gli intervalli [t0, t1] non coperti da nessun segmento - dovrebbe
    essere sempre vuoto per i trackdata generati (a differenza di quelli originali
    del gioco, che invece spesso ne hanno)."""
    gaps = []
    prev_end = 0.0
    for s in sorted(segs, key=lambda s: s['_startTime']):
        if s['_startTime'] - prev_end > tolerance:
            gaps.append((prev_end, s['_startTime']))
        prev_end = max(prev_end, s['_startTime'] + s['_length'])
    if duration - prev_end > tolerance:
        gaps.append((prev_end, duration))
    return gaps


def _prevent_clipping(audio, headroom=0.98):
    """Riscala l'intero buffer se il picco supera il fondo scala, cosi' il wav
    che scriviamo non introduce un clipping digitale netto (tetto piatto,
    percepito come fruscio/distorsione) anche quando l'mp3 sorgente e' gia'
    "caldo". Segnalato in VR il 25/08 su Baddadan ("interferenze audio... dei
    fruscii") - misurato: l'mp3 originale ha un picco di **2.68** (ben oltre
    il fondo scala, tipico di master aggressivi in generi bass-heavy), e il
    nostro wav lo scriveva a 1.0 esatto con oltre 400.000 campioni clippati -
    quasi lo stesso numero della sorgente, quindi la distorsione viene
    per lo più ereditata, non creata da noi, ma non c'e' motivo di
    perpetuarla quando riscalare non costa nulla e non tocca il ritmo/
    contenuto musicale, solo il volume relativo. Non e' specifico di
    Baddadan: misurato anche su Chop Suey! (picco 1.34, 0.26% clippato) e
    Master Of Puppets (1.15, trascurabile) - variabile per brano, quindi
    controllato sempre, non solo quando il sintomo e' stato segnalato."""
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    if peak <= 1.0 or peak == 0.0:
        return audio
    return audio * (headroom / peak)


def sidecar_engine():
    """Importa e ritorna il motore della sidecar (sidecar sandbox/engine.py) -
    usato sia da generate_track() (marker_times) sia dall'anteprima visiva
    nella GUI (_open_visual_preview), cosi' i due punti non rischiano di
    disallinearsi su COME lo si importa.

    Nell'exe compilato (onefile) 'sidecar sandbox/engine.py' e' un file
    aggiunto via --add-data (build_exe.bat), estratto a runtime sotto
    sys._MEIPASS - NON accanto a sys.executable e NON detto che __file__ di
    questo stesso modulo punti li' (i moduli Python puri vivono tipicamente
    nell'archivio PYZ, non estratti su disco come file sciolti). Va risolto
    rispetto a _MEIPASS quando frozen, non rispetto a se stesso - a
    differenza di madmom_worker.exe (_find_madmom_worker sopra), che invece
    e' copiato ACCANTO all'exe da build_exe.bat, non impacchettato dentro."""
    _base = sys._MEIPASS if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS') \
        else os.path.dirname(os.path.abspath(__file__))
    _sidecar_dir = os.path.join(_base, 'sidecar sandbox')
    if _sidecar_dir not in sys.path:
        sys.path.insert(0, _sidecar_dir)
    import engine
    return engine


def generate_track(audio_path, output_folder, punch_ratio=0.5, forced_bpm=None, density=1.0,
                    beat_engine='librosa', structural_segments=True, boundary_bars=None,
                    preset=None, marker_times=None, sidecar_mode=None, exclude_obstacles=False,
                    min_gap_ms=None, log=print):
    """Genera <hash>.trackdata.txt + <hash>.wav + <hash>.wdef.txt in output_folder,
    PIU' la coreografia (serialisedActionList, vedi boxvr_choreo) per lo stesso
    brano - senza questa, il brano generato suonerebbe muto a patch attiva,
    esattamente il buco chiuso 2026-08-23 (vedi [[boxvr-roadmap]]).

    `forced_bpm`: se l'utente ha corretto manualmente il BPM nell'anteprima (vedi
    generate_song_analysis), va riusato qui - altrimenti la generazione batch
    finale ripartirebbe dal BPM rilevato automaticamente, ignorando la
    correzione fatta a schermo. `density`: 0-1, vedi density_to_fractions -
    controlla quanto e' denso il brano generato (per-brano, come punch_ratio -
    prima era un unico valore per l'intera sessione di generazione). `beat_engine`:
    'librosa' (default) o 'madmom' (vedi detect_beats_and_bars). `preset`:
    'light'|'medium'|'high' per la coreografia (vedi boxvr_choreo.INTENSITY_PRESETS),
    None usa il default del modulo coreografia (attualmente 'medium').

    `marker_times` (26/08 notte, prima integrazione della sidecar nel tool
    vero - prima viveva solo in `sidecar sandbox/`, "senza toccare il tool"
    per costruzione/validazione in isolamento): secondi sul brano, marcati a
    mano dall'utente in GUI mentre ascolta. Se dati (anche non vuoti), la
    coreografia usa `engine.build_choreography` invece del solo
    `build_move_actions` - vedi `sidecar sandbox/engine.py` per il
    meccanismo di copertura parziale.

    `sidecar_mode` (27/08, richiesto esplicitamente): None o
    engine.MODE_HARMONIZE (default, comportamento di sempre) / MODE_MARKERS_ONLY
    (niente pattern automatico - solo i marker piu' gli ostacoli, sempre
    autonomi) / MODE_EXTEND (30/08: fedele ai marker DOVE ci sono - stessa
    riduzione di MODE_MARKERS_ONLY in quel tratto - automatico pieno FUORI
    da quel tratto, cosi' un brano marcato solo in parte non resta silenzioso
    nel resto). Ignorato se `marker_times` e' vuoto. (MODE_AUTOMATIC, che
    ignorava i marker per una generazione senza cancellarli, e' stato
    rimosso il 30/08: lo strumento "Automatica" a se stante, separato dalla
    sidecar, produce lo stesso identico risultato.)
    `exclude_obstacles` ("solo hit marker"): se True, un marker non diventa
    mai Squat/Dodge - solo Block o un colpo.

    `min_gap_ms` (30/08, richiesto esplicitamente - slider soglia nella
    sidecar): millisecondi minimi fra due marker consecutivi prima che il
    piu' vicino venga scartato. None usa il default del motore
    (engine.MIN_INPUT_GAP_S, 170ms - il minimo misurato sui 465 workout
    ufficiali)."""
    import boxvr_choreo as _choreo  # importato qui, non in cima al file, per
    # evitare un giro di dipendenza a livello di modulo - boxvr_choreo importa
    # gia' boxvr_generator (in modo altrettanto locale) dal lato opposto

    os.makedirs(output_folder, exist_ok=True)
    analysis = generate_song_analysis(audio_path, forced_bpm=forced_bpm, beat_engine=beat_engine,
                                       structural_segments=structural_segments,
                                       boundary_bars=boundary_bars, log=log)
    max_silence_fraction, max_light_or_silence_fraction = density_to_fractions(density)
    level_map = classify_segments_for_generation(
        analysis, punch_ratio, max_silence_fraction=max_silence_fraction,
        max_light_or_silence_fraction=max_light_or_silence_fraction)

    track_id = uuid.uuid4().hex
    wav_name = f"{track_id}.wav"
    wav_path = os.path.join(output_folder, wav_name)
    sf.write(wav_path, _prevent_clipping(analysis['native_audio']), analysis['sr'])

    trackdata = build_trackdata_json(analysis, level_map, track_id, wav_path.replace('\\', '/'))
    wdef = build_wdef_json(track_id, analysis)

    with open(os.path.join(output_folder, f"{track_id}.trackdata.txt"), 'w', encoding='utf-8') as f:
        json.dump(trackdata, f)
    with open(os.path.join(output_folder, f"{track_id}.wdef.txt"), 'w', encoding='utf-8') as f:
        json.dump(wdef, f)

    if marker_times:
        _engine = sidecar_engine()
        # correct_imprecision=True (30/08): la correzione a 80ms era gia'
        # implementata e testata (sidecar sandbox/engine.py,
        # _snap_marker_to_onset) ma non era mai stata effettivamente accesa
        # in questa chiamata reale - bug di collegamento trovato analizzando
        # la richiesta di una "griglia magnetica" piu' ampia: prima di
        # aggiungerne una nuova, si e' scoperto che quella gia' pronta non
        # girava mai davvero. Corretto qui.
        move_actions = _engine.build_choreography(
            analysis, marker_times, preset=preset or _choreo.DEFAULT_PRESET,
            mode=sidecar_mode or _engine.MODE_HARMONIZE, exclude_obstacles=exclude_obstacles,
            correct_imprecision=True,
            min_gap_s=(min_gap_ms / 1000.0) if min_gap_ms is not None else _engine.MIN_INPUT_GAP_S)
    else:
        move_actions = _choreo.build_move_actions(analysis, preset=preset or _choreo.DEFAULT_PRESET)
    action_list = _choreo.serialize_actions(move_actions, track_id, analysis['bpm'],
                                             wav_path.replace('\\', '/'))
    # La coreografia viene salvata ANCHE su disco, accanto al brano, non solo
    # restituita al chiamante. Motivo (bug reale, 25/08): la coreografia vive
    # dentro la PLAYLIST, non nel trackdata, quindi chi genera senza indicare un
    # nome playlist la calcolava e la buttava via - e se poi installava i brani
    # e accettava "vuoi creare una playlist?", quel percorso
    # (boxvr_install.add_to_playlist) scriveva actionList VUOTE. A patch attiva
    # il gioco non le rigenera piu': brani muti, e in piu' la schermata delle
    # playlist va in NullReferenceException e non ne mostra NESSUNA (osservato
    # sul PC dell'utente con la playlist "Media"). Con il file qui accanto
    # qualunque percorso di installazione puo' recuperare la coreografia vera.
    with open(os.path.join(output_folder, f"{track_id}.actionlist.json"), 'w',
              encoding='utf-8') as f:
        json.dump(action_list, f)

    gaps = find_no_coverage_gaps(analysis['segs'], analysis['duration'])
    if gaps:
        log(f"ATTENZIONE: {len(gaps)} buchi residui di copertura in {analysis['name']} (non dovrebbe succedere)")
    seg_label = "sezioni musicali" if analysis.get('seg_mode') == 'structural' else "blocchi fissi"
    log(f"Generato {analysis['name']} - {analysis['artist']} "
        f"({analysis['bpm']:.1f} BPM, {len(analysis['segs'])} segmenti su {seg_label}, "
        f"{len(analysis['beats'])} beat) -> {track_id}")
    log(f"  coreografia: {_choreo.describe(move_actions, analysis['duration'])}")
    return {'track_id': track_id, 'analysis': analysis, 'level_map': level_map,
            'output_folder': output_folder, 'gaps': gaps, 'action_list': action_list}


def find_audio_files(folder):
    files = []
    for ext in AUDIO_EXTENSIONS:
        files.extend(glob.glob(os.path.join(folder, f'*{ext}')))
    return sorted(files)


def _split_by_duration(entries, base_name, max_minutes):
    """Spezza una lista di brani in gruppi che non superano `max_minutes`,
    mantenendo l'ordine. Ritorna [(nome, gruppo), ...] - un solo gruppo col
    nome originale se non serve spezzare (o se max_minutes e' None).

    Un brano piu' lungo del limite finisce comunque da solo nel suo gruppo:
    meglio una playlist fuori misura che un brano scartato in silenzio.
    """
    if not max_minutes or sum(e['duration'] for e in entries) / 60 <= max_minutes:
        return [(base_name, entries)]

    limit = max_minutes * 60
    groups, cur, cur_dur = [], [], 0.0
    for e in entries:
        if cur and cur_dur + e['duration'] > limit:
            groups.append(cur)
            cur, cur_dur = [], 0.0
        cur.append(e)
        cur_dur += e['duration']
    if cur:
        groups.append(cur)
    return [(f"{base_name} {i}", g) for i, g in enumerate(groups, 1)]


def generate_songs(items, output_folder, dry_run=False, playlist_name=None,
                    max_playlist_minutes=None, log=print):
    """Come generate_folder, ma su una lista esplicita di file audio (dict con
    almeno 'audio_path'; 'ratio', 'density' e 'preset' opzionali, default
    0.5/1.0/'medium') - permette di aggregare brani trascinati da cartelle
    diverse in un'unica sessione. Densita' (vedi density_to_fractions) e
    preset di intensita' della coreografia (vedi boxvr_choreo.INTENSITY_PRESETS)
    sono per-brano esattamente come il rapporto pugni/misto, non un unico
    valore per l'intera sessione di generazione.

    `playlist_name`: se valorizzato, scrive anche un .workoutplaylist.txt che
    raggruppa i brani generati in questa sessione, con le coreografie gia'
    dentro - senza, i brani restano file singoli da assemblare a mano.
    `max_playlist_minutes`: **None di default, cioe' nessun limite** - una
    playlist lunga quanto i brani che ci metti dentro e' il comportamento
    normale. Se valorizzato, spezza in piu' file numerati ("Nome 1",
    "Nome 2", ...) mantenendo l'ordine originale: serve a chi vuole
    deliberatamente allenamenti piu' corti (es. per provare dei brani senza
    farsi un'ora intera), non e' una regola imposta dal tool.
    """
    os.makedirs(output_folder, exist_ok=True)

    if not items:
        log("Nessun file audio da generare.")
        return {'n_ok': 0, 'n_errors': 0, 'output_folder': output_folder, 'track_ids': []}

    n_ok, n_errors = 0, 0
    entries = []
    track_ids = []
    for i, item in enumerate(items, 1):
        path = item['audio_path']
        try:
            ratio = item.get('ratio', 0.5)
            density = item.get('density', 1.0)
            forced_bpm = item.get('forced_bpm')
            beat_engine = item.get('beat_engine', 'librosa')
            structural = item.get('structural_segments', True)
            boundary_bars = item.get('boundary_bars')
            preset = item.get('preset')
            marker_times = item.get('marker_times')
            sidecar_mode = item.get('sidecar_mode')
            exclude_obstacles = item.get('exclude_obstacles', False)
            min_gap_ms = item.get('min_gap_ms')
            if dry_run:
                analysis = generate_song_analysis(path, forced_bpm=forced_bpm, beat_engine=beat_engine,
                                                   structural_segments=structural,
                                                   boundary_bars=boundary_bars, log=log)
                gaps = find_no_coverage_gaps(analysis['segs'], analysis['duration'])
                log(f"[{i}/{len(items)}] DRY-RUN {analysis['name']}: {len(analysis['segs'])} segmenti "
                    f"({analysis['seg_mode']}), {len(gaps)} buchi")
            else:
                res = generate_track(path, output_folder, punch_ratio=ratio, forced_bpm=forced_bpm,
                                      density=density, beat_engine=beat_engine,
                                      structural_segments=structural, boundary_bars=boundary_bars,
                                      preset=preset, marker_times=marker_times,
                                      sidecar_mode=sidecar_mode, exclude_obstacles=exclude_obstacles,
                                      min_gap_ms=min_gap_ms, log=log)
                entries.append({'track_id': res['track_id'],
                                'duration': res['analysis']['duration'],
                                'action_list': res['action_list']})
                track_ids.append(res['track_id'])
                # prefisso "[i/n]" riconosciuto dalla GUI per far avanzare la
                # barra di progresso in tempo reale (vedi boxvr_fixer_gui._log)
                # - senza, il caso di successo (a differenza di DRY-RUN/ERRORE
                # sopra/sotto) non la faceva muovere fino alla fine dell'intera
                # sessione, segnalato 2026-08-24 guardando il codice.
                log(f"[{i}/{len(items)}] OK {res['analysis']['name']}: "
                    f"{len(res['analysis']['segs'])} segmenti")
            n_ok += 1
        except Exception as e:
            n_errors += 1
            log(f"[{i}/{len(items)}] ERRORE {os.path.basename(path)}: {e}")

    playlist_paths = []
    if entries and playlist_name and not dry_run:
        import boxvr_choreo as _choreo
        try:
            for name, chunk in _split_by_duration(entries, playlist_name, max_playlist_minutes):
                p = _choreo.write_playlist(name, chunk, out_dir=output_folder)
                playlist_paths.append(p)
                mins = sum(e['duration'] for e in chunk) / 60
                log(f"Playlist scritta: {os.path.basename(p)} ({len(chunk)} brani, {mins:.0f} min)")
        except Exception as e:
            log(f"ATTENZIONE: playlist non scritta ({e}) - i singoli brani sono comunque generati.")
    playlist_path = playlist_paths[0] if playlist_paths else None

    log(f"\nFATTO. {n_ok} generati, {n_errors} errori.")
    if not dry_run:
        log(f"File in: {output_folder}")
        log("Per usarli in gioco, copia manualmente <hash>.trackdata.txt + <hash>.wav in "
            "%AppData%/LocalLow/FITXR/BoxVR/Playlists/TrackData e <hash>.wdef.txt in "
            "%AppData%/LocalLow/FITXR/BoxVR/Playlists/TrackDefinitions (fai un backup prima).")
        if playlist_paths:
            # Non piu' "spostala a mano": «Installa in BoxVR» le copia. La
            # riga precedente diceva di farlo a mano ed e' rimasta vera
            # troppo a lungo - la playlist restava nei generati e in gioco
            # non compariva niente.
            log("Le %d playlist vanno in "
                "%%AppData%%/LocalLow/FITXR/BoxVR/Playlists/WorkoutPlaylists/BoxVR: "
                "le copia \"Installa in BoxVR\" insieme ai brani. "
                "Ricorda che la coreografia scritta ha effetto SOLO col gioco patchato."
                % len(playlist_paths))
    # `track_ids`: SOLO gli id costruiti in QUESTA chiamata, non tutto cio' che
    # potrebbe gia' esserci in output_folder da sessioni precedenti - vedi
    # boxvr_install.files_for_track_ids, che e' il motivo per cui esiste.
    return {'n_ok': n_ok, 'n_errors': n_errors, 'output_folder': output_folder,
            # `playlist_path` resta la prima, per i chiamanti gia' scritti.
            # Ma con un limite di durata le playlist sono PIU' DI UNA
            # (spezzate apposta), e chi deve installarle le vuole tutte: la
            # versione precedente ne nominava una sola, e le altre non
            # esistevano per nessuno tranne che sul disco.
            'playlist_path': playlist_path, 'playlist_paths': list(playlist_paths),
            'track_ids': track_ids}
