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
BoxVR Choreography Generator
============================
Costruisce una MusicActionList - la coreografia colpo per colpo - da mettere
dentro una playlist di BoxVR, al posto di lasciar generare il gioco.

PERCHE' ESISTE
--------------
Il trackdata (quello che genera boxvr_generator.py) dice soltanto "questa
sezione e' carica cosi'": e' poi BoxVR a scegliere a runtime quali pugni far
comparire, pescando a caso da un repertorio di pattern in base all'intensita'.
Con la lista di azioni scritta a mano decidiamo noi ogni singolo evento: tipo
di mossa, posizione nello spazio e istante esatto. Questo sblocca squat,
schivate, parate e cambi di guardia, che con il solo _energyLevel erano
inesprimibili.

RICHIEDE LA PATCH AL GIOCO. Di suo BoxVR rigenera la coreografia a ogni avvio
di una playlist utente e butta via la nostra (GameStateTraining.OnEnableGameState
chiama GenerateActionSequence in modo incondizionato). Vedi
`patch boxvr/patch_boxvr.py` e la nota [[boxvr-internals]]. Senza patch questa
lista viene semplicemente ignorata - non e' un errore, e nulla si rompe.

DA DOVE VIENE IL VOCABOLARIO
----------------------------
`data/training_sequences.json` e' il repertorio ORIGINALE di BoxVR, estratto
dagli asset Unity del gioco (Training.sequencecollection). Non e' inventato:
sono gli stessi pattern che il gioco userebbe, organizzati per intensita' 0-5,
di 16 beat (4 battute) ciascuno.

