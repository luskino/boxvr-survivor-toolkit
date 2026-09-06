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

"""Registratore da riga di comando per la modalita' sidecar - Fase B1 del
piano (UI & Warframing/rd_modalita_sidecar.md). Riproduce un brano e cattura
DUE tasti equivalenti (default: 'z' e 'x') mentre suona - entrambi generano
lo stesso evento "qui ci vuole qualcosa" (mai una scelta di corsia, coerente
con la decisione gia' presa su questo punto). Salva solo i timestamp grezzi,
NON applica ancora il filtro del limite fisico ne' decide corsia/tipo di
colpo - quello lo fa `engine.py` a valle, separazione deliberata fra
"cosa ha premuto l'utente" e "cosa ne facciamo".

Nessuna dipendenza nuova: `msvcrt` e' nella libreria standard di Windows,
non serve installare `keyboard`/`pynput` (verificato il 26/08: nessuno dei
due e' nell'ambiente di sviluppo, e per un tool che gia' evita dipendenze
pesanti - vedi la scelta contro Demucs/PyTorch in STATO E ROADMAP.md - non
ha senso aggiungerne una per due tasti).

ATTENZIONE - non ancora provato dal vivo (26/08): la logica di lettura audio
e cattura tasti e' scritta e ragionata, ma non verificabile da un agente
senza mani reali su una tastiera mentre la musica suona. Il primo test vero
lo deve fare l'utente.
"""
import json
import msvcrt
import os
import sys
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

EVENT_KEYS = {'z', 'x'}   # entrambi equivalenti - "qui ci vuole qualcosa"
QUIT_KEY = '\x1b'         # Esc


class _MinimalPlayer:
    """Riproduzione con posizione esposta, senza dipendere dalla GUI (che
    importerebbe tkinter/customtkinter solo per una classe) - stessa idea di
    SongPlayer in boxvr_fixer_gui.py, ridotta all'essenziale per uno script
    da riga di comando."""

    def __init__(self, audio, sr):
        self.audio = audio
        self.sr = sr
        self.pos = 0
        self.finished = False
        # latency='low' (27/08: difetto reale trovato nella GUI e corretto
        # anche qui per coerenza - vedi SongPlayer.audible_position_seconds
        # in boxvr_fixer_gui.py per la misura: 90-180ms col default su
        # questa macchina, abbastanza da sentirsi come "fuori tempo" anche
        # premendo esattamente sul beat).
        self.stream = sd.OutputStream(
            samplerate=sr, channels=audio.shape[1], dtype='float32', latency='low',
            callback=self._callback, finished_callback=self._on_finished,
        )

    def _callback(self, outdata, frames, time_info, status):
        p = self.pos
        n = min(frames, len(self.audio) - p)
        if n <= 0:
            outdata.fill(0)
            raise sd.CallbackStop()
        outdata[:n] = self.audio[p:p + n]
        if n < frames:
            outdata[n:].fill(0)
        self.pos = p + n

    def _on_finished(self):
        self.finished = True

    def position_seconds(self):
        return self.pos / self.sr

    def audible_position_seconds(self):
        """Istante DAVVERO udibile ora, non quello gia' consegnato al buffer
        - vedi SongPlayer.audible_position_seconds in boxvr_fixer_gui.py per
        la spiegazione completa. E' questo, non position_seconds(), che va
        usato per marcare un evento a tempo."""
        return max(0.0, self.position_seconds() - (self.stream.latency or 0.0))

    def start(self):
        self.stream.start()

    def close(self):
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass


def record(audio_path, dest_path=None, event_keys=EVENT_KEYS):
    """Riproduce `audio_path`, registra i timestamp (in secondi) di ogni
    pressione di uno dei tasti in `event_keys`, li scrive in `dest_path`
    (default: stesso nome del brano + '.markers.json') e li ritorna.

    Esce quando il brano finisce o quando si preme Esc."""
    audio, sr = sf.read(audio_path, always_2d=True, dtype='float32')
    dur = len(audio) / sr
    player = _MinimalPlayer(audio, sr)
    dest_path = dest_path or (os.path.splitext(audio_path)[0] + '.markers.json')

    keys_label = "' o '".join(sorted(event_keys))
    print(f"Registrazione su: {os.path.basename(audio_path)} ({dur:.0f}s)")
    print(f"Premi '{keys_label}' per segnare un evento, Esc per uscire prima.")
    print("Inizio tra 2 secondi...")
    time.sleep(2)

    markers = []
    player.start()
    try:
        while not player.finished:
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                try:
                    key = ch.decode('utf-8', errors='ignore').lower()
                except Exception:
                    key = ''
                if key == QUIT_KEY:
                    break
                if key in event_keys:
                    t = player.audible_position_seconds()
                    markers.append(t)
                    print(f"  evento a {t:6.3f}s  (totale: {len(markers)})")
            time.sleep(0.001)   # polling stretto, non un limite alla precisione:
            # il timestamp viene da player.audible_position_seconds() (istante
            # DAVVERO udibile, compensato per la latenza del dispositivo - vedi
            # sopra), non da quando il polling se ne accorge
    finally:
        player.close()

    with open(dest_path, 'w', encoding='utf-8') as f:
        json.dump({'audio_path': audio_path, 'duration': dur, 'markers': markers}, f, indent=2)
    print(f"\n{len(markers)} eventi salvati in {dest_path}")
    return markers


# Nota su cosa NON e' ancora risolto (Fase A2/A3 del piano, non affrontate
# stanotte): la latenza vera fra "il campione esce dalla scheda audio" e
# "l'utente lo sente" non e' nota su questa macchina, e il tempo di reazione
# umano (systematically in ritardo di qualche decina/centinaio di ms) non e'
# calibrato. Il timestamp salvato qui e' quello GREZZO (posizione audio nel
# momento in cui msvcrt nota il tasto premuto) - la calibrazione va applicata
# a valle, non qui, per non confondere "quello che l'utente ha fatto" con
# "la correzione che gli applichiamo".


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("uso: python recorder.py <percorso_audio> [percorso_output.json]")
        sys.exit(1)
    dest = sys.argv[2] if len(sys.argv) > 2 else None
    record(sys.argv[1], dest)
