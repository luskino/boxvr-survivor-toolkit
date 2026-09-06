#!/usr/bin/env python3
r"""
Test di latenza audio REALE fino all'altoparlante (31/08/2026 notte)
=======================================================================
Chiude (o almeno misura per davvero) l'ultimo rischio rimasto aperto in
sezione A della checklist: finora era stato misurato solo l'offset fra
`audio.currentTime` e l'orologio di sistema (~25ms, spike del 23/08) - un
numero tutto interno al software, non il ritardo FISICO fino a quando il
suono esce davvero dall'altoparlante.

Come funziona: Python fa suonare un click breve e netto nella pagina
(via evaluate_js, non un click dell'utente - cosi' si conosce l'istante
esatto in cui e' stato CHIESTO di suonarlo) mentre REGISTRA dal microfono
con `sounddevice` (stessa libreria gia' usata da SongPlayer nella GUI
vera - non una dipendenza nuova). Poi cerca nel file registrato il vero
istante in cui il click e' arrivato al microfono (soglia di energia,
stessa idea di detect_breath_and_bursts in boxvr_generator.py, non
reinventata da zero). La differenza fra i due istanti e' la latenza VERA,
end-to-end: uscita audio del browser -> altoparlante -> aria -> microfono
-> ADC - non solo la parte software.

Serve un microfono posizionato vicino agli altoparlanti reali (quelli
usati per giocare a BoxVR), con un volume udibile - il test non funziona
se il microfono e' lontano o il volume e' troppo basso. Va bene anche un
microfono integrato di webcam/laptop, non serve hardware professionale:
qui interessa un ordine di grandezza (decine di ms), non una precisione
al campione.
"""
import json
import os
import sys
import tempfile
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

sys.path.insert(0, r"F:\BoxVR Songs Tool\web_migration_spike")
import webview
import webview2_check

SAMPLE_RATE = 44100   # per il click generato (lato browser, indipendente dalla registrazione)
RECORD_SECONDS = 2.5
N_TRIALS = 5
CLICK_MS = 15   # click breve e netto - piu' facile da individuare con precisione di un tono lungo

HTML = """<!doctype html><html><body style="font-family:sans-serif;background:#111;color:#eee">
<h2 id="status">Pronto</h2>
<audio id="click" src="click.wav" preload="auto"></audio>
<script>
  const audio = document.getElementById('click');
  window.playClick = function() {
    audio.currentTime = 0;
    audio.play();
  };
  document.getElementById('status').textContent = 'Pagina pronta - in attesa dei trial da Python';
</script>
</body></html>"""


