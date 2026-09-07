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

"""Motore prototipo per la modalita' sidecar - Fase B (sandbox), come da
piano in UI & Warframing/rd_modalita_sidecar.md: "senza toccare il tool".

Prende una lista di ISTANTI scelti dall'utente (in secondi, sul brano - MAI
corsia, MAI tipo di colpo, coerente con la decisione gia' presa) e produce
una coreografia completa. Riusa deliberatamente pezzi gia' scritti e testati
per la generazione automatica, invece di reinventarli:

- `boxvr_choreo._sample_next_arm_move`/`ARM_TRANSITION_PROBS` per la
  sequenza dei tipi di colpo laterali (Jab/Hook/Uppercut) - lo stesso motore
  Markov delle figure _jab_combo/_hook_accent di stasera (26/08).
- `boxvr_choreo.enforce_playability(..., snap_to_grid=False)` come rete di
  sicurezza finale: gli istanti dell'utente sono '_exact' e non vengono mai
  riquantizzati ne' spostati, esattamente come gli accenti audio veri.

Novita' di questo file: la decisione CENTRO vs LATERALE (A4, misurata sui
465 workout ufficiali, 26/08 sera) - vedi CENTRO_PROB_TABLE sotto per la
provenienza esatta dei numeri.

**Copertura PARZIALE dei marker (26/08, seconda meta' della notte).**
Chiarito dall'utente: i marker non sono l'intero brano, sono una BASE - puo'
marcarne pochi (es. solo i ritornelli) o nessuno, e nei tratti senza marker
(o anche VICINO a marker radi) la generazione automatica deve comunque
riempire, esattamente come farebbe da sola. Non e' un motore "riempimento"
separato e piu' povero: e' LO STESSO `build_move_actions` che gira sull'
intero brano, con i marker dell'utente sovrapposti sopra come livello di
priorita' ASSOLUTA - vedi `build_choreography()` sotto, e il nuovo
sotto-livello '_sidecar' aggiunto a `enforce_playability` in
boxvr_choreo.py (26/08): un marker dell'utente vince SEMPRE, anche contro un
accento audio vicino, non solo contro le nostre figure iniettate."""
import bisect
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boxvr_choreo as choreo

# Limite fisico minimo fra due input dell'utente, in secondi - misurato sui
# 465 workout ufficiali (rd_modalita_sidecar.md, sezione 2): 169ms il minimo
# assoluto misurato, 214ms sullo stesso lato. Qui, a monte di ogni decisione
# di corsia, si usa il piu' severo (170ms) come filtro grezzo: un secondo
# input troppo vicino al precedente viene ignorato, non genera un secondo
# colpo che il gioco stesso non produrrebbe mai.
# ---------------------------------------------------------------------------
# I valori qui sotto si possono regolare da `tuning.json` senza toccare il
# codice: le costanti restano quelle di sempre (tutto cio' che le usa non
# cambia), ma il loro valore lo chiede la tabella all'avvio. Vedi tuning.py
# per l'elenco completo, i limiti e la provenienza di ciascuno, e
# confronta_tuning.py per vedere l'effetto di una modifica senza rimettersi
# il visore.
#
# Se `tuning` non c'e', si usano i numeri scritti qui: la tabella e' una
# comodita', non una dipendenza.
try:
    import tuning as _tuning

    def _reg(chiave, ripiego):
        try:
            return _tuning.valore(chiave)
        except Exception:                      # noqa: BLE001
            return ripiego
except Exception:                              # noqa: BLE001
    def _reg(chiave, ripiego):
        return ripiego

MIN_INPUT_GAP_S = _reg('soglia_fra_i_tuoi_colpi_ms', 170) / 1000.0

# Finestra di correzione (27/08, richiesta esplicita: "correggere leggere
# imprecisioni dei marker"): se un marker cade entro questa distanza da un
# accento audio VERO, si assume che l'utente stesse mirando a quello e lo si
# sposta li' esattamente - anche dopo la correzione di latenza (26/08 notte),
# il tempo motorio umano ha una sua imprecisione residua e non e' realistico
# aspettarsi un tap sempre esatto al millisecondo. NON misurata sui 465
# workout (non c'e' un "marker umano" li' da confrontare a un bersaglio noto,
# a differenza degli altri numeri di questo file) - scelta prudente per
# analogia con le finestre di giudizio "buono" tipiche dei giochi ritmici,
# abbastanza piccola da correggere solo un vero quasi-centro, non da
# spostare un marker verso un accento che l'utente non intendeva colpire.
MARKER_SNAP_WINDOW_S = _reg('aggancio_agli_accenti_ms', 80) / 1000.0

# Quanto brano deve aver marcato l'utente perche' «Estendi» possa dire di
# aver imparato qualcosa (richiesto esplicitamente: 45 secondi). Sotto
# questa soglia una cadenza e una firma ritmica si possono sempre
# CALCOLARE, ma sarebbero il ritratto di quattro colpi, non di un modo di
# colpire: la modalita' continua a funzionare e lo dichiara, invece di
# spacciare per "imparato" un numero senza fondamento.
EXTEND_MIN_COVERAGE_S = _reg('estendi_secondi_minimi', 45.0)

# ...e almeno questo numero di marker. Quarantacinque secondi con quattro
# colpi dentro sono una copertura larga, non una cadenza: senza questo
# secondo vincolo bastava marcare l'inizio e la fine del brano per far
# credere al motore di aver visto un modo di colpire.
EXTEND_MIN_MARKER = _reg('estendi_colpi_minimi', 8)

# --- Blocchi ritmici e accenti isolati ---------------------------------
#
# Quanti colpi, e quanto fitti, perche' un gruppo di marker sia un RITMO e
# non una manciata di punti fermi. Quattro colpi di fila dentro almeno una
# battuta sono gia' una frase: sotto, sono accenti.
BLOCCO_MIN_COLPI = 4
BLOCCO_MIN_BATTUTE = 1.0

# Quando si considera che l'utente abbia SMESSO di marcare. Non un numero
# fisso di secondi: dipende da quanto fitto stava marcando. Sei volte il
# suo intervallo tipico e' una pausa che non appartiene piu' alla frase -
# con i limiti sotto perche' su cadenze estreme non degeneri.
PAUSA_MULTIPLO = 6.0
PAUSA_MIN_BATTUTE = 2.0
PAUSA_MAX_BATTUTE = 8.0

# Come in boxvr_generator (che qui non si importa: sarebbe tirarsi dietro
# tutto il generatore per un numero).
BEATS_PER_BAR = 4

# In quante parti si divide il beat per guardare DOVE cadono i colpi.
# Quattro = sedicesimi: la suddivisione piu' fine che in un workout si
# distingua ancora a orecchio (a 120 bpm sono 125 ms, contro i 170 ms del
# limite fisico fra due input - vedi MIN_INPUT_GAP_S).
GRID_DIVISIONI = _reg('suddivisioni_della_griglia', 4)

# Di quanto al massimo l'aggancio magnetico puo' spostare un colpo.
# Espresso come FRAZIONE del passo della griglia, non in millisecondi
# fissi: a 128 bpm un sedicesimo dura 117 ms, e una tolleranza di 60 ms -
# praticamente mezzo passo - avrebbe agganciato TUTTO, cancellando la
# possibilita' stessa di un colpo messo fuori tempo apposta. Un terzo
# scarso del passo raddrizza la sbavatura e lascia stare la scelta.
GRID_SNAP_FRAZIONE = 0.34
# Tetto assoluto, per i brani molto lenti dove un terzo di passo sarebbe
# comunque un salto grosso a orecchio.
GRID_SNAP_MAX_S = _reg('aggancio_alla_griglia_ms', 60) / 1000.0


def _snap_marker_to_onset(t, onsets):
    """Ritorna l'accento audio vero piu' vicino a `t` se cade entro
    MARKER_SNAP_WINDOW_S, altrimenti `t` invariato. `onsets` deve essere gia'
    ordinato (vedi analysis['onsets'], boxvr_generator.py)."""
    if not onsets:
        return t
    i = bisect.bisect_left(onsets, t)
    best, best_d = t, MARKER_SNAP_WINDOW_S
    for j in (i - 1, i):
        if 0 <= j < len(onsets):
            d = abs(onsets[j] - t)
            if d < best_d:
                best, best_d = onsets[j], d
    return best

