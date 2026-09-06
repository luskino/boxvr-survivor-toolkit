# -*- coding: utf-8 -*-
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

"""Un brano di prova costruito dal nulla, per i test.

PERCHE' ESISTE
--------------
I test che riguardano Correggi avevano bisogno di brani veri nella cartella
di lavoro: cioe' della musica commerciale sul disco dell'autore. Funzionava
finche' il progetto era privato, ma su un repository pubblico significa che
chiunque cloni si trova un test rosso al primo colpo, senza sapere perche' -
e l'unico modo per farlo passare sarebbe procurarsi dei file che nessuno
puo' distribuirgli.

Qui il brano se lo fabbrica il test: un'onda sintetica con dei colpi a tempo,
piu' il `trackdata` che il gioco avrebbe prodotto per quell'audio. Nessun
diritto di terzi, nessun file da procurarsi, e il test misura esattamente la
stessa cosa di prima - anzi meglio, perche' adesso l'ingresso e' noto invece
che "il primo file che capita nella cartella".
"""
import json
import math
import os
import struct
import uuid
import wave

SR = 22050
BPM = 120.0
BEATS_PER_BAR = 4
BARRE = 32                      # 64 secondi a 120 BPM

# Intensita' relativa di ogni tratto del brano, dal silenzio al pieno. Non e'
# decorazione: e' cio' che rende il brano di prova utile a verificare i
# preset, che ridistribuiscono i livelli lungo questa curva.
PROFILO = (0.15, 0.45, 0.85, 1.00, 0.35, 0.70, 1.00, 0.25)


def _campioni(durata_s, beat_s):
    """Onda con un colpo secco su ogni beat: qualcosa che un rilevatore di
    ritmo possa davvero agganciare, non rumore bianco."""
    n = int(SR * durata_s)
    fuori = []
    for i in range(n):
        t = i / SR
        # fondo grave continuo
        v = 0.18 * math.sin(2 * math.pi * 55.0 * t)
        # colpo: attacco che decade in fretta, sul beat
        fase = t % beat_s
        if fase < 0.09:
            inv = 1.0 - (fase / 0.09)
            v += 0.72 * inv * inv * math.sin(2 * math.pi * 180.0 * fase)
        # Profilo di energia a gradini, uno per segmento. Serve al test dei
        # preset: con un brano di intensita' uniforme, 20%% e 80%% danno lo
        # stesso risultato e il test fallisce pur essendo il codice sano -
        # e' successo davvero. Qui la curva ha qualcosa da ridistribuire.
        quota = t / durata_s
        gradino = PROFILO[min(len(PROFILO) - 1, int(quota * len(PROFILO)))]
        v *= gradino
        if gradino > 0.6:
            v += (gradino - 0.6) * 0.7 * math.sin(2 * math.pi * 110.0 * t)
        fuori.append(max(-1.0, min(1.0, v)))
    return fuori


def scrivi_wav(percorso, durata_s=None, bpm=BPM):
    beat_s = 60.0 / bpm
    durata_s = durata_s or (BARRE * BEATS_PER_BAR * beat_s)
    dati = _campioni(durata_s, beat_s)
    with wave.open(percorso, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b''.join(
            struct.pack('<h', int(v * 32000)) for v in dati))
    return durata_s


