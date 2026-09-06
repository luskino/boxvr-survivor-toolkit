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
BoxVR Level Fixer - GUI con drag & drop, anteprima timeline, preset pugni/misto
e generazione trackdata da zero a partire da mp3/wav
==================================================================================
Due schede:
  - "Correggi esistenti": corregge l'energyLevel delle coppie <trackId>.txt +
    <trackId>.wav gia' presenti in TrackData (come prima).
  - "Genera da MP3": genera da zero trackdata.txt + wav + wdef.txt a partire da
    file mp3/wav, con copertura completa della canzone (nessun buco).

Si possono trascinare sia cartelle che singoli file, anche piu' volte: ogni drop
si AGGIUNGE all'elenco corrente invece di sostituirlo. Interfaccia in stile
"Apple Control Center" (card arrotondate, badge circolari, switch/slider stile
iOS) via customtkinter, con font Poppins incorporato (caricato privatamente,
non serve che sia installato sul PC di chi usa l'exe). Interfaccia disponibile
in italiano/inglese.

Dipendenze:
    pip install numpy scipy tkinterdnd2 sounddevice librosa soundfile mutagen customtkinter

Per creare l'eseguibile:
    pip install pyinstaller
    build_exe.bat
"""

import bisect
import ctypes
import glob
import json
import itertools
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import numpy as np
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageTk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

try:
    import sounddevice as sd
    HAS_AUDIO = True
except Exception:
    sd = None
    HAS_AUDIO = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boxvr_fixer import (
    compute_song_analysis, classify_segments_with_preset, process_songs_with_presets,
    load_wav_for_playback, find_track_id, read_correct_item,
)
from boxvr_generator import (
    classify_segments_for_generation, generate_songs,
    find_audio_files, read_generate_item, AUDIO_EXTENSIONS, density_to_fractions,
    is_madmom_available, analyze_for_generate, bpm_search_url,
    set_game_dir as gen_set_game_dir, sidecar_engine,
)
import boxvr_patch
import boxvr_install
from version import VERSION


def _base_dir():
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


# -- persistenza preferenze tra sessioni -------------------------------------
# %APPDATA% (non la cartella dell'exe, che con --onefile e' una directory temporanea
# diversa ad ogni avvio) - unico posto scrivibile senza permessi admin e stabile
# tra un avvio e l'altro dell'eseguibile frozen.
DEFAULT_SETTINGS = {
    'lang': 'it',
    'theme': 'dark',
    'margin': 0.12,
    'last_browse_dir_correct': None,
    'last_browse_dir_generate': None,
    # Cartella di installazione di BoxVR, scelta a mano dall'utente al primo
    # avvio. Non e' solo comodita': serve per i tool di segmentazione, per la
    # patch e per leggere i dati del gioco, e il rilevamento automatico via
    # librerie Steam non trova nulla per le edizioni Oculus/Viveport.
    'game_dir': None,
}


def _settings_path():
    base = os.environ.get('APPDATA') or _base_dir()
    d = os.path.join(base, 'BoxVR Level Fixer')
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return os.path.join(d, 'settings.json')


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(_settings_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        for k in DEFAULT_SETTINGS:
            if k in data:
                settings[k] = data[k]
    except Exception:
        pass
    return settings


def save_settings(settings):
    """Non deve MAI sollevare: e' chiamata da una decina di punti diversi
    della GUI, incluso il gestore di chiusura finestra - un'eccezione qui
    interrompe silenziosamente qualunque cosa la chiami (nell'exe, senza
    console, senza nessun errore visibile). Prima catturava solo OSError,
    non TypeError - un valore non serializzabile in `settings` (es. un numpy
    float invece di un float nativo, facile in un codebase che usa numpy
    ovunque) avrebbe interrotto il chiamante a meta', root.destroy() incluso
    quando chiamata da _on_close - segnalato dall'utente 25/08 come 'il tool
    non si chiude piu''."""
    try:
        with open(_settings_path(), 'w', encoding='utf-8') as f:
            json.dump(settings, f)
    except (OSError, TypeError, ValueError):
        pass


GAME_EXE_NAME = 'boxvr.exe'   # nome ESATTO verificato dell'eseguibile del gioco
# (E:\...\BOXVR\BoxVR.exe su Steam) - non una supposizione.


def _is_boxvr_running():
    """Controlla se il PROCESSO DEL GIOCO (BoxVR.exe, nome esatto) e' in
    esecuzione, prima di scrivere nella sua libreria live - se il gioco e'
    aperto i file appena copiati potrebbero non essere raccolti finche' non
    lo si riavvia, o si potrebbero creare conflitti di scrittura.

    Bug reale, in due versioni successive:
    1. Il primo controllo cercava "boxvr" come SOTTOSTRINGA in tutto l'output
       di tasklist - risultato, il tool rilevava se STESSO come "il gioco in
       esecuzione" (il proprio eseguibile si chiama
       "BoxVR_Level_Fixer_v...exe", contiene "boxvr").
    2. Il fix di allora escludeva solo il PID del processo CORRENTE, ma la
       sottostringa restava - una copia PRECEDENTE del tool ancora aperta (per
       esempio se non si chiude correttamente, vedi il bug della finestra che
       non si chiude) ha un PID diverso e continuava a far scattare il falso
       positivo, sempre, ogni volta - segnalato dall'utente 25/08.

    Ora si confronta il nome immagine con quello ESATTO del gioco, non una
    sottostringa: nessuna copia di questo stesso tool, per quanti PID diversi
    possa avere in giro, puo' piu' confondersi col gioco vero."""
    if sys.platform != 'win32':
        return False
    try:
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        out = subprocess.run(
            ['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True,
            timeout=5, creationflags=flags,
        )
        for line in out.stdout.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) < 1:
                continue
            image_name = parts[0]
            if image_name.lower() == GAME_EXE_NAME:
                return True
        return False
    except Exception:
        return False


def _load_private_fonts():
    """Carica Poppins dal sottocartella fonts/ senza bisogno che sia installato
    sul sistema (AddFontResourceEx con FR_PRIVATE - solo per questo processo)."""
    fonts_dir = os.path.join(_base_dir(), 'fonts')
    if sys.platform != 'win32' or not os.path.isdir(fonts_dir):
        return
    FR_PRIVATE = 0x10
    for fname in os.listdir(fonts_dir):
        if fname.lower().endswith('.ttf'):
            try:
                ctypes.windll.gdi32.AddFontResourceExW(os.path.join(fonts_dir, fname), FR_PRIVATE, 0)
            except Exception:
                pass


_load_private_fonts()

FONT_REGULAR = "Poppins"
FONT_MEDIUM = "Poppins Medium"
FONT_SEMIBOLD = "Poppins SemiBold"

# Palette ispirata al Control Center di iOS: sfondo quasi nero, card grigio
# neutro (non potendo fare vero "vetro sfumato" in Tkinter, si simula la
# profondita' con livelli di grigio via via piu' chiari), accenti vivaci.
#
# Ogni costante e' una tupla (chiaro, scuro): i widget CTk (CTkFrame/CTkButton/
# CTkLabel/...) accettano nativamente questa forma per fg_color/text_color/
# hover_color/border_color e si ricolorano da soli quando cambia
# ctk.set_appearance_mode("light"/"dark") - niente da ricablare widget per
# widget. I pochi tk.Canvas/tk.Label "grezzi" (timeline, pallini, sparkline,
# tooltip, la finestra root stessa) NON hanno questo comportamento automatico:
# per quelli si usa resolve_color(token) per risolvere la tupla nel colore effettivo del
# tema corrente, e li si riconfigura esplicitamente al cambio tema (vedi
# refresh_theme più sotto).
# Palette v2, "SaaS dashboard moderno" - sostituisce il precedente monocromo
# ispirato al Control Center (grigi + un solo blu iOS) su richiesta dell'utente,
# che ha fornito due reference dirette (una dashboard vendite viola/indigo con
# card bianche su sfondo lavanda, una seconda con gradiente lavanda->menta e
# badge circolari colorati). Niente gradienti veri (fragili da rendere bene coi
# widget CTk/tk grezzi che questa app usa gia' - vedi le note DPI-scaling piu'
# sotto in questo file): la stessa sensazione "moderna" viene invece da un
# accento indigo/viola deciso + una seconda famiglia teal/corallo, sfondo chiaro
# leggermente lavanda invece di grigio neutro, e raggi piu' morbidi sulle card.
BG = ("#EDEDF7", "#0b0b0f")
CARD = ("#ffffff", "#1c1c1e")
CARD2 = ("#F3F3FA", "#28282b")
CARD3 = ("#E7E7F3", "#3a3a3d")
CARD_HOVER = ("#DADAED", "#48484b")
SHADOW_TONE = ("#9494B8", "#4a4a52")     # tinta base delle ombre morbide sotto le card principali - in
                                          # scuro sfumare verso il nero e' quasi inutile (lo sfondo e'
                                          # gia' quasi nero, zero contrasto: #000 su #0b0b0f e' invisibile);
                                          # i design system scuri (Material incluso) rendono l'elevazione
                                          # con un tono piu' CHIARO che "emerge" dal fondo, non piu' scuro -
                                          # qui una grigio medio, piu' chiaro dello sfondo ma piu' scuro
                                          # delle card stesse, stesso principio.
BORDER = ("#C7C7DE", "#55555a")          # bordo dei bottoni "outline" - CARD3 aveva troppo poco
                                          # contrasto contro lo sfondo card/bianco, quasi invisibile
ACCENT = ("#6C63FF", "#8A82FF")          # indigo/viola dalle reference (era il blu iOS)
ACCENT_HOVER = ("#8078FF", "#a39cff")
ACCENT_SOFT = ("#EDEBFF", "#241f4a")
ACTION_ACCENT = ("#F4506B", "#FF5470")   # corallo (era rosso-arancio iOS)
ACTION_ACCENT_HOVER = ("#FF6B83", "#ff7d92")
HIGHLIGHT = ("#0EA5A5", "#2DD4D4")       # teal, seconda famiglia della reference
SUCCESS = ("#22C55E", "#30d158")
# Fondo tenue per gli avvisi bloccanti (banner "manca la patch"): abbastanza
# caldo da leggersi come richiamo, non cosi' saturo da competere con
# ACTION_ACCENT del pulsante che ci sta dentro.
WARNING_SOFT = ("#FDF0D5", "#3A2E14")
# Testo di avviso su fondo normale (non su WARNING_SOFT): scuro abbastanza da
# leggersi sul chiaro, chiaro abbastanza da leggersi sullo scuro - serve alla
# nota "Rilevata Patch" sulla card disabilitata della schermata di scelta.
WARNING = ("#B45309", "#F0A868")
TEXT = ("#1c1c1e", "#ffffff")
SUBTEXT = ("#6B7099", "#98989d")         # grigio con una punta di lavanda, non piu' neutro

# Sfondo del canvas della timeline/log: resta scelto per un buon contrasto con
# LEVEL_COLORS (mai theme-tupled: sono pensati per leggersi bene su entrambi gli
# sfondi) - "quasi bianco" in chiaro invece di "quasi nero", non un mezzo grigio.
TIMELINE_BG = ("#EDEDF7", "#050507")
LOG_BG = ("#EDEDF7", "#050507")
LOG_TEXT = ("#1c1c1e", "#c8d0e0")

# Palette omogenea per le 4 fasce, aggiornata sulla stessa famiglia indigo/blu/
# corallo delle reference (Silenzio=lavanda spenta, Leggero=blu, Pugni=corallo
# - la fascia piu' intensa, Misto=indigo come l'accento principale, per legare
# visivamente "varieta'" al colore del brand). Non theme-tupled deliberatamente:
# LEVEL_COLORS e' sempre leggibile su TIMELINE_BG in entrambe le varianti
# (verificato).
LEVEL_COLORS = {0: "#9CA3C4", 1: "#4A9DE0", 2: "#F4506B", 3: "#6C63FF"}
ENERGY_CURVE_COLOR = ("#0EA5A5", "#2DD4D4")
# Stesso ambra dell'anello marker nell'anteprima visiva (boxvr_visual_preview.
# MARKER_FLASH_COLOR) - coerenza visiva fra le due viste dello stesso dato.
# Non theme-tupled per lo stesso motivo di LEVEL_COLORS: resta leggibile su
# TIMELINE_BG in entrambi i temi.
MARKER_TICK_COLOR = "#ffd60a"

# Range dello slider soglia minima fra due marker (30/08). Il default e il
# minimo "reale" marcato sullo slider sono lo stesso valore
# (sidecar_engine().MIN_INPUT_GAP_S in ms) - duplicato qui come intero perche'
# CTkSlider ha bisogno del valore prima ancora che un song sia selezionato;
# _refresh_sidecar_panel confronta comunque contro quello vero del motore per
# calcolare i marker scartati, non contro questa costante.
SIDECAR_MIN_GAP_MIN_MS = 50
SIDECAR_MIN_GAP_MAX_MS = 300
SIDECAR_MIN_GAP_DEFAULT_MS = 170
SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# Larghezza fissa della colonna sinistra (elenco brani) nel layout orizzontale:
# giusto lo spazio che serve al contenuto delle righe (titolo+artista+bpm+
# sparkline+preset+padding), senza lasciare spazio vuoto a destra della tabella
# come succedeva quando l'elenco occupava tutta la larghezza della finestra.
LEFT_COL_WIDTH = 750

# Altezza (px) riservata all'asse temporale in fondo alla timeline principale, e
# risoluzione (n. colonne pre-calcolate, indipendente dalla larghezza a schermo)
# del profilo d'ampiezza cache-ato per brano - vedi _draw_time_axis/_get_waveform_peaks.
# Misurato a runtime (non stimato): un item di testo "00:00" a font=(FONT_REGULAR, 8)
# su questa macchina occupa realmente ~23px di altezza (bbox del canvas), molto
# piu' degli ~11-14px che il punteggio "8" farebbe supporre - stesso scaling DPI
# gia' visto altrove in questo file. AXIS_HEIGHT deve contenere quell'altezza
# reale per intero, altrimenti il canvas (che ritaglia tutto cio' che sta oltre
# la propria altezza) taglia via la parte inferiore delle cifre.
AXIS_HEIGHT = 32
WAVEFORM_RESOLUTION = 2000


def resolve_color(token):
    """Risolve una tupla (chiaro, scuro) nel colore effettivo del tema corrente -
    serve solo ai widget tk "grezzi" (Canvas/Label/Tk) che CTk non ricolora da
    solo. Se non e' una tupla (es. un token non theme-aware) lo ritorna intatto."""
    if isinstance(token, tuple):
        return token[0] if ctk.get_appearance_mode() == "Light" else token[1]
    return token


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def ui_font(size, weight="medium"):
    # Default "medium" (non "regular"): il Poppins Regular a corpo piccolo
    # risultava troppo sottile/poco leggibile su schermo secondo il feedback -
    # "medium" resta comunque piu' leggero di "semibold" (riservato ai titoli).
    family = {"regular": FONT_REGULAR, "medium": FONT_MEDIUM, "semibold": FONT_SEMIBOLD}.get(weight, FONT_REGULAR)
    return ctk.CTkFont(family=family, size=size)


STRINGS = {
    'it': {
        'app_title': "BoxVR Level Fixer",
        'app_subtitle': "Strumento di analisi e correzione dei livelli BoxVR",
        'tab_correct': "Correggi esistenti",
        'tab_generate': "Genera da MP3",
        'subtitle_correct': "Trascina cartelle o coppie di file .txt + .wav da correggere (anche più volte)",
        'subtitle_generate': "Trascina cartelle o file mp3/wav da cui generare i trackdata (anche più volte)",
        'drop_hint': "Trascina qui cartelle o file\noppure usa \"Scegli cartella...\"",
        'browse_btn': "Scegli cartella...",
        'clear_list_btn': "Svuota elenco",
        'open_boxvr_btn': "Cartella BoxVR",
        'warn_boxvr_folder_missing': "Cartella non trovata:\n{folder}\n\nBoxVR non risulta installato su questo PC (o non ha ancora importato nessun brano).",
        'no_folder': "Nessun brano aggiunto",
        'folder_selected': "{n} brani nell'elenco",
        'folder_selected_progress': "{n} brani nell'elenco · {done}/{n} analizzati",
        'select_song_prompt': "Seleziona una canzone dall'elenco",
        'track_id_label': "ID: {track_id}",
        'timeline_original_label': "Struttura eventi da BoxVR",
        'timeline_corrected_label': "Struttura eventi corretta",
        'timeline_tooltip': "{phase} — {n} eventi",
        'legend_0': "Silenzio", 'legend_1': "Leggero", 'legend_2': "Pugni", 'legend_3': "Misto",
        'col_title': "Titolo", 'col_artist': "Artista", 'col_bpm': "BPM", 'col_preset': "Pugni %",
        'punch_ratio_label': "Solo eventi pugni",
        'punch_ratio_chip': "{pct}% pugni",
        'play': "▶  Play", 'pause': "⏸  Pausa", 'audio_unavailable': "Audio non disponibile",
        'visual_btn': "👁  Anteprima visiva",
        'visual_preview_empty': "Questo brano non produce nessun colpo con il preset scelto.",
        'visual_preview_no_audio': "Audio non caricato per questo brano: attendi la fine dell'analisi.",
        'visual_preview_error': "Anteprima visiva non disponibile: {msg}",
        'analyzing': "Analisi in corso...",
        'analysis_error': "Errore analisi: {msg}",
        'audio_device_error': "Nessun dispositivo audio disponibile per la riproduzione:\n{msg}",
        'log_audio_device_error': "Play non disponibile: nessun dispositivo audio ({msg})",
        'phase': "Fase: {level}",
        'margin_label': "Margine di confidenza",
        'margin_info_tooltip': "Quanto deve essere sicura l'analisi prima di correggere un livello. Più alto = correzioni più caute (solo quando l'analisi è molto sicura, il resto resta come l'ha calcolato il gioco). Più basso = più correzioni, ma alcune meno certe.",
        'density_label': "Livelli energia trackdata (solo a patch disattivata)",
        'density_legacy_tooltip': ("Questo slider e il rapporto pugni/misto scrivono i livelli di energia "
                                    "nel trackdata, che servono SOLO quando il gioco NON è patchato: in quel "
                                    "caso è BoxVR a scegliere i colpi da sé, guardando questi livelli.\n\n"
                                    "Con la patch attiva (necessaria per generare) il gioco li ignora, e anche "
                                    "la coreografia scritta non li usa: parte direttamente dalla curva di "
                                    "energia del brano. Quindi qui non cambiano ciò che giochi — per quello "
                                    "usa \"Intensità coreografia\" qui sotto.\n\n"
                                    "Restano utili solo se un giorno ripristini il gioco e vuoi che i brani "
                                    "generati funzionino anche così."),
        'density_real_marker_tooltip': "▲ = densità media misurata sui trackdata reali di BoxVR",
        'choreo_preset_label': "Intensità coreografia",
        'choreo_light': "Leggero",
        'choreo_medium': "Medio",
        'choreo_high': "Intenso",
        'choreo_preset_tooltip': ("Quanti e quali colpi vengono scritti nella coreografia: Leggero "
                                   "salta i passaggi più complessi, Intenso li rende per intero.\n\n"
                                   "Diverso dalla densità qui sopra, che governa i livelli di energia "
                                   "del brano: questo governa cosa si gioca davvero, e ha effetto "
                                   "solo con il gioco patchato."),
        'choreo_epm_hint': "~{epm} colpi/min (di solito {lo}-{hi}) · BoxVR ufficiale ~{official}",
        'choreo_epm_tooltip': ("Quanti colpi al minuto produce in media questo preset, MISURATO sulla "
                                "coreografia davvero generata (26/08, su 6 brani), non un valore "
                                "teorico.\n\nL'intervallo fra parentesi è reale e ampio: dipende molto "
                                "dal brano — un pezzo fitto e regolare produce molti più colpi di uno "
                                "lento, a parità di preset.\n\nIl riferimento BoxVR ufficiale (~82/min) "
                                "è misurato sulla coreografia vera di 15 brani ufficiali del gioco, "
                                "estratta dai suoi stessi file."),
        'generate_tool_automatic': "Automatica",
        'generate_tool_sidecar': "Sidecar",
        'sidecar_title': "Sidecar — marca tu gli accenti (sperimentale)",
        'sidecar_tooltip': ("Ascolta il brano e premi l'area MARCA (o i tasti F/K sulla tastiera) quando "
                             "vuoi un colpo lì: mai la corsia, mai il tipo — li decide comunque "
                             "l'algoritmo, come già fa con gli accenti veri dell'audio.\n\nI tuoi marker "
                             "sono una BASE, non serve coprire tutto il brano: la generazione automatica "
                             "riempie comunque il resto, e un tuo marker vince sempre in caso di "
                             "conflitto.\n\n\"Registra\" continua SEMPRE dal punto in cui sei posizionato "
                             "sulla timeline, scartando solo i marker da lì in poi — comodo per rifare un "
                             "punto che non ti è piaciuto senza perdere il resto. \"Ferma\" mette in pausa "
                             "senza toccare nulla. Per azzerare tutto il brano usa \"Resetta\"; per togliere "
                             "solo i marker lasciando modalità/soglia com'erano usa \"Cancella\"."),
        'sidecar_record_btn': "Registra",
        'sidecar_stop_btn': "Ferma",
        'sidecar_mark_area': "MARCA",
        'sidecar_clear_btn': "Cancella",
        'sidecar_reset_btn': "Resetta",
        'sidecar_count': "{n} marker registrati",
        'sidecar_usage_note_active': "I marker registrati vengono usati automaticamente in generazione. Per tornare all'automatico, premi Cancella.",
        'sidecar_usage_note_empty': "Nessun marker: la generazione userà solo l'algoritmo automatico.",
        'sidecar_mode_label': "Modalità",
        'sidecar_mode_markers_only': "Solo marker",
        'sidecar_mode_harmonize': "Armonizza",
        'sidecar_mode_extend': "Estendi",
        'sidecar_mode_tooltip': ("Quanto pesano i tuoi marker rispetto alla coreografia automatica:\n\n"
                                  "• Armonizza (di solito): il resto del brano lo scrive comunque "
                                  "l'algoritmo per intero, i tuoi marker vincono solo dove cadono.\n\n"
                                  "• Solo marker: nessun pattern automatico — il resto del brano resta "
                                  "silenzioso, TRANNE gli ostacoli (Squat/Schivata), che l'algoritmo "
                                  "continua a piazzare da solo indipendentemente dai marker (non li marchi "
                                  "mai tu, quindi il workout ne ha comunque bisogno per variare).\n\n"
                                  "• Estendi: se marchi solo UNA PARTE del brano (es. il primo minuto e "
                                  "mezzo di tre), dentro quel tratto vale la stessa regola di \"Solo "
                                  "marker\" (nessun colpo automatico non richiesto si infila fra i tuoi "
                                  "marker), ma FUORI da quel tratto l'algoritmo genera per intero — il "
                                  "resto del brano non resta silenzioso.\n\n"
                                  "Per confrontare rapidamente con/senza i tuoi marker, senza doverli "
                                  "cancellare, passa allo strumento \"Automatica\" qui sopra — i marker "
                                  "restano salvati su questo brano anche mentre non lo usi."),
        'sidecar_exclude_label': "Solo hit marker (mai ostacoli sui marker)",
        'sidecar_exclude_tooltip': ("Quando attivo, un istante che marchi non diventa mai Squat o "
                                     "Schivata — solo Scudo o un colpo. Gli ostacoli restano sempre una "
                                     "scelta autonoma dell'algoritmo, mai imposta su un tuo marker — vale "
                                     "anche in modalità \"Solo marker\": anche lì gli ostacoli continuano "
                                     "a comparire da soli, indipendentemente da dove marchi."),
        'sidecar_min_gap_label': "Soglia minima fra i colpi",
        'sidecar_min_gap_tooltip': ("Due marker più vicini di questa soglia vengono uniti: sopravvive solo "
                                     "il primo. Il valore di default (170ms) è il minimo assoluto mai "
                                     "misurato sui 465 workout ufficiali di BoxVR — nessun brano reale del "
                                     "gioco ha mai avuto due colpi più vicini di così. Abbassarlo permette "
                                     "colpi più fitti di qualunque cosa il gioco abbia mai generato davvero: "
                                     "usalo consapevolmente, guardando quanti marker verrebbero scartati "
                                     "prima di decidere."),
        'sidecar_min_gap_real_marker_tooltip': "170ms — il minimo assoluto misurato sui 465 workout ufficiali di BoxVR",
        'sidecar_min_gap_dropped': "A questa soglia, {dropped} di {n} marker verrebbero uniti al precedente",
        'sidecar_min_gap_none_dropped': "Nessun marker troppo vicino a questa soglia",
        'risky_playlists_msg': ("Attenzione: alcune playlist installate hanno brani senza "
                                 "coreografia — a patch attiva suonano MUTI:\n\n{list}\n\n"
                                 "Rigenerali o rimuovili dalla playlist."),
        'risky_playlists_more': "e altre {n}",
        'dry_run': "Solo report (non modificare i file)",
        'replace_originals_label': "Sostituisci gli originali (con backup automatico)",
        'replace_originals_info_tooltip': "Sovrascrive direttamente i file .txt originali invece di salvarli in una cartella \"corretti\" separata da spostare a mano. Prima di ogni sovrascrittura viene creata una copia di backup con data e ora accanto ai file originali (cartella \"backup_correzioni\"), così puoi sempre tornare alla versione precedente.",
        'playlist_duration_label': "Durata massima playlist (minuti)",
        'playlist_duration_placeholder': "nessun limite",
        'playlist_duration_tooltip': "Se la somma dei brani generati in questa sessione supera questo tempo, la playlist viene spezzata in più file numerati (\"Nome 1\", \"Nome 2\", ...) invece di uno solo lunghissimo — utile per allenamenti brevi di proposito.\n\nVuoto = nessun limite: una playlist lunga quanto i brani che ci metti dentro, il comportamento di sempre.",
        'log_playlist_duration_invalid': "Durata playlist \"{value}\" non è un numero valido, ignorata (nessun limite applicato).",
        'run_btn_correct': "Avvia correzione",
        'run_btn_generate': "Genera",
        'open_btn': "Apri cartella risultati",
        'log_label': "Log",
        'note_no_dnd': "Nota: modulo tkinterdnd2 non trovato, usa 'Scegli cartella...'.",
        'note_no_audio': "Nota: modulo sounddevice non trovato, l'anteprima audio e' disabilitata (la timeline resta comunque visibile).",
        'warn_invalid_drop': "Trascina una cartella o dei file validi.",
        'warn_no_pairs': "Nessuna coppia .txt + .wav trovata.",
        'warn_no_audio_files': "Nessun file mp3/wav trovato.",
        'warn_wrong_tab_mp3': ("Hai trascinato un file mp3 in questa scheda: con un mp3 si può solo generare "
                                "un trackdata da zero. Passa alla scheda \"Genera da MP3\"."),
        'log_added_n': "Aggiunti {n} nuovi brani (totale {total}).",
        'log_analysis_error': "Errore analisi {name}: {msg}",
        'log_start_correct': "Avvio correzione su {n} brani",
        'log_start_generate': "Avvio generazione su {n} brani",
        'log_params': "Margine: {margin}  |  Solo report: {dry_run}",
        'log_preset_line': "  {name} — {artist}: {preset}",
        'log_error': "ERRORE: {message}",
        'done_summary_correct': ("Fatto!\n\nBrani processati: {n_ok}\nCon correzioni: {n_changed}\n"
                                  "Correzioni totali: {n_total_changes}\nSaltati (wav mancante): {n_skipped}\n"
                                  "Errori: {n_errors}\n\nRisultati in:\n{output_folder}"),
        'done_summary_generate': ("Fatto!\n\nBrani generati: {n_ok}\nErrori: {n_errors}\n\n"
                                   "Risultati in:\n{output_folder}\n\n"
                                   "Per usarli in gioco, copia manualmente <hash>.trackdata.txt + <hash>.wav in\n"
                                   "%AppData%/LocalLow/FITXR/BoxVR/Playlists/TrackData\n"
                                   "e <hash>.wdef.txt in\n"
                                   "%AppData%/LocalLow/FITXR/BoxVR/Playlists/TrackDefinitions\n"
                                   "(fai un backup prima)."),
        'warn_no_txt': "Nessun brano da elaborare.",
        'error_prefix': "Si e' verificato un errore:\n{message}",
        'browse_dialog_title_correct': "Scegli la cartella con i file .txt e .wav",
        'browse_dialog_title_generate': "Scegli la cartella con i file mp3/wav",
        'info_btn': "Dove vanno i file",
        'info_generate_body': (
            "Ogni brano generato produce 3 file, che il gioco cerca in 2 cartelle diverse:\n\n"
            "• <hash>.trackdata.txt  →  Playlists\\TrackData\n"
            "• <hash>.wav  →  Playlists\\TrackData\n"
            "• <hash>.wdef.txt  →  Playlists\\TrackDefinitions\n\n"
            "(il wdef.txt e' il piccolo file indice che serve al gioco per riconoscere ed "
            "elencare un brano nuovo - senza non compare in libreria)\n\n"
            "Le cartelle complete di solito sono:\n"
            "%AppData%/LocalLow/FITXR/BoxVR/Playlists/TrackData\n"
            "%AppData%/LocalLow/FITXR/BoxVR/Playlists/TrackDefinitions\n\n"
            "Puoi copiarli a mano, oppure usare il pulsante \"Installa in BoxVR\" dopo la "
            "generazione per farlo automaticamente (fai comunque un backup se non sei sicuro)."
        ),
        'install_btn': "📥 Installa in BoxVR",
        'confirm_install_title': "Installare in BoxVR?",
        'confirm_install_body': (
            "Verranno copiati {n_tracks} brani nella libreria di BoxVR su questo PC:\n\n"
            "{n_data} file (trackdata + wav) in\n{trackdata_dir}\n\n"
            "{n_wdef} file wdef.txt in\n{trackdefs_dir}\n\n"
            "Eventuali file con lo stesso nome verranno sovrascritti. Procedere?"
        ),
        'install_done': "Installazione completata: {n} file copiati in BoxVR.",
        'install_error': "Errore durante la copia in BoxVR:\n{msg}",
        'warn_install_no_files': "Nessun file generato da installare (genera prima almeno un brano).",
        'apply_all_btn': "Applica il preset del brano selezionato a tutti",
        'ask_create_playlist': "Vuoi anche creare (o aggiornare) una playlist di allenamento con questi brani?",
        'ask_playlist_name': "Nome della playlist:",
        'default_playlist_name': "Brani generati",
        'playlist_done': "Playlist \"{name}\" aggiornata con {n} brani.",
        'log_label_collapsed': "▸ Log",
        'log_label_expanded': "▾ Log",
        'remove_song_tooltip': "Rimuovi",
        'confirm_clear_songs': "Svuotare l'elenco? Tutti i brani e i preset assegnati verranno rimossi.",
        'status_queued': "In coda per l'analisi",
        'status_analyzing': "Analisi in corso...",
        'status_ready': "Analisi completata",
        'status_error': "Errore nell'analisi (vedi log)",
        'undo_remove_btn': "↺ Annulla rimozione \"{name}\"",
        'drag_handle_tooltip': "Trascina per riordinare",
        'warn_boxvr_running': ("BoxVR risulta aperto in questo momento. I file appena copiati potrebbero "
                                "non essere riconosciuti finche' non riavvii il gioco, o potresti creare "
                                "conflitti di scrittura. Continuare comunque?"),
        'overwrite_dialog_title': "Brani gia' presenti in BoxVR",
        'overwrite_dialog_intro': ("{n} dei brani da installare esistono gia' nella libreria BoxVR su questo "
                                    "PC (stesso trackId). Scegli quali sovrascrivere - quelli deselezionati "
                                    "verranno saltati e resteranno come sono ora nel gioco."),
        'select_all_btn': "Seleziona tutti",
        'select_none_btn': "Deseleziona tutti",
        'cancel_btn': "Annulla",
        'confirm_overwrite_btn': "Continua",
        'bpm_panel_text': "BPM: {bpm}",
        'bpm_uncertain_tooltip': ("Il tempo rilevato sembrava troppo lento per un brano da allenamento, "
                                   "quindi e' stato raddoppiato automaticamente (capita su drum & bass/"
                                   "breakbeat). Ascolta la base a click per verificare se e' corretto - "
                                   "in caso contrario correggilo a mano."),
        'beat_engine_label': "Precisione extra",
        'beat_engine_tooltip': ("Usa madmom invece del motore veloce (librosa) per rilevare i beat - "
                                 "molto piu' lento (minuti invece di secondi), ma segue meglio i cambi "
                                 "di tempo locali/le sezioni del brano. Consigliato solo se ascoltando "
                                 "la base a click senti il colpo scivolare fuori sincro in alcuni punti."),
        'beat_engine_unavailable_tooltip': ("Motore madmom non disponibile in questa installazione "
                                             "(manca madmom_worker.exe)."),
        'madmom_fallback_log': ("{name}: motore 'precisione extra' non disponibile ({msg}) - "
                                 "uso il motore veloce per questo brano."),
        'suspicious_bpm_tooltip': ("Il pre-check automatico ha rilevato una griglia dei beat poco stabile "
                                    "(o un forte disaccordo tra i motori) - clicca per verificare il BPM "
                                    "con una ricerca online, o correggilo a mano se serve."),
        'engine_choice_title': "Motore di rilevamento beat",
        'engine_choice_intro': ("{n} brani non hanno un motore scelto a mano. Di norma viene usato madmom, "
                                 "lo stesso motore di BoxVR; dove la griglia dei beat risulta gia' "
                                 "perfettamente stabile si tiene il risultato veloce di librosa, che li' "
                                 "vale quanto madmom. Puoi anche forzare lo stesso motore per tutti."),
        'patch_state_on': "Patch attiva",
        'patch_state_off': "Patch non attiva",
        'patch_state_unknown': "Patch: build ignota",
        'patch_state_missing': "Gioco non trovato",
        'patch_tooltip': ("Stato della modifica al gioco che gli fa suonare le coreografie scritte da "
                           "questo strumento invece di generarne una propria. Clicca per applicarla o "
                           "rimuoverla."),
        'patch_apply_confirm': ("Applico la modifica a BoxVR?\n\nDa quel momento il gioco suonera' "
                                 "ESATTAMENTE la coreografia scritta nella playlist. Le playlist create "
                                 "prima, che non ne hanno una, suoneranno senza pugni: e' il "
                                 "comportamento atteso, non un guasto.\n\nViene creato un backup e la "
                                 "modifica si puo' togliere in qualsiasi momento."),
        'patch_revert_confirm': ("Rimuovo la modifica e rimetto BoxVR com'era?\n\nIl gioco tornera' a "
                                  "generare da se' i pugni, ignorando le coreografie scritte."),
        'patch_unknown_msg': ("I byte da modificare non corrispondono a quelli attesi: questa copia del "
                               "gioco e' diversa da quella su cui la modifica e' stata calcolata. Non "
                               "viene toccato nulla."),
        'game_dir_prompt': "Seleziona la cartella di installazione di BoxVR",
        'game_dir_ask_auto': ("Ho trovato BoxVR qui:\n\n{path}\n\nE' l'installazione giusta?\n\n"
                               "Scegli No per indicarne un'altra."),
        'game_dir_ask_none': ("Non ho trovato BoxVR automaticamente.\n\nVuoi indicarmi tu la cartella "
                               "di installazione?"),
        'game_dir_invalid': ("Quella cartella non sembra contenere BoxVR: dovrebbe avere dentro "
                              "BoxVR_Data\\Managed\\Assembly-CSharp.dll."),
        'lock_banner_text': ("Per generare allenamenti serve la modifica al gioco: senza, BoxVR ignora "
                              "le coreografie e continua a inventarsele da solo."),
        'lock_banner_btn': "Applica la modifica",
        'chooser_subtitle': "Cosa vuoi fare oggi?",
        'chooser_fix_title': "Correggi brani esistenti",
        'chooser_fix_desc': ("Aggiusta i livelli di intensita' dei brani che BoxVR ha gia' creato. "
                              "Funziona con il gioco cosi' com'e', nessuna modifica necessaria."),
        'chooser_fix_cta': "Correggi",
        'chooser_fix_patched_note': "Rilevata Patch.",
        'chooser_fix_patched_action': "Disabilita",
        'chooser_make_title': "Genera coreografie da MP3",
        'chooser_make_desc': ("Crea allenamenti nuovi da zero, con i colpi posizionati a mano su brani "
                               "tuoi. Richiede una piccola modifica al gioco, applicabile da qui."),
        'chooser_make_cta': "Genera",
        'engine_choice_recommended': "Scegli tu per me, brano per brano",
        'engine_choice_madmom': "Sempre madmom, anche dove non serve (piu' lento)",
        'engine_choice_librosa': "Sempre librosa: veloce, qualita' non garantita",
        'click_track_label': "Base a click",
        'volume_tooltip': "Volume di riproduzione",
        'zoom_tooltip': "Zoom sulla timeline - trascina per scorrere quando sei ingrandito",
        'log_bpm_regenerated': "BPM di {name} corretto manualmente a {bpm:.1f} e ririlevato - {n} segmenti.",
        'timeline_mode_curve': "Curva",
        'timeline_mode_beats': "Colpi",
        'timeline_mode_markers': "Marker",
    },
    'en': {
        'app_title': "BoxVR Level Fixer",
        'app_subtitle': "BoxVR level analysis and correction tool",
        'tab_correct': "Fix existing",
        'tab_generate': "Generate from MP3",
        'subtitle_correct': "Drop folders or matching .txt + .wav file pairs to fix here (you can drop more than once)",
        'subtitle_generate': "Drop folders or mp3/wav files to generate trackdata from here (you can drop more than once)",
        'drop_hint': "Drop folders or files here\nor use \"Choose folder...\"",
        'browse_btn': "Choose folder...",
        'clear_list_btn': "Clear list",
        'open_boxvr_btn': "BoxVR folder",
        'warn_boxvr_folder_missing': "Folder not found:\n{folder}\n\nBoxVR doesn't appear to be installed on this PC (or hasn't imported any song yet).",
        'no_folder': "No songs added",
        'folder_selected': "{n} songs in the list",
        'folder_selected_progress': "{n} songs in the list · {done}/{n} analyzed",
        'select_song_prompt': "Select a song from the list",
        'track_id_label': "ID: {track_id}",
        'timeline_original_label': "Event structure from BoxVR",
        'timeline_corrected_label': "Corrected event structure",
        'timeline_tooltip': "{phase} — {n} events",
        'legend_0': "Silence", 'legend_1': "Light", 'legend_2': "Punches", 'legend_3': "Mixed",
        'col_title': "Title", 'col_artist': "Artist", 'col_bpm': "BPM", 'col_preset': "Punch %",
        'punch_ratio_label': "Only punch events",
        'punch_ratio_chip': "{pct}% punches",
        'play': "▶  Play", 'pause': "⏸  Pause", 'audio_unavailable': "Audio unavailable",
        'visual_btn': "👁  Visual preview",
        'visual_preview_empty': "This track produces no punches with the chosen preset.",
        'visual_preview_no_audio': "Audio not loaded for this track yet: wait for the analysis to finish.",
        'visual_preview_error': "Visual preview unavailable: {msg}",
        'analyzing': "Analyzing...",
        'analysis_error': "Analysis error: {msg}",
        'audio_device_error': "No audio output device available for playback:\n{msg}",
        'log_audio_device_error': "Play unavailable: no audio device ({msg})",
        'phase': "Phase: {level}",
        'margin_label': "Confidence margin",
        'margin_info_tooltip': "How sure the analysis needs to be before correcting a level. Higher = more cautious corrections (only when the analysis is very confident, the rest stays as the game originally computed it). Lower = more corrections, but some less certain.",
        'density_label': "Trackdata energy levels (unpatched game only)",
        'density_legacy_tooltip': ("This slider and the punch/mixed ratio write energy levels into the "
                                    "trackdata, which only matter when the game is NOT patched: in that case "
                                    "BoxVR picks the punches itself, based on these levels.\n\n"
                                    "With the patch active (required to generate) the game ignores them, and "
                                    "the written choreography doesn't use them either — it works straight from "
                                    "the track's energy curve. So these don't change what you play; use "
                                    "\"Choreography intensity\" below for that.\n\n"
                                    "They only stay useful if you ever revert the game and want generated "
                                    "tracks to work that way too."),
        'density_real_marker_tooltip': "▲ = average density measured across real BoxVR trackdata",
        'choreo_preset_label': "Choreography intensity",
        'choreo_light': "Light",
        'choreo_medium': "Medium",
        'choreo_high': "Intense",
        'choreo_preset_tooltip': ("How many and which punches get written into the choreography: "
                                   "Light skips the busiest passages, Intense renders them in full.\n\n"
                                   "Different from the density slider above, which governs the track's "
                                   "energy levels: this governs what you actually play, and only takes "
                                   "effect with the game patched."),
        'choreo_epm_hint': "~{epm} punches/min (usually {lo}-{hi}) · official BoxVR ~{official}",
        'choreo_epm_tooltip': ("How many punches per minute this preset produces on average, MEASURED "
                                "on the choreography actually generated (26/08, across 6 songs), not a "
                                "theoretical target.\n\nThe range in brackets is real and wide: it "
                                "depends heavily on the song — a dense, steady track yields far more "
                                "punches than a slow one at the same preset.\n\nThe official BoxVR "
                                "reference (~82/min) is measured on the real choreography of 15 "
                                "official game songs, extracted from the game's own files."),
        'generate_tool_automatic': "Automatic",
        'generate_tool_sidecar': "Sidecar",
        'sidecar_title': "Sidecar — mark the accents yourself (experimental)",
        'sidecar_tooltip': ("Listen to the track and press the MARK area (or the F/K keys on your "
                             "keyboard) whenever you want a hit there: never the lane, never the move "
                             "type — the algorithm still decides those, exactly as it already does for "
                             "real audio accents.\n\nYour markers are a BASE, not the whole song: "
                             "automatic generation still fills in the rest, and one of your markers "
                             "always wins a conflict.\n\n\"Record\" always continues from wherever you're "
                             "positioned on the timeline, discarding only the markers from that point "
                             "onward — handy for redoing a spot you didn't like without losing the rest. "
                             "\"Stop\" pauses without touching anything. Use \"Reset\" to clear the whole "
                             "song; use \"Clear\" to remove just the markers while keeping mode/threshold "
                             "as they were."),
        'sidecar_record_btn': "Record",
        'sidecar_stop_btn': "Stop",
        'sidecar_mark_area': "MARK",
        'sidecar_clear_btn': "Clear",
        'sidecar_reset_btn': "Reset",
        'sidecar_count': "{n} markers recorded",
        'sidecar_usage_note_active': "Recorded markers are used automatically when generating. To go back to fully automatic, press Clear.",
        'sidecar_usage_note_empty': "No markers: generation will use only the automatic algorithm.",
        'sidecar_mode_label': "Mode",
        'sidecar_mode_markers_only': "Markers only",
        'sidecar_mode_harmonize': "Harmonize",
        'sidecar_mode_extend': "Extend",
        'sidecar_mode_tooltip': ("How much weight your markers carry against the automatic choreography:\n\n"
                                  "• Harmonize (usual): the rest of the song is still written by the full "
                                  "algorithm, your markers only win where they land.\n\n"
                                  "• Markers only: no automatic pattern at all — the rest of the song stays "
                                  "silent, EXCEPT for obstacles (Squat/Dodge), which the algorithm keeps "
                                  "placing on its own regardless of your markers (you never mark those "
                                  "yourself, so the workout still needs them for variety).\n\n"
                                  "• Extend: if you only mark PART of the song (e.g. the first minute and "
                                  "a half of three), inside that stretch the same \"Markers only\" rule "
                                  "applies (no unrequested automatic hit slips in among your markers), but "
                                  "OUTSIDE that stretch the algorithm generates in full — the rest of the "
                                  "song doesn't stay silent.\n\n"
                                  "For a quick with/without comparison, switch to the \"Automatic\" tool "
                                  "above instead — your markers stay saved on this song even while you're "
                                  "not using them."),
        'sidecar_exclude_label': "Marker hits only (never obstacles on markers)",
        'sidecar_exclude_tooltip': ("When on, an instant you mark never becomes a Squat or Dodge — only "
                                     "a Block or a punch. Obstacles stay an autonomous choice of the "
                                     "algorithm, never forced onto one of your markers — this also applies "
                                     "in \"Markers only\" mode: obstacles still appear on their own there "
                                     "too, regardless of where you mark."),
        'sidecar_min_gap_label': "Minimum gap between hits",
        'sidecar_min_gap_tooltip': ("Two markers closer than this threshold get merged: only the first "
                                     "survives. The default (170ms) is the absolute minimum ever measured "
                                     "across BoxVR's 465 official workouts — no real song in the game has "
                                     "ever had two hits closer than that. Lowering it allows hits denser "
                                     "than anything the game has ever actually generated: use it knowingly, "
                                     "checking how many markers would be dropped before deciding."),
        'sidecar_min_gap_real_marker_tooltip': "170ms — the absolute minimum measured across BoxVR's 465 official workouts",
        'sidecar_min_gap_dropped': "At this threshold, {dropped} of {n} markers would be merged into the previous one",
        'sidecar_min_gap_none_dropped': "No markers too close at this threshold",
        'risky_playlists_msg': ("Warning: some installed playlists have songs with no "
                                 "choreography — with the patch active they play SILENT:\n\n{list}\n\n"
                                 "Regenerate them or remove them from the playlist."),
        'risky_playlists_more': "and {n} more",
        'dry_run': "Report only (don't modify files)",
        'replace_originals_label': "Replace originals (with automatic backup)",
        'replace_originals_info_tooltip': "Overwrites the original .txt files directly instead of saving to a separate \"corretti\" folder you'd have to move by hand. A timestamped backup copy is made right next to the originals before each overwrite (\"backup_correzioni\" folder), so you can always go back to the previous version.",
        'playlist_duration_label': "Maximum playlist duration (minutes)",
        'playlist_duration_placeholder': "no limit",
        'playlist_duration_tooltip': "If the total length of the songs generated in this session goes over this time, the playlist is split into several numbered files (\"Name 1\", \"Name 2\", ...) instead of one very long one — useful for deliberately short workouts.\n\nEmpty = no limit: a playlist as long as the songs you put in it, the usual behavior.",
        'log_playlist_duration_invalid': "Playlist duration \"{value}\" is not a valid number, ignored (no limit applied).",
        'run_btn_correct': "Start correction",
        'run_btn_generate': "Generate",
        'open_btn': "Open results folder",
        'log_label': "Log",
        'note_no_dnd': "Note: tkinterdnd2 module not found, use 'Choose folder...'.",
        'note_no_audio': "Note: sounddevice module not found, audio preview is disabled (the timeline is still visible).",
        'warn_invalid_drop': "Drop a folder or valid files.",
        'warn_no_pairs': "No .txt + .wav pair found.",
        'warn_no_audio_files': "No mp3/wav file found.",
        'warn_wrong_tab_mp3': ("You dropped an mp3 file in this tab: an mp3 can only be used to generate a "
                                "trackdata from scratch. Switch to the \"Generate from MP3\" tab."),
        'log_added_n': "Added {n} new songs (total {total}).",
        'log_analysis_error': "Analysis error {name}: {msg}",
        'log_start_correct': "Starting correction on {n} songs",
        'log_start_generate': "Starting generation on {n} songs",
        'log_params': "Margin: {margin}  |  Report only: {dry_run}",
        'log_preset_line': "  {name} — {artist}: {preset}",
        'log_error': "ERROR: {message}",
        'done_summary_correct': ("Done!\n\nSongs processed: {n_ok}\nWith corrections: {n_changed}\n"
                                  "Total corrections: {n_total_changes}\nSkipped (missing wav): {n_skipped}\n"
                                  "Errors: {n_errors}\n\nResults in:\n{output_folder}"),
        'done_summary_generate': ("Done!\n\nSongs generated: {n_ok}\nErrors: {n_errors}\n\n"
                                   "Results in:\n{output_folder}\n\n"
                                   "To use them in-game, manually copy <hash>.trackdata.txt + <hash>.wav into\n"
                                   "%AppData%/LocalLow/FITXR/BoxVR/Playlists/TrackData\n"
                                   "and <hash>.wdef.txt into\n"
                                   "%AppData%/LocalLow/FITXR/BoxVR/Playlists/TrackDefinitions\n"
                                   "(back up first)."),
        'warn_no_txt': "No songs to process.",
        'error_prefix': "An error occurred:\n{message}",
        'browse_dialog_title_correct': "Choose the folder with the .txt and .wav files",
        'browse_dialog_title_generate': "Choose the folder with the mp3/wav files",
        'info_btn': "Where files go",
        'info_generate_body': (
            "Each generated song produces 3 files, which the game looks for in 2 different folders:\n\n"
            "• <hash>.trackdata.txt  →  Playlists\\TrackData\n"
            "• <hash>.wav  →  Playlists\\TrackData\n"
            "• <hash>.wdef.txt  →  Playlists\\TrackDefinitions\n\n"
            "(the wdef.txt is the small index file the game needs to recognize and list a new "
            "song - without it, it won't show up in the library)\n\n"
            "The full paths are usually:\n"
            "%AppData%/LocalLow/FITXR/BoxVR/Playlists/TrackData\n"
            "%AppData%/LocalLow/FITXR/BoxVR/Playlists/TrackDefinitions\n\n"
            "You can copy them by hand, or use the \"Install to BoxVR\" button after generating "
            "to do it automatically (back up first if you're not sure)."
        ),
        'install_btn': "📥 Install to BoxVR",
        'confirm_install_title': "Install to BoxVR?",
        'confirm_install_body': (
            "{n_tracks} songs will be copied into your local BoxVR library:\n\n"
            "{n_data} files (trackdata + wav) into\n{trackdata_dir}\n\n"
            "{n_wdef} wdef.txt files into\n{trackdefs_dir}\n\n"
            "Any file with the same name will be overwritten. Proceed?"
        ),
        'install_done': "Install complete: {n} files copied into BoxVR.",
        'install_error': "Error while copying into BoxVR:\n{msg}",
        'warn_install_no_files': "No generated files to install (generate at least one song first).",
        'apply_all_btn': "Apply the selected song's preset to all",
        'ask_create_playlist': "Do you also want to create (or update) a workout playlist with these songs?",
        'ask_playlist_name': "Playlist name:",
        'default_playlist_name': "Generated songs",
        'playlist_done': "Playlist \"{name}\" updated with {n} songs.",
        'log_label_collapsed': "▸ Log",
        'log_label_expanded': "▾ Log",
        'remove_song_tooltip': "Remove",
        'confirm_clear_songs': "Clear the list? All songs and their assigned presets will be removed.",
        'status_queued': "Queued for analysis",
        'status_analyzing': "Analyzing...",
        'status_ready': "Analysis complete",
        'status_error': "Analysis error (see log)",
        'undo_remove_btn': "↺ Undo remove \"{name}\"",
        'drag_handle_tooltip': "Drag to reorder",
        'warn_boxvr_running': ("BoxVR appears to be open right now. Files you just copied might not be "
                                "picked up until you restart the game, or you could run into write "
                                "conflicts. Continue anyway?"),
        'overwrite_dialog_title': "Songs already in BoxVR",
        'overwrite_dialog_intro': ("{n} of the songs you're installing already exist in the BoxVR library "
                                    "on this PC (same trackId). Choose which ones to overwrite - unchecked "
                                    "ones will be skipped and stay as they currently are in the game."),
        'select_all_btn': "Select all",
        'select_none_btn': "Select none",
        'cancel_btn': "Cancel",
        'confirm_overwrite_btn': "Continue",
        'bpm_panel_text': "BPM: {bpm}",
        'bpm_uncertain_tooltip': ("The detected tempo looked too slow for a workout track, so it was "
                                   "automatically doubled (happens on drum & bass/breakbeat). Listen to "
                                   "the click track to check it's right - fix it by hand if it isn't."),
        'beat_engine_label': "Extra accuracy",
        'beat_engine_tooltip': ("Use madmom instead of the fast engine (librosa) for beat detection - "
                                 "much slower (minutes instead of seconds), but follows local tempo/section "
                                 "changes better. Only worth it if the click track sounds like it drifts "
                                 "out of sync in some spots."),
        'beat_engine_unavailable_tooltip': "madmom engine not available in this install (madmom_worker.exe missing).",
        'madmom_fallback_log': "{name}: 'extra accuracy' engine unavailable ({msg}) - using the fast engine instead.",
        'suspicious_bpm_tooltip': ("The automatic pre-check found an unstable beat grid (or a strong "
                                    "disagreement between engines) - click to check the BPM with an online "
                                    "search, or fix it by hand if needed."),
        'engine_choice_title': "Beat-detection engine",
        'engine_choice_intro': ("{n} songs have no manually-chosen engine. madmom — the same engine BoxVR "
                                 "itself uses — is used by default; where the beat grid already comes out "
                                 "perfectly stable, librosa's faster result is kept instead, since there it "
                                 "is just as good. You can also force the same engine for all of them."),
        'patch_state_on': "Patch active",
        'patch_state_off': "Patch not active",
        'patch_state_unknown': "Patch: unknown build",
        'patch_state_missing': "Game not found",
        'patch_tooltip': ("State of the change to the game that makes it play the choreography written "
                           "by this tool instead of generating its own. Click to apply or remove it."),
        'patch_apply_confirm': ("Apply the change to BoxVR?\n\nFrom then on the game will play EXACTLY "
                                 "the choreography written in the playlist. Playlists made earlier, which "
                                 "have none, will play with no punches: that is expected, not a "
                                 "fault.\n\nA backup is made and the change can be removed at any time."),
        'patch_revert_confirm': ("Remove the change and put BoxVR back as it was?\n\nThe game will go "
                                  "back to inventing the punches itself, ignoring written choreography."),
        'patch_unknown_msg': ("The bytes to change don't match the expected ones: this copy of the game "
                               "differs from the one the change was worked out on. Nothing was touched."),
        'game_dir_prompt': "Select the BoxVR installation folder",
        'game_dir_ask_auto': ("Found BoxVR here:\n\n{path}\n\nIs this the right installation?\n\n"
                               "Choose No to point somewhere else."),
        'game_dir_ask_none': ("Couldn't find BoxVR automatically.\n\nWould you like to point me to the "
                               "installation folder?"),
        'game_dir_invalid': ("That folder doesn't look like BoxVR: it should contain "
                              "BoxVR_Data\\Managed\\Assembly-CSharp.dll."),
        'lock_banner_text': ("Generating workouts needs the change to the game: without it BoxVR ignores "
                              "the choreography and keeps making its own up."),
        'lock_banner_btn': "Apply the change",
        'chooser_subtitle': "What do you want to do today?",
        'chooser_fix_title': "Fix existing tracks",
        'chooser_fix_desc': ("Adjust the intensity levels of songs BoxVR has already created. Works "
                              "with the game as-is, no change needed."),
        'chooser_fix_cta': "Fix",
        'chooser_fix_patched_note': "Patch detected.",
        'chooser_fix_patched_action': "Disable it",
        'chooser_make_title': "Generate choreography from MP3s",
        'chooser_make_desc': ("Build brand-new workouts from scratch, with hits placed by hand on your "
                               "own tracks. Needs a small change to the game, applicable from here."),
        'chooser_make_cta': "Generate",
        'engine_choice_recommended': "Decide per song for me",
        'engine_choice_madmom': "Always madmom, even when unnecessary (slower)",
        'engine_choice_librosa': "Always librosa: fast, quality not guaranteed",
        'click_track_label': "Click track",
        'volume_tooltip': "Playback volume",
        'zoom_tooltip': "Zoom into the timeline - drag to pan while zoomed in",
        'log_bpm_regenerated': "{name}'s BPM manually corrected to {bpm:.1f} and re-detected - {n} segments.",
        'timeline_mode_curve': "Curve",
        'timeline_mode_beats': "Hits",
        'timeline_mode_markers': "Markers",
    },
}


