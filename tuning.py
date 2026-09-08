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

"""I valori che regolano come si sente la coreografia.

PERCHE' ESISTE
--------------
Chi prova il tool in VR vede subito cosa non va - "i colpi dopo un gancio
sono troppo vicini", "gli squat sono troppi" - ma per correggerlo doveva
passare da me, e io andavo a tentoni: una modifica, una ricostruzione, una
sessione in visore, e da capo. Il 07/09 ho fatto tre giri di modifiche per
un difetto che era gia' corretto al primo, perche' avevo misurato su un
brano solo e stavo inseguendo il rumore.

Qui i valori stanno in un posto solo, si cambiano senza toccare il codice, e
`--confronta` (vedi confronta_tuning.py) fa vedere l'effetto PRIMA di
rimettersi il visore. Le due cose vanno insieme: una tabella senza un modo
di misurare l'effetto non toglie il tentoni, lo sposta.

COME SI USA
-----------
Un file `tuning.json` accanto all'eseguibile. Si scrive SOLO cio' che si
cambia; tutto il resto resta di fabbrica, quindi il file non invecchia
quando qui dentro se ne aggiungono di nuovi.

    {"respiro_dopo_swing_altro_lato": 0.9}

Si applica al riavvio. Per tornare com'era, si cancella il file.

COSA C'E' E COSA NO
-------------------
Ci sono i valori che cambiano come si SENTE la coreografia. Non ci sono, di
proposito, quelli che sono il formato del gioco (la lunghezza dei pattern, i
codici delle mosse, i canali): sbagliarli non produce una coreografia
brutta, produce file che il gioco non legge.

Ogni valore porta con se' da DOVE VIENE, ed e' la cosa piu' importante di
questa tabella:

    misurato   preso dai file del gioco o dai 465 workout ufficiali. Se lo
               cambi, ti stai allontanando da come si comporta BoxVR - a
               volte e' esattamente cio' che vuoi, ma sappilo.
    provato    scelto da noi e poi confermato da una sessione in VR.
    scelto     scelto da noi e mai verificato in visore. Questi sono quelli
               su cui vale piu' la pena giocare.
"""
import json
import os
import sys