def _make_click_wav(path):
    """Click sintetico: rampa rapida su/giu' (niente attacco morbido, per un
    fronte netto facile da individuare), non un asset esterno da scaricare."""
    n = int(SAMPLE_RATE * CLICK_MS / 1000)
    t = np.arange(n) / SAMPLE_RATE
    tone = np.sin(2 * np.pi * 2000 * t)
    envelope = np.ones(n)
    fade = max(1, n // 8)
    envelope[:fade] = np.linspace(0, 1, fade)
    envelope[-fade:] = np.linspace(1, 0, fade)
    click = (tone * envelope * 0.9).astype(np.float32)
    sf.write(path, click, SAMPLE_RATE)


def _detect_onset(recording, sr, threshold_frac=0.15):
    """Primo campione che supera una frazione del picco assoluto della
    registrazione - stessa idea (soglia di energia) gia' usata altrove nel
    progetto per individuare respiro/raffiche/onset reali, non un algoritmo
    nuovo inventato per questo script."""
    mono = recording.mean(axis=1) if recording.ndim > 1 else recording
    peak = np.abs(mono).max()
    if peak < 1e-4:
        return None  # silenzio - il microfono non ha sentito nulla
    threshold = peak * threshold_frac
    idx = np.argmax(np.abs(mono) > threshold)
    return idx / sr


def run_trials(window, record_sample_rate=SAMPLE_RATE):
    results = []
    for i in range(N_TRIALS):
        print(f"[latenza] trial {i + 1}/{N_TRIALS}...")
        rec = sd.rec(int(RECORD_SECONDS * record_sample_rate), samplerate=record_sample_rate, channels=1, dtype='float32')
        t_request = time.perf_counter()
        window.evaluate_js('playClick()')
        sd.wait()

        onset_s = _detect_onset(rec, record_sample_rate)
        if onset_s is None:
            print("  ATTENZIONE: nessun suono rilevato dal microfono su questo trial (volume troppo basso o microfono troppo lontano) - scartato")
            continue
        latency_ms = onset_s * 1000.0
        # onset_s e' gia' relativo all'inizio della registrazione, che e'
        # iniziata circa a t_request (sd.rec parte subito, prima della
        # evaluate_js) - la latenza vera e' quindi ~onset_s meno il piccolo
        # margine fra l'avvio della registrazione e la chiamata JS, gia'
        # sotto 1ms in pratica (chiamata sincrona immediatamente successiva)
        print(f"  onset rilevato a {latency_ms:.1f}ms nella registrazione")
        results.append(latency_ms)
        time.sleep(0.5)
    return results


def on_loaded(window, out_path, record_sample_rate):
    results = run_trials(window, record_sample_rate)
    summary = {
        'n_trials_requested': N_TRIALS,
        'n_trials_valid': len(results),
        'latencies_ms': results,
        'mean_ms': float(np.mean(results)) if results else None,
        'median_ms': float(np.median(results)) if results else None,
        'min_ms': float(np.min(results)) if results else None,
        'max_ms': float(np.max(results)) if results else None,
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    print(f"\n[latenza] RISULTATO: {json.dumps(summary, indent=2)}")
    print(f"[latenza] salvato in {out_path}")
    window.destroy()


def main():
    if '--list-devices' in sys.argv:
        print(sd.query_devices())
        return

    input_device = None
    if '--input-device' in sys.argv:
        # per NOME, non per indice numerico - verificato su questa macchina
        # che gli indici NON sono stabili fra un'esecuzione e l'altra dello
        # script (73 dispositivi enumerati in un run, 29 nel run precedente -
        # probabilmente per gli endpoint audio virtuali di VR/streaming che
        # compaiono/spariscono) - un indice preso da `--list-devices` e
        # riusato in un secondo comando puo' silenziosamente puntare a un
        # dispositivo diverso. Cercato per sottostringa del nome invece,
        # RISOLTO nello stesso processo in cui viene poi usato.
        idx = sys.argv.index('--input-device')
        name_query = sys.argv[idx + 1].lower()
        devices = sd.query_devices()
        apis = sd.query_hostapis()
        matches = [i for i, d in enumerate(devices)
                  if name_query in d['name'].lower() and d['max_input_channels'] > 0]
        if not matches:
            print(f'Nessun microfono trovato con "{name_query}" nel nome. Dispositivi disponibili:')
            print(sd.query_devices())
            return
        # preferito WASAPI se disponibile per quel nome - verificato su
        # questa macchina che MME dichiara 90ms di latenza intrinseca contro
        # i 3ms di WASAPI per lo STESSO microfono fisico: un fattore di 30x
        # che avrebbe dominato la misura senza questa scelta.
        wasapi_matches = [i for i in matches if apis[devices[i]['hostapi']]['name'] == 'Windows WASAPI']
        input_device = wasapi_matches[0] if wasapi_matches else matches[0]
        sd.default.device = (input_device, sd.default.device[1])

    if not webview2_check.ensure_webview2_or_exit():
        return

    input_info = sd.query_devices(input_device, kind='input') if input_device is not None else sd.query_devices(kind='input')
    # WASAPI (e altre API moderne) spesso rifiutano un samplerate diverso
    # dal nativo del dispositivo (verificato: PortAudioError "Invalid sample
    # rate" su questa macchina chiedendo 44100 a un mic WASAPI nativo 48000) -
    # si registra sempre al samplerate REALE del dispositivo scelto, mai un
    # valore fisso assunto uguale per tutti.
    record_sample_rate = int(input_info['default_samplerate'])
    print("Dispositivo di registrazione:", input_info['name'], f"({record_sample_rate} Hz)")
    print("Dispositivo di riproduzione predefinito:", sd.query_devices(kind='output')['name'])
    print("Assicurati che il microfono scelto sia vicino agli altoparlanti reali e il volume sia udibile.")
    print("(Usa 'python audio_latency_test.py --list-devices' per vedere tutti i dispositivi,")
    print(' poi \'python audio_latency_test.py --input-device "nome o parte del nome"\' per sceglierne uno.)\n')

    work_dir = tempfile.mkdtemp(prefix="boxvr_audio_latency_")
    _make_click_wav(os.path.join(work_dir, 'click.wav'))
    index_path = os.path.join(work_dir, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(HTML)
    out_path = os.path.join(os.path.dirname(__file__), 'audio_latency_result.json')

    window = webview.create_window("Test latenza audio", index_path, width=500, height=200)
    window.events.loaded += lambda: on_loaded(window, out_path, record_sample_rate)
    webview.start()

    import shutil
    shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