def paths_from_drop_data(root, data):
    """tkdnd racchiude i path con spazi tra {}: usa tk.splitlist per separarli bene."""
    return list(root.tk.splitlist(data))


def _fmt_time(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _darken_hex(hex_color, factor=0.55):
    """Scurisce un colore #rrggbb - usato per le tacche del visualizzatore per-beat,
    cosi' risaltano sopra la fascia di sfondo dello stesso colore (stessa tinta,
    piu' scura) invece di sparirci dentro."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f'#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}'


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _blend_hex(hex_a, hex_b, t):
    """Interpola linearmente tra due colori esadecimali (t=0 -> hex_a, t=1 -> hex_b)."""
    a, b = _hex_to_rgb(hex_a), _hex_to_rgb(hex_b)
    return _rgb_to_hex(tuple(x + (y - x) * t for x, y in zip(a, b)))


# -- icone/pallini anti-aliasati via PIL -----------------------------------
#
# Le emoji a colori (Segoe UI Emoji su Windows) sono in realta' glifi bitmap
# incorporati a risoluzione fissa, non vettoriali: tkinter le richiede al
# punto-size dichiarato dal font, e se quello non coincide con una delle
# risoluzioni native del font (specie con lo scaling DPI ~125% di questa
# macchina, gia' visto altrove in questo file), Windows le ridimensiona con un
# filtro scadente -> risultato visibilmente "sgranato"/pixellato, segnalato
# dall'utente. Stesso discorso per gli ovali disegnati a mano su tk.Canvas
# (create_oval): GDI non li anti-alias a piccola dimensione, escono "a
# scalini". Fix unico per entrambi i casi: disegnare a una risoluzione MOLTO
# piu' alta di quella finale (supersampling) e poi ridurre con un filtro di
# qualita' (LANCZOS) - la riduzione stessa produce l'anti-aliasing che ne'
# tkinter ne' GDI applicano di loro. Cache per (contenuto, dimensione) dato
# che lo stesso pallino/icona viene ridisegnato spesso (ogni riga canzone,
# ogni redraw tema).
_ICON_CACHE = {}
_EMOJI_FONT_CANDIDATES = ("seguiemj.ttf", "Segoe UI Emoji", "NotoColorEmoji.ttf")


def _load_first_font(candidates, size):
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _render_emoji_icon(emoji, size=18, supersample=4):
    """Ritorna un ctk.CTkImage quadrato (size x size) con `emoji` disegnata
    anti-aliasata e centrata, sfondo trasparente. Vedi commento sopra per il
    perche' non si puo' semplicemente usare un CTkLabel/CTkButton text=emoji."""
    key = ('emoji', emoji, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    big = size * supersample
    canvas = Image.new("RGBA", (big * 2, big * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    font = _load_first_font(_EMOJI_FONT_CANDIDATES, int(big * 0.82))
    try:
        draw.text((big, big), emoji, font=font, anchor="mm", embedded_color=True)
    except TypeError:
        # Font non a colori (fallback simbolo) - niente embedded_color, serve un fill.
        draw.text((big, big), emoji, font=font, anchor="mm", fill=(140, 140, 160, 255))
    # anchor="mm" centra secondo le metriche del font, NON secondo il bounding
    # box visivo del glifo - i glifi bitmap di Segoe UI Emoji hanno bearing
    # molto irregolari (es. il cestino risultava spostato in alto-a-sinistra,
    # tagliato fuori dal riquadro finale) - si ricentra quindi sul bbox reale
    # dei pixel non trasparenti (getbbox) invece di fidarsi delle metriche.
    bbox = canvas.getbbox()
    if bbox is not None:
        glyph = canvas.crop(bbox)
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        gw, gh = glyph.size
        scale = min(big * 0.92 / gw, big * 0.92 / gh, 1.0) if max(gw, gh) > 0 else 1.0
        if scale < 1.0:
            glyph = glyph.resize((max(1, int(gw * scale)), max(1, int(gh * scale))), Image.LANCZOS)
            gw, gh = glyph.size
        img.paste(glyph, ((big - gw) // 2, (big - gh) // 2), glyph)
    else:
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    img = img.resize((size, size), Image.LANCZOS)
    photo = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    _ICON_CACHE[key] = photo
    return photo


def _render_flag_icon(country, size=20, supersample=4):
    """Bandierina disegnata a mano con primitive PIL, non emoji - le vere
    bandiere Unicode sono SEMPRE coppie di "Regional Indicator Symbol" che
    richiedono la composizione in legatura del text-shaper (raqm/HarfBuzz) per
    diventare un unico glifo colorato; questa build di Pillow non ha raqm
    (verificato: PIL.features.check('raqm') -> False, probabile anche nel
    Pillow bundlato da customtkinter nell'exe compilato) - senza legatura,
    draw.text disegna le due lettere sciolte del fallback ("IT"/"GB" come testo
    semplice), non la bandiera - il problema esatto segnalato dall'utente
    guardando lo screenshot. Disegnare la bandiera stessa aggira la shaping
    del tutto: nessun font coinvolto, nessuna dipendenza da raqm."""
    key = ('flag', country, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    big = size * supersample
    w, h = big, int(big * 0.72)
    ox, oy = 0, (big - h) // 2
    radius = int(big * 0.09)

    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((ox, oy, ox + w - 1, oy + h - 1), radius=radius, fill=255)

    flag = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    fd = ImageDraw.Draw(flag)
    if country == 'it':
        third = w / 3
        fd.rectangle((ox, oy, ox + third, oy + h), fill="#009246")
        fd.rectangle((ox + third, oy, ox + 2 * third, oy + h), fill="#ffffff")
        fd.rectangle((ox + 2 * third, oy, ox + w, oy + h), fill="#CE2B37")
    else:  # 'gb' - Union Jack semplificato (proporzioni approssimate, non araldiche)
        fd.rectangle((ox, oy, ox + w, oy + h), fill="#00247D")
        fd.line((ox, oy, ox + w, oy + h), fill="#ffffff", width=max(1, int(h * 0.22)))
        fd.line((ox + w, oy, ox, oy + h), fill="#ffffff", width=max(1, int(h * 0.22)))
        fd.line((ox, oy, ox + w, oy + h), fill="#CF142B", width=max(1, int(h * 0.09)))
        fd.line((ox + w, oy, ox, oy + h), fill="#CF142B", width=max(1, int(h * 0.09)))
        fd.rectangle((ox, oy + h * 0.36, ox + w, oy + h * 0.64), fill="#ffffff")
        fd.rectangle((ox + w * 0.40, oy, ox + w * 0.60, oy + h), fill="#ffffff")
        fd.rectangle((ox, oy + h * 0.44, ox + w, oy + h * 0.56), fill="#CF142B")
        fd.rectangle((ox + w * 0.46, oy, ox + w * 0.54, oy + h), fill="#CF142B")

    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    img.paste(flag, (0, 0), mask)
    img = img.resize((size, size), Image.LANCZOS)
    photo = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    _ICON_CACHE[key] = photo
    return photo


def _render_dot_image(color_hex, diameter=12, supersample=4):
    """Pallino pieno anti-aliasato (per i pallini di legenda/stato, prima
    disegnati a mano su tk.Canvas con create_oval - vedi commento sopra)."""
    key = ('dot', color_hex, diameter)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    big = diameter * supersample
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, big - 1, big - 1), fill=color_hex)
    img = img.resize((diameter, diameter), Image.LANCZOS)
    photo = ctk.CTkImage(light_image=img, dark_image=img, size=(diameter, diameter))
    _ICON_CACHE[key] = photo
    return photo


SHADOW_BLUR_RADIUS = 5    # sfocatura del filtro gaussiano, in px alla risoluzione finale - vincolato
# dal padx=16 che song_list_frame/preview_frame hanno verso i rispettivi genitori: pad (il
# margine di rendering, blur_radius*3 - vedi _render_card_shadow_image) deve restare SOTTO
# quel budget, altrimenti self.scroll (una CTkScrollableFrame, il cui canvas interno ritaglia
# qualunque figlio ecceda i propri confini) tronca la sfocatura di netto a meta' sfumatura -
# si vedeva un bordo grigio duro con un lato sfumato e l'altro reciso, non "nessuna ombra": la
# sfocatura c'era, solo tagliata (verificato con zoom reale sullo screenshot). alpha piu' alto
# (110 invece di 90) compensa il raggio piu' piccolo, cosi' l'ombra resta ben visibile pur
# restando entro il margine disponibile.
SHADOW_ALPHA = 110         # opacita' massima dell'ombra (0-255) al centro della sagoma
SHADOW_OFFSET_Y = 4        # spostamento verso il basso, per una luce "dall'alto"
_SHADOW_IMG_CACHE = {}


def _render_card_shadow_image(w, h, radius, color_hex, blur_radius=SHADOW_BLUR_RADIUS,
                               alpha=SHADOW_ALPHA, supersample=2):
    """Ritorna (img RGBA, pad) - un'ombra sfumata con GaussianBlur VERO attorno
    a un rettangolo arrotondato w x h di raggio `radius`, pronta per essere
    piazzata dietro una card (vedi _add_soft_shadow per il perche').

    `pad` e' il margine attorno alla sagoma: deve essere generoso (multiplo
    del raggio di blur) perche' la sfocatura ha bisogno di spazio libero
    tutt'intorno per dissolversi fino alla trasparenza - se il margine fosse
    stretto quanto il raggio stesso, il filtro verrebbe troncato di netto sul
    bordo dell'immagine e si vedrebbe di nuovo uno spigolo secco, lo stesso
    identico problema che questa riscrittura serve a risolvere, solo spostato
    dal bordo della card al bordo dell'immagine.

    Supersample basso (2, non 4 come le icone): qui il canvas e' grande
    quanto un'intera card (centinaia di px), non una piccola icona - un
    supersample da 4x lo renderebbe enorme e lento da rigenerare ad ogni
    resize della finestra senza un guadagno visivo percepibile, dato che il
    blur stesso gia' maschera l'aliasing dei bordi arrotondati."""
    key = (round(w), round(h), radius, color_hex, blur_radius, alpha)
    if key in _SHADOW_IMG_CACHE:
        return _SHADOW_IMG_CACHE[key]
    pad = blur_radius * 3
    big_pad = pad * supersample
    big_w, big_h = w * supersample, h * supersample
    big_radius = radius * supersample
    canvas = Image.new("RGBA", (big_w + big_pad * 2, big_h + big_pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    rgb = _hex_to_rgb(color_hex)
    draw.rounded_rectangle(
        (big_pad, big_pad, big_pad + big_w - 1, big_pad + big_h - 1),
        radius=big_radius, fill=(*rgb, alpha),
    )
    canvas = canvas.filter(ImageFilter.GaussianBlur(blur_radius * supersample))
    img = canvas.resize((w + pad * 2, h + pad * 2), Image.LANCZOS)
    _SHADOW_IMG_CACHE[key] = (img, pad)
    return img, pad


def _animate_color_pulse(set_color_fn, from_hex, to_hex, after_fn, steps=8, interval_ms=22):
    """Anima una serie di chiamate set_color_fn(hex) da from_hex a to_hex in
    `steps` passi lineari (~175ms totali con i default - in linea con le durate
    consigliate per un microfeedback: breve, purposeful, mai puramente
    decorativo) invece di uno scatto secco. CTk non ha un motore di animazione
    nativo, quindi il "tween" e' fatto a mano qui: `set_color_fn` puo' essere sia
    un `widget.configure(fg_color=...)` sia un `canvas.itemconfig(item, fill=...)`,
    cosi' lo stesso helper serve sia per i widget CTk sia per gli item disegnati a
    mano sui Canvas grezzi (pallino di stato, chip). `after_fn` e' il .after() di
    un qualunque widget vivo usato solo per schedulare i passi."""
    from_rgb = _hex_to_rgb(from_hex)
    to_rgb = _hex_to_rgb(to_hex)

    def step(i=0):
        if i > steps:
            return
        frac = i / steps
        cur = tuple(a + (b - a) * frac for a, b in zip(from_rgb, to_rgb))
        try:
            set_color_fn(_rgb_to_hex(cur))
        except Exception:
            return
        after_fn(interval_ms, lambda: step(i + 1))

    step()


def _truncate(text, max_chars):
    text = text or ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1].rstrip() + "…"


def _build_click_overlay(n_samples, n_ch, sr, beats, click_gain=0.35):
    """Un breve click sintetico (un "tick" percussivo, non uno strumento vero) ad
    ogni beat rilevato - per ascoltare ad orecchio se il tempo rilevato/corretto
    e' davvero allineato alla musica prima di fidarsene, invece di doverlo
    giudicare solo a occhio dalla timeline. Ritorna SOLO l'overlay dei click
    (silenzio altrove), non piu' premiscelato con l'audio della canzone: quel
    mix veniva fatto una volta sola qui, e poi lo SLIDER DEL VOLUME scalava
    l'intero buffer gia' fuso - abbassando il volume per sentire meglio il
    click, paradossalmente si abbassava anche il click stesso. Ora il volume
    (in SongPlayer._callback) si applica SOLO alla canzone; il click viene
    sommato dopo, sempre alla stessa intensita' fissa, sempre chiaramente
    udibile a qualunque volume di ascolto."""
    out = np.zeros((n_samples, n_ch), dtype=np.float32)
    click_len = int(sr * 0.03)  # 30ms: breve, non copre il beat successivo a tempi alti
    t = np.arange(click_len) / sr
    click_wave = (np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 90)).astype(np.float32) * click_gain
    for b in beats:
        start = int(b['_triggerTime'] * sr)
        if start < 0 or start >= n_samples:
            continue
        end = min(start + click_len, n_samples)
        seg_len = end - start
        for ch in range(n_ch):
            out[start:end, ch] += click_wave[:seg_len]
    return out


def _apply_auto_scrollbar(scrollable_frame):
    """CTkScrollableFrame mostra sempre la sua scrollbar, anche quando il
    contenuto non supera affatto l'altezza visibile - la nasconde/mostra da sola
    confrontando l'altezza reale del contenuto con quella del canvas, ricontrollato
    ad ogni ridimensionamento o cambio di contenuto (entrambi passano gia' da un
    <Configure> sul frame o sul suo canvas interno)."""
    def _check(event=None):
        scrollable_frame.after_idle(_update)

    def _update():
        try:
            canvas = scrollable_frame._parent_canvas
            bbox = canvas.bbox("all")
            content_h = (bbox[3] - bbox[1]) if bbox else 0
            visible_h = canvas.winfo_height()
            if content_h > visible_h:
                scrollable_frame._scrollbar.grid()
            else:
                scrollable_frame._scrollbar.grid_remove()
        except Exception:
            pass

    scrollable_frame.bind("<Configure>", _check, add="+")
    scrollable_frame._parent_canvas.bind("<Configure>", _check, add="+")
    _check()


def _make_inner_scroll_handler(canvas):
    """CTkScrollableFrame lega <MouseWheel> con bind_all (non sul singolo widget),
    quindi con due CTkScrollableFrame annidati (la lista canzoni dentro il pannello
    scorrevole del tab) lo scroll sopra quella interna fa scorrere ANCHE quella
    esterna/l'intera finestra: entrambi gli handler globali scattano insieme dato
    che check_if_master_is_canvas() e' vero per entrambi. Il fix e' legare
    <MouseWheel> DIRETTAMENTE (bind, non bind_all) sui widget della lista interna,
    scorrere a mano il suo canvas, e ritornare "break" cosi' l'evento non arriva
    piu' all'handler bind_all del contenitore esterno."""
    def handler(event):
        if sys.platform.startswith('win'):
            canvas.yview('scroll', -int(event.delta / 6), 'units')
        else:
            canvas.yview('scroll', -event.delta, 'units')
        return 'break'
    return handler


class SongPlayer:
    """Riproduce un buffer audio in memoria con seek/play/pausa a bassa latenza.

    Il callback gira sul thread real-time di PortAudio: legge/scrive solo il
    cursore `pos` sotto lock, non tocca mai Tkinter direttamente.
    """

    def __init__(self, audio, sr, volume=1.0, click_overlay=None):
        self.audio = audio
        self.sr = sr
        self.pos = 0
        self.finished = False
        self.volume = volume
        # Overlay dei click (solo i tick, silenzio altrove) sommato DOPO aver
        # applicato il volume alla canzone, non prima - cosi' il volume abbassa
        # solo la canzone e il click resta sempre alla stessa intensita' fissa,
        # udibile a qualunque volume di ascolto (vedi _build_click_overlay).
        self.click_overlay = click_overlay
        self._lock = threading.Lock()
        # latency='low' invece del default (27/08: misurato 180ms col
        # default su questa macchina, contro 90ms richiedendo 'low' - vedi
        # audible_position_seconds sotto per il perche' conta cosi' tanto
        # per la sidecar).
        self.stream = sd.OutputStream(
            samplerate=sr, channels=audio.shape[1], dtype='float32', latency='low',
            callback=self._callback, finished_callback=self._on_finished,
        )

    def _callback(self, outdata, frames, time_info, status):
        with self._lock:
            p = self.pos
            n = min(frames, len(self.audio) - p)
            if n <= 0:
                outdata.fill(0)
                raise sd.CallbackStop()
            mixed = self.audio[p:p + n] * self.volume
            if self.click_overlay is not None:
                mixed = mixed + self.click_overlay[p:p + n]
                np.clip(mixed, -1.0, 1.0, out=mixed)
            outdata[:n] = mixed
            if n < frames:
                outdata[n:].fill(0)
            self.pos = p + n

    def set_volume(self, volume):
        with self._lock:
            self.volume = max(0.0, min(1.0, volume))

    def set_click_overlay(self, click_overlay):
        with self._lock:
            self.click_overlay = click_overlay

    def _on_finished(self):
        self.finished = True

    def toggle(self):
        if self.stream.active:
            self.stream.stop()
        else:
            if self.finished:
                with self._lock:
                    self.pos = 0
                    self.finished = False
            self.stream.start()

    def seek(self, t):
        frame = max(0, min(len(self.audio), int(t * self.sr)))
        with self._lock:
            self.pos = frame
            self.finished = False

    def position_seconds(self):
        with self._lock:
            return self.pos / self.sr

    def audible_position_seconds(self):
        """Istante che l'utente sta DAVVERO sentendo in questo momento, non
        quello gia' consegnato al buffer di uscita - `self.pos` avanza non
        appena il callback scrive i campioni nel buffer, ma quelli diventano
        udibili solo dopo la latenza reale del dispositivo (`self.stream.
        latency`, misurata: 90-180ms su questa macchina a seconda delle
        impostazioni). Per la riproduzione normale la differenza non si nota;
        per la sidecar e' esattamente il difetto segnalato il 27/08 ("fuori
        tempo anche premendo al momento esatto del beat") - un marker preso
        da position_seconds() sarebbe sistematicamente IN ANTICIPO sul beat
        vero di quella stessa quantita', perche' l'utente reagisce a un suono
        che in realta' e' gia' 'vecchio' di `latency` secondi rispetto al
        cursore interno. Usata SOLO da _sidecar_mark - il resto della GUI
        (playhead, timeline) continua a usare position_seconds() com'era."""
        return max(0.0, self.position_seconds() - (self.stream.latency or 0.0))

    def close(self):
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass


class _Tooltip:
    """Piccolo popup non decorato mostrato al passaggio del mouse su un widget, con
    un ritardo prima di apparire (non scatta per uno sfioramento veloce). Riusato
    per il pallino di stato riga, la "X" di rimozione e l'icona di incertezza BPM.
    `text_getter` e' una funzione (non una stringa fissa) cosi' il testo puo'
    dipendere dallo stato corrente al momento dell'hover (es. stato della riga)."""

    def __init__(self, widget, text_getter, delay=400):
        self.widget = widget
        self.text_getter = text_getter
        self.delay = delay
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _schedule(self, event=None):
        self._cancel_after()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel_after(self):
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self):
        self._after_id = None
        text = self.text_getter()
        if not text or self._tip is not None:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        try:
            self._tip.wm_attributes("-topmost", True)
        except Exception:
            pass
        self._tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self._tip, text=text, justify="left", background=resolve_color(CARD3),
                          foreground=resolve_color(TEXT), relief="solid", borderwidth=1,
                          font=(FONT_REGULAR, 10), padx=8, pady=5, wraplength=280)
        label.pack()

    def _hide(self, event=None):
        self._cancel_after()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class _CanvasHoverTooltip:
    """Come _Tooltip, ma per un tk.Canvas dove il testo dipende dalla posizione X
    del mouse (una fascia timeline ha piu' segmenti diversi sotto lo stesso
    widget) invece che essere fisso per l'intero widget. Nessun ritardo prima di
    apparire: qui l'uso e' esplorativo (scorrere il mouse sulla fascia), non un
    hover accidentale su un bottone."""

    def __init__(self, canvas, text_at):
        self.canvas = canvas
        self.text_at = text_at  # callable(event) -> str|None
        self._tip = None
        self._last_text = None
        canvas.bind("<Motion>", self._on_motion, add="+")
        canvas.bind("<Leave>", self._hide, add="+")

    def _on_motion(self, event):
        text = self.text_at(event)
        if not text:
            self._hide()
            return
        if text != self._last_text or self._tip is None:
            self._hide()
            self._last_text = text
            self._tip = tk.Toplevel(self.canvas)
            self._tip.wm_overrideredirect(True)
            try:
                self._tip.wm_attributes("-topmost", True)
            except Exception:
                pass
            tk.Label(
                self._tip, text=text, justify="left", background=resolve_color(CARD3),
                foreground=resolve_color(TEXT), relief="solid", borderwidth=1,
                font=(FONT_REGULAR, 10), padx=8, pady=5,
            ).pack()
        self._tip.wm_geometry(f"+{event.x_root + 14}+{event.y_root + 14}")

    def _hide(self, event=None):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None
        self._last_text = None