# (predefinito, minimo, massimo, provenienza, a cosa serve)
VALORI = {
    # ---------------------------------------------------- il respiro
    'respiro_minimo': (
        0.5, 0.25, 1.0, 'misurato',
        'Il pavimento assoluto fra due mosse qualsiasi, in beat. Sotto '
        'questo non si scende mai.'),
    'respiro_fra_colpi_stesso_lato': (
        1.0, 0.75, 2.0, 'misurato',
        'Due colpi consecutivi con lo STESSO braccio: deve tornare in '
        'posizione. Nel repertorio ufficiale il minimo e\' 1 beat.'),
    'respiro_dopo_swing_stesso_lato': (
        1.5, 1.0, 2.5, 'provato',
        'Dopo un gancio o un montante, sullo stesso braccio. Segnalato in '
        'VR il 24/08: "un gancio non puo\' avere un diretto nello stesso '
        'braccio vicino della stessa quantita\'".'),
    'respiro_dopo_swing_altro_lato': (
        0.75, 0.5, 1.5, 'provato',
        'Dopo un gancio o un montante, quando il colpo dopo e\' sull\'altro '
        'braccio. Segnalato in VR il 07/09 ("un pochino di ms in piu\'"). '
        'Il gioco usa 1.0, ma copiarlo renderebbe le coreografie rade come '
        'le sue: 0.75 e\' a meta\' strada.'),
    'respiro_prima_di_uno_swing': (
        1.0, 0.0, 2.5, 'misurato',
        'Lo spazio che deve esserci PRIMA di un gancio o di un montante, '
        'qualunque sia il colpo che lo precede. Caricare uno swing vuole '
        'spazio quanto recuperarci: guardando solo il colpo di prima, un '
        'gancio subito dopo un diretto passava e nessuno slider lo '
        'allontanava (segnalato l\'08/09). Nel repertorio ufficiale il '
        'minimo e\' 1 beat pieno, uguale sullo stesso braccio (8 casi) e '
        'sull\'altro (141).'),
    'respiro_attorno_schivata': (
        1.0, 0.5, 2.0, 'misurato',
        'Lo spazio libero prima e dopo una schivata. Tutte e dieci le '
        'schivate del repertorio ne hanno almeno un beat.'),
    'spostamento_massimo': (
        1.0, 0.25, 2.0, 'scelto',
        'Di quanto una mossa puo\' essere spostata in avanti per rispettare '
        'le distanze prima di essere scartata. Spostare conserva il colpo, '
        'scartare lo perde.'),

    # ------------------------------------------------- il vocabolario
    'quota_ganci_bassi': (
        0.09, 0.0, 0.35, 'misurato',
        'Quanti ganci vanno al corpo invece che alla testa. Nel repertorio '
        'sono 12 su 132.'),
    # `quota_scudi_bassi` c'era ed e' stata TOLTA il 07/09 sera: non e' una
    # quota, e' una regola. Nel repertorio lo scudo e' basso esattamente
    # quando c'e' uno squat sotto (12 su 12) e alto quando e' da solo (44 su
    # 44), senza eccezioni. Estrarlo a caso produceva scudi bassi senza squat
    # e scudi alti col squat, cioe' le due posizioni che nel gioco non
    # esistono. Vedi allinea_scudi_agli_squat in boxvr_choreo.py.
    'squat_che_diventano_schivate': (
        0.40, 0.0, 1.0, 'scelto',
        'La quota di squat generati dai marker che diventano una schivata. '
        'Serve perche\' altrimenti la modalita\' marker non ne produce quasi '
        'mai. NON tocca gli squat del livello automatico, che ci sono anche '
        'in «Solo marker»: anche a 1 quelli restano squat, ed e\' voluto - '
        'gli ostacoli il motore li mette per conto suo, a prescindere dai '
        'marker.'),
    'catena_massima_di_squat': (
        3, 1, 16, 'scelto',
        'Quanti squat di fila al massimo. Segnalato in VR il 07/09: "quando '
        'ci sono, sono troppo presenti e lunghi" - misurate catene da otto. '
        'Il repertorio arriva a 16, ma con una mediana di 1.'),
    'preferenza_squat_contro_scudo': (
        0.0, -1.0, 1.0, 'scelto',
        'Sposta peso fra squat e scudo quando un tuo marker diventa una '
        'mossa centrale. A 0 restano le proporzioni misurate sui 465 '
        'workout; verso -1 piu\' scudi, verso +1 piu\' squat.'),

    # ------------------------------------------------- il ritmo e i marker
    'deroga_sui_tuoi_marker': (
        1, 0, 2, 'scelto',
        'Quanto i colpi che marchi TU possono infischiarsene delle regole di '
        'respiro. 1 (predefinito) = vale per i pugni dritti, dove metterli '
        'vicini e\' una tua scelta ed e\' eseguibile, ma NON per ganci e '
        'montanti, che sono movimenti ampi e vicini non si fanno. '
        '2 = deroga piena, i tuoi colpi restano dove li hai messi comunque. '
        '0 = nessuna deroga, i tuoi marker seguono le stesse regole di tutto '
        'il resto. '
        'Il predefinito e\' passato da 2 a 1 l\'08/09: con la deroga piena le '
        'regole di respiro non toccavano i tuoi colpi, quindi alzando il '
        'respiro sparivano i colpi automatici - che non danno fastidio - e '
        'restavano i due swing attaccati, che sono quelli difficili da '
        'colpire. Misurato: 12 colpi automatici in meno e 13 coppie '
        'ravvicinate ancora li\', tutte tue.'),
    'respiro_fra_i_tuoi_colpi_stesso_lato': (
        1.225, 0.5, 2.5, 'provato',
        'Come «respiro fra colpi stesso lato», ma SOLO fra due colpi che hai '
        'marcato tu. Provato in anteprima l\'08/09 e tenuto: 1.225 va bene sui '
        'tuoi, mentre imporlo a tutto renderebbe non piu\' eseguibili due '
        'figure ritmiche del catalogo (tresillo e cinquillo largo, che stanno '
        'a 1 beat esatto come nel repertorio ufficiale). Il livello '
        'automatico usa figure costruite sul gioco, dove 1 beat esiste e '
        'funziona; i tuoi marker no, e li\' un po\' di respiro in piu\' si '
        'sente.'),
    'soglia_fra_i_tuoi_colpi_ms': (
        170, 80, 400, 'misurato',
        'Due tuoi marker piu\' vicini di cosi\' contano come uno solo. E\' il '
        'minimo misurato sui 465 workout ufficiali.'),
    'aggancio_alla_griglia_frazione': (
        0.34, 0.0, 0.5, 'scelto',
        'Di quanto un tuo colpo viene spostato sulla suddivisione piu\' '
        'vicina, come FRAZIONE del passo della griglia. E\' questo il numero '
        'che decide quasi sempre: a 123 bpm il passo e\' 116 ms, e 0.34 fa '
        '39 ms. A 0 l\'aggancio e\' spento e i colpi restano esattamente dove '
        'li hai battuti; a 0.5 viene agganciato tutto e un colpo messo fuori '
        'tempo apposta non e\' piu\' possibile.'),
    'aggancio_alla_griglia_ms': (
        60, 0, 150, 'scelto',
        'TETTO in millisecondi allo spostamento qui sopra, per i brani '
        'lenti. Vince il piu\' piccolo dei due, e sopra gli 85 bpm circa '
        'vince sempre la frazione: se muovi questo e non cambia niente, e\' '
        'perche\' e\' la frazione che sta decidendo.'),
    'aggancio_agli_accenti_ms': (
        80, 0, 200, 'scelto',
        'Di quanto un tuo colpo viene spostato su un accento VERO del brano. '
        'Un accento e\' un fatto della musica, la griglia e\' la nostra '
        'approssimazione della musica.'),
    'suddivisioni_della_griglia': (
        4, 2, 8, 'scelto',
        'In quante parti si divide un beat. Sopra 4 il ritmo diventa '
        'difficile da leggere in VR.'),

    # ------------------------------------------------------- Estendi
    'estendi_secondi_minimi': (
        45.0, 15.0, 120.0, 'scelto',
        'Quanti secondi di ritmo continuo devi marcare perche\' «Estendi» '
        'abbia qualcosa da imparare.'),
    'estendi_colpi_minimi': (
        8, 4, 40, 'scelto',
        'Idem, contati in colpi dentro i blocchi ritmici.'),
    'estendi_segue_la_tua_cadenza': (
        1, 0, 1, 'scelto',
        'Se 1, quando marchi piu\' fitto del preset piu\' intenso «Estendi» '
        'segue la TUA cadenza invece di fermarsi al tetto. Misurato il '
        '07/09: due colpi per beat sono 241 colpi/min contro gli 88 del '
        'preset piu\' intenso, un divario di 2,7 volte - ed e\' il motivo per '
        'cui "non riesce a imparare i colpi in rapida successione".'),

    # ---------------------------------------------------- la generazione
    'variazione_dei_pattern_leggero': (
        0.10, 0.0, 0.6, 'scelto',
        'Quanto ci si discosta dal repertorio ufficiale, col preset '
        'Leggero. A 0 si usano i pattern del gioco tali e quali.'),
    'variazione_dei_pattern_medio': (0.20, 0.0, 0.6, 'scelto', 'Come sopra, preset Medio.'),
    'variazione_dei_pattern_intenso': (0.30, 0.0, 0.6, 'scelto', 'Come sopra, preset Intenso.'),
    'colpi_al_minuto_leggero': (
        42, 20, 200, 'misurato',
        'La densita\' a cui punta il preset Leggero. Un workout ufficiale '
        'BoxVR sta a 82.'),
    'colpi_al_minuto_medio': (74, 20, 200, 'misurato', 'Come sopra, preset Medio.'),
    'colpi_al_minuto_intenso': (88, 20, 200, 'misurato', 'Come sopra, preset Intenso.'),
}

