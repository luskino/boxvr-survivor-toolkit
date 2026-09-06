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
Anteprima visiva della coreografia - Fase 5 della rotta.
=========================================================
Una finestra che mostra, come un POV del livello, i bersagli che arrivano
verso il giocatore mentre la canzone suona - cosi' si vede A OCCHIO (non solo
a orecchio, che il riscontro di oggi ha mostrato non bastare da solo) se il
posizionamento dei colpi ha senso, senza dover indossare il visore.

GEOMETRIA: BoxVR non ha uno spazio 3D libero, solo sei canali fissi
(FitXR.MusicActions.MoveChannel: Front/Front_Low/Center/Center_Low/Back/
Back_Low - vedi [[boxvr-internals]]). Sono quindi 6 caselle fisse, 3 colonne
per 2 righe (Normale/Basso). Le etichette a schermo (Sinistra/Centro/Destra)
non corrispondono ai nomi reali dei canali (Front/Center/Back) - scelta
esplicita dell'utente, che si aspetta di leggere una griglia di boxe in
quei termini anche se sotto il cofano restano Front/Center/Back.

Ogni bersaglio nasce piccolo verso un punto di fuga in alto al centro e cresce
muovendosi verso la sua casella, arrivando a dimensione piena esattamente
all'istante del colpo (`startTime`) - l'effetto e' "sta arrivando verso di
te", lo stesso principio di un qualunque rhythm game.

