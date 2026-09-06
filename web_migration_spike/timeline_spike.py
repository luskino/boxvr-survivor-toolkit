#!/usr/bin/env python3
r"""
Spike: timeline + playhead + marker in pywebview (30/08/2026 notte)
====================================================================
Primo VERTICALE della migrazione a framework web, come proposto in
"UI & Warframing\rd_migrazione_framework.md" (punto 3 della sequenza:
"un primo verticale piccolo e isolato, non l'intera GUI"). Prova i tre
pezzi difficili piu' rischiosi identificati li' (waveform/playhead, sync
audio, marker durante la riproduzione) in una finestra separata, senza
toccare la GUI Tkinter esistente - stesso spirito dello spike del bridge
audio del 23/08 (misurare il rischio prima, non assumerlo).

A DIFFERENZA dello spike del 23/08 (throwaway, ambiente/venv isolato mai
mersi nel progetto): qui pywebview e' installato nell'ambiente vero del
progetto (Python 3.14, stesso interprete di boxvr_fixer_gui.py) - verificato
di nuovo che installa pulito (era gia' noto dal 23/08, ri-confermato qui),
NON ancora aggiunto a build_exe.bat: questo file resta un esperimento
isolato, non fa parte del tool spedito finche' la migrazione non e' una
decisione presa per intero.

Regola dura ereditata dallo spike precedente, rispettata nel template HTML:
il playhead si disegna SEMPRE leggendo audio.currentTime, mai
performance.now()/un orologio di sistema separato - vedi il commento nel
loop di disegno in index_template.html.

Dati REALI, non inventati: beat e durata letti dal trackdata di un brano
gia' presente nel set di test noto del progetto (RA TA TA, usato fin
dall'inizio per validare il beat-tracking) - non serve rianalizzare nulla
per questo spike, la sola timeline/rendering e' il rischio da misurare qui.
"""
import json
import os
import shutil
import sys
import tempfile

import webview

TEST_WAV_DIR = r"F:\BoxVR Songs Tool\file di test da correggere wav"
TRACK_ID = "e53fbe2c7da3be7c504f79ec2a369863"   # RA TA TA - nel set di test noto


def _load_beats_and_duration():
    trackdata_path = os.path.join(TEST_WAV_DIR, TRACK_ID + ".trackdata.txt")
    with open(trackdata_path, encoding='utf-8') as f:
        outer = json.load(f)
    duration = float(outer['duration'])
    beat_structure = json.loads(outer['beatStrucureJSON'])
    raw_beats = beat_structure['_beatList']['_beats']
    beats = [{'t': b['_triggerTime'], 'beatInBar': b['_beatInBar']} for b in raw_beats]
    return beats, duration


def _build_page(work_dir):
    """Scrive index.html (dal template, con beat/durata reali iniettati) e
    copia il wav accanto - STESSA cartella, non un percorso diverso: e' la
    combinazione gia' verificata funzionante nello spike del 23/08 (una
    pagina caricata da file di stringa non ha origine disco e nega le
    letture file:///; pagina+audio nella stessa cartella reale la risolve)."""
    beats, duration = _load_beats_and_duration()

    template_path = os.path.join(os.path.dirname(__file__), 'index_template.html')
    with open(template_path, encoding='utf-8') as f:
        html = f.read()
    html = (html
            .replace('__BEATS_JSON__', json.dumps(beats))
            .replace('__DURATION_S__', repr(duration))
            .replace('__N_BEATS__', str(len(beats))))

    index_path = os.path.join(work_dir, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)

    shutil.copy2(os.path.join(TEST_WAV_DIR, TRACK_ID + '.wav'),
                os.path.join(work_dir, 'track.wav'))
    return index_path


class Api:
    """Il bridge Python<->JS vero e proprio - non solo misurato in astratto
    come nello spike del 23/08 (0.78-0.91ms/round-trip), ma usato per un
    caso reale: salvare i marker piazzati durante l'ascolto, esattamente il
    flusso che la sidecar Tkinter fa oggi con `_learn_sidecar_bias`/
    `sidecar_markers`. Qui si limita a stampare in console e a scrivere un
    json accanto allo script - dimostra il percorso, non implementa ancora
    la persistenza vera (quella e' compito della migrazione reale)."""

    def save_markers(self, markers):
        out_path = os.path.join(os.path.dirname(__file__), 'spike_markers_output.json')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(markers, f, indent=2)
        print(f"[spike] {len(markers)} marker ricevuti dal browser e salvati in {out_path}: {markers}")
        return f"{len(markers)} marker salvati in spike_markers_output.json"


def main():
    work_dir = tempfile.mkdtemp(prefix="boxvr_web_spike_")
    index_path = _build_page(work_dir)
    print(f"[spike] pagina generata in {index_path}")

    api = Api()
    webview.create_window("Spike: timeline web (BoxVR)", index_path, js_api=api,
                          width=1280, height=320)
    webview.start()

    shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