# P(mossa centrale | beatInBar, gap causale dall'ultimo laterale) - misurata
# sui 465 workout ufficiali il 26/08 sera (measure_a4_causal_rule.py in
# training data/), VERSIONE CAUSALE (guarda solo il passato, utilizzabile da
# un motore che genera in tempo reale) - non la prima versione (retrospettiva,
# guardava avanti al prossimo laterale reale), inutilizzabile qui. Bucket del
# gap: 'none' = nessun laterale prima d'ora, 'short' < 0.75 beat,
# 'mid' 0.75-1.5 beat, 'long' >= 1.5 beat. Risultato controintuitivo rispetto
# alla prima ipotesi: un gap CORTO riduce la probabilita' di centro (si e'
# dentro una raffica di laterali fitti, non serve una pausa), un gap PIU'
# LUNGO la alza (c'e' spazio per inserirla).
CENTRO_PROB_TABLE = {
    (1, 'none'): 0.496, (1, 'long'): 0.195, (1, 'mid'): 0.219, (1, 'short'): 0.028,
    (2, 'none'): 0.746, (2, 'long'): 0.105, (2, 'mid'): 0.051, (2, 'short'): 0.076,
    (3, 'none'): 0.723, (3, 'long'): 0.170, (3, 'mid'): 0.132, (3, 'short'): 0.016,
    (4, 'none'): 0.864, (4, 'long'): 0.147, (4, 'mid'): 0.098, (4, 'short'): 0.070,
}
CENTRO_PROB_FALLBACK = 0.134   # base rate complessiva, se beatInBar manca

# Distribuzione del TIPO di mossa centrale (Block/Squat/Dodge), misurata sui
# 465 workout ufficiali - CONDIZIONATA al gap dalla mossa precedente (26/08),
# non piu' una media piatta. Misurato (measure_centro_type_context.py):
#
#   gap          Squat   Block   Dodge     n
#   <0.75        86.1%   13.9%    0.0%   1898
#   0.75-1.5     41.9%   40.7%   17.4%   9036
#   >=1.5        56.5%   19.8%   23.7%   7160
#   (media piatta usata prima: 52.4% / 29.5% / 18.1%)
#
# Il segnale piu' netto e' anche il piu' sensato fisicamente: **con poco
# spazio la schivata non compare MAI** (0.0% sotto 0.75 beat) - coerente con
# la misura gia' nota "Dodge non scende MAI sotto un beat pieno"
# (rd_modalita_sidecar.md, sezione 3). Con la media piatta il motore poteva
# piazzare una schivata in uno spazio in cui il gioco non la mette mai.
CENTRO_TYPE_PROBS_BY_GAP = {
    'short': {choreo.MOVE_SQUAT: 0.861, choreo.MOVE_BLOCK: 0.139, choreo.MOVE_DODGE: 0.000},
    'mid':   {choreo.MOVE_SQUAT: 0.419, choreo.MOVE_BLOCK: 0.407, choreo.MOVE_DODGE: 0.174},
    'long':  {choreo.MOVE_SQUAT: 0.565, choreo.MOVE_BLOCK: 0.198, choreo.MOVE_DODGE: 0.237},
}
# media piatta, usata solo quando non c'e' una mossa precedente da cui
# misurare il gap (inizio brano/frase): li' nessun bucket si applica.
CENTRO_TYPE_PROBS = {
    choreo.MOVE_SQUAT: 0.524,
    choreo.MOVE_BLOCK: 0.295,
    choreo.MOVE_DODGE: 0.181,
}

# Tabella a DUE entrate (gap x tipo della mossa PRECEDENTE, qualunque tipo),
# misurata sui 465 workout ufficiali (26/08, dopo l'approvazione a procedere -
# measure_centro_type_2d.py in training data/). Il tipo precedente e' un
# segnale forte e in parte indipendente dal gap: es. con gap corto, dopo uno
# Squat e' SEMPRE un altro Squat (100.0%, n=1553), ma dopo un Jab con lo
# STESSO gap corto e' Block nel 74.1% dei casi (n=301) - una differenza che
# la sola tabella 1D (CENTRO_TYPE_PROBS_BY_GAP) non poteva catturare, perche'
# mediava i due casi insieme.
#
# Solo le celle con almeno 200 osservazioni sono incluse: sotto quella soglia
# la percentuale misurata e' rumore, non segnale (es. 'short' dopo Uppercut
# aveva solo 26 osservazioni - scartata, non genuinamente diversa da zero
# solo per caso). Una cella assente qui casca sul fallback 1D
# (CENTRO_TYPE_PROBS_BY_GAP), che resta comunque misurato e affidabile.
CENTRO_TYPE_PROBS_BY_GAP_AND_PREV = {
    ('short', choreo.MOVE_SQUAT):    {choreo.MOVE_SQUAT: 1.000, choreo.MOVE_BLOCK: 0.000, choreo.MOVE_DODGE: 0.000},
    ('short', choreo.MOVE_JAB):      {choreo.MOVE_SQUAT: 0.259, choreo.MOVE_BLOCK: 0.741, choreo.MOVE_DODGE: 0.000},
    ('mid',   choreo.MOVE_JAB):      {choreo.MOVE_SQUAT: 0.370, choreo.MOVE_BLOCK: 0.442, choreo.MOVE_DODGE: 0.188},
    ('mid',   choreo.MOVE_HOOK):     {choreo.MOVE_SQUAT: 0.436, choreo.MOVE_BLOCK: 0.392, choreo.MOVE_DODGE: 0.172},
    ('mid',   choreo.MOVE_UPPERCUT): {choreo.MOVE_SQUAT: 0.471, choreo.MOVE_BLOCK: 0.357, choreo.MOVE_DODGE: 0.171},
    ('mid',   choreo.MOVE_SQUAT):    {choreo.MOVE_SQUAT: 0.763, choreo.MOVE_BLOCK: 0.237, choreo.MOVE_DODGE: 0.000},
    ('long',  choreo.MOVE_UPPERCUT): {choreo.MOVE_SQUAT: 0.624, choreo.MOVE_BLOCK: 0.173, choreo.MOVE_DODGE: 0.203},
    ('long',  choreo.MOVE_JAB):      {choreo.MOVE_SQUAT: 0.510, choreo.MOVE_BLOCK: 0.236, choreo.MOVE_DODGE: 0.254},
    ('long',  choreo.MOVE_HOOK):     {choreo.MOVE_SQUAT: 0.447, choreo.MOVE_BLOCK: 0.301, choreo.MOVE_DODGE: 0.253},
    ('long',  choreo.MOVE_SQUAT):    {choreo.MOVE_SQUAT: 0.783, choreo.MOVE_BLOCK: 0.052, choreo.MOVE_DODGE: 0.165},
    ('long',  choreo.MOVE_DODGE):    {choreo.MOVE_SQUAT: 0.416, choreo.MOVE_BLOCK: 0.110, choreo.MOVE_DODGE: 0.474},
    ('long',  choreo.MOVE_BLOCK):    {choreo.MOVE_SQUAT: 0.398, choreo.MOVE_BLOCK: 0.289, choreo.MOVE_DODGE: 0.313},
}

# Ripartizione Squat -> Dodge+pugno, RICHIESTA ESPLICITAMENTE dall'utente
# (30/08 notte, dopo il primo allenamento reale con marker densi che non
# produceva mai una schivata - vedi [[boxvr_choreo]]): "da 100% del loro
# numero passano a 60%, e il 40% del loro numero diventano schivata con
# jab o gancio". NON una misura sui 465 workout ufficiali come le altre
# probabilita' di questo file - una scelta di design dell'utente per
# compensare la scarsita' quasi totale di schivate nella modalita' marker,
# non un tentativo di replicare fedelmente la distribuzione reale del
# gioco (che infatti non ha mai avuto bisogno di questo aggiustamento:
# li' la schivata compare quando compare, senza doverla "creare" a partire
# da uno squat). Si applica SOLO quando la tabella dei tipi centrali sceglie
# Squat per un marker (mai sui pattern automatici del repertorio ufficiale,
# che restano fedeli al vocabolario originale) - vedi il punto di innesto in
# _place_on_markers.
# Rinominata il 06/09 (era SQUAT_TO_DODGE_COMBO_PROB): la quota resta quella,
# ma cio' che produce non e' piu' un combo. Vedi il commento su
# LEGAL_SIMULTANEOUS in boxvr_choreo.py - la schivata col pugno simultaneo e'
# risultata ineseguibile in VR, e non e' correggibile scegliendo il lato,
# perche' la direzione della schivata non e' scritta da nessuna parte.
SQUAT_TO_DODGE_PROB = _reg('squat_che_diventano_schivate', 0.40)