NOME_FILE = 'tuning.json'
NOME_ESEMPIO = 'tuning.esempio.json'

_caricato = None
_problemi = []
# cio' che si sta provando adesso dal pannello: vince su tutto e non
# tocca mai il file. Vedi la sezione "Regolazione DAL VIVO" in fondo.
_vivo = {}


def _cartella():
    """Dove cercare il file: accanto all'eseguibile, o alla radice in sviluppo."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _carica():
    global _caricato, _problemi
    if _caricato is not None:
        return _caricato
    _caricato, _problemi = {}, []
    percorso = os.path.join(_cartella(), NOME_FILE)
    if not os.path.isfile(percorso):
        return _caricato
    try:
        with open(percorso, encoding='utf-8') as f:
            grezzo = json.load(f)
    except Exception as e:                     # noqa: BLE001
        _problemi.append('%s non si legge (%s): si usano i valori di fabbrica'
                         % (NOME_FILE, e))
        return _caricato
    if not isinstance(grezzo, dict):
        _problemi.append('%s deve contenere un oggetto JSON' % NOME_FILE)
        return _caricato

    for chiave, valore in grezzo.items():
        if chiave.startswith('_'):             # commenti dell'utente
            continue
        if chiave not in VALORI:
            _problemi.append('"%s" non e\' un valore regolabile: ignorato' % chiave)
            continue
        pred, minimo, massimo, _prov, _desc = VALORI[chiave]
        if not isinstance(valore, (int, float)) or isinstance(valore, bool):
            _problemi.append('"%s" deve essere un numero: resta %s' % (chiave, pred))
            continue
        if not (minimo <= valore <= massimo):
            _problemi.append('"%s" = %s e\' fuori dall\'intervallo ammesso '
                             '(%s - %s): resta %s' % (chiave, valore, minimo,
                                                      massimo, pred))
            continue
        # un predefinito intero resta intero: mezzo squat non esiste
        _caricato[chiave] = type(pred)(valore) if isinstance(pred, int) else float(valore)
    return _caricato


def valore(chiave):
    """Il valore in vigore adesso.

    In ordine di precedenza: quello che si sta provando dal vivo nel
    pannello, poi quello scritto in `tuning.json`, poi la fabbrica. Il
    "dal vivo" vince perche' e' l'ultima cosa che una persona ha chiesto,
    e non tocca il file: si prova, e si salva solo se convince.
    """
    if chiave not in VALORI:
        raise KeyError('valore di tuning sconosciuto: %s' % chiave)
    if chiave in _vivo:
        return _vivo[chiave]
    return _carica().get(chiave, VALORI[chiave][0])


def modificati():
    """Solo cio' che l'utente ha davvero cambiato: {nome: (di fabbrica, suo)}."""
    return {k: (VALORI[k][0], v) for k, v in _carica().items()}


def problemi():
    """I messaggi sui valori rifiutati. Vuoto se e' andato tutto bene."""
    _carica()
    return list(_problemi)