class SongRow(ctk.CTkFrame):
    """Una riga-card per una canzone nell'elenco (stile "riga di Control Center"):
    titolo, artista, BPM, chip col preset corrente. Click ovunque sulla riga per
    selezionarla."""

    # Larghezze FISSE (in pixel, non a peso) per ogni colonna: usare grid con
    # colonne "weight" fa si' che ogni riga - essendo un CTkFrame/griglia a se'
    # stante - si auto-dimensioni sul PROPRIO contenuto, quindi righe con titoli
    # di lunghezza diversa finiscono con colonne disallineate tra loro. Larghezza
    # fissa + testo troncato con "..." garantisce che tutte le righe si allineino.
    TITLE_W, ARTIST_W, BPM_W, PRESET_W = 175, 115, 64, 150
    SPARK_W = 56

    # Colori del pallino di stato analisi per riga: in coda (non ancora presa in
    # carico dal worker in background), in analisi, pronta, o errore - cosi' con
    # liste lunghe si capisce a colpo d'occhio cosa sta ancora succedendo senza
    # dover mettere in focus ogni singola riga.
    STATUS_COLORS = {'queued': SUBTEXT, 'analyzing': ACCENT, 'ready': SUCCESS, 'error': ACTION_ACCENT}

    def __init__(self, parent, panel, song):
        super().__init__(parent, corner_radius=14, fg_color=CARD2, height=52)
        self.panel = panel
        self.song = song
        self.pack_propagate(False)
        self._bpm_uncertain = False
        self._suspicious = False

        # Maniglia di trascinamento per riordinare: overlay in .place() nel gap a
        # sinistra del titolo (che per farle spazio passa da padx=(14,4) a (24,4)),
        # cosi' solo QUESTA piccola area avvia un riordino - il resto della riga
        # resta clic-per-selezionare senza ambiguita' tra le due interazioni.
        self.drag_handle = ctk.CTkLabel(self, text="⠿", font=ui_font(13), text_color=SUBTEXT,
                                         width=16, height=24, cursor="fleur")
        self.drag_handle.place(x=2, rely=0.5, anchor="w")
        self.drag_handle.bind("<ButtonPress-1>", self._on_drag_press)
        self.drag_handle.bind("<B1-Motion>", self._on_drag_motion)
        self.drag_handle.bind("<ButtonRelease-1>", self._on_drag_release)

        # Tile icona a sinistra del titolo: le 4 reference Dribbble studiate
        # (fintech, chatbot, real estate, travel) hanno TUTTE un'icona/avatar
        # sul bordo sinistro di ogni riga lista (logo del brand nelle
        # transazioni, avatar dei contatti, badge della proprieta') - un ancora
        # visiva che questa lista non aveva affatto, solo testo. Puramente
        # decorativa/di identita' (non codifica un dato in piu', la nota
        # musicale e' generica) - CARD3 neutro cosi' non compete col chip
        # "Pugni %" gia' colorato per dato.
        self.type_icon = ctk.CTkLabel(
            self, text="", image=_render_emoji_icon("🎵", 14),
            fg_color=CARD3, corner_radius=8, width=26, height=26,
        )
        self.type_icon.place(x=22, rely=0.5, anchor="w")

        # "semibold" (non piu' "medium"): titolo e artista erano gia' distinti
        # per colore/dimensione ma il salto di PESO tra i due era minimo -
        # nelle reference (tutte e 4) il titolo di una card e' sempre
        # nettamente piu' pesante del sottotitolo, non solo piu' grande.
        self.title_label = ctk.CTkLabel(self, text=_truncate(song['name'], 21), font=ui_font(13, "semibold"),
                                         text_color=TEXT, anchor="w", width=self.TITLE_W)
        self.title_label.grid(row=0, column=0, sticky="w", padx=(56, 4))
        self.artist_label = ctk.CTkLabel(self, text=_truncate(song['artist'], 14), font=ui_font(12),
                                          text_color=SUBTEXT, anchor="w", width=self.ARTIST_W)
        self.artist_label.grid(row=0, column=1, sticky="w", padx=4)

        self.bpm_frame = ctk.CTkFrame(self, fg_color="transparent", width=self.BPM_W, height=24)
        self.bpm_frame.grid(row=0, column=2, sticky="w", padx=4)
        self.bpm_frame.pack_propagate(False)
        self.status_dot = ctk.CTkLabel(self.bpm_frame, text="", fg_color="transparent",
                                        image=_render_dot_image(resolve_color(self.STATUS_COLORS['queued'])),
                                        width=12, height=12)
        self._last_status = 'queued'
        self.status_dot.pack(side="left", padx=(2, 6))
        self.bpm_label = ctk.CTkLabel(self.bpm_frame, text="?", font=ui_font(12), text_color=SUBTEXT, anchor="w")
        self.bpm_label.pack(side="left")

        # Mini curva di energia ("colpo d'occhio" sulla forma del brano senza
        # doverlo aprire) - disegnata solo quando l'analisi in background finisce
        # (vedi draw_sparkline), vuota finche' non arriva bar_score.
        self.sparkline = tk.Canvas(self, width=self.SPARK_W, height=24, bg=resolve_color(CARD2), highlightthickness=0)
        self.sparkline.grid(row=0, column=3, sticky="w", padx=4)

        self.preset_chip = ctk.CTkLabel(self, text="", font=ui_font(11, "medium"), text_color=TEXT,
                                         fg_color=CARD3, corner_radius=10, anchor="center",
                                         width=self.PRESET_W, height=24)
        # Spazio extra a destra (34px anziche' 14) riservato alla "X" di rimozione,
        # che appare in overlay (.place) solo al passaggio del mouse sulla riga.
        self.preset_chip.grid(row=0, column=4, sticky="e", padx=(4, 34))

        self.remove_btn = ctk.CTkButton(
            self, text="✕", command=self._on_remove, width=22, height=22, corner_radius=11,
            fg_color=CARD3, hover_color=ACTION_ACCENT, text_color=SUBTEXT, font=ui_font(10, "semibold"),
        )
        self._remove_btn_visible = False
        self._leave_after_id = None
        self._selected = False

        clickable = (self, self.title_label, self.artist_label, self.bpm_frame,
                     self.status_dot, self.bpm_label, self.sparkline, self.preset_chip)
        hoverable = clickable + (self.remove_btn,)
        for w in clickable:
            w.bind("<Button-1>", self._on_click)
        for w in hoverable:
            w.bind("<Enter>", self._on_hover_enter)
            w.bind("<Leave>", self._on_hover_leave)

        if HAS_DND:
            for w in (self, self.title_label, self.artist_label):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", panel._on_drop)

        scroll_handler = panel.inner_scroll_handler
        for w in clickable + (self.remove_btn, self.drag_handle):
            w.bind("<MouseWheel>", scroll_handler)

        _Tooltip(self.status_dot, self._status_tooltip_text)
        _Tooltip(self.remove_btn, lambda: self.panel.t('remove_song_tooltip'))
        _Tooltip(self.drag_handle, lambda: self.panel.t('drag_handle_tooltip'))
        _Tooltip(self.bpm_frame, self._bpm_uncertain_tooltip_text)

    def _on_click(self, event=None):
        self.panel.select_song(self.song)

    def _on_remove(self):
        self.panel._remove_song(self.song)

    def set_status(self, status):
        final_color = resolve_color(self.STATUS_COLORS.get(status, SUBTEXT))
        if status == 'ready' and self._last_status == 'analyzing':
            # Breve pulso bianco->verde invece di uno scatto secco, solo sulla
            # vera transizione "appena finito di analizzare" - da' un feedback
            # visibile riga per riga che prima mancava (l'unico segnale
            # d'insieme era la progress bar della fase finale "Avvia correzione").
            _animate_color_pulse(
                lambda hex_c: self.status_dot.configure(image=_render_dot_image(hex_c)),
                "#ffffff", final_color, self.status_dot.after,
            )
        else:
            self.status_dot.configure(image=_render_dot_image(final_color))
        self._last_status = status

    def refresh_theme(self):
        """Ricolora il pallino di stato/la sparkline della riga, che a differenza
        dei widget CTk circostanti non si aggiornano da soli al cambio tema
        chiaro/scuro (il pallino e' un'immagine PIL pre-renderizzata, non un
        colore CTk nativo - vedi _render_dot_image)."""
        self.set_status(self.song.get('_status', 'queued'))
        self.sparkline.configure(bg=resolve_color(CARD2))
        if self.song.get('analysis') is not None:
            self.draw_sparkline(self.song['analysis']['bar_score'])

    def draw_sparkline(self, bar_score):
        c = self.sparkline
        c.delete("spark")
        w, h, pad = self.SPARK_W, 24, 3
        n = len(bar_score) if bar_score is not None else 0
        if n < 2:
            return
        lo, hi = float(min(bar_score)), float(max(bar_score))
        span = (hi - lo) or 1.0
        step = (w - 2 * pad) / (n - 1)
        points = []
        for i, v in enumerate(bar_score):
            x = pad + i * step
            y = (h - pad) - ((float(v) - lo) / span) * (h - 2 * pad)
            points.extend([x, y])
        c.create_line(*points, fill=resolve_color(HIGHLIGHT), width=1.6, tags="spark",
                      smooth=True, splinesteps=24, capstyle="round", joinstyle="round")

    def _status_tooltip_text(self):
        return self.panel.t(f"status_{self.song.get('_status', 'queued')}")

    # -- riordino per trascinamento -------------------------------------------

    def _on_drag_press(self, event):
        self.configure(fg_color=CARD3)
        self.panel._begin_drag(self.song)

    def _on_drag_motion(self, event):
        self.panel._drag_motion(event.y_root)

    def _on_drag_release(self, event):
        self.set_selected(self.panel.current_song is self.song)
        self.panel._end_drag()

    # -- "X" di rimozione al passaggio del mouse -----------------------------
    # <Enter>/<Leave> sono per-widget in Tkinter: muovere il mouse da un'etichetta
    # all'altra DENTRO la stessa riga genera comunque Leave+Enter, quindi un
    # nascondimento immediato al primo Leave farebbe sfarfallare il pulsante.
    # Si rimanda il nascondimento di qualche decina di ms e si verifica, tramite
    # winfo_containing, se il puntatore e' ancora sopra un discendente della riga.

    def _on_hover_enter(self, event=None):
        if self._leave_after_id is not None:
            self.after_cancel(self._leave_after_id)
            self._leave_after_id = None
        if not self._remove_btn_visible:
            self._remove_btn_visible = True
            self.remove_btn.place(relx=1.0, x=-8, rely=0.5, anchor="e")
        # Leggero rialzo/feedback visivo al passaggio del mouse (prima la riga
        # non dava alcun segnale finche' non si notava la X di rimozione) - non
        # tocca lo sfondo se la riga e' gia' quella selezionata, per non
        # confondere i due stati.
        if not self._selected:
            self.configure(fg_color=CARD_HOVER)

    def _on_hover_leave(self, event=None):
        if self._leave_after_id is not None:
            self.after_cancel(self._leave_after_id)
        self._leave_after_id = self.after(60, self._check_still_hovering)

    def _check_still_hovering(self):
        self._leave_after_id = None
        x, y = self.winfo_pointerx(), self.winfo_pointery()
        under = self.winfo_containing(x, y)
        if not self._is_descendant(under):
            self._remove_btn_visible = False
            self.remove_btn.place_forget()
            if not self._selected:
                self.configure(fg_color=CARD2)

    def _is_descendant(self, widget):
        w = widget
        while w is not None:
            if w is self:
                return True
            try:
                w = w.master
            except AttributeError:
                return False
        return False

    def set_selected(self, selected):
        self._selected = selected
        self.configure(fg_color=ACCENT_SOFT if selected else CARD2)

    def set_bpm(self, text):
        self.bpm_label.configure(text=text)

    def set_bpm_uncertain(self, uncertain):
        """Colora il BPM in modo diverso quando la correzione automatica di
        "ottava del tempo" e' intervenuta (vedi _correct_tempo_octave in
        boxvr_generator.py) - un'euristica, non una certezza, quindi vale la pena
        segnalarlo invece di mostrarlo come fosse sicuro al 100%."""
        self._bpm_uncertain = uncertain
        self._refresh_bpm_color()

    def set_suspicious(self, suspicious):
        """Colora il BPM quando il pre-check automatico (beat-grid instabile
        con librosa, vedi recommend_engine_from_beats) segnala il brano come
        da controllare - stesso meccanismo di set_bpm_uncertain, colore diverso
        per distinguere le due cause a colpo d'occhio nella lista."""
        self._suspicious = suspicious
        self._refresh_bpm_color()

    def _refresh_bpm_color(self):
        # sospetto (istabilita' beat-grid) ha priorita' visiva sull'ottava
        # corretta - e' il segnale piu' serio dei due - ma il tooltip elenca
        # entrambi se sono veri contemporaneamente.
        if getattr(self, '_suspicious', False):
            color = ("#c0392b", "#e0654a")
        elif getattr(self, '_bpm_uncertain', False):
            color = ("#b8860b", "#e0a030")
        else:
            color = SUBTEXT
        self.bpm_label.configure(text_color=color)

    def _bpm_uncertain_tooltip_text(self):
        parts = []
        if getattr(self, '_suspicious', False):
            parts.append(self.panel.t('suspicious_bpm_tooltip'))
        if getattr(self, '_bpm_uncertain', False):
            parts.append(self.panel.t('bpm_uncertain_tooltip'))
        return "\n\n".join(parts)

    def set_preset_text(self, text, ratio=None):
        """Testo del chip 'Pugni %'; se ratio e' fornito, tinge anche lo sfondo
        del chip interpolando tra il colore 'misto' e quello 'pugni' (LEVEL_COLORS),
        cosi' a colpo d'occhio si distingue una riga a bassa densita' di pugni da
        una quasi tutta pugni, invece del grigio piatto uguale per tutte le righe."""
        self.preset_chip.configure(text=text)
        if ratio is not None:
            tint = _blend_hex(LEVEL_COLORS[3], LEVEL_COLORS[2], max(0.0, min(1.0, ratio)))
            self.preset_chip.configure(fg_color=_blend_hex(resolve_color(CARD3), tint, 0.35))

    def flash_preset_chip(self, ratio=None):
        """Breve pulso di colore sul chip preset - usato da "applica a tutti" per
        dare un riscontro visibile riga per riga che il valore e' stato copiato
        qui, non solo sul brano corrente (altrimenti l'unico segnale era il chip
        che cambiava testo, facile da perdere scorrendo una lista lunga). Il pulso
        torna a riposo sulla tinta colorata per ratio (vedi set_preset_text), non
        piu' sempre sul grigio piatto, per non "spegnere" il colore appena applicato."""
        if ratio is not None:
            tint = _blend_hex(LEVEL_COLORS[3], LEVEL_COLORS[2], max(0.0, min(1.0, ratio)))
            rest_color = _blend_hex(resolve_color(CARD3), tint, 0.35)
        else:
            rest_color = resolve_color(CARD3)
        _animate_color_pulse(
            lambda hex_c: self.preset_chip.configure(fg_color=hex_c),
            resolve_color(ACCENT_SOFT), rest_color, self.preset_chip.after, steps=10, interval_ms=30,
        )

    def set_name_artist(self, name, artist):
        self.title_label.configure(text=_truncate(name, 21))
        self.artist_label.configure(text=_truncate(artist, 14))