L'IDEA IN PIU' RISPETTO AL GIOCO
--------------------------------
Il generatore del gioco pesca un pattern a caso ad ogni cambio di intensita',
quindi due ritornelli identici ricevono coreografie diverse. Noi abbiamo le
etichette delle sezioni musicali dal segmentatore Vamp (`_sectionLabel`), che
si ripetono quando la sezione torna: diamo alla stessa sezione la STESSA
combinazione ogni volta che ricompare. E' cio' che fa percepire un allenamento
come composto invece che casuale.
"""

import bisect
import json
import os
import random
import sys

# --- enum reali del gioco (valori letti dai metadati di Assembly-CSharp.dll) --
MOVE_NONE, MOVE_REST, MOVE_STANCE = 0, 1, 2
MOVE_BLOCK, MOVE_JAB, MOVE_HOOK = 100, 101, 102
MOVE_UPPERCUT, MOVE_DODGE, MOVE_SQUAT = 103, 104, 105

CH_FRONT, CH_FRONT_LOW, CH_CENTER = 0, 1, 2
CH_CENTER_LOW, CH_BACK, CH_BACK_LOW = 3, 4, 5

ACT_MOVECUE, ACT_MESSAGE, ACT_BPM, ACT_AUDIO = 0, 1, 2, 3

PATTERN_BEATS = 16   # ogni pattern del repertorio copre 4 battute

_VOCAB_CACHE = {}


# -- modello di intensita' -------------------------------------------------
#
# Sostituisce due manopole che si sovrapponevano in modo confuso: la "densita'"
# applicata al trackdata al momento della generazione e lo "shift" applicato
# alla coreografia. Avevano effetti che si sommavano senza che fosse chiaro
# quale delle due stessi girando.
#
# La ragione per cui ora si puo' semplificare: con il gioco patchato
# _energyLevel non parla piu' a BoxVR (il generatore procedurale e' scavalcato),
# quindi non siamo piu' obbligati a passare per le sue quattro fasce. La
# coreografia si decide direttamente dalla CURVA DI ENERGIA CONTINUA del brano
# (bar_score, gia' calcolato battuta per battuta).
#
# Un preset non dice solo "piu' o meno colpi": dice quanto si spinge (floor) e
# quanto e' ampia l'escursione tra la parte piu' calma e il drop (ceiling). Il
# brano modula DENTRO quella cornice, cosi' due canzoni diverse allo stesso
# preset restano lo stesso allenamento ma ognuna segue la propria musica.
#
# `rest_below`: percentile della curva di energia sotto il quale la sezione
# diventa silenzio vero. E' il "riposo" del preset - e a differenza del gioco
# possiamo permettercelo tutte le volte che serve, non solo la prima (BoxVR
# onora il livello 0 una volta sola, vedi [[boxvr-internals]]).
#
# I ritmi indicativi (eventi/minuto) NON sono impostati direttamente: emergono
# dalla densita' dei pattern alle intensita' comprese tra floor e ceiling.
# Sono annotati qui come bersaglio da verificare, e vanno tarati sulle
# reference dell'utente (un workout ufficiale BoxVR sta sugli 86/min).
#
# `target_epm` MISURATO (26/08), non piu' un bersaglio a intuito. I valori
# precedenti (60/90/130) non erano mai stati usati ne' verificati da nessuna
# parte del codice, ed erano tutti SOVRASTIMATI: misurando la coreografia
# davvero prodotta su 6 brani (3 di riferimento + 3 ufficiali) i numeri reali
# sono 42/74/88. Ora sono un dato osservato, mostrato anche all'utente
# nell'interfaccia (richiesta esplicita del 26/08: vedere i colpi/min attesi e
# il riferimento ufficiale, invece del solo nome astratto del preset).
# `epm_range` accompagna la media perche' la dispersione fra brani e' ampia e
# reale (medium va da 61 a 103 a seconda del brano): mostrare solo la media
# darebbe un'idea falsa di precisione.
INTENSITY_PRESETS = {
    'light':  {'label': 'Leggero', 'floor': 1, 'ceiling': 3, 'rest_below': 0.25,
               'moves': ('jab', 'hook'), 'target_epm': 42, 'epm_range': (32, 58)},
    # ceiling 5 + squat ammessi (cambiato 25/08 dopo il verdetto VR "due colpi a
    # tempo che potevano averne uno in mezzo": densita' misurata 0.55-0.61 colpi
    # per beat contro lo 0.70 medio - e 0.97 nei picchi - dei workout ufficiali).
    #
    # I due cambiamenti vanno INSIEME e da soli non funzionano:
    #   - alzare il solo ceiling a 5 non produce nulla, perche' l'intensita' 5
    #     ha 0 pattern utilizzabili su 11 finche' gli squat non sono ammessi
    #     (li contengono tutti);
    #   - ammettere i soli squat lascia il tetto a 4 e non sblocca il gradino
    #     piu' denso.
    # Insieme: densita' media simulata 0.68 (obiettivo 0.70) e squat al 10%
    # delle mosse, contro il 7% misurato sui 465 workout ufficiali - quindi
    # allineati al riferimento reale, non un'invenzione. Gli squat restano una
    # minoranza e arrivano solo ai livelli 3 e 5: il livello 4, il piu'
    # frequente, non ne contiene nessuno.
    #
    # Le schivate restano fuori: sono l'unica mossa che i workout ufficiali
    # usano davvero poco (3%) e non servono a sbloccare nessun gradino.
    'medium': {'label': 'Medio',   'floor': 2, 'ceiling': 5, 'rest_below': 0.15,
               'moves': ('jab', 'hook', 'uppercut', 'block', 'squat'),
               'target_epm': 74, 'epm_range': (61, 103)},
    'high':   {'label': 'Intenso', 'floor': 3, 'ceiling': 5, 'rest_below': 0.08,
               'moves': ('jab', 'hook', 'uppercut', 'block', 'squat', 'dodge'),
               'target_epm': 88, 'epm_range': (65, 119)},
}
DEFAULT_PRESET = 'medium'

# Colpi/min di un workout UFFICIALE BoxVR - misurato il 26/08 sulla
# coreografia vera di 15 brani ufficiali (non piu' una stima: l'audio e le
# coreografie ufficiali sono stati estratti dai .fdb del gioco). Mostrato
# nell'interfaccia accanto al valore del preset, cosi' l'utente vede a colpo
# d'occhio quanto si sta allontanando dallo standard del gioco.
OFFICIAL_EPM = 82

# quali mosse ammette ogni preset, per filtrare i pattern del repertorio
_MOVE_GROUP = {
    MOVE_JAB: 'jab', MOVE_HOOK: 'hook', MOVE_UPPERCUT: 'uppercut',
    MOVE_BLOCK: 'block', MOVE_SQUAT: 'squat', MOVE_DODGE: 'dodge',
    MOVE_STANCE: 'jab', MOVE_REST: 'jab', MOVE_NONE: 'jab',
}


def segment_energies(analysis):
    """Energia rappresentativa per segmento, presa dalla curva continua
    bar_score invece che dal livello quantizzato. Ritorna una lista parallela
    ad analysis['segs'].

    NON e' la media pura - e' una miscela 60% media / 40% 75esimo percentile
    dei bar dentro il segmento. Trovato il perche' il 25/08 confrontando con
    BeatSaver (Du Hast, t=170s): il segmentatore strutturale a volte produce
    blocchi lunghi (qui 88 beat, 42s) che attraversano una vera transizione
    quieto->carico senza vedere il confine - la media pura del blocco
    (0.11) affossava una salita reale negli ultimi 25s (fino a 0.17, esattamente
    dove la mappa reale aveva il suo picco), classificando l'intero segmento
    come silenzio. Il percentile alto tira su il valore quando il segmento
    CONTIENE davvero bar energici, senza farsi ingannare da un singolo bar
    isolato (a differenza del massimo puro) - per segmenti brevi (pochi bar)
    la differenza dalla media resta minima, il problema riguarda solo i
    blocchi lunghi dove la media puo' davvero nascondere una salita interna.

    Se bar_score non c'e' (analisi ricostruita da un trackdata installato, dove
    la curva non e' salvata) ripiega su _averageEnergy, che il formato porta con
    se' per ogni segmento."""
    import numpy as np
    segs = analysis['segs']
    score = analysis.get('bar_score')
    bars = analysis.get('bars')
    if score is None or bars is None or not len(score):
        return [float(s.get('_averageEnergy', 0.0)) for s in segs]
    starts = [b['_beatIndex'] for b in bars]
    out = []
    for s in segs:
        b0 = s['_startBeatIndex']
        b1 = b0 + s['_numBeats']
        idx = [i for i, bi in enumerate(starts) if b0 <= bi < b1]
        vals = [score[i] for i in idx if i < len(score)]
        if not vals:
            out.append(float(s.get('_averageEnergy', 0.0)))
            continue
        mean_v = float(np.mean(vals))
        p75_v = float(np.percentile(vals, 75))
        out.append(0.6 * mean_v + 0.4 * p75_v)
    return out


def _percentile_ranks(pairs):
    """`pairs`: lista di (chiave, valore). Rank percentile (0-1) per chiave,
    in un dict - l'ordine del dict NON e' per rank crescente, va sempre letto
    per chiave. Una sola voce non ha nulla con cui confrontarsi: rank 1.0 (non
    forzarla al silenzio per mancanza di contesto, non per merito - stesso
    principio cauto gia' usato altrove nel generatore, es. _pattern_for che
    preferisce un pattern fuori vocabolario a un buco nell'allenamento)."""
    if len(pairs) <= 1:
        return {k: 1.0 for k, _ in pairs}
    ordered = sorted(pairs, key=lambda kv: kv[1])
    return {k: pos / (len(ordered) - 1) for pos, (k, _) in enumerate(ordered)}


def structural_energy_rank(analysis, energies):
    """Percentile a DUE LIVELLI invece che sull'intero brano - vedi
    energies_to_intensities per cosa sostituisce e perche'.

    Nato da un caso reale (Master Of Puppets, VR 25/08): il riff pesante
    dell'intro finiva al 9 percentile dell'INTERO brano di 8 minuti (che ha
    sezioni molto piu' cariche dopo, es. i tornado di doppia cassa) e veniva
    zittito come vero silenzio - forte in assoluto, ma il metro di paragone
    sbagliato (l'intero brano invece della propria sezione).

    Macroblocco = gruppo di sezioni che si RIPETONO (`_sectionLabel`, gia'
    calcolato dal segmentatore strutturale per far ripetere lo stesso pattern
    sulle sezioni che tornano - non un chunking nuovo, e' quello che
    abbiamo gia'). Ogni segmento riceve due percentili:
    - quanto conta la SUA sezione rispetto alle altre sezioni del brano
      (energia media del gruppo, classificata fra i gruppi - "macro");
    - quanto conta LUI rispetto agli altri momenti della stessa sezione
      (classificato solo fra i membri del suo gruppo - "locale").
    Il valore finale e' la loro media: un momento resta vero silenzio solo se
    e' debole su ENTRAMBI i piani, non perche' un ritornello lontano e senza
    relazione con lui e' piu' carico.

    Verificato sui dati reali di Master Of Puppets: il gruppo 'A' (l'intro,
    3 occorrenze: apertura, il riff con chitarra+batteria, un richiamo
    successivo) porta il riff dal 9% (silenziato) al 33% (attivo), mentre il
    solo istante davvero muto dell'apertura resta sotto soglia.

    Si ripiega sul percentile piatto di sempre quando la segmentazione
    strutturale non c'e' (`seg_mode` fisso) o produce un solo gruppo - un
    livello macro non aggiungerebbe informazione in quei casi."""
    segs = analysis['segs']
    n = len(energies)
    if n == 0:
        return []
    labels = [s.get('_sectionLabel') or f'seg{i}' for i, s in enumerate(segs)]
    if analysis.get('seg_mode') != 'structural' or len(set(labels)) <= 1:
        flat = _percentile_ranks(list(enumerate(energies)))
        return [flat[i] for i in range(n)]

    groups = {}
    for i, lab in enumerate(labels):
        groups.setdefault(lab, []).append(i)

    macro_energy = [(lab, sum(energies[i] for i in idxs) / len(idxs))
                     for lab, idxs in groups.items()]
    macro_rank = _percentile_ranks(macro_energy)

    local_rank = {}
    for idxs in groups.values():
        local_rank.update(_percentile_ranks([(i, energies[i]) for i in idxs]))

    return [(macro_rank[labels[i]] + local_rank[i]) / 2.0 for i in range(n)]


def energies_to_intensities(energies, preset=DEFAULT_PRESET, rank=None):
    """Mappa la curva di energia sulle intensita' del repertorio (0-5).

    Normalizza per PERCENTILE dentro il brano, non sul valore assoluto: brani
    masterizzati piu' forte o piu' piano darebbero altrimenti allenamenti di
    intensita' diversa a parita' di preset, il che non e' quello che si intende
    scegliendo "Medio". Cosi' invece il preset governa il livello e la musica
    governa la forma.

    `rank`: se dato, usa questi percentili (0-1, uno per elemento di
    `energies`, stesso ordine) invece di calcolarli qui dal solo valore
    assoluto - vedi structural_energy_rank per il caso d'uso reale (percentile
    a due livelli invece che sull'intero brano, che da solo puo' zittire un
    momento forte in un brano lungo e dinamicamente ampio)."""
    p = INTENSITY_PRESETS.get(preset) or INTENSITY_PRESETS[DEFAULT_PRESET]
    n = len(energies)
    if not n:
        return []
    if rank is None:
        order = sorted(range(n), key=lambda i: energies[i])
        rank = [0.0] * n
        for pos, i in enumerate(order):
            rank[i] = pos / (n - 1) if n > 1 else 1.0
    floor, ceiling = p['floor'], p['ceiling']
    out = []
    for r in rank:
        if r < p['rest_below']:
            out.append(0)                      # riposo vero
            continue
        # riscala il resto della curva sull'intervallo del preset
        span = 1.0 - p['rest_below']
        t = (r - p['rest_below']) / span if span > 0 else 1.0
        out.append(int(round(floor + (ceiling - floor) * t)))
    return out


def _pattern_allowed(pattern, preset):
    """True se il pattern usa solo mosse ammesse dal preset. Serve a tenere
    squat e schivate fuori dai preset piu' leggeri: un pattern del repertorio
    e' un blocco unico, quindi o lo si prende tutto o lo si scarta."""
    allowed = set(INTENSITY_PRESETS.get(preset, {}).get('moves', ()))
    if not allowed:
        return True
    for m in pattern.get('moveActions', []):
        if _MOVE_GROUP.get(m.get('moveType'), 'jab') not in allowed:
            return False
    return True


def _base_dir():
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


class VocabularyMissing(FileNotFoundError):
    """Il repertorio ufficiale non e' disponibile su questa macchina.

    Non e' un errore di programmazione ma una situazione prevista: il
    repertorio e' contenuto del gioco e non viene distribuito col tool, viene
    estratto dalla copia dell'utente quando si installa la patch (vedi
    boxvr_extract.py). Ha un tipo suo perche' l'interfaccia possa distinguerlo
    da un vero file mancante e dire all'utente cosa fare."""


def _find_vocabulary():
    """Percorso del repertorio: prima quello estratto dal gioco dell'utente,
    poi quello eventualmente spedito accanto al tool.

    L'ordine conta: l'estratto viene dalla copia REALE dell'utente, quindi
    riflette la sua versione del gioco; quello accanto al tool e' un ripiego
    utile in sviluppo (dove data/ e' presente) e per le build storiche."""
    estratto = _extract_mod().user_data_path() if _extract_mod() else None
    if estratto and os.path.isfile(estratto):
        return estratto
    return os.path.join(_base_dir(), 'data', 'training_sequences.json')


def _extract_mod():
    """boxvr_extract importato pigramente: boxvr_choreo e' usato anche da
    script di analisi che non hanno bisogno dell'estrattore."""
    try:
        import boxvr_extract
        return boxvr_extract
    except ImportError:
        return None


def load_vocabulary(path=None):
    """Carica il repertorio ufficiale, indicizzato per intensita'.
    Ritorna {intensita: [pattern, ...]} con solo le liste di tipo Normal
    (quelle Start/End servono agli agganci del gioco, non a noi)."""
    path = path or _find_vocabulary()
    if path in _VOCAB_CACHE:
        return _VOCAB_CACHE[path]
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        raise VocabularyMissing(
            "Repertorio dei pattern non trovato. Viene estratto dalla tua copia "
            "di BoxVR quando installi la patch: apri la sezione della patch e "
            "applicala (o riapplicala) per generarlo.") from None
    by_intensity = {}
    for lst in data.get('sequenceLists', []):
        if lst.get('sequenceType') != 2:      # 2 = Normal
            continue
        by_intensity.setdefault(lst['sequenceIntensity'], []).extend(lst.get('sequenceList', []))
    _VOCAB_CACHE[path] = by_intensity
    return by_intensity


def energy_to_intensity(energy_level, difficulty=2, shift=0):
    # NON usata piu' dal generatore (che ora parte dalla curva continua, vedi
    # energies_to_intensities). Resta perche' documenta la formula REALE del
    # gioco, letta dall'IL: serve a sapere cosa farebbe BoxVR con un dato
    # trackdata quando la patch NON e' attiva.
    """Mappa _energyLevel (0-3) -> intensita' del repertorio (0-5), con la
    formula ESATTA del gioco, letta dall'IL di MovePatternIntensityControl:
        livello 0        -> 0
        livello 1/2/3    -> difficolta' + livello
    difficulty: 0=Easy, 1=Medium, 2=Hard.

    Differenza importante rispetto al gioco: BoxVR onora il livello 0 (silenzio)
    SOLO la prima volta in un brano, e da li' in poi lo sostituisce con
    difficolta'+1 (flag _playZeroIntensityOnce). Noi scriviamo gli eventi
    direttamente, quindi quel vincolo non ci tocca: il silenzio resta silenzio
    tutte le volte, e riguadagniamo la granularita' che in Hard faceva
    collassare livello 0 e 1 sulla stessa cosa.

    `shift`: sposta l'intensita' di N gradini (negativo = piu' leggero) senza
    toccare il trackdata. Serve perche' la densita' finale dipende da due cose
    diverse: i livelli scritti nel trackdata (manopola "densita'" al momento
    della generazione) e questa mappatura. Su un trackdata generato a densita'
    piena, in Hard, la maggior parte dei segmenti finisce a intensita' 4-5, cioe'
    una mossa per beat: fedele a quello che farebbe il gioco, ma ~160 eventi al
    minuto contro gli ~86 di un workout ufficiale. Con shift=-1 si scende
    nell'ordine di grandezza giusto senza dover rigenerare tutta la libreria.
    Il silenzio resta silenzio: lo shift non lo tocca mai."""
    if energy_level <= 0:
        return 0
    return max(1, min(5, difficulty + energy_level + shift))


def _pattern_for(section_key, intensity, vocab, chooser, memo, avoid=None, preset=None):
    """Sceglie un pattern per una sezione, ricordando la scelta: la stessa
    sezione musicale alla stessa intensita' riceve sempre lo stesso pattern.

    `avoid`: nome del pattern usato dal segmento precedente. Serve solo alla
    PRIMA scelta di una sezione nuova: due sezioni diverse e adiacenti che
    pescano per caso lo stesso pattern suonerebbero identiche, annullando
    proprio la varieta' che la segmentazione strutturale vuole dare. Non
    intacca la ricorrenza: se la sezione e' gia' stata vista si riusa la
    scelta memorizzata, anche se coincide con quella precedente."""
    pool = vocab.get(intensity) or []
    if preset:
        # tiene squat/schivate fuori dai preset leggeri; se il filtro non
        # lascia nulla si usa comunque il repertorio pieno, meglio un pattern
        # fuori vocabolario che un buco nell'allenamento.
        filtered = [p for p in pool if _pattern_allowed(p, preset)]
        pool = filtered or pool
    if not pool:
        return None
    key = (section_key, intensity, preset)
    if key not in memo:
        idx = chooser.randrange(len(pool))
        if avoid and len(pool) > 1:
            for _ in range(4):
                if pool[idx].get('sequenceName') != avoid:
                    break
                idx = chooser.randrange(len(pool))
        memo[key] = idx
    return pool[memo[key] % len(pool)]


# --- vincoli di giocabilita' -------------------------------------------------
# Ricavati MISURANDO il repertorio ufficiale del gioco (data/training_sequences.json,
# 45 pattern di tipo Normal), non scelti a intuito:
#   - distanza minima fra due mosse consecutive: 0.5 beat, mai meno (45 occorrenze
#     a 0.5, poi 1.0 beat come caso dominante con 341);
#   - le UNICHE due combinazioni simultanee che il gioco usa sono Block+Squat (12
#     volte) e Jab+Squat (10). Squat e' l'unica mossa che si abbina, ed e'
#     l'unica di gambe: le altre sono di braccia e non possono coesistere.
# Confermato dal test in VR del 2026-08-24: pugni sovrapposti, colpi sopra i
# ganci e scudo+pugno erano tutti fisicamente non eseguibili.
MIN_GAP_BEATS = 0.5
LEGAL_SIMULTANEOUS_MEASURED = frozenset((
    frozenset((MOVE_BLOCK, MOVE_SQUAT)),
    frozenset((MOVE_JAB, MOVE_SQUAT)),
))

# RITIRATA il 06/09, dopo la prova in VR. Dal 30/08 al 06/09 qui c'era
# LEGAL_SIMULTANEOUS_REQUESTED = {Dodge+Jab, Dodge+Hook}, aggiunta su
# richiesta per rimediare alla scarsita' quasi totale di schivate nella
# modalita' marker - con scritto qui accanto, per esteso, che non era
# verificata in VR e andava provata prima di fidarsene. E' stata provata:
# «impossibili da colpire - se schivo verso sinistra devo avere il colpo a
# sinistra perche' la destra e' occupata dall'ostacolo».
#
# E la correzione ovvia - mettere il pugno dalla parte libera - NON E'
# POSSIBILE. Il repertorio del gioco dice perche': tutte e dieci le schivate
# ufficiali stanno sul canale 2 (centro), mentre i pugni usano 0 e 4, cioe' i
# due lati. **La direzione della schivata non esiste nel formato**: la
# sceglie il gioco, e noi non possiamo ne' leggerla ne' imporla. Qualunque
# lato scegliessimo sarebbe quello occupato meta' delle volte.
#
# Lo stesso repertorio diceva gia' che il combo era estraneo al gioco, e
# sarebbe bastato guardarlo prima di aggiungerlo: nei 47 pattern l'unica
# coppia simultanea che esiste e' Block+Squat (12 volte), e ognuna delle
# dieci schivate ha un beat intero libero attorno. Il gioco non chiede mai
# di colpire mentre si schiva.
#
# Il problema che il combo voleva risolvere resta, e si risolve altrove:
# SQUAT_TO_DODGE_PROB in sidecar sandbox/engine.py trasforma la stessa quota
# di squat in schivate SOLE, e MIN_GAP_DODGE_BEATS (qui sotto) da' loro lo
# spazio.
LEGAL_SIMULTANEOUS = LEGAL_SIMULTANEOUS_MEASURED

# Il pavimento di 0.5 beat vale per le mosse di GAMBE (squat/schivata). Fra due
# colpi di BRACCIA il repertorio ufficiale non scende MAI sotto 1 beat pieno:
# misurato su tutte le coppie consecutive dei 45 pattern Normal - Jab->Jab
# (100 coppie), Hook->Jab, Hook->Hook, Uppercut->Jab... tutte con minimo 1.00,
# sia sullo stesso lato sia su lati diversi. Le uniche coppie a 0.5 sono
# Squat->Squat e Jab->Squat, cioe' quelle che coinvolgono le gambe.
# Il primo test in VR con soglia 0.5 lo ha confermato a orecchio: in Act A Fool
# restavano 21 coppie a 215ms percepite come "troppo vicine".
MIN_GAP_ARM_BEATS = 1.0

# Dopo un gancio o un montante SULLO STESSO LATO serve piu' recupero: sono
# movimenti ampi (rotatorio/verticale) da cui il braccio deve tornare in guardia
# prima di un altro colpo. Segnalato in VR il 2026-08-24 ("un gancio non puo'
# avere un diretto nello stesso braccio vicino della stessa quantita'"). Il
# repertorio non lo contraddice: ha pochissime coppie del genere, e
# Uppercut->Uppercut ha mediana 1.5 beat.
MIN_GAP_AFTER_SWING_BEATS = 1.5

# Il respiro attorno a una SCHIVATA, in beat. Misurato sul repertorio
# ufficiale: tutte e dieci le schivate hanno almeno un beat intero libero
# prima e dopo, e nessun pattern mette mai qualcos'altro nel loro stesso
# istante. Non e' stile: e' il tempo che serve a spostare il corpo di lato
# e tornare in guardia, e vale in tutte e due le direzioni.
MIN_GAP_DODGE_BEATS = 1.0

# Tolleranza per il jitter del rilevatore di accenti, in beat - vedi il
# commento su _fits() in enforce_playability. ~0.02 beat sono pochi
# millisecondi alla maggior parte dei tempi: assorbe l'imprecisione fisiologica
# di una misura audio reale senza allentare in modo percepibile i vincoli.
ONSET_JITTER_TOLERANCE_BEATS = 0.02

# Quanto una mossa puo' essere SPOSTATA in avanti per rispettare la distanza
# minima prima di rinunciare e scartarla ("dovra' spostarsi di poco"): spostare
# conserva il colpo, scartare lo perde, quindi si prova sempre prima a spostare.
MAX_SHIFT_BEATS = 1.0

ARM_MOVES = frozenset((MOVE_BLOCK, MOVE_JAB, MOVE_HOOK, MOVE_UPPERCUT))
SWING_MOVES = frozenset((MOVE_HOOK, MOVE_UPPERCUT))

# Mosse che richiedono un vero movimento del CORPO (scudo alzato, accosciata,
# schivata laterale) invece che solo del braccio - la deroga sidecar_min_gap_s
# in enforce_playability/_fits (vedi sotto) NON si applica quando una di
# queste e' coinvolta: e' pensata per lasciare l'utente libero di infittire
# PUGNI (jab/hook/uppercut) oltre la cadenza misurata, non per accorciare il
# recupero fisico reale di uno scudo o di uno squat. Bug reale in VR il
# 30/08: con lo slider abbassato aggressivamente, due Block consecutivi (dai
# marker dell'utente) finivano a meno di 200ms - "molto difficili" a detta
# dell'utente - perche' _required_gap_beats (che imporrebbe 1 beat pieno,
# vedi MIN_GAP_ARM_BEATS) veniva bypassato solo perche' ENTRAMBI i lati
# erano '_sidecar', a prescindere dal tipo di mossa.
OBSTACLE_MOVES = frozenset((MOVE_BLOCK, MOVE_SQUAT, MOVE_DODGE))


def _same_side(a, b):
    """Stessa colonna della griglia a 6 caselle (0/1 = un lato, 2/3 = centro,
    4/5 = l'altro): e' il miglior indicatore di "stesso braccio" disponibile,
    dato che il formato non registra quale mano tira - vedi [[boxvr-internals]]."""
    return a['moveChannel'] // 2 == b['moveChannel'] // 2


def _required_gap_beats(prev, cur):
    """Distanza minima in beat fra due mosse consecutive, per tipo e lato.

    Il recupero lungo (`MIN_GAP_ARM_BEATS`) vale solo per due colpi di braccia
    sullo STESSO lato: e' lo stesso braccio che deve tornare in posizione.
    Alternando i lati bastano `MIN_GAP_BEATS`, perche' le due braccia si
    muovono in parallelo.

    Corretto il 25/08: la versione precedente imponeva 1.0 beat a QUALUNQUE
    coppia di colpi di braccia, lato diverso compreso. Misurato sui 465 workout
    ufficiali, e' piu' severo del gioco stesso:

        lati DIVERSI  minimo 0.50 beat, 5° percentile 0.50, 9.5% sotto 0.75
        stesso lato   minimo 0.50 beat, 5° percentile 1.00, 3.6% sotto 0.75

    BoxVR usa colpi a mezzo beat su lati alternati in quasi un caso su dieci.
    Vietarlo rendeva **impossibile per costruzione** seguire un riff veloce: su
    Master Of Puppets gli accenti distano 0.58 e 0.51 beat, cioe' esattamente
    cio' che veniva scartato - il difetto segnalato in VR ("avrebbero potuto
    avere un altro colpo nel mezzo").

    Il vincolo sullo stesso lato resta intatto, ed e' quello che protegge
    davvero la giocabilita'.

    Aggiunto il 25/08 sera, dopo un vero riascolto in VR ("non posso avere un
    gancio o un montante vicinissimo dietro a un block"): **Block prima di un
    gancio/montante e' un caso a se'**, indipendente dal lato (Block e'
    sempre al centro, quindi _same_side lo classificherebbe sempre come "lato
    diverso" e gli darebbe solo 0.5 beat). Misurato sui 465 workout ufficiali:

        Block -> Hook/Uppercut   minimo 1.00 beat, 1° percentile 1.00 (quasi
                                  senza eccezioni - e' un vincolo duro)
        Block -> Jab             minimo 0.50 beat (si comporta come un
                                  braccio normale)

    Il gioco tratta un gancio/montante subito dopo un block come richiede
    tempo di preparazione, non solo di recupero - Block resta un braccio
    normale se quello che segue e' un Jab."""
    a, b = prev['moveType'], cur['moveType']
    # La schivata vuole il suo spazio, qualunque cosa le stia accanto e da
    # qualunque parte arrivi (marker dell'utente o pattern automatico).
    # Misurato sul repertorio ufficiale, dove ogni schivata ha un beat intero
    # libero prima e dopo. Segnalato in VR il 06/09, quando una schivata con
    # un pugno simultaneo si e' rivelata ineseguibile - vedi il commento su
    # LEGAL_SIMULTANEOUS.
    if MOVE_DODGE in (a, b):
        return MIN_GAP_DODGE_BEATS
    if a == MOVE_BLOCK and b in SWING_MOVES:
        return MIN_GAP_ARM_BEATS
    if a in ARM_MOVES and b in ARM_MOVES and _same_side(prev, cur):
        if a in SWING_MOVES:
            return MIN_GAP_AFTER_SWING_BEATS
        return MIN_GAP_ARM_BEATS
    return MIN_GAP_BEATS


def _grid_times(beats):
    """Griglia di posizioni valide: ogni beat piu' il punto a meta' fra due beat
    consecutivi. E' la risoluzione piu' fine che il gioco stesso usa (0.5 beat),
    quindi non inventa suddivisioni che il repertorio ufficiale non conosce."""
    ts = [b['_triggerTime'] for b in beats]
    grid = []
    for i, t in enumerate(ts):
        grid.append(t)
        if i + 1 < len(ts):
            grid.append((t + ts[i + 1]) / 2.0)
    return grid


def enforce_playability(actions, beats, min_gap_beats=MIN_GAP_BEATS, snap_to_grid=True,
                        sidecar_min_gap_s=None):
    """Rende una coreografia fisicamente eseguibile, in tre passaggi.

    `sidecar_min_gap_s` (30/08, bug reale corretto - vedi il commento dentro
    `_fits`): se dato, sostituisce `_required_gap_beats` (il recupero
    braccio pensato per le combo generate da NOI) con questa soglia,
    convertita in beat, ma SOLO per una coppia di azioni ENTRAMBE marcate
    '_sidecar' - due marker dell'utente, gia' passati dal loro filtro
    dedicato (sidecar sandbox/engine.py). Non tocca nessun'altra coppia
    (automatico-automatico, automatico-marker): quelle continuano a
    rispettare il vincolo di sempre.

    1. AGGANCIO ALLA GRIGLIA. Le mosse nate da un istante audio reale
       (raffica/veloce, vedi _apply_rhythm_events) avevano il timestamp grezzo
       dell'onset: fuori dalla griglia dei beat, quindi fuori tempo. Il test in
       VR del 2026-08-24 lo ha confermato in modo netto - i due brani percepiti
       come "molto fuori dal beat" erano esattamente i due con piu' colpi fuori
       griglia (Baddadan 37%, Act A Fool 27%), mentre le parti costruite sul
       repertorio (gia' quantizzate) suonavano "quasi a tempo di musica".
       Qui ogni mossa viene agganciata al punto di griglia piu' vicino.
    2. SIMULTANEITA' LEGALE. Dopo l'aggancio piu' mosse possono cadere sullo
       stesso istante: si tiene solo cio' che il gioco ammette davvero
       (LEGAL_SIMULTANEOUS), scartando il resto.
    3. DISTANZA MINIMA. Fra due istanti diversi devono passare almeno
       `min_gap_beats` beat.

    A parita' di conflitto si preferisce SEMPRE la mossa che viene dal
    repertorio ufficiale (quelle iniettate portano `_injected`): il pattern e'
    il linguaggio del gioco, l'iniezione e' una nostra aggiunta.

    `snap_to_grid=False` salta SOLO il passaggio 1, lasciando i colpi
    esattamente dove sono e mantenendo intatti i vincoli fisici (2 e 3).
    Serve quando gli istanti vengono da accenti musicali VERIFICATI e la
    precisione al millisecondo e' il punto - vedi il caso misurato sul riff di
    Master Of Puppets, dove gli accenti stanno a 0.559, 2.555, 3.136 e 3.646
    beat: le distanze sono 2.00, 0.58 e 0.51, cioe' **non multipli esatti di
    mezzo beat**, perche' e' un riff suonato a mano. La griglia li sposta di
    30-80ms e ne fa collidere due, che e' esattamente il difetto segnalato
    ("hai aggiunto altri due colpi ma senza contare mezza battuta").

    Il passaggio 3 (distanza minima) risolve le collisioni in QUATTRO livelli
    di priorita' (25/08: da due a tre quando le figure nostre e l'ancoraggio
    agli accenti hanno smesso di escludersi a vicenda per intere zone - vedi
    `skip_spans` rimosso da _apply_rhythm_events/_apply_section_accents;
    26/08: da tre a quattro per la modalita' sidecar, vedi sotto):

    1. azioni '_exact' E '_sidecar' - istanti confermati dall'UTENTE (sidecar
       sandbox/engine.py). Vincono SEMPRE, anche su un accento audio vicino:
       l'utente ha detto esplicitamente "qui", l'audio e' solo la nostra
       stima automatica di dove cade un accento.
    2. azioni '_exact' senza '_sidecar' - accenti audio veri, rilevati
       automaticamente. Mai spostate ne' scartate se non contro un altro
       accento vero (audio o sidecar) gia' piazzato.
    3. figure '_protected' (jab_combo/hook_accent/euclidean/chiusura di
       sezione). In conflitto, chi arriva prima nel brano ha la precedenza
       sull'istante originale, ma chi perde NON sparisce piu' (27/08): si
       prova a spostarla in avanti sulla griglia come al livello 4, si
       scarta solo se non c'e' posto entro MAX_SHIFT_BEATS.
    4. tutto il resto (sposta o scarta).

    Prima della correzione del 25/08 un'azione '_exact' non '_protected'
    finiva nell'ultimo livello e POTEVA essere spostata sulla griglia per far
    posto a una figura iniettata vicina - innocuo finche' `skip_spans` teneva
    le due cose lontane per intere sezioni, diventato un rischio reale appena
    rimosso quello.

    ATTENZIONE, il default resta True per un motivo misurato: il test in VR del
    24/08 ha giudicato "molto fuori dal beat" proprio i due brani con piu' colpi
    fuori griglia (Baddadan 37%, Act A Fool 27%). L'ipotesi da verificare e' che
    allora gli onset fossero imprecisi - rilevatore meno selettivo, senza soglia
    locale - non che la quantizzazione sia indispensabile. Finche' un test in VR
    non lo chiarisce, disattivarla e' una scelta esplicita di chi chiama, non il
    comportamento normale.
    """
    if not actions or not beats:
        return actions

    # La griglia serve SEMPRE, anche con snap_to_grid=False: le distanze
    # minime si misurano in posizioni di griglia (vedi il commento su
    # grid_index piu' sotto), non in secondi. Senza snap non ci si aggancia
    # sopra, ma la si continua a usare come righello.
    grid = _grid_times(beats)
    if not grid:
        return actions

    # 1. aggancio alla griglia (saltabile: vedi snap_to_grid nel docstring).
    # Le azioni marcate '_exact' (vedi _place_moves_on_onsets/_snap_to_onsets)
    # NON vengono mai riagganciate qui, a prescindere da snap_to_grid: sono
    # gia' sull'accento audio vero, e riagganciarle alla griglia le
    # riporterebbe indietro esattamente al difetto appena corretto - bug
    # reale misurato il 25/08 sera (0.330/1.440/2.020 invece degli accenti
    # veri 0.313/1.431/2.042, perche' questo stesso passaggio le rimetteva
    # sulla griglia subito dopo averle spostate).
    snapped = []
    if not snap_to_grid:
        snapped = [dict(a) for a in actions]
    else:
        for a in actions:
            if a.get('_exact'):
                snapped.append(dict(a))
                continue
            i = bisect.bisect_left(grid, a['startTime'])
            cand = [grid[j] for j in (i - 1, i) if 0 <= j < len(grid)]
            if not cand:
                continue
            t = min(cand, key=lambda g: abs(a['startTime'] - g))
            b = dict(a)
            b['startTime'] = float(t)
            b['beatNumber'] = _beat_number_at(beats, t)
            snapped.append(b)

    # 2. raggruppa per istante e riduci a un insieme ammesso
    buckets = {}
    for a in snapped:
        buckets.setdefault(round(a['startTime'], 6), []).append(a)

    def _resolve(group):
        """Riduce le mosse su uno stesso istante a un insieme eseguibile."""
        if len(group) == 1:
            return group
        # priorita' ASSOLUTA a un marker dell'utente (27/08 - bug reale
        # trovato correggendo le imprecisioni dei marker: se un marker viene
        # agganciato a un accento vero che l'automatico ha GIA' scelto per lo
        # stesso istante, prima di questa riga _resolve non sapeva nulla di
        # '_sidecar' e sceglieva "primary" solo guardando '_injected' - un
        # accento automatico non iniettato batteva il marker per puro ordine
        # di lista, il contrario della regola "un marker vince sempre" gia'
        # valida ovunque nel resto della funzione).
        sidecar_group = [a for a in group if a.get('_sidecar')]
        if sidecar_group:
            # 30/08 notte: due marker sidecar sullo STESSO istante non sono
            # piu' per forza una collisione da ridurre a uno solo - capita
            # quando la generazione stessa crea di proposito una coppia
            # simultanea (Dodge+Jab/Hook, richiesto esplicitamente - vedi
            # LEGAL_SIMULTANEOUS_REQUESTED e sidecar sandbox/engine.py). Se
            # sono davvero due e formano una combinazione legale si tengono
            # entrambi, altrimenti vince il primo come sempre (nessuna
            # collisione di questo tipo e' mai stata osservata fra marker
            # indipendenti, resta un ripiego prudente).
            if (len(sidecar_group) == 2 and
                    frozenset((sidecar_group[0]['moveType'], sidecar_group[1]['moveType']))
                    in LEGAL_SIMULTANEOUS):
                return sidecar_group
            return [sidecar_group[0]]
        # priorita' al repertorio: se c'e' una mossa non iniettata, comanda lei
        primary = next((a for a in group if not a.get('_injected')), group[0])
        partner = next((a for a in group if a is not primary and
                        frozenset((primary['moveType'], a['moveType'])) in LEGAL_SIMULTANEOUS), None)
        if partner is not None:
            return [primary, partner]
        return [primary]

    # 3. distanza minima: prima si prova a SPOSTARE in avanti sulla griglia,
    #    si scarta solo se non c'e' posto entro MAX_SHIFT_BEATS. Spostare
    #    conserva il colpo (e la sua musicalita' approssimata), scartare lo
    #    perde: "dovra' spostarsi di poco", non sparire.
    ts_beats = [b['_triggerTime'] for b in beats]
    beat_len = ((ts_beats[-1] - ts_beats[0]) / (len(ts_beats) - 1)
                if len(ts_beats) > 1 else 0.5)
    max_shift = beat_len * MAX_SHIFT_BEATS

    # Le FIGURE protette (combo di diretti) si piazzano per prime e non si
    # toccano: sono gia' costruite a distanza legale fra loro ed e' la loro
    # cadenza regolare a renderle riconoscibili. Tutto il resto si adatta
    # attorno. Senza questa precedenza le combo venivano spezzate: gli scarti
    # misurati alternavano 1 e 1.5 beat invece di restare costanti.
    placed = []                          # [(t, [azioni])] sempre ordinato

    # La distanza si misura in POSIZIONI DI GRIGLIA, non in secondi: i beat
    # reali non sono equidistanti (su Baddadan vanno da 300 a 480 ms contro
    # una media di 345), quindi confrontare con la durata media del beat
    # segnalava come "troppo vicini" colpi che stavano su beat consecutivi -
    # cioe' esattamente dove il gioco li mette. Un indice per mezzo-beat rende
    # il confronto esatto e immune a questa oscillazione.
    grid_index = {round(g, 6): i for i, g in enumerate(grid)}

    def _steps(t):
        """Posizione di `t` sulla griglia, come indice di mezzo-beat.

        Con snap_to_grid attivo l'istante e' esattamente su un punto di griglia
        e la ricerca esatta basta. Senza snap l'istante e' quello dell'accento
        musicale, che di norma NON coincide con un punto di griglia: si
        interpola fra i due punti adiacenti, cosi' la distanza minima resta
        misurabile con lo stesso righello invece di diventare None e far
        saltare il controllo."""
        exact = grid_index.get(round(t, 6))
        if exact is not None:
            return exact
        i = bisect.bisect_left(grid, t)
        if i <= 0:
            return 0.0
        if i >= len(grid):
            return float(len(grid) - 1)
        lo, hi = grid[i - 1], grid[i]
        span = hi - lo
        return (i - 1) + ((t - lo) / span if span > 0 else 0.0)

    def _fits(t, group):
        """La distanza da cio' che e' gia' piazzato e' rispettata?"""
        si = _steps(t)
        i = bisect.bisect_left([p[0] for p in placed], t)
        for j in (i - 1, i):
            if not (0 <= j < len(placed)):
                continue
            ot, og = placed[j]
            if abs(ot - t) < 1e-9:
                return False             # istante gia' occupato
            # l'ORDINE conta: il recupero lungo serve dopo un gancio/montante,
            # non prima. Passare la coppia al contrario faceva sfuggire proprio
            # il caso segnalato in VR (gancio seguito da diretto sullo stesso
            # lato a un solo beat).
            #
            # ECCEZIONE (30/08, bug reale segnalato: "la soglia minima
            # dell'utente non viene rispettata" - vero, ma non nel punto
            # dove sembrava): quando ENTRAMBI i lati del confronto sono
            # marker dell'utente ('_sidecar'), _required_gap_beats (il
            # recupero braccio dell'automatico, 0.5-1.5 beat, pensato per
            # COMBO GENERATE DA NOI) non e' la regola giusta - due marker
            # sono due decisioni INDIPENDENTI e deliberate dell'utente, gia'
            # passate dal loro filtro dedicato (sidecar sandbox/engine.py,
            # snap_and_filter_markers/min_gap_s) PRIMA di arrivare qui.
            # Applicare ANCHE il vincolo in beat li' sopra vanificava in
            # silenzio uno slider che l'utente aveva consapevolmente
            # abbassato (misurato: due marker a 90ms sopravvivevano al
            # filtro con min_gap_s=50ms ma sparivano comunque qui, a un
            # tempo dove 0.5 beat = 174ms > 90ms). `sidecar_min_gap_s`
            # (in secondi, convertito in passi di griglia con lo stesso
            # beat_len usato altrove in questa funzione) sostituisce
            # _required_gap_beats SOLO in questo caso - una coppia con
            # almeno un lato automatico continua a rispettare il recupero
            # braccio come sempre.
            #
            # ULTERIORE ECCEZIONE (30/08 sera, bug reale in VR - "non
            # permettere mai uno scudo subito dopo un altro scudo"): la
            # deroga sopra NON si applica se una delle due mosse e' uno
            # scudo/squat/schivata (OBSTACLE_MOVES) - richiedono un vero
            # movimento del corpo, non solo del braccio, e restano sempre
            # governate da _required_gap_beats (>= MIN_GAP_ARM_BEATS = 1
            # beat pieno per due scudi) anche quando entrambe le mosse sono
            # marker dell'utente. Lo slider resta libero di infittire solo
            # i PUGNI, per cui era stato pensato.
            if (sidecar_min_gap_s is not None
                    and all(a.get('_sidecar') for a in og) and all(a.get('_sidecar') for a in group)
                    and all(a['moveType'] not in OBSTACLE_MOVES for a in og)
                    and all(a['moveType'] not in OBSTACLE_MOVES for a in group)):
                need = sidecar_min_gap_s / beat_len
            elif ot < t:
                need = max(_required_gap_beats(p, c) for p in og for c in group)
            else:
                need = max(_required_gap_beats(p, c) for p in group for c in og)
            sj = _steps(ot)
            # Tolleranza per il jitter del rilevatore, SOLO quando almeno un
            # lato e' un accento audio vero ('_exact'): due timestamp reali
            # misurati indipendentemente non cadono mai a una distanza
            # teorica perfetta. Misurato il 25/08 sera sul riff di Master Of
            # Puppets: due accenti veri distavano 0.495 beat contro un minimo
            # ufficiale di ESATTAMENTE 0.500 (zero eccezioni su 89.418 coppie
            # misurate) - 3 millisecondi di scarto, piu' verosimilmente
            # imprecisione del rilevatore che un vincolo davvero violato. Le
            # posizioni a griglia restano a tolleranza piena (1e-9): sono
            # calcolate per interpolazione esatta, non hanno rumore di misura,
            # quindi una violazione li' e' sempre reale.
            eps = 2 * ONSET_JITTER_TOLERANCE_BEATS if (
                any(a.get('_exact') for a in group) or any(a.get('_exact') for a in og)
            ) else 1e-9
            if si is None or sj is None:            # fuori griglia: ripiego sul tempo
                if abs(t - ot) < need * beat_len - 1e-6:
                    return False
            elif abs(si - sj) < need * 2 - eps:      # 2 passi di griglia = 1 beat
                return False
        return True

    # Livello 1: accenti VERI ('_exact'), in due sotto-livelli. Mai spostati,
    # mai ceduti a qualunque altra cosa - sono la realta' misurata (audio o
    # dito dell'utente), non una nostra costruzione. Scartati SOLO se in vero
    # conflitto con un altro accento vero gia' piazzato.
    #
    # 1a. Istanti confermati dall'UTENTE (sidecar, '_sidecar'), sempre prima -
    # vincono anche su un accento audio vicino, perche' l'utente ha detto
    # esplicitamente "qui" mentre l'audio e' solo la nostra stima automatica
    # di dove cade un accento. Deciso il 26/08: "quelli dell'utente devono
    # essere sempre" (presenti), non solo probabili.
    for t in sorted(buckets):
        group = _resolve(buckets[t])
        if any(a.get('_sidecar') for a in group) and _fits(t, group):
            bisect.insort(placed, (t, group), key=lambda p: p[0])

    # 1b. Accenti audio veri rilevati automaticamente - stesso trattamento,
    # ma dopo: un accento audio che cade troppo vicino a un istante gia'
    # confermato dall'utente cede il passo, non il contrario.
    for t in sorted(buckets):
        group = _resolve(buckets[t])
        if any(a.get('_sidecar') for a in group):
            continue                     # gia' valutato sopra (1a)
        if any(a.get('_exact') for a in group) and _fits(t, group):
            bisect.insort(placed, (t, group), key=lambda p: p[0])

    # Livello 2: figure protette (jab_combo/hook_accent/euclidean), controllate
    # anche fra loro E contro gli accenti veri gia' piazzati sopra: due figure
    # adiacenti con fase diversa (una sul beat, una in levare) finirebbero a
    # mezzo beat l'una dall'altra, che fra colpi di braccia non e' eseguibile.
    #
    # In conflitto, PRIMA di rinunciare, si prova a spostare in avanti sulla
    # griglia (27/08 - la stessa ricerca gia' usata al livello 3 qui sotto,
    # non piu' riservata alle mosse non protette). Misurato subito prima:
    # con quattro famiglie di figure ora attive insieme (jab_combo/hook_accent/
    # euclidee/chiusura di sezione, quest'ultima aggiunta il 26/08), il vecchio
    # "vince chi arriva prima, l'altro sparisce" scartava il 49-73% dei colpi
    # protetti su tre brani di riferimento - molto peggio del 7-22% misurato
    # il 24/08 con solo due famiglie. Spostare di un passo di griglia invece
    # di scartare rende la cadenza della figura leggermente meno regolare nel
    # solo istante spostato, ma un colpo spostato resta un colpo suonato -
    # nettamente meglio di uno perso, ed enforce_playability continua a
    # garantire che il nuovo istante sia comunque eseguibile.
    for t in sorted(buckets):
        group = _resolve(buckets[t])
        if any(a.get('_exact') for a in group):
            continue                     # gia' valutata sopra (livello 1)
        if not any(a.get('_protected') for a in group):
            continue
        target = t if _fits(t, group) else None
        if target is None:
            i = bisect.bisect_left(grid, t)
            for g in grid[i:]:
                if g - t > max_shift + 1e-9:
                    break
                if _fits(g, group):
                    target = g
                    break
        if target is None:
            continue                     # nessuno slot utile vicino: si rinuncia
        if target != t:
            for a in group:
                a['startTime'] = float(target)
                a['beatNumber'] = _beat_number_at(beats, target)
        bisect.insort(placed, (target, group), key=lambda p: p[0])

    # Livello 3: tutto il resto (mosse del pattern a griglia fissa, mai
    # protette). Puo' essere spostato in avanti o scartato per fare posto ai
    # livelli sopra.
    for t in sorted(buckets):
        group = _resolve(buckets[t])
        if any(a.get('_exact') for a in group) or any(a.get('_protected') for a in group):
            continue                     # gia' valutate sopra
        target = t if _fits(t, group) else None
        if target is None:
            i = bisect.bisect_left(grid, t)
            for g in grid[i:]:
                if g - t > max_shift + 1e-9:
                    break
                if _fits(g, group):
                    target = g
                    break
        if target is None:
            continue                     # nessuno slot utile vicino: si rinuncia
        if target != t:
            for a in group:
                a['startTime'] = float(target)
                a['beatNumber'] = _beat_number_at(beats, target)
        bisect.insort(placed, (target, group), key=lambda p: p[0])

    result = []
    for _, group in placed:
        result.extend(group)
    return result


def _beat_number_at(beats, t):
    """Indice di battuta (frazionario) all'istante t - l'inverso di come
    build_move_actions risolve normalmente idx -> tempo. Serve per dare un
    beatNumber sensato alle azioni piazzate su un istante audio reale
    (raffica/veloce) invece che su una posizione di pattern gia' nota."""
    n = len(beats)
    if n == 0:
        return 0.0
    if t <= beats[0]['_triggerTime']:
        return 0.0
    for i in range(n - 1):
        t0, t1 = beats[i]['_triggerTime'], beats[i + 1]['_triggerTime']
        if t0 <= t < t1:
            return i + ((t - t0) / (t1 - t0) if t1 > t0 else 0.0)
    return float(n - 1)


# quanto dettaglio di una RAFFICA arriva a ogni preset - non inventato,
# ricalca un principio osservato 2026-08-23 confrontando le difficolta' di
# una mappa Beat Saber generata da BeatSage per lo stesso identico "sparo"
# isolato di Act A Fool: Normal/Hard lo saltano (silenzio), Expert ne mostra
# una parte, ExpertPlus lo mostra per intero come un accordo - piu' aumenta
# la difficolta', piu' dettaglio viene rivelato nello STESSO istante, non
# e' solo "piu' densita' in generale". Resta a soglia netta (non continua)
# perche' una raffica e' per natura un evento breve e isolato dentro un
# respiro gia' silenzioso - poco senso ha "sfumarne" una parte.
# `None` = salta del tutto, un intero = tiene un colpo ogni N di quelli
# rilevati.
_BURST_STRIDE = {'light': None, 'medium': 2, 'high': 1}
# quanto puo' "spingere" al massimo la sezione veloce, per preset - tetto
# superiore della probabilita' continua sotto, non piu' uno stride fisso.
_FAST_CEILING = {'light': 0.30, 'medium': 0.65, 'high': 1.0}

# Quanti colpi ha una raffica, per preset. E' una FIGURA riconoscibile (colpi
# alternati su beat consecutivi), non colpi sparsi sugli onset: segnalato in VR
# il 2026-08-24 che i momenti belli erano proprio "i tris di colpi in sequenza"
# e "i momenti di ripetizione dei diretti", mentre altrove sembrava "una
# classica coreografia BoxVR" - cioe' l'iniezione non si faceva sentire come
# gesto proprio.
_COMBO_LENGTH = {'light': 2, 'medium': 3, 'high': 4}

# Quota di raffiche che usa un ritmo euclideo invece del solito _jab_combo -
# vedi _EUCLIDEAN_PATTERNS piu' sotto e il commento dove viene usata. Bassa
# apposta: la raffica di diretti e' gia' validata in VR ("i momenti belli
# erano proprio i tris di colpi in sequenza"), qui si aggiunge varieta' senza
# sostituirla. Cresce col preset come tutto il resto dell'iniezione ritmica.
_EUCLIDEAN_BURST_PROB = {'light': 0.15, 'medium': 0.30, 'high': 0.45}

# Matrice di transizione Jab/Hook/Uppercut, misurata sui 465 workout ufficiali
# (26/08 - fase 3 del piano di training, "quale mossa esatta in che sequenza",
# vedi STATO E ROADMAP.md). 72.729 transizioni braccio->braccio pure (Block/
# Squat/Dodge saltate nel conteggio: la sequenza "vista" da un braccio ignora
# l'intervallo fisico, non lo azzera). Serve a dare alle NOSTRE figure
# (_jab_combo, _hook_accent) una sequenza di tipi presa dai dati reali invece
# di "sempre lo stesso colpo per tutta la raffica" - la richiesta esplicita
# dell'utente era proprio "dopo due Jab il gioco alterna spesso verso un Hook,
# non un altro Jab all'infinito". Ogni riga somma a 1.0.
ARM_TRANSITION_PROBS = {
    MOVE_JAB:      {MOVE_JAB: 0.738, MOVE_HOOK: 0.142, MOVE_UPPERCUT: 0.120},
    MOVE_HOOK:     {MOVE_JAB: 0.391, MOVE_HOOK: 0.404, MOVE_UPPERCUT: 0.205},
    MOVE_UPPERCUT: {MOVE_JAB: 0.375, MOVE_HOOK: 0.147, MOVE_UPPERCUT: 0.478},
}


# Quanto spesso una mossa di BRACCIA del pattern ufficiale viene sostituita
# con una campionata da ARM_TRANSITION_PROBS invece di essere copiata
# letteralmente - la "struttura nostra" chiesta esplicitamente dall'utente
# (26/08): "avevamo detto di creare una tua struttura di colpi oltre a quella
# gia' esistente per variare le coreografie", cioe' NON limitarsi a replicare
# meglio BoxVR.
#
# Perche' bassa e graduale, non aggressiva: i pattern ufficiali sono anche
# cio' che rende le combo SENSATE DA TIRARE (scritte da chi conosce il
# pugilato) - variarli troppo darebbe combo plausibili sulla carta ma scomode
# col corpo, che e' esattamente il tipo di difetto che solo la VR rivela.
# Cresce col preset come tutto il resto, e va validata in VR prima di alzarla.
#
# Perche' Squat/Dodge restano SEMPRE invariate: hanno vincoli di corsia
# rigidi (sempre CH_CENTER, misurato 100% sui 465 workout) e ARM_TRANSITION_PROBS
# non le copre - scambiarle darebbe corsie illegali senza nemmeno un tipo di
# ricambio misurato.
#
# Lo SCUDO (Block) invece, dal 26/08, PUO' essere variato in un colpo di
# braccia laterale (stessa probabilita' e stesso meccanismo qui sopra) - e'
# la causa unica dietro tutti e tre gli scarti misurati sui 194 brani ufficiali
# (vedi STATO E ROADMAP.md, "Perche' il mix e' sbilanciato"): riproduciamo
# fedelmente la quota di Block del CATALOGO (10.2%), ma i workout VERI di
# BoxVR ne usano meno della meta' (4.7%) - e' il catalogo a essere sovra-
# rappresentato in Block, non il nostro codice a sbagliare. Anche lo scudo e'
# tecnicamente "centrale" come Squat/Dodge (corsia fissa nel pattern), ma qui
# la corsia NON e' un vincolo fisico del gioco (a differenza di Squat/Dodge):
# e' solo la scelta del pattern scritto a mano, quindi si puo' ricalcolare -
# chi chiama _vary_pattern_move DEVE farlo quando il tipo restituito e'
# diverso da MOVE_BLOCK (vedi i due punti di chiamata: nel percorso ancorato
# agli accenti la corsia e' gia' ricalcolata dinamicamente da CENTRO_MOVES,
# nel percorso a griglia va assegnata esplicitamente).
PATTERN_VARIATION_PROB = {'light': 0.10, 'medium': 0.20, 'high': 0.30}


def _vary_pattern_move(move_type, prev_arm_type, rng, prob):
    """Restituisce il tipo di mossa da usare davvero al posto di quello che il
    pattern ufficiale prevedeva in questa posizione.

    Con probabilita' `prob` (vedi PATTERN_VARIATION_PROB) sostituisce una
    mossa di braccia CON UN'ALTRA mossa di braccia, campionata dalla matrice
    di transizione reale, condizionata sull'ultima mossa di braccia
    EFFETTIVAMENTE piazzata (non su quella che il pattern prevedeva): cosi'
    la variazione segue comunque le statistiche vere del gioco invece di
    essere casuale, e resta coerente con quello che il giocatore ha appena
    tirato. Dal 26/08 lo SCUDO (Block) e' incluso fra le mosse variabili -
    vedi il commento sopra PATTERN_VARIATION_PROB per il perche'.

    Squat e Dodge tornano SEMPRE invariati (vincoli di corsia fisici, non
    scelte di pattern). Il chiamante resta responsabile della corsia quando
    il tipo restituito e' MOVE_BLOCK->qualcos'altro (la corsia centrale del
    pattern non e' piu' valida) e dei vincoli fisici (enforce_playability a
    valle, piu' la forzatura del Jab sugli spazi stretti dove prevista)."""
    if move_type not in ARM_MOVES:
        return move_type          # Squat/Dodge: vincoli di corsia fisici, mai variati
    if prob <= 0 or rng.random() >= prob:
        return move_type
    seed_type = prev_arm_type or (MOVE_JAB if move_type == MOVE_BLOCK else move_type)
    return _sample_next_arm_move(seed_type, rng)


def _sample_next_arm_move(prev_move, rng):
    """Prossimo tipo di colpo di braccia, campionato dalla distribuzione REALE
    (ARM_TRANSITION_PROBS) condizionata sul colpo precedente - non un tipo
    fisso per tutta la figura. Non tocca il LATO (gia' deciso altrove, sempre
    alternato): qui si decide solo Jab/Hook/Uppercut.

    La sicurezza fisica non dipende da questa scelta: sia _jab_combo che
    _hook_accent alternano il lato a ogni colpo, quindi anche nel caso
    peggiore (due ganci/montanti consecutivi campionati di fila) restano su
    lati diversi e bastano 0.5 beat - ampiamente coperti dalla cadenza fissa
    di entrambe le figure (1 beat/4 beat). Un gancio o montante sullo STESSO
    lato puo' capitare solo a due posizioni di distanza (k e k+2), dove il
    doppio della cadenza e' comunque sopra il minimo di recupero
    (MIN_GAP_AFTER_SWING_BEATS=1.5)."""
    probs = ARM_TRANSITION_PROBS.get(prev_move, ARM_TRANSITION_PROBS[MOVE_JAB])
    r = rng.random()
    acc = 0.0
    for move_type, p in probs.items():
        acc += p
        if r < acc:
            return move_type
    return MOVE_JAB   # ripiego per arrotondamento float, non dovrebbe mai servire


def _jab_combo(beats, t_start, n, start_side=0, rng=None):
    """`n` colpi di braccia alternati a UN BEAT DI DISTANZA, agganciati alla
    posizione di griglia piu' vicina a `t_start` - che puo' essere un beat
    oppure un MEZZO beat. Un beat pieno di distanza e' esattamente il minimo
    che il repertorio ufficiale usa fra due colpi di braccia, quindi la
    figura e' eseguibile per costruzione e non verra' diradata da
    enforce_playability.

    La figura APRE sempre con un Jab (l'evento che la fa scattare - respiro/
    veloce - e' un fatto di RITMO, non di tipo), poi ogni colpo successivo e'
    campionato da ARM_TRANSITION_PROBS condizionato sul precedente - vedi
    _sample_next_arm_move. Prima del 26/08 erano SEMPRE Jab; corretto su
    richiesta esplicita dopo aver misurato la sequenza vera nei 465 workout
    ufficiali.

    La fase la detta la musica: se l'attacco sonoro rilevato cade piu' vicino al
    mezzo beat che al beat, l'intera figura parte IN LEVARE e resta sincopata.
    Serve perche' il repertorio di BoxVR non sincopa mai i colpi di braccia
    (misurato: 490 azioni su 550 a offset 0, e le uniche fuori battere sono
    squat), mentre i pugni sincopati sono fra le cose piu' divertenti secondo il
    test in VR del 2026-08-24 - vanno quindi costruiti da noi, non pescati."""
    ts = [b['_triggerTime'] for b in beats]
    if len(ts) < 2:
        return []
    rng = rng or random.Random("jab_combo_fallback_seed")
    grid = _grid_times(beats)             # beat + mezzi beat, alternati
    i = bisect.bisect_left(grid, t_start)
    if i > 0 and (i >= len(grid) or abs(grid[i - 1] - t_start) <= abs(grid[i] - t_start)):
        i -= 1
    out = []
    move_type = MOVE_JAB
    for k in range(n):
        j = i + k * 2                     # 2 passi di griglia = 1 beat
        if j >= len(grid):
            break
        if k > 0:
            move_type = _sample_next_arm_move(move_type, rng)
        t = grid[j]
        out.append({
            'startTime': float(t),
            'beatNumber': _beat_number_at(beats, t),
            'moveType': move_type,
            'moveChannel': CH_FRONT if (k + start_side) % 2 == 0 else CH_BACK,
            '_injected': True,
            # una figura ha senso solo se resta INTATTA: enforce_playability non
            # deve spostarla sui mezzi beat per far posto ad altro, altrimenti la
            # cadenza regolare (che e' tutto il punto) si spezza in 1 / 1.5 beat
            # alternati - misurato accadere prima di questa protezione.
            '_protected': True,
            '_figure': 'arm_combo',   # tag di provenienza, solo per audit/debug
        })
    return out


# Ganci radi che punteggiano l'APERTURA di una sezione piu' carica, il
# contrario della raffica di diretti (densa, riempie). "gancio/-/-/-/gancio"
# nella nota della roadmap 2026-08-24: 4 beat vuoti fra un gancio e il
# successivo. Lato alternato cosi' resta eseguibile anche se gap_beats
# scendesse sotto MIN_GAP_AFTER_SWING_BEATS.
_HOOK_ACCENT_GAP_BEATS = 4
_HOOK_ACCENT_LENGTH = {'light': 2, 'medium': 2, 'high': 3}
# Beat minimi fra un accento e il successivo: su una successione di segmenti
# brevi che salgono ripetutamente, senza questo limite l'accento perderebbe il
# suo scopo (punteggiare un momento raro) diventando un'altra raffica.
_MIN_SECTION_ACCENT_GAP_BEATS = 8


def _hook_accent(beats, t_start, n, start_side=0, gap_beats=_HOOK_ACCENT_GAP_BEATS, rng=None):
    """`n` colpi distanziati di `gap_beats` beat l'uno dall'altro, agganciati
    alla griglia piu' vicina a `t_start`. Vedi _HOOK_ACCENT_GAP_BEATS sopra per
    il perche' della cadenza rada invece che densa come _jab_combo.

    APRE sempre con un gancio (e' la sua identita': l'accento che punteggia
    l'apertura di una sezione), poi ogni colpo successivo e' campionato da
    ARM_TRANSITION_PROBS condizionato sul precedente, come in _jab_combo -
    vedi _sample_next_arm_move. Prima del 26/08 erano SEMPRE ganci."""
    ts = [b['_triggerTime'] for b in beats]
    if len(ts) < 2:
        return []
    rng = rng or random.Random("hook_accent_fallback_seed")
    grid = _grid_times(beats)
    i = bisect.bisect_left(grid, t_start)
    if i > 0 and (i >= len(grid) or abs(grid[i - 1] - t_start) <= abs(grid[i] - t_start)):
        i -= 1
    out = []
    move_type = MOVE_HOOK
    for k in range(n):
        j = i + k * gap_beats * 2         # 2 passi di griglia = 1 beat
        if j >= len(grid):
            break
        if k > 0:
            move_type = _sample_next_arm_move(move_type, rng)
        t = grid[j]
        out.append({
            'startTime': float(t),
            'beatNumber': _beat_number_at(beats, t),
            'moveType': move_type,
            'moveChannel': CH_FRONT if (k + start_side) % 2 == 0 else CH_BACK,
            '_injected': True,
            '_protected': True,
            '_figure': 'hook_accent',
        })
    return out


def _strip_overlaps(kept, injected, ts_beats):
    """Toglie da `kept` le azioni del pattern che cadono dentro la durata delle
    figure di `injected`, cosi' non si accavallano (misurato causare "troppi
    colpi sovrapposti" quando mancava, vedi _apply_rhythm_events).

    Le azioni '_exact' (accento audio vero) non vengono mai tolte da qui:
    sono gia' precise quanto una figura iniettata, spesso di piu' - toglierle
    per far posto a una figura ancorata al solo inizio dell'evento le
    sostituiva con qualcosa di meno preciso, silenziosamente."""
    if not injected:
        return kept
    spans = [c['startTime'] for c in injected]
    span_set = set(spans)
    lo, hi = min(spans), max(spans)
    beat_len = ((ts_beats[-1] - ts_beats[0]) / (len(ts_beats) - 1)
                if len(ts_beats) > 1 else 0.5)
    return [a for a in kept
            if a.get('_exact')
            or not (lo - beat_len * 0.5 <= a['startTime'] <= hi + beat_len * 0.5
                    and any(abs(a['startTime'] - t) < beat_len * 0.9 for t in span_set))]


def _apply_section_accents(actions, segs, intensities, beats, preset=DEFAULT_PRESET, rng=None):
    """Punteggia i confini di sezione con un accento di ganci radi: APERTURA
    su ogni sezione che SALE di intensita' rispetto all'ultima sezione attiva
    (o la primissima del brano), CHIUSURA sulla fine di ogni sezione che sta
    per SCENDERE - la figura "di apertura/chiusura sezione" della roadmap
    (DA FARE #1, 2026-08-24 apertura; #2, 26/08 chiusura). Sono eventi
    isolati e strutturali (nascono dal confine fra segmenti), non audio come
    raffica/veloce - per questo sono un passaggio separato da
    _apply_rhythm_events invece di un altro `event.type` li' dentro:
    silenziare un accento per "respiro" lo romperebbe, essendo gia' un
    momento raro per costruzione.

    La chiusura punteggia la FINE della sezione che si sta affievolendo
    (le sue ultime `n_hooks` posizioni a `gap_beats` di distanza, non
    l'inizio della sezione piu' debole che segue) - un ultimo accento prima
    che il brano si allenti, non un benvenuto alla sezione piu' debole.
    Condivide `_MIN_SECTION_ACCENT_GAP_BEATS` con l'apertura (un solo
    contatore): sono la stessa famiglia di eventi rari, non due quote
    separate. Un vero silenzio (intensita' 0) interrompe la sequenza -
    non ha senso "chiudere" una sezione attiva quando la si compara solo a
    un vuoto prima o dopo.

    Possono cadere ANCHE dentro un segmento gia' ancorato agli accenti audio
    veri (_place_moves_on_onsets) - corretto il 25/08, non piu' escluso a
    priori con `skip_spans`. Sono '_protected' ma sotto le azioni '_exact'
    nella scala di priorita' di enforce_playability: se cadono esattamente su
    un accento vero gia' occupato, l'accento vero vince e l'accento di
    sezione si scarta - non serve piu' evitarlo qui a monte. Nota: apertura e
    chiusura possono in teoria collidere fra loro su un confine di sezione
    molto corto (la chiusura della sezione N finisce vicino a dove apre la
    sezione N+1) - in quel caso vince chi viene valutato prima
    (earliest-wins, lo stesso meccanismo gia' usato ovunque per le figure
    protette), non ancora un criterio di scelta piu' fine."""
    if 'hook' not in INTENSITY_PRESETS.get(preset, {}).get('moves', ()):
        return actions          # preset senza ganci (nessuno oggi, ma resta corretto se cambiasse)
    rng = rng or random.Random("section_accent_fallback_seed")
    ts_beats = [b['_triggerTime'] for b in beats]
    if len(ts_beats) < 2:
        return actions
    n_hooks = _HOOK_ACCENT_LENGTH.get(preset, 2)
    n_beats_total = len(beats)

    injected = []
    prev_intensity = None
    prev_seg = None
    last_accent_beat = None
    for si, seg in enumerate(segs):
        intensity = intensities[si] if si < len(intensities) else 0
        if intensity <= 0:
            prev_intensity = None
            prev_seg = None
            continue
        is_climb = prev_intensity is None or intensity > prev_intensity
        is_descent = prev_intensity is not None and intensity < prev_intensity

        if is_descent and prev_seg is not None:
            end_beat = min(prev_seg['_startBeatIndex'] + prev_seg['_numBeats'], n_beats_total - 1)
            close_beat = max(prev_seg['_startBeatIndex'], end_beat - (n_hooks - 1) * _HOOK_ACCENT_GAP_BEATS)
            if last_accent_beat is None or close_beat - last_accent_beat >= _MIN_SECTION_ACCENT_GAP_BEATS:
                t_close = beats[close_beat]['_triggerTime']
                last_accent_beat = close_beat
                fig = _hook_accent(beats, t_close, n_hooks, start_side=rng.randint(0, 1), rng=rng)
                for a in fig:
                    a['_figure'] = 'section_close'
                injected.extend(fig)

        if is_climb:
            start_beat = seg['_startBeatIndex']
            if start_beat < n_beats_total and (
                    last_accent_beat is None or start_beat - last_accent_beat >= _MIN_SECTION_ACCENT_GAP_BEATS):
                t_start = beats[start_beat]['_triggerTime']
                last_accent_beat = start_beat
                injected.extend(_hook_accent(beats, t_start, n_hooks, start_side=rng.randint(0, 1), rng=rng))

        prev_intensity = intensity
        prev_seg = seg

    if not injected:
        return actions
    kept = _strip_overlaps(actions, injected, ts_beats)
    result = kept + injected
    result.sort(key=lambda a: a['startTime'])
    return result


# --- ritmi euclidei: terza famiglia di figure, 2026-08-24 -------------------
#
# Origine: l'utente ha chiesto se esiste una tecnica generica per "riempire i
# vuoti senza perdere il ritmo" invece di inventare a mano ogni figura, come
# fatto finora per _jab_combo e _hook_accent. Risposta trovata nella
# letteratura musicale: l'algoritmo di Euclide/Bjorklund, che distribuisce k
# colpi su n posizioni nel modo PIU' UNIFORME possibile - non a caso, non
# ammassati. E' l'algoritmo dietro pattern reali come il tresillo cubano
# (E(3,8) = 10010010, verificato byte per byte contro l'implementazione di
# riferimento https://github.com/brianhouse/bjorklund). Ruotare lo stesso
# pattern (cambiare da quale colpo si parte) sposta gli accenti rispetto al
# beat - lo stesso principio gia' usato a mano in _jab_combo per la sincope,
# qui generalizzato a intere famiglie di figure diverse invece di una sola
# forma (diretti fitti) o l'altra (ganci radi).

def _bjorklund(n_pulses, n_steps):
    """Algoritmo di Bjorklund: distribuisce `n_pulses` colpi su `n_steps`
    posizioni nel modo piu' uniforme possibile. Ritorna una lista di 0/1 lunga
    n_steps, ruotata cosi' che il primo passo sia sempre un colpo (posizione
    0). Porting diretto dell'implementazione di riferimento (vedi sopra) -
    non reinventata da zero apposta, per non rischiare un bug sottile in un
    algoritmo che ha gia' un'implementazione nota e verificata."""
    if n_pulses <= 0:
        return [0] * n_steps
    if n_pulses >= n_steps:
        return [1] * n_steps
    pattern = []
    counts = []
    remainders = [n_pulses]
    divisor = n_steps - n_pulses
    level = 0
    while True:
        counts.append(divisor // remainders[level])
        remainders.append(divisor % remainders[level])
        divisor = remainders[level]
        level += 1
        if remainders[level] <= 1:
            break
    counts.append(divisor)

    def build(lvl):
        if lvl == -1:
            pattern.append(0)
        elif lvl == -2:
            pattern.append(1)
        else:
            for _ in range(counts[lvl]):
                build(lvl - 1)
            if remainders[lvl] != 0:
                build(lvl - 2)

    build(level)
    i = pattern.index(1)
    return pattern[i:] + pattern[:i]


# Catalogo di pattern con nome, non parametri liberi a runtime: stessa scelta
# gia' fatta per _COMBO_LENGTH/_HOOK_ACCENT_LENGTH, un pugno di forme tarate
# invece di un sistema generico che potrebbe produrre combinazioni mai
# verificate. Ogni voce e' (k, n, beat_per_step, mossa_accento) - GIA'
# verificata qui sotto (vedi _EUCLIDEAN_PATTERNS_VALID) rispettare
# MIN_GAP_ARM_BEATS anche nel caso peggiore (tutti i colpi di braccia): non e'
# affidato al calcolo a mano, che aveva gia' sbagliato altrove in questo
# progetto (vedi le distanze misurate in secondi invece che in passi di
# griglia) - si misura lo scarto minimo reale con lo stesso metodo usato da
# enforce_playability._steps.
_EUCLIDEAN_PATTERNS = {
    # tresillo, E(3,8) su un ciclo di 4 beat (0.5 beat/passo): 10010010,
    # gap 1.5/1.5/1 beat - il piu' "cubano" dei tre, primo colpo di ogni
    # gruppo accentato a Hook, gli altri Jab.
    'tresillo': {'k': 3, 'n': 8, 'beat_per_step': 0.5},
    # E(5,8) su un ciclo di 8 beat (1 beat/passo, serve piu' largo o scende
    # sotto 1 beat fra due colpi di braccia): 10110110, gap 2/1/2/1/2.
    'cinquillo_largo': {'k': 5, 'n': 8, 'beat_per_step': 1.0},
    # shiko, E(2,5) su un ciclo di 5 beat: 10100, gap 2/3 - il piu' rado,
    # vicino nello spirito a _hook_accent ma con fase diversa.
    'shiko': {'k': 2, 'n': 5, 'beat_per_step': 1.0},
}


def _euclidean_pattern_gap_beats(name):
    """Scarto minimo REALE (in beat) fra due colpi consecutivi del pattern
    (incluso l'avvolgimento fine-inizio), misurato sul pattern effettivo -
    non assunto. Usato sia per validare il catalogo sia da chi decide se un
    pattern e' adatto a un dato tipo di mossa."""
    spec = _EUCLIDEAN_PATTERNS[name]
    steps = [i for i, v in enumerate(_bjorklund(spec['k'], spec['n'])) if v]
    if len(steps) < 2:
        return spec['n'] * spec['beat_per_step']
    gaps = [(steps[i + 1] - steps[i]) * spec['beat_per_step'] for i in range(len(steps) - 1)]
    gaps.append((spec['n'] - steps[-1] + steps[0]) * spec['beat_per_step'])
    return min(gaps)


# Quale colpo FORTE usare sugli accenti di un ritmo euclideo. Prima era
# sempre Hook; dal 26/08 si campiona fra i due colpi "ampi" con le proporzioni
# reali misurate sui 465 workout ufficiali (Hook 16.6%, Uppercut 18.2% del
# totale -> 48/52 fra i soli due). Motivo, oltre alla varieta' chiesta
# dall'utente: le figure euclidee erano l'ultimo punto della pipeline che
# usava il gancio in modo fisso, e il gancio risultava gia' sovra-usato
# rispetto a BoxVR vero nel confronto diretto del 26/08.
#
# Perche' e' sicuro variare QUI ma non ovunque: negli accenti cade il colpo
# preceduto dallo scarto PIU' LUNGO del pattern (e' la definizione di
# accento in _euclidean_figure), cioe' esattamente le posizioni con piu'
# spazio - quelle dove un colpo ampio e' eseguibile. Le posizioni strette
# restano Jab, invariate. La struttura forte/debole del pattern non cambia:
# cambia solo QUALE colpo forte.
_EUCLIDEAN_ACCENT_PROBS = {MOVE_HOOK: 0.477, MOVE_UPPERCUT: 0.523}


def _euclidean_figure(beats, t_start, pattern_name, start_side=0,
                       accent_move=None, fill_move=MOVE_JAB, rng=None):
    """Un colpo per ogni impulso del pattern euclideo `pattern_name`,
    agganciato alla griglia piu' vicina a `t_start` come le altre figure. Il
    PRIMO colpo di ogni "gruppo" (quello preceduto da uno scarto piu' lungo
    della media, cioe' l'inizio di una cellula ritmica: es. nel tresillo
    10010010 sono gli indici 0,3,6) prende un colpo AMPIO, per dare al
    pattern lo stesso carattere forte/debole che ha nella musica reale - gli
    altri `fill_move` (Jab). Lato alternato come le altre figure.

    `accent_move`: se dato, e' il colpo forte fisso da usare (comportamento
    storico, usato dai test). Se None - il caso normale dal 26/08 - viene
    campionato per ogni figura da `_EUCLIDEAN_ACCENT_PROBS`, cosi' due
    occorrenze dello stesso pattern euclideo nello stesso brano non sono
    piu' identiche. Campionato UNA volta per figura, non per colpo: dentro
    una singola cellula ritmica il colpo forte resta lo stesso, che e' cio'
    che la rende riconoscibile come figura."""
    spec = _EUCLIDEAN_PATTERNS[pattern_name]
    pulses = _bjorklund(spec['k'], spec['n'])
    steps = [i for i, v in enumerate(pulses) if v]
    if not steps:
        return []
    if accent_move is None:
        rng = rng or random.Random("euclidean_accent_fallback_seed")
        r = rng.random()
        acc = 0.0
        accent_move = MOVE_HOOK
        for mt, p in _EUCLIDEAN_ACCENT_PROBS.items():
            acc += p
            if r < acc:
                accent_move = mt
                break
    gaps_before = [steps[0] + spec['n'] - steps[-1]] + [steps[j] - steps[j - 1] for j in range(1, len(steps))]
    avg_gap = spec['n'] / len(steps)

    ts = [b['_triggerTime'] for b in beats]
    if len(ts) < 2:
        return []
    grid = _grid_times(beats)
    i0 = bisect.bisect_left(grid, t_start)
    if i0 > 0 and (i0 >= len(grid) or abs(grid[i0 - 1] - t_start) <= abs(grid[i0] - t_start)):
        i0 -= 1

    out = []
    for k, step in enumerate(steps):
        step_offset = round(step * spec['beat_per_step'] * 2)  # 2 passi di griglia = 1 beat
        j = i0 + step_offset
        if j >= len(grid):
            break
        t = grid[j]
        move = accent_move if gaps_before[k] > avg_gap + 1e-9 else fill_move
        out.append({
            'startTime': float(t),
            'beatNumber': _beat_number_at(beats, t),
            'moveType': move,
            'moveChannel': CH_FRONT if (k + start_side) % 2 == 0 else CH_BACK,
            '_injected': True,
            '_protected': True,
            '_figure': pattern_name,
        })
    return out


# Quanto lontano puo' essere l'attacco reale perche' un colpo ci venga spostato
# sopra, in frazione di beat. 0.30 e' poco piu' di una semicroma: abbastanza per
# raggiungere la meta' battuta piu' vicina (0.5) partendo dal quarto quando
# l'attacco e' li' vicino, ma non tanto da far migrare un colpo su un accento
# che appartiene a un'altra posizione ritmica.
SNAP_WINDOW_BEATS = 0.30


def _snap_to_onsets(actions, onsets, beats):
    """Sposta ogni colpo sull'attacco reale dell'audio piu' vicino, se ce n'e'
    uno abbastanza vicino. Non aggiunge ne' toglie colpi: cambia solo QUANDO.

    Perche' esiste (verdetto VR 25/08 sera). I colpi nascono dai pattern del
    repertorio, che dichiarano la posizione come `sequenceBeat + actionOffset`,
    cioe' fissa rispetto alla griglia. Su un riff sincopato questo li fa cadere
    sistematicamente nel posto sbagliato: sull'intro di Master Of Puppets gli
    attacchi veri stanno a 2.51, 7.69, 8.44, 10.47, 12.52 beat - tutte mezze
    battute - mentre i nostri colpi stavano a 1.00, 2.00, 3.00, 4.00.
    L'utente lo ha descritto cosi': "avrebbero potuto avere un altro colpo nel
    mezzo […] devi riuscire a inserire i colpi a meta' battuta".

    Aumentare la densita' non lo risolve: aggiunge altri colpi sugli stessi
    quarti sbagliati (provato, e il verdetto e' stato di nuovo negativo).

    La figura resta quella del pattern - quali mosse, quale alternanza di
    lato - perche' quella parte era gia' giudicata buona in VR ("i tris di
    colpi erano i momenti belli"). Cambia solo l'istante.

    `enforce_playability` gira comunque DOPO: puo' rifiutare uno spostamento
    che avvicina troppo due colpi sullo stesso braccio, ed e' giusto cosi' -
    i vincoli fisici vengono prima della fedelta' al brano."""
    if not onsets or not actions or not beats:
        return actions
    import bisect
    ons = sorted(float(t) for t in onsets)
    n_beats = len(beats)

    def durata_beat(t):
        """Lunghezza del beat in cui cade `t`: la finestra di aggancio e' in
        frazione di beat, e su brani a tempo variabile un valore in secondi
        fisso sarebbe troppo largo nei tratti veloci e troppo stretto in
        quelli lenti."""
        i = bisect.bisect_right([b['_triggerTime'] for b in beats], t) - 1
        i = min(max(i, 0), n_beats - 1)
        bl = beats[i].get('_beatLength')
        if bl:
            return float(bl)
        if i + 1 < n_beats:
            return float(beats[i + 1]['_triggerTime'] - beats[i]['_triggerTime'])
        return 0.5

    out = []
    for a in actions:
        t = float(a['startTime'])
        bl = durata_beat(t)
        finestra = SNAP_WINDOW_BEATS * bl
        j = bisect.bisect_left(ons, t)
        vicini = [ons[k] for k in (j - 1, j) if 0 <= k < len(ons)]
        if vicini:
            best = min(vicini, key=lambda o: abs(o - t))
            if abs(best - t) <= finestra:
                b = dict(a)
                b['startTime'] = float(best)
                # beatNumber va ricalcolato: e' quello che il gioco usa per
                # sincronizzare, e lasciarlo al valore del pattern lo
                # slegherebbe dall'istante reale appena cambiato.
                i = bisect.bisect_right([x['_triggerTime'] for x in beats], best) - 1
                i = min(max(i, 0), n_beats - 1)
                dur = beats[i].get('_beatLength') or bl
                b['beatNumber'] = float(i + (best - beats[i]['_triggerTime']) / dur) if dur else float(i)
                # segna l'istante come esatto: senza questo, enforce_playability
                # lo rimetterebbe sulla griglia subito dopo, annullando in
                # silenzio proprio lo spostamento appena fatto - bug reale
                # misurato il 25/08 sera (colpi finiti a 0.330/1.440/2.020
                # invece degli accenti veri 0.313/1.431/2.042).
                b['_exact'] = True
                out.append(b)
                continue
        out.append(a)
    return out


def _apply_rhythm_events(actions, events, beats, preset=DEFAULT_PRESET, rng=None, density_curve=None):
    """Corregge la coreografia gia' costruita dai pattern del repertorio con
    quello che i pattern non possono vedere - vedi
    boxvr_generator.detect_breath_and_bursts e [[boxvr-roadmap]] per i casi
    reali su cui questo e' stato tarato:

    - "respiro": azzittisce le azioni del pattern che cadono nella finestra,
      con probabilita' CONTINUA (non un taglio netto sì/no) legata al
      percentile di densita' in quell'istante preciso - verificato su 20
      brani reali che una soglia netta perdeva un segnale debole ma vero
      presente in 16/20 (correlazione media 0.26, vedi [[boxvr-roadmap]]
      2026-08-23); una probabilita' che sfuma invece di tagliare di netto
      lo sfrutta meglio senza fidarsi ciecamente del bordo esatto.
    - "raffica": rimane a soglia netta apposta (vedi `_BURST_STRIDE` sopra) -
      e' un evento isolato e breve, non ha senso "sfumarlo".
    - "veloce": stessa idea del respiro ma all'altro estremo - piu' un
      istante e' oggettivamente denso rispetto al resto del brano, piu' e'
      probabile (non certo) che venga mostrato un colpo reale li', fino al
      tetto del preset (`_FAST_CEILING`).

    In entrambi i casi la mano/corsia (Front/Back alternati) resta la stessa
    approssimazione gia' documentata altrove - il formato non registra
    quale mano tira il colpo, vedi [[boxvr-internals]]. `rng` deve essere lo
    stesso generatore seminato dal titolo|artista gia' in uso nel resto
    della funzione chiamante, cosi' la scelta resta deterministica/
    ripetibile come tutto il resto della pipeline - senza, si ripiega su un
    seme fisso solo per non rompere le chiamate esistenti.

    Puo' iniettare figure ANCHE dentro un tratto gia' coperto da
    `_place_moves_on_onsets` (ancorato agli accenti audio veri) - corretto il
    25/08, non piu' escluso a priori con `skip_spans` come nella prima
    versione. Non serve piu': `enforce_playability` ora tiene le azioni
    '_exact' a un livello di priorita' sopra le figure protette, mai
    spostabili ne' scartabili per fare posto a una figura iniettata (vedi il
    suo docstring). L'esclusione a zona intera era una misura piu' grezza di
    quella vera - su un brano molto ritmato (es. Baddadan, dove ogni
    segmento attivo risulta ancorato) escludeva TUTTE le nostre figure
    dall'intero brano, non solo quelle in vero conflitto."""
    if not events:
        return actions

    rng = rng or random.Random("rhythm_events_fallback_seed")
    rank_at = None
    if density_curve is not None:
        import boxvr_generator as _gen
        centers, density = density_curve
        rank_at = _gen.density_rank_lookup(centers, density)

    def _silence_prob(t):
        if rank_at is None:
            return 1.0  # niente curva continua disponibile: torna al taglio netto (sempre silenzio dentro il respiro)
        return max(0.0, 1.0 - 2.0 * rank_at(t))

    def _fast_prob(t, ceiling):
        if rank_at is None:
            return ceiling
        return ceiling * max(0.0, min(1.0, 2.0 * rank_at(t) - 1.0))

    breath_windows = [(e['start'], e['end']) for e in events if e['type'] == 'breath']

    def _in_breath(t):
        return any(t0 <= t < t1 for t0, t1 in breath_windows)

    # Le azioni '_exact' (ancorate a un accento audio VERO, vedi
    # _place_moves_on_onsets/_snap_to_onsets) sono protette da tutto questo
    # passaggio, come le figure '_protected' altrove: respiro/veloce/raffica
    # ragionano sulla densita' della zona, non sanno che quell'istante preciso
    # e' gia' un accento confermato - senza questa protezione lo silenziavano
    # o lo sostituivano con una figura iniettata a un istante diverso, bug
    # reale misurato il 25/08 sera (l'accento a 0.311s diventava 0.33s).
    kept = []
    for a in actions:
        if a.get('_exact'):
            kept.append(a)
            continue
        if _in_breath(a['startTime']) and rng.random() < _silence_prob(a['startTime']):
            continue  # azzittita - probabilita' piu' alta quanto piu' e' vicina al cuore del respiro
        kept.append(a)

    fast_ceiling = _FAST_CEILING.get(preset, 1.0)
    if fast_ceiling > 0:
        fast_windows = [(e['start'], e['end']) for e in events if e['type'] == 'fast']
        kept = [a for a in kept if a.get('_exact')
               or not any(t0 <= a['startTime'] < t1 for t0, t1 in fast_windows)]
    else:
        fast_windows = []  # tetto 0 per il preset: la sezione veloce resta quella del pattern originale, non toccata

    burst_stride = _BURST_STRIDE.get(preset, 1)
    combo_len = _COMBO_LENGTH.get(preset, 3)
    ts_beats = [b['_triggerTime'] for b in beats]

    injected = []
    for e in events:
        if e['type'] == 'fast':
            if fast_ceiling <= 0:
                continue
            # Sezione veloce: diretti alternati su OGNI beat della finestra,
            # cioe' "i dritti alternati veloci a tempo perfetto" chiesti per i
            # drop. Prima erano piazzati sui singoli onset: fuori griglia e
            # senza forma. La probabilita' continua ora decide se la finestra
            # merita la figura, non piu' il singolo colpo.
            if rng.random() >= _fast_prob(e['start'], fast_ceiling):
                continue
            n = sum(1 for t in ts_beats if e['start'] <= t < e['end'])
            injected.extend(_jab_combo(beats, e['start'], max(2, n),
                                        start_side=rng.randint(0, 1), rng=rng))
            continue
        if e['type'] != 'burst':
            continue
        if burst_stride is None:
            continue
        # Raffica: una figura breve e chiusa (il "tris di colpi" apprezzato).
        # Una parte usa i ritmi euclidei (2026-08-24, vedi _EUCLIDEAN_PATTERNS)
        # invece del solito _jab_combo: stessa idea (figura riconoscibile,
        # ancorata all'inizio della raffica), ma varieta' vera invece di
        # "sempre diretti in fila" - la richiesta esplicita era alzare la
        # quota di figure nostre oltre ai due casi gia' validati in VR, non
        # sostituirli (la maggioranza resta jab_combo, gia' apprezzato).
        euclidean_prob = _EUCLIDEAN_BURST_PROB.get(preset, 0.0)
        if euclidean_prob > 0 and rng.random() < euclidean_prob:
            pattern_name = rng.choice(list(_EUCLIDEAN_PATTERNS))
            injected.extend(_euclidean_figure(beats, e['start'], pattern_name,
                                               start_side=rng.randint(0, 1), rng=rng))
        else:
            injected.extend(_jab_combo(beats, e['start'], combo_len,
                                        start_side=rng.randint(0, 1), rng=rng))

    # Le figure iniettate devono LEGGERSI: si tolgono le azioni del pattern che
    # cadono dentro la loro durata, altrimenti si accavallano (era la causa dei
    # "troppi colpi sovrapposti" a inizio brano, dove le raffiche si sommavano
    # a quanto il pattern gia' prevedeva invece di sostituirlo).
    kept = _strip_overlaps(kept, injected, ts_beats)

    result = kept + injected
    result.sort(key=lambda a: a['startTime'])
    return result


MIN_ONSET_COUNT = 3  # numero ASSOLUTO minimo di accenti reali per fidarsi - non una
# frazione del target del pattern. Corretto il 25/08 sera dopo averlo misurato su
# Master Of Puppets: il segmento del riff ha 7 accenti reali in 4.81s (~0.9 al
# beat, in linea con la densita' media ufficiale) ma il pattern scelto per quella
# intensita' ne voleva 16 (2/beat, molto piu' denso) - una soglia proporzionale al
# target del pattern scartava l'ancoraggio proprio perche' il pattern era troppo
# denso per quel riff, ripiegando sulla griglia esattamente nel caso che questa
# funzione doveva risolvere. Pochi accenti VERI restano comunque materiale reale
# su cui ancorarsi, anche se sono meno di quanti il pattern ne vorrebbe: si piazza
# su tutti quelli disponibili, accettando una densita' piu' bassa per quel
# segmento invece di inventare struttura che l'audio non ha.

# Densita' minima (accenti/secondo) perche' un segmento classificato "silenzio
# vero" per energia venga comunque attivato - aggiunto il 25/08 (notte
# successiva) dopo aver misurato che il caso originale (l'intro/riff di
# Master Of Puppets, "sono stato fermo tutto il tempo... il riff nemmeno
# tracciato") era ANCORA silenziato sul brano intero nonostante il percentile
# a due livelli (structural_energy_rank): quel segmento e' la occorrenza PIU'
# debole (per energia RMS) del suo gruppo strutturale, pur avendo 61 accenti
# reali in 18.4s (3.31/s) - e' proprio il riff che si sta testando in VR da
# stasera. Misurato PRIMA di scegliere la soglia: su 3 brani di riferimento,
# ogni segmento attualmente classificato "silenzio" ha densita' fra 2.24 e
# 3.31 onset/s, cioe' dentro il range NORMALE dei segmenti gia' attivi
# (min 0.22, mediana 3.38 su 46 segmenti attivi) - l'energia RMS li giudicava
# silenziosi, gli accenti reali no. 1.5 sta comodamente sotto tutti e 4 i casi
# trovati e sopra la densita' della clip di riferimento del riff (7 accenti in
# 4.81s = 1.46/s, gia' descritta altrove come "in linea con la densita' media
# ufficiale"). Non calibrata su un vero caso di silenzio con rumore di fondo
# denso (nessuno trovato nei 3 brani misurati) - da restringere se in futuro
# un brano reale mostrasse un falso positivo (silenzio vero riattivato per
# errore).
MIN_ACTIVITY_ONSET_RATE = 1.5


def _place_moves_on_onsets(actions, song_onsets, seg_start_t, seg_end_t, target_n, move_defs,
                           beats, n_beats, span_beats=None, rng=None, variation_prob=0.0):
    """Piazza le mosse del pattern SUGLI ACCENTI REALI dell'audio in questo
    segmento, invece che a offset fissi rispetto al beat - la correzione
    decisa dopo il verdetto VR del 25/08 sera ("i colpi non erano a meta'
    battuta"). Ritorna True se ha piazzato qualcosa (in tal caso ha gia'
    scritto in `actions`), False se il segmento non ha abbastanza accenti
    reali e il chiamante deve ripiegare sul posizionamento a griglia fissa.

    Perche' questo e' il modo giusto e la sola nudged (_snap_to_onsets) non
    bastava: quella sposta un colpo GIA' PIAZZATO sull'accento piu' vicino
    entro una finestra stretta, ma non puo' far comparire un colpo dove il
    pattern a griglia fissa non ne aveva messo nessuno vicino - ed e'
    esattamente il caso misurato su Master Of Puppets (l'accento a 1.756s del
    riff non aveva nessun colpo del pattern nelle vicinanze da spostare li').
    Qui si parte dagli accenti, non dal pattern: il pattern serve solo a
    decidere la SEQUENZA di mosse da ciclare, non il quando - il lato lo
    decide questa funzione (vedi sotto).

    `target_n`: quante mosse il pattern avrebbe messo in questo segmento con
    il posizionamento a griglia fissa (stesso conteggio, stessa densita' gia'
    validata in Fase 2 - qui cambia SOLO l'istante, non quanti eventi).

    `move_defs`: lista di `(moveType, rel_beat)`, dove `rel_beat` e' la
    posizione (sequenceBeat + actionOffset) della mossa DENTRO UNA sola
    ripetizione del pattern (0..PATTERN_BEATS). `span_beats`: quanti beat
    copre l'intero segmento in termini di ripetizioni del pattern
    (`reps * PATTERN_BEATS`, calcolato dal chiamante).

    Selezione degli accenti - corretta il 25/08 notte dopo un difetto reale
    trovato in VR ("le coppie di montanti si comprimono in una raffica"):
    non piu' indici equidistanti sulla lista degli accenti (che ignorava
    completamente LA FORMA del pattern), ma la posizione RELATIVA di ogni
    mossa dentro il pattern, scalata sulla durata del segmento, poi abbinata
    all'accento reale piu' vicino ancora libero. Un pattern con una coppia
    ravvicinata e poi una pausa lunga (es. `AutoSeq_Compl_3_D`, 8 montanti a
    coppie: beat 0,1 - pausa di 3 beat - 4,5 - pausa - ...) ora produce
    bersagli vicino/vicino/lontano nello stesso rapporto, e l'abbinamento
    goloso tende a scegliere due accenti reali vicini per la coppia e uno
    piu' lontano dopo la pausa - la FORMA del pattern sopravvive
    all'irregolarita' dei veri accenti, non solo la sua sequenza di mosse.
    Se i due accenti piu' vicini a un bersaglio sono gia' presi da un
    bersaglio precedente, quello slot resta senza colpo: e' la pausa del
    pattern che si preserva, non un accento "rubato" a un bersaglio lontano.
    La densita' finale viene comunque rifinita da `enforce_playability` a
    valle, che sposta o scarta cio' che non rispetta i vincoli fisici -
    stessa rete di sicurezza usata ovunque nella pipeline.

    Richiede un numero assoluto minimo di accenti abbinati (`MIN_ONSET_COUNT`),
    non una frazione del target del pattern - vedi il commento sulla costante
    per il caso reale (Master Of Puppets) che ha portato a questa correzione.
    Con MENO di quel minimo, il segmento e' probabilmente un tratto
    sostenuto/ambient dove gli "accenti" rilevati sono rumore, non musica -
    meglio il pattern a griglia fissa che inventare struttura dove non c'e'."""
    import bisect
    rng = rng or random.Random("place_on_onsets_fallback_seed")
    lo = bisect.bisect_left(song_onsets, seg_start_t)
    hi = bisect.bisect_left(song_onsets, seg_end_t)
    seg_onsets = song_onsets[lo:hi]
    if len(seg_onsets) < MIN_ONSET_COUNT:
        return False

    n_defs = len(move_defs)
    if not n_defs:
        return False
    seg_len = seg_end_t - seg_start_t
    span = span_beats if span_beats else (target_n / n_defs) * PATTERN_BEATS

    # Bersaglio temporale di ogni mossa: dove il pattern la vorrebbe, scalato
    # sulla durata reale del segmento - non solo il suo ordine.
    targets = []
    for k in range(target_n):
        rep = k // n_defs
        move_type, rel_beat = move_defs[k % n_defs]
        abs_beat = rep * PATTERN_BEATS + rel_beat
        frac = abs_beat / span if span else 0.0
        targets.append((seg_start_t + frac * seg_len, move_type))

    # Abbinamento goloso, un accento per bersaglio, mai riusato: preserva la
    # forma vicino/lontano del pattern invece di distribuire alla cieca.
    used = [False] * len(seg_onsets)
    chosen = []   # [(t_onset, move_type), ...]
    for t_target, move_type in targets:
        i = bisect.bisect_left(seg_onsets, t_target)
        best_j, best_d = None, None
        for j in (i - 1, i):
            if 0 <= j < len(seg_onsets) and not used[j]:
                d = abs(seg_onsets[j] - t_target)
                if best_d is None or d < best_d:
                    best_d, best_j = d, j
        if best_j is None:
            continue          # nessun accento libero vicino: resta una pausa vera
        used[best_j] = True
        chosen.append((seg_onsets[best_j], move_type))
    chosen.sort(key=lambda x: x[0])
    if len(chosen) < MIN_ONSET_COUNT:
        return False          # la forma del pattern non ha trovato abbastanza accenti da abbinare

    # Il LATO alterna per conto suo (k%2) invece di ereditarlo dal pattern.
    # Motivo, trovato misurando (non assunto): i move_defs del pattern
    # alternano i lati assumendo LA SUA cadenza regolare (mezzo beat
    # costante); sugli accenti reali, irregolari, ereditare quella sequenza
    # puo' far cadere due mosse consecutive sullo STESSO lato quando la
    # distanza reale e' troppo corta - enforce_playability le sposta/scarta
    # di nuovo a valle, silenziosamente vanificando l'ancoraggio. Alternare
    # qui e' anche cio' che la prova di fattibilita' di stamattina gia'
    # faceva (e che funzionava): coerente con la misura sui workout
    # ufficiali, che cambiano lato nell'84% delle transizioni.
    CENTRO_MOVES = frozenset((MOVE_BLOCK, MOVE_SQUAT, MOVE_DODGE))
    lateral_k = 0   # conta SOLO le mosse laterali: due jab separati da uno
    # squat devono comunque alternare fra loro, non condividere il lato solo
    # perche' cadono sullo stesso resto pari/dispari dell'indice generale.
    prev_t = None
    prev_arm_type = None   # ultima mossa di BRACCIA davvero piazzata (per la variazione)
    for k, (t, move_type) in enumerate(chosen):
        i = bisect.bisect_right([b['_triggerTime'] for b in beats], t) - 1
        i = min(max(i, 0), n_beats - 1)
        bl = beats[i].get('_beatLength') or 0.5

        # VARIAZIONE NOSTRA sopra il pattern ufficiale (26/08) - vedi
        # _vary_pattern_move e PATTERN_VARIATION_PROB. Applicata PRIMA della
        # forzatura del Jab qui sotto, non dopo: cosi' anche una mossa
        # appena variata resta soggetta al vincolo dello spazio stretto,
        # invece di scavalcarlo.
        move_type = _vary_pattern_move(move_type, prev_arm_type, rng, variation_prob)

        # Se lo spazio dal colpo scelto precedente e' stretto, il gancio o il
        # montante che il pattern avrebbe ciclato qui diventa un Jab. Deciso
        # dopo un vero riascolto in VR sul riff di Master Of Puppets, il 25/08
        # sera: il quarto accento distava 0.495 beat dal precedente e non era
        # fisicamente vietato metterci un gancio (il minimo misurato per
        # "gancio/montante a lato diverso" e' 0.50), ma era la scelta
        # sbagliata - sui 465 workout ufficiali, quando lo spazio disponibile
        # e' sotto 0.6 beat il gioco mette un Jab nell'80% dei casi, un
        # gancio/montante solo nel 17%. Non e' un divieto assoluto (per
        # questo enforce_playability resta l'arbitro finale sulla
        # giocabilita'), e' seguire cosa fa davvero il gioco quando ha poco
        # spazio, invece di limitarsi a non romperlo.
        if move_type in SWING_MOVES and prev_t is not None:
            gap_beats = (t - prev_t) / bl if bl else 999
            if gap_beats < 0.6:
                move_type = MOVE_JAB
        prev_t = t

        # le mosse centrali restano SEMPRE al centro (100% dei casi misurato
        # sui workout ufficiali) - solo le mosse laterali alternano il lato
        # in modo indipendente dal pattern, vedi commento sopra.
        if move_type in CENTRO_MOVES:
            move_channel = CH_CENTER
        else:
            move_channel = CH_FRONT if lateral_k % 2 == 0 else CH_BACK
            lateral_k += 1
            prev_arm_type = move_type
        beat_number = i + (t - beats[i]['_triggerTime']) / bl if bl else float(i)
        actions.append({
            'startTime': float(t), 'beatNumber': float(beat_number),
            'moveType': move_type, 'moveChannel': move_channel,
            '_exact': True,   # non ri-agganciare alla griglia: vedi enforce_playability
        })
    return True


def build_move_actions(analysis, preset=DEFAULT_PRESET, seed=None):
    """Costruisce la lista di MoveCue per un brano gia' analizzato.

    `analysis`: il dict di boxvr_generator.generate_song_analysis, oppure quello
    ricostruito da analysis_from_installed.
    `preset`: 'light' | 'medium' | 'high' - vedi INTENSITY_PRESETS. Governa
    quanto si spinge e quanto e' ampia l'escursione; la forma dell'allenamento
    la da' comunque la curva di energia del brano.
    `seed`: normalmente non serve - di default il seme deriva da titolo|artista,
    cosi' lo stesso brano produce SEMPRE la stessa coreografia (vedi
    [[boxvr-choreo]] sulla ripetibilita').

    Ritorna una lista di dict pronti per la playlist (vedi serialize_actions).
    """
    vocab = load_vocabulary()
    beats = analysis['beats']
    n_beats = len(beats)
    if not n_beats:
        return []
    rng = random.Random(seed if seed is not None else f"{analysis.get('name')}|{analysis.get('artist')}")
    memo = {}
    actions = []
    last_pattern = None

    seg_energies = segment_energies(analysis)
    intensities = energies_to_intensities(
        seg_energies, preset, rank=structural_energy_rank(analysis, seg_energies))

    song_onsets = sorted(analysis.get('onsets') or [])
    # quota di mosse del pattern ufficiale sostituite con una campionata dalla
    # matrice di transizione reale - la "struttura nostra" oltre al repertorio
    # BoxVR, vedi PATTERN_VARIATION_PROB per il perche' e' bassa e graduale.
    variation_prob = PATTERN_VARIATION_PROB.get(preset, 0.0)
    # generatore casuale SEPARATO per la variazione, non `rng`. Motivo trovato
    # misurando (26/08): condividendo `rng`, ogni estrazione fatta dalla
    # variazione sfasava tutto il flusso casuale a valle - scelta dei pattern
    # e iniezione delle figure comprese. Accendere o spegnere la variazione
    # cambiava quindi MOLTO piu' di quanto dichiarasse (misurato: 50-56% dei
    # colpi diversi con una quota nominale del 20%), e rendeva impossibile
    # misurarne l'effetto isolato. Con un flusso suo, la variazione tocca solo
    # cio' che deve toccare.
    var_rng = random.Random(
        f"{seed if seed is not None else str(analysis.get('name')) + '|' + str(analysis.get('artist'))}|variation")

    for si, seg in enumerate(analysis['segs']):
        intensity = intensities[si] if si < len(intensities) else 0
        if intensity <= 0:
            # L'energia RMS dice "silenzio vero", ma un numero sufficiente di
            # accenti audio REALI dice il contrario - vedi MIN_ACTIVITY_ONSET_RATE.
            # Caso reale che ha portato alla correzione: il riff dell'intro di
            # Master Of Puppets, silenziato anche dopo il percentile a due
            # livelli perche' e' l'occorrenza piu' debole (per energia) del suo
            # gruppo strutturale, pur avendo 61 accenti veri in 18.4s.
            seg_start_t = seg.get('_startTime')
            seg_len = seg.get('_length')
            if seg_start_t is not None and seg_len and song_onsets:
                lo = bisect.bisect_left(song_onsets, seg_start_t)
                hi = bisect.bisect_left(song_onsets, seg_start_t + seg_len)
                n_here = hi - lo
                if n_here >= MIN_ONSET_COUNT and n_here / seg_len >= MIN_ACTIVITY_ONSET_RATE:
                    intensity = 1   # attivato dal materiale reale, non dall'energia media
            if intensity <= 0:
                continue           # riposo vero: nessun evento
        # sezioni ricorrenti -> stessa coreografia; senza etichetta si ripiega
        # sull'indice del segmento, che rende ogni segmento a se' stante.
        section_key = seg.get('_sectionLabel') or f"seg{seg['_index']}"
        pattern = _pattern_for(section_key, intensity, vocab, rng, memo,
                                avoid=last_pattern, preset=preset)
        if not pattern:
            continue
        last_pattern = pattern.get('sequenceName')

        start_beat = seg['_startBeatIndex']
        seg_beats = seg['_numBeats']
        reps = max(1, seg_beats // PATTERN_BEATS)
        # (moveType, posizione relativa dentro UNA ripetizione del pattern) -
        # la posizione serve a _place_moves_on_onsets per preservare la FORMA
        # del pattern (vicino/vicino/lontano) quando ancora agli accenti
        # reali, non solo la sua sequenza di mosse. Vedi il suo docstring.
        move_defs = [(int(mv.get('moveType', MOVE_JAB)),
                      mv.get('sequenceBeat', 0) + float(mv.get('actionOffset', 0.0)))
                     for mv in pattern.get('moveActions', [])]

        placed_on_onsets = False
        if move_defs and song_onsets:
            seg_start_t = seg.get('_startTime')
            seg_len = seg.get('_length')
            if seg_start_t is not None and seg_len:
                target_n = len(move_defs) * reps
                placed_on_onsets = _place_moves_on_onsets(
                    actions, song_onsets, seg_start_t, seg_start_t + seg_len,
                    target_n, move_defs, beats, n_beats, span_beats=reps * PATTERN_BEATS,
                    rng=var_rng, variation_prob=variation_prob)

        if placed_on_onsets:
            continue

        # RIPIEGO: nessun accento reale abbastanza denso in questo segmento
        # (silenzio, synth sostenuto, sezione ambient) - il pattern resta
        # posizionato a offset fissi rispetto al beat, come sempre.
        prev_arm_type = None   # ultima mossa di braccia piazzata, per la variazione
        block_lateral_k = 0    # alterna il lato SOLO per gli scudi variati in
        # colpo di braccia (26/08): per tutte le altre mosse la corsia resta
        # quella scritta nel pattern, invariata - qui serve solo perche' lo
        # scudo non ne ha mai avuta una laterale da riusare.
        for rep in range(0, reps):
            base = start_beat + rep * PATTERN_BEATS
            for mv in pattern.get('moveActions', []):
                # nel repertorio la posizione e' sequenceBeat (intero) piu'
                # actionOffset (frazione di beat, per le figure fuori battere);
                # nell'azione finale l'istante e' gia' risolto, quindi
                # actionOffset torna a 0 come nei file ufficiali.
                pos = mv.get('sequenceBeat', 0) + float(mv.get('actionOffset', 0.0))
                idx = base + pos
                i0 = int(idx)
                if i0 < 0 or i0 >= n_beats:
                    continue
                frac = idx - i0
                t = beats[i0]['_triggerTime']
                if frac and i0 + 1 < n_beats:
                    t += (beats[i0 + 1]['_triggerTime'] - t) * frac
                # VARIAZIONE NOSTRA sopra il pattern ufficiale - vedi
                # _vary_pattern_move. Qui le POSIZIONI restano quelle fisse
                # del pattern (e' il percorso a griglia), cambia solo QUALE
                # colpo cade in ciascuna: la spaziatura pensata dal pattern
                # e' preservata per costruzione, quindi il rischio di rendere
                # la combo ineseguibile e' limitato al tipo di mossa - e
                # enforce_playability resta comunque l'arbitro finale.
                orig_type = int(mv.get('moveType', MOVE_JAB))
                move_type = _vary_pattern_move(orig_type, prev_arm_type, var_rng, variation_prob)
                if move_type in ARM_MOVES and move_type != MOVE_BLOCK:
                    prev_arm_type = move_type
                if orig_type == MOVE_BLOCK and move_type != MOVE_BLOCK:
                    # lo scudo variato in un colpo di braccia perde la corsia
                    # centrale del pattern - un Jab/Hook/Uppercut al centro
                    # verrebbe scartato da enforce_playability, quindi va
                    # assegnata una corsia laterale qui (a differenza delle
                    # altre mosse di braccia, che tengono la corsia gia'
                    # scritta nel pattern anche quando il TIPO viene variato).
                    move_channel = CH_FRONT if block_lateral_k % 2 == 0 else CH_BACK
                    block_lateral_k += 1
                else:
                    move_channel = int(mv.get('moveChannel', CH_FRONT))
                actions.append({
                    'startTime': float(t),
                    'beatNumber': float(idx),
                    'moveType': move_type,
                    'moveChannel': move_channel,
                })

    # PRIMA di tutto il resto: sposta i colpi sugli attacchi VERI dell'audio.
    # I pattern del repertorio hanno posizioni fisse rispetto al beat, quindi su
    # un riff sincopato cadono sui quarti mentre la musica accenta le meta'
    # battute - vedi _snap_to_onsets per il caso reale che l'ha motivata.
    actions = _snap_to_onsets(actions, analysis.get('onsets') or [], beats)
    actions = _apply_rhythm_events(actions, analysis.get('rhythm_events') or [], beats, preset=preset,
                                    rng=rng, density_curve=analysis.get('rhythm_density'))
    actions = _apply_section_accents(actions, analysis['segs'], intensities, beats, preset=preset, rng=rng)
    # Ultimo passaggio, sempre: aggancia alla griglia, elimina le sovrapposizioni
    # impossibili e impone la distanza minima. Va DOPO l'iniezione ritmica, che e'
    # proprio cio' che introduce mosse fuori griglia e collisioni - vedi
    # enforce_playability per le regole e da quali misure vengono.
    actions = enforce_playability(actions, beats)
    actions.sort(key=lambda a: a['startTime'])
    return actions


def serialize_actions(move_actions, track_id, bpm, wav_path):
    """Impacchetta le mosse nel formato serialisedActionList di BoxVR: JSON
    annidato in stringa, con davanti l'azione BPM e quella Audio, esattamente
    nell'ordine osservato nei workout ufficiali."""
    def wrap(atype, payload):
        return {'musicActionType': atype,
                'musicActionJSON': json.dumps(payload, separators=(',', ':'))}

    out = [
        wrap(ACT_BPM, {'startTime': 0.0, 'beatNumber': 0.0,
                       'musicActiontype': ACT_BPM, 'segmentBPM': float(bpm)}),
        wrap(ACT_AUDIO, {'startTime': 0.0, 'beatNumber': 0.0,
                         'musicActiontype': ACT_AUDIO,
                         'wavFilePath': wav_path.replace('\\', '/'),
                         'trackId': track_id}),
    ]
    for a in move_actions:
        out.append(wrap(ACT_MOVECUE, {
            'startTime': a['startTime'], 'beatNumber': a['beatNumber'],
            'musicActiontype': ACT_MOVECUE,
            'moveAction': {'moveType': a['moveType'], 'moveChannel': a['moveChannel'],
                           'sequenceBeat': 0, 'actionOffset': 0.0},
        }))
    return {'actionList': out}


def analysis_from_installed(track_id, with_sections=True, log=None):
    """Ricostruisce il minimo indispensabile (beat, segmenti, livelli) leggendo
    il trackdata GIA' INSTALLATO nel gioco, invece di rianalizzare l'mp3.

    E' il modo corretto per aggiungere una coreografia a un brano gia' in
    libreria: gli eventi devono cadere sui beat del trackdata che il gioco
    caricera' davvero. Una nuova analisi produrrebbe una griglia leggermente
    diversa (madmom e librosa non sono bit-identici tra una versione e l'altra
    del file) e la coreografia risulterebbe sfasata rispetto all'audio.

    `with_sections`: rileva anche le sezioni musicali dal wav installato, per
    dare la stessa combinazione ai ritornelli ricorrenti. Costa una passata di
    sonic-annotator (qualche decina di secondi); senza, ogni segmento fa storia
    a se'."""
    track_dir, tdef_dir, _ = boxvr_dirs()
    with open(os.path.join(track_dir, f"{track_id}.trackdata.txt"), encoding='utf-8-sig') as f:
        outer = json.load(f)
    inner = json.loads(outer['beatStrucureJSON'])
    segs = inner['_segmentList']['_segments']
    analysis = {
        'beats': inner['_beatList']['_beats'],
        'bars': inner['_barList']['_bars'],
        'segs': segs,
        'duration': outer['duration'], 'bpm': outer['bpm'],
        'name': outer.get('originalTrackName', '?'),
        'artist': outer.get('originalArtist', '?'),
    }
    analysis['rhythm_events'] = []
    analysis['rhythm_density'] = None
    if with_sections:
        try:
            import soundfile as sf_read
            import boxvr_generator as _gen
            wav = os.path.join(track_dir, f"{track_id}.wav")
            audio, sr = sf_read.read(wav, dtype='float32', always_2d=True)
            mono = audio.mean(axis=1)
            # chiave = track_id: la segmentazione di questo brano viene calcolata
            # una volta sola e poi riletta, cosi' la coreografia e' identica ad
            # ogni rigenerazione (qm-segmenter non e' deterministico).
            rows = _gen.structural_segment_times(mono, sr, log=log, with_labels=True,
                                                  cache_key=f"tid_{track_id}")
            _gen._tag_segments_with_sections(segs, rows)
            # respiro/raffica/veloce (vedi boxvr_generator.detect_breath_and_bursts):
            # e' deterministico (nessuna parte casuale, a differenza della
            # segmentazione sopra), quindi non serve cache per la ripetibilita' -
            # ma costa hpss (l'80% del tempo di analisi su un brano lungo), quindi
            # una cache PER VELOCITA' ha comunque senso se si rigenera piu' volte
            # la coreografia per lo stesso brano installato (30/08).
            cached_breath = _gen.load_cached_breath_bursts(f"tid_{track_id}")
            if cached_breath is not None:
                rhythm_events, dens_centers, dens_values, onsets = cached_breath
            else:
                rhythm_events, dens_centers, dens_values, onsets = _gen.detect_breath_and_bursts(mono, sr)
                _gen.save_cached_breath_bursts(f"tid_{track_id}", rhythm_events, dens_centers, dens_values, onsets)
            analysis['rhythm_events'] = rhythm_events
            analysis['rhythm_density'] = (dens_centers, dens_values)
            analysis['onsets'] = onsets
        except Exception as e:
            if log:
                log(f"Sezioni musicali non rilevate ({e}); ogni segmento fa storia a se'.")
            for s in segs:
                s['_sectionLabel'] = None
    else:
        for s in segs:
            s['_sectionLabel'] = None
    return analysis


def boxvr_dirs():
    """Rimane esposta qui per compatibilita' (script e boxvr_visual_preview la
    importano da questo modulo), ma la definizione vera vive in
    boxvr_install: unica fonte di verita' per i percorsi della libreria."""
    import boxvr_install
    return boxvr_install.boxvr_dirs()


def write_playlist(name, entries, out_dir=None):
    """Scrive una .workoutplaylist.txt con la coreografia gia' dentro.

    `entries`: lista di dict {track_id, duration, action_list} - action_list e'
    il risultato di serialize_actions. Il nome viene ripulito dai caratteri che
    Windows non ammette nei nomi di file.
    """
    import re
    track_dir, _, pl_dir = boxvr_dirs()
    out_dir = out_dir or pl_dir
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        'definition': {
            'workoutName': name, 'game': 0, 'workoutStyle': 0, 'authorName': 'author',
            'trackGenre': 0, 'leaderboardId': 'undefined', 'sonyLeaderboardId': -1,
            'workoutId': '', 'hasSquats': True, 'hasJumps': False,
            'workoutType': 1,
            'duration': float(sum(e['duration'] for e in entries)),
        },
        'songs': [{'trackDataName': e['track_id'],
                   'serialisedActionList': e['action_list']} for e in entries],
    }
    safe = re.sub(r'[<>:"/\\|?*]', '_', name)
    path = os.path.join(out_dir, f"{safe}.workoutplaylist.txt")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f)
    return path


MOVE_NAMES = {MOVE_NONE: 'None', MOVE_REST: 'Rest', MOVE_STANCE: 'StanceChange',
              MOVE_BLOCK: 'Block', MOVE_JAB: 'Jab', MOVE_HOOK: 'Hook',
              MOVE_UPPERCUT: 'Uppercut', MOVE_DODGE: 'Dodge', MOVE_SQUAT: 'Squat'}


def describe(move_actions, duration=None):
    """Riepilogo leggibile di una coreografia - per log e verifiche."""
    from collections import Counter
    c = Counter(MOVE_NAMES.get(a['moveType'], a['moveType']) for a in move_actions)
    parts = [f"{n}x{k}" for k, n in c.most_common()]
    rate = f", {len(move_actions) / duration * 60:.0f} eventi/min" if duration else ""
    return f"{len(move_actions)} eventi ({', '.join(parts)}){rate}"
