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

"""Promuove la build interna a release pubblica.

    python rilascia.py --prova          guarda cosa farebbe, senza toccare niente
    python rilascia.py 1.2.0            promuove davvero

COSA FA. Le build interne avanzano con `BUILD` in version.py e si chiamano
"BoxVR SrvToolkit 1.2.0 build 6.exe"; il numero pubblico resta fermo. Quando
una di quelle build merita di uscire, questo comando:

  1. mette il numero pubblico che gli dici (o conferma quello che c'e' gia');
  2. azzera BUILD, cosi' il prossimo eseguibile prende il nome pubblico;
  3. data la voce del changelog, in italiano e in inglese.

COSA NON FA, ed e' voluto: non ricostruisce, non tocca git, non pubblica
niente. La pubblicazione e' un atto separato che si fa con il permesso
esplicito di chi decide, e dopo che una persona ha provato la build in VR.
Questo comando prepara i file e si ferma.
"""
import datetime
import io
import os
import re
import sys

RADICE = os.path.dirname(os.path.abspath(__file__))
VERSIONE = os.path.join(RADICE, 'version.py')
CHANGELOG = {
    'en': (os.path.join(RADICE, 'CHANGELOG.md'), 'not yet released',
           ['January', 'February', 'March', 'April', 'May', 'June', 'July',
            'August', 'September', 'October', 'November', 'December']),
    'it': (os.path.join(RADICE, 'CHANGELOG.it.md'), 'non ancora pubblicata',
           ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
            'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre']),
}

sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def leggi_versione():
    s = io.open(VERSIONE, encoding='utf-8').read()
    pub = re.search(r'^VERSION_WEB = "([^"]+)"', s, re.M)
    bui = re.search(r'^BUILD = (\d+)', s, re.M)
    if not pub or not bui:
        raise SystemExit('version.py non ha VERSION_WEB e BUILD come attesi')
    return s, pub.group(1), int(bui.group(1))


def main():
    argomenti = [a for a in sys.argv[1:] if not a.startswith('--')]
    prova = '--prova' in sys.argv or '-n' in sys.argv
    testo, pubblica, build = leggi_versione()
    nuova = argomenti[0] if argomenti else pubblica

    if not re.match(r'^\d+\.\d+\.\d+$', nuova):
        raise SystemExit('«%s» non e\' un numero di versione (serve X.Y.Z)' % nuova)

    print('adesso:  pubblica %s, build interna %d' % (pubblica, build))
    print('diventa: pubblica %s, build 0' % nuova)
    if build == 0 and nuova == pubblica:
        print('\n(la %s risulta gia\' promossa: non c\'e\' niente da fare)' % nuova)
        return

    # ---- le voci di changelog da datare
    oggi = datetime.date.today()
    lavori = []
    for lingua, (percorso, marcatore, mesi) in CHANGELOG.items():
        s = io.open(percorso, encoding='utf-8').read()
        vecchia = None
        for m in re.finditer(r'^## (\S+) — (.+)$', s, re.M):
            if m.group(2).strip() == marcatore:
                vecchia = m.group(0)
                break
        if vecchia is None:
            print('  ATTENZIONE  %s non ha una voce «%s»: non la dato'
                  % (os.path.basename(percorso), marcatore))
            continue
        data = '%d %s %d' % (oggi.day, mesi[oggi.month - 1], oggi.year)
        if lingua == 'en':
            data = '%d %s %d' % (oggi.day, mesi[oggi.month - 1], oggi.year)
        nuova_riga = '## %s — %s' % (nuova, data)
        lavori.append((percorso, s, vecchia, nuova_riga))
        print('  %-16s %s  ->  %s' % (os.path.basename(percorso), vecchia, nuova_riga))

    if prova:
        print('\n--prova: non ho scritto niente.')
        return

    for percorso, s, vecchia, nuova_riga in lavori:
        io.open(percorso, 'w', encoding='utf-8').write(s.replace(vecchia, nuova_riga, 1))

    testo = re.sub(r'^VERSION_WEB = "[^"]+"', 'VERSION_WEB = "%s"' % nuova,
                   testo, count=1, flags=re.M)
    testo = re.sub(r'^BUILD = \d+', 'BUILD = 0', testo, count=1, flags=re.M)
    io.open(VERSIONE, 'w', encoding='utf-8').write(testo)

    print('\nfatto. Adesso, in ordine:')
    print('  1. python -m PyInstaller --noconfirm --distpath dist_web '
          '--workpath build_web BoxVR_Toolkit_web.spec')
    print('     -> dist_web/BoxVR SrvToolkit %s Public Beta.exe' % nuova)
    print('  2. verifica che le correzioni siano DENTRO il binario')
    print('  3. falla provare in VR a una persona')
    print('  4. solo dopo un si\' esplicito: tag, release e pubblicazione')


if __name__ == '__main__':
    main()