class SongBrowserPanel(ctk.CTkFrame):
    """Elenco brani + anteprima (timeline con curva di energia, preset, playback).

    Riusato identico dalle due schede - `mode` ('correct' o 'generate') decide
    solo come si interpretano i file trascinati, come si analizza un elemento e
    come si lancia l'elaborazione batch; timeline/preset/playback sono identici
    perche' sia compute_song_analysis (correzione) che generate_song_analysis
    (da zero) ritornano un dict con le stesse chiavi. Si puo' trascinare piu'
    volte (cartelle o singoli file): ogni drop si aggiunge all'elenco corrente.
    """

    def __init__(self, parent, app, mode):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.mode = mode

        self.log_queue = queue.Queue()
        self.analysis_queue = queue.Queue()
        self.worker = None
        self.last_output_folder = None
        self.last_track_ids = []       # solo gli id dell'ultima sessione, vedi _on_finished
        self.last_playlist_path = None
        self.base_folder = None  # cartella del primo elemento aggiunto, usata per l'output

        self.songs = []
        self.song_keys = set()
        self.song_rows = {}  # key -> SongRow
        self.current_song = None
        self.player = None
        self._player_song = None
        self._sidecar_recording = False
        self.playhead_id = None
        self.legend_labels = {}
        self._spinner_active = False
        self._spinner_frame = 0
        self._spinner_after_id = None
        self.empty_placeholder = None
        self._log_expanded = False
        self.last_removed = None
        self._undo_after_id = None
        self._drag_active = False
        self._drag_song = None
        self._shadow_layers = []  # vedi _add_soft_shadow/_recolor_shadow_layers

        # Coda di analisi in background: ogni brano appena aggiunto ci finisce dentro
        # subito (non solo quando viene messo in focus), cosi' il BPM compare in lista
        # da solo. Un unico thread persistente la consuma in ordine FIFO - l'analisi e'
        # pesante (filtro passa-basso scipy + beat-tracking librosa), quindi un solo
        # worker seriale evita di saturare la CPU se si trascina una cartella intera.
        self._analysis_pending = queue.Queue()
        threading.Thread(target=self._background_analysis_loop, daemon=True).start()

        self._build_ui()
        self.after(80, self._poll_log_queue)
        self.after(80, self._poll_analysis_queue)
        self.after(150, self._poll_playhead)

    def t(self, key, **kwargs):
        return self.app.t(key, **kwargs)

    # -- costruzione UI -----------------------------------------------------

    def _build_ui(self):
        pad = 16
        self._pad = pad
        # Layout a due colonne affiancate: a sinistra tutto cio' che riguarda
        # l'elenco brani (larghezza fissa, un po' piu' stretta del contenuto che
        # prima occupava l'intera finestra - qui non c'e' piu' spazio vuoto a
        # destra della tabella), a destra anteprima/preset/timeline/azioni/log,
        # che scorre per conto suo dato che resta l'unico blocco potenzialmente
        # piu' alto della finestra.
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        # bg_color=BG esplicito, non "transparent": vedi la stessa nota piu' sotto
        # per self.scroll - qualunque CTkFrame/CTkScrollableFrame la cui catena di
        # genitori tocca la root pura (tk.Tk, non un widget CTk) rileva il proprio
        # bg_color UNA VOLTA SOLA leggendo root.cget("bg") e non lo aggiorna mai
        # piu' al cambio tema, lasciando angoli arrotondati "congelati" nel colore
        # sbagliato - specificarlo esplicitamente lo rende sempre theme-aware.
        left_col = ctk.CTkFrame(body, fg_color=BG, bg_color=BG, width=LEFT_COL_WIDTH)
        left_col.pack(side="left", fill="y", padx=(0, 10))
        left_col.pack_propagate(False)

        self.sub_label = ctk.CTkLabel(left_col, font=ui_font(12), text_color=SUBTEXT, anchor="w", justify="left")
        self.sub_label.pack(fill="x", padx=pad, pady=(pad, 8))

        top_row = ctk.CTkFrame(left_col, fg_color="transparent")
        top_row.pack(fill="x", padx=pad)
        self.browse_btn = ctk.CTkButton(
            top_row, command=self._browse_folder, corner_radius=20, height=42,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white", font=ui_font(12, "medium"),
        )
        self.browse_btn.pack(side="left")
        # Icona-soltanto (non piu' testo): il testo tradotto resta disponibile solo
        # come tooltip al passaggio del mouse, non serve piu' a leggersi il bottone
        # a colpo d'occhio dato che l'icona da sola e' gia' chiara.
        self.clear_btn = ctk.CTkButton(
            top_row, text="", image=_render_emoji_icon("🗑️", 18), command=self._clear_songs,
            corner_radius=20, height=42, width=42,
            fg_color="transparent", hover_color=CARD2, text_color=SUBTEXT, font=ui_font(14),
            border_width=1, border_color=BORDER,
        )
        self.clear_btn.pack(side="left", padx=(8, 0))
        _Tooltip(self.clear_btn, lambda: self.t('clear_list_btn'))
        # Bottone "annulla rimozione": creato subito ma non impacchettato - compare
        # (via .pack in _offer_undo) solo per qualche secondo dopo un click sulla
        # "X" di una riga, e sparisce da solo o al click.
        # ACCENT, non piu' HIGHLIGHT: era l'unico bottone/controllo dell'app a
        # usare il teal, una terza famiglia di colore "chrome" in competizione
        # con indigo (ACCENT) e corallo (ACTION_ACCENT) - HIGHLIGHT resta solo
        # dove marca davvero un dato (curva sparkline, marcatore densita' reale,
        # etichetta fase), non su un bottone interattivo qualsiasi.
        self.undo_btn = ctk.CTkButton(
            top_row, command=self._undo_remove, corner_radius=20, height=42,
            fg_color="transparent", hover_color=CARD2, text_color=ACCENT, font=ui_font(12),
            border_width=1, border_color=ACCENT,
        )
        # Tornato testo+icona (non icona-soltanto come gli altri): l'emoji cartella
        # da sola era ambigua, soprattutto avendo un'altra icona-cartella simile
        # (quella per "Apri cartella risultati") nella stessa schermata.
        self.open_boxvr_btn = ctk.CTkButton(
            top_row, command=self._open_boxvr_folder, corner_radius=20, height=42,
            image=_render_emoji_icon("📂", 16), compound="left",
            fg_color="transparent", hover_color=CARD2, text_color=SUBTEXT, font=ui_font(12),
            border_width=1, border_color=BORDER,
        )
        self.open_boxvr_btn.pack(side="left", padx=(8, 0))
        # Visibile solo in modalita' generazione: qui (a differenza della correzione)
        # nascono file NUOVI che l'utente deve smistare in 2 cartelle diverse del gioco,
        # quindi merita un pulsante che spieghi la destinazione anche PRIMA di aver
        # ancora generato nulla, non solo nel riepilogo a fine elaborazione.
        self.info_btn = None
        if self.mode == 'generate':
            self.info_btn = ctk.CTkButton(
                top_row, command=self._show_generate_info, corner_radius=20, height=42,
                image=_render_emoji_icon("ℹ️", 16), compound="left",
                fg_color="transparent", hover_color=CARD2, text_color=SUBTEXT, font=ui_font(12),
                border_width=1, border_color=BORDER,
            )
            self.info_btn.pack(side="left", padx=(8, 0))

        self.selected_label = ctk.CTkLabel(left_col, font=ui_font(11), text_color=SUBTEXT, anchor="w")
        self.selected_label.pack(fill="x", padx=pad, pady=(8, 0))

        # -- intestazione colonne (allineata alle stesse larghezze/padx di SongRow,
        # + lo scarto fisso del padx=6 con cui ogni riga viene gridata dentro
        # song_list_frame) - resta fuori dalla lista scorrevole cosi' non scorre via.
        header_row_frame = ctk.CTkFrame(left_col, fg_color="transparent")
        header_row_frame.pack(fill="x", padx=pad + 6)
        # Intestazioni cliccabili per ordinare (Titolo/Artista/BPM - il Preset non
        # ha un ordine naturale utile, resta solo etichetta). _sort_key/_sort_reverse
        # tracciano lo stato corrente; un'altra pressione sulla stessa colonna
        # inverte la direzione invece di ripartire sempre da ascendente.
        self._sort_key = None
        self._sort_reverse = False
        self.list_header_title = ctk.CTkLabel(header_row_frame, font=ui_font(11, "semibold"), text_color=SUBTEXT,
                                               anchor="w", width=SongRow.TITLE_W, cursor="hand2")
        self.list_header_title.grid(row=0, column=0, sticky="w", padx=(56, 4))
        self.list_header_title.bind("<Button-1>", lambda e: self._on_sort_click('name'))
        self.list_header_artist = ctk.CTkLabel(header_row_frame, font=ui_font(11, "semibold"), text_color=SUBTEXT,
                                                anchor="w", width=SongRow.ARTIST_W, cursor="hand2")
        self.list_header_artist.grid(row=0, column=1, sticky="w", padx=4)
        self.list_header_artist.bind("<Button-1>", lambda e: self._on_sort_click('artist'))
        self.list_header_bpm = ctk.CTkLabel(header_row_frame, font=ui_font(11, "semibold"), text_color=SUBTEXT,
                                             anchor="center", width=SongRow.BPM_W, cursor="hand2")
        self.list_header_bpm.grid(row=0, column=2, sticky="w", padx=4)
        self.list_header_bpm.bind("<Button-1>", lambda e: self._on_sort_click('bpm'))
        # Placeholder vuoto: allinea la colonna successiva sotto la mini-curva di
        # energia della riga (SongRow.sparkline), che non ha un'intestazione propria
        # (non e' ordinabile).
        spark_placeholder = ctk.CTkLabel(header_row_frame, text="", width=SongRow.SPARK_W)
        spark_placeholder.grid(row=0, column=3, sticky="w", padx=4)
        self.list_header_preset = ctk.CTkLabel(header_row_frame, font=ui_font(11, "semibold"), text_color=SUBTEXT,
                                                anchor="e", width=SongRow.PRESET_W)
        self.list_header_preset.grid(row=0, column=4, sticky="e", padx=(4, 34))

        # -- elenco canzoni (righe-card in una lista scorrevole) -----------------
        # Non piu' un'altezza fissa/regolabile a mano (era una maniglia di
        # ridimensionamento subito sotto - rimossa: la lista ha gia' il suo
        # scroll interno, la maniglia era ridondante). fill="both"+expand=True
        # la fa crescere per riempire tutto lo spazio verticale libero di
        # left_col (che a sua volta occupa sempre l'intera altezza della
        # finestra, vedi fill="y" sul pack di left_col) - cosi' la tabella si
        # allunga da sola quando la finestra e' piu' alta (es. massimizzata),
        # invece di restare piccola con un vuoto sotto.
        self.song_list_frame = ctk.CTkScrollableFrame(
            left_col, fg_color=CARD, corner_radius=28,
        )
        self.song_list_frame.pack(fill="both", expand=True, padx=pad, pady=(4, pad))
        self._add_soft_shadow(self.song_list_frame, left_col)
        self.song_list_frame.grid_columnconfigure(0, weight=1)
        _apply_auto_scrollbar(self.song_list_frame)
        # Vedi _make_inner_scroll_handler: song_list_frame e' un CTkScrollableFrame
        # annidato dentro left_col - senza questo, scrollare sopra la lista canzoni
        # fa scorrere anche il resto (per quanto left_col stesso non scorra piu'
        # dato che non e' un CTkScrollableFrame, il bind diretto resta comunque
        # necessario per evitare che l'evento risalga fino alla colonna destra).
        self.inner_scroll_handler = _make_inner_scroll_handler(self.song_list_frame._parent_canvas)
        self.song_list_frame.bind("<MouseWheel>", self.inner_scroll_handler)
        self._show_empty_placeholder()

        if HAS_DND:
            # song_list_frame e' un CTkScrollableFrame: il rettangolo visibile che
            # riempie l'area sotto la scritta e' in realta' il suo tk.Canvas interno
            # (_parent_canvas), non il CTkFrame esterno stesso - registrare il drop
            # target solo sul frame esterno lascia inerte tutta l'area visibile tranne
            # dove galleggia empty_placeholder (che si registra per conto suo). Stesso
            # tipo di bug gia' visto per lo scroll con la rotellina del mouse (vedi
            # _make_inner_scroll_handler / _apply_auto_scrollbar), stessa causa: la
            # gerarchia interna di CTkScrollableFrame non e' "vista" da chi si aspetta
            # che registrare sul frame esterno basti a coprire tutto cio' che sembra
            # visivamente suo.
            for w in (self.song_list_frame, self.song_list_frame._parent_canvas):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)
                w.dnd_bind("<<DragEnter>>", self._on_drag_enter)
                w.dnd_bind("<<DragLeave>>", self._on_drag_leave)

        # -- colonna destra: anteprima, preset, timeline, azioni, log ------------
        # fg_color=BG esplicito, non "transparent": CTkScrollableFrame e' sostenuto
        # internamente da un tk.Canvas, e la risoluzione di "transparent" per quel
        # canvas resta "congelata" al colore con cui e' stato creato invece di
        # riseguire ctk.set_appearance_mode() al volo - toccando il tema a runtime
        # restava una fascia scura sotto ai pulsanti anche passando al chiaro.
        self.scroll = ctk.CTkScrollableFrame(body, fg_color=BG, bg_color=BG)
        self.scroll.pack(side="left", fill="both", expand=True)
        _apply_auto_scrollbar(self.scroll)

        preview_frame = ctk.CTkFrame(self.scroll, fg_color=CARD, corner_radius=28)
        # pady=(10, 16): il bordo inferiore prima non aveva alcun margine (0) -
        # oltre a sembrare piu' compresso li' che altrove, tagliava di netto
        # l'ombra morbida della card proprio nell'angolo in basso a destra
        # (l'offset verticale dell'ombra non aveva spazio in cui esistere,
        # veniva troncato dal bordo del contenuto scrollabile - segnalato
        # dall'utente come ombra "rotta" in quell'angolo). 16 come gli altri
        # margini, cosi' anche lo spazio attorno alla card torna coerente.
        preview_frame.pack(fill="x", padx=pad, pady=(10, 16))
        self._add_soft_shadow(preview_frame, self.scroll)

        self.song_title_label = ctk.CTkLabel(preview_frame, font=ui_font(15, "semibold"), text_color=TEXT, anchor="w")
        self.song_title_label.pack(fill="x", padx=18, pady=(16, 4 if self.mode == 'correct' else 8))

        # Codice alfanumerico del trackId: solo in correzione, dove il nome del
        # file (<trackId>.trackdata.txt/.wav) e' proprio quell'hash - aiuta a
        # ritrovare il brano dentro TrackData/TrackDefinitions del gioco. In
        # generazione non ha senso mostrarlo qui: il trackId non esiste ancora,
        # viene creato solo al momento di "Genera".
        self.track_id_label = None
        if self.mode == 'correct':
            self.track_id_label = ctk.CTkLabel(preview_frame, font=("Consolas", 10), text_color=SUBTEXT, anchor="w")
            self.track_id_label.pack(fill="x", padx=18, pady=(0, 8))

        # Pannello BPM: solo in generazione, dato che li' il tempo e' rilevato
        # dall'audio (puo' sbagliare) - in correzione il BPM viene letto diretto
        # dal trackdata del gioco, non c'e' nulla da "correggere" li' (la base a
        # click per verificarlo a orecchio, pero', ha senso in entrambe le
        # modalita' - vedi controls_row piu' sotto, condivisa).
        # Contenitore dei controlli dello strumento "Automatica" (30/08,
        # richiesta esplicita di riorganizzazione UI, con schizzo a corredo:
        # timeline in alto, sotto uno switch Automatica/Sidecar, in fondo il
        # blocco di generazione). Creato qui perche' i widget sottostanti
        # (rapporto pugni, densita', intensita') diventano suoi figli, ma il
        # suo .pack() vero e proprio avviene molto piu' sotto, DOPO
        # controls_row - l'ordine di impacchettamento fra fratelli sotto
        # preview_frame e' quello che conta per la posizione a schermo, non
        # l'ordine di creazione nel codice.
        self.automatic_tools_frame = None
        if self.mode == 'generate':
            self.automatic_tools_frame = ctk.CTkFrame(preview_frame, fg_color="transparent")

        # Il pannello BPM NON e' figlio di automatic_tools_frame (30/08,
        # osservazione dell'utente confermata): il BPM/la griglia di beat che
        # ne deriva servono anche alla sidecar, non solo alla generazione
        # automatica - _place_on_markers decide corsia/tipo/lato guardando
        # beatInBar e il gap in BEAT dall'ultima mossa (CENTRO_PROB_TABLE,
        # CENTRO_TYPE_PROBS_BY_GAP*, sidecar sandbox/engine.py), ed enforce_
        # playability applica i suoi vincoli di spaziatura anch'essi in beat
        # (boxvr_choreo.MIN_GAP_BEATS e affini) - un BPM sbagliato sposta
        # quella griglia per ENTRAMBI gli strumenti, non solo per Automatica.
        # Resta quindi figlio diretto di preview_frame, impacchettato vicino
        # al volume (zoom_row, piu' sotto) - visibile sempre, non nascosto
        # dietro lo switch Automatica/Sidecar. Creato qui, impacchettato li'
        # (stesso schema differito di automatic_tools_frame sopra).
        self.bpm_panel = None
        if self.mode == 'generate':
            self.bpm_panel = ctk.CTkFrame(preview_frame, fg_color="transparent")
            self.bpm_value_label = ctk.CTkLabel(self.bpm_panel, font=ui_font(12, "medium"), text_color=TEXT)
            self.bpm_value_label.pack(side="left")
            self.bpm_warning_label = ctk.CTkLabel(self.bpm_panel, text="", image=_render_emoji_icon("⚠️", 15), width=22)
            # non impacchettata di default: solo se il brano corrente ha
            # tempo_corrected=True (vedi _update_bpm_panel)
            _Tooltip(self.bpm_warning_label, lambda: self.t('bpm_uncertain_tooltip'))

            # Bottone "verifica online": compare solo se il pre-check automatico ha
            # segnalato il brano come sospetto (beat-grid instabile con librosa - vedi
            # recommend_engine_from_beats). Apre nel browser predefinito una ricerca
            # gia' pronta invece di provare a leggere il BPM in autonomo (scraping
            # fragile/API con account+backlink, entrambi scartati - vedi
            # bpm_search_url in boxvr_generator.py) - stesso identico gesto che farebbe
            # l'utente a mano, solo un click piu' vicino.
            self.bpm_search_btn = ctk.CTkLabel(
                self.bpm_panel, text="", image=_render_emoji_icon("🔎", 15), width=22, cursor="hand2",
            )
            self.bpm_search_btn.bind("<Button-1>", lambda e: self._open_bpm_search())
            _Tooltip(self.bpm_search_btn, lambda: self.t('suspicious_bpm_tooltip'))

            # Campo BPM modificabile in linea + frecce +-1, non piu' un dialog
            # modale (che interrompeva il flusso e non dava un riscontro immediato
            # riascoltando con la base a click).
            self.bpm_entry_var = tk.StringVar()
            self.bpm_entry = ctk.CTkEntry(
                self.bpm_panel, textvariable=self.bpm_entry_var, width=58, height=26,
                font=ui_font(11, "medium"), justify="center", fg_color=CARD3, border_width=0,
            )
            self.bpm_entry.pack(side="left", padx=(10, 2))
            self.bpm_entry.bind("<Return>", self._on_bpm_entry_commit)

            stepper_col = ctk.CTkFrame(self.bpm_panel, fg_color="transparent")
            stepper_col.pack(side="left")
            self.bpm_up_btn = ctk.CTkButton(
                stepper_col, text="▲", command=lambda: self._step_bpm(1), width=20, height=13,
                corner_radius=4, font=ui_font(8), fg_color=CARD3, hover_color=CARD_HOVER, text_color=TEXT,
            )
            self.bpm_up_btn.pack(pady=(0, 1))
            self.bpm_down_btn = ctk.CTkButton(
                stepper_col, text="▼", command=lambda: self._step_bpm(-1), width=20, height=13,
                corner_radius=4, font=ui_font(8), fg_color=CARD3, hover_color=CARD_HOVER, text_color=TEXT,
            )
            self.bpm_down_btn.pack()

            # Motore di beat-tracking alternativo (madmom, via un sottoprocesso
            # esterno - vedi boxvr_generator.py:detect_beats_and_bars) - piu'
            # lento (minuti invece di secondi a brano) ma piu' robusto ai cambi
            # di tempo locali/sezione, validato empiricamente sui brani reali
            # segnalati dall'utente come "fuori sincro". Per-brano come
            # punch_ratio/density, non una scelta unica per l'intera sessione.
            # Disabilitato (mai crash) se madmom_worker.exe non e' presente in
            # questa build - vedi is_madmom_available.
            self.beat_engine_switch = ctk.CTkSwitch(
                self.bpm_panel, text="", font=ui_font(11), text_color=TEXT, progress_color=ACCENT,
                button_color=TEXT, fg_color=CARD3, command=self._on_beat_engine_toggle,
            )
            self.beat_engine_switch.pack(side="left", padx=(10, 4))
            if not is_madmom_available():
                self.beat_engine_switch.configure(state="disabled")
            self._info_icon(
                self.bpm_panel,
                'beat_engine_tooltip' if is_madmom_available() else 'beat_engine_unavailable_tooltip',
                side="left")

        # I 3 preset a scelta fissa (50/50, 70/30, 90/10) sono stati rimossi: misurato
        # su dati reali che il 15% dei segmenti piu' energici va sempre a pugni puri
        # a prescindere dal preset scelto, quindi su molti brani il preset non
        # cambiava visibilmente nulla (vedi [[boxvr-gui-tool]]). Sostituiti con
        # un unico slider continuo (0-100%) che governa lo stesso punch_ratio, cosi'
        # l'utente puo' scegliere qualunque punto intermedio invece di 3 soli scatti,
        # con l'anteprima aggiornata dal vivo come gli altri slider dell'app.
        # In correzione questo controllo sta direttamente in preview_frame
        # (nessuno strumento Automatica/Sidecar li' - non esiste la sidecar);
        # in generazione diventa un figlio di automatic_tools_frame.
        punch_parent = self.automatic_tools_frame if self.mode == 'generate' else preview_frame
        punch_row = ctk.CTkFrame(punch_parent, fg_color="transparent")
        punch_row.pack(fill="x", padx=18)
        self.punch_label = ctk.CTkLabel(punch_row, font=ui_font(11), text_color=TEXT, anchor="w")
        self.punch_label.pack(side="left")
        self.punch_value_label = ctk.CTkLabel(punch_row, text="50%", font=ui_font(11, "medium"), text_color=ACCENT)
        self.punch_value_label.pack(side="left", padx=(6, 0))

        self.apply_all_btn = ctk.CTkButton(
            punch_row, text="↔", command=self._apply_preset_to_all, corner_radius=18, height=28, width=28,
            fg_color="transparent", hover_color=CARD_HOVER, text_color=SUBTEXT, font=ui_font(12),
            border_width=1, border_color=BORDER,
        )
        self.apply_all_btn.pack(side="right")
        _Tooltip(self.apply_all_btn, lambda: self.t('apply_all_btn'))

        self.punch_ratio_slider = ctk.CTkSlider(
            punch_parent, from_=0.0, to=1.0, number_of_steps=100, height=16,
            progress_color=ACCENT, button_color=TEXT, button_hover_color=ACCENT_HOVER,
            fg_color=CARD3, command=self._on_punch_ratio_slide,
        )
        self.punch_ratio_slider.set(0.5)
        self.punch_ratio_slider.pack(fill="x", padx=18, pady=(6, 8))

        # Margine di confidenza (correzione) / Densita' colpi (generazione): prima
        # vivevano in opts_frame, sotto la sezione di playback, visivamente lontani
        # dalla timeline che invece ridisegnano dal vivo appena li si muove -
        # spostati qui accanto ad essa seguendo il principio di controllo-vicino-
        # alla-visualizzazione (Nielsen Norman Group, "Data Visualizations for
        # Dashboards": i controlli di una singola visualizzazione vanno posizionati
        # accanto ad essa, non altrove nella pagina).
        if self.mode == 'correct':
            self.density_label = None
            self.density_value_label = None
            self.density_slider = None
            self.choreo_preset_label = None
            self.choreo_preset_menu = None
            self._choreo_preset_key = 'medium'
            margin_head = ctk.CTkFrame(preview_frame, fg_color="transparent")
            margin_head.pack(fill="x", padx=18)
            self.margin_label = ctk.CTkLabel(margin_head, font=ui_font(11), text_color=TEXT, anchor="w")
            self.margin_label.pack(side="left")
            saved_margin = self.app.settings.get('margin', 0.12)
            self.margin_value_label = ctk.CTkLabel(margin_head, text=f"{saved_margin:.2f}", font=ui_font(11, "medium"), text_color=ACCENT)
            self.margin_value_label.pack(side="left", padx=(6, 0))
            self._info_icon(margin_head, 'margin_info_tooltip', side="left", padx=(6, 0))
            self.margin_slider = ctk.CTkSlider(
                preview_frame, from_=0.0, to=1.0, number_of_steps=100, height=16,
                progress_color=ACCENT, button_color=TEXT, button_hover_color=ACCENT_HOVER,
                fg_color=CARD3, command=self._on_margin_slide,
            )
            self.margin_slider.set(saved_margin)
            self.margin_slider.pack(fill="x", padx=18, pady=(4, 10))
        else:
            self.margin_label = None
            self.margin_value_label = None
            self.margin_slider = None
            # Densita' colpi: ora per-brano come il rapporto pugni/misto (prima era
            # un'unica impostazione per l'intera sessione di generazione - vedi
            # _on_density_slide/_apply_preset_to_all).
            density_head = ctk.CTkFrame(self.automatic_tools_frame, fg_color="transparent")
            density_head.pack(fill="x", padx=18)
            self.density_label = ctk.CTkLabel(density_head, font=ui_font(11), text_color=TEXT, anchor="w")
            self.density_label.pack(side="left")
            saved_density = self.app.settings.get('density', 1.0)
            self.density_value_label = ctk.CTkLabel(density_head, text=f"{saved_density:.2f}",
                                                      font=ui_font(11, "medium"), text_color=SUBTEXT)
            self.density_value_label.pack(side="left", padx=(6, 0))
            # audit 2026-08-23: questo slider (e il rapporto pugni/misto sopra)
            # scrivono SOLO _energyLevel nel trackdata, che con la patch attiva
            # - obbligatoria in questa modalita' - il gioco ignora, e che la
            # coreografia non legge affatto (parte da bar_score, vedi
            # boxvr_choreo.segment_energies). Restano perche' servono davvero a
            # gioco ripristinato, ma vanno presentati per quello che sono,
            # altrimenti sembrano governare l'allenamento senza farlo.
            self._info_icon(density_head, 'density_legacy_tooltip', side="left", padx=(6, 0))
            self.density_slider = ctk.CTkSlider(
                self.automatic_tools_frame, from_=0.0, to=1.0, number_of_steps=100, height=16,
                progress_color=ACCENT, button_color=TEXT, button_hover_color=ACCENT_HOVER,
                fg_color=CARD3, command=self._on_density_slide,
            )
            self.density_slider.set(saved_density)
            self.density_slider.pack(fill="x", padx=18, pady=(4, 10))
            # Marcatore al 50%: quel punto e' tarato per corrispondere alla
            # densita' media REALE misurata sui trackdata originali di BoxVR
            # (vedi DENSITY_ANCHORS in boxvr_generator.py) - senza questo
            # indizio visivo non e' affatto intuitivo che "50" sullo slider
            # significhi "come il gioco vero", non un punto medio qualsiasi.
            self.density_real_marker = ctk.CTkLabel(
                self.automatic_tools_frame, text="▼", font=ui_font(13), text_color=HIGHLIGHT,
                fg_color="transparent", width=0, height=0,
            )
            self.density_real_marker.place(in_=self.density_slider, relx=0.5, rely=0.0, anchor="s", y=-2)
            _Tooltip(self.density_real_marker, lambda: self.t('density_real_marker_tooltip'))

            # Intensita' della COREOGRAFIA scritta (boxvr_choreo.INTENSITY_PRESETS):
            # diversa dalla densita' sopra, che governa i livelli di energia del
            # trackdata - questa governa quanti/quali colpi vengono scritti nella
            # lista azioni, cioe' cosa si gioca davvero a patch attiva. Per-brano
            # come tutto il resto, cosi' una playlist puo' mescolare brani piu' o
            # meno intensi.
            choreo_head = ctk.CTkFrame(self.automatic_tools_frame, fg_color="transparent")
            choreo_head.pack(fill="x", padx=18, pady=(2, 0))
            self.choreo_preset_label = ctk.CTkLabel(choreo_head, font=ui_font(11), text_color=TEXT, anchor="w")
            self.choreo_preset_label.pack(side="left")
            self._info_icon(choreo_head, 'choreo_preset_tooltip', side="left", padx=(6, 0))
            self.choreo_preset_menu = ctk.CTkSegmentedButton(
                self.automatic_tools_frame, values=[self.t('choreo_light'), self.t('choreo_medium'), self.t('choreo_high')],
                command=self._on_choreo_preset_change, height=28, font=ui_font(11),
                fg_color=CARD3, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
                unselected_color=CARD3, unselected_hover_color=CARD_HOVER, text_color=TEXT,
            )
            self._choreo_preset_key = self.app.settings.get('choreo_preset') or 'medium'
            self.choreo_preset_menu.set(self._choreo_preset_label(self._choreo_preset_key))
            self.choreo_preset_menu.pack(fill="x", padx=18, pady=(4, 2))

            # Colpi/min attesi + riferimento ufficiale BoxVR (richiesta del
            # 26/08: "esporre il valore di colpi medi al minuto, così da fargli
            # vedere quale sarebbe l'intervallo classico di boxvr e quanto può
            # aumentarlo"). Valori MISURATI sulla coreografia davvero prodotta,
            # non teorici - vedi INTENSITY_PRESETS in boxvr_choreo.py.
            self.choreo_epm_label = ctk.CTkLabel(
                self.automatic_tools_frame, font=ui_font(10), text_color=SUBTEXT, anchor="w")
            self.choreo_epm_label.pack(fill="x", padx=18, pady=(0, 10))
            _Tooltip(self.choreo_epm_label, lambda: self.t('choreo_epm_tooltip'))
            self._refresh_choreo_epm()

        # Fascia "originale" (struttura eventi cosi' come letta dal file del gioco,
        # _energyLevel non toccato da preset/margine): solo in correzione, dove ha
        # senso un prima/dopo - in generazione non esiste un "originale da BoxVR"
        # con cui confrontare, il brano viene creato ex novo. Sempre visibile
        # (non un toggle) cosi' l'effetto del preset/margine si vede a colpo
        # d'occhio senza dover cliccare avanti e indietro tra due viste.
        self.orig_timeline_label = None
        self.canvas_original = None
        self.corrected_timeline_label = None
        self._orig_timeline_regions = []
        if self.mode == 'correct':
            self.orig_timeline_label = ctk.CTkLabel(preview_frame, font=ui_font(10, "medium"), text_color=SUBTEXT, anchor="w")
            self.orig_timeline_label.pack(fill="x", padx=18, pady=(12, 2))
            self.canvas_original = tk.Canvas(preview_frame, height=22, bg=resolve_color(TIMELINE_BG), highlightthickness=0)
            self.canvas_original.pack(fill="x", padx=18, pady=(0, 4))
            self.canvas_original.bind("<Configure>", lambda e: self._render_timeline())
            _CanvasHoverTooltip(self.canvas_original, lambda e: self._region_tooltip_text(self._orig_timeline_regions, e.x))

            self.corrected_timeline_label = ctk.CTkLabel(preview_frame, font=ui_font(10, "medium"), text_color=SUBTEXT, anchor="w")
            self.corrected_timeline_label.pack(fill="x", padx=18, pady=(4, 2))

        # Zoom orizzontale sulla timeline principale: su un brano lungo (4-5 minuti,
        # 40+ segmenti reali da ~5-20s l'uno) l'intero brano compresso in una sola
        # larghezza fissa rende i segmenti brevi larghi pochi pixel, difficili da
        # leggere/agganciare anche coi separatori. self.zoom/self.view_start (in
        # secondi) sono stato del pannello, azzerati ad ogni cambio brano in
        # select_song. Trascinare col tasto sinistro sulla timeline principale
        # scorre la vista quando zoom>1 (vedi _on_canvas_press/_drag/_release);
        # un click "secco" (senza trascinamento) resta un seek come prima.
        # BPM impacchettato qui, appena sopra zoom/volume (30/08): stessa
        # riga di "controlli che riguardano il brano nella sua interezza",
        # non nascosto dentro lo strumento Automatica - vedi il commento
        # dov'e' costruito, molto piu' sopra, per il perche'.
        if self.bpm_panel is not None:
            self.bpm_panel.pack(fill="x", padx=18, pady=(0, 6))

        self.zoom = 1.0
        self.view_start = 0.0
        zoom_row = ctk.CTkFrame(preview_frame, fg_color="transparent")
        zoom_row.pack(fill="x", padx=18, pady=(0, 2))
        self.zoom_label = ctk.CTkLabel(zoom_row, text="", image=_render_emoji_icon("🔍", 15))
        self.zoom_label.pack(side="left", padx=(0, 4))
        self.zoom_slider = ctk.CTkSlider(
            zoom_row, from_=1.0, to=8.0, number_of_steps=70, width=110, height=14,
            progress_color=ACCENT, button_color=TEXT, button_hover_color=ACCENT_HOVER,
            fg_color=CARD3, command=self._on_zoom_slide,
        )
        self.zoom_slider.set(1.0)
        self.zoom_slider.pack(side="left")
        self.zoom_value_label = ctk.CTkLabel(zoom_row, text="1.0x", font=ui_font(10), text_color=SUBTEXT)
        self.zoom_value_label.pack(side="left", padx=(6, 0))
        _Tooltip(self.zoom_label, lambda: self.t('zoom_tooltip'))

        # Volume spostato qui accanto allo zoom (prima stava nella riga dei
        # controlli di playback, lontano dalla timeline) - entrambi si
        # riferiscono a come si sta visualizzando/ascoltando il brano in
        # anteprima, non all'azione di riproduzione in se' (play/pausa), quindi
        # stanno meglio raggruppati con lo zoom che con quella.
        self.volume_label = ctk.CTkLabel(zoom_row, text="", image=_render_emoji_icon("🔊", 15))
        self.volume_label.pack(side="right")
        self.volume_slider = ctk.CTkSlider(
            zoom_row, from_=0.0, to=1.0, number_of_steps=100, width=90, height=14,
            progress_color=ACCENT, button_color=TEXT, button_hover_color=ACCENT_HOVER,
            fg_color=CARD3, command=self._on_volume_slide,
        )
        self.volume_slider.set(self.app.settings.get('volume', 1.0))
        self.volume_slider.pack(side="right", padx=(0, 6))
        _Tooltip(self.volume_label, lambda: self.t('volume_tooltip'))

        self._timeline_regions = []
        self.canvas = tk.Canvas(preview_frame, height=104, bg=resolve_color(TIMELINE_BG), highlightthickness=0)
        self.canvas.pack(fill="x", padx=18, pady=(0 if self.mode == 'correct' else 12, 6))
        self.canvas.bind("<Configure>", lambda e: self._render_timeline())
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        _CanvasHoverTooltip(self.canvas, lambda e: self._region_tooltip_text(self._timeline_regions, e.x))

        legend_row = ctk.CTkFrame(preview_frame, fg_color="transparent")
        legend_row.pack(fill="x", padx=18, pady=(0, 8))
        # I 4 pallini+etichette vivevano sciolti direttamente su legend_row -
        # stesso difetto gia' corretto per il cluster tema/lingua (audit
        # Dribbble): controlli imparentati senza un contenitore visivo che li
        # tenga insieme si leggono come elementi sparsi, non come un gruppo
        # "legenda". Ora e' un'unica pillola-card (fg_color=CARD2, un filo
        # piu' tenue di CARD dato che qui e' puramente informativo, non
        # interattivo) che li contiene tutti.
        legend_card = ctk.CTkFrame(legend_row, fg_color=CARD2, corner_radius=14)
        legend_card.pack(side="left")
        for lvl in (0, 1, 2, 3):
            # Pallino anti-aliasato via PIL (supersampling + LANCZOS, vedi
            # _render_dot_image) - un tk.Canvas con create_oval non anti-alias
            # a piccola dimensione (uscivano "a scalini"), un CTkLabel con
            # corner_radius e' un rounded-rect rasterizzato che a sua volta
            # sfocava con lo scaling OS (125% su questa macchina). L'immagine
            # PIL pre-ridotta con un filtro di qualita' evita entrambi i problemi
            # e non serve nemmeno piu' seguire il colore di sfondo per tema,
            # dato che ha canale alpha (fg_color="transparent").
            dot = ctk.CTkLabel(legend_card, text="", fg_color="transparent",
                                image=_render_dot_image(resolve_color(LEVEL_COLORS[lvl])), width=16, height=16)
            dot.pack(side="left", padx=(12 if lvl == 0 else 0, 6), pady=8)
            lbl = ctk.CTkLabel(legend_card, font=ui_font(12), text_color=SUBTEXT)
            lbl.pack(side="left", padx=(0, 14 if lvl < 3 else 12), pady=8)
            self.legend_labels[lvl] = lbl

        # Modalita' della timeline: "Curva" (l'andamento continuo dell'energia,
        # gia' esistente) o "Colpi" (una tacca per ogni singolo beat, colorata
        # come la fase a cui appartiene - da' il colpo d'occhio su quanti colpi
        # ci sono davvero in una fase invece che solo sulla sua energia media).
        self.timeline_mode = 'curve'
        self.timeline_mode_buttons = {}
        mode_toggle = ctk.CTkFrame(legend_row, fg_color="transparent")
        mode_toggle.pack(side="right")
        for mode_key in ('curve', 'beats'):
            b = ctk.CTkButton(
                mode_toggle, text="", command=lambda m=mode_key: self._set_timeline_mode(m),
                corner_radius=12, height=24, width=64, font=ui_font(10, "medium"),
                fg_color=CARD3, hover_color=CARD_HOVER, text_color=TEXT,
            )
            b.pack(side="left", padx=(4, 0))
            self.timeline_mode_buttons[mode_key] = b

        controls_row = ctk.CTkFrame(preview_frame, fg_color="transparent")
        controls_row.pack(fill="x", padx=18, pady=(0, 18))
        self.play_btn = ctk.CTkButton(
            controls_row, command=self._toggle_play, state="disabled", height=38,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white", font=ui_font(12, "medium"),
        )
        self.play_btn.pack(side="left")
        self.time_label = ctk.CTkLabel(controls_row, text="00:00 / 00:00", text_color=SUBTEXT, font=("Consolas", 11))
        self.time_label.pack(side="left", padx=(12, 0))

        # Base a click: in ENTRAMBE le modalita', non solo in generazione - in
        # correzione non serve a verificare una NOSTRA rilevazione (il BPM viene
        # letto diretto dal trackdata del gioco), ma aiuta comunque a sentire come
        # il gioco stesso ha interpretato il tempo del brano originale. Switch +
        # etichetta racchiusi in un unico chip (fg_color proprio, non transparent)
        # invece di stare "sciolti" fianco a fianco nella riga - si leggevano come
        # due controlli scollegati, cosi' si leggono come un solo controllo.
        click_track_chip = ctk.CTkFrame(controls_row, fg_color=CARD3, corner_radius=14)
        click_track_chip.pack(side="left", padx=(18, 0))
        self.click_track_switch = ctk.CTkSwitch(
            click_track_chip, text="", font=ui_font(10), progress_color=SUCCESS, button_color=TEXT,
            fg_color=CARD_HOVER, command=self._on_click_track_toggle, width=34,
        )
        self.click_track_switch.pack(side="left", padx=(8, 4), pady=6)
        self.click_track_label = ctk.CTkLabel(click_track_chip, font=ui_font(10), text_color=SUBTEXT)
        self.click_track_label.pack(side="left", padx=(0, 10), pady=6)

        # Anteprima visiva: solo in generazione, perche' e' l'unica modalita' in
        # cui esiste una coreografia da guardare (in correzione si cambiano i
        # livelli, i colpi li sceglie il gioco). Serve a giudicare un brano senza
        # indossare il visore: ogni prova in VR costa una sessione intera.
        self.visual_btn = None
        if self.mode == 'generate':
            self.visual_btn = ctk.CTkButton(
                controls_row, command=self._open_visual_preview, state="disabled", height=38,
                fg_color=CARD3, hover_color=CARD_HOVER, text_color=TEXT, font=ui_font(12, "medium"),
            )
            self.visual_btn.pack(side="left", padx=(18, 0))

        self.phase_label = ctk.CTkLabel(controls_row, text="", text_color=HIGHLIGHT, font=ui_font(12, "medium"))
        self.phase_label.pack(side="right")

        # Switch Automatica/Sidecar (30/08, richiesta esplicita di
        # riorganizzazione UI, con schizzo a corredo): "Automatico" prima era
        # una delle tre voci DENTRO il menu modalita' della sidecar
        # (MODE_AUTOMATIC) - qui diventa invece lo strumento di generazione
        # classico (rapporto pugni/densita'/intensita', quello che il tool
        # ha sempre avuto), scelto esplicitamente allo stesso livello della
        # sidecar, non annidato in essa. La timeline sopra resta comune a
        # entrambi; il blocco "Genera" resta sempre in fondo (opts_frame,
        # gia' fuori da preview_frame, invariato).
        self.generate_tool_switch = None
        self.generate_tool = 'automatic'
        if self.mode == 'generate':
            self.generate_tool_switch = ctk.CTkSegmentedButton(
                preview_frame, command=self._on_generate_tool_change, height=30, font=ui_font(11, "medium"),
                fg_color=CARD3, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
                unselected_color=CARD3, unselected_hover_color=CARD_HOVER, text_color=TEXT,
                values=[self.t('generate_tool_automatic'), self.t('generate_tool_sidecar')],
            )
            self.generate_tool_switch.set(self.t('generate_tool_automatic'))
            self.generate_tool_switch.pack(fill="x", padx=18, pady=(0, 14))

        # Sidecar (26/08 notte): l'utente marca a mano gli istanti mentre
        # ascolta, con lo STESSO player del pulsante Play qui sopra - non un
        # secondo motore audio. Prima integrazione nel tool vero del motore
        # gia' scritto e testato in isolamento (sidecar sandbox/engine.py,
        # 43 test verdi): "Registra" riparte dall'inizio e fa partire la
        # riproduzione, "Marca" registra l'istante corrente (mai la corsia,
        # mai il tipo di colpo - li decide l'algoritmo, esattamente come per
        # gli accenti audio veri). I marker sono una BASE, non l'intero
        # brano: la generazione automatica riempie comunque il resto.
        self.sidecar_frame = None
        self.sidecar_record_btn = self.sidecar_clear_btn = self.sidecar_reset_btn = None
        self.sidecar_count_label = self.sidecar_usage_label = None
        self.sidecar_mark_area = None
        self.sidecar_mode_menu = self.sidecar_exclude_switch = self.sidecar_exclude_label = None
        self.sidecar_min_gap_slider = self.sidecar_min_gap_value_label = None
        self.sidecar_min_gap_dropped_label = self.sidecar_min_gap_real_marker = None
        self.sidecar_min_gap_label = None
        if self.mode == 'generate':
            # Non impacchettato subito (30/08): quale dei due strumenti e'
            # visibile lo decide _apply_generate_tool_visibility, chiamata a
            # fine costruzione pannello e ad ogni cambio switch/brano - di
            # default parte "Automatica" (automatic_tools_frame).
            sidecar_frame = ctk.CTkFrame(preview_frame, fg_color=CARD3, corner_radius=14)
            self.sidecar_frame = sidecar_frame

            # Area di click GRANDE per "Marca" (richiesta dall'utente il 27/08,
            # con schizzo a corredo): il piccolo pulsante nella riga sotto
            # basta a chi usa il mouse con precisione, ma per marcare A TEMPO
            # mentre si ascolta un bersaglio grande e a destra e' molto piu'
            # comodo da colpire ripetutamente senza mancarlo - stesso comando
            # (_sidecar_mark) - anche da tastiera, tasti F/K (vedi il bind
            # piu' sotto), utile per non dover mirare col mouse mentre si
            # ascolta a tempo. Il pulsante "Marca" piccolo separato e' stato
            # tolto il 27/08 su richiesta esplicita: ridondante con questa.
            self.sidecar_mark_area = ctk.CTkButton(
                sidecar_frame, command=self._sidecar_mark, width=150,
                fg_color=CARD_HOVER, hover_color=ACCENT_HOVER, text_color=TEXT,
                font=ui_font(15, "bold"), corner_radius=12, border_width=2,
                border_color=ACCENT, state="disabled",
            )
            self.sidecar_mark_area.pack(side="right", fill="y", padx=(0, 14), pady=14)

            sidecar_left = ctk.CTkFrame(sidecar_frame, fg_color="transparent")
            sidecar_left.pack(side="left", fill="both", expand=True)

            sidecar_head = ctk.CTkFrame(sidecar_left, fg_color="transparent")
            sidecar_head.pack(fill="x", padx=14, pady=(10, 2))
            self.sidecar_title_label = ctk.CTkLabel(sidecar_head, font=ui_font(11, "medium"), text_color=TEXT, anchor="w")
            self.sidecar_title_label.pack(side="left")
            self._info_icon(sidecar_head, 'sidecar_tooltip', side="left", padx=(6, 0))

            sidecar_row = ctk.CTkFrame(sidecar_left, fg_color="transparent")
            sidecar_row.pack(fill="x", padx=14, pady=(4, 4))
            self.sidecar_record_btn = ctk.CTkButton(
                sidecar_row, command=self._sidecar_toggle_record, height=32, width=110,
                fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white", font=ui_font(11, "medium"),
                state="disabled",
            )
            self.sidecar_record_btn.pack(side="left")
            self.sidecar_clear_btn = ctk.CTkButton(
                sidecar_row, command=self._sidecar_clear, height=32, width=90,
                fg_color="transparent", hover_color=CARD_HOVER, text_color=SUBTEXT, font=ui_font(11),
                state="disabled",
            )
            self.sidecar_clear_btn.pack(side="left", padx=(8, 0))
            # "Resetta" (30/08, richiesto esplicitamente insieme al cambio di
            # comportamento di "Registra" - ora un punch-in che non azzera
            # piu' nulla da solo, vedi _sidecar_toggle_record): un reset
            # COMPLETO del brano (marker + modalita' + "solo hit marker" +
            # soglia minima, tutto ai valori di default), non solo i marker
            # come "Cancella" - per quando si vuole ripartire davvero da
            # zero su un brano, non solo rifare i colpi.
            self.sidecar_reset_btn = ctk.CTkButton(
                sidecar_row, command=self._sidecar_reset, height=32, width=90,
                fg_color="transparent", hover_color=CARD_HOVER, text_color=SUBTEXT, font=ui_font(11),
                state="disabled",
            )
            self.sidecar_reset_btn.pack(side="left", padx=(8, 0))
            self.sidecar_count_label = ctk.CTkLabel(sidecar_row, font=("Consolas", 11), text_color=SUBTEXT)
            self.sidecar_count_label.pack(side="left", padx=(14, 0))

            # Niente interruttore "usa questi marker" (tolto il 27/08 su
            # richiesta esplicita, dopo che l'utente si e' confuso avendo
            # registrato marker ma dimenticato di accenderlo): se i marker
            # ci sono, si usano - se non li vuoi, li cancelli con Cancella.
            # Una sola fonte di verita' (la lista), non lista+interruttore
            # che potevano disallinearsi.
            self.sidecar_usage_label = ctk.CTkLabel(
                sidecar_left, font=ui_font(10), text_color=SUBTEXT, anchor="w", justify="left")
            self.sidecar_usage_label.pack(fill="x", padx=14, pady=(0, 8))

            # Modalita' (27/08, richiesta esplicita): quanto i marker
            # "pesano" rispetto alla coreografia automatica vera - vedi
            # sidecar sandbox/engine.py, MODE_* per il significato esatto di
            # ciascuna. Per-brano come preset/densita'.
            sidecar_mode_head = ctk.CTkFrame(sidecar_left, fg_color="transparent")
            sidecar_mode_head.pack(fill="x", padx=14, pady=(0, 2))
            self.sidecar_mode_label = ctk.CTkLabel(sidecar_mode_head, font=ui_font(10), text_color=TEXT, anchor="w")
            self.sidecar_mode_label.pack(side="left")
            self._info_icon(sidecar_mode_head, 'sidecar_mode_tooltip', side="left", padx=(6, 0))
            self.sidecar_mode_menu = ctk.CTkSegmentedButton(
                sidecar_left, command=self._on_sidecar_mode_change, height=26, font=ui_font(10),
                fg_color=CARD3, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
                unselected_color=CARD3, unselected_hover_color=CARD_HOVER, text_color=TEXT,
            )
            self.sidecar_mode_menu.pack(fill="x", padx=14, pady=(0, 8))

            # "Solo hit marker" (27/08, richiesta esplicita): sui marker mai
            # Squat/Dodge, solo Block o un colpo - gli ostacoli restano
            # sempre una scelta autonoma dell'algoritmo, anche in modalita'
            # "Solo marker". Spiegato in tooltip perche' l'effetto non e'
            # ovvio dal solo nome dello switch.
            sidecar_excl_row = ctk.CTkFrame(sidecar_left, fg_color="transparent")
            sidecar_excl_row.pack(fill="x", padx=14, pady=(0, 10))
            self.sidecar_exclude_switch = ctk.CTkSwitch(
                sidecar_excl_row, text="", font=ui_font(10), progress_color=SUCCESS, button_color=TEXT,
                fg_color=CARD_HOVER, command=self._on_sidecar_exclude_toggle, width=34,
            )
            self.sidecar_exclude_switch.pack(side="left")
            self.sidecar_exclude_label = ctk.CTkLabel(sidecar_excl_row, font=ui_font(10), text_color=SUBTEXT, anchor="w")
            self.sidecar_exclude_label.pack(side="left", padx=(8, 0))
            self._info_icon(sidecar_excl_row, 'sidecar_exclude_tooltip', side="left", padx=(4, 0))

            # Soglia minima fra due marker (30/08, richiesta esplicita dopo
            # aver scoperto - analizzando un test reale su Master of Puppets
            # - che ~1/3 dei marker di un riff veloce venivano scartati IN
            # SILENZIO da MIN_INPUT_GAP_S, 170ms): invece di imporre quel
            # valore come tetto invalicabile, lo si rende uno slider con
            # indicatore live di quanti marker verrebbero scartati alla
            # soglia corrente - la scelta di scendere sotto il minimo
            # misurato sui 465 workout ufficiali resta dell'utente, informata.
            sidecar_gap_head = ctk.CTkFrame(sidecar_left, fg_color="transparent")
            sidecar_gap_head.pack(fill="x", padx=14, pady=(0, 2))
            self.sidecar_min_gap_label = ctk.CTkLabel(sidecar_gap_head, font=ui_font(10), text_color=TEXT, anchor="w")
            self.sidecar_min_gap_label.pack(side="left")
            self.sidecar_min_gap_value_label = ctk.CTkLabel(
                sidecar_gap_head, text=f"{SIDECAR_MIN_GAP_DEFAULT_MS} ms",
                font=ui_font(10, "medium"), text_color=SUBTEXT)
            self.sidecar_min_gap_value_label.pack(side="left", padx=(6, 0))
            self._info_icon(sidecar_gap_head, 'sidecar_min_gap_tooltip', side="left", padx=(6, 0))
            self.sidecar_min_gap_slider = ctk.CTkSlider(
                sidecar_left, from_=SIDECAR_MIN_GAP_MIN_MS, to=SIDECAR_MIN_GAP_MAX_MS,
                number_of_steps=(SIDECAR_MIN_GAP_MAX_MS - SIDECAR_MIN_GAP_MIN_MS) // 10, height=14,
                progress_color=ACCENT, button_color=TEXT, button_hover_color=ACCENT_HOVER,
                fg_color=CARD3, command=self._on_sidecar_min_gap_slide,
            )
            self.sidecar_min_gap_slider.set(SIDECAR_MIN_GAP_DEFAULT_MS)
            self.sidecar_min_gap_slider.pack(fill="x", padx=14, pady=(0, 2))
            # Marcatore al valore REALE misurato (170ms, minimo assoluto sui
            # 465 workout ufficiali) - stessa convenzione visiva gia' usata
            # dallo slider densita' per il suo 50% "come il gioco vero".
            real_gap_relx = (SIDECAR_MIN_GAP_DEFAULT_MS - SIDECAR_MIN_GAP_MIN_MS) / (
                SIDECAR_MIN_GAP_MAX_MS - SIDECAR_MIN_GAP_MIN_MS)
            self.sidecar_min_gap_real_marker = ctk.CTkLabel(
                sidecar_left, text="▼", font=ui_font(11), text_color=HIGHLIGHT,
                fg_color="transparent", width=0, height=0,
            )
            self.sidecar_min_gap_real_marker.place(
                in_=self.sidecar_min_gap_slider, relx=real_gap_relx, rely=0.0, anchor="s", y=-1)
            _Tooltip(self.sidecar_min_gap_real_marker, lambda: self.t('sidecar_min_gap_real_marker_tooltip'))
            self.sidecar_min_gap_dropped_label = ctk.CTkLabel(
                sidecar_left, font=ui_font(10), text_color=SUBTEXT, anchor="w", justify="left")
            self.sidecar_min_gap_dropped_label.pack(fill="x", padx=14, pady=(2, 10))

            # Scorciatoie da tastiera per "Marca" (27/08, richiesta esplicita,
            # "per prova" - F e K): sulla finestra intera, non su un widget
            # specifico, cosi' funzionano mentre si ascolta senza dover
            # cliccare prima sul pulsante - _sidecar_mark() e' gia' un
            # no-op quando non si sta registrando, quindi il bind e' innocuo
            # anche fuori contesto. L'unico caso da escludere e' un campo di
            # testo con il focus (es. durata playlist): altrimenti scrivere
            # una "f" o una "k" in un campo qualunque marcherebbe per sbaglio.
            toplevel = self.winfo_toplevel()
            for key in ('f', 'F', 'k', 'K'):
                toplevel.bind(f'<KeyPress-{key}>', self._on_sidecar_hotkey, add="+")

            self._refresh_sidecar_labels()
            # Mostra lo strumento di default ("Automatica") ora che entrambi
            # i contenitori (automatic_tools_frame/sidecar_frame) e i loro
            # figli sono stati costruiti - vedi _apply_generate_tool_visibility.
            self._apply_generate_tool_visibility('automatic')

        opts_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        opts_frame.pack(fill="x", padx=pad, pady=(14, 0))
        self.dry_run_switch = ctk.CTkSwitch(
            opts_frame, text="", font=ui_font(11), text_color=TEXT, progress_color=SUCCESS,
            button_color=TEXT, fg_color=CARD3, command=self._on_dry_run_toggle,
        )
        self.dry_run_switch.pack(anchor="w")

        # Solo correzione: prima l'unico modo era scrivere in una cartella
        # "corretti" separata, che l'utente doveva poi spostare a mano dentro
        # TrackData - spaesante soprattutto quando la cartella di partenza era
        # gia' TrackData stessa (aperta con "Cartella BoxVR"). Con questo switch
        # acceso i file originali vengono sovrascritti sul posto, ma solo dopo
        # averne fatto un backup con timestamp accanto a loro (vedi
        # process_songs_with_presets in_place=True) - nessuno spostamento
        # manuale, e si puo' sempre tornare indietro dal backup.
        self.replace_originals_switch = None
        if self.mode == 'correct':
            replace_row = ctk.CTkFrame(opts_frame, fg_color="transparent")
            replace_row.pack(anchor="w", pady=(8, 0))
            # Testo DENTRO lo switch stesso (come dry_run_switch sopra), non
            # un'etichetta esterna separata: un'etichetta esterna, anche con
            # padding "uguale" a occhio, non e' mai garantita allinearsi
            # esattamente al padding interno che CTkSwitch usa per il proprio
            # testo - infatti non lo faceva (scarto visibile, segnalato
            # dall'utente). Riusando lo stesso meccanismo di dry_run_switch
            # l'allineamento e' garantito per costruzione, non per somiglianza.
            self.replace_originals_switch = ctk.CTkSwitch(
                replace_row, text="", font=ui_font(11), text_color=TEXT, progress_color=SUCCESS,
                button_color=TEXT, fg_color=CARD3,
            )
            self.replace_originals_switch.pack(side="left")
            self._info_icon(replace_row, 'replace_originals_info_tooltip', side="left", padx=(6, 0))
        self._on_dry_run_toggle()

        # Durata obiettivo della playlist (27/08, richiesta gia' annotata):
        # generate_songs() supporta gia' max_playlist_minutes da tempo (spezza
        # in piu' file numerati, "Nome 1"/"Nome 2"/...), mancava solo un
        # controllo vero in interfaccia - prima era raggiungibile solo
        # chiamando la funzione da script. Vuoto/0 = nessun limite, il
        # comportamento di sempre: non e' una regola imposta dal tool, solo
        # un'opzione per chi la vuole (es. allenamenti brevi di proposito).
        self.max_playlist_minutes_entry = None
        if self.mode == 'generate':
            playlist_dur_row = ctk.CTkFrame(opts_frame, fg_color="transparent")
            playlist_dur_row.pack(anchor="w", pady=(10, 0), fill="x")
            self.playlist_dur_label = ctk.CTkLabel(playlist_dur_row, font=ui_font(11), text_color=TEXT, anchor="w")
            self.playlist_dur_label.pack(side="left")
            self._info_icon(playlist_dur_row, 'playlist_duration_tooltip', side="left", padx=(6, 0))
            self.max_playlist_minutes_entry = ctk.CTkEntry(
                playlist_dur_row, width=70, height=28, font=ui_font(11),
                fg_color=CARD3, border_color=BORDER, text_color=TEXT,
                placeholder_text=self.t('playlist_duration_placeholder'),
            )
            self.max_playlist_minutes_entry.pack(side="left", padx=(10, 0))
            saved = self.app.settings.get('max_playlist_minutes')
            if saved:
                self.max_playlist_minutes_entry.insert(0, str(saved))
            self.max_playlist_minutes_entry.bind('<FocusOut>', self._on_playlist_duration_change)
            self.max_playlist_minutes_entry.bind('<Return>', self._on_playlist_duration_change)

        action_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        action_frame.pack(fill="x", padx=pad, pady=14)
        self.run_btn = ctk.CTkButton(
            action_frame, command=self._start_processing, state="disabled", corner_radius=22, height=46,
            fg_color=ACTION_ACCENT, hover_color=ACTION_ACCENT_HOVER, text_color="white", font=ui_font(13, "semibold"),
        )
        self.run_btn.pack(side="left")
        self.open_btn = ctk.CTkButton(
            action_frame, text="📁", command=self._open_output_folder, state="disabled",
            corner_radius=22, height=46, width=46,
            fg_color=CARD2, hover_color=CARD3, text_color=TEXT, font=ui_font(16),
        )
        self.open_btn.pack(side="left", padx=(10, 0))
        _Tooltip(self.open_btn, lambda: self.t('open_btn'))
        # Solo in generazione: la correzione riscrive file gia' presenti in TrackData
        # (l'utente li rimette a posto da se', come sempre), ma i brani generati da
        # zero sono file NUOVI che vanno smistati in 2 cartelle diverse - da qui la
        # richiesta di automatizzare la copia, con conferma esplicita prima di scrivere
        # nella libreria reale del gioco.
        self.install_btn = None
        if self.mode == 'generate':
            self.install_btn = ctk.CTkButton(
                action_frame, command=self._install_to_boxvr, state="disabled", corner_radius=22, height=46,
                fg_color=CARD2, hover_color=CARD3, text_color=TEXT, font=ui_font(12),
            )
            self.install_btn.pack(side="left", padx=(10, 0))

        # "determinate", non piu' "indeterminate": si riempie da 0 a 1 seguendo il
        # reale avanzamento [i/n] che process_songs_with_presets/generate_songs
        # scrivono in ogni riga di log, invece di una barra animata senza percentuale.
        # height/corner_radius espliciti (non i default CTk, sottili al punto
        # da sembrare una linea piatta invece di una vera barra a pillola
        # coerente col resto dell'interfaccia arrotondata).
        self.progress = ctk.CTkProgressBar(self.scroll, mode="determinate", progress_color=ACCENT,
                                            fg_color=CARD3, height=8, corner_radius=4)
        self.progress.pack(fill="x", padx=pad, pady=(0, 10))
        self.progress.set(0)

        # Log racchiuso in una sezione a scomparsa (parte chiusa): l'header e' un
        # CTkLabel cliccabile con una piccola freccia che fa da indicatore di stato.
        self.log_label = ctk.CTkLabel(self.scroll, font=ui_font(10), text_color=SUBTEXT, anchor="w", cursor="hand2")
        self.log_label.pack(fill="x", padx=pad)
        self.log_label.bind("<Button-1>", lambda e: self._toggle_log())

        self.log_box = ctk.CTkTextbox(
            self.scroll, fg_color=LOG_BG, text_color=LOG_TEXT, font=("Consolas", 9),
            corner_radius=14, wrap="word", height=110,
        )
        self.log_box.configure(state="disabled")
        if self._log_expanded:
            self.log_box.pack(fill="x", padx=pad, pady=(4, pad))

    # -- stato vuoto elenco --------------------------------------------------

    def _show_empty_placeholder(self):
        if self.empty_placeholder is not None:
            return
        # Prima era una singola CTkLabel con l'emoji cartella dentro il testo a
        # font size 12 - un "utilitario" scarno rispetto al tono delle
        # reference, dove uno stato vuoto e' sempre un momento visivo curato
        # (icona grande, testo primario/secondario distinti), non solo
        # un'informazione tecnica. Ora e' un piccolo blocco verticale: icona
        # grande anti-aliasata sopra, testo sotto - stesso contenuto, piu'
        # presenza. Ogni figlio deve registrarsi come drop-target a sua volta
        # (non solo il contenitore), altrimenti trascinare esattamente
        # sull'icona o sul testo non funzionerebbe.
        self.empty_placeholder = ctk.CTkFrame(self.song_list_frame, fg_color="transparent")
        self.empty_placeholder.grid(row=0, column=0, sticky="ew", pady=44)
        icon_lbl = ctk.CTkLabel(self.empty_placeholder, text="", image=_render_emoji_icon("📁", 40))
        icon_lbl.pack(pady=(0, 12))
        self.empty_placeholder_text = ctk.CTkLabel(
            self.empty_placeholder, font=ui_font(13), text_color=SUBTEXT, justify="center",
        )
        self.empty_placeholder_text.configure(text=self.t('drop_hint'))
        self.empty_placeholder_text.pack()
        for w in (self.empty_placeholder, icon_lbl, self.empty_placeholder_text):
            w.bind("<MouseWheel>", self.inner_scroll_handler)
            if HAS_DND:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)

    def _hide_empty_placeholder(self):
        if self.empty_placeholder is not None:
            self.empty_placeholder.destroy()
            self.empty_placeholder = None

    # -- log a scomparsa ------------------------------------------------------

    def _toggle_log(self):
        self._log_expanded = not self._log_expanded
        if self._log_expanded:
            self.log_box.pack(fill="x", padx=self._pad, pady=(4, self._pad))
        else:
            self.log_box.pack_forget()
        self._update_log_label()

    def _update_log_label(self):
        key = 'log_label_expanded' if self._log_expanded else 'log_label_collapsed'
        self.log_label.configure(text=self.t(key))

    # -- "applica a tutti" -----------------------------------------------------

    def _apply_preset_to_all(self):
        if self.current_song is None or not self.songs:
            return
        ratio = self.current_song['punch_ratio']
        # Copia anche la densita' quando presente (solo modalita' generazione,
        # dove ora e' per-brano come il rapporto pugni/misto invece che un'unica
        # impostazione per l'intera sessione) - stesso bottone, un solo click per
        # allineare entrambe le preferenze del brano corrente a tutto l'elenco.
        density = self.current_song.get('density')
        for s in self.songs:
            s['punch_ratio'] = ratio
            if density is not None and 'density' in s:
                s['density'] = density
            row = self.song_rows.get(s['key'])
            if row is not None:
                row.set_preset_text(self._punch_ratio_text(ratio), ratio)
                row.flash_preset_chip(ratio)
        if density is not None:
            self._refresh_density_slider()

    def _punch_ratio_text(self, ratio):
        return self.t('punch_ratio_chip', pct=int(round(ratio * 100)))

    def _info_icon(self, parent, tooltip_key, **pack_kwargs):
        """Icona "i" con tooltip al passaggio del mouse - punto UNICO da cui
        crearne una, cosi' ogni icona informativa dell'app ha sempre lo stesso
        aspetto e SEMPRE lo stesso comportamento (hover -> tooltip, mai un click
        che apre altro, mai un'icona senza spiegazione): usarla ogni volta che
        serve chiarire un controllo senza occupare spazio con testo fisso."""
        icon = ctk.CTkLabel(parent, text="ⓘ", font=ui_font(11), text_color=SUBTEXT, cursor="question_arrow")
        icon.pack(**pack_kwargs)
        _Tooltip(icon, lambda: self.t(tooltip_key))
        return icon

    def _add_soft_shadow(self, card, shadow_parent):
        """Ombra morbida VERA (sfumata con un filtro gaussiano reale), non piu'
        un trucco a rettangoli piatti offset. Tre round di tentativi con
        CTkFrame a tinta unita (vedi cronologia sotto, tenuta perche' i
        principi di posizionamento restano validi) non sono mai riusciti a
        produrre una vera dissolvenza - un CTkFrame e' sempre un rettangolo a
        colore uniforme, quindi ovunque due colori si toccano resta un bordo
        netto, quale che sia il numero di livelli o quanto siano ravvicinati:
        1 livello si leggeva come una maniglia di ridimensionamento, 3 livelli
        ravvicinati si leggevano come "l'ombra triplicata" (segnalato
        dall'utente, con tanto di screenshot a confronto con una vera ombra
        sfumata) - piu' passi con quella tecnica peggiora il problema, non lo
        attenua. La soluzione era gia' nel progetto: la stessa tecnica
        supersampling+filtro-di-qualita' usata per icone/pallini
        (_render_emoji_icon/_render_dot_image), qui con un GaussianBlur PIL
        vero invece di un semplice resize - _render_card_shadow_image
        disegna la sagoma della card su un canvas trasparente con margine
        abbondante (altrimenti la sfocatura verrebbe troncata di netto sul
        bordo dell'immagine, lo stesso problema di prima spostato di un
        livello) e la sfoca per davvero, producendo un'immagine RGBA con una
        vera dissolvenza che nessun CTkFrame puo' replicare.

        shadow_parent va comunque scelto con cura (questa parte della lezione
        resta valida): deve essere il vero genitore DIRETTO della card
        (`left_col` per song_list_frame, `self.scroll` per preview_frame),
        MAI card.master - sia song_list_frame che preview_frame sono
        CTkScrollableFrame (o vivono dentro una), il cui .master e' il Canvas
        interno di scroll, che CLIPPA qualunque figlio ecceda i propri
        confini; un'ombra (ora un'immagine, prima un frame) posizionata li'
        dentro verrebbe troncata invece di dissolversi visibilmente oltre il
        bordo della card.

        L'immagine va rigenerata quando la card cambia dimensione (si lega a
        <Configure> sulla card - la larghezza di preview_frame segue la
        finestra) e quando cambia il tema (colore diverso - vedi
        refresh_theme/_recolor_shadow_layers, ora un elenco di funzioni di
        ridisegno da richiamare, non piu' di frame+blend da riconfigurare)."""
        radius = card.cget('corner_radius')
        # tk.Label crudo + ImageTk.PhotoImage, NON ctk.CTkLabel/CTkImage: la
        # combinazione CTkImage(size=...) + place() e' risultata inaffidabile
        # su questa macchina in DUE modi opposti, entrambi verificati con
        # screenshot reali. Primo giro: place(width=img.width, height=...) in
        # pixel RAW (l'unita' nativa di Tk) mentre CTkImage scala
        # internamente per il proprio fattore di DPI (ScalingTracker) -
        # l'immagine risultava fisicamente PIU' GRANDE del rettangolo
        # place()-ato, che la tagliava via quasi per intero (bordo netto,
        # nessuna sfumatura visibile). Secondo giro (rimossi width/height da
        # place, per lasciare che il widget si auto-dimensionasse sulla
        # richiesta "gia' DPI-consapevole"): il risultato e' stato l'ESATTO
        # opposto, un rettangolo grigio molto PIU' GRANDE della card, esteso
        # per un centinaio di px oltre il bordo reale (verificato con zoom
        # sullo screenshot, altezza incongruente col vero card.winfo_height()
        # loggato). In nessuno dei due giri le unita' di misura di
        # CTkImage(size=...) e quelle di place()/winfo_*() sono risultate
        # coerenti fra loro in modo prevedibile. tk.Label+ImageTk.PhotoImage
        # e' Tk puro, senza alcun layer di scaling CTk in mezzo: l'immagine
        # PIL e' gia' esattamente wide x tall pixel fisici, il PhotoImage e'
        # esattamente quella risoluzione, e place(width=, height=) nello
        # stesso identico sistema di unita' di winfo_width()/height() - stessa
        # tecnica gia' comprovata per song_list_frame/sparkline altrove in
        # questo file (tk.Canvas grezzo, non widget CTk, per lo stesso motivo).
        label = tk.Label(shadow_parent, bd=0, highlightthickness=0)
        label.lower()  # vedi sopra: in fondo allo stack IN ASSOLUTO, non solo sotto card
        last_size = {'wh': None}

        def redraw(event=None):
            w, h = card.winfo_width(), card.winfo_height()
            if w <= 1 or h <= 1 or (w, h) == last_size['wh']:
                return
            last_size['wh'] = (w, h)
            color = resolve_color(SHADOW_TONE)
            bg = resolve_color(BG)
            img, pad = _render_card_shadow_image(w, h, radius, color_hex=color)
            photo = ImageTk.PhotoImage(img)
            label.configure(image=photo, bg=bg)
            label._shadow_photo_ref = photo  # tiene viva la PhotoImage, altrimenti il garbage
            # collector la ricicla e il label smette di mostrare nulla appena
            # esce lo scope di questa funzione (nessun'altra variabile Python
            # la referenzia).
            label.place(in_=card, x=-pad, y=-pad + SHADOW_OFFSET_Y, width=img.width, height=img.height)

        # add="+" e non un bind semplice: song_list_frame e' una CTkScrollableFrame,
        # che si lega GIA' da sola al proprio <Configure> per gestire canvas/scrollbar
        # interni - il bind() di tkinter di default SOSTITUISCE qualunque binding
        # precedente sulla stessa sequenza sullo stesso widget, quindi senza add="+"
        # questo redraw veniva silenziosamente scavalcato per song_list_frame (mai
        # richiamato dopo la prima chiamata sincrona a larghezza 1, percio' nessuna
        # ombra visibile li' - a differenza di preview_frame, una CTkFrame normale
        # senza un proprio Configure interno, dove infatti il redraw funzionava).
        card.bind("<Configure>", redraw, add="+")
        redraw()
        self._shadow_layers.append(redraw)

    def _recolor_shadow_layers(self):
        for redraw in self._shadow_layers:
            redraw()

    # -- lingua -----------------------------------------------------------

    def apply_language(self):
        subtitle_key = 'subtitle_correct' if self.mode == 'correct' else 'subtitle_generate'
        run_key = 'run_btn_correct' if self.mode == 'correct' else 'run_btn_generate'
        self.sub_label.configure(text=self.t(subtitle_key))
        if self.empty_placeholder is not None:
            self.empty_placeholder_text.configure(text=self.t('drop_hint'))
        self.browse_btn.configure(text=self.t('browse_btn'))
        self.open_boxvr_btn.configure(text=self.t('open_boxvr_btn'))
        # clear_btn/apply_all_btn/open_btn restano icona-soltanto (vedi _build_ui) -
        # il testo tradotto vive solo nel tooltip al passaggio del mouse (_Tooltip,
        # che chiama self.t(...) al momento dell'hover, quindi segue la lingua
        # corrente da solo senza bisogno di essere riconfigurato qui).
        if self.info_btn is not None:
            self.info_btn.configure(text=self.t('info_btn'))
        if self.install_btn is not None:
            self.install_btn.configure(text=self.t('install_btn'))
        if self.margin_label is not None:
            self.margin_label.configure(text=self.t('margin_label'))
        if self.density_label is not None:
            self.density_label.configure(text=self.t('density_label'))
        if getattr(self, 'choreo_preset_label', None) is not None:
            self.choreo_preset_label.configure(text=self.t('choreo_preset_label'))
        if getattr(self, 'choreo_preset_menu', None) is not None:
            # I valori del segmented button sono etichette tradotte: al cambio
            # lingua vanno ricostruite. La selezione va ripresa dalla CHIAVE
            # logica tenuta in self._choreo_preset_key, non rileggendo
            # l'etichetta dal widget: quando arriviamo qui self.t() risponde
            # gia' nella lingua NUOVA, quindi l'etichetta vecchia non sarebbe
            # piu' riconosciuta e la scelta dell'utente verrebbe silenziosamente
            # riportata a "Medio" (bug reale, visto in test).
            self.choreo_preset_menu.configure(
                values=[self.t('choreo_light'), self.t('choreo_medium'), self.t('choreo_high')])
            self.choreo_preset_menu.set(self._choreo_preset_label(self._choreo_preset_key))
        # la riga dei colpi/min e' testo tradotto con segnaposti: va rigenerata
        # come le altre etichette, non basta il tooltip (che si traduce da solo).
        self._refresh_choreo_epm()
        self._refresh_sidecar_labels()
        if self.orig_timeline_label is not None:
            self.orig_timeline_label.configure(text=self.t('timeline_original_label'))
        if self.corrected_timeline_label is not None:
            self.corrected_timeline_label.configure(text=self.t('timeline_corrected_label'))
        self.dry_run_switch.configure(text=self.t('dry_run'))
        if self.replace_originals_switch is not None:
            self.replace_originals_switch.configure(text=self.t('replace_originals_label'))
        if self.max_playlist_minutes_entry is not None:
            self.playlist_dur_label.configure(text=self.t('playlist_duration_label'))
            self.max_playlist_minutes_entry.configure(placeholder_text=self.t('playlist_duration_placeholder'))
        if self.bpm_panel is not None:
            self.beat_engine_switch.configure(text=self.t('beat_engine_label'))
        self.run_btn.configure(text=self.t(run_key))
        self.timeline_mode_buttons['curve'].configure(text=self.t('timeline_mode_curve'))
        # In "Genera" la seconda modalita' mostra i MARKER dell'utente (30/08,
        # richiesto: la vecchia vista "Colpi" era una sequenza illeggibile) -
        # in "Correggi" non esiste il concetto di marker (nessuna sidecar li'),
        # quindi resta la vista a tacche per beat di sempre.
        self.timeline_mode_buttons['beats'].configure(
            text=self.t('timeline_mode_markers' if self.mode == 'generate' else 'timeline_mode_beats'))
        self._refresh_timeline_mode_buttons()
        self.list_header_preset.configure(text=self.t('col_preset'))
        self._update_sort_header_indicators()
        self._update_log_label()
        self.click_track_label.configure(text=self.t('click_track_label'))
        if self.bpm_panel is not None:
            self._update_bpm_panel()

        self.punch_label.configure(text=self.t('punch_ratio_label'))
        for lvl, lbl in self.legend_labels.items():
            lbl.configure(text=self.t(f'legend_{lvl}'))
        for s in self.songs:
            row = self.song_rows.get(s['key'])
            if row is not None:
                row.set_preset_text(self._punch_ratio_text(s['punch_ratio']), s['punch_ratio'])

        self._refresh_dynamic_labels()
        self._render_timeline()

    def _refresh_dynamic_labels(self):
        if self.songs:
            # Progresso d'insieme dell'analisi in background - prima l'unico
            # segnale per una lista lunga era il pallino di stato per riga
            # (bisognava scorrere per farsi un'idea), qui invece si legge subito
            # "quanti mancano" senza dover premere "Avvia correzione". Sparisce
            # da solo (torna al testo semplice) appena tutti sono pronti/in
            # errore - Nielsen Norman Group: loading ed empty-state lavorano in
            # sequenza, il segnale di caricamento non deve restare li' per sempre
            # una volta risolto.
            done = sum(1 for s in self.songs if s.get('analysis') is not None or s.get('_status') == 'error')
            total = len(self.songs)
            if done < total:
                self.selected_label.configure(text=self.t('folder_selected_progress', n=total, done=done))
            else:
                self.selected_label.configure(text=self.t('folder_selected', n=total))
        else:
            self.selected_label.configure(text=self.t('no_folder'))

        if self.current_song:
            self.song_title_label.configure(text=f"{self.current_song['name']} — {self.current_song['artist']}")
        else:
            self.song_title_label.configure(text=self.t('select_song_prompt'))
        if self.track_id_label is not None:
            track_id = self.current_song['key'] if self.current_song else ''
            self.track_id_label.configure(text=self.t('track_id_label', track_id=track_id) if track_id else "")

        if not HAS_AUDIO:
            self.play_btn.configure(text=self.t('audio_unavailable'))
        elif self.player is not None and self._player_song is self.current_song and self.player.stream.active:
            self.play_btn.configure(text=self.t('pause'))
        else:
            self.play_btn.configure(text=self.t('play'))
        if getattr(self, 'visual_btn', None) is not None:
            self.visual_btn.configure(text=self.t('visual_btn'))

    # -- selezione / aggiunta cartelle e file --------------------------------

    def _on_drag_enter(self, event):
        self.song_list_frame.configure(fg_color=CARD2)

    def _on_drag_leave(self, event):
        self.song_list_frame.configure(fg_color=CARD)

    def _on_drop(self, event):
        self._on_drag_leave(event)
        paths = paths_from_drop_data(self, event.data)
        self._add_paths(paths)

    def _browse_folder(self):
        key = 'browse_dialog_title_correct' if self.mode == 'correct' else 'browse_dialog_title_generate'
        settings_key = f'last_browse_dir_{self.mode}'
        initialdir = self.app.settings.get(settings_key) or None
        folder = filedialog.askdirectory(title=self.t(key), initialdir=initialdir)
        if folder:
            self.app.settings[settings_key] = folder
            save_settings(self.app.settings)
            self._add_paths([folder])

    def _clear_songs(self):
        if not self.songs:
            return
        if not messagebox.askyesno(self.t('app_title'), self.t('confirm_clear_songs')):
            return
        if self.player is not None:
            self.player.close()
            self.player = None
            self._player_song = None
        for row in self.song_rows.values():
            row.destroy()
        self.song_rows = {}
        self.songs = []
        self.song_keys = set()
        self.current_song = None
        self.base_folder = None
        self._stop_spinner()
        self._render_timeline()
        self._refresh_dynamic_labels()
        self._show_empty_placeholder()
        self.run_btn.configure(state="disabled")

    # -- aggiunta brani (cartelle e/o singoli file, sempre in append) -------

    def _add_paths(self, paths):
        """Aggiunge cartelle e/o singoli file all'elenco (sempre in append, mai
        sostituendo quanto gia' presente; i duplicati - stesso 'key' - vengono
        ignorati silenziosamente). Mostra un avviso solo se non c'era davvero
        nulla di valido da aggiungere (distinto dal caso "era tutto gia' in
        elenco", che non e' un errore)."""
        added_before = len(self.songs)
        was_empty = self.current_song is None and not self.songs
        found_valid = False
        saw_wrong_type = False
        for p in paths:
            if os.path.isdir(p):
                if not self.base_folder:
                    self.base_folder = p
                valid, wrong = self._add_folder(p)
            elif os.path.isfile(p):
                if not self.base_folder:
                    self.base_folder = os.path.dirname(p)
                valid, wrong = self._add_file(p)
            else:
                valid, wrong = False, False
            found_valid |= valid
            saw_wrong_type |= wrong

        n_added = len(self.songs) - added_before
        if n_added > 0:
            self._hide_empty_placeholder()
            self._log(self.t('log_added_n', n=n_added, total=len(self.songs)))
            self.run_btn.configure(state="normal")
            self._refresh_dynamic_labels()
            if self._sort_key is not None:
                self._apply_sort()
            if was_empty:
                # Primo popolamento dell'elenco: seleziona subito il primo brano e
                # avvia l'analisi, cosi' l'utente non deve fare un click in piu'.
                self.select_song(self.songs[0])
        elif found_valid:
            pass  # tutto quello trovato era gia' in elenco: non e' un errore, nessun avviso
        elif saw_wrong_type and self.mode == 'correct':
            messagebox.showwarning(self.t('app_title'), self.t('warn_wrong_tab_mp3'))
        else:
            warn_key = 'warn_no_pairs' if self.mode == 'correct' else 'warn_no_audio_files'
            messagebox.showwarning(self.t('app_title'), self.t(warn_key))

    def _add_folder(self, folder):
        """Ritorna (trovato_qualcosa_di_valido, trovato_tipo_sbagliato_per_questa_scheda)."""
        found_valid = False
        saw_wrong_type = False
        if self.mode == 'correct':
            txts = sorted(glob.glob(os.path.join(folder, '*.txt')))
            for txt_path in txts:
                found_valid |= self._add_correct_item(txt_path)
            if not txts and glob.glob(os.path.join(folder, '*.mp3')):
                saw_wrong_type = True
        else:
            for path in find_audio_files(folder):
                found_valid |= self._add_generate_item(path)
        return found_valid, saw_wrong_type

    def _add_file(self, path):
        """Ritorna (trovato_qualcosa_di_valido, trovato_tipo_sbagliato_per_questa_scheda)."""
        ext = os.path.splitext(path)[1].lower()
        if self.mode == 'correct':
            if ext == '.txt':
                return self._add_correct_item(path), False
            if ext == '.mp3':
                return False, True
            return False, False
        else:
            if ext in AUDIO_EXTENSIONS:
                return self._add_generate_item(path), False
            return False, False

    def _add_correct_item(self, txt_path):
        """Ritorna True se txt_path e' una coppia valida (gia' in elenco o appena
        aggiunta) - False solo se manca il wav corrispondente. La decisione
        (validita' + identita' per la lista) vive in read_correct_item -
        vedi il suo docstring in boxvr_fixer.py."""
        tid = find_track_id(os.path.basename(txt_path))
        if tid in self.song_keys:
            return True
        item = read_correct_item(txt_path)
        if item is None:
            return False
        self._add_song({k: v for k, v in item.items() if k != 'bpm_text'}, item['bpm_text'])
        return True

    def _add_generate_item(self, audio_path):
        """Ritorna True se audio_path e' un file valido (gia' in elenco o appena
        aggiunto) per questa scheda. Vedi read_generate_item in
        boxvr_generator.py per come si ricava il nome/artista mostrato."""
        if audio_path in self.song_keys:
            return True
        self._add_song(read_generate_item(audio_path), "?")
        return True

    def _add_song(self, base, bpm_text):
        song = dict(base)
        song.update({
            'punch_ratio': 0.5, 'density': self.app.settings.get('density', 1.0),
            'analysis': None, 'play_audio': None, 'play_sr': None,
            '_last_level_map': {}, '_status': 'queued', '_bpm_text': bpm_text,
            'forced_bpm': None, 'tempo_corrected': False, '_click_overlay': None,
            'beat_engine': 'librosa',
            # intensita' della coreografia scritta (vedi
            # boxvr_choreo.INTENSITY_PRESETS): None = default del modulo
            # ('medium'). Per-brano, cosi' in una stessa playlist si possono
            # avere brani piu' o meno intensi.
            'choreo_preset': self.app.settings.get('choreo_preset'),
            # 'auto': il motore viene scelto da soli in base alla stabilita' del
            # beat-grid di librosa (vedi _background_analysis_loop/
            # recommend_engine_from_beats) - passa a 'manual' non appena
            # l'utente tocca lo switch a mano (_on_beat_engine_toggle), da quel
            # momento la scelta automatica non lo tocca piu'.
            'engine_mode': 'auto', 'suspicious': False, 'stability_std': None,
            # Sidecar (26/08 notte, prima integrazione nel tool vero - vedi
            # sidecar sandbox/engine.py): istanti in secondi marcati a mano
            # dall'utente per QUESTO brano, per-brano come punch_ratio/preset.
            # Nessun interruttore separato (tolto il 27/08 su richiesta
            # esplicita, causa reale di confusione: marker registrati ma
            # l'interruttore dimenticato spento): se la lista non e' vuota,
            # i marker vengono usati - punto. Per non usarli si cancellano.
            'sidecar_markers': [],
            # Modalita' e "solo hit marker" (27/08, richiesti esplicitamente) -
            # per-brano come i marker stessi. 'harmonize' = comportamento di
            # sempre (automatico intero + marker sopra) - vedi
            # sidecar sandbox/engine.py, MODE_*.
            'sidecar_mode': 'harmonize', 'sidecar_exclude_obstacles': False,
            # Soglia minima fra due marker consecutivi (30/08, "possiamo
            # avere uno slider per la soglia?") - None = usa il default del
            # motore (engine.MIN_INPUT_GAP_S, 170ms, il minimo misurato sui
            # 465 workout ufficiali), non un valore duplicato qui che
            # rischierebbe di disallinearsi da quello vero.
            'sidecar_min_gap_ms': None,
            # Quale strumento sta usando l'utente per QUESTO brano (30/08,
            # riorganizzazione UI): 'automatic' (rapporto pugni/densita'/
            # intensita', lo strumento classico) o 'sidecar' - per-brano
            # come tutto il resto di questa sezione.
            'generate_tool': 'automatic',
        })
        self.songs.append(song)
        self._insert_row(song, len(self.songs) - 1)
        # In coda per l'analisi in background subito, non solo quando l'utente lo
        # mette in focus - cosi' il BPM compare in lista da solo.
        self._analysis_pending.put(song)

    def _insert_row(self, song, index):
        """Crea/piazza la SongRow per un brano gia' presente in self.songs - condiviso
        tra _add_song e l'annulla-rimozione (_undo_remove), che deve ricreare la riga
        con lo stato/bpm che aveva PRIMA della rimozione, non da zero."""
        self.song_keys.add(song['key'])
        row = SongRow(self.song_list_frame, self, song)
        row.grid(row=index, column=0, sticky="ew", padx=6, pady=3)
        row.set_bpm(song.get('_bpm_text', '?'))
        row.set_bpm_uncertain(song.get('tempo_corrected', False))
        row.set_suspicious(song.get('suspicious', False))
        row.set_status(song.get('_status', 'queued'))
        row.set_preset_text(self._punch_ratio_text(song['punch_ratio']), song['punch_ratio'])
        if song.get('analysis') is not None:
            row.draw_sparkline(song['analysis']['bar_score'])
        self.song_rows[song['key']] = row
        return row

    def _remove_song(self, song):
        key = song['key']
        original_index = self.songs.index(song) if song in self.songs else len(self.songs)
        if self.player is not None and self._player_song is song:
            self.player.close()
            self.player = None
            self._player_song = None
        row = self.song_rows.pop(key, None)
        if row is not None:
            row.destroy()
        if song in self.songs:
            self.songs.remove(song)
        self.song_keys.discard(key)
        was_current = self.current_song is song
        if was_current:
            self.current_song = None
            self.canvas.delete("all")
            self.play_btn.configure(state="disabled")
            if self.visual_btn is not None:
                self.visual_btn.configure(state="disabled")
            self.phase_label.configure(text="")
        self._regrid_song_rows()
        self._refresh_dynamic_labels()
        if not self.songs:
            self._show_empty_placeholder()
            self.run_btn.configure(state="disabled")
        elif was_current:
            self.select_song(self.songs[0])
        self._offer_undo(song, original_index)

    # -- annulla rimozione (undo a un solo livello) --------------------------

    def _offer_undo(self, song, index):
        self.last_removed = (song, index)
        if self._undo_after_id is not None:
            self.after_cancel(self._undo_after_id)
        self.undo_btn.configure(text=self.t('undo_remove_btn', name=_truncate(song['name'], 22)))
        self.undo_btn.pack(side="left", padx=(8, 0))
        self._undo_after_id = self.after(8000, self._hide_undo)

    def _hide_undo(self):
        self._undo_after_id = None
        self.last_removed = None
        self.undo_btn.pack_forget()

    def _undo_remove(self):
        if self.last_removed is None:
            return
        song, index = self.last_removed
        self._hide_undo()
        if song['key'] in self.song_keys:
            return  # gia' rimesso in elenco nel frattempo (non dovrebbe capitare)
        self._hide_empty_placeholder()
        index = max(0, min(index, len(self.songs)))
        self.songs.insert(index, song)
        self._insert_row(song, index)
        self._regrid_song_rows()
        self.run_btn.configure(state="normal")
        self._refresh_dynamic_labels()
        if self._sort_key is not None:
            self._apply_sort()

    def _regrid_song_rows(self):
        for i, s in enumerate(self.songs):
            row = self.song_rows.get(s['key'])
            if row is not None:
                row.grid(row=i, column=0, sticky="ew", padx=6, pady=3)

    # -- ordinamento colonne -------------------------------------------------

    def _on_sort_click(self, key):
        if self._sort_key == key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key = key
            self._sort_reverse = False
        self._apply_sort()

    def _apply_sort(self):
        if self._sort_key is None or not self.songs:
            return
        key = self._sort_key

        def sort_value(s):
            if key == 'bpm':
                # _bpm_text e' gia' la stessa stringa mostrata nella riga
                # (tenuta sincronizzata da _add_song/_insert_row e
                # dall'analisi in background) - leggerla da li' invece che
                # dal widget evita un giro inutile per un valore gia'
                # disponibile nel dict puro.
                try:
                    return float(s.get('_bpm_text', '?'))
                except (ValueError, TypeError):
                    return -1.0  # '?' (non ancora analizzato) sempre in fondo
            return (s.get(key) or '').casefold()

        self.songs.sort(key=sort_value, reverse=self._sort_reverse)
        self._regrid_song_rows()
        self._update_sort_header_indicators()

    def _update_sort_header_indicators(self):
        columns = (('name', self.list_header_title, 'col_title'),
                   ('artist', self.list_header_artist, 'col_artist'),
                   ('bpm', self.list_header_bpm, 'col_bpm'))
        for key, lbl, text_key in columns:
            suffix = ""
            if key == self._sort_key:
                suffix = "  ▾" if self._sort_reverse else "  ▲"
            lbl.configure(text=self.t(text_key) + suffix)

    # -- riordino per trascinamento -------------------------------------------

    def _begin_drag(self, song):
        self._drag_active = True
        self._drag_song = song

    def _drag_motion(self, y_root):
        if not self._drag_active or self._drag_song is None:
            return
        target_index = None
        for i, s in enumerate(self.songs):
            row = self.song_rows.get(s['key'])
            if row is None:
                continue
            top = row.winfo_rooty()
            if top <= y_root <= top + row.winfo_height():
                target_index = i
                break
        if target_index is None:
            return
        current_index = self.songs.index(self._drag_song)
        if target_index != current_index:
            self.songs.insert(target_index, self.songs.pop(current_index))
            self._regrid_song_rows()

    def _end_drag(self):
        self._drag_active = False
        self._drag_song = None
        if self._sort_key is not None:
            # Un riordino manuale sostituisce/disattiva l'ordinamento automatico
            # per colonna, altrimenti la prossima aggiunta lo rimescolerebbe subito.
            self._sort_key = None
            self._update_sort_header_indicators()

    def select_song(self, song):
        if self.player is not None:
            self.player.close()
            self.player = None
            self._player_song = None
        self._sidecar_recording = False

        if self.current_song is not None:
            prev_row = self.song_rows.get(self.current_song['key'])
            if prev_row is not None:
                prev_row.set_selected(False)

        self.current_song = song
        row = self.song_rows.get(song['key'])
        if row is not None:
            row.set_selected(True)
        # Zoom/vista sono per-visualizzazione, non per-brano: cambiando canzone
        # si riparte sempre dalla vista d'insieme, altrimenti si rischia di
        # "perdere" un brano appena selezionato dentro lo zoom del precedente.
        self.zoom = 1.0
        self.view_start = 0.0
        self.zoom_slider.set(1.0)
        self.zoom_value_label.configure(text="1.0x")
        self._refresh_punch_ratio_slider()
        self._refresh_density_slider()
        self._refresh_choreo_preset()
        self._refresh_sidecar_panel()
        if self.bpm_panel is not None:
            if song.get('beat_engine') == 'madmom':
                self.beat_engine_switch.select()
            else:
                self.beat_engine_switch.deselect()
        self._refresh_dynamic_labels()
        self.time_label.configure(text="00:00 / 00:00")
        # La base a click e' per-ascolto, non una preferenza del brano: si riparte
        # sempre spenta cambiando canzone, altrimenti resterebbe accesa "per
        # sbaglio" su un brano diverso da quello controllato.
        self.click_track_switch.deselect()

        if song['analysis'] is None:
            # Non serve piu' avviare qui un thread dedicato: ogni brano finisce nella
            # coda di analisi in background gia' al momento in cui viene aggiunto
            # (vedi _add_song/_background_analysis_loop), quindi e' gia' in coda o
            # in elaborazione - qui si mostra solo lo spinner finche' non arriva.
            self.play_btn.configure(state="disabled")
            if self.visual_btn is not None:
                self.visual_btn.configure(state="disabled")
            self.canvas.delete("all")
            self._start_spinner()
            self._update_bpm_panel()
        else:
            self.phase_label.configure(text="")
            self.play_btn.configure(state="normal" if HAS_AUDIO else "disabled")
            if self.visual_btn is not None:
                self.visual_btn.configure(state="normal")
            self._render_timeline()
            self._update_bpm_panel()

    def _background_analysis_loop(self):
        """Unico worker persistente, seriale: consuma _analysis_pending in ordine
        FIFO per l'intera vita del pannello, cosi' ogni brano aggiunto viene
        analizzato prima o poi anche se l'utente non lo mette mai in focus."""
        while True:
            song = self._analysis_pending.get()
            if song.get('analysis') is not None:
                continue
            self.analysis_queue.put(('status', song, 'analyzing'))
            try:
                if self.mode == 'correct':
                    analysis = compute_song_analysis(song['txt_path'], song['wav_path'])
                    play_audio, play_sr = (None, None)
                    if HAS_AUDIO:
                        play_audio, play_sr = load_wav_for_playback(song['wav_path'])
                else:
                    # la decisione (quale motore, se ripiegare su librosa se
                    # madmom fallisce) vive in analyze_for_generate - vedi il
                    # suo docstring in boxvr_generator.py: qui restano solo lo
                    # scrivere il risultato su `song` e il log del ripiego
                    outcome = analyze_for_generate(
                        song['audio_path'], forced_bpm=song.get('forced_bpm'),
                        engine_mode=song.get('engine_mode', 'auto'), beat_engine=song.get('beat_engine', 'librosa'),
                        on_fallback=lambda msg: self._log(self.t('madmom_fallback_log', name=song['name'], msg=msg)),
                    )
                    analysis = outcome['analysis']
                    song['beat_engine'] = outcome['engine_used']
                    song['stability_std'] = outcome['stability_std']
                    song['suspicious'] = outcome['suspicious']
                    play_audio, play_sr = (analysis['native_audio'], analysis['sr']) if HAS_AUDIO else (None, None)
                self.analysis_queue.put(('done', song, analysis, play_audio, play_sr))
            except Exception as e:
                self.analysis_queue.put(('error', song, str(e)))

    def _poll_analysis_queue(self):
        try:
            while True:
                item = self.analysis_queue.get_nowait()
                kind = item[0]
                song = item[1]
                row = self.song_rows.get(song['key'])
                if kind == 'status':
                    song['_status'] = item[2]
                    if row is not None:
                        row.set_status(item[2])
                elif kind == 'done':
                    _, _, analysis, play_audio, play_sr = item
                    song['analysis'] = analysis
                    song['play_audio'] = play_audio
                    song['play_sr'] = play_sr
                    song['_status'] = 'ready'
                    if song.pop('_bpm_pending_requeue', False):
                        # il BPM e' stato scritto MENTRE questo risultato era
                        # gia' in elaborazione (30/08, "magari conosco gia' i
                        # bpm e non ha senso aspettare l'analisi") - riflette
                        # ancora il valore vecchio, si rimanda subito in coda
                        # con quello giusto invece di mostrare un risultato
                        # gia' superato all'utente.
                        self._apply_forced_bpm(song['forced_bpm'])
                        continue
                    if row is not None:
                        row.set_status('ready')
                        row.draw_sparkline(analysis['bar_score'])
                    if self.mode == 'generate':
                        song['name'], song['artist'] = analysis['name'], analysis['artist']
                        song['_bpm_text'] = f"{analysis['bpm']:.0f}"
                        song['tempo_corrected'] = analysis.get('tempo_corrected', False)
                        if row is not None:
                            row.set_bpm(song['_bpm_text'])
                            row.set_bpm_uncertain(song['tempo_corrected'])
                            row.set_suspicious(song.get('suspicious', False))
                            row.set_name_artist(song['name'], song['artist'])
                    self._refresh_dynamic_labels()
                    if self.current_song is song:
                        self._stop_spinner()
                        self.phase_label.configure(text="")
                        self.play_btn.configure(state="normal" if HAS_AUDIO else "disabled")
                        if self.visual_btn is not None:
                            self.visual_btn.configure(state="normal")
                        self._refresh_sidecar_panel()
                        self._render_timeline()
                        self._update_bpm_panel()
                    if self._sort_key == 'bpm':
                        # Il BPM di questo brano e' appena arrivato in modo asincrono:
                        # se l'ordinamento attivo e' proprio per BPM va ricalcolato,
                        # altrimenti il brano resterebbe fermo nella posizione "?"
                        # anche dopo che il valore vero e' disponibile.
                        self._apply_sort()
                elif kind == 'error':
                    msg = item[2]
                    song['_status'] = 'error'
                    if row is not None:
                        row.set_status('error')
                    self._refresh_dynamic_labels()
                    if self.current_song is song:
                        self._stop_spinner()
                        self.phase_label.configure(text=self.t('analysis_error', msg=msg))
                    self._log(self.t('log_analysis_error', name=song['name'], msg=msg))
        except queue.Empty:
            pass
        self.after(80, self._poll_analysis_queue)

    # -- spinner "analisi in corso" ------------------------------------------

    def _start_spinner(self):
        self._spinner_active = True
        self._spinner_frame = 0
        self._tick_spinner()

    def _tick_spinner(self):
        if not self._spinner_active:
            return
        ch = SPINNER_FRAMES[self._spinner_frame % len(SPINNER_FRAMES)]
        self._spinner_frame += 1
        self.phase_label.configure(text=f"{ch} {self.t('analyzing')}")
        self._spinner_after_id = self.after(100, self._tick_spinner)

    def _stop_spinner(self):
        self._spinner_active = False
        if self._spinner_after_id:
            self.after_cancel(self._spinner_after_id)
            self._spinner_after_id = None

    # -- preset e timeline ------------------------------------------------------

    def _on_punch_ratio_slide(self, value):
        song = self.current_song
        if song is None:
            return
        ratio = float(value)
        song['punch_ratio'] = ratio
        self.punch_value_label.configure(text=f"{int(round(ratio * 100))}%")
        row = self.song_rows.get(song['key'])
        if row is not None:
            row.set_preset_text(self._punch_ratio_text(ratio), ratio)
        self._render_timeline()

    def _refresh_punch_ratio_slider(self):
        song = self.current_song
        ratio = song['punch_ratio'] if song is not None else 0.5
        self.punch_ratio_slider.set(ratio)
        self.punch_value_label.configure(text=f"{int(round(ratio * 100))}%")

    def _on_margin_slide(self, value):
        if self.margin_value_label is not None:
            self.margin_value_label.configure(text=f"{value:.2f}")
        self.app.settings['margin'] = float(value)
        save_settings(self.app.settings)
        self._render_timeline()

    def _margin(self):
        if self.margin_slider is None:
            return 0.12
        try:
            return float(self.margin_slider.get())
        except Exception:
            return 0.12

    def _on_density_slide(self, value):
        # Per-brano come punch_ratio (prima era un'unica impostazione per l'intera
        # sessione di generazione) - persistito comunque anche in settings come
        # valore di default per i PROSSIMI brani aggiunti, non per quelli gia' in
        # elenco (quelli tengono il proprio valore, modificabile indipendentemente).
        song = self.current_song
        if song is None:
            return
        density = float(value)
        song['density'] = density
        if self.density_value_label is not None:
            self.density_value_label.configure(text=f"{density:.2f}")
        self.app.settings['density'] = density
        save_settings(self.app.settings)
        self._render_timeline()

    def _refresh_density_slider(self):
        if self.density_slider is None:
            return
        song = self.current_song
        density = song['density'] if song is not None else self.app.settings.get('density', 1.0)
        self.density_slider.set(density)
        if self.density_value_label is not None:
            self.density_value_label.configure(text=f"{density:.2f}")

    # I preset della coreografia sono chiavi tecniche stabili ('light'/'medium'/
    # 'high', vedi boxvr_choreo.INTENSITY_PRESETS) ma a schermo vanno tradotte -
    # queste due funzioni fanno da ponte, cosi' cambiare lingua non cambia il
    # valore salvato nel brano.
    def _choreo_preset_from_label(self, label):
        for key in ('light', 'medium', 'high'):
            if label == self.t(f'choreo_{key}'):
                return key
        return 'medium'

    def _choreo_preset_label(self, key):
        return self.t(f'choreo_{key or "medium"}')

    def _refresh_choreo_epm(self):
        """Aggiorna la riga "~N colpi/min · BoxVR ufficiale ~82" sotto il
        selettore del preset. I numeri vengono da INTENSITY_PRESETS
        (misurati, vedi il commento li'), non sono scritti qui: se un domani
        la misura viene rifatta, l'interfaccia segue da sola."""
        label = getattr(self, 'choreo_epm_label', None)
        if label is None:
            return
        # import locale come altrove in questo modulo: boxvr_choreo importa
        # (indirettamente) la GUI per l'anteprima visiva, a livello di modulo
        # sarebbe una dipendenza circolare.
        import boxvr_choreo as _choreo
        preset = _choreo.INTENSITY_PRESETS.get(self._choreo_preset_key or 'medium')
        if not preset or not preset.get('target_epm'):
            label.configure(text="")
            return
        lo, hi = preset.get('epm_range') or (preset['target_epm'], preset['target_epm'])
        label.configure(text=self.t('choreo_epm_hint', epm=preset['target_epm'],
                                    lo=lo, hi=hi, official=_choreo.OFFICIAL_EPM))

    def _on_choreo_preset_change(self, label):
        preset = self._choreo_preset_from_label(label)
        # la chiave logica si aggiorna SEMPRE, anche senza brano selezionato:
        # e' quella che sopravvive a un cambio lingua (vedi apply_language)
        self._choreo_preset_key = preset
        song = self.current_song
        if song is not None:
            song['choreo_preset'] = preset
        # persistito come default per i PROSSIMI brani aggiunti, non per quelli
        # gia' in elenco - stessa logica di density/punch_ratio
        self.app.settings['choreo_preset'] = preset
        save_settings(self.app.settings)
        self._refresh_choreo_epm()

    def _refresh_choreo_preset(self):
        if getattr(self, 'choreo_preset_menu', None) is None:
            return
        song = self.current_song
        preset = (song.get('choreo_preset') if song is not None
                  else self.app.settings.get('choreo_preset')) or 'medium'
        self._choreo_preset_key = preset
        self.choreo_preset_menu.set(self._choreo_preset_label(preset))
        self._refresh_choreo_epm()

    def _classify(self, analysis, ratio, density=1.0):
        if self.mode == 'generate':
            max_silence, max_light_silence = density_to_fractions(density)
            return classify_segments_for_generation(
                analysis, ratio, max_silence_fraction=max_silence,
                max_light_or_silence_fraction=max_light_silence)
        return classify_segments_with_preset(analysis, self._margin(), ratio)

    def _region_tooltip_text(self, regions, x):
        for r in regions:
            if r['x0'] <= x <= r['x1']:
                return self.t('timeline_tooltip', phase=self.t(f"legend_{r['level']}"), n=r['n_events'])
        return None

    def _visible_window(self, duration):
        """(view_start, durata_visibile) in secondi, dato lo zoom corrente -
        clampato cosi' la finestra non esce mai dal brano."""
        visible = duration / max(self.zoom, 1.0)
        view_start = max(0.0, min(duration - visible, self.view_start))
        return view_start, visible

    def _time_to_x(self, t, view_start, visible, w):
        return ((t - view_start) / visible) * w if visible > 0 else 0.0

    def _get_waveform_peaks(self, song):
        """Profilo d'ampiezza (picco assoluto per colonna, WAVEFORM_RESOLUTION
        colonne coprendo l'intero brano) calcolato una volta sola e messo in
        cache sul brano - la timeline ridisegna spesso (ogni cambio preset/zoom/
        pan) e ricalcolarlo dall'audio grezzo ogni volta sarebbe sprecato."""
        if song.get('_waveform_peaks') is not None:
            return song['_waveform_peaks']
        audio = song.get('play_audio')
        if audio is None:
            return None
        mono = audio.mean(axis=1) if audio.ndim > 1 else audio
        n = len(mono)
        peaks = np.zeros(WAVEFORM_RESOLUTION, dtype=np.float32)
        if n > 0:
            idx = np.linspace(0, n, WAVEFORM_RESOLUTION + 1).astype(int)
            for i in range(WAVEFORM_RESOLUTION):
                chunk = mono[idx[i]:idx[i + 1]]
                if len(chunk):
                    peaks[i] = float(np.max(np.abs(chunk)))
        song['_waveform_peaks'] = peaks
        return peaks

    def _draw_waveform(self, song, view_start, visible, w, top, bottom):
        """Profilo d'ampiezza reale disegnato sopra le fasce colorate (in una
        tinta piu' scura dello stesso colore, coerente con le tacche beat) - i
        pattern standard degli editor waveform (wavesurfer.js Regions/Envelope,
        qualunque DAW) mostrano sempre la forma d'onda reale sotto le annotazioni
        colorate, non solo un colore piatto: e' quello che da' il colpo d'occhio
        "qui c'e' un drop, qui c'e' silenzio vero" prima ancora di leggere la
        legenda."""
        peaks = self._get_waveform_peaks(song)
        if peaks is None:
            return
        duration = song['analysis']['duration'] or 1.0
        mid = (top + bottom) / 2.0
        half_h = max((bottom - top) / 2.0 - 2, 1)
        start_idx = int((view_start / duration) * WAVEFORM_RESOLUTION)
        end_idx = int(((view_start + visible) / duration) * WAVEFORM_RESOLUTION)
        end_idx = max(start_idx + 1, min(WAVEFORM_RESOLUTION, end_idx))
        cols = max(int(w), 1)
        col_idx = np.linspace(start_idx, end_idx, cols, endpoint=False).astype(int)
        col_idx = np.clip(col_idx, 0, len(peaks) - 1)
        col_values = peaks[col_idx]
        regions = self._timeline_regions
        ri = 0
        for x in range(cols):
            v = float(col_values[x])
            if v <= 0.001:
                continue
            while ri + 1 < len(regions) and regions[ri]['x1'] < x:
                ri += 1
            lvl = regions[ri]['level'] if regions and regions[ri]['x0'] <= x <= regions[ri]['x1'] else 0
            color = _darken_hex(LEVEL_COLORS.get(lvl, "#555555"), factor=0.7)
            dy = v * half_h
            self.canvas.create_line(x, mid - dy, x, mid + dy, fill=color, width=1)

    def _draw_time_axis(self, view_start, visible, w, axis_top, axis_bottom):
        """Tacche + etichette m:ss lungo il bordo inferiore della timeline
        principale - pattern standard di ogni editor waveform (notch/etichette
        temporali sotto la forma d'onda), assente prima: l'unico riferimento
        temporale era il numero "00:00 / 02:43" sopra i controlli di playback,
        bisognava distogliere lo sguardo dalla timeline per orientarsi."""
        if visible <= 0:
            return
        # Passo "carino" (5/10/15/30s, 1/2/5/10min...) piu' vicino a ~10 tacche
        # visibili, cosi' l'asse resta leggibile sia molto zoomati che no.
        nice_steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800]
        target = visible / 8.0
        step = nice_steps[-1]
        for s in nice_steps:
            if s >= target:
                step = s
                break
        t = math.ceil(view_start / step) * step
        while t <= view_start + visible:
            x = self._time_to_x(t, view_start, visible, w)
            self.canvas.create_line(x, axis_top, x, axis_top + 4, fill=resolve_color(SUBTEXT), width=1)
            # anchor="nw" ancorato subito sotto la tacca (non al bordo inferiore
            # del canvas con anchor="sw"): il testo cresce verso il basso da un
            # punto gia' sicuramente sotto le fasce colorate, invece di crescere
            # verso l'alto da un bordo la cui distanza reale dal testo dipende
            # dall'altezza effettiva del font renderizzato - che con lo scaling
            # DPI di questa macchina (125%, gia' visto altrove in questo stesso
            # file) risultava piu' alta del previsto e faceva invadere le fasce
            # colorate sopra invece di restare nella striscia riservata all'asse.
            self.canvas.create_text(x + 3, axis_top + 5, text=_fmt_time(t), fill=resolve_color(SUBTEXT),
                                     font=(FONT_REGULAR, 8), anchor="nw")
            t += step

    def _render_timeline(self):
        self.canvas.delete("all")
        self.playhead_id = None
        song = self.current_song
        if song is None or song['analysis'] is None:
            self._timeline_regions = []
            self._orig_timeline_regions = []
            if self.canvas_original is not None:
                self.canvas_original.delete("all")
            return
        analysis = song['analysis']
        ratio = song['punch_ratio']
        density = song.get('density', 1.0)
        level_map = self._classify(analysis, ratio, density)
        song['_last_level_map'] = level_map

        duration = analysis['duration'] or 1.0
        view_start, visible = self._visible_window(duration)
        w = max(self.canvas.winfo_width(), 10)
        h_total = max(self.canvas.winfo_height(), 10)
        axis_h = AXIS_HEIGHT if h_total > AXIS_HEIGHT + 20 else 0
        h = h_total - axis_h
        self._timeline_regions = []
        for i, seg in enumerate(analysis['segs']):
            t0 = seg['_startTime']
            t1 = t0 + seg['_length']
            x0 = self._time_to_x(t0, view_start, visible, w)
            x1 = max(self._time_to_x(t1, view_start, visible, w), x0 + 1)
            lvl = level_map.get(i, seg['_energyLevel'])
            color = LEVEL_COLORS.get(lvl, "#555555")
            # outline nel colore di sfondo (non "", che sparisce): senza un
            # separatore, due segmenti adiacenti con lo stesso livello risultante
            # si fondono in un unico blocco indistinguibile - misurato sugli 8
            # brani di test, capita spesso e "nasconde" segmenti veri (fino a piu'
            # della meta' su un brano) dietro un blocco apparentemente unico.
            self.canvas.create_rectangle(x0, 0, x1, h, fill=color, outline=resolve_color(TIMELINE_BG), width=1)
            self._timeline_regions.append({'x0': x0, 'x1': x1, 'level': lvl, 'n_events': seg['_numBeats']})

        self._draw_waveform(song, view_start, visible, w, 0, h)
        if self.timeline_mode == 'beats':
            if self.mode == 'generate':
                self._draw_marker_ticks(song, view_start, visible, w, h)
            else:
                self._draw_beat_ticks(analysis, level_map, view_start, visible, w, h)
        else:
            self._draw_energy_curve(analysis, view_start, visible, w, h)
        if axis_h:
            self.canvas.create_line(0, h, w, h, fill=resolve_color(CARD3), width=1)
            self._draw_time_axis(view_start, visible, w, h + 2, h_total - 2)
        self.playhead_id = self.canvas.create_line(0, 0, 0, h, fill="#ffffff", width=2)

        has_player = self.player is not None and self._player_song is song
        pos_t = self.player.position_seconds() if has_player else 0.0
        self._update_playhead_visual(pos_t, duration, live=has_player)

        if self.canvas_original is not None:
            self._render_original_timeline(analysis, duration)

    def _render_original_timeline(self, analysis, duration):
        """Fascia "prima": stessi segmenti, ma colorati con l'_energyLevel letto
        cosi' com'e' dal trackdata del gioco - level_map non entra qui, e' proprio
        il valore che preset/margine andrebbero a cambiare. Mostra sempre il
        brano per intero (mai lo zoom della fascia principale sotto): resta una
        panoramica fissa d'insieme, come una minimap, utile proprio quando la
        fascia sotto e' zoomata su un dettaglio."""
        c = self.canvas_original
        c.delete("all")
        w = max(c.winfo_width(), 10)
        h = max(c.winfo_height(), 10)
        self._orig_timeline_regions = []
        for seg in analysis['segs']:
            t0 = seg['_startTime']
            t1 = t0 + seg['_length']
            x0 = (t0 / duration) * w
            x1 = max((t1 / duration) * w, x0 + 1)
            lvl = seg['_energyLevel']
            color = LEVEL_COLORS.get(lvl, "#555555")
            c.create_rectangle(x0, 0, x1, h, fill=color, outline=resolve_color(TIMELINE_BG), width=1)
            self._orig_timeline_regions.append({'x0': x0, 'x1': x1, 'level': lvl, 'n_events': seg['_numBeats']})

    def _draw_energy_curve(self, analysis, view_start, visible, w, h):
        bar_score = analysis['bar_score']
        bars = analysis['bars']
        if len(bar_score) < 2:
            return
        max_score = float(np.max(bar_score)) or 1.0
        margin_top, margin_bottom = 4, 4
        usable_h = max(h - margin_top - margin_bottom, 1)
        points = []
        for bi, b in enumerate(bars):
            x = self._time_to_x(b['_startTime'], view_start, visible, w)
            norm = min(1.0, max(0.0, bar_score[bi] / max_score))
            y = margin_top + (1.0 - norm) * usable_h
            points.extend([x, y])
        if len(points) >= 4:
            # Estende l'ultimo tratto fino al bordo destro: l'ultima bar rilevata
            # inizia sempre un po' prima della fine del file, altrimenti la curva
            # sembrerebbe interrompersi prima della fine della timeline.
            points.extend([self._time_to_x(view_start + visible, view_start, visible, w), points[-1]])
            self.canvas.create_line(*points, fill=resolve_color(ENERGY_CURVE_COLOR), width=2, smooth=True)

    # Altezza (frazione dello spazio disponibile, crescita simmetrica dal centro
    # come un misuratore audio) di una tacca "Colpi" per livello - Pugni piena,
    # Misto media, Leggero bassa, Silenzio appena accennata. Resta un'euristica
    # sul GRIGLIA di beat che abbiamo (non decompiliamo il motore del gioco, vedi
    # la conversazione su madmom/generazione eventi), ma da' un colpo d'occhio
    # sull'intensita' relativa che prima mancava (tacche tutte alte uguali).
    BEAT_TICK_HEIGHT_BY_LEVEL = {0: 0.22, 1: 0.45, 2: 1.0, 3: 0.7}

    def _draw_beat_ticks(self, analysis, level_map, view_start, visible, w, h):
        """Una tacca verticale per ogni beat rilevato, colorata come la fase a cui
        appartiene (una tinta piu' scura del colore della fascia di sfondo, per
        risaltare) e alta in proporzione al livello (BEAT_TICK_HEIGHT_BY_LEVEL) -
        non e' "il numero esatto di colpi che generera' il gioco" (quello lo
        decide il motore a runtime), ma la posizione/densita'/intensita' relativa
        reale dei beat su cui il gioco potra' effettivamente agganciare un
        evento, fase per fase - l'informazione piu' vicina che possiamo mostrare
        senza duplicare la logica del gioco."""
        segs = analysis['segs']
        beats = analysis['beats']
        if not beats:
            return
        seg_level_by_beat = {}
        for i, seg in enumerate(segs):
            lvl = level_map.get(i, seg['_energyLevel'])
            start = seg['_startBeatIndex']
            for bi in range(start, start + seg['_numBeats']):
                seg_level_by_beat[bi] = lvl
        mid = h / 2.0
        half_span = h * 0.44
        for b in beats:
            x = self._time_to_x(b['_triggerTime'], view_start, visible, w)
            lvl = seg_level_by_beat.get(b['_index'], 0)
            dy = half_span * self.BEAT_TICK_HEIGHT_BY_LEVEL.get(lvl, 0.22)
            self.canvas.create_line(x, mid - dy, x, mid + dy,
                                     fill=_darken_hex(LEVEL_COLORS.get(lvl, "#555555")), width=1)

    def _draw_marker_ticks(self, song, view_start, visible, w, h):
        """Una stanghetta gialla piena per ogni marker piazzato dall'utente
        (30/08, richiesto: la vecchia vista "Colpi" era una sequenza
        illeggibile - qui invece si vede a colpo d'occhio DOVE si e' marcato,
        senza dover aprire l'anteprima visiva). A tutta altezza e piu' spessa
        delle tacche beat: sono eventi rari e intenzionali dell'utente, non
        un dato denso come i beat automatici, meritano di risaltare di piu'."""
        markers = song.get('sidecar_markers') or []
        for t in markers:
            x = self._time_to_x(t, view_start, visible, w)
            self.canvas.create_line(x, 0, x, h, fill=MARKER_TICK_COLOR, width=2)

    def _set_timeline_mode(self, mode):
        if mode == self.timeline_mode:
            return
        self.timeline_mode = mode
        self._refresh_timeline_mode_buttons()
        self._render_timeline()

    def _refresh_timeline_mode_buttons(self):
        for m, b in self.timeline_mode_buttons.items():
            active = m == self.timeline_mode
            b.configure(fg_color=ACCENT if active else CARD3, text_color="white" if active else TEXT)

    def _on_zoom_slide(self, value):
        song = self.current_song
        old_zoom = self.zoom
        self.zoom = float(value)
        self.zoom_value_label.configure(text=f"{self.zoom:.1f}x")
        if song is not None and song.get('analysis') is not None:
            # Zoomare ricentra la vista sul punto di riproduzione corrente (o
            # sull'inizio se non si e' mai riprodotto nulla), non la lascia ferma
            # sul vecchio view_start - altrimenti aumentare lo zoom potrebbe far
            # "sparire" dalla vista proprio il punto che si stava guardando.
            duration = song['analysis']['duration'] or 1.0
            pos_t = self.player.position_seconds() if (self.player is not None and self._player_song is song) else self.view_start
            old_visible = duration / max(old_zoom, 1.0)
            center = self.view_start + old_visible / 2.0 if old_zoom > 1.0 else pos_t
            new_visible = duration / max(self.zoom, 1.0)
            self.view_start = max(0.0, min(duration - new_visible, center - new_visible / 2.0))
        self._render_timeline()

    def _on_canvas_press(self, event):
        self._canvas_drag_start = (event.x, event.y)
        self._canvas_dragged = False

    def _on_canvas_drag(self, event):
        start = getattr(self, '_canvas_drag_start', None)
        if start is None:
            return
        x0, y0 = start
        if abs(event.x - x0) > 3 or abs(event.y - y0) > 3:
            self._canvas_dragged = True
        if self.zoom <= 1.0:
            return
        song = self.current_song
        if song is None or song['analysis'] is None:
            return
        duration = song['analysis']['duration'] or 1.0
        w = max(self.canvas.winfo_width(), 1)
        _, visible = self._visible_window(duration)
        dt = -(event.x - x0) / w * visible
        self.view_start = max(0.0, min(duration - visible, self.view_start + dt))
        self._canvas_drag_start = (event.x, event.y)
        self._render_timeline()

    def _on_canvas_release(self, event):
        # Un click "secco" (mai trascinato oltre la soglia in _on_canvas_drag)
        # resta un seek come prima - solo un vero trascinamento sposta la vista
        # invece di far saltare la riproduzione. Senza questa distinzione, ogni
        # tentativo di scorrere la timeline zoomata avrebbe anche fatto seek al
        # punto di rilascio del mouse.
        if not getattr(self, '_canvas_dragged', False):
            self._on_canvas_click(event)
        self._canvas_dragged = False

    def _on_canvas_click(self, event):
        song = self.current_song
        if song is None or song['analysis'] is None or not HAS_AUDIO or song['play_audio'] is None:
            return
        w = max(self.canvas.winfo_width(), 1)
        duration = song['analysis']['duration'] or 1.0
        view_start, visible = self._visible_window(duration)
        t = view_start + max(0.0, min(1.0, event.x / w)) * visible
        if self.player is None or self._player_song is not song:
            self._create_player(song)
        if self.player is None:
            return
        self.player.seek(t)
        self._update_playhead_visual(t, duration)

    # -- playback -------------------------------------------------------------

    def _create_player(self, song):
        if self.player is not None:
            self.player.close()
            self.player = None
            self._player_song = None
        volume = self.app.settings.get('volume', 1.0)
        click_on = bool(self.click_track_switch.get()) and song.get('analysis') is not None
        click_overlay = self._click_overlay_for(song) if click_on else None
        try:
            self.player = SongPlayer(song['play_audio'], song['play_sr'], volume=volume, click_overlay=click_overlay)
            self._player_song = song
        except Exception as e:
            # sd.OutputStream() puo' fallire se non c'e' nessun dispositivo audio di
            # output disponibile (cuffie scollegate, driver in errore) - prima non era
            # gestito: l'eccezione restava non catturata dentro un handler di click,
            # il pulsante Play smetteva di funzionare senza alcun messaggio (e in una
            # build --windowed non c'e' nemmeno una console dove vedere il perche').
            self._log(self.t('log_audio_device_error', msg=str(e)))
            messagebox.showerror(self.t('app_title'), self.t('audio_device_error', msg=str(e)))

    def _click_overlay_for(self, song):
        """Overlay dei click (solo i tick, non premiscelati con la canzone) -
        calcolato una volta sola e messo in cache sul brano. Prima il click era
        premiscelato in un unico buffer con la canzone, e lo slider del volume
        scalava quel buffer intero: abbassare il volume per sentire meglio il
        click ne abbassava anche l'intensita', l'opposto di quello che serviva.
        Ora resta separato e SongPlayer lo somma dopo aver applicato il volume
        solo alla canzone (vedi SongPlayer._callback)."""
        if song.get('_click_overlay') is None:
            song['_click_overlay'] = _build_click_overlay(
                song['play_audio'].shape[0], song['play_audio'].shape[1],
                song['play_sr'], song['analysis']['beats'])
        return song['_click_overlay']

    def _on_volume_slide(self, value):
        self.app.settings['volume'] = float(value)
        save_settings(self.app.settings)
        if self.player is not None:
            self.player.set_volume(float(value))

    def _toggle_play(self):
        song = self.current_song
        if song is None or not HAS_AUDIO or song['play_audio'] is None:
            return
        if self.player is None or self._player_song is not song:
            self._create_player(song)
        if self.player is None:
            return
        self.player.toggle()
        self.play_btn.configure(text=self.t('pause') if self.player.stream.active else self.t('play'))

    # -- sidecar (26/08 notte) --------------------------------------------

    def _sidecar_toggle_record(self):
        """'Registra': continua SEMPRE dal punto della timeline su cui ci si
        e' posizionati (click/scrub), non piu' sempre dall'inizio del brano
        (30/08, richiesto esplicitamente: "così posso continuare la
        registrazione se per esempio mi fermo e voglio registrare sopra un
        punto che non mi è piaciuto come è venuto"). E' un "punch-in", non
        un azzeramento totale: i marker DA QUEL PUNTO IN POI (istante
        corrente incluso) vengono scartati - si sta per ri-registrarli - ma
        quelli PRIMA restano intatti. Per azzerare tutto il brano c'e' il
        pulsante dedicato "Resetta" (vedi _sidecar_reset), non piu' Registra.
        Un secondo click ('Ferma') mette in pausa senza toccare nulla: i
        marker restano li' pronti per essere usati, ri-registrati da un
        punto in poi, o cancellati/resettati."""
        song = self.current_song
        if song is None or not HAS_AUDIO or song.get('play_audio') is None:
            return
        if not self._sidecar_recording:
            if self.player is None or self._player_song is not song:
                self._create_player(song)
            if self.player is None:
                return
            cutoff = self.player.position_seconds()
            song['sidecar_markers'] = [t for t in song.get('sidecar_markers') or [] if t < cutoff]
            if not self.player.stream.active:
                self.player.toggle()
            self._sidecar_recording = True
        else:
            if self.player is not None and self.player.stream.active:
                self.player.toggle()
            self._sidecar_recording = False
            # Calibrazione personale (27/08, richiesta esplicita: "il tool
            # impara da come l'utente in locale crea i marker") - a fine
            # registrazione, non a ogni singolo marker: una media su piu'
            # colpi e' un segnale piu' solido di uno grezzo su un solo tap.
            self._learn_sidecar_bias(song)
        if self.player is not None:
            self.play_btn.configure(text=self.t('pause') if self.player.stream.active else self.t('play'))
        self._refresh_sidecar_panel()

    def _sidecar_mark(self):
        """'Marca': registra SOLO l'istante corrente, mai la corsia ne' il
        tipo di colpo - li decide l'algoritmo (stessa filosofia degli accenti
        audio veri, vedi sidecar sandbox/engine.py). Un click che arriva
        troppo vicino al precedente non viene scartato qui: il filtro sul
        limite fisico (MIN_INPUT_GAP_S) e' compito del motore, non della GUI,
        cosi' la stessa regola vale anche per il registratore CLI.

        Usa audible_position_seconds(), non position_seconds() (27/08,
        difetto reale segnalato: "fuori tempo anche premendo al momento
        esatto del beat") - la differenza e' la latenza vera del dispositivo
        audio (90-180ms misurati), che altrimenti anticipa sistematicamente
        ogni marker rispetto al beat che l'utente ha davvero sentito.

        Poi sottrae la CALIBRAZIONE PERSONALE appresa (vedi
        _learn_sidecar_bias) - un secondo correttivo, oltre alla latenza
        del dispositivo sopra: quella e' uguale per chiunque su questa
        macchina, questa e' la tendenza residua di QUESTO utente (chi
        anticipa sempre un po' il beat, chi lo rincorre), imparata dalle sue
        stesse registrazioni precedenti."""
        if not self._sidecar_recording or self.player is None:
            return
        song = self.current_song
        if song is None:
            return
        t = self.player.audible_position_seconds() - self.app.settings.get('sidecar_bias_s', 0.0)
        song.setdefault('sidecar_markers', []).append(max(0.0, t))
        self._refresh_sidecar_panel()

    # oltre questa distanza da un accento reale un marker non e' un "tap un
    # po' fuori tempo" ma probabilmente un colpo voluto su un punto senza
    # accento marcato (es. un levare, un momento a scelta dell'utente) - non
    # va fatto contribuire alla calibrazione, altrimenti la sporca
    SIDECAR_BIAS_LEARN_WINDOW_S = 0.15
    # oltre questo numero di campioni la media mobile diventa quasi
    # insensibile a un cambio di tendenza recente (es. l'utente si accorge
    # di anticipare e si corregge da solo) - la cappiamo per restare adattiva
    SIDECAR_BIAS_MAX_N = 200

    def _learn_sidecar_bias(self, song):
        """Calibrazione personale locale (27/08, richiesta esplicita: "il
        tool impara da come l'utente in locale crea i marker"). Ad ogni
        registrazione fermata, guarda quanto i marker appena piazzati si
        scostano in media dall'accento audio reale piu' vicino, e aggiorna
        una media mobile pesata per conteggio salvata nelle impostazioni
        dell'app (locale, non condivisa - vedi la nota fatta all'utente sul
        perche' questo tipo di esperienza resta sul dispositivo).

        Una media su piu' colpi di UNA registrazione, non un aggiornamento
        per singolo marker: un singolo tap puo' essere un errore isolato,
        una decina di marker nella stessa sessione da' un segnale piu'
        solido sulla tendenza reale dell'utente (sempre un po' in anticipo,
        sempre un po' in ritardo)."""
        markers = song.get('sidecar_markers') or []
        analysis = song.get('analysis')
        if not markers or analysis is None:
            return
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
            if abs(delta) <= self.SIDECAR_BIAS_LEARN_WINDOW_S:
                deltas.append(delta)
        if not deltas:
            return
        session_bias = sum(deltas) / len(deltas)
        session_n = len(deltas)
        prev_bias = self.app.settings.get('sidecar_bias_s', 0.0)
        prev_n = self.app.settings.get('sidecar_bias_n', 0)
        total_n = min(prev_n + session_n, self.SIDECAR_BIAS_MAX_N)
        if prev_n <= 0:
            new_bias = session_bias
        else:
            weight_prev = prev_n / (prev_n + session_n)
            new_bias = prev_bias * weight_prev + session_bias * (1.0 - weight_prev)
        self.app.settings['sidecar_bias_s'] = new_bias
        self.app.settings['sidecar_bias_n'] = total_n
        save_settings(self.app.settings)

    def _on_sidecar_hotkey(self, event):
        """Tasti F/K come scorciatoia per 'Marca' (27/08). Non marca se il
        focus e' su un campo di testo (es. durata playlist) - altrimenti
        scrivere una "f" o una "k" in un campo qualunque, mentre per
        coincidenza si sta anche registrando, marcherebbe per sbaglio invece
        di limitarsi a scrivere la lettera."""
        if isinstance(event.widget, tk.Entry):
            return
        self._sidecar_mark()

    def _sidecar_clear(self):
        song = self.current_song
        if song is None:
            return
        song['sidecar_markers'] = []
        if self._sidecar_recording:
            if self.player is not None and self.player.stream.active:
                self.player.toggle()
                self.play_btn.configure(text=self.t('play'))
            self._sidecar_recording = False
        self._refresh_sidecar_panel()

    def _sidecar_reset(self):
        """'Resetta' (30/08, richiesto esplicitamente insieme al nuovo
        comportamento "punch-in" di Registra, che non azzera piu' nulla da
        solo): riporta il brano ai valori di default dell'intera sezione
        sidecar, non solo i marker come "Cancella" - modalita' 'harmonize',
        "solo hit marker" spento, soglia minima al default del motore."""
        song = self.current_song
        if song is None:
            return
        song['sidecar_markers'] = []
        song['sidecar_mode'] = 'harmonize'
        song['sidecar_exclude_obstacles'] = False
        song['sidecar_min_gap_ms'] = None
        if self._sidecar_recording:
            if self.player is not None and self.player.stream.active:
                self.player.toggle()
                self.play_btn.configure(text=self.t('play'))
            self._sidecar_recording = False
        self._refresh_sidecar_panel()

    def _sidecar_mode_from_label(self, label):
        # 'automatic' rimosso il 30/08 (ridondante con lo strumento
        # "Automatica" a se stante, separato dalla sidecar) - un song
        # residuo con sidecar_mode=='automatic' da una sessione precedente
        # a questo cambiamento ricade su 'harmonize' via _sidecar_mode_label.
        # 'extend' aggiunta lo stesso giorno (fedele ai marker dove ci sono,
        # automatico pieno dove non ci sono - vedi sidecar sandbox/engine.py,
        # MODE_EXTEND).
        for key in ('markers_only', 'harmonize', 'extend'):
            if label == self.t(f'sidecar_mode_{key}'):
                return key
        return 'harmonize'

    def _sidecar_mode_label(self, key):
        # 'automatic' rimosso il 30/08 - vedi _sidecar_mode_from_label.
        if key not in ('markers_only', 'harmonize', 'extend'):
            key = 'harmonize'
        return self.t(f'sidecar_mode_{key}')

    def _on_sidecar_mode_change(self, label):
        song = self.current_song
        if song is None:
            return
        song['sidecar_mode'] = self._sidecar_mode_from_label(label)

    def _generate_tool_from_label(self, label):
        return 'sidecar' if label == self.t('generate_tool_sidecar') else 'automatic'

    def _generate_tool_label(self, tool):
        return self.t('generate_tool_sidecar' if tool == 'sidecar' else 'generate_tool_automatic')

    def _on_generate_tool_change(self, label):
        tool = self._generate_tool_from_label(label)
        song = self.current_song
        if song is not None:
            song['generate_tool'] = tool
        self._apply_generate_tool_visibility(tool)

    def _apply_generate_tool_visibility(self, tool):
        """Mostra automatic_tools_frame O sidecar_frame, mai entrambi - i due
        strumenti sono alternativi, non sovrapponibili (30/08, richiesta
        esplicita di separare "Automatico" dall'essere una sotto-modalita'
        della sidecar). Chiamato alla costruzione del pannello, dal click
        sullo switch, e da _refresh_sidecar_panel quando cambia il brano
        selezionato (ogni brano ricorda il proprio strumento, come
        sidecar_mode)."""
        if self.automatic_tools_frame is None or self.sidecar_frame is None:
            return
        self.generate_tool = tool
        if tool == 'sidecar':
            self.automatic_tools_frame.pack_forget()
            self.sidecar_frame.pack(fill="x", padx=18, pady=(0, 14))
        else:
            self.sidecar_frame.pack_forget()
            self.automatic_tools_frame.pack(fill="x", padx=0, pady=0)
        if self.generate_tool_switch is not None:
            self.generate_tool_switch.set(self._generate_tool_label(tool))

    def _on_sidecar_exclude_toggle(self):
        song = self.current_song
        if song is None:
            return
        song['sidecar_exclude_obstacles'] = bool(self.sidecar_exclude_switch.get())

    def _refresh_sidecar_labels(self):
        """Testi tradotti, statici finche' non cambia la lingua - separati dallo
        stato dinamico (_refresh_sidecar_panel) come per le altre sezioni."""
        if self.sidecar_frame is None:
            return
        # stessa cautela di sidecar_mode_menu: ricostruire i valori (etichette
        # tradotte) e riselezionare dalla CHIAVE logica del brano, non dal
        # testo gia' sul widget - altrimenti un cambio lingua riporterebbe la
        # selezione al primo valore della nuova lista.
        song = self.current_song
        self.generate_tool_switch.configure(
            values=[self.t('generate_tool_automatic'), self.t('generate_tool_sidecar')])
        self.generate_tool_switch.set(self._generate_tool_label(
            song.get('generate_tool', 'automatic') if song is not None else 'automatic'))
        self.sidecar_title_label.configure(text=self.t('sidecar_title'))
        self.sidecar_mark_area.configure(text=self.t('sidecar_mark_area'))
        self.sidecar_clear_btn.configure(text=self.t('sidecar_clear_btn'))
        self.sidecar_reset_btn.configure(text=self.t('sidecar_reset_btn'))
        self.sidecar_mode_label.configure(text=self.t('sidecar_mode_label'))
        # i valori del segmented button sono etichette tradotte: al cambio
        # lingua vanno ricostruite, la selezione ripresa dalla CHIAVE logica
        # tenuta sul brano - stessa cautela gia' presa per choreo_preset_menu
        # (rileggere l'etichetta dal widget qui fallirebbe silenziosamente
        # dopo un cambio lingua, riportando la scelta al primo valore).
        # 'Automatico' rimosso il 30/08 (ridondante, vedi
        # _sidecar_mode_from_label): quella terza voce e' ora lo strumento
        # "Automatica" a se stante. 'Estendi' aggiunta lo stesso giorno.
        self.sidecar_mode_menu.configure(values=[
            self.t('sidecar_mode_markers_only'), self.t('sidecar_mode_harmonize'),
            self.t('sidecar_mode_extend')])
        song = self.current_song
        self.sidecar_mode_menu.set(self._sidecar_mode_label(
            song.get('sidecar_mode') if song is not None else None))
        self.sidecar_exclude_label.configure(text=self.t('sidecar_exclude_label'))
        self.sidecar_min_gap_label.configure(text=self.t('sidecar_min_gap_label'))
        self._refresh_sidecar_panel()

    def _refresh_sidecar_panel(self):
        """Stato dinamico (abilitato/disabilitato, conteggio marker) - chiamato
        al cambio brano, dopo ogni marker registrato/cancellato, e dal refresh
        dei testi sopra cosi' non serve duplicare la logica del conteggio."""
        if self.sidecar_frame is None:
            return
        song = self.current_song
        has_song = song is not None and HAS_AUDIO and song.get('play_audio') is not None
        n = len(song.get('sidecar_markers') or []) if song is not None else 0
        # Segue lo strumento del brano SELEZIONATO (30/08): ogni brano
        # ricorda se lo si sta lavorando con "Automatica" o "Sidecar", come
        # gia' fa per sidecar_mode/choreo_preset - senza questo, cambiando
        # brano lo switch resterebbe fermo sull'ultima scelta del brano
        # precedente invece di riflettere quella vera del nuovo.
        self._apply_generate_tool_visibility(song.get('generate_tool', 'automatic') if song is not None else 'automatic')
        # fg_color esplicito anche qui (27/08): un CTkButton disabilitato non
        # si distingue abbastanza da uno attivo solo cambiando `state` - e'
        # proprio quello che ha reso invisibile all'utente che il pulsante
        # era disabilitato in un giro precedente (bug reale: il pannello non
        # veniva riaggiornato quando l'audio del brano finiva di caricare in
        # background, vedi _poll_analysis_queue).
        self.sidecar_record_btn.configure(
            state="normal" if has_song else "disabled",
            fg_color=ACCENT if has_song else CARD_HOVER,
            text_color="white" if has_song else SUBTEXT,
            text=self.t('sidecar_stop_btn') if self._sidecar_recording else self.t('sidecar_record_btn'))
        mark_enabled = has_song and self._sidecar_recording
        # l'area grande usa lo stesso colore ACCENT del pulsante Registra
        # quando puo' davvero essere premuta - senza, a bordo colorato ma
        # fg_color grigio fisso, si rischia la stessa confusione "sembra
        # attivo ma non lo e'" gia' vista con Registra (vedi sotto).
        self.sidecar_mark_area.configure(
            state="normal" if mark_enabled else "disabled",
            fg_color=ACCENT if mark_enabled else CARD_HOVER,
            text_color="white" if mark_enabled else SUBTEXT)
        self.sidecar_clear_btn.configure(state="normal" if (has_song and n > 0) else "disabled")
        # "Resetta" si abilita anche se non ci sono marker ma qualcos'altro
        # e' gia' stato cambiato dal default (modalita'/"solo hit marker"/
        # soglia) - "Cancella" guarda solo ai marker, "Resetta" a tutto lo
        # stato sidecar del brano.
        has_non_default_state = bool(
            song is not None and (
                n > 0
                or (song.get('sidecar_mode') or 'harmonize') != 'harmonize'
                or song.get('sidecar_exclude_obstacles')
                or song.get('sidecar_min_gap_ms') is not None))
        self.sidecar_reset_btn.configure(state="normal" if (has_song and has_non_default_state) else "disabled")
        self.sidecar_count_label.configure(text=self.t('sidecar_count', n=n))
        # nessun interruttore da riflettere qui (tolto il 27/08): la nota
        # sotto dice semplicemente cosa succede, sempre vero per costruzione
        # visto che non c'e' piu' uno stato separato da disallineare.
        self.sidecar_usage_label.configure(
            text=self.t('sidecar_usage_note_active' if n > 0 else 'sidecar_usage_note_empty'))
        # modalita' ed "solo hit marker" (27/08): impostabili anche prima di
        # registrare alcun marker (sono preferenze per QUANDO ce ne saranno),
        # quindi legate a has_song, non al conteggio n come i pulsanti sopra.
        self.sidecar_mode_menu.configure(state="normal" if has_song else "disabled")
        self.sidecar_mode_menu.set(self._sidecar_mode_label(
            song.get('sidecar_mode') if song is not None else None))
        self.sidecar_exclude_switch.configure(state="normal" if has_song else "disabled")
        if song is not None and song.get('sidecar_exclude_obstacles'):
            self.sidecar_exclude_switch.select()
        else:
            self.sidecar_exclude_switch.deselect()
        self.sidecar_min_gap_slider.configure(state="normal" if has_song else "disabled")
        self._refresh_sidecar_min_gap(song, n)
        # se la timeline sta mostrando i marker, ridisegnarla appena cambiano
        # (marcato/cancellato) - senza questo la vista "Marker" resterebbe
        # ferma alla situazione di quando e' stata aperta l'ultima volta,
        # invece di seguire in diretta quello che si sta registrando.
        if self.mode == 'generate' and self.timeline_mode == 'beats':
            self._render_timeline()

    def _sidecar_min_gap_ms_for(self, song):
        if song is None:
            return SIDECAR_MIN_GAP_DEFAULT_MS
        return song.get('sidecar_min_gap_ms') or SIDECAR_MIN_GAP_DEFAULT_MS

    def _refresh_sidecar_min_gap(self, song, n):
        """Sincronizza slider/etichetta con la soglia del brano corrente e
        ricalcola LIVE quanti marker verrebbero scartati a quella soglia -
        stessa regola usata davvero in generazione (sidecar_engine().
        snap_and_filter_markers), non una stima approssimata separata che
        rischierebbe di disallinearsi (30/08, richiesto esplicitamente:
        "un indicatore di quanti marker verranno rimossi con una data
        soglia")."""
        gap_ms = self._sidecar_min_gap_ms_for(song)
        self.sidecar_min_gap_slider.set(gap_ms)
        self.sidecar_min_gap_value_label.configure(text=f"{gap_ms:.0f} ms")
        if song is None or n == 0:
            self.sidecar_min_gap_dropped_label.configure(text="")
            return
        onsets = (song.get('analysis') or {}).get('onsets') if song.get('analysis') else None
        survivors = len(sidecar_engine().snap_and_filter_markers(
            song['sidecar_markers'], onsets, min_gap_s=gap_ms / 1000.0))
        dropped = n - survivors
        if dropped > 0:
            self.sidecar_min_gap_dropped_label.configure(
                text=self.t('sidecar_min_gap_dropped', dropped=dropped, n=n))
        else:
            self.sidecar_min_gap_dropped_label.configure(text=self.t('sidecar_min_gap_none_dropped'))

    def _on_sidecar_min_gap_slide(self, value):
        song = self.current_song
        if song is None:
            return
        song['sidecar_min_gap_ms'] = round(float(value))
        self._refresh_sidecar_min_gap(song, len(song.get('sidecar_markers') or []))

    def _open_visual_preview(self):
        """Apre l'anteprima visiva sul brano selezionato, costruendo la
        coreografia al volo dall'analisi gia' in memoria - non serve che il
        brano sia gia' generato o installato: e' proprio il punto, giudicare
        prima di scrivere i file.

        Import dentro la funzione, non in cima: boxvr_visual_preview importa a
        sua volta SongPlayer da questo modulo, quindi a livello di modulo
        sarebbe una dipendenza circolare (stessa convenzione gia' usata fra
        boxvr_generator e boxvr_choreo).
        """
        song = self.current_song
        if song is None or song.get('analysis') is None:
            return
        try:
            import boxvr_choreo as _choreo
            import boxvr_visual_preview as _vp
        except Exception as e:
            messagebox.showerror(self.app.t('app_title'), self.t('visual_preview_error', msg=str(e)))
            return

        # se una finestra e' gia' aperta la si riusa, invece di accumularne una
        # per ogni click (ognuna tiene aperto un suo stream audio)
        if getattr(self, '_visual_win', None) is not None:
            try:
                self._visual_win.destroy()
            except Exception:
                pass
            self._visual_win = None

        try:
            markers = song.get('sidecar_markers') or None
            if markers:
                _engine = sidecar_engine()
                actions = _engine.build_choreography(
                    song['analysis'], markers, preset=song.get('choreo_preset') or _choreo.DEFAULT_PRESET,
                    mode=song.get('sidecar_mode') or _engine.MODE_HARMONIZE,
                    exclude_obstacles=bool(song.get('sidecar_exclude_obstacles')),
                    # stesso correct_imprecision=True e stessa soglia min_gap_s
                    # della generazione reale (boxvr_generator.generate_track)
                    # - altrimenti l'anteprima mostrerebbe una coreografia
                    # diversa da quella che poi finisce davvero nel gioco.
                    correct_imprecision=True,
                    min_gap_s=self._sidecar_min_gap_ms_for(song) / 1000.0)
            else:
                actions = _choreo.build_move_actions(
                    song['analysis'], preset=song.get('choreo_preset') or _choreo.DEFAULT_PRESET)
            if not actions:
                messagebox.showinfo(self.app.t('app_title'), self.t('visual_preview_empty'))
                return
            # la mano e' una convenzione visiva nostra, non un dato del formato:
            # la decide la colonna dove il colpo atterra (vedi
            # boxvr_visual_preview.hand_for_channel), non un contatore cieco -
            # altrimenti un'icona "destra" puo' finire sulla colonna Sinistra,
            # segnalato il 2026-08-24 guardando proprio questa finestra
            center_hand = itertools.cycle(('L', 'R'))
            marks = [{'startTime': a['startTime'], 'moveType': a['moveType'],
                      'moveChannel': a['moveChannel'],
                      'hand': _vp.hand_for_channel(a['moveChannel'], center_hand) if a['moveType'] in _vp.PUNCH_TYPES else None,
                      # marcato dall'utente (sidecar), non deciso dal solo
                      # algoritmo - segnalato in anteprima con un indicatore
                      # dedicato (richiesto 27/08): qui la corsia/il tipo li
                      # ha scelti l'algoritmo comunque, ma l'ISTANTE e' quello
                      # che l'utente ha marcato a mano, vale la pena vederlo.
                      'sidecar': bool(a.get('_sidecar'))}
                     for a in sorted(actions, key=lambda a: a['startTime'])]

            audio, sr = song.get('play_audio'), song.get('play_sr')
            if audio is None or sr is None:
                messagebox.showinfo(self.app.t('app_title'), self.t('visual_preview_no_audio'))
                return

            win = ctk.CTkToplevel(self)
            win.transient(self.winfo_toplevel())
            self._visual_win = win
            self._set_visual_preview_lock(True)
            _vp.PreviewWindow(win, {'label': f"{song.get('name','?')} - {song.get('artist','?')}",
                                     'audio': audio, 'sr': sr, 'actions': marks},
                               on_close=self._on_visual_preview_closed)
        except Exception as e:
            messagebox.showerror(self.app.t('app_title'), self.t('visual_preview_error', msg=str(e)))

    def _set_visual_preview_lock(self, locked):
        """Blocca/sblocca i controlli che cambiano la coreografia mentre
        l'anteprima visiva e' aperta - l'anteprima e' uno scatto dei parametri
        al momento dell'apertura (vedi _open_visual_preview), lasciarli
        modificabili la renderebbe disallineata da quello che si sta guardando
        senza che il brano venga rigenerato. Richiesto 2026-08-24; vale anche
        come riferimento per lo stesso comportamento nella futura GUI."""
        state = "disabled" if locked else "normal"
        for widget in (self.punch_ratio_slider, self.density_slider, self.choreo_preset_menu):
            if widget is not None:
                widget.configure(state=state)

    def _on_visual_preview_closed(self):
        self._visual_win = None
        self._set_visual_preview_lock(False)

    def _on_click_track_toggle(self):
        song = self.current_song
        if song is None or song.get('analysis') is None:
            return
        if self.player is not None and self._player_song is song:
            overlay = self._click_overlay_for(song) if bool(self.click_track_switch.get()) else None
            self.player.set_click_overlay(overlay)

    def _step_bpm(self, delta):
        song = self.current_song
        if song is None or song.get('analysis') is None:
            return
        self._apply_forced_bpm(round(song['analysis']['bpm']) + delta)

    def _on_bpm_entry_commit(self, event=None):
        song = self.current_song
        if song is None:
            return
        try:
            new_bpm = float(self.bpm_entry_var.get().replace(',', '.'))
        except ValueError:
            if song.get('analysis') is not None:
                self.bpm_entry_var.set(f"{song['analysis']['bpm']:.1f}")
            else:
                self.bpm_entry_var.set(f"{song['forced_bpm']:.1f}" if song.get('forced_bpm') else "")
            return
        if song.get('analysis') is not None:
            self._apply_forced_bpm(new_bpm)
        else:
            self._set_forced_bpm_before_analysis(new_bpm)

    def _set_forced_bpm_before_analysis(self, new_bpm):
        """Il campo BPM si puo' compilare ANCHE prima che l'analisi
        automatica sia finita (30/08, difetto reale segnalato: "magari
        conosco gia' i bpm e non ha senso aspettare l'analisi") - se il
        brano e' ancora in coda (non ancora preso in carico dal worker),
        basta scrivere qui: _background_analysis_loop legge
        song.get('forced_bpm') SOLO al momento in cui estrae il brano dalla
        coda, quindi lo trovera' gia' impostato. Se invece l'analisi e' GIA'
        in corso in questo istante, quella chiamata ha gia' catturato il
        valore precedente - si segna il brano per una ri-analisi automatica
        non appena arriva quel risultato ormai superato (vedi
        _poll_analysis_queue, ramo 'done')."""
        song = self.current_song
        if song is None:
            return
        new_bpm = max(40.0, min(300.0, float(new_bpm)))
        song['forced_bpm'] = new_bpm
        if song.get('_status') == 'analyzing':
            song['_bpm_pending_requeue'] = True
        self.bpm_entry_var.set(f"{new_bpm:.1f}")

    def _apply_forced_bpm(self, new_bpm):
        """Rimette in coda il brano corrente per una nuova analisi, questa volta
        con start_bpm agganciato al valore scelto dall'utente (campo di testo o
        frecce +-1, non piu' un dialog modale - si vuole poter aggiustare e
        riascoltare subito con la base a click) invece che a quello rilevato
        automaticamente (vedi detect_beats_and_bars in boxvr_generator.py,
        forced_bpm) - la correzione si propaga anche alla generazione batch
        finale (salvata su song['forced_bpm'], riusata da _start_processing)."""
        song = self.current_song
        if song is None or song.get('analysis') is None:
            return
        new_bpm = max(40.0, min(300.0, float(new_bpm)))
        current_bpm = song['analysis']['bpm']
        if abs(new_bpm - current_bpm) < 0.05:
            return
        song['forced_bpm'] = new_bpm
        song['analysis'] = None
        song['_click_overlay'] = None
        song['_status'] = 'queued'
        row = self.song_rows.get(song['key'])
        if row is not None:
            row.set_status('queued')
        self.play_btn.configure(state="disabled")
        self.canvas.delete("all")
        self._start_spinner()
        self.bpm_entry_var.set(f"{new_bpm:.1f}")
        self._analysis_pending.put(song)

    def _on_beat_engine_toggle(self):
        """Cambia il motore di beat-tracking del brano corrente e rimette in coda
        per una nuova analisi - stesso schema di _apply_forced_bpm (invalida
        analisi/click/overlay, torna 'queued', rimette in coda), dato che
        cambiare motore significa ricalcolare i beat da zero."""
        song = self.current_song
        if song is None:
            return
        song['beat_engine'] = 'madmom' if bool(self.beat_engine_switch.get()) else 'librosa'
        song['forced_bpm'] = None  # un forced_bpm dell'altro motore non ha senso qui
        # Da qui in poi la scelta e' dell'utente, non piu' automatica - il
        # pre-check (_background_analysis_loop) non deve piu' rifare la scelta
        # al posto suo ne' rigenerare un flag "sospetto" ormai non pertinente
        # (l'utente ha gia' visto e agito).
        song['engine_mode'] = 'manual'
        song['suspicious'] = False
        song['stability_std'] = None
        song['analysis'] = None
        song['_click_overlay'] = None
        song['_status'] = 'queued'
        row = self.song_rows.get(song['key'])
        if row is not None:
            row.set_status('queued')
            row.set_suspicious(False)
        self.play_btn.configure(state="disabled")
        self.canvas.delete("all")
        self._start_spinner()
        self._analysis_pending.put(song)

    def _update_bpm_panel(self):
        if self.bpm_panel is None:
            return
        song = self.current_song
        if song is None:
            self.bpm_value_label.configure(text=self.t('bpm_panel_text', bpm='?'))
            self.bpm_warning_label.pack_forget()
            self.bpm_search_btn.pack_forget()
            self.bpm_entry.configure(state="disabled")
            self.bpm_up_btn.configure(state="disabled")
            self.bpm_down_btn.configure(state="disabled")
            self.bpm_entry_var.set("")
            return
        if song.get('analysis') is None:
            # Analisi non ancora pronta - il CAMPO resta comunque scrivibile
            # (30/08, difetto reale segnalato: "magari conosco gia' i bpm e
            # non ha senso aspettare l'analisi"), vedi
            # _set_forced_bpm_before_analysis. Le frecce +-1 restano
            # disabilitate: non c'e' ancora un valore rilevato da cui partire
            # per incrementare/decrementare di 1.
            self.bpm_value_label.configure(text=self.t('bpm_panel_text', bpm='?'))
            self.bpm_warning_label.pack_forget()
            self.bpm_search_btn.pack_forget()
            self.bpm_entry.configure(state="normal")
            self.bpm_up_btn.configure(state="disabled")
            self.bpm_down_btn.configure(state="disabled")
            forced = song.get('forced_bpm')
            self.bpm_entry_var.set(f"{forced:.1f}" if forced else "")
            return
        bpm = song['analysis']['bpm']
        self.bpm_value_label.configure(text=self.t('bpm_panel_text', bpm=f"{bpm:.1f}"))
        self.bpm_entry.configure(state="normal")
        self.bpm_up_btn.configure(state="normal")
        self.bpm_down_btn.configure(state="normal")
        self.bpm_entry_var.set(f"{bpm:.1f}")
        if song.get('tempo_corrected'):
            self.bpm_warning_label.pack(side="left", padx=(8, 0))
        else:
            self.bpm_warning_label.pack_forget()
        if song.get('suspicious'):
            self.bpm_search_btn.pack(side="left", padx=(4, 0))
        else:
            self.bpm_search_btn.pack_forget()

    def _open_bpm_search(self):
        song = self.current_song
        if song is None:
            return
        webbrowser.open(bpm_search_url(song.get('name', ''), song.get('artist', '')))

    def _poll_playhead(self):
        if self.player is not None and self.current_song is not None and self._player_song is self.current_song:
            duration = self.current_song['analysis']['duration'] or 1.0
            pos_t = self.player.position_seconds()
            self._update_playhead_visual(pos_t, duration)
            if self.player.finished:
                self.play_btn.configure(text=self.t('play'))
            delay = 33 if self.player.stream.active else 150
        else:
            delay = 150
        self.after(delay, self._poll_playhead)

    def _update_playhead_visual(self, pos_t, duration, live=True):
        """`live=False` e' il solo caso in cui pos_t e' un valore sintetico (0.0,
        nessuna riproduzione in corso per questo brano) invece della vera
        posizione di playback - senza questa distinzione, ogni pan manuale con
        lo zoom attivo veniva subito annullato: _render_timeline richiama questo
        metodo a fine ridisegno anche a riproduzione ferma, e pos_t=0.0 risultava
        quasi sempre "fuori dalla vista" dopo un trascinamento, facendo scattare
        la ricentratura automatica pensata solo per seguire il playhead reale."""
        view_start, visible = self._visible_window(duration)
        if live and self.zoom > 1.0 and (pos_t < view_start or pos_t > view_start + visible):
            # Il playhead e' uscito dalla finestra zoomata durante la
            # riproduzione: ricentra la vista invece di lasciarlo sparire fuori
            # schermo (si puo' comunque trascinare per guardare altrove, il
            # prossimo avanzamento la ricentrera' di nuovo).
            self.view_start = max(0.0, min(duration - visible, pos_t - visible / 2.0))
            self._render_timeline()
            return
        w = max(self.canvas.winfo_width(), 1)
        x = self._time_to_x(pos_t, view_start, visible, w)
        if self.playhead_id is not None:
            self.canvas.coords(self.playhead_id, x, 0, x, self.canvas.winfo_height())
        self.time_label.configure(text=f"{_fmt_time(pos_t)} / {_fmt_time(duration)}")

        song = self.current_song
        if song is None or song['analysis'] is None or self._spinner_active:
            return
        level_map = song.get('_last_level_map', {})
        for i, seg in enumerate(song['analysis']['segs']):
            t0 = seg['_startTime']
            t1 = t0 + seg['_length']
            if t0 <= pos_t < t1:
                lvl = level_map.get(i, seg['_energyLevel'])
                self.phase_label.configure(text=self.t('phase', level=self.t(f'legend_{lvl}')))
                break

    def _on_dry_run_toggle(self):
        """"Sostituisci gli originali" non ha senso insieme a "Solo report" (dry-run
        non scrive nulla, quindi non c'e' nulla da sostituire) - prima restavano
        entrambi selezionabili insieme, ambiguo su quale avrebbe vinto. Ora lo
        switch di sostituzione si disabilita (e si spegne) quando dry-run e'
        attivo, invece di lasciare una combinazione senza significato."""
        if self.replace_originals_switch is None:
            return
        if bool(self.dry_run_switch.get()):
            self.replace_originals_switch.deselect()
            self.replace_originals_switch.configure(state="disabled")
        else:
            self.replace_originals_switch.configure(state="normal")

    def _on_playlist_duration_change(self, event=None):
        """Persiste il valore appena il campo perde il fuoco o si preme
        Invio - la stessa lettura che _get_max_playlist_minutes() rifara' per
        davvero all'avvio della generazione, cosi' i due punti non possono
        disallinearsi silenziosamente."""
        self.app.settings['max_playlist_minutes'] = self._get_max_playlist_minutes()
        save_settings(self.app.settings)

    def _get_max_playlist_minutes(self):
        """None = nessun limite (comportamento di sempre): campo vuoto, zero,
        negativo o testo non numerico ricadono tutti li' invece di bloccare
        la generazione per un'opzione facoltativa - vedi generate_songs()."""
        if self.max_playlist_minutes_entry is None:
            return None
        raw = self.max_playlist_minutes_entry.get().strip()
        if not raw:
            return None
        try:
            val = float(raw)
        except ValueError:
            self._log(self.t('log_playlist_duration_invalid', value=raw))
            return None
        return val if val > 0 else None

    # -- elaborazione ---------------------------------------------------------

    def _start_processing(self):
        if not self.songs:
            return
        if self.worker and self.worker.is_alive():
            return
        if self.mode == 'generate':
            n_auto = sum(1 for s in self.songs if s.get('engine_mode', 'auto') == 'auto')
            if n_auto > 0 and is_madmom_available():
                choice = self._ask_engine_choice(n_auto)
                if choice is None:
                    return
                if choice == 'madmom':
                    for s in self.songs:
                        s['beat_engine'] = 'madmom'
                elif choice == 'librosa':
                    for s in self.songs:
                        s['beat_engine'] = 'librosa'
                # 'recommended': beat_engine di ogni brano resta quello gia' deciso
                # dal pre-check automatico (_background_analysis_loop) - nessuna
                # modifica necessaria qui.
        margin = self._margin()

        self.run_btn.configure(state="disabled")
        self.browse_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.progress.configure(mode="determinate")
        self.progress.set(0)
        # subito animata (30/08): il primo brano non ha ancora nessuna riga
        # "[i/n]" da mostrare, quindi senza questo la barra resterebbe ferma
        # a 0% per tutta la sua elaborazione - vedi _log per il resto del
        # meccanismo indeterminate/determinate alternato.
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self._clear_log()
        start_key = 'log_start_correct' if self.mode == 'correct' else 'log_start_generate'
        self._log(self.t(start_key, n=len(self.songs)))
        self._log(self.t('log_params', margin=margin, dry_run=bool(self.dry_run_switch.get())) + "\n")

        dry_run = bool(self.dry_run_switch.get())
        output_folder = os.path.join(self.base_folder or os.getcwd(), 'corretti' if self.mode == 'correct' else 'generati')
        if self.mode == 'correct':
            items = [{'txt_path': s['txt_path'], 'wav_path': s['wav_path'], 'tid': s['key'],
                      'ratio': s['punch_ratio']} for s in self.songs]
        else:
            # boundary_bars: i confini strutturali gia' calcolati durante
            # l'analisi di anteprima vengono passati alla generazione invece di
            # essere ricalcolati. Non e' solo un risparmio di tempo: il
            # segmentatore non e' deterministico (vedi structural_segment_times),
            # quindi ricalcolarlo qui darebbe un file DIVERSO da quello che
            # l'utente ha appena visto nella timeline.
            items = [{'audio_path': s['audio_path'], 'ratio': s['punch_ratio'],
                      'density': s.get('density', 1.0), 'forced_bpm': s.get('forced_bpm'),
                      'beat_engine': s.get('beat_engine', 'librosa'),
                      'preset': s.get('choreo_preset'),
                      'boundary_bars': (s.get('analysis') or {}).get('seg_boundary_bars'),
                      'marker_times': s.get('sidecar_markers') or None,
                      'sidecar_mode': s.get('sidecar_mode'),
                      'exclude_obstacles': bool(s.get('sidecar_exclude_obstacles')),
                      'min_gap_ms': s.get('sidecar_min_gap_ms')}
                     for s in self.songs]
        for s in self.songs:
            self._log(self.t('log_preset_line', name=s['name'], artist=s['artist'],
                              preset=self._punch_ratio_text(s['punch_ratio'])))

        in_place = bool(self.replace_originals_switch.get()) if self.replace_originals_switch is not None else False
        max_playlist_minutes = self._get_max_playlist_minutes() if self.mode == 'generate' else None
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(items, output_folder, margin, dry_run, in_place, max_playlist_minutes), daemon=True,
        )
        self.worker.start()

    def _run_worker(self, items, output_folder, margin, dry_run, in_place=False, max_playlist_minutes=None):
        try:
            if self.mode == 'correct':
                result = process_songs_with_presets(
                    items, output_folder, margin=margin, dry_run=dry_run, in_place=in_place,
                    log=lambda msg: self.log_queue.put(("log", msg)),
                )
            else:
                # nome playlist: dalla cartella di origine dei brani, cosi'
                # una sessione di generazione produce un allenamento gia'
                # assemblato invece di file sciolti da unire a mano
                pl_name = os.path.basename(os.path.normpath(self.base_folder)) if self.base_folder else None
                result = generate_songs(
                    items, output_folder, dry_run=dry_run, playlist_name=pl_name,
                    max_playlist_minutes=max_playlist_minutes,
                    log=lambda msg: self.log_queue.put(("log", msg)),
                )
            self.log_queue.put(("done", result))
        except Exception as e:
            self.log_queue.put(("error", str(e)))

    def _poll_log_queue(self):
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "done":
                    self._on_finished(payload)
                elif kind == "error":
                    self._on_error(payload)
        except queue.Empty:
            pass
        self.after(80, self._poll_log_queue)

    def _on_finished(self, result):
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(1.0)
        self.run_btn.configure(state="normal")
        self.browse_btn.configure(state="normal")
        if result.get("output_folder") and result.get("n_ok", 0) + result.get("n_errors", 0) > 0:
            self.last_output_folder = result["output_folder"]
            # SOLO gli id costruiti in QUESTA sessione, non tutto cio' che
            # potrebbe gia' esserci in output_folder da sessioni precedenti -
            # e' la cartella fissa "generati"/"corretti", mai ripulita. Vedi
            # boxvr_install.files_for_track_ids (bug segnalato 25/08).
            self.last_track_ids = result.get("track_ids") or []
            self.last_playlist_path = result.get("playlist_path")
            self.open_btn.configure(state="normal")
            if self.install_btn is not None:
                self.install_btn.configure(state="normal")
            if self.mode == 'correct':
                messagebox.showinfo(self.t('app_title'), self.t(
                    'done_summary_correct', n_ok=result['n_ok'], n_changed=result['n_changed'],
                    n_total_changes=result['n_total_changes'], n_skipped=result['n_skipped'],
                    n_errors=result['n_errors'], output_folder=result['output_folder'],
                ))
            else:
                messagebox.showinfo(self.t('app_title'), self.t(
                    'done_summary_generate', n_ok=result['n_ok'], n_errors=result['n_errors'],
                    output_folder=result['output_folder'],
                ))
        else:
            messagebox.showwarning(self.t('app_title'), self.t('warn_no_txt'))

    def _on_error(self, message):
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(0)
        self.run_btn.configure(state="normal")
        self.browse_btn.configure(state="normal")
        # _start_processing disabilita sempre open_btn/install_btn all'avvio di un
        # nuovo run - se questo run fallisce del tutto (non i singoli brani, quello
        # e' gia' gestito riga per riga, ma un errore di sistema), prima restavano
        # disabilitati anche se un run precedente riuscito aveva gia' una cartella
        # d'output valida da poter riaprire/installare.
        has_prior_output = bool(self.last_output_folder and os.path.isdir(self.last_output_folder))
        self.open_btn.configure(state="normal" if has_prior_output else "disabled")
        if self.install_btn is not None:
            self.install_btn.configure(state="normal" if has_prior_output else "disabled")
        self._log(self.t('log_error', message=message))
        messagebox.showerror(self.t('app_title'), self.t('error_prefix', message=message))

    def _open_output_folder(self):
        if self.last_output_folder and os.path.isdir(self.last_output_folder):
            os.startfile(self.last_output_folder)

    def _open_boxvr_folder(self):
        """Apre %AppData%/LocalLow/FITXR/BoxVR/Playlists - contiene TrackData (dove
        vivono trackdata.txt + wav, sia per correggere che per installare un brano
        generato) e TrackDefinitions (dove va il wdef.txt di un brano generato da
        zero)."""
        # la cartella padre di TrackData: un livello sopra i percorsi che
        # boxvr_install conosce, ricavata da li' invece di riscriverla
        folder = os.path.dirname(boxvr_install.boxvr_dirs()[0])
        if os.path.isdir(folder):
            os.startfile(folder)
        else:
            messagebox.showwarning(self.t('app_title'), self.t('warn_boxvr_folder_missing', folder=folder))

    def _show_generate_info(self):
        messagebox.showinfo(self.t('app_title'), self.t('info_generate_body'))

    # I percorsi della libreria live vivono in boxvr_install.boxvr_dirs(),
    # unica fonte di verita' - qui erano duplicati (terza copia nel progetto).
    def _boxvr_track_dirs(self):
        trackdata, trackdefs, _ = boxvr_install.boxvr_dirs()
        return trackdata, trackdefs

    def _boxvr_playlists_dir(self):
        return boxvr_install.boxvr_dirs()[2]

    def _install_to_boxvr(self):
        """Copia i file appena generati (trackdata.txt+wav in TrackData, wdef.txt in
        TrackDefinitions) direttamente nella libreria live di BoxVR su questo PC.
        Chiede sempre conferma esplicita prima di scrivere, dato che tocca dati reali
        del gioco al di fuori della cartella di output dello strumento. Controlla anche
        se il gioco e' aperto in questo momento e se qualche brano sovrascriverebbe
        una traccia gia' installata, lasciando scegliere quali sovrascrivere.

        Installa SOLO i brani di self.last_track_ids (quelli costruiti
        nell'ultima sessione), non tutto cio' che scan_generated troverebbe
        elencando l'intera output_folder - che e' una cartella fissa, mai
        ripulita fra una sessione e l'altra. Bug reale segnalato dall'utente
        25/08: installava anche brani di giorni prima, mischiati a quelli
        freschi nella stessa playlist."""
        track_ids = list(self.last_track_ids)
        data_files, wdef_files = boxvr_install.files_for_track_ids(self.last_output_folder, track_ids)
        if not data_files and not wdef_files:
            messagebox.showwarning(self.t('app_title'), self.t('warn_install_no_files'))
            return

        if _is_boxvr_running():
            if not messagebox.askyesno(self.t('app_title'), self.t('warn_boxvr_running')):
                return

        trackdata_dir, trackdefs_dir = self._boxvr_track_dirs()
        conflicts = [{'tid': tid, 'name': self._track_display_name(tid)}
                     for tid in boxvr_install.find_conflicts(track_ids, trackdata_dir, trackdefs_dir)]

        skip_tids = set()
        if conflicts:
            selection = self._ask_overwrite_selection(conflicts)
            if selection is None:
                return
            skip_tids = selection

        data_files = [f for f in data_files if self._track_id_of(f, ('.trackdata.txt', '.wav')) not in skip_tids]
        wdef_files = [f for f in wdef_files if self._track_id_of(f, ('.wdef.txt',)) not in skip_tids]
        if not data_files and not wdef_files:
            return  # l'utente ha escluso tutti i brani in conflitto, nulla da installare

        n_tracks = len(track_ids) - len(skip_tids)
        proceed = messagebox.askyesno(
            self.t('confirm_install_title'),
            self.t('confirm_install_body', n_tracks=n_tracks, n_data=len(data_files),
                   trackdata_dir=trackdata_dir, n_wdef=len(wdef_files), trackdefs_dir=trackdefs_dir),
        )
        if not proceed:
            return

        try:
            # la copia (con rollback dei soli file nuovi se fallisce a meta')
            # vive in boxvr_install.install_files, dove e' verificabile senza
            # aprire una finestra - vedi il docstring di quel modulo
            n_copied = boxvr_install.install_files(
                self.last_output_folder, data_files, wdef_files, trackdata_dir, trackdefs_dir)
        except OSError as e:
            messagebox.showerror(self.t('app_title'), self.t('install_error', msg=str(e)))
            return

        self._log(self.t('install_done', n=n_copied))
        messagebox.showinfo(self.t('app_title'), self.t('install_done', n=n_copied))
        self._maybe_create_playlist(wdef_files)

    def _track_id_of(self, fname, suffixes):
        return boxvr_install.track_id_of(fname, suffixes)

    def _track_display_name(self, tid):
        return boxvr_install.track_display_name(self.last_output_folder, tid)

    def _ask_overwrite_selection(self, conflicts):
        """Dialog con una checkbox per brano in conflitto (non per singolo file: chi
        installa ragiona per canzone, non per estensione) - ritorna l'insieme dei
        track id da NON installare (deselezionati), o None se l'utente ha annullato
        l'intera operazione."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(self.t('overwrite_dialog_title'))
        dialog.geometry("480x440")
        dialog.configure(fg_color=BG)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        ctk.CTkLabel(dialog, text=self.t('overwrite_dialog_intro', n=len(conflicts)), font=ui_font(12),
                     text_color=TEXT, wraplength=440, justify="left").pack(padx=16, pady=(16, 8), anchor="w")

        list_frame = ctk.CTkScrollableFrame(dialog, fg_color=CARD)
        list_frame.pack(fill="both", expand=True, padx=16, pady=8)
        _apply_auto_scrollbar(list_frame)

        vars_by_tid = {}
        for c in conflicts:
            var = tk.BooleanVar(value=True)
            ctk.CTkCheckBox(list_frame, text=_truncate(c['name'], 44), variable=var,
                             font=ui_font(11), text_color=TEXT).pack(anchor="w", pady=3, padx=4)
            vars_by_tid[c['tid']] = var

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkButton(btn_row, text=self.t('select_all_btn'), height=30, fg_color=CARD3, hover_color=CARD_HOVER,
                      text_color=TEXT, command=lambda: [v.set(True) for v in vars_by_tid.values()]).pack(side="left")
        ctk.CTkButton(btn_row, text=self.t('select_none_btn'), height=30, fg_color=CARD3, hover_color=CARD_HOVER,
                      text_color=TEXT, command=lambda: [v.set(False) for v in vars_by_tid.values()]
                      ).pack(side="left", padx=(8, 0))

        result = {'cancelled': True, 'skip': set()}

        def on_confirm():
            result['cancelled'] = False
            result['skip'] = {tid for tid, v in vars_by_tid.items() if not v.get()}
            dialog.destroy()

        action_row = ctk.CTkFrame(dialog, fg_color="transparent")
        action_row.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(action_row, text=self.t('cancel_btn'), height=36, fg_color=CARD2, hover_color=CARD3,
                      text_color=TEXT, command=dialog.destroy).pack(side="right")
        ctk.CTkButton(action_row, text=self.t('confirm_overwrite_btn'), height=36, fg_color=ACTION_ACCENT,
                      hover_color=ACTION_ACCENT_HOVER, text_color="white", command=on_confirm
                      ).pack(side="right", padx=(0, 8))

        dialog.wait_window()
        return None if result['cancelled'] else result['skip']

    def _ask_engine_choice(self, n_auto):
        """Dialog mostrato prima di una generazione batch quando almeno un brano ha
        ancora engine_mode='auto' (scelta lasciata al pre-check, non forzata a mano
        dall'utente - vedi _on_beat_engine_toggle). 3 pulsanti, non una checkbox per
        brano come _ask_overwrite_selection: qui la scelta e' UNA politica per
        l'intera generazione (consigliati per-brano / tutti madmom / tutti librosa),
        non una lista di brani da includere o meno. None se annullato (chiude senza
        scegliere) - _start_processing deve allora NON avviare nulla."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(self.t('engine_choice_title'))
        dialog.geometry("460x300")
        dialog.configure(fg_color=BG)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        ctk.CTkLabel(dialog, text=self.t('engine_choice_intro', n=n_auto), font=ui_font(12),
                     text_color=TEXT, wraplength=420, justify="left").pack(padx=16, pady=(16, 12), anchor="w")

        result = {'choice': None}

        def choose(c):
            result['choice'] = c
            dialog.destroy()

        btn_col = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_col.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkButton(btn_col, text=self.t('engine_choice_recommended'), height=42, corner_radius=20,
                      fg_color=ACTION_ACCENT, hover_color=ACTION_ACCENT_HOVER, text_color="white",
                      font=ui_font(12, "semibold"), command=lambda: choose('recommended')).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(btn_col, text=self.t('engine_choice_madmom'), height=38, corner_radius=20,
                      fg_color=CARD2, hover_color=CARD3, text_color=TEXT, font=ui_font(12),
                      command=lambda: choose('madmom')).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(btn_col, text=self.t('engine_choice_librosa'), height=38, corner_radius=20,
                      fg_color=CARD2, hover_color=CARD3, text_color=TEXT, font=ui_font(12),
                      command=lambda: choose('librosa')).pack(fill="x")

        action_row = ctk.CTkFrame(dialog, fg_color="transparent")
        action_row.pack(fill="x", padx=16, pady=(8, 16))
        ctk.CTkButton(action_row, text=self.t('cancel_btn'), height=32, corner_radius=16,
                      fg_color="transparent", hover_color=CARD2, text_color=SUBTEXT,
                      border_width=1, border_color=BORDER, command=dialog.destroy).pack(side="right")

        dialog.wait_window()
        return result['choice']

    def _maybe_create_playlist(self, wdef_files):
        """Chiede se creare/aggiornare una playlist di allenamento con i brani appena
        installati - schema scoperto ispezionando i file .workoutplaylist.txt reali
        di BoxVR su questo PC (Playlists/WorkoutPlaylists/BoxVR/*.workoutplaylist.txt):
        {"definition": {..., "duration": <somma secondi>}, "songs": [{"trackDataName":
        "<hash>", "serialisedActionList": {"actionList": []}}, ...]}."""
        if not wdef_files:
            return
        if not messagebox.askyesno(self.t('app_title'), self.t('ask_create_playlist')):
            return
        name = simpledialog.askstring(
            self.t('app_title'), self.t('ask_playlist_name'), initialvalue=self.t('default_playlist_name'),
        )
        if not name or not name.strip():
            return
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name.strip())
        track_ids = [f[:-len('.wdef.txt')] for f in wdef_files]
        playlists_dir = self._boxvr_playlists_dir()
        playlist_path = os.path.join(playlists_dir, f"{safe_name}.workoutplaylist.txt")

        # riusa la coreografia GIA' VERA scritta a fine generazione
        # (self.last_playlist_path), invece di ricostruirla da capo cercando
        # .actionlist.json - stesso dato, due percorsi diversi per arrivarci
        # sono un modo comodo per farli divergere in silenzio. Vuoto per la
        # modalita' Correggi, che non scrive playlist in generazione: li'
        # add_to_playlist ripiega correttamente su actionList vuota.
        action_lists = boxvr_install.action_lists_from_playlist(self.last_playlist_path)

        try:
            boxvr_install.add_to_playlist(playlist_path, track_ids, safe_name,
                                          self.last_output_folder, action_lists=action_lists)
        except OSError as e:
            messagebox.showerror(self.t('app_title'), self.t('install_error', msg=str(e)))
            return

        self._log(self.t('playlist_done', name=safe_name, n=len(track_ids)))
        messagebox.showinfo(self.t('app_title'), self.t('playlist_done', name=safe_name, n=len(track_ids)))

    # -- log --------------------------------------------------------------

    def _log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        # process_songs_with_presets/generate_songs prefissano ogni riga di
        # avanzamento con "[i/n]" - se lo riconosciamo, e' la percentuale reale da
        # mostrare nella barra. Fra una riga [i/n] e la prossima pero' la barra
        # in modalita' determinate resterebbe ferma per l'intera elaborazione
        # di UN brano - invisibile su un batch di tanti brani brevi, ma un
        # difetto reale segnalato (30/08) su un brano singolo molto lungo
        # (Master of Puppets, ~8 minuti, analisi pesante): "come se non avesse
        # idea del progresso". Si passa a un'animazione indeterminata MENTRE
        # un brano e' in lavorazione, e si torna a un valore determinate reale
        # appena arriva la prossima riga [i/n] - il meglio dei due mondi senza
        # dover instradare un vero callback di progresso dentro ogni fase
        # dell'analisi di un singolo brano.
        m = re.match(r"\[(\d+)/(\d+)\]", message)
        if m:
            i, n = int(m.group(1)), int(m.group(2))
            if n > 0:
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self.progress.set(min(1.0, i / n))
                if i < n:
                    self.progress.configure(mode="indeterminate")
                    self.progress.start()

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def close(self):
        if self.player is not None:
            self.player.close()

    def refresh_theme(self):
        """Ricolora i tk.Canvas grezzi del pannello (timeline + ogni riga) dopo un
        cambio tema chiaro/scuro - i widget CTk circostanti si aggiornano da soli
        tramite ctk.set_appearance_mode, questi no. I pallini di legenda non
        servono piu' qui: sono immagini PIL con canale alpha (vedi
        _render_dot_image), non seguono/non serve seguano lo sfondo per tema."""
        self.canvas.configure(bg=resolve_color(TIMELINE_BG))
        if self.canvas_original is not None:
            self.canvas_original.configure(bg=resolve_color(TIMELINE_BG))
        self._recolor_shadow_layers()
        self._render_timeline()
        for row in self.song_rows.values():
            row.refresh_theme()


