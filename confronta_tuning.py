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

"""Che effetto ha avuto il mio tuning?

    python confronta_tuning.py "un brano.mp3"

Genera lo stesso brano DUE volte - una coi valori di fabbrica, una con il
tuo `tuning.json` - e mette le misure a confronto.

PERCHE' ESISTE, che e' il punto
-------------------------------
Una tabella di valori regolabili, da sola, non toglie il "andare a tentoni":
lo sposta da chi scrive il codice a chi lo usa. Cambi un numero, e per
sapere se hai fatto quello che volevi devi rigenerare, installare e metterti
il visore.

Il 07/09 e' successo esattamente questo, a me: per il difetto dei colpi
bassi ho fatto tre giri di modifiche, misurando ogni volta su un brano solo.
Al terzo ho misurato su dodici brani e ho scoperto che il fix funzionava dal
primo giro: stavo inseguendo il rumore di un campione singolo. Ecco perche'
qui si generano piu' semi, e non uno.

Il visore resta necessario per il giudizio - se la coreografia e' bella,
se e' faticosa al punto giusto. Ma non per sapere se hai spostato il numero
nella direzione che volevi.
"""
import argparse
import collections
import os
import statistics
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
for _p in (QUI, os.path.join(QUI, 'sidecar sandbox'),
           os.path.join(QUI, 'web_migration_spike')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

NOMI = {100: 'Block', 101: 'Jab', 102: 'Hook', 103: 'Uppercut',
        104: 'Dodge', 105: 'Squat'}
CORSIE_BASSE = (1, 3, 5)


def misura(azioni, durata_s):
    """Le stesse misure che si usano per giudicare un difetto segnalato."""
    import boxvr_choreo as choreo
    if not azioni:
        return {}
    az = sorted(azioni, key=lambda a: a['startTime'])
    pugni = [a for a in az if a['moveType'] in
             (choreo.MOVE_JAB, choreo.MOVE_HOOK, choreo.MOVE_UPPERCUT)]
    swing = (choreo.MOVE_HOOK, choreo.MOVE_UPPERCUT)
    dopo_swing = [d['beatNumber'] - p['beatNumber']
                  for p, d in zip(az, az[1:]) if p['moveType'] in swing]
    catene, cur = [], 0
    for a in az:
        if a['moveType'] == choreo.MOVE_SQUAT:
            cur += 1
        else:
            if cur:
                catene.append(cur)
            cur = 0
    if cur:
        catene.append(cur)
    blocchi = [a for a in az if a['moveType'] == choreo.MOVE_BLOCK]
    distanze = [d['beatNumber'] - p['beatNumber'] for p, d in zip(az, az[1:])
                if d['beatNumber'] > p['beatNumber']]
    c = collections.Counter(a['moveType'] for a in az)
    return {
        'mosse totali': len(az),
        'colpi al minuto': (len(pugni) / (durata_s / 60.0)) if durata_s else 0,
        'ganci e montanti': sum(c[m] for m in swing) / len(az) * 100,
        'corsie basse %': sum(1 for a in az if a.get('moveChannel') in CORSIE_BASSE)
                          / len(az) * 100,
        'scudi': len(blocchi),
        'scudi bassi %': (sum(1 for a in blocchi if a['moveChannel'] in CORSIE_BASSE)
                          / len(blocchi) * 100) if blocchi else 0,
        'squat %': c[choreo.MOVE_SQUAT] / len(az) * 100,
        'squat, catena piu lunga': max(catene) if catene else 0,
        'schivate': c[choreo.MOVE_DODGE],
        'dopo swing sotto il beat %': (sum(1 for x in dopo_swing if x < 0.99)
                                       / len(dopo_swing) * 100) if dopo_swing else 0,
        'distanza minima (beat)': min(distanze) if distanze else 0,
        'distanza mediana (beat)': statistics.median(distanze) if distanze else 0,
    }


def media(elenco):
    """La media di piu' generazioni: una sola misura e' rumore.

    Il 07/09 un solo brano dava 1 gancio basso su 44 e sembrava un difetto;
    su dodici generazioni erano l'8,8%, cioe' il valore atteso.
    """
    if not elenco:
        return {}
    chiavi = elenco[0].keys()
    return {k: sum(d.get(k, 0) for d in elenco) / len(elenco) for k in chiavi}


def genera(mp3, preset, semi, con_tuning):
    """Genera `semi` volte, con o senza il tuning dell'utente."""
    import tuning
    # Si ricaricano i moduli perche' le costanti leggono la tabella
    # all'IMPORT: e' il contratto dichiarato ("si applica al riavvio"), e
    # qui si simula il riavvio invece di chiedere all'utente di farlo due
    # volte a mano.
    for nome in ('boxvr_choreo', 'engine', 'boxvr_generator'):
        sys.modules.pop(nome, None)
    tuning._caricato = None if con_tuning else {}
    if not con_tuning:
        tuning._problemi = []
    import boxvr_choreo as choreo                              # noqa: F401
    import boxvr_generator as gen
    analisi = gen.generate_song_analysis(mp3)
    misure = [misura(choreo.build_move_actions(analisi, preset=preset, seed=s),
                     analisi['duration'])
              for s in range(semi)]
    return media(misure), analisi


def main():
    ap = argparse.ArgumentParser(
        description="Che effetto ha il tuo tuning.json, senza mettersi il visore.")
    ap.add_argument('brano', help='un mp3 o wav su cui provare')
    ap.add_argument('--preset', default='medium',
                    choices=('light', 'medium', 'high'))
    ap.add_argument('--semi', type=int, default=6,
                    help='quante generazioni mediare (default 6: una sola e rumore)')
    args = ap.parse_args()

    if not os.path.isfile(args.brano):
        print('brano non trovato:', args.brano)
        return 2

    import tuning
    modificati = tuning.modificati()
    for p in tuning.problemi():
        print('  ATTENZIONE:', p)
    if not modificati:
        print('Nessun tuning.json (o nessun valore cambiato): non c\'e\' niente '
              'da confrontare.')
        print('Copia %s come %s e cambia qualche riga.'
              % (tuning.NOME_ESEMPIO, tuning.NOME_FILE))
        return 1

    print('brano  : %s' % os.path.basename(args.brano))
    print('preset : %s, media su %d generazioni' % (args.preset, args.semi))
    print('cambiati:')
    for k, (fabbrica, tuo) in sorted(modificati.items()):
        prov = tuning.VALORI[k][3]
        print('  %-34s %s -> %s   [%s]' % (k, fabbrica, tuo, prov))
    print()

    base, _ = genera(args.brano, args.preset, args.semi, con_tuning=False)
    tuo, _ = genera(args.brano, args.preset, args.semi, con_tuning=True)

    print('%-30s %14s %14s' % ('', 'di fabbrica', 'il tuo tuning'))
    print('-' * 62)
    for k in base:
        a, b = base[k], tuo[k]
        segno = ''
        if abs(a - b) > max(0.05, abs(a) * 0.02):
            segno = '  <- cambiato'
        fmt = '%14.0f' if abs(a) >= 100 or k == 'mosse totali' else '%14.2f'
        print(('%-30s' + fmt + fmt + '%s') % (k, a, b, segno))
    print()
    print('Il visore resta necessario per dire se la coreografia e\' BELLA.')
    print('Questo dice solo se il numero si e\' mosso come volevi.')
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.exit(main())
