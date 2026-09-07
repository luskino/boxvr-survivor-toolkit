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
    'quota_scudi_bassi': (
        0.21, 0.0, 0.5, 'misurato',
        'Quante parate sono basse. Nel repertorio sono 12 su 56.'),
    'squat_che_diventano_schivate': (
        0.40, 0.0, 1.0, 'scelto',
        'La quota di squat generati dai marker che diventano una schivata. '
        'Serve perche\' altrimenti la modalita\' marker non ne produce quasi '
        'mai.'),
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
    'soglia_fra_i_tuoi_colpi_ms': (
        170, 80, 400, 'misurato',
        'Due tuoi marker piu\' vicini di cosi\' contano come uno solo. E\' il '
        'minimo misurato sui 465 workout ufficiali.'),
    'aggancio_alla_griglia_ms': (
        60, 0, 150, 'scelto',
        'Di quanto un tuo colpo viene spostato sulla suddivisione piu\' '
        'vicina. Serve a non far sentire i tuoi colpi diversi da quelli del '
        'tool; troppo alto li sposta dove non li hai messi.'),
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
    """Il valore regolato, o quello di fabbrica."""
    if chiave not in VALORI:
        raise KeyError('valore di tuning sconosciuto: %s' % chiave)
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