def scrivi_esempio(cartella=None):
    """Scrive il file di esempio COMPLETO, con limiti e provenienza.

    Serve a sapere cosa si puo' toccare senza doverlo chiedere: e' l'unico
    posto in cui i valori stanno tutti insieme, con scritto da dove vengono.
    """
    cartella = cartella or _cartella()
    percorso = os.path.join(cartella, NOME_ESEMPIO)
    righe = [
        '{',
        '  "_come_si_usa": [',
        '    "Copia questo file come tuning.json, tieni SOLO le righe che vuoi",',
        '    "cambiare, e riavvia il tool. Per tornare com\'era, cancella",',
        '    "tuning.json. Le righe che cominciano con _ sono commenti.",',
        '    "",',
        '    "Per vedere l\'effetto senza mettersi il visore:",',
        '    "  python confronta_tuning.py <un brano.mp3>"',
        '  ],',
        '  "_provenienza": [',
        '    "misurato = preso dai file del gioco o dai 465 workout ufficiali.",',
        '    "           Cambiandolo ti allontani da come si comporta BoxVR.",',
        '    "provato  = scelto da noi e confermato in VR.",',
        '    "scelto   = scelto da noi e mai verificato in visore: qui c\'e\'",',
        '    "           piu\' margine per giocare."',
        '  ],',
    ]
    for chiave in VALORI:
        pred, minimo, massimo, prov, desc = VALORI[chiave]
        righe.append('')
        righe.append('  "_%s": "[%s] %s (fra %s e %s)",'
                     % (chiave, prov, desc.replace('"', "'"), minimo, massimo))
        righe.append('  "%s": %s,' % (chiave, json.dumps(pred)))
    if righe[-1].endswith(','):
        righe[-1] = righe[-1][:-1]
    righe.append('}')
    with open(percorso, 'w', encoding='utf-8') as f:
        f.write('\n'.join(righe) + '\n')
    return percorso