# -- le due modalita' dell'applicazione ------------------------------------
#
# Correzione e generazione richiedono ormai STATI OPPOSTI del gioco: la
# correzione agisce su _energyLevel, che ha effetto solo con il gioco NON
# patchato; la generazione scrive coreografie, che hanno effetto solo con il
# gioco patchato. Tenerle nella stessa finestra costringerebbe l'interfaccia a
# contraddirsi (una meta' chiede una condizione, l'altra il suo contrario).
#
# Sono quindi due strumenti distinti, ma UN SOLO sorgente: condividono
# timeline, riproduttore, anteprima e temi, e duplicarli sarebbe peso morto.
# La modalita' si sceglie all'avvio (argomento --mode, o il nome dell'exe) e
# decide quale scheda esiste e se serve la patch.
APP_MODE_FIX = 'fix'
APP_MODE_MAKE = 'make'


class BoxVRFixerApp:
    def __init__(self, root, app_mode=None):
        self.root = root
        self.app_mode = app_mode
        self.settings = load_settings()
        self.lang = self.settings.get('lang', 'it')
        self.theme = self.settings.get('theme', 'dark')
        ctk.set_appearance_mode(self.theme)  # prima di costruire la UI, cosi' ogni
        # widget CTk nasce gia' con i colori del tema giusto invece di doverli
        # ricalcolare subito dopo.
        self.root.configure(bg=resolve_color(BG))
        if app_mode is None:
            # Un solo eseguibile, non piu' due: all'avvio si chiede cosa fare
            # invece di dedurlo dal nome del file (fragile - un utente rinomina
            # o copia il file senza pensarci) o da un argomento a riga di
            # comando (che un collegamento perderebbe). --mode= resta un
            # bypass valido per test/script, vedi _resolve_app_mode.
            self.root.title("BoxVR Level Fixer")
            self._build_mode_chooser()
        else:
            self._start_app(app_mode)

    def _build_mode_chooser(self):
        """Schermata di ingresso: l'utente sceglie cosa fare invece che il tool
        lo indovini. Costruita direttamente su self.root, che a questo punto
        non ha ancora nessun altro widget - _pick_mode la ripulisce del tutto
        prima di costruire l'app vera nella modalita' scelta."""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w, win_h = min(880, screen_w - 100), min(560, screen_h - 100)
        pos_x = max(0, (screen_w - win_w) // 2)
        pos_y = max(0, (screen_h - win_h) // 2)
        self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.root.minsize(680, 460)

        wrap = ctk.CTkFrame(self.root, fg_color=BG, bg_color=BG)
        wrap.pack(fill="both", expand=True)

        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(pady=(34, 22))
        ctk.CTkLabel(head, text="BoxVR Level Fixer", font=ui_font(23, "bold"),
                     text_color=TEXT).pack()
        ctk.CTkLabel(head, text=self.t('chooser_subtitle'), font=ui_font(13),
                     text_color=SUBTEXT).pack(pady=(4, 0))

        cards_row = ctk.CTkFrame(wrap, fg_color="transparent")
        cards_row.pack(fill="both", expand=True, padx=32, pady=(0, 32))
        cards_row.grid_columnconfigure(0, weight=1)
        cards_row.grid_columnconfigure(1, weight=1)
        cards_row.grid_rowconfigure(0, weight=1)

        # Correggere ha effetto SOLO a gioco non patchato: con la patch attiva
        # il generatore procedurale e' scavalcato, quindi i livelli corretti
        # non verrebbero mai letti e l'utente lavorerebbe a vuoto senza alcun
        # segnale. E' lo specchio esatto del blocco gia' presente in modalita'
        # genera (vedi _set_ui_locked) - senza, restava scoperto proprio il
        # caso opposto. Si blocca solo su STATE_PATCHED certo: se lo stato non
        # e' determinabile (percorso del gioco non ancora scelto, file
        # mancante) meglio lasciar passare che sbarrare la strada per un dubbio.
        patched = boxvr_patch.state(self.settings.get('game_dir')) == boxvr_patch.STATE_PATCHED

        self._build_mode_card(cards_row, col=0, mode=APP_MODE_FIX, icon="🛠️", accent=ACCENT,
                              title_key='chooser_fix_title', desc_key='chooser_fix_desc',
                              cta_key='chooser_fix_cta', disabled=patched,
                              disabled_note_key='chooser_fix_patched_note',
                              disabled_action_key='chooser_fix_patched_action')
        self._build_mode_card(cards_row, col=1, mode=APP_MODE_MAKE, icon="🥊", accent=ACTION_ACCENT,
                              title_key='chooser_make_title', desc_key='chooser_make_desc',
                              cta_key='chooser_make_cta')

    def _build_mode_card(self, parent, col, mode, icon, accent, title_key, desc_key, cta_key,
                          disabled=False, disabled_note_key=None, disabled_action_key=None):
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=20, border_width=1, border_color=BORDER)
        card.grid(row=0, column=col, sticky="nsew", padx=10)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=24, pady=24)

        ctk.CTkLabel(inner, text="", image=_render_emoji_icon(icon, 34), width=44, height=44).pack(anchor="w")
        ctk.CTkLabel(inner, text=self.t(title_key), font=ui_font(16, "semibold"), text_color=TEXT,
                     anchor="w", justify="left").pack(anchor="w", pady=(14, 6), fill="x")
        ctk.CTkLabel(inner, text=self.t(desc_key), font=ui_font(12), text_color=SUBTEXT,
                     anchor="w", justify="left", wraplength=280).pack(anchor="w", fill="x")

        if disabled:
            # Stato disabilitato (design Figma "Tile mode"): pulsante spento con
            # lucchetto e, sotto, il motivo PIU' l'azione per uscirne - dire
            # solo "non puoi" lascerebbe l'utente in un vicolo cieco.
            note_row = ctk.CTkFrame(inner, fg_color="transparent")
            note_row.pack(side="bottom", fill="x", pady=(8, 0))
            ctk.CTkLabel(note_row, text="", image=_render_emoji_icon("⚠️", 13),
                         width=17).pack(side="left")
            ctk.CTkLabel(note_row, text=self.t(disabled_note_key), font=ui_font(11),
                         text_color=WARNING).pack(side="left", padx=(4, 0))
            action = ctk.CTkLabel(note_row, text=self.t(disabled_action_key),
                                   font=ui_font(11, "semibold"), text_color=WARNING, cursor="hand2")
            action.pack(side="left", padx=(4, 0))
            action.bind("<Button-1>", lambda e: self._open_patch_dialog())

            ctk.CTkButton(
                inner, text=f"{self.t(cta_key)}  🔒", command=None, state="disabled",
                corner_radius=18, height=42, fg_color=CARD3, hover_color=CARD3,
                text_color=SUBTEXT, font=ui_font(13, "semibold"),
            ).pack(side="bottom", fill="x", pady=(18, 0))
            return

        ctk.CTkButton(
            inner, text=self.t(cta_key), command=lambda m=mode: self._pick_mode(m),
            corner_radius=18, height=42, fg_color=accent, hover_color=accent,
            text_color="white", font=ui_font(13, "semibold"),
        ).pack(side="bottom", fill="x", pady=(18, 0))

    def _rebuild_mode_chooser(self):
        """Ridisegna la schermata di scelta dopo che lo stato della patch e'
        cambiato (la card "Correggi" dipende da quello). Stesso ritardo di
        _pick_mode e per lo stesso motivo: le animazioni interne dei CTkButton
        sopravvivono al click e non devono trovarsi i widget gia' distrutti."""
        def _redraw():
            for w in self.root.winfo_children():
                w.destroy()
            self._build_mode_chooser()
        self.root.after(150, _redraw)

    def _pick_mode(self, mode):
        # CTkButton pianifica animazioni interne (hover/click) con il proprio
        # .after(), che sopravvivono al singolo click - distruggere subito i
        # widget della schermata le lascia puntare a un oggetto Tk gia'
        # sparito ("invalid command name"). Un piccolo ritardo le lascia
        # esaurire prima di ripulire la schermata.
        self.root.after(150, lambda: self._finish_pick_mode(mode))

    def _finish_pick_mode(self, mode):
        for w in self.root.winfo_children():
            w.destroy()
        self._start_app(mode)

    def _start_app(self, app_mode):
        """Costruisce l'app vera e propria nella modalita' scelta - o passata
        direttamente (--mode=), o scelta dalla schermata di ingresso, che a
        questo punto ha gia' ripulito i propri widget da self.root."""
        self.app_mode = app_mode
        self.root.title(f"BoxVR Level Fixer v{VERSION}")
        # Layout ora a due colonne affiancate (non piu' tutto impilato in verticale):
        # la finestra e' diventata piu' larga e molto meno alta di prima, dato che
        # l'elenco brani e l'anteprima non si sommano piu' l'uno sopra l'altro.
        #
        # Dimensione FISSA "1900x900" (non piu' usata) apriva la finestra piu'
        # grande dello schermo utile su schermi piu' piccoli o con scaling
        # Windows elevato, e Windows la piazzava/ridimensionava in modi che
        # tagliavano fuori parte del contenuto (segnalato dall'utente: la
        # scheda "Correggi esistenti" restava in parte nascosta all'avvio,
        # visibile solo ridimensionando a mano). Ora la dimensione si calcola
        # dallo schermo REALE disponibile (winfo_screenwidth/height, gia'
        # al netto della taskbar), con un margine di rispetto, e la finestra
        # viene centrata esplicitamente - mai piu' grande dello schermo, mai
        # posizionata a caso da Windows.
        # win_h: niente piu' un tetto fisso a 900 - con l'header/legenda/icone
        # aggiunte nell'audit visivo il contenuto della scheda e' cresciuto
        # in altezza, e un tetto arbitrario piu' basso di quanto lo schermo
        # permetta davvero forzava lo scroll verticale ad attivarsi anche
        # quando c'era spazio libero sotto (segnalato dall'utente). Il calcolo
        # manuale screen_h-70 pero' lasciava comunque un margine a vuoto che
        # bastava a nascondere la sezione log/avvia-correzione in fondo alla
        # colonna destra (di nuovo scroll necessario per vederla, segnalato
        # dall'utente con uno screenshot). Tentato root.state('zoomed') per usare
        # la vera "area di lavoro" di Windows invece di un numero indovinato - ma
        # su questa macchina si e' rivelato INAFFIDABILE: su un avvio ha prodotto
        # una finestra 3458x1398 con origine a coordinate NEGATIVE (-9,-9), ben
        # oltre i confini di un singolo schermo (probabile bug di Windows nel
        # massimizzare una finestra Tk non-DPI-aware quando .geometry() e' stata
        # appena chiamata e la finestra non e' ancora stata mappata/idle - la
        # richiesta di zoom parte da uno stato di layout non ancora assestato).
        # Tornati alla geometria calcolata a mano: meno "perfetta" ma deterministica
        # e verificata stabile su piu' avvii consecutivi in questa sessione.
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w = min(1900, screen_w - 80)
        win_h = screen_h - 70
        pos_x = max(0, (screen_w - win_w) // 2)
        pos_y = max(0, (screen_h - win_h) // 2)
        self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self.root.minsize(min(1780, win_w), min(760, win_h))
        # maxsize = lo schermo reale: rete di sicurezza contro un bug di
        # contenuto scoperto in questa sessione (un CTkScrollableFrame interno
        # ha richiesto per errore >2000px di larghezza, e root - propagate
        # abilitato di default - si e' riespanso per assecondarlo, arrivando
        # a 3458x1398 con origine a coordinate NEGATIVE, ben oltre un singolo
        # schermo). maxsize fa rispettare un tetto SEMPRE, qualunque cosa
        # richieda il contenuto dopo la costruzione della UI - resta comunque
        # possibile per l'utente ridimensionare/massimizzare a mano fino a
        # tutto lo schermo, solo non oltre.
        self.root.maxsize(screen_w, screen_h)
        # niente self.root.configure(bg=...) qui: e' gia' impostato una volta
        # sola alla creazione di root (in main()), e richiamarlo qui - dopo che
        # _finish_pick_mode ha distrutto gli widget della schermata di scelta -
        # fa scattare l'appearance tracker globale di customtkinter, che itera
        # anche i CTkFrame gia' distrutti e solleva
        # "_tkinter.TclError: invalid command name '.!ctkframe'".
        self.current_tab = 'correct' if app_mode == APP_MODE_FIX else 'generate'

        self._egg_clicks = 0
        self._egg_after_id = None

        self._build_ui()

        # geometry() qui sopra viene chiamata PRIMA che il contenuto esista -
        # root ha propagate abilitato di default, quindi se un widget dentro
        # _build_ui() richiede una larghezza innaturale (bug a parte, capitato
        # con un CTkScrollableFrame interno che ha richiesto >2000px), root può
        # riespandersi per farcelo stare, scavalcando la dimensione centrata
        # scelta sopra (osservato concretamente: finestra finita a 3458x1398,
        # con origine a coordinate NEGATIVE, ben oltre i confini upplicati per
        # arrotondare). Riapplicarla QUI, a contenuto gia' costruito, la
        # riporta con forza alla dimensione voluta indipendentemente da
        # qualunque richiesta di spazio dei figli.
        self.root.update_idletasks()
        self.root.geometry(f"{win_w}x{win_h}+{pos_x}+{pos_y}")
        self._apply_language()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if app_mode == APP_MODE_MAKE:
            # Dopo che la finestra esiste gia', altrimenti il dialogo
            # comparirebbe da solo su uno schermo ancora vuoto.
            self.root.after(200, self._prompt_game_dir_if_needed)

    def t(self, key, **kwargs):
        text = STRINGS[self.lang][key]
        return text.format(**kwargs) if kwargs else text

    def _build_ui(self):
        pad = 16
        # bg_color=BG esplicito (non solo fg_color): bg_color e' cio' con cui CTk
        # fonde gli angoli arrotondati del widget (l'esterno), fg_color e' il suo
        # riempimento (l'interno) - qui sono uguali dato che il frame sta a diretto
        # contatto con lo sfondo della finestra. Senza bg_color esplicito, un
        # CTkFrame figlio diretto della root (un tk.Tk puro, non un widget CTk)
        # lo rileva UNA SOLA VOLTA leggendo root.cget("bg") al momento della
        # creazione e non lo aggiorna mai piu' quando cambia il tema - risultato:
        # angoli smussati rimasti del colore di quando l'app e' partita, in
        # contrasto con tutto il resto che si ricolora correttamente.
        header_row = ctk.CTkFrame(self.root, fg_color=BG, bg_color=BG)
        header_row.pack(fill="x", padx=pad, pady=(pad, 0))
        header = ctk.CTkLabel(header_row, text="BoxVR Level Fixer", font=ui_font(24, "semibold"),
                               text_color=TEXT, anchor="w", cursor="hand2")
        header.pack(side="left")
        header.bind("<Button-1>", self._on_header_click)

        version_label = ctk.CTkLabel(header_row, text=f"v{VERSION}", font=ui_font(10), text_color=SUBTEXT, anchor="w")
        version_label.pack(side="left", padx=(8, 0), pady=(10, 0))

        # Tab "Correggi esistenti"/"Genera da MP3" spostate nell'header accanto al
        # titolo (invece di una riga a se stante) per recuperare spazio verticale;
        # stile "sottolineatura" deliberatamente diverso dai pulsanti a pillola
        # pieni usati altrove, cosi' si riconoscono a colpo d'occhio come tab di
        # navigazione e non come azioni.
        # Un solo strumento per modalita': niente selettore di schede da
        # mostrare quando la scheda e' una sola.
        self._tab_keys = ('correct',) if self.app_mode == APP_MODE_FIX else ('generate',)
        self.tabs_frame = ctk.CTkFrame(header_row, fg_color="transparent")
        if len(self._tab_keys) > 1:
            self.tabs_frame.pack(side="left", padx=(20, 0))
        self.tab_labels = {}
        self.tab_underlines = {}
        for key in self._tab_keys:
            col = ctk.CTkFrame(self.tabs_frame, fg_color="transparent")
            col.pack(side="left", padx=10)
            lbl = ctk.CTkLabel(col, font=ui_font(13, "semibold"), cursor="hand2")
            lbl.pack(pady=(6, 2))
            underline = ctk.CTkFrame(col, height=3, corner_radius=2, fg_color="transparent")
            underline.pack(fill="x")
            lbl.bind("<Button-1>", lambda e, k=key: self._switch_tab(k))
            self.tab_labels[key] = lbl
            self.tab_underlines[key] = underline

        # Niente frame arrotondato "contenitore" attorno ai due bottoni: un CTkFrame
        # arrotondato con dentro dei CTkButton anch'essi arrotondati produce un
        # artefatto visivo (gli angoli del bounding box rettangolare del bottone
        # figlio sporgono oltre gli angoli arrotondati del frame genitore). Due
        # pillole indipendenti, affiancate con un piccolo distacco, evitano del
        # tutto il problema.
        # Toggle tema chiaro/scuro: un vero CTkSwitch (non un bottone con
        # un'emoji che cambia) affiancato dalle due icone di stato, sullo stesso
        # stile di ogni altro switch on/off dell'app (es. dry_run_switch).
        # Prima erano 5 elementi sciolti affiancati direttamente su header_row
        # (bandiera, bandiera, luna, switch, sole) - a colpo d'occhio si
        # leggevano come controlli scollegati tra loro invece che un unico
        # gruppo "impostazioni", il tipico effetto "poco curato" segnalato
        # nell'audit visivo (confrontato con le reference Dribbble fornite:
        # anche li' i controlli imparentati vivono sempre dentro un unico
        # contenitore riconoscibile, mai sparsi). Ora e' un'unica pillola-card
        # (stesso fg_color/raggio delle altre card, coerenza cromatica) che li
        # contiene tutti, con un separatore verticale sottile a marcare i due
        # sotto-gruppi (lingua | tema) invece di un padding indistinguibile
        # da quello usato ovunque altrove nell'header.
        controls_card = ctk.CTkFrame(header_row, fg_color=CARD, corner_radius=18)
        controls_card.pack(side="right", padx=(6, 0), pady=(4, 0))

        _LANG_FLAGS = {'en': 'gb', 'it': 'it'}
        self.lang_buttons = {}
        for code in ('it', 'en'):
            btn = ctk.CTkButton(
                controls_card, text="", image=_render_flag_icon(_LANG_FLAGS[code], 20),
                command=lambda c=code: self._set_language(c),
                corner_radius=13, width=38, height=30,
            )
            btn.pack(side="left", padx=(8 if code == 'it' else 3, 3), pady=6)
            self.lang_buttons[code] = btn

        ctk.CTkFrame(controls_card, width=1, height=22, fg_color=BORDER).pack(side="left", padx=(5, 7), pady=6)

        ctk.CTkLabel(controls_card, text="", image=_render_emoji_icon("🌙", 14), width=16).pack(side="left", padx=(0, 3))
        self.theme_switch = ctk.CTkSwitch(
            controls_card, text="", command=self._on_theme_switch, width=38, height=20,
            progress_color=ACCENT, button_color=TEXT, button_hover_color=TEXT, fg_color=CARD3,
        )
        self.theme_switch.pack(side="left")
        ctk.CTkLabel(controls_card, text="", image=_render_emoji_icon("☀️", 14), width=16).pack(side="left", padx=(3, 8))
        if self.theme == 'light':
            self.theme_switch.select()
        else:
            self.theme_switch.deselect()

        # Stato della patch al gioco, accanto agli altri controlli globali.
        # Sta nell'header e non dentro una scheda perche' non riguarda un brano
        # o una modalita': e' una condizione dell'installazione, e sapere se e'
        # attiva o meno cambia il significato di tutto cio' che il tool produce
        # (senza patch le coreografie vengono ignorate in silenzio).
        # Solo nello strumento di generazione: la correzione funziona (anzi,
        # funziona SOLO) con il gioco non patchato, quindi li' il pulsante
        # sarebbe fuorviante.
        self.patch_btn = None
        if self.app_mode == APP_MODE_MAKE:
            ctk.CTkFrame(controls_card, width=1, height=22, fg_color=BORDER).pack(side="left", padx=(3, 7), pady=6)
            self.patch_btn = ctk.CTkButton(
                controls_card, text="", command=self._open_patch_dialog,
                corner_radius=13, height=30, width=104, font=ui_font(11, "medium"),
            )
            self.patch_btn.pack(side="left", padx=(0, 8), pady=6)
            _Tooltip(self.patch_btn, lambda: self.t('patch_tooltip'))

        self.subtitle = ctk.CTkLabel(self.root, bg_color=BG, font=ui_font(12), text_color=SUBTEXT, anchor="w")
        self.subtitle.pack(fill="x", padx=pad, pady=(2, 0))

        # Linea sottile tra header e contenuto: prima l'header "galleggiava"
        # direttamente sullo sfondo senza alcun confine con il resto - le
        # reference separano sempre chiaramente le zone (barra di navigazione
        # / contenuto), anche solo con un filo sottilissimo come questo.
        ctk.CTkFrame(self.root, height=1, fg_color=BORDER, bg_color=BG).pack(fill="x", padx=pad, pady=(pad, 0))

        # fg_color=BG (non "transparent") anche qui, stesso motivo di header_row:
        # essendo figlio diretto della root pura, un fg_color "transparent" non
        # disegna nulla ma il bg_color per la fusione degli angoli arrotondati
        # verrebbe comunque rilevato UNA VOLTA SOLA da root.cget("bg") e restare
        # bloccato la' - dargli lo stesso colore di sfondo esplicito (invece di
        # lasciarlo "indovinare") lo rende immune al problema in entrambe le
        # direzioni del cambio tema, ed e' visivamente identico dato che
        # coincide comunque con lo sfondo della finestra.
        # Banner di blocco: creato ora ma non impacchettato - lo mostra
        # _set_ui_locked solo quando la patch non e' attiva.
        self._app_pad = pad
        self._ui_locked = None
        self.lock_banner = ctk.CTkFrame(self.root, fg_color=WARNING_SOFT, bg_color=BG, corner_radius=14)
        lb_row = ctk.CTkFrame(self.lock_banner, fg_color="transparent")
        lb_row.pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(lb_row, text="", image=_render_emoji_icon("⚠️", 20), width=26).pack(side="left")
        self.lock_banner_label = ctk.CTkLabel(
            lb_row, font=ui_font(12), text_color=TEXT, anchor="w", justify="left", wraplength=760)
        self.lock_banner_label.pack(side="left", padx=(10, 12), fill="x", expand=True)
        self.lock_banner_btn = ctk.CTkButton(
            lb_row, command=self._open_patch_dialog, corner_radius=18, height=36,
            fg_color=ACTION_ACCENT, hover_color=ACTION_ACCENT_HOVER, text_color="white",
            font=ui_font(12, "semibold"))
        self.lock_banner_btn.pack(side="right")

        self.tabs_container = ctk.CTkFrame(self.root, fg_color=BG, bg_color=BG)
        self.tabs_container.pack(fill="both", expand=True, padx=pad, pady=pad)

        # Si costruisce solo il pannello della modalita' attiva: l'altro non
        # servirebbe a nulla e costerebbe comunque un'analisi audio in
        # background e memoria.
        self.correct_panel = self.generate_panel = None
        if 'correct' in self._tab_keys:
            self.correct_panel = SongBrowserPanel(self.tabs_container, self, mode='correct')
            self.correct_panel.pack(fill="both", expand=True)
        if 'generate' in self._tab_keys:
            self.generate_panel = SongBrowserPanel(self.tabs_container, self, mode='generate')
            if self.correct_panel is None:
                self.generate_panel.pack(fill="both", expand=True)

        if not HAS_DND:
            for p in (self.correct_panel, self.generate_panel):
                if p is not None:
                    p._log(self.t('note_no_dnd'))
        if not HAS_AUDIO:
            self.correct_panel._log(self.t('note_no_audio'))
            self.generate_panel._log(self.t('note_no_audio'))

    # -- percorso del gioco e patch -------------------------------------------

    def _refresh_patch_button(self):
        """Il pulsante mostra lo STATO, non un'azione: e' la prima cosa da
        sapere guardando l'header, perche' senza patch le coreografie scritte
        vengono ignorate senza alcun avviso."""
        if self.patch_btn is None:
            return
        st = boxvr_patch.state(self.settings.get('game_dir'))
        look = {
            boxvr_patch.STATE_PATCHED: ('patch_state_on', SUCCESS, SUCCESS),
            boxvr_patch.STATE_ORIGINAL: ('patch_state_off', CARD2, CARD3),
            boxvr_patch.STATE_UNKNOWN: ('patch_state_unknown', CARD2, CARD3),
            boxvr_patch.STATE_MISSING: ('patch_state_missing', CARD2, CARD3),
        }[st]
        key, fg, hover = look
        self.patch_btn.configure(
            text=self.t(key), fg_color=fg, hover_color=hover,
            text_color="white" if st == boxvr_patch.STATE_PATCHED else TEXT,
        )
        self._set_ui_locked(st != boxvr_patch.STATE_PATCHED)
        if st == boxvr_patch.STATE_PATCHED:
            self._check_risky_playlists()

    def _check_risky_playlists(self):
        """Avviso 'playlist a rischio' (26/08, residuo tecnico gia' annotato -
        la funzione playlists_without_choreography esisteva gia', mancava solo
        il collegamento alla GUI). Controllato solo a patch ATTIVA: solo li'
        una coreografia vuota rende davvero un brano muto in gioco - vedi il
        bug reale corretto il 25/08 (boxvr_install.playlists_without_choreography).

        Una volta per sessione (`_risky_playlist_warned`): questa funzione gira
        a ogni cambio di stato della patch (vedi _refresh_patch_button, 4
        punti di chiamata), un messagebox ripetuto ogni volta sarebbe un
        fastidio, non un avviso utile."""
        if getattr(self, '_risky_playlist_warned', False):
            return
        try:
            risky = boxvr_install.playlists_without_choreography()
        except Exception:
            return
        if not risky:
            return
        self._risky_playlist_warned = True
        lines = "\n".join(f"  • {fn} ({n_vuote}/{n_tot})" for fn, n_vuote, n_tot in risky[:8])
        if len(risky) > 8:
            lines += f"\n  … {self.t('risky_playlists_more', n=len(risky) - 8)}"
        messagebox.showwarning(self.t('app_title'), self.t('risky_playlists_msg', list=lines))

    def _set_ui_locked(self, locked):
        """Senza patch il gioco ignora le coreografie SENZA dare alcun segnale:
        un utente vedrebbe il tool lavorare e il risultato non cambiare mai.
        Meglio bloccare tutto e dire perche', invece di lasciar produrre file
        che non avranno effetto."""
        if getattr(self, '_ui_locked', None) == locked:
            return
        self._ui_locked = locked

        def walk(w, disable):
            for child in w.winfo_children():
                try:
                    if isinstance(child, (ctk.CTkButton, ctk.CTkSwitch, ctk.CTkSlider,
                                           ctk.CTkEntry, ctk.CTkCheckBox, ctk.CTkOptionMenu)):
                        child.configure(state="disabled" if disable else "normal")
                except Exception:
                    pass
                walk(child, disable)

        walk(self.tabs_container, locked)
        if locked:
            self.lock_banner.pack(fill="x", padx=self._app_pad, pady=(8, 0), before=self.tabs_container)
        else:
            self.lock_banner.pack_forget()

    def _ask_game_dir(self, initial=None):
        """Selezione manuale della cartella di BoxVR. Il rilevamento automatico
        serve solo a precompilare la proposta: sulle edizioni Oculus/Viveport
        non trova nulla, e li' l'unico che sa dov'e' il gioco e' l'utente."""
        start = initial or self.settings.get('game_dir') or boxvr_patch.autodetect_game_dir() or ""
        chosen = filedialog.askdirectory(title=self.t('game_dir_prompt'), initialdir=start or None)
        if not chosen:
            return None
        chosen = os.path.normpath(chosen)
        if not boxvr_patch.looks_like_game_dir(chosen):
            messagebox.showwarning(self.t('app_title'), self.t('game_dir_invalid'))
            return None
        self.settings['game_dir'] = chosen
        save_settings(self.settings)
        gen_set_game_dir(chosen)
        self._refresh_patch_button()
        return chosen

    def _prompt_game_dir_if_needed(self):
        """Chiesta al primo avvio, e solo allora: una volta salvata la cartella
        non si disturba piu' l'utente ad ogni lancio - si richiede soltanto se
        il percorso salvato non e' piu' valido (gioco spostato o disinstallato)."""
        saved = self.settings.get('game_dir')
        if saved and boxvr_patch.looks_like_game_dir(saved):
            gen_set_game_dir(saved)
            return
        auto = boxvr_patch.autodetect_game_dir()
        if messagebox.askyesno(self.t('app_title'),
                               self.t('game_dir_ask_auto', path=auto) if auto
                               else self.t('game_dir_ask_none')):
            if auto and boxvr_patch.looks_like_game_dir(auto):
                self.settings['game_dir'] = auto
                save_settings(self.settings)
                gen_set_game_dir(auto)
                self._refresh_patch_button()
                return
        self._ask_game_dir(auto)

    def _open_patch_dialog(self):
        game_dir = self.settings.get('game_dir')
        st = boxvr_patch.state(game_dir)
        if st == boxvr_patch.STATE_MISSING:
            if not self._ask_game_dir():
                return
            st = boxvr_patch.state(self.settings.get('game_dir'))
        if st == boxvr_patch.STATE_UNKNOWN:
            messagebox.showwarning(self.t('app_title'), self.t('patch_unknown_msg'))
            return
        if st == boxvr_patch.STATE_PATCHED:
            if messagebox.askyesno(self.t('app_title'), self.t('patch_revert_confirm')):
                ok, msg = boxvr_patch.revert(self.settings.get('game_dir'))
                messagebox.showinfo(self.t('app_title'), msg) if ok else \
                    messagebox.showerror(self.t('app_title'), msg)
        else:
            if messagebox.askyesno(self.t('app_title'), self.t('patch_apply_confirm')):
                ok, msg = boxvr_patch.apply(self.settings.get('game_dir'))
                messagebox.showinfo(self.t('app_title'), msg) if ok else \
                    messagebox.showerror(self.t('app_title'), msg)
        self._refresh_patch_button()
        # Se siamo ancora sulla schermata di scelta (app_mode non deciso), la
        # card "Correggi" era abilitata/disabilitata in base allo stato appena
        # cambiato: va ricostruita, altrimenti resterebbe a mostrare il vecchio.
        if self.app_mode is None:
            self._rebuild_mode_chooser()

    def _set_language(self, code):
        if code == self.lang:
            return
        self.lang = code
        self.settings['lang'] = code
        save_settings(self.settings)
        self._apply_language()

    def _on_theme_switch(self):
        self.theme = 'light' if self.theme_switch.get() else 'dark'
        self.settings['theme'] = self.theme
        save_settings(self.settings)

        # customtkinter chiama update_idletasks() dentro _set_appearance_mode() di
        # OGNI SINGOLO widget (vedi CTkBaseClass._set_appearance_mode nella
        # libreria). Il punto chiave, verificato leggendo tkinter.Misc.update_idletasks:
        # non aggiorna SOLO quel widget - e' un'unica coda di ridisegno "idle"
        # condivisa da tutta l'interfaccia Tcl dell'app, quindi ogni singola
        # chiamata forza un flush REALE sullo schermo di tutto cio' che e' gia'
        # in coda fino a quel momento. Con centinaia di widget (ogni riga ne ha
        # una decina) il tema cambia attraverso centinaia di flush completi in
        # sequenza invece di un unico aggiornamento finale - quello e' l'effetto
        # "a cascata stile vecchia pagina web". Le due versioni precedenti
        # (nascondere con l'alpha, poi coprire con un riquadro a tinta unita)
        # mascheravano il sintomo senza risolverlo. Qui invece si sopprime
        # temporaneamente update_idletasks per l'intera libreria (no-op) per
        # tutta la durata della ricolorazione, e lo si richiama UNA SOLA VOLTA a
        # lavoro finito: nessun flush intermedio arriva mai sullo schermo, il
        # cambio tema diventa un unico aggiornamento realmente atomico invece di
        # un trucco per nasconderne uno a cascata.
        real_update_idletasks = tk.Misc.update_idletasks
        tk.Misc.update_idletasks = lambda self_widget: None
        try:
            ctk.set_appearance_mode(self.theme)
            self.root.configure(bg=resolve_color(BG))
            # Ricolora subito e per intero SOLO il pannello visibile (timeline,
            # righe, sparkline...) - ricolorare anche il pannello dell'altra tab
            # nello stesso istante e' lavoro sprecato (non e' a schermo). Il
            # pannello nascosto viene ricolorato pigramente, un attimo prima di
            # essere effettivamente mostrato (vedi _switch_tab).
            active_panel = self.correct_panel if self.current_tab == 'correct' else self.generate_panel
            stale_panel = self.generate_panel if self.current_tab == 'correct' else self.correct_panel
            active_panel.refresh_theme()
            stale_panel.theme_stale = True
        finally:
            # SEMPRE ripristinato, anche se qualcosa solleva un'eccezione -
            # altrimenti update_idletasks resterebbe rotto per il resto della
            # sessione, non solo per questo cambio tema.
            tk.Misc.update_idletasks = real_update_idletasks
            real_update_idletasks(self.root)

    def _switch_tab(self, key):
        if key == self.current_tab:
            return
        self.current_tab = key
        for k, lbl in self.tab_labels.items():
            active = k == key
            lbl.configure(text_color=TEXT if active else SUBTEXT)
            self.tab_underlines[k].configure(fg_color=ACCENT if active else "transparent")
        if key == 'correct':
            self.generate_panel.pack_forget()
            self.correct_panel.pack(fill="both", expand=True)
            if getattr(self.correct_panel, 'theme_stale', False):
                self.correct_panel.refresh_theme()
                self.correct_panel.theme_stale = False
        else:
            self.correct_panel.pack_forget()
            self.generate_panel.pack(fill="both", expand=True)
            if getattr(self.generate_panel, 'theme_stale', False):
                self.generate_panel.refresh_theme()
                self.generate_panel.theme_stale = False

    def _apply_language(self):
        for code, btn in self.lang_buttons.items():
            active = code == self.lang
            btn.configure(fg_color=ACCENT if active else "transparent", text_color="white" if active else SUBTEXT)
        self.subtitle.configure(text=self.t('app_subtitle'))

        for k, lbl in self.tab_labels.items():
            lbl.configure(text=self.t('tab_correct' if k == 'correct' else 'tab_generate'))
            active = k == self.current_tab
            lbl.configure(text_color=TEXT if active else SUBTEXT)
            self.tab_underlines[k].configure(fg_color=ACCENT if active else "transparent")

        for p in (self.correct_panel, self.generate_panel):
            if p is not None:
                p.apply_language()
        if self.patch_btn is not None:
            self.lock_banner_label.configure(text=self.t('lock_banner_text'))
            self.lock_banner_btn.configure(text=self.t('lock_banner_btn'))
            self._refresh_patch_button()

    def _on_header_click(self, event=None):
        self._egg_clicks += 1
        if self._egg_after_id:
            self.root.after_cancel(self._egg_after_id)
        self._egg_after_id = self.root.after(1200, self._reset_egg)
        if self._egg_clicks >= 5:
            self._egg_clicks = 0
            self.root.after_cancel(self._egg_after_id)
            self._egg_after_id = None
            self._trigger_easter_egg()

    def _reset_egg(self):
        self._egg_clicks = 0
        self._egg_after_id = None

    def _trigger_easter_egg(self):
        messagebox.showinfo(
            "👞👞👞🦵",
            "TRE UOMINI E UNA GAMBA\n\n"
            "Hai trovato l'easter egg. Come nel film: qui non si butta via "
            "niente, nemmeno un segmento di canzone - nessun buco, promesso.",
        )

    def _on_close(self):
        """Chiude la finestra. Verificato dal vivo il 25/08 (processo reale
        bloccato, WM_CLOSE inviato via Win32 e ignorato, nessun errore in
        nessun log): un try/except da solo NON basta, perche' protegge da un
        errore SOLLEVATO ma non da una chiamata che si BLOCCA senza sollevare
        nulla - e SongPlayer.close() chiama sounddevice/PortAudio
        (stream.stop()/close()), che su Windows puo' bloccarsi in certe
        condizioni. Se l'utente aveva ascoltato un'anteprima in quella
        sessione, e' un candidato concreto.

        Due livelli di protezione, non uno solo:
        1. Ogni passaggio gira in un thread A SE', con un tempo massimo
           d'attesa - se si blocca, si prosegue comunque (il thread resta
           appeso in background, ma e' un thread daemon: non impedisce
           all'app di chiudersi).
        2. Un timer di sicurezza forza la chiusura DAVVERO (`os._exit`) pochi
           secondi dopo, nel caso anche `root.destroy()` non bastasse a far
           terminare l'interprete per qualche motivo non ancora capito -
           l'utente ha chiesto di chiudere, non deve poter restare bloccato
           per nessun motivo."""
        import threading as _threading

        def _run_bounded(fn, timeout=1.5):
            t = _threading.Thread(target=fn, daemon=True)
            t.start()
            t.join(timeout)

        def _step_settings():
            try:
                save_settings(self.settings)
            except Exception:
                pass

        def _step_correct():
            try:
                self.correct_panel.close()
            except Exception:
                pass

        def _step_generate():
            try:
                self.generate_panel.close()
            except Exception:
                pass

        # rete di sicurezza finale: se il processo e' ancora vivo fra 4
        # secondi, qualcosa ha impedito la chiusura normale - forzarla.
        _threading.Timer(4.0, lambda: os._exit(0)).start()

        for step in (_step_settings, _step_correct, _step_generate):
            _run_bounded(step)
        self.root.destroy()


def _crash_log_path():
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'boxvr_fixer_gui_crash.log')


def _resolve_app_mode(argv=None):
    """Un solo eseguibile ora, non piu' due: la modalita' normalmente la
    sceglie l'utente dalla schermata di ingresso (vedi
    BoxVRFixerApp._build_mode_chooser), non si deduce piu' dal nome del file.
    --mode= resta come scorciatoia per test/script, per saltare la schermata
    quando non serve interazione. Ritorna None se non specificato: e' il
    segnale per BoxVRFixerApp di mostrare la schermata di scelta."""
    argv = argv if argv is not None else sys.argv[1:]
    for a in argv:
        if a.startswith('--mode='):
            v = a.split('=', 1)[1].strip().lower()
            if v in (APP_MODE_FIX, APP_MODE_MAKE):
                return v
    return None


def main():
    mode = _resolve_app_mode()
    root = tk.Tk()
    if HAS_DND:
        try:
            TkinterDnD._require(root)
        except Exception:
            pass
    root.configure(bg=resolve_color(BG))
    BoxVRFixerApp(root, app_mode=mode)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        try:
            with open(_crash_log_path(), 'w', encoding='utf-8') as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise
