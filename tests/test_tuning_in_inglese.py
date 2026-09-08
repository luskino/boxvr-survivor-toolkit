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

"""Il pannello di tuning parla inglese quando l'app e' in inglese?

Da quando il tuning non e' piu' uno strumento interno ma una funzione che
l'utente puo' usare, deve seguire la lingua come tutto il resto. Con
l'interfaccia in inglese si apriva un pannello interamente in italiano.

IL PUNTO DEBOLE DI QUESTO IMPIANTO, ed e' il motivo per cui il test esiste:
il dizionario aggancia le stringhe per TESTO ESATTO, e i nomi e le
descrizioni dei valori vivono in `tuning.py`. Basta ritoccare una virgola in
una descrizione perche' la sua traduzione smetta di agganciare - senza un
errore, senza una riga rossa: quella voce torna in italiano e basta.

Qui si confronta il dizionario con cio' che `tuning.py` produce DAVVERO, e
si elenca cio' che resterebbe indietro.
"""
import io
import os
import re
import sys

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RADICE)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import tuning                                                   # noqa: E402

PAGINA = os.path.join(RADICE, 'web_migration_spike', 'genera_real', 'index.html')

esiti = []


def prova(ok, nome, dettaglio=''):
    esiti.append((bool(ok), nome, dettaglio))


def chiavi_del_dizionario():
    """Le stringhe italiane che il dizionario IT->EN sa tradurre.

    Si legge il blocco `const TRAD = { ... }` e se ne prendono le chiavi.
    Non si esegue il JS: serve solo sapere quali testi sono coperti.
    """
    s = io.open(PAGINA, encoding='utf-8').read()
    i = s.index('const TRAD = {')
    j = s.index('\n  };', i)
    blocco = s[i:j]
    # chiavi fra apici singoli a inizio riga, fino a ':' - gli apici
    # interni sono sfuggiti con \'
    return set(re.findall(r"^\s*'((?:[^'\\]|\\.)*)'\s*:", blocco, re.M))


def ripulisci(t):
    """Da come sta scritta nel sorgente JS a come sta in memoria."""
    return t.replace("\\'", "'").replace('\\\\', '\\')


def main():
    grezze = chiavi_del_dizionario()
    coperte = {ripulisci(k) for k in grezze}
    prova(len(coperte) > 200,
          'il dizionario di traduzione si legge',
          '%d stringhe coperte' % len(coperte))

    d = tuning.per_il_pannello()

    # ---- i nomi dei valori, come li scrive il pannello
    nomi = [v['chiave'].replace('_', ' ') for v in d['voci']]
    fuori = [n for n in nomi if n not in coperte]
    prova(not fuori,
          'ogni valore regolabile ha il NOME tradotto',
          ('senza traduzione: %s' % fuori) if fuori
          else '%d nomi' % len(nomi))

    # ---- e le descrizioni, che sono la parte che spiega cosa fa
    desc = [v['descrizione'] for v in d['voci']]
    fuori = [x[:48] + '...' for x in desc if x not in coperte]
    prova(not fuori,
          'e la DESCRIZIONE, che e\' la parte che spiega a cosa serve',
          ('senza traduzione: %s' % fuori[:3]) if fuori
          else '%d descrizioni' % len(desc))

    # ---- i tre gruppi
    fuori = []
    for g in d['gruppi']:
        if g['titolo'] not in coperte:
            fuori.append(g['titolo'])
        if g['spiega'] and g['spiega'] not in coperte:
            fuori.append(g['spiega'][:40] + '...')
    prova(not fuori,
          'i tre blocchi hanno titolo e spiegazione tradotti',
          ('senza: %s' % fuori) if fuori else '3 blocchi')

    # ---- le provenienze, che sono l'informazione piu' importante del
    #      pannello: dicono se stai scavalcando una misura o un nostro
    #      numero mai verificato
    prov = sorted({v['provenienza'] for v in d['voci']})
    fuori = [p for p in prov if p not in coperte]
    prova(not fuori,
          'e le tre provenienze (misurato / provato / scelto)',
          ('senza: %s' % fuori) if fuori else ', '.join(prov))

    # ---- i comandi del pannello, presi dal markup e non da un elenco a
    #      mano: se domani se ne aggiunge uno, questo lo vede
    s = io.open(PAGINA, encoding='utf-8').read()
    i = s.index('<div class="tuning-pan"')
    j = s.index('</div>', s.index('tp-msg', i))
    pannello = s[i:j]
    # Le entita' HTML vanno sciolte: nel markup c'e' `&hellip;`, nel DOM
    # arriva il carattere, ed e' il carattere che il dizionario aggancia.
    import html as _html
    testi = set()
    for m in re.finditer(r'>([^<>{}$]+)<', pannello):
        t = _html.unescape(m.group(1)).strip()
        if len(t) > 2 and re.search(r'[a-zA-Z]', t):
            testi.add(t)
    for m in re.finditer(r'(?:title|placeholder|aria-label)="([^"${]+)"', pannello):
        t = _html.unescape(m.group(1)).strip()
        if len(t) > 2:
            testi.add(t)
    fuori = sorted(t for t in testi if t not in coperte)
    prova(not fuori,
          'e i comandi del pannello (bottoni, segnaposto, suggerimenti)',
          ('senza traduzione: %s' % fuori) if fuori
          else '%d testi' % len(testi))


if __name__ == '__main__':
    main()
    print('===== IL PANNELLO DI TUNING IN INGLESE =====')
    if not esiti:
        print('  FALLITO  nessun controllo eseguito')
        sys.exit(1)
    rossi = 0
    for ok, nome, dett in esiti:
        print(('  ok       ' if ok else '  FALLITO  ') + nome)
        if dett:
            print('             %s' % dett)
        rossi += 0 if ok else 1
    print('  %d problemi' % rossi)
    sys.exit(1 if rossi else 0)