def riepilogo():
    """Una riga per il log all'avvio. Vuota se non c'e' niente da dire."""
    m = modificati()
    p = problemi()
    parti = []
    if m:
        parti.append('tuning: %d valori modificati (%s)'
                     % (len(m), ', '.join('%s=%s' % (k, v[1]) for k, v in
                                          sorted(m.items()))))
    for x in p:
        parti.append('tuning: ' + x)
    return '\n'.join(parti)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print('valori regolabili: %d' % len(VALORI))
    print('file di esempio scritto in:', scrivi_esempio())
    r = riepilogo()
    print(r if r else 'nessun tuning.json: tutti i valori di fabbrica')


# ---------------------------------------------------------------------------
# Regolazione DAL VIVO (pannello di tuning nel visualizzatore)
#
# Il contratto normale e' "cambia il file, riavvia": semplice e adatto a chi
# regola una cosa ogni tanto. Non basta per cercare un valore a occhio,
# perche' li' servono venti tentativi di fila e venti riavvii non li fa
# nessuno. Da qui i valori si cambiano IN MEMORIA e la coreografia si
# rigenera subito - misurato: 33 ms, cioe' meno di due frame.
#
# Cio' che si prova dal vivo NON tocca il file: si salva solo quando lo si
# chiede. Cosi' si puo' girare la manopola avanti e indietro senza lasciare
# tracce, che e' esattamente cio' che serve mentre si cerca.
# ---------------------------------------------------------------------------

# I gruppi sono per AMBITO: su quale parte della coreografia agisce ciascun
# valore. Non e' una classificazione a occhio - si ricava da dove il valore
# viene letto:
#
#   ovunque      in `enforce_playability` e nelle passate finali di
#                boxvr_choreo, per cui passa qualunque coreografia
#   generata     in `build_move_actions`, cioe' il livello che costruisce il
#                tool: c'e' in Automatica, Armonizza ed Estendi, e NON in
#                «Solo marker»
#   tuoi colpi   in sidecar sandbox/engine.py, cioe' cio' che riguarda i
#                marker che batti tu
#
# Il secondo non si chiama "solo automatico" perche' sarebbe falso: quel
# livello c'e' anche in Armonizza e in Estendi.
GRUPPI = [
    ('Su tutti i tipi di workout',
     'Valgono sempre: automatico, misto e solo marker.', (
         'respiro_minimo', 'respiro_fra_colpi_stesso_lato',
         'respiro_dopo_swing_stesso_lato', 'respiro_dopo_swing_altro_lato',
         'respiro_prima_di_uno_swing', 'respiro_attorno_schivata',
         'respiro_fra_scudo_e_squat',
         'spostamento_massimo', 'catena_massima_di_squat',
         'preferenza_squat_contro_scudo')),
    ('Solo sulla parte generata dal tool',
     "Il livello automatico: c'e' in Automatica, Armonizza ed Estendi, "
     'non in «Solo marker».', (
         'quota_ganci_bassi',
         'colpi_al_minuto_leggero', 'colpi_al_minuto_medio',
         'colpi_al_minuto_intenso', 'variazione_dei_pattern_leggero',
         'variazione_dei_pattern_medio', 'variazione_dei_pattern_intenso')),
    ('Solo sui colpi che batti tu',
     'Riguardano i marker: come vengono filtrati, agganciati e quanto '
     'possono infischiarsene delle regole.', (
         'deroga_sui_tuoi_marker', 'respiro_fra_i_tuoi_colpi_stesso_lato',
         'soglia_fra_i_tuoi_colpi_ms',
         'aggancio_alla_griglia_frazione',
         'aggancio_alla_griglia_ms', 'aggancio_agli_accenti_ms',
         'suddivisioni_della_griglia', 'squat_che_diventano_schivate',
         'estendi_secondi_minimi', 'estendi_colpi_minimi',
         'estendi_segue_la_tua_cadenza')),
]