def griglia_metrica(beats, divisioni=GRID_DIVISIONI):
    """Gli istanti della griglia ritmica e la loro posizione dentro il beat.

    Ritorna una lista ordinata di (istante, fase), con fase 0 sul battere e
    1..divisioni-1 sulle suddivisioni. I beat NON sono equidistanti (la
    griglia viene dal beat-tracking del brano vero), quindi ogni intervallo
    si divide per conto suo invece di usare un passo medio."""
    bt = [b['_triggerTime'] for b in beats]
    punti = []
    for i in range(len(bt) - 1):
        passo = (bt[i + 1] - bt[i]) / float(divisioni)
        if passo <= 0:
            continue
        for k in range(divisioni):
            punti.append((bt[i] + k * passo, k))
    if bt:
        punti.append((bt[-1], 0))
    return punti


def _punto_griglia_vicino(t, griglia, fasi=None):
    """Il punto di griglia piu' vicino a `t`, eventualmente solo fra certe
    fasi. Ritorna (istante, fase, distanza) oppure None se la griglia e'
    vuota."""
    if not griglia:
        return None
    tempi = [p[0] for p in griglia]
    i = bisect.bisect_left(tempi, t)
    migliore = None
    for j in range(max(0, i - 2), min(len(griglia), i + 3)):
        istante, fase = griglia[j]
        if fasi is not None and fase not in fasi:
            continue
        d = abs(istante - t)
        if migliore is None or d < migliore[2]:
            migliore = (istante, fase, d)
    return migliore


def firma_ritmica(marker_times, beats, divisioni=GRID_DIVISIONI):
    """DOVE cadono i colpi dell'utente dentro il beat.

    Ritorna la quota di marker su ciascuna suddivisione (lista lunga
    `divisioni`, somma 1), o None se non c'e' abbastanza materiale. E' la
    differenza che si SENTE fra un tratto marcato a mano e uno generato:
    due coreografie con gli stessi colpi al minuto suonano lontanissime se
    una sta sul battere e l'altra sui levare."""
    griglia = griglia_metrica(beats, divisioni)
    if not griglia or not marker_times:
        return None
    conteggi = [0] * divisioni
    visti = 0
    for t in marker_times:
        vicino = _punto_griglia_vicino(t, griglia)
        if vicino is None:
            continue
        conteggi[vicino[1]] += 1
        visti += 1
    if not visti:
        return None
    return [c / float(visti) for c in conteggi]


def fasi_preferite(firma, soglia=0.12):
    """Le suddivisioni che l'utente usa DAVVERO. Una fase colpita una volta
    su cinquanta e' rumore, non uno stile: tenerla vorrebbe dire riaprire
    tutta la griglia e non aver imparato niente."""
    if not firma:
        return None
    fasi = set(i for i, quota in enumerate(firma) if quota >= soglia)
    return fasi or {0}