Riusa `SongPlayer` di boxvr_fixer_gui.py per la riproduzione audio (stesso
motore a bassa latenza gia' collaudato nel resto del tool) e la stessa
cadenza di aggiornamento (33ms, ~30fps) gia' usata da `_poll_playhead` per il
cursore della timeline.
"""
import itertools
import json
import math
import os
import sys
import tkinter as tk

import numpy as np
import soundfile as sf
from PIL import Image, ImageTk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _icon_base_dir():
    """Cartella da cui leggere data/icons - funziona sia da sorgente sia
    dentro l'eseguibile congelato (PyInstaller estrae i dati in _MEIPASS)."""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


from boxvr_fixer_gui import SongPlayer  # noqa: E402  (riuso deliberato, vedi sopra)
from boxvr_choreo import boxvr_dirs  # noqa: E402  (stessa fonte dei percorsi TrackData/TrackDefinitions/Playlists usata dal resto del tool - niente copie separate qui)

MOVE_JAB, MOVE_HOOK, MOVE_UPPERCUT, MOVE_BLOCK, MOVE_DODGE, MOVE_SQUAT = 101, 102, 103, 100, 104, 105
MOVE_NAMES = {MOVE_BLOCK: 'Block', MOVE_JAB: 'Jab', MOVE_HOOK: 'Hook',
              MOVE_UPPERCUT: 'Uppercut', MOVE_DODGE: 'Dodge', MOVE_SQUAT: 'Squat'}
PUNCH_TYPES = (MOVE_JAB, MOVE_HOOK, MOVE_UPPERCUT)

# canale (int del gioco) -> (colonna 0..2, riga 0..1): vedi il docstring sopra
CHANNEL_CELL = {0: (0, 0), 1: (0, 1), 2: (1, 0), 3: (1, 1), 4: (2, 0), 5: (2, 1)}
# Le ETICHETTE mostrate ("Sinistra"/"Destra") non corrispondono al nome vero
# del canale nei dati (Front/Back, vedi CHANNEL_CELL sopra e [[boxvr-internals]])
# - richiesta esplicita dell'utente, 2026-08-23: sotto il cofano restano
# Front/Center/Back, a schermo si leggono come sinistra/centro/destra perche'
# e' cosi' che si aspetta di vederle disposte chi guarda una griglia di boxe.
COL_LABELS = ("Sinistra", "Centro", "Destra")
ROW_LABELS = ("Normale", "Basso")

# Icone e colori congrui con la grafica del gioco (richiesta esplicita
# dell'utente, 2026-08-23): blu = mano sinistra, fucsia = mano destra, scudo
# rosso per Block, barre arancioni per gli ostacoli (orizzontale = Squat,
# diagonale = Dodge). IMPORTANTE: il formato delle azioni (sia quello scritto
# da boxvr_choreo.py sia quello ufficiale) non registra QUALE mano tira il
# colpo - solo moveType e moveChannel, vedi [[boxvr-internals]]. La mano qui
# e' quindi una CONVENZIONE VISIVA scelta da noi (alternanza sinistra/destra
# in ordine cronologico, vedi load_song), non un dato che il gioco fornisce -
# resta deterministica/ripetibile come tutto il resto della pipeline, ma non
# corrisponde necessariamente a quale mano il gioco mostrera' davvero.
HAND_COLORS = {'L': '#3a86ff', 'R': '#ff2ec4'}
BLOCK_COLOR = '#e6323c'
OBSTACLE_COLOR = '#ff9d3d'
FULL_R = {MOVE_JAB: 22, MOVE_HOOK: 24, MOVE_UPPERCUT: 24, MOVE_BLOCK: 24, MOVE_SQUAT: 30, MOVE_DODGE: 30}

# --- icone vere, disegnate dall'utente ---------------------------------------
# PNG estratti una volta sola dal set Figma "Icone visualizzatore" (vedi
# data/icons/): niente libreria SVG a runtime nell'eseguibile - stessa scelta
# gia' fatta per data/training_sequences.json, e la stessa lezione pagata con
# madmom su una dipendenza nativa fragile.
# Le icone arrivano GIA' colorate per lato (blu = sinistra, rosa = destra),
# quindi non serve piu' tingerle a mano: si sceglie l'asset, non il colore.
# Squat e Dodge restano disegnati a runtime: sono barre la cui lunghezza
# dipende dalla larghezza della griglia a schermo, non asset di misura fissa.
ICON_DIR = os.path.join(_icon_base_dir(), 'data', 'icons')
# Suono d'impatto sovrapposto ai pugni (30/08, richiesto esplicitamente:
# "il suono dei colpi sovrapposto, non troppo forte"). NON e' il suono vero
# di BoxVR - estrarlo dai file del gioco e ridistribuirlo qui sarebbe una
# violazione di copyright (e' un'opera creativa, diverso dai dati di pattern
# di data/training_sequences.json, già usati come solo riferimento
# algoritmico) - vedi assets/sfx/SOURCE.md per la provenienza e la licenza
# del campione libero usato al suo posto.
HIT_SFX_PATH = os.path.join(_icon_base_dir(), 'assets', 'sfx', 'hit_punch.wav')
ICON_FILES = {
    (MOVE_JAB, 'L'): 'jab_sx', (MOVE_JAB, 'R'): 'jab_dx',
    (MOVE_HOOK, 'L'): 'hook_sx', (MOVE_HOOK, 'R'): 'hook_dx',
    (MOVE_UPPERCUT, 'L'): 'uppercut_sx', (MOVE_UPPERCUT, 'R'): 'uppercut_dx',
    (MOVE_BLOCK, None): 'block',
}
_ICON_CACHE = {}          # (nome, lato_px) -> PhotoImage, tenuta viva qui


def hand_for_channel(channel, center_fallback):
    """Quale mano (icona/colore) disegnare per un colpo su questo canale.

    Il formato non registra quale mano tira davvero il colpo (vedi il
    commento su HAND_COLORS) - ma non deve nemmeno essere una scelta
    arbitraria: un'icona "destra" che atterra sulla colonna Sinistra si legge
    come un errore a schermo, esattamente quello che e' stato segnalato il
    2026-08-24 (l'alternanza cronologica pura ci finiva sopra per caso circa
    meta' delle volte). Misurato sul repertorio ufficiale che i pugni
    (Jab/Hook/Uppercut) non usano MAI la colonna Centro (canali 0/1/4/5 soli),
    quindi la colonna decide la mano senza ambiguita' in quel caso reale:
    Sinistra -> 'L', Destra -> 'R'. Il Centro non ha una convenzione reale (i
    pugni non ci atterrano mai nel repertorio ufficiale, ma le figure nostre
    o dati futuri potrebbero) - li' si ripiega su `center_fallback`
    (un itertools.cycle) solo per restare deterministico e variato."""
    col = CHANNEL_CELL.get(channel, (1, 0))[0]
    if col == 0:
        return 'L'
    if col == 2:
        return 'R'
    return next(center_fallback)


def _icon(move_type, hand, size):
    """PhotoImage dell'icona alla dimensione richiesta, con cache.

    La cache serve davvero: un bersaglio cresce avvicinandosi, quindi la stessa
    icona viene richiesta a decine di dimensioni diverse per fotogramma, e
    ridimensionare un PNG ogni volta farebbe crollare il frame rate.
    """
    name = ICON_FILES.get((move_type, hand)) or ICON_FILES.get((move_type, None))
    if not name:
        return None
    size = max(6, int(size))
    key = (name, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    path = os.path.join(ICON_DIR, name + '.png')
    try:
        img = Image.open(path).convert('RGBA').resize((size, size), Image.LANCZOS)
    except Exception:
        return None           # asset mancante: si ripiega sul disegno a mano
    photo = ImageTk.PhotoImage(img)
    _ICON_CACHE[key] = photo
    return photo

BG_COLOR = '#12141a'
GRID_COLOR = '#2a2e3a'
TEXT_COLOR = '#8a8f9c'
RING_COLOR = '#3a4050'
# Colore dedicato ai colpi che vengono da un marker dell'utente (sidecar),
# non dal solo algoritmo - richiesto 27/08: "l'utente non sceglie tipo di
# colpo e corsia" per quei colpi, quindi vale la pena segnalare QUANDO
# l'algoritmo ne sta onorando uno. Ambra: distinto sia dal blu che dal
# magenta gia' usati per le mani (HAND_COLORS), non clashano.
MARKER_FLASH_COLOR = '#ffd60a'

LOOKAHEAD_S = 1.8   # da quanto prima del colpo un bersaglio inizia ad "arrivare"
FLASH_S = 0.12      # durata del lampo di impatto dopo il colpo
MARKER_FLASH_S = 0.35   # piu' lungo del lampo bianco normale - deve essere
# notato mentre si guardano i bersagli in arrivo, non solo il punto colpito


def _draw_glove(canvas, x, y, r, color, tag):
    """Pugno chiuso visto di fronte (come arriva verso il giocatore): tre
    nocche smussate in alto, separate da fessure sottili, sopra un corpo che
    si stringe verso il polso - forma originale ispirata alla reference
    fotografica passata dall'utente (icona stock, non riprodotta: qui e'
    ridisegnata a mano coi soli primitivi del Canvas)."""
    knuckle_r = r * 0.5
    top_y = y - r * 0.32
    for dx in (-r * 0.62, 0.0, r * 0.62):
        canvas.create_oval(x + dx - knuckle_r, top_y - knuckle_r, x + dx + knuckle_r, top_y + knuckle_r,
                            fill=color, outline="", tags=tag)
    body_top = y - r * 0.10
    body_bottom = y + r * 0.85
    canvas.create_rectangle(x - r * 0.92, body_top, x + r * 0.92, body_bottom,
                             fill=color, outline="", tags=tag)
    canvas.create_oval(x - r * 0.92, body_bottom - r * 0.32, x + r * 0.92, body_bottom + r * 0.15,
                        fill=color, outline="", tags=tag)
    # fessure fra le nocche (colore di sfondo, come i vuoti bianchi della reference)
    gap_w = max(1, int(r * 0.14))
    for dx in (-r * 0.31, r * 0.31):
        canvas.create_line(x + dx, top_y - knuckle_r * 0.5, x + dx, y + r * 0.55,
                            fill=BG_COLOR, width=gap_w, capstyle=tk.ROUND, tags=tag)


def _draw_motion_lines(canvas, x, y, r, color, direction, tag):
    """Tre trattini paralleli che si allontanano dal guantone in `direction`
    (dx, dy unitario) - la scia di velocita' di Hook/Uppercut."""
    dx, dy = direction
    for k in range(3):
        off = r * (1.1 + k * 0.45)
        length = r * (0.5 - k * 0.08)
        cx, cy = x + dx * off, y + dy * off
        canvas.create_line(cx - dy * length, cy + dx * length, cx + dy * length, cy - dx * length,
                            fill=color, width=max(2, int(r * 0.18)), capstyle=tk.ROUND, tags=tag)


def _draw_shield(canvas, x, y, r, tag):
    pts = [x, y - r, x + r * 0.85, y - r * 0.45, x + r * 0.7, y + r * 0.6,
           x, y + r * 1.05, x - r * 0.7, y + r * 0.6, x - r * 0.85, y - r * 0.45]
    canvas.create_polygon(pts, fill=BLOCK_COLOR, outline="", tags=tag)


def _draw_obstacle_bar(canvas, x, y, r, length, diagonal, tag):
    """Squat/Dodge non sono un bersaglio in una casella: sono barre che
    attraversano piu' corsie (richiesta esplicita dell'utente, 2026-08-23).
    `length` e' passata da fuori (deriva dalla larghezza della griglia, non
    da r) cosi' la barra si allunga fino a coprire davvero le corsie
    coinvolte, non solo la propria casella - `r` continua a governare solo
    lo spessore, che cresce con l'avvicinamento come tutto il resto."""
    width = max(4, int(r * 0.35))
    dx, dy = (0.707, 0.707) if diagonal else (1.0, 0.0)
    canvas.create_line(x - dx * length, y - dy * length, x + dx * length, y + dy * length,
                        fill=OBSTACLE_COLOR, width=width, capstyle=tk.ROUND, tags=tag)


def _draw_marker(canvas, x, y, r, move_type, hand, tag, obstacle_length=None):
    # Ostacoli: barre disegnate a runtime, non icone (la lunghezza dipende
    # dalla griglia a schermo - vedi _draw_obstacle_bar).
    if move_type == MOVE_SQUAT:
        _draw_obstacle_bar(canvas, x, y, r, obstacle_length or r * 1.8, diagonal=False, tag=tag)
        return
    if move_type == MOVE_DODGE:
        _draw_obstacle_bar(canvas, x, y, r, obstacle_length or r * 1.8, diagonal=True, tag=tag)
        return

    # Colpi: icone vere. La scia direzionale e' gia' dentro il disegno
    # (montante verso l'alto, gancio laterale), quindi non si aggiungono piu'
    # trattini a codice come faceva la versione a primitive.
    photo = _icon(move_type, hand, r * 2.2)
    if photo is not None:
        canvas.create_image(x, y, image=photo, tags=tag)
        return

    # Ripiego se l'asset manca: le vecchie forme a primitive, cosi' l'anteprima
    # resta utilizzabile invece di mostrare il nulla.
    color = HAND_COLORS.get(hand, HAND_COLORS['L'])
    if move_type == MOVE_BLOCK:
        _draw_shield(canvas, x, y, r, tag)
    else:
        _draw_glove(canvas, x, y, r, color, tag)


class ChoreoPreviewCanvas:
    """Disegna la griglia a 6 caselle e i bersagli in arrivo su un tk.Canvas
    gia' esistente. Separata dalla finestra standalone qui sotto apposta,
    cosi' si potra' incorporare nella scheda 'Genera' della GUI principale
    senza doverla riscrivere."""

    def __init__(self, canvas, width, height):
        self.canvas = canvas
        self.width = width
        self.height = height
        self.vanish = (width / 2, height * 0.10)
        # margin_x grande = colonne Sinistra/Destra vicine al bordo = l'occhio
        # deve saltare da un capo all'altro dello schermo per seguire
        # un'alternanza rapida - segnalato dall'utente il 2026-08-24 guardando
        # davvero la finestra ("non si riesce a leggerle in tempo"). 0.30
        # dimezza circa la distanza fra le colonne estreme rispetto a 0.16.
        margin_x = width * 0.30
        col_xs = np.linspace(margin_x, width - margin_x, 3)
        row_ys = (height * 0.52, height * 0.82)
        self.cell_pos = {}
        for ch, (col, row) in CHANNEL_CELL.items():
            self.cell_pos[ch] = (float(col_xs[col]), float(row_ys[row]))
        # larghezza piena della griglia (colonna sinistra -> destra): usata solo
        # da Squat/Dodge, che devono attraversare piu' corsie, non stare in una
        # sola casella come i pugni - vedi _draw_obstacle_bar.
        xs = [x for x, _ in self.cell_pos.values()]
        self.grid_span = max(xs) - min(xs)
        self._draw_static()

    def _draw_static(self):
        self.canvas.delete("static")
        self.canvas.create_rectangle(0, 0, self.width, self.height, fill=BG_COLOR, outline="", tags="static")
        vx, vy = self.vanish
        for ch, (x, y) in self.cell_pos.items():
            self.canvas.create_line(vx, vy, x, y, fill=GRID_COLOR, width=1, tags="static")
        # etichette colonna, lette dalle posizioni gia' calcolate (non ricalcolate)
        seen_cols = {}
        for ch, (col, row) in CHANNEL_CELL.items():
            seen_cols.setdefault(col, self.cell_pos[ch][0])
        for col, x in seen_cols.items():
            self.canvas.create_text(x, self.height * 0.94, text=COL_LABELS[col],
                                     fill=TEXT_COLOR, font=("Segoe UI", 11, "bold"), tags="static")
        # etichette riga (Normale/Basso), a sinistra della prima colonna
        seen_rows = {}
        for ch, (col, row) in CHANNEL_CELL.items():
            seen_rows.setdefault(row, self.cell_pos[ch][1])
        label_x = min(x for x, _ in self.cell_pos.values()) - 70
        for row, y in seen_rows.items():
            self.canvas.create_text(label_x, y, text=ROW_LABELS[row],
                                     fill=TEXT_COLOR, font=("Segoe UI", 10), tags="static")
        for ch, (x, y) in self.cell_pos.items():
            r = 30
            self.canvas.create_oval(x - r, y - r, x + r, y + r, outline=RING_COLOR, width=2, tags="static")

    def render(self, now_t, actions_sorted, start_idx_hint=0):
        """Ridisegna solo i bersagli (tag 'marker'); la griglia statica resta.
        `actions_sorted` deve essere ordinata per startTime - la funzione
        ritorna un indice da cui ripartire la prossima chiamata, cosi' non si
        riscandisce l'intera lista ad ogni frame su brani lunghi."""
        self.canvas.delete("marker")
        vx, vy = self.vanish
        i = start_idx_hint
        n = len(actions_sorted)
        while i < n and actions_sorted[i]['startTime'] < now_t - max(FLASH_S, MARKER_FLASH_S):
            i += 1
        j = i
        # un colpo da marker e' "in vista" (per l'indicatore in alto a destra,
        # vedi sotto) da quando entra nel raggio d'azione finche' il suo
        # lampo d'impatto non e' finito - non solo nell'istante di impatto.
        marker_visible = False
        while j < n and actions_sorted[j]['startTime'] < now_t + LOOKAHEAD_S:
            a = actions_sorted[j]
            t0 = a['startTime']
            fx, fy = self.cell_pos.get(a['moveChannel'], (vx, vy))
            full_r = FULL_R.get(a['moveType'], 22)
            is_obstacle = a['moveType'] in (MOVE_SQUAT, MOVE_DODGE)
            # a piena grandezza la barra sconfina leggermente oltre le colonne
            # esterne (*1.15) invece di fermarsi esattamente al bordo - si legge
            # meglio come "attraversa tutto", non come "tocca giusto il limite"
            full_span = self.grid_span * 1.15 / 2.0 if is_obstacle else None
            is_sidecar = bool(a.get('sidecar'))
            dt = t0 - now_t
            if dt >= 0:
                progress = max(0.0, min(1.0, 1.0 - dt / LOOKAHEAD_S))
                eased = progress ** 2  # parte lento (lontano), accelera avvicinandosi
                x = vx + (fx - vx) * eased
                y = vy + (fy - vy) * eased
                r = max(3.0, full_r * (0.15 + 0.85 * eased))
                obstacle_len = full_span * (0.15 + 0.85 * eased) if is_obstacle else None
                # anello colorato ATTACCATO al bersaglio, non un segnale
                # separato altrove - viaggia con lui per tutto l'arrivo, cosi'
                # si vede da lontano QUALE bersaglio viene da un marker
                # (richiesto 27/08, dopo che il lampo su tutte le corsie
                # sembrava "un'altra cosa" rispetto al bersaglio vero).
                if is_sidecar:
                    self.canvas.create_oval(x - r * 1.5, y - r * 1.5, x + r * 1.5, y + r * 1.5,
                                             outline=MARKER_FLASH_COLOR, width=3, tags="marker")
                    marker_visible = True
                _draw_marker(self.canvas, x, y, r, a['moveType'], a.get('hand'), "marker", obstacle_len)
            else:
                # appena colpito: alone che sfuma (colorato se e' un marker,
                # bianco altrimenti - stesso trattamento, colore diverso),
                # icona a dimensione piena sotto
                fade = max(0.0, 1.0 - (-dt) / (MARKER_FLASH_S if is_sidecar else FLASH_S))
                flash_hex = MARKER_FLASH_COLOR if is_sidecar else '#ffffff'
                glow_color = self._blend(BG_COLOR, flash_hex, fade)
                if fade > 0:
                    glow_r = full_r * (1.3 + 0.9 * fade)
                    self.canvas.create_oval(fx - glow_r, fy - glow_r, fx + glow_r, fy + glow_r,
                                             outline=glow_color, width=3, tags="marker")
                    if is_sidecar:
                        marker_visible = True
                _draw_marker(self.canvas, fx, fy, full_r, a['moveType'], a.get('hand'), "marker", full_span)
            j += 1
        if marker_visible:
            self._draw_marker_indicator(now_t)
        return i

    def _draw_marker_indicator(self, now_t):
        """Etichetta pulsante in alto a destra, attiva ogni volta che un
        colpo da marker e' in vista (in arrivo o appena colpito) - richiesto
        27/08: non piu' un lampo su tutte le corsie (sembrava un segnale
        separato dal bersaglio vero, vedi gli anelli colorati sopra), ma un
        promemoria compatto che resta comunque utile a colpo d'occhio."""
        pulse = 0.5 + 0.5 * math.sin(now_t * 6.0)   # 0..1, un paio di battiti al secondo
        color = self._blend(BG_COLOR, MARKER_FLASH_COLOR, 0.55 + 0.45 * pulse)
        x, y = self.width - 90, self.height * 0.05
        r = 6 + 2 * pulse
        self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="", tags="marker")
        self.canvas.create_text(x + 16, y, text="MARKER", fill=color, anchor="w",
                                 font=("Segoe UI", 12, "bold"), tags="marker")

    @staticmethod
    def _blend(hex_a, hex_b, t):
        def to_rgb(h):
            h = h.lstrip('#')
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        a, b = to_rgb(hex_a), to_rgb(hex_b)
        mixed = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
        return '#%02x%02x%02x' % mixed


# --------------------------------------------------------------------------
# finestra standalone, per provare subito senza agganciarla alla GUI principale
# --------------------------------------------------------------------------

TRACKDATA_DIR, TRACKDEF_DIR, PLAYLIST_DIR = boxvr_dirs()


def playlist_path(name):
    """Percorso di una playlist installata dato il suo nome (senza estensione)."""
    return os.path.join(PLAYLIST_DIR, f"{name}.workoutplaylist.txt")


def available_playlists():
    """Nomi delle playlist installate, in ordine alfabetico."""
    suffix = '.workoutplaylist.txt'
    try:
        return sorted(f[:-len(suffix)] for f in os.listdir(PLAYLIST_DIR) if f.endswith(suffix))
    except OSError:
        return []


def songs_in(name):
    """[(indice, etichetta, n_colpi)] della playlist - per sceglierne una senza
    doverla aprire a mano."""
    try:
        with open(playlist_path(name), encoding='utf-8-sig') as f:
            pl = json.load(f)
    except OSError:
        return []
    out = []
    for i, s in enumerate(pl.get('songs', [])):
        n = sum(1 for a in s['serialisedActionList']['actionList'] if a['musicActionType'] == 0)
        out.append((i, _song_label(s['trackDataName']), n))
    return out


def _song_label(track_id):
    path = os.path.join(TRACKDEF_DIR, f"{track_id}.wdef.txt")
    try:
        with open(path, encoding='utf-8-sig') as f:
            d = json.load(f)
        return f"{d.get('tagLibArtist', '?')} - {d.get('tagLibTitle', '?')}"
    except Exception:
        return track_id


def load_song(song_index=0, path=None):
    with open(path, encoding='utf-8-sig') as f:
        playlist = json.load(f)
    entry = playlist['songs'][song_index]
    track_id = entry['trackDataName']
    actions = []
    for act in entry['serialisedActionList']['actionList']:
        if act['musicActionType'] != 0:
            continue
        payload = json.loads(act['musicActionJSON'])
        actions.append({
            'startTime': float(payload['startTime']),
            'moveType': int(payload['moveAction']['moveType']),
            'moveChannel': int(payload['moveAction']['moveChannel']),
        })
    actions.sort(key=lambda a: a['startTime'])
    # la mano (sinistra/destra) non e' nel formato - vedi hand_for_channel:
    # la decide la colonna dove il colpo atterra, non un contatore cieco.
    center_cycle = itertools.cycle(('L', 'R'))
    for a in actions:
        a['hand'] = hand_for_channel(a['moveChannel'], center_cycle) if a['moveType'] in PUNCH_TYPES else None
    wav_path = os.path.join(TRACKDATA_DIR, f"{track_id}.wav")
    audio, sr = sf.read(wav_path, dtype='float32', always_2d=True)
    return {'label': _song_label(track_id), 'audio': audio, 'sr': sr, 'actions': actions}


# Guadagno del suono d'impatto rispetto al brano (30/08, "non troppo forte" -
# richiesto esplicitamente): -12dB circa, pensato per accompagnare il ritmo
# senza coprire la musica. Non esposto come controllo utente per ora - se in
# prova risultasse troppo/poco presente, e' un singolo numero da aggiustare.
HIT_SFX_GAIN = 0.25

_hit_sfx_cache = {}   # (sr, n_channels) -> array gia' pronto, evita ricaricare/ricampionare ad ogni apertura


def _load_hit_sfx(target_sr, n_channels):
    """Campione del colpo, ricampionato e adattato al numero di canali del
    brano corrente - il file su disco e' fisso (44100Hz stereo), il brano
    generato puo' avere un sample rate diverso."""
    key = (target_sr, n_channels)
    if key in _hit_sfx_cache:
        return _hit_sfx_cache[key]
    sfx, sfx_sr = sf.read(HIT_SFX_PATH, dtype='float32', always_2d=True)
    if sfx_sr != target_sr:
        import librosa
        sfx = np.stack(
            [librosa.resample(sfx[:, c], orig_sr=sfx_sr, target_sr=target_sr) for c in range(sfx.shape[1])],
            axis=1)
    if sfx.shape[1] != n_channels:
        mono = sfx.mean(axis=1)
        sfx = np.repeat(mono[:, None], n_channels, axis=1)
    sfx = np.ascontiguousarray(sfx, dtype='float32')
    _hit_sfx_cache[key] = sfx
    return sfx


def _overlay_hit_sounds(audio, sr, actions):
    """Ritorna una COPIA di `audio` con il campione del colpo sommato ad ogni
    pugno (Jab/Hook/Uppercut - non su Block/Squat/Dodge, che non sono un
    impatto). `audio` originale non viene toccato: serve intatto altrove
    (es. PreviewWindow.duration), solo il buffer dato al player e' quello
    con il suono sovrapposto."""
    hits = [a for a in actions if a['moveType'] in PUNCH_TYPES]
    if not hits or not os.path.isfile(HIT_SFX_PATH):
        return audio
    sfx = _load_hit_sfx(sr, audio.shape[1]) * HIT_SFX_GAIN
    mixed = audio.copy()
    n = len(mixed)
    sfx_len = len(sfx)
    for a in hits:
        start = int(round(a['startTime'] * sr))
        if start >= n:
            continue
        end = min(start + sfx_len, n)
        mixed[start:end] += sfx[:end - start]
    peak = float(np.max(np.abs(mixed))) if n else 0.0
    if peak > 1.0:
        mixed /= peak
    return mixed


class PreviewWindow:
    def __init__(self, root, song, on_close=None):
        self.root = root
        self.song = song
        self.actions = song['actions']
        self.marker_idx = 0
        # chiamato quando la finestra si chiude (in aggiunta alla pulizia
        # interna sotto) - la GUI principale lo usa per riabilitare i
        # controlli che aveva bloccato all'apertura, vedi
        # boxvr_fixer_gui._open_visual_preview: l'anteprima e' uno scatto dei
        # parametri al momento dell'apertura, cambiarli mentre e' aperta la
        # renderebbe disallineata da quello che si vede.
        self._on_close_cb = on_close

        root.title(f"Anteprima visiva - {song['label']}")
        root.configure(bg=BG_COLOR)

        width, height = 1000, 620
        self.canvas = tk.Canvas(root, width=width, height=height, bg=BG_COLOR, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.preview = ChoreoPreviewCanvas(self.canvas, width, height)

        self.duration = len(song['audio']) / song['sr']

        bar = tk.Frame(root, bg=BG_COLOR)
        bar.pack(fill="x", pady=8)
        self.play_btn = tk.Button(bar, text="Play", command=self.toggle, width=10)
        self.play_btn.pack(side="left", padx=12)
        self.time_label = tk.Label(bar, text="0:00 / 0:00", bg=BG_COLOR, fg=TEXT_COLOR,
                                    font=("Segoe UI", 11), width=13, anchor="w")
        self.time_label.pack(side="left", padx=(12, 6))

        # Scorrimento libero nel tempo: senza, per giudicare un passaggio preciso
        # bisognava riascoltare il brano dall'inizio. `_seeking` evita che il
        # cursore venga riposizionato dal tick mentre lo si sta trascinando.
        self._seeking = False
        self.scrub = tk.Scale(bar, from_=0.0, to=max(0.1, self.duration), resolution=0.05,
                              orient="horizontal", showvalue=False, bg=BG_COLOR, fg=TEXT_COLOR,
                              troughcolor=GRID_COLOR, highlightthickness=0, borderwidth=0,
                              sliderrelief="flat", length=420)
        self.scrub.pack(side="left", fill="x", expand=True, padx=(0, 14))
        self.scrub.bind("<Button-1>", lambda e: setattr(self, '_seeking', True))
        self.scrub.bind("<ButtonRelease-1>", self._on_scrub_release)

        # Il player riceve il brano CON il suono dei colpi sovrapposto -
        # song['audio'] resta quello originale (usato altrove, es.
        # self.duration sopra), _overlay_hit_sounds ne fa una copia.
        preview_audio = _overlay_hit_sounds(song['audio'], song['sr'], self.actions)
        self.player = SongPlayer(preview_audio, song['sr'], volume=0.9)
        root.bind("<space>", lambda e: self.toggle())
        root.bind("<Left>", lambda e: self._nudge(-5))
        root.bind("<Right>", lambda e: self._nudge(5))
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tick()

    def _on_scrub_release(self, _event=None):
        self._seek_to(float(self.scrub.get()))
        self._seeking = False

    def _nudge(self, delta):
        self._seek_to(self.player.position_seconds() + delta)

    def _seek_to(self, t):
        t = max(0.0, min(self.duration, t))
        self.player.seek(t)
        # l'indice dei bersagli e' una scorciatoia per non riscandire la lista a
        # ogni fotogramma: dopo un salto va ricalcolato, o la resa riparte dal
        # punto sbagliato (bersagli mancanti, o gia' passati mostrati di nuovo)
        self.marker_idx = 0
        self.scrub.set(t)

    def toggle(self):
        self.player.toggle()
        self.play_btn.configure(text="Pausa" if self.player.stream.active else "Play")

    def _fmt(self, t):
        t = max(0.0, t)
        return f"{int(t // 60)}:{int(t % 60):02d}"

    def _tick(self):
        t = self.player.position_seconds()
        self.marker_idx = self.preview.render(t, self.actions, self.marker_idx)
        if self.marker_idx > 0 and (self.marker_idx >= len(self.actions) or
                                     self.actions[self.marker_idx - 1]['startTime'] > t + LOOKAHEAD_S):
            self.marker_idx = max(0, self.marker_idx - 1)
        self.time_label.configure(text=f"{self._fmt(t)} / {self._fmt(self.duration)}")
        if not self._seeking:
            self.scrub.set(t)
        if self.player.finished:
            self.play_btn.configure(text="Play")
        delay = 33 if self.player.stream.active else 100
        self.root.after(delay, self._tick)

    def _on_close(self):
        self.player.close()
        self.root.destroy()
        if self._on_close_cb is not None:
            self._on_close_cb()


def main():
    """Uso:
        python boxvr_visual_preview.py                        elenca le playlist
        python boxvr_visual_preview.py "Nome playlist"         elenca i brani
        python boxvr_visual_preview.py "Nome playlist" 3       apre il 3o brano
    """
    args = [a for a in sys.argv[1:]]
    if not args:
        print("Playlist installate:\n")
        for n in available_playlists():
            print(f"   {n}")
        print('\nUsa: python boxvr_visual_preview.py "Nome playlist"')
        return

    name = args[0]
    if not os.path.isfile(playlist_path(name)):
        print(f'Playlist "{name}" non trovata. Disponibili:\n')
        for n in available_playlists():
            print(f"   {n}")
        return

    songs = songs_in(name)
    if len(args) < 2:
        print(f'"{name}" contiene {len(songs)} brani:\n')
        for i, label, n in songs:
            print(f"   {i + 1}. {label}  ({n} colpi)")
        print(f'\nUsa: python boxvr_visual_preview.py "{name}" <numero>')
        return

    idx = max(0, min(int(args[1]) - 1, len(songs) - 1))
    song = load_song(idx, playlist_path(name))
    print(f"Carico: {song['label']} ({len(song['actions'])} azioni, "
          f"{len(song['audio']) / song['sr']:.1f}s)")
    root = tk.Tk()
    PreviewWindow(root, song)
    root.mainloop()


if __name__ == '__main__':
    main()