def imposta_dal_vivo(valori):
    """Applica dei valori solo in memoria. Ritorna i messaggi sui rifiutati."""
    global _vivo
    messaggi = []
    nuovo = dict(_vivo)
    for chiave, v in (valori or {}).items():
        if chiave not in VALORI:
            messaggi.append('"%s" non e\' un valore regolabile' % chiave)
            continue
        pred, minimo, massimo, _p, _d = VALORI[chiave]
        try:
            v = float(v)
        except (TypeError, ValueError):
            messaggi.append('"%s" deve essere un numero' % chiave)
            continue
        if not (minimo <= v <= massimo):
            messaggi.append('"%s" fuori dall\'intervallo %s - %s'
                            % (chiave, minimo, massimo))
            continue
        nuovo[chiave] = type(pred)(v) if isinstance(pred, int) else v
    _vivo = nuovo
    return messaggi


def azzera_dal_vivo():
    """Torna a cio' che dice il file (o alla fabbrica, se non c'e')."""
    # anche il metodo torna a «Predefinito»: i valori che si stanno
    # buttando via erano i suoi, e lasciare il suo nome scritto nella
    # tendina direbbe una cosa falsa
    global _vivo, _metodo_corrente
    _vivo = {}
    _metodo_corrente = PREDEFINITO


def dal_vivo():
    return dict(_vivo)


def salva_su_file(valori=None):
    """Scrive `tuning.json` con cio' che si sta provando (o con `valori`).

    Si scrivono SOLO i valori diversi da quelli di fabbrica: un file che
    ripete i predefiniti invecchia male, perche' congela dei numeri che
    altrove potrebbero cambiare.
    """
    global _caricato
    da_scrivere = dict(valori) if valori is not None else dict(_vivo)
    magri = {k: v for k, v in da_scrivere.items()
             if k in VALORI and v != VALORI[k][0]}
    percorso = os.path.join(_cartella(), NOME_FILE)
    if not magri:
        if os.path.isfile(percorso):
            os.remove(percorso)
        _caricato = {}
        return None
    testo = {'_scritto_dal_pannello': 'valori diversi da quelli di fabbrica'}
    testo.update(magri)
    with open(percorso, 'w', encoding='utf-8') as f:
        json.dump(testo, f, indent=2, ensure_ascii=False)
    _caricato = dict(magri)
    return percorso


def firma():
    """Uno stato compatto di TUTTI i valori effettivi.

    Serve a chi tiene in cache qualcosa che dipende dal tuning: se questa
    cambia, quel qualcosa va rifatto. Si costruisce dai valori veri e non
    da un elenco scritto a mano, altrimenti il prossimo valore aggiunto
    resterebbe fuori e la cache tornerebbe a mentire - che e' esattamente
    il difetto per cui questa funzione esiste (07/09: l'anteprima del
    workout non si rigenerava, perche' la sua firma guardava solo le
    impostazioni del brano).
    """
    return tuple(sorted((k, valore(k)) for k in VALORI))


