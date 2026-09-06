#!/usr/bin/env python3
"""Worker standalone per il beat-tracking via madmom (DBNBeatTrackingProcessor).

Vive DELIBERATAMENTE fuori dall'ambiente Python del tool principale: madmom
non supporta Python 3.14 (il tool gira su 3.14), quindi questo script viene
eseguito come sottoprocesso da un interprete/exe compilato a parte (Python
3.10) - vedi boxvr_generator.py:detect_beats_and_bars_madmom() per il lato
chiamante. Comunicazione tramite argv (percorso audio in ingresso) e stdout
(JSON in uscita) cosi' non serve nessuna dipendenza condivisa tra i due
processi oltre al file audio stesso.

Uso: madmom_worker.exe <percorso_audio> [--forced-bpm=139.5]
Output su stdout: {"beat_times": [...], "tempo": <float stimato dai beat>}
   oppure, in caso di errore: {"error": "<messaggio>"}  (su stdout, exit 1)
"""
import json
import sys

import numpy as np


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "uso: madmom_worker.exe <audio_path> [--forced-bpm=X]"}))
        sys.exit(1)
    audio_path = sys.argv[1]
    forced_bpm = None
    for arg in sys.argv[2:]:
        if arg.startswith("--forced-bpm="):
            forced_bpm = float(arg.split("=", 1)[1])

    try:
        import madmom
        proc = madmom.features.beats.RNNBeatProcessor()
        activations = proc(audio_path)
        # DBNBeatTrackingProcessor modella il tempo come stato che evolve nel
        # tempo (catena di Markov), non un unico valore fisso per tutto il
        # brano - e' questa la proprieta' che lo rende piu' robusto ai cambi
        # di sezione/deriva locale rispetto al DP a tempo globale di librosa
        # (confrontati empiricamente su brani reali, vedi memoria di progetto).
        kwargs = {"fps": 100}
        if forced_bpm is not None:
            # min/max_bpm stretti intorno al valore forzato dall'utente -
            # vincola il DBN a restare in quell'ottava senza rifare la stima
            # da zero (lo stesso spirito di bpm= in librosa.beat.beat_track).
            kwargs["min_bpm"] = forced_bpm * 0.9
            kwargs["max_bpm"] = forced_bpm * 1.1
        tracker = madmom.features.beats.DBNBeatTrackingProcessor(**kwargs)
        beat_times = tracker(activations)

        if len(beat_times) < 2:
            print(json.dumps({"error": f"rilevati solo {len(beat_times)} beat"}))
            sys.exit(1)

        intervals = np.diff(beat_times)
        tempo_est = float(60.0 / np.median(intervals))
        print(json.dumps({
            "beat_times": [float(t) for t in beat_times],
            "tempo": tempo_est,
        }))
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