def aggancia_marker_alla_griglia(marker_times, beats, divisioni=GRID_DIVISIONI,
                                 max_s=GRID_SNAP_MAX_S, onsets=None):
    """Aggancio magnetico: ogni colpo dell'utente va sulla suddivisione piu'
    vicina, se dista meno di `max_s`.

    Il livello automatico e' costruito sui beat del brano. Un marker a
    quaranta millisecondi dal beat non e' una scelta: e' il tempo di
    reazione della mano, che nemmeno la correzione di latenza azzera. Fra
    due colpi che devono suonare uguali quella differenza si sente, ed e'
    la "differenza grossolana" fra i colpi propri e quelli del tool."""
    griglia = griglia_metrica(beats, divisioni)
    if not griglia:
        return list(marker_times)
    passi = [griglia[i + 1][0] - griglia[i][0] for i in range(min(len(griglia) - 1, 200))]
    passo = sorted(passi)[len(passi) // 2] if passi else 0.0
    tolleranza = min(max_s, GRID_SNAP_FRAZIONE * passo) if passo else max_s
    fuori = []
    for t in marker_times:
        # Un colpo che sta gia' su un accento VERO del brano non si tocca:
        # l'accento e' un fatto del brano, la griglia e' la nostra
        # approssimazione del brano. Se le due cose non coincidono, ha
        # ragione il brano.
        if onsets and _su_un_accento(t, onsets):
            fuori.append(t)
            continue
        vicino = _punto_griglia_vicino(t, griglia)
        fuori.append(vicino[0] if (vicino and vicino[2] <= tolleranza) else t)
    return sorted(fuori)


def _su_un_accento(t, onsets, tolleranza=0.005):
    """`t` cade praticamente su un accento audio gia' noto."""
    i = bisect.bisect_left(onsets, t)
    for j in (i - 1, i):
        if 0 <= j < len(onsets) and abs(onsets[j] - t) <= tolleranza:
            return True
    return False


def ritma_come_utente(azioni, beats, firma, divisioni=GRID_DIVISIONI,
                      soglia=0.03):
    """Rimette i colpi generati sulle suddivisioni che l'utente usa davvero,
    NELLE SUE PROPORZIONI.

    Sostituisce `allinea_azioni_alla_firma`, che spostava ogni colpo sulla
    fase ammessa piu' VICINA. Con la coreografia automatica costruita sui
    beat, "la piu' vicina" era quasi sempre la stessa per tutti, e le
    proporzioni collassavano. Misurato su tre marcature:

        l'utente marca                      usciva              adesso
        50% fase 1, 50% fase 3              100% sulla 3        50/50
        32% battere, 68% contrattempo       100% sul battere    32/68

    E le proporzioni SONO il ritmo: due tratti con gli stessi colpi al
    minuto suonano lontanissimi se uno sta sul battere e l'altro no. Lo dice
    gia' il commento di `firma_ritmica`; il codice che doveva applicarlo
    faceva il contrario, e quello che ne usciva era un metronomo - cioe' "lo
    standard BoxVR" della segnalazione in VR del 06/09.

    Come funziona: beat per beat, ogni suddivisione accumula il credito che
    le spetta (la sua quota, per quanti colpi ha quel beat); si servono
    quelle col credito piu' alto; chi viene servito paga. Sulla lunga
    distanza ciascuna e' servita in proporzione al suo peso. Nessun
    sorteggio: due generazioni dello stesso brano danno lo stesso risultato.

    Non cambia QUANTI colpi ci sono (la densita' l'ha decisa il preset) ne'
    QUALI sono (tipo e corsia vengono dal repertorio): cambia solo dove
    cadono.

    Gli ostacoli non si toccano: l'utente non li marca mai, e spostarli
    significherebbe inventargli un'intenzione che non ha espresso."""
    if not firma or not azioni or not beats:
        return list(azioni)

    usate = [k for k, q in enumerate(firma) if q >= soglia]
    if not usate or len(usate) >= divisioni:
        # usa tutta la griglia: non c'e' una preferenza da riprodurre
        return list(azioni)
    totale = sum(firma[k] for k in usate) or 1.0
    peso = {k: firma[k] / totale for k in usate}
    # per i colpi in eccesso (piu' colpi che suddivisioni usate in un beat):
    # le suddivisioni meno battute, mai fuori dalla griglia dell'utente
    riserva = sorted((k for k in range(divisioni) if k not in peso),
                     key=lambda k: -firma[k])

    ostacoli = (choreo.MOVE_SQUAT, choreo.MOVE_DODGE, choreo.MOVE_BLOCK)
    fermi = [a for a in azioni if a.get('moveType') in ostacoli]
    mobili = [a for a in azioni if a.get('moveType') not in ostacoli]
    if not mobili:
        return list(azioni)

    tempi_beat = [b['_triggerTime'] for b in beats]
    per_beat = {}
    fuori = []
    for a in mobili:
        i = bisect.bisect_right(tempi_beat, a['startTime'] + 1e-9) - 1
        if i < 0 or i >= len(beats) - 1:
            fuori.append(a)
            continue
        per_beat.setdefault(i, []).append(a)

    risultato = list(fermi) + fuori
    credito = {k: 0.0 for k in usate}
    for i in sorted(per_beat):
        gruppo = sorted(per_beat[i], key=lambda a: a['startTime'])
        t0 = tempi_beat[i]
        passo = (tempi_beat[i + 1] - t0) / float(divisioni)
        if passo <= 0:
            risultato.extend(dict(a) for a in gruppo)
            continue
        for k in usate:
            credito[k] += peso[k] * len(gruppo)
        quanti = min(len(gruppo), len(usate))
        # a parita' di credito decide la suddivisione piu' pesante, poi la
        # piu' presto nel beat
        scelte = sorted(usate, key=lambda k: (-credito[k], -peso[k], k))[:quanti]
        for k in scelte:
            credito[k] -= 1.0
        scelte = scelte + riserva[:max(0, len(gruppo) - quanti)]
        scelte.sort()
        for a, fase in zip(gruppo, scelte):
            b = dict(a)
            b['startTime'] = t0 + fase * passo
            risultato.append(b)
        # se i colpi sono piu' delle suddivisioni, gli ultimi restano dove
        # sono: la densita' non si tocca, ma due colpi non possono stare
        # sullo stesso istante
        risultato.extend(dict(a) for a in gruppo[len(scelte):])

    risultato.sort(key=lambda a: a['startTime'])
    return risultato


def allinea_azioni_alla_firma(azioni, beats, fasi, divisioni=GRID_DIVISIONI):
    """Riporta la coreografia automatica sulle suddivisioni che usa l'utente.

    SUPERATA il 06/09 da `ritma_come_utente`, e vale la pena dire perche':
    questa sposta ogni colpo sulla fase ammessa piu' VICINA, e con la
    coreografia automatica tutta sul battere "la piu' vicina" e' quasi
    sempre la stessa per tutti. Misurato: una marcatura 32% battere / 68%
    contrattempo usciva 100% sul battere. Le proporzioni sono il ritmo, e
    appiattirle da' un metronomo - la segnalazione in VR diceva
    esattamente "scivolano nello standard BoxVR".

    Resta perche' e' l'unica cosa sensata quando si conoscono le fasi ma non
    le loro proporzioni, e perche' i test la usano per confrontare i due
    comportamenti.

    Gli ostacoli (Squat/Schivata/Block) NON si toccano: non sono colpi,
    l'utente non li marca mai, e spostarli sulle sue fasi significherebbe
    inventargli un'intenzione che non ha espresso."""
    if not fasi or len(fasi) >= divisioni:
        return list(azioni)          # usa tutta la griglia: niente da allineare
    griglia = griglia_metrica(beats, divisioni)
    if not griglia:
        return list(azioni)
    ostacoli = (choreo.MOVE_SQUAT, choreo.MOVE_DODGE, choreo.MOVE_BLOCK)
    fuori = []
    for a in azioni:
        if a.get('moveType') in ostacoli:
            fuori.append(a)
            continue
        vicino = _punto_griglia_vicino(a['startTime'], griglia, fasi)
        if vicino is None:
            fuori.append(a)
            continue
        b = dict(a)
        b['startTime'] = vicino[0]
        fuori.append(b)
    fuori.sort(key=lambda a: a['startTime'])
    return fuori


def _durata_battuta(beats):
    """Quanto dura una battuta, dai beat veri del brano."""
    if not beats:
        return 2.0
    lunghezze = sorted(b.get('_beatLength') or 0.5 for b in beats)
    return lunghezze[len(lunghezze) // 2] * BEATS_PER_BAR


def pausa_di_stacco(marker_ordinati, beats):
    """Oltre quanto silenzio due marker non appartengono piu' alla stessa
    frase. Si ricava dal modo di marcare dell'utente, non da una costante:
    chi tira raffiche di sedicesimi e chi segna un colpo a battuta hanno
    due idee diverse di "pausa"."""
    battuta = _durata_battuta(beats)
    minimo, massimo = PAUSA_MIN_BATTUTE * battuta, PAUSA_MAX_BATTUTE * battuta
    if len(marker_ordinati) < 3:
        return massimo
    salti = sorted(marker_ordinati[i + 1] - marker_ordinati[i]
                   for i in range(len(marker_ordinati) - 1))
    tipico = salti[len(salti) // 2]
    return max(minimo, min(massimo, PAUSA_MULTIPLO * tipico))


def raggruppa_marker(marker_ordinati, beats):
    """I marker divisi in gruppi: due colpi separati da una pausa di stacco
    stanno in due gruppi diversi."""
    if not marker_ordinati:
        return []
    stacco = pausa_di_stacco(marker_ordinati, beats)
    gruppi, corrente = [], [marker_ordinati[0]]
    for t in marker_ordinati[1:]:
        if t - corrente[-1] > stacco:
            gruppi.append(corrente)
            corrente = [t]
        else:
            corrente.append(t)
    gruppi.append(corrente)
    return gruppi


def classifica_marcatura(marker_ordinati, beats):
    """Divide i marker in BLOCCHI RITMICI e ACCENTI ISOLATI.

    Ritorna un dict con:
      'blocchi'  - lista di gruppi che dettano un ritmo (il tool non ci
                   mette niente di suo)
      'accenti'  - lista di gruppi troppo corti o troppo radi per essere un
                   ritmo (l'automatico continua a scorrere, il colpo vince)
      'intervalli' - (inizio, fine) di ogni blocco ritmico
      'copertura'  - somma delle durate dei blocchi: e' QUESTA la copertura
                     vera, non "dall'ultimo al primo marker" (che con due
                     colpi agli estremi del brano valeva tre minuti)
      'colpi_nei_blocchi' - quanti marker stanno dentro i blocchi
    """
    battuta = _durata_battuta(beats)
    blocchi, accenti = [], []
    for gruppo in raggruppa_marker(marker_ordinati, beats):
        durata = gruppo[-1] - gruppo[0]
        if len(gruppo) >= BLOCCO_MIN_COLPI and durata >= BLOCCO_MIN_BATTUTE * battuta:
            blocchi.append(gruppo)
        else:
            accenti.append(gruppo)
    return {
        'blocchi': blocchi,
        'accenti': accenti,
        'intervalli': [(g[0], g[-1]) for g in blocchi],
        'copertura': sum(g[-1] - g[0] for g in blocchi),
        'colpi_nei_blocchi': sum(len(g) for g in blocchi),
    }


def _dentro_un_blocco(t, intervalli):
    for a, b in intervalli:
        if a <= t <= b:
            return True
    return False


def ha_imparato(copertura_s, n_marker):
    """L'unica regola che decide se «Estendi» puo' dire di aver imparato.

    La usano SIA il motore SIA il pannello: quando erano due condizioni
    scritte in due punti, il pannello annunciava "Estendi usera' la tua
    cadenza" mentre il motore ricadeva sul preset del brano."""
    return copertura_s >= EXTEND_MIN_COVERAGE_S and n_marker >= EXTEND_MIN_MARKER


def copertura_marcata(marker_times, onsets=None, min_gap_s=MIN_INPUT_GAP_S,
                      beats=None):
    """Come e' fatta la marcatura dell'utente, per il motore e per il pannello.

    Stessa pipeline di `snap_and_filter_markers` e stessa classificazione del
    motore, cosi' il numero mostrato nell'interfaccia e quello su cui il
    motore decide non possono divergere: e' gia' successo, e il pannello
    annunciava "Estendi usera' la tua cadenza" mentre il motore ricadeva sul
    preset del brano.

    Senza `beats` (analisi del brano non ancora pronta) non si puo'
    classificare niente - i gruppi si misurano in battute - e si risponde
    dicendolo, invece di dare un numero inventato.
    """
    filtrati = snap_and_filter_markers(marker_times, onsets, min_gap_s)
    if not beats:
        return {'analisi_pronta': False, 'marker': len(filtrati),
                'minimo': EXTEND_MIN_COVERAGE_S, 'minimo_marker': EXTEND_MIN_MARKER,
                'secondi': 0.0, 'blocchi': 0, 'accenti': 0,
                'intervalli': [], 'accenti_intervalli': [], 'sufficiente': False}
    m = classifica_marcatura(filtrati, beats)
    return {
        'analisi_pronta': True,
        'blocchi': len(m['blocchi']),
        'accenti': len(m['accenti']),
        # per la banda sulla timeline: dove sta ciascuno
        'intervalli': [[a, b] for a, b in m['intervalli']],
        'accenti_intervalli': [[g[0], g[-1]] for g in m['accenti']],
        # la copertura vera: la SOMMA dei blocchi ritmici
        'secondi': m['copertura'],
        'marker': m['colpi_nei_blocchi'],
        'marker_totali': len(filtrati),
        'minimo': EXTEND_MIN_COVERAGE_S,
        'minimo_marker': EXTEND_MIN_MARKER,
        'sufficiente': ha_imparato(m['copertura'], m['colpi_nei_blocchi']),
    }


def togli_ostacoli(azioni):
    """Via squat e schivate dal livello automatico, per «nessun ostacolo».

    Fino al 07/09 quell'opzione arrivava solo ai marker dell'utente, quindi
    gli ostacoli AUTOMATICI restavano tutti: misurati 11 squat ancora
    presenti in Armonizza e 5 in «Solo marker», con una catena da otto.

    Lo SCUDO resta: e' una mossa di braccia, si para in piedi, e non ha
    niente a che vedere con l'abbassarsi. Ma se sta nello STESSO ISTANTE di
    uno squat se ne va con lui: quello e' il combo Block+Squat, l'unica
    coppia simultanea che il gioco usa davvero, e li' lo scudo e' basso
    perche' il corpo e' gia' abbassato - senza lo squat sotto non e' piu'
    quella mossa. E' quello che chiede la segnalazione: gli squat con lo
    scudo contano come squat.
    """
    fuori = (choreo.MOVE_SQUAT, choreo.MOVE_DODGE)
    istanti_ostacolo = {round(a['startTime'], 4)
                        for a in azioni if a['moveType'] in fuori}
    return [a for a in azioni
            if a['moveType'] not in fuori
            and not (a['moveType'] == choreo.MOVE_BLOCK
                     and round(a['startTime'], 4) in istanti_ostacolo)]


def _keep_auto_obstacles(auto_full):
    """Tiene Squat/Dodge del livello automatico (MAI un Block da solo - vedi
    il commento su `exclude_obstacles`: gli ostacoli restano una scelta
    esclusiva dell'automatico, mai imposti su un istante marcato a mano),
    MA se uno Squat automatico ha un Block simultaneo allo STESSO istante
    esatto tiene anche quel Block, invece di romperne la coppia.

    Bug reale in VR (30/08): "gli scudi che normalmente erano sotto uno
    squat, ora erano sempre alti e sempre poco prima dello squat, rendendo
    difficile pararsi e abbassarsi". Causa: Squat+Block simultaneo e' un
    combo VERO e comune del repertorio ufficiale (misurato: 5 delle 11
    famiglie di pattern Normal a intensita' alta lo contengono, es.
    AutoSeq_Compl_5_G/5_I/5_K), non una coincidenza - `build_move_actions`
    lo emette gia' risolto da `enforce_playability`
    (LEGAL_SIMULTANEOUS in boxvr_choreo.py), quindi qualunque Block nel
    livello automatico che condivide l'istante esatto di uno Squat tenuto
    e' per costruzione il suo compagno di combo, non un ostacolo isolato.
    Il vecchio filtro (solo moveType in Squat/Dodge) scartava sempre quel
    Block, lasciando lo squat orfano - un marker vicino dell'utente
    finiva per piazzarne uno slegato poco prima, invece che insieme."""
    by_time = {}
    for a in auto_full:
        by_time.setdefault(round(a['startTime'], 6), []).append(a)
    kept = []
    for group in by_time.values():
        types = {a['moveType'] for a in group}
        if choreo.MOVE_SQUAT in types or choreo.MOVE_DODGE in types:
            kept.extend(a for a in group
                        if a['moveType'] in (choreo.MOVE_SQUAT, choreo.MOVE_DODGE, choreo.MOVE_BLOCK))
    return kept


def _gap_bucket(gap_beats):
    if gap_beats is None:
        return 'none'
    if gap_beats < 0.75:
        return 'short'
    if gap_beats < 1.5:
        return 'mid'
    return 'long'


def _sposta_peso_squat_scudo(probs):
    """Il cursore `preferenza_squat_contro_scudo` applicato a una riga.

    A 0 la riga resta com'e' stata misurata sui 465 workout. Verso -1 il
    peso passa dallo squat allo scudo, verso +1 il contrario. Le somme
    restano 1 per costruzione: si sposta peso, non se ne aggiunge.

    Serve perche' la tabella da' lo squat all'86% quando c'e' poco spazio e
    al 42-56% altrove - domina ovunque, e lo scudo compare solo quando
    avanza posto. E' la causa diretta di «tutti gli scudi sono solo con
    squat» (07/09). Esporre le nove celle sarebbe un invito a rompere
    l'equilibrio senza accorgersene: un cursore solo, che le muove tutte
    insieme, fa la stessa cosa senza quel rischio.
    """
    k = _reg('preferenza_squat_contro_scudo', 0.0)
    if not k:
        return probs
    squat = probs.get(choreo.MOVE_SQUAT, 0.0)
    scudo = probs.get(choreo.MOVE_BLOCK, 0.0)
    if k < 0:
        sposta = squat * min(1.0, -k)          # dallo squat allo scudo
        squat, scudo = squat - sposta, scudo + sposta
    else:
        sposta = scudo * min(1.0, k)           # dallo scudo allo squat
        scudo, squat = scudo - sposta, squat + sposta
    nuove = dict(probs)
    nuove[choreo.MOVE_SQUAT] = squat
    nuove[choreo.MOVE_BLOCK] = scudo
    return nuove


def _sample_weighted(probs, rng):
    r = rng.random()
    acc = 0.0
    for k, p in probs.items():
        acc += p
        if r < acc:
            return k
    return next(iter(probs))   # ripiego per arrotondamento float


def snap_and_filter_markers(marker_times, onsets=None, min_gap_s=MIN_INPUT_GAP_S,
                            beats=None):
    """Applica ESATTAMENTE la stessa pipeline di `_place_on_markers` prima di
    decidere corsia/tipo: aggancio agli accenti veri (se `onsets` dato), poi
    il filtro sul limite fisico minimo fra input consecutivi (MIN_INPUT_GAP_S
    di default, sovrascrivibile con `min_gap_s`). Estratta come funzione a
    se' (30/08, richiesto: dare visibilita' a quanti marker vengono davvero
    scartati - prima la GUI non aveva modo di saperlo senza duplicare questa
    logica, col rischio che le due copie finissero per divergere) cosi' sia
    `_place_on_markers` sia chi vuole solo CONTARE i sopravvissuti (es. la
    GUI, per avvisare l'utente prima ancora di generare) usano la stessa
    identica regola.

    `min_gap_s` (30/08, richiesto esplicitamente - "possiamo avere uno
    slider per la soglia?"): MIN_INPUT_GAP_S e' un limite MISURATO (minimo
    assoluto sui 465 workout ufficiali, mai violato), non una scelta
    arbitraria - ma resta una scelta prudente lasciare all'utente la
    possibilita' di abbassarlo consapevolmente per un brano specifico (es.
    un riff molto veloce dove alcuni marker sono piu' ravvicinati di
    qualunque cosa il gioco abbia mai generato), mostrandogli chiaramente
    quanti marker questo scarterebbe PRIMA di generare, invece di imporre il
    valore misurato come un tetto invalicabile silenzioso."""
    ordered = sorted(marker_times)
    if onsets:
        ordered = sorted(_snap_marker_to_onset(t, onsets) for t in ordered)
    # Aggancio magnetico alla griglia, DOPO l'accento audio e PRIMA del
    # filtro: l'accento e' un fatto del brano e viene prima di tutto, la
    # griglia raddrizza cio' che resta, e solo alla fine si decide chi e'
    # troppo vicino a chi - altrimenti si scarterebbero marker che dopo
    # l'aggancio sarebbero stati distanti a sufficienza.
    if beats:
        ordered = aggancia_marker_alla_griglia(ordered, beats, onsets=onsets)
    filtered = []
    for t in ordered:
        if filtered and (t - filtered[-1]) < min_gap_s:
            continue
        filtered.append(t)
    return filtered


def _place_on_markers(marker_times, beats, rng, context_actions=None, exclude_obstacles=False,
                      onsets=None, min_gap_s=MIN_INPUT_GAP_S,
                      aggancio_magnetico=False):
    """Decide corsia/tipo per ogni marker dell'utente e ritorna le azioni
    GREZZE (non ancora passate da enforce_playability - la risoluzione dei
    conflitti e' compito di chi chiama, cosi' puo' farla insieme al livello
    automatico invece che due volte separate).

    `marker_times`: secondi, in qualunque ordine - vengono ordinati qui.
    `beats`: la lista di beat dell'analisi, serve `_triggerTime`/
    `_beatLength`/`_beatInBar`.

    `context_actions` (26/08, seconda meta' della notte): le azioni GIA'
    piazzate dal livello automatico (`build_move_actions`), ordinate o meno -
    vengono riordinate qui. Se date, ogni decisione (centro/laterale, tipo,
    lato) guarda anche a QUESTE, non solo ai marker precedenti dell'utente.
    Prima i due livelli non condividevano la memoria del ritmo: un marker
    subito dopo un colpo automatico non lo "vedeva", quindi poteva scegliere
    lo stesso lato (invece di alternare, come misurato sull'84% dei workout
    ufficiali) o un tipo implausibile subito dopo quello vero - il difetto si
    intrecciava solo alla fine, in enforce_playability, che pero' verifica
    solo la GIOCABILITA' (spaziatura/corsie legali), non la plausibilita'
    statistica della sequenza. Senza `context_actions` il comportamento resta
    quello di prima (place_moves_on_markers, usato nei test in isolamento).

    `exclude_obstacles` (27/08, "solo hit marker" - richiesto esplicitamente:
    "sui marker devono andarci solo scudi o colpi"): se True, la decisione
    centro non sceglie mai Squat/Dodge per un marker - solo Block. Non tocca
    la probabilita' centro-vs-laterale (A4, misurata), solo QUALE mossa
    centrale: gli ostacoli restano una scelta del solo livello automatico,
    mai imposti su un istante che l'utente ha marcato a mano.

    `onsets` (27/08, "correggere leggere imprecisioni dei marker" -
    richiesto esplicitamente): se dati, ogni marker entro
    MARKER_SNAP_WINDOW_S da un accento audio VERO viene spostato esattamente
    li' prima di ogni altra decisione - vedi _snap_marker_to_onset. None
    (default) disattiva la correzione, comportamento di sempre."""
    if not beats:
        return []
    ts_beats = [b['_triggerTime'] for b in beats]

    # Correzione (se richiesta) e filtro sul limite fisico fra input
    # consecutivi (min_gap_s) - vedi snap_and_filter_markers, condivisa con
    # chi vuole solo CONTARE i sopravvissuti senza duplicare la regola.
    filtered = snap_and_filter_markers(marker_times, onsets, min_gap_s,
                                      beats=(beats if aggancio_magnetico else None))

    context_actions = sorted(context_actions or [], key=lambda a: a['beatNumber'])
    context_beats = [a['beatNumber'] for a in context_actions]

    actions = []
    placed_beats = []   # parallela ad `actions`, per lo stesso bisect - vedi _most_recent

    def _most_recent(before_beat, predicate):
        """Ultima azione con beatNumber < before_beat che soddisfa
        `predicate`, cercando SIA nel livello automatico SIA fra i marker
        gia' decisi in questo stesso giro (non solo nell'uno o nell'altro) -
        None se nessuna delle due la soddisfa. Bisect su liste precalcolate:
        poche decine di marker per brano, ma centinaia di azioni automatiche,
        farlo con una scansione lineare a ogni marker sarebbe comunque
        accettabile qui - il bisect e' immediato e non costa nulla in piu'."""
        best = None
        for lst, beat_lst in ((context_actions, context_beats), (actions, placed_beats)):
            i = bisect.bisect_left(beat_lst, before_beat)
            for j in range(i - 1, -1, -1):
                if predicate(lst[j]):
                    if best is None or lst[j]['beatNumber'] > best['beatNumber']:
                        best = lst[j]
                    break
        return best

    for t in filtered:
        i = bisect.bisect_right(ts_beats, t) - 1
        i = min(max(i, 0), len(beats) - 1)
        bl = beats[i].get('_beatLength') or 0.5
        beat_number = i + (t - beats[i]['_triggerTime']) / bl if bl else float(i)
        bib = beats[i].get('_beatInBar', 1)

        # A4: gap dall'ultima mossa LATERALE (channel != CENTRO), di
        # QUALUNQUE provenienza - serve anche sotto per tipo/lato laterale,
        # una sola ricerca invece di due (la stessa mossa risponde a entrambe
        # le domande: "quanto spazio c'era" e "cosa/dove era l'ultima").
        recent_lateral = _most_recent(beat_number, lambda a: a['moveChannel'] != choreo.CH_CENTER)
        gap = (beat_number - recent_lateral['beatNumber']) if recent_lateral is not None else None
        bucket = _gap_bucket(gap)
        p_centro = CENTRO_PROB_TABLE.get((bib, bucket), CENTRO_PROB_FALLBACK)

        if rng.random() < p_centro:
            if exclude_obstacles:
                # "solo hit marker": niente Squat/Dodge su un istante marcato
                # a mano - l'unica mossa centrale ammessa e' lo scudo. Non si
                # ricampiona nient'altro: con Squat/Dodge esclusi resta un solo
                # candidato, non serve rifare i conti di probabilita'.
                move_type = choreo.MOVE_BLOCK
            else:
                # il TIPO di mossa centrale dipende dallo spazio disponibile
                # dalla mossa precedente qualunque E dal SUO tipo - cascata
                # dalla piu' alla meno specifica, ciascuna misurata (26/08):
                #   1. tabella a due entrate (gap, tipo precedente), solo
                #      celle con abbastanza dati - CENTRO_TYPE_PROBS_BY_GAP_AND_PREV
                #   2. tabella a una entrata (solo gap) se la cella 2D manca o
                #      non c'e' ancora una mossa precedente da cui prenderne
                #      il tipo - CENTRO_TYPE_PROBS_BY_GAP
                #   3. media piatta se non c'e' nemmeno una mossa prima
                #      (inizio brano/frase, nessun gap misurabile) - CENTRO_TYPE_PROBS
                recent_any = _most_recent(beat_number, lambda a: True)
                gap_any = (beat_number - recent_any['beatNumber']) if recent_any is not None else None
                if gap_any is None:
                    centro_probs = CENTRO_TYPE_PROBS
                else:
                    bucket_any = _gap_bucket(gap_any)
                    centro_probs = CENTRO_TYPE_PROBS_BY_GAP_AND_PREV.get(
                        (bucket_any, recent_any['moveType']),
                        CENTRO_TYPE_PROBS_BY_GAP[bucket_any])
                move_type = _sample_weighted(
                    _sposta_peso_squat_scudo(centro_probs), rng)

                if move_type == choreo.MOVE_SQUAT and rng.random() < SQUAT_TO_DODGE_PROB:
                    # Una quota degli squat diventa SCHIVATA (vedi
                    # SQUAT_TO_DODGE_PROB): senza, la modalita' marker non ne
                    # produce quasi mai una.
                    #
                    # Fino al 06/09 qui si generava una schivata PIU' un pugno
                    # simultaneo. In VR e' risultato ineseguibile: il corpo e'
                    # spostato di lato e meta' dello spazio e' occupata
                    # dall'ostacolo. Adesso e' una mossa sola.
                    #
                    # Lo spazio attorno glielo fa rispettare
                    # enforce_playability, che conosce MIN_GAP_DODGE_BEATS e
                    # lo applica alla coreografia UNITA - automatico compreso
                    # - invece che solo a cio' che si vede da qui: spostando
                    # la mossa di poco quando basta, e scartandola solo se
                    # proprio non ci sta.
                    move_type = choreo.MOVE_DODGE
            move_channel = choreo.CH_CENTER
        else:
            prev_arm_type = recent_lateral['moveType'] if recent_lateral is not None else choreo.MOVE_JAB
            move_type = choreo._sample_next_arm_move(prev_arm_type, rng)
            # lato SEMPRE alternato rispetto all'ultimo laterale VERO (di
            # qualunque provenienza), non a un contatore separato per i soli
            # marker - e' esattamente il difetto che questa modifica corregge.
            if recent_lateral is not None:
                move_channel = (choreo.CH_BACK if recent_lateral['moveChannel'] == choreo.CH_FRONT
                                else choreo.CH_FRONT)
            else:
                move_channel = choreo.CH_FRONT

        action = {
            'startTime': float(t),
            'beatNumber': float(beat_number),
            'moveType': move_type,
            'moveChannel': move_channel,
            '_exact': True,
            '_sidecar': True,   # tag di provenienza - vince SEMPRE in enforce_playability
        }
        actions.append(action)
        placed_beats.append(beat_number)
    return actions


# Le modalita' (27/08, richieste esplicitamente): quanto la coreografia
# reale del brano viene onorata rispetto ai marker. MODE_AUTOMATIC (i marker
# ignorati per questa generazione, ma tenuti salvati) e' stato RIMOSSO il
# 30/08: da quando esiste uno strumento "Automatica" a se stante, separato
# dalla sidecar (vedi boxvr_fixer_gui.py, generate_tool), passare a
# quello strumento produce lo stesso identico risultato (generazione
# automatica pura, marker intatti sul brano) - tenere anche una modalita'
# interna alla sidecar con lo stesso effetto era solo un secondo nome per
# la stessa cosa, fonte di confusione segnalata dall'utente.
MODE_HARMONIZE = 'harmonize'        # comportamento di sempre: automatico intero + marker sopra
MODE_MARKERS_ONLY = 'markers_only'  # niente pattern automatico - solo i marker
                                     # PIU' gli ostacoli (vedi build_choreography)
MODE_EXTEND = 'extend'              # 30/08, richiesto esplicitamente: fedele ai
                                     # marker DOVE ci sono, automatico pieno SOLO
                                     # dove non ci sono (vedi build_choreography)


def place_moves_on_markers(marker_times, beats, rng=None, exclude_obstacles=False, onsets=None,
                           min_gap_s=MIN_INPUT_GAP_S):
    """Coreografia SOLO dai marker dell'utente, senza livello automatico -
    utile per provare l'algoritmo A4/Markov in isolamento (vedi test_engine.py),
    o per un brano dove l'utente ha marcato letteralmente tutto. Per l'uso
    normale (copertura parziale, intreccio con la generazione automatica)
    vedi `build_choreography()` sotto.

    Ritorna azioni pronte per `serialize_actions`, gia' passate per
    `enforce_playability(snap_to_grid=False)`."""
    rng = rng or random.Random()
    actions = _place_on_markers(marker_times, beats, rng, exclude_obstacles=exclude_obstacles,
                                onsets=onsets, min_gap_s=min_gap_s)
    return choreo.enforce_playability(actions, beats, snap_to_grid=False, sidecar_min_gap_s=min_gap_s)


def preset_su_misura(n_colpi, durata_s, preset_base='high'):
    """Un preset con la TUA cadenza, quando superi il piu' intenso.

    Ritorna (nome, configurazione) da passare a build_move_actions, oppure
    None se la cadenza sta gia' dentro i preset esistenti.

    Serve perche' `preset_da_cadenza` puo' solo scegliere fra tre, e il piu'
    fitto punta a 88 colpi al minuto: due colpi per beat sono 241, cioe' 2,7
    volte tanto. Tutto cio' che sta sopra veniva ricondotto a 88, ed e' il
    motivo per cui «Estendi» non seguiva i colpi in rapida successione.

    Del preset intenso si tiene TUTTO tranne la densita': vocabolario di
    mosse, livelli di intensita', soglia di riposo sono misurati sui workout
    ufficiali e non c'entrano niente con quanto fitto batti tu.
    """
    if not _reg('estendi_segue_la_tua_cadenza', 1):
        return None
    minuti = durata_s / 60.0
    if minuti <= 0 or not n_colpi:
        return None
    tua = n_colpi / minuti
    base = choreo.INTENSITY_PRESETS.get(preset_base)
    if not base:
        return None
    tetto = base.get('target_epm', 0)
    if tua <= tetto:
        return None                       # ci sta gia' dentro
    cfg = dict(base)
    cfg['target_epm'] = tua
    basso, alto = cfg.get('epm_range', (tetto, tetto))
    cfg['epm_range'] = (basso, max(alto, tua))
    cfg['label'] = '%s (la tua cadenza: %.0f/min)' % (base.get('label', preset_base), tua)
    return ('_su_misura', cfg)


def preset_da_cadenza(n_colpi, durata_s):
    """Quale INTENSITY_PRESETS (light/medium/high, con target_epm MISURATO
    sui 465 workout ufficiali) somiglia di piu' a questa cadenza.

    Prende i due numeri gia' pronti invece dell'intervallo: la cadenza vera
    e' colpi-nei-blocchi diviso durata-dei-blocchi, e con marcature spezzate
    l'intervallo [primo, ultimo] non e' piu' il denominatore giusto."""
    minuti = durata_s / 60.0
    if minuti <= 0 or not n_colpi:
        return None
    osservata = n_colpi / minuti
    migliore, distanza = None, float('inf')
    for nome, cfg in choreo.INTENSITY_PRESETS.items():
        d = abs(cfg['target_epm'] - osservata)
        if d < distanza:
            migliore, distanza = nome, d
    return migliore


def _infer_preset_from_marker_density(filtered_markers, span_start, span_end):
    """Stima quale INTENSITY_PRESETS (boxvr_choreo.py - light/medium/high,
    con target_epm MISURATO sui 465 workout ufficiali, non a intuito)
    somiglia di piu' alla cadenza REALE dei marker dell'utente nel tratto
    marcato, in colpi al minuto - usata da MODE_EXTEND per generare il
    resto del brano (30/08, richiesto esplicitamente dopo la prima prova
    reale: "deve essere piu' aggressiva, non sta seguendo le logiche
    dell'utente ma continua a fare coreografie classiche BoxVR" - prima il
    tratto fuori dallo span usava sempre e solo il preset gia' configurato
    sul brano, spesso 'medium' per default, a prescindere da quanto densi
    fossero davvero i marker).

    None se lo span e' degenere (un solo marker, o marker tutti sullo
    stesso istante) - in quel caso non c'e' una cadenza da misurare, meglio
    ricadere sul preset gia' scelto per il brano che su un numero senza
    senso."""
    return preset_da_cadenza(len(filtered_markers), span_end - span_start)


def build_choreography(analysis, marker_times, preset='medium', rng=None,
                       mode=MODE_HARMONIZE, exclude_obstacles=False, correct_imprecision=False,
                       min_gap_s=MIN_INPUT_GAP_S, aggancio_magnetico=True):
    """Uso normale della sidecar: i marker dell'utente possono coprire
    QUALUNQUE frazione del brano (tutto, niente, solo i ritornelli).

    `mode` (27/08, richiesto esplicitamente - vedi MODE_* sopra):
    - MODE_HARMONIZE (default, comportamento di sempre): il resto lo scrive
      la generazione automatica esattamente come farebbe da sola, gli stessi
      accenti audio veri e le stesse figure anche VICINO a un marker, non
      solo lontano da esso. Un marker dell'utente vince sempre un conflitto
      (vedi il sotto-livello '_sidecar' in enforce_playability, boxvr_choreo.py).
    - MODE_MARKERS_ONLY: nessun pattern automatico - il resto del brano resta
      silenzioso, TRANNE gli ostacoli (Squat/Dodge), che continuano a essere
      piazzati dal livello automatico indipendentemente dai marker. Motivo:
      l'utente non marca mai un ostacolo (non è un "colpo" nel senso in cui
      marca gli altri), quindi anche nella modalita' piu' minimale il
      workout ha comunque bisogno di variare fisicamente - richiesto
      esplicitamente: "gli ostacoli vanno gestiti in autonomia a prescindere
      dalla rete di marker (anche in modalita' solo marker)".
    - MODE_EXTEND (30/08, richiesto esplicitamente, poi reso piu' aggressivo
      dopo la prima prova reale): un ibrido pensato per chi marca solo UNA
      PARTE del brano (es. il primo minuto e mezzo di tre) e vuole che il
      resto non resti ne' silenzioso (MODE_MARKERS_ONLY) ne' "sporcato" da
      colpi automatici non richiesti anche dove ha gia' marcato (il difetto
      di MODE_HARMONIZE). Dentro l'intervallo [primo marker, ultimo marker]:
      stessa riduzione di MODE_MARKERS_ONLY (solo marker + ostacoli
      autonomi, nessuna interferenza automatica). Fuori da quell'intervallo:
      generazione automatica PIENA, con il preset (light/medium/high) la cui
      cadenza MISURATA (target_epm, boxvr_choreo.INTENSITY_PRESETS) somiglia
      di piu' a quella osservata nei marker dell'utente dentro lo span -
      vedi _infer_preset_from_marker_density - non piu' semplicemente il
      preset gia' configurato sul brano (spesso 'medium' di default, a
      prescindere da quanto densi fossero davvero i marker: la prima
      versione di questa modalita' "continuava a fare coreografie classiche
      BoxVR" invece di seguire la cadenza scelta dall'utente).

    `exclude_obstacles` ("solo hit marker"): se True, i marker stessi non
    generano mai Squat/Dodge (solo Block o colpi) - vedi _place_on_markers.
    Indipendente da `mode`: ha senso anche in MODE_HARMONIZE.

    `correct_imprecision` (27/08, richiesto esplicitamente, indipendente da
    `mode` ed `exclude_obstacles`): se True, un marker entro
    MARKER_SNAP_WINDOW_S da un accento audio vero di `analysis['onsets']`
    viene spostato esattamente li' - vedi _snap_marker_to_onset.

    `analysis`: il dict completo di boxvr_generator.generate_song_analysis
    (o analysis_from_installed) - serve tutto, non solo i beat, perche' il
    livello automatico e' `build_move_actions` per intero, non una versione
    ridotta.

    Il livello automatico (o la sua sola parte ostacoli, in MODE_MARKERS_ONLY)
    viene generato PRIMA e passato come contesto a `_place_on_markers` (26/08):
    ogni marker dell'utente decide corsia/tipo guardando anche alle mosse
    automatiche vicine, non solo agli altri marker.

    `min_gap_s` (30/08): soglia minima fra due marker consecutivi, vedi
    snap_and_filter_markers - default MIN_INPUT_GAP_S (170ms, il minimo
    misurato sui 465 workout ufficiali), sovrascrivibile per-brano se
    l'utente sceglie consapevolmente di scendere sotto quel valore."""
    rng = rng or random.Random()
    beats = analysis['beats']
    if not beats:
        return []

    auto_full = choreo.build_move_actions(analysis, preset=preset)
    if mode == MODE_MARKERS_ONLY:
        auto_layer = _keep_auto_obstacles(auto_full)
    elif mode == MODE_EXTEND:
        # I marker si dividono in BLOCCHI RITMICI e ACCENTI ISOLATI, e i due
        # casi vogliono trattamenti opposti (vedi classifica_marcatura):
        #
        #   blocco ritmico  -> l'utente sta dettando un ritmo: li' dentro
        #                      niente colpi automatici, solo i suoi (piu' gli
        #                      ostacoli, che non marca mai)
        #   accento isolato -> l'utente sta mettendo un punto fermo: li'
        #                      l'automatico continua a scorrere e il suo
        #                      colpo vince il conflitto, come in Armonizza
        #   il resto        -> generato, imitando i blocchi se c'e' abbastanza
        #                      materiale per imparare
        #
        # Prima c'era un intervallo unico [primo marker, ultimo marker], e
        # bastava marcare l'inizio e la fine del brano perche' coprisse
        # tutto: non restava niente da estendere e «Estendi» diventava
        # identica a «Solo marker», silenzio in mezzo compreso.
        filtered_markers = snap_and_filter_markers(
            marker_times, analysis.get('onsets') if correct_imprecision else None, min_gap_s,
            beats=(beats if aggancio_magnetico else None))
        marcatura = classifica_marcatura(filtered_markers, beats)
        intervalli = marcatura['intervalli']

        # La copertura vera e' la SOMMA dei blocchi, non "dall'ultimo al
        # primo marker" - che con due colpi agli estremi del brano valeva
        # tre minuti di copertura per due soli colpi.
        imparato = ha_imparato(marcatura['copertura'], marcatura['colpi_nei_blocchi'])

        # La cadenza da imitare si misura sui blocchi: e' li' che l'utente
        # ha davvero dettato un passo.
        inferred_preset = preset
        su_misura = None
        if imparato:
            inferred_preset = preset_da_cadenza(marcatura['colpi_nei_blocchi'],
                                                marcatura['copertura']) or preset
            # E se batti piu' fitto del preset piu' intenso, si segue la TUA
            # cadenza invece di ricondurti a 88 colpi/min: vedi
            # preset_su_misura, e la misura del divario di 2,7 volte.
            su_misura = preset_su_misura(marcatura['colpi_nei_blocchi'],
                                         marcatura['copertura'])
        if su_misura:
            nome, cfg = su_misura
            precedente = choreo.INTENSITY_PRESETS.get(nome)
            choreo.INTENSITY_PRESETS[nome] = cfg
            try:
                auto_outside_source = choreo.build_move_actions(analysis, preset=nome)
            finally:
                # il preset su misura vale per QUESTO brano e basta: e'
                # costruito sulla marcatura di adesso, e lasciarlo in giro
                # lo farebbe usare anche dal brano dopo
                if precedente is None:
                    choreo.INTENSITY_PRESETS.pop(nome, None)
                else:
                    choreo.INTENSITY_PRESETS[nome] = precedente
        else:
            auto_outside_source = (choreo.build_move_actions(analysis, preset=inferred_preset)
                                   if inferred_preset != preset else auto_full)

        inside_obstacles = [a for a in _keep_auto_obstacles(auto_full)
                            if _dentro_un_blocco(a['startTime'], intervalli)]
        outside_full = [a for a in auto_outside_source
                        if not _dentro_un_blocco(a['startTime'], intervalli)]

        # La cadenza dice QUANTI colpi; la firma ritmica dice DOVE. E' la
        # seconda che si sente: due tratti con gli stessi colpi al minuto
        # suonano lontanissimi se uno sta sul battere e l'altro sui levare.
        # La firma si legge SOLO nei blocchi: un accento isolato non e' un
        # ritmo, e mescolarlo sporcherebbe la statistica con un colpo solo.
        if imparato:
            colpi_dei_blocchi = [t for g in marcatura['blocchi'] for t in g]
            # Si PIAZZA dalla firma invece di avvicinare alla firma cio'
            # che era gia' sul battere - vedi ritma_come_utente e il
            # commento sul perche' il metodo precedente appiattiva le
            # proporzioni, che sono la cosa che si sente.
            outside_full = ritma_come_utente(
                outside_full, beats, firma_ritmica(colpi_dei_blocchi, beats))

        auto_layer = inside_obstacles + outside_full
    else:
        # ARMONIZZA. Il livello automatico resta pieno - e' cio' che
        # distingue questa modalita': i colpi del tool continuano a scorrere
        # anche dentro i tratti marcati, e nei conflitti vince il marker.
        # Ma DOVE cadono si impara dall'utente, come in Estendi.
        #
        # Fino al 06/09 qui c'era `auto_full` e basta: il repertorio cosi'
        # com'e', costruito sui beat del brano senza guardare una sola volta
        # dove colpisce chi sta giocando. Segnalato in VR insieme a Estendi
        # - «perdono il ritmo dell'input e scivolano nello standard BoxVR» -
        # e per Armonizza era letterale, perche' non c'era proprio niente
        # che provasse a impararlo.
        #
        # E' l'altra meta' di un lavoro gia' fatto per meta': l'aggancio
        # magnetico avvicina i colpi dell'UTENTE alla griglia del tool,
        # questo avvicina quelli del tool al ritmo dell'utente. Serviva
        # perche' "i colpi propri e quelli del tool non si sentano come due
        # cose diverse", e da un lato solo non bastava.
        auto_layer = auto_full
        filtrati_arm = snap_and_filter_markers(
            marker_times, analysis.get('onsets') if correct_imprecision else None,
            min_gap_s, beats=(beats if aggancio_magnetico else None))
        marcatura_arm = classifica_marcatura(filtrati_arm, beats)
        if ha_imparato(marcatura_arm['copertura'], marcatura_arm['colpi_nei_blocchi']):
            colpi_arm = [t for g in marcatura_arm['blocchi'] for t in g]
            auto_layer = ritma_come_utente(
                auto_layer, beats, firma_ritmica(colpi_arm, beats))

    sidecar_actions = _place_on_markers(
        marker_times, beats, rng, context_actions=auto_layer, exclude_obstacles=exclude_obstacles,
        onsets=(analysis.get('onsets') if correct_imprecision else None), min_gap_s=min_gap_s,
        aggancio_magnetico=aggancio_magnetico)

    if exclude_obstacles:
        # «Nessun ostacolo» vale anche per il livello AUTOMATICO, non solo
        # per i marker: prima arrivava solo a _place_on_markers, e gli
        # ostacoli automatici - che sono la maggior parte - restavano tutti.
        # Vedi togli_ostacoli per cosa resta e cosa se ne va.
        auto_layer = togli_ostacoli(auto_layer)

    combined = auto_layer + sidecar_actions
    result = choreo.enforce_playability(combined, beats, snap_to_grid=False, sidecar_min_gap_s=min_gap_s)
    result.sort(key=lambda a: a['startTime'])
    return result