def costruisci_trackdata(durata_s, bpm=BPM, livelli=(0, 1, 3, 3, 1, 2, 3, 1)):
    """Il `trackdata` che BoxVR avrebbe scritto per quell'audio.

    Stessa forma dei file veri (verificata sui file reali del gioco): beat
    annidati che portano il segmento, `_dataVersion` 3, `_isBuilt` vero,
    `_buildCompleteEvent` di servizio. I VALORI sono nostri, la STRUTTURA e'
    quella che il gioco si aspetta - qui non c'e' niente di FitXR, solo il
    formato, che e' come dire "un file JSON con questi campi".
    """
    beat_s = 60.0 / bpm
    n_beat = int(durata_s / beat_s)
    per_segmento = max(1, n_beat // len(livelli))

    beats, bars, segs = [], [], []
    for i in range(n_beat):
        idx_seg = min(len(livelli) - 1, i // per_segmento)
        if idx_seg >= len(segs):
            # _startBeatIndex/_numBeats non sono decorativi: sono i campi
            # con cui il correttore trova le battute di un segmento. Senza,
            # falliva con KeyError - e il test lo ha scoperto, che e'
            # esattamente il suo mestiere.
            segs.append({
                '_energyLevel': livelli[idx_seg],
                '_startTime': round(i * beat_s, 4),
                '_duration': round(per_segmento * beat_s, 4),
                '_startBeatIndex': i,
                '_numBeats': per_segmento,
                '_sectionLabel': 'S%d' % idx_seg,
            })
        beats.append({
            '_index': i,
            '_beatInBar': (i % BEATS_PER_BAR) + 1,
            '_triggerTime': round(i * beat_s, 4),
            '_beatLength': round(beat_s, 6),
            '_bpm': bpm,
            '_isLastBeat': False,
            '_magnitude': round(0.4 + 0.3 * math.sin(i / 7.0), 4),
            # stesso OGGETTO del segmento, non una copia: e' cosi' nei file
            # veri, ed e' il motivo per cui scrivere il livello nel segmento
            # lo fa vedere a tutti i beat che vi appartengono
            '_segment': segs[idx_seg],
        })
        if i % BEATS_PER_BAR == 0:
            bars.append({
                '_beatIndex': i,
                '_startTime': round(i * beat_s, 4),
                '_duration': round(BEATS_PER_BAR * beat_s, 4),
                '_avgEnergy': round(0.35 + 0.25 * math.sin(i / 11.0), 4),
            })

    if segs:
        segs[-1]['_numBeats'] = n_beat - segs[-1]['_startBeatIndex']

    # La forma e' quella vera: un `outer` che porta i metadati, e tutta la
    # struttura ritmica dentro `beatStrucureJSON` come STRINGA JSON (il
    # refuso "Strucure" e' del formato del gioco, non nostro). Rispecchiata
    # da boxvr_generator.build_trackdata_json invece che indovinata: il
    # primo tentativo l'aveva scritta piatta e il correttore non la leggeva.
    inner = {
        '_buildCompleteEvent': {'m_PersistentCalls': {'m_Calls': []}},
        '_isBuilt': True,
        '_dataVersion': 3,
        '_barList': {'_bars': bars},
        '_beatList': {'_beats': beats},
        '_segmentList': {'_segments': segs},
    }
    return {
        'trackId': {'trackId': uuid.uuid4().hex},
        'originalFilePath': '',
        'originalTrackName': 'Brano di prova sintetico',
        'originalArtist': 'BoxVR Survivor Toolkit',
        'duration': round(durata_s, 3),
        'bpm': bpm,
        'firstBeatOffset': beats[0]['_triggerTime'] if beats else 0.0,
        'locationMode': 0,
        'beatStrucureJSON': json.dumps(inner),
    }


def crea(cartella, nome=None, bpm=BPM):
    """Scrive la coppia .trackdata.txt + .wav dentro `cartella`.
    Ritorna (track_id, percorso_trackdata, percorso_wav)."""
    os.makedirs(cartella, exist_ok=True)
    track_id = nome or uuid.uuid4().hex
    wav = os.path.join(cartella, track_id + '.wav')
    durata = scrivi_wav(wav, bpm=bpm)
    dati = costruisci_trackdata(durata, bpm=bpm)
    dati['trackId']['trackId'] = track_id
    td = os.path.join(cartella, track_id + '.trackdata.txt')
    with open(td, 'w', encoding='utf-8') as f:
        json.dump(dati, f)
    return track_id, td, wav


if __name__ == '__main__':
    import tempfile
    d = tempfile.mkdtemp(prefix='boxvr_fixture_')
    tid, td, wav = crea(d)
    print('brano di prova creato in', d)
    print('  ', os.path.basename(td), os.path.getsize(td), 'byte')
    print('  ', os.path.basename(wav), os.path.getsize(wav), 'byte')