def per_il_pannello():
    """Tutto cio' che serve alla GUI: valori, limiti, provenienza, gruppi."""
    _carica()
    voci = []
    for titolo, spiega, chiavi in GRUPPI:
        for chiave in chiavi:
            if chiave not in VALORI:
                continue
            pred, minimo, massimo, prov, desc = VALORI[chiave]
            corrente = _vivo.get(chiave, _caricato.get(chiave, pred))
            voci.append({
                'chiave': chiave, 'gruppo': titolo, 'valore': corrente,
                'fabbrica': pred, 'min': minimo, 'max': massimo,
                'intero': isinstance(pred, int), 'provenienza': prov,
                'descrizione': desc,
                'modificato': corrente != pred,
            })
    return {'voci': voci,
            'gruppi': [{'titolo': t, 'spiega': d, 'quanti': len(k)}
                       for t, d, k in GRUPPI],
            'metodi': elenco_metodi(),
            'metodo': _metodo_corrente,
            'da_file': dict(_caricato),
            'dal_vivo': dict(_vivo),
            'problemi': list(_problemi)}


# ---------------------------------------------------------------------------
# METODI SALVATI
#
# Un `tuning.json` solo va bene finche' si cerca UN assetto. Ma cercando si
# trovano assetti diversi buoni per cose diverse - uno piu' rado per i brani
# lenti, uno fitto per i pezzi tirati - e con un file solo il secondo
# cancella il primo.
#
# Un metodo e' lo stesso formato, con un nome, in una cartella accanto
# all'eseguibile. Si sceglie da un elenco, e "Predefinito" e' semplicemente
# l'assenza di scelta: i valori di fabbrica.
# ---------------------------------------------------------------------------

CARTELLA_METODI = 'tuning'
PREDEFINITO = 'Predefinito'

# Quale metodo si sta usando adesso. Serve solo al pannello, per dire
# a chi guarda da dove vengono i numeri che ha davanti: senza, dopo
# aver caricato un metodo e mosso uno slider non si sa piu' su cosa si
# sta lavorando.
_metodo_corrente = PREDEFINITO


def _cartella_metodi():
    d = os.path.join(_cartella(), CARTELLA_METODI)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def elenco_metodi():
    """I metodi salvati, in ordine. Il primo e' sempre «Predefinito»."""
    fuori = [PREDEFINITO]
    d = _cartella_metodi()
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.lower().endswith('.json'):
                fuori.append(f[:-5])
    return fuori


def _percorso_metodo(nome):
    # Solo il nome del file: un nome con dentro dei separatori scriverebbe
    # fuori dalla cartella dei metodi, e non e' cio' che chi lo digita
    # intende.
    sicuro = os.path.basename(str(nome or '').strip())
    if not sicuro or sicuro == PREDEFINITO:
        return None
    if not sicuro.lower().endswith('.json'):
        sicuro += '.json'
    return os.path.join(_cartella_metodi(), sicuro)


def _versione_del_tool():
    try:
        import version
        return getattr(version, "VERSION_WEB", "")
    except Exception:                          # noqa: BLE001
        return ""


