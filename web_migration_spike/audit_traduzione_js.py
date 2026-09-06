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

"""Testi italiani SCRITTI DAL JAVASCRIPT che restano tali in inglese.

`audit_traduzione.py` guarda il markup: trova quello che sta scritto nella
pagina. Ma buona parte dei testi che l'utente legge non sta nel markup -
li scrive il codice a runtime:

    el.textContent = 'Analisi in corso — i comandi si attivano...'
    document.getElementById('p-name').textContent = 'Ricalcolo con BPM...'

Quei testi non passano da nessun dizionario a meno che qualcuno non ce li
metta, e nessun controllo li vedeva. Segnalato dall'utente su uno
screenshot in inglese pieno di italiano.

Qui si estraggono le stringhe assegnate a `textContent`/`innerHTML`/`title`
e quelle passate ad `alert()`, si tiene solo cio' che sembra italiano, e si
verifica se il dizionario IT->EN le conosce.
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

QUI = os.path.dirname(os.path.abspath(__file__))
PAGINE = ('genera_real', 'correggi_real', 'dashboard_real', 'playlist_real')

# Parole che in inglese non esistono (o non con quella grafia): bastano a
# distinguere una frase italiana da una tecnica o gia' tradotta.
SPIE = re.compile(
    r'\b(il|lo|la|le|gli|un|una|del|della|dei|delle|degli|nel|nella|'
    r'con|per|non|piu|più|che|come|quando|questo|questa|sono|essere|'
    r'analisi|brano|brani|colpi|marker|corso|attesa|errore|riuscita|'
    r'seleziona|selezionato|aggiungi|rimuovi|scegli|cartella|griglia|'
    r'ancora|pochi|resto|automatica|automatico|ritmo|cadenza|blocco|'
    r'blocchi|accento|accenti|marcati|ignorati|ignorato|generazione)\b',
    re.IGNORECASE)

# Assegnazioni di testo visibile
RE_ASSEGNA = re.compile(
    r"""(?:textContent|innerHTML|\.title|placeholder|alert)\s*(?:=|\()\s*
        (['"`])((?:\\.|(?!\1)[^\\])*)\1""",
    re.VERBOSE)

# Template literal con parti fisse: `${n} blocco ritmico, ...`
RE_TEMPLATE = re.compile(r'`((?:\\.|[^`\\])*)`')


def dizionario(html):
    """Le chiavi italiane che il dizionario IT->EN conosce."""
    chiavi = set()
    for m in re.finditer(r"^\s*'((?:\\.|[^'\\])+)':\s*'", html, re.M):
        chiavi.add(m.group(1))
    for m in re.finditer(r'^\s*"((?:\\.|[^"\\])+)":\s*"', html, re.M):
        chiavi.add(m.group(1))
    return chiavi


def pulisci(t):
    t = re.sub(r'\$\{[^}]*\}', '\u2026', t)      # via le interpolazioni
    t = re.sub(r'<[^>]+>', ' ', t)               # via i tag
    t = re.sub(r'\\u[0-9a-fA-F]{4}|\\n|\\t', ' ', t)
    return ' '.join(t.split())


def analizza(pagina):
    p = os.path.join(QUI, pagina, 'index.html')
    if not os.path.isfile(p):
        return []
    html = io.open(p, encoding='utf-8').read()
    # solo il corpo dello script, non il dizionario stesso
    noti = dizionario(html)

    trovati = {}
    for m in RE_ASSEGNA.finditer(html):
        grezzo = m.group(2)
        testo = pulisci(grezzo)
        if len(testo) < 4 or not SPIE.search(testo):
            continue
        if grezzo in noti or testo in noti:
            continue
        trovati.setdefault(testo, grezzo)

    for m in RE_TEMPLATE.finditer(html):
        testo = pulisci(m.group(1))
        if len(testo) < 8 or not SPIE.search(testo):
            continue
        if any(testo in k or k in testo for k in noti):
            continue
        trovati.setdefault(testo, m.group(1))

    return sorted(trovati)


def main():
    totale = 0
    for pagina in PAGINE:
        voci = analizza(pagina)
        if not voci:
            continue
        print('===== TESTI JS NON TRADOTTI: %s =====' % pagina.upper())
        for v in voci:
            print('   %s' % v[:110])
        print('   (%d)' % len(voci))
        print()
        totale += len(voci)

    if totale:
        print('TOTALE da valutare: %d' % totale)
        print()
        print('Non sono per forza difetti: un testo puo\' essere corretto in')
        print('entrambe le lingue, o non essere mai mostrato. Vanno guardati.')
    else:
        print('Nessun testo italiano scritto dal JavaScript resta fuori dal')
        print('dizionario.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