def leggi_intestazione(percorso):
    """Chi l'ha fatto, per cosa, con che versione - senza applicarlo."""
    try:
        with open(percorso, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:                          # noqa: BLE001
        return None
    if not isinstance(d, dict):
        return None
    valori = {k: v for k, v in d.items() if not k.startswith("_")}
    return {
        "nome": d.get("_metodo") or os.path.splitext(os.path.basename(percorso))[0],
        "autore": d.get("_autore", ""),
        "descrizione": d.get("_descrizione", ""),
        "creato": d.get("_creato", ""),
        "versione": d.get("_versione_del_tool", ""),
        "quanti": len(valori),
        "sconosciuti": [k for k in valori if k not in VALORI],
    }


def importa_metodo(percorso):
    """Copia un metodo ricevuto da fuori dentro la cartella dei metodi.

    Ritorna (nome, avvisi). Gli avvisi dicono cosa NON sara' applicato -
    tipicamente valori spariti o rinominati fra una versione e l'altra. Chi
    riceve un metodo deve saperlo: altrimenti si ritrova un assetto diverso
    da quello che l'autore aveva provato, e nessuno glielo dice.
    """
    import shutil
    testa = leggi_intestazione(percorso)
    if testa is None:
        return None, ["«%s» non e' un metodo leggibile" % os.path.basename(percorso)]
    avvisi = []
    if testa["sconosciuti"]:
        avvisi.append("non riconosciuti in questa versione, saranno ignorati: "
                      + ", ".join(testa["sconosciuti"]))
    if testa["versione"] and testa["versione"] != _versione_del_tool():
        avvisi.append("fatto con la versione %s, tu hai la %s"
                      % (testa["versione"], _versione_del_tool()))
    dest = _percorso_metodo(testa["nome"])
    if dest is None:
        return None, ["nome del metodo non valido"]
    # gia' dentro la cartella: e' un reimporto, non c'e' niente da copiare
    if os.path.abspath(percorso) != os.path.abspath(dest):
        shutil.copy2(percorso, dest)
    return testa["nome"], avvisi


def esporta_metodo(nome, percorso):
    """Copia un metodo fuori dalla cartella, per mandarlo a qualcuno."""
    import shutil
    src = _percorso_metodo(nome)
    if not src or not os.path.isfile(src):
        raise ValueError("il metodo «%s» non si trova" % nome)
    shutil.copy2(src, percorso)
    return percorso


def salva_metodo(nome, valori=None, autore="", descrizione=""):
    """Scrive i valori che si stanno provando come metodo `nome`.

    Il file porta con se' chi l'ha fatto, quando, per cosa e con quale
    versione. Serve perche' i metodi sono pensati per GIRARE: uno buono lo
    si manda a qualcun altro, e se regge finisce in una release. Un file di
    soli numeri, ricevuto da uno sconosciuto, non dice nemmeno se e' ancora
    valido per la versione che si ha in mano.
    """
    percorso = _percorso_metodo(nome)
    if percorso is None:
        raise ValueError('«%s» e\' l\'assetto di fabbrica: scegli un altro nome'
                         % PREDEFINITO)
    da = dict(valori) if valori is not None else dict(_vivo)
    magri = {k: v for k, v in da.items() if k in VALORI and v != VALORI[k][0]}
    import datetime
    testo = {
        "_metodo": nome,
        "_autore": autore,
        "_descrizione": descrizione,
        "_creato": datetime.date.today().isoformat(),
        "_versione_del_tool": _versione_del_tool(),
        "_nota": "Solo i valori diversi da quelli di fabbrica. Per usarlo: "
                 "mettilo nella cartella tuning/ accanto all'eseguibile, "
                 "oppure importalo dal pannello Avanzate.",
    }
    testo.update(magri)
    with open(percorso, 'w', encoding='utf-8') as f:
        json.dump(testo, f, indent=2, ensure_ascii=False)
    global _metodo_corrente
    _metodo_corrente = nome
    return percorso


def metodo_corrente():
    return _metodo_corrente


def carica_metodo(nome):
    """Applica un metodo salvato. «Predefinito» torna alla fabbrica."""
    global _vivo, _metodo_corrente
    if not nome or nome == PREDEFINITO:
        _vivo = {}
        _metodo_corrente = PREDEFINITO
        return []
    percorso = _percorso_metodo(nome)
    if not percorso or not os.path.isfile(percorso):
        return ['il metodo «%s» non si trova' % nome]
    try:
        with open(percorso, encoding='utf-8') as f:
            grezzo = json.load(f)
    except Exception as e:                     # noqa: BLE001
        return ['«%s» non si legge (%s)' % (nome, e)]
    _vivo = {}
    _metodo_corrente = nome
    return imposta_dal_vivo({k: v for k, v in grezzo.items()
                             if not k.startswith('_')})


def elimina_metodo(nome):
    global _metodo_corrente
    percorso = _percorso_metodo(nome)
    if percorso and os.path.isfile(percorso):
        os.remove(percorso)
        if _metodo_corrente == nome:
            _metodo_corrente = PREDEFINITO
        return True
    return False


def intestazione_metodo(nome):
    """L'intestazione di un metodo gia' in cartella, per il pannello."""
    percorso = _percorso_metodo(nome)
    if not percorso or not os.path.isfile(percorso):
        return None
    return leggi_intestazione(percorso)
