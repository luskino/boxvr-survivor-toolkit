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

"""I brani gia' generati spariscono, e solo quelli.

DIFETTO VERO, 06/09: 715 MB in 76 file dentro la cartella dei risultati,
accumulati sessione dopo sessione. La pulizia che gia' esisteva
(`pulisci_vecchie_cartelle`) si occupa delle cartelle TEMPORANEE di servizio
in %TEMP%, che sono un'altra cosa: quelle sono le copie di lavoro, questi
sono i risultati. Erano due problemi diversi, e per un pezzo si e' risolto
solo il primo.

Quattro cose da verificare, e la quarta e' la piu' importante:

  1. i file che produciamo noi vengono tolti
  2. da TUTTE le cartelle dei risultati (genera e correggi)
  3. senza far saltare niente se la cartella non esiste
  4. **cio' che non abbiamo prodotto noi resta dov'e'** - li' dentro finisce
     solo roba nostra, ma se qualcuno ci ha messo un suo file non tocca a
     noi decidere di buttarlo

Le cartelle sono finte: `percorsi.cartella_output` viene sostituita, e alla
fine si controlla che le cartelle VERE non siano state sfiorate.
"""
import os
import shutil
import sys
import tempfile

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import percorsi                                                 # noqa: E402
import pulizia_temp                                             # noqa: E402

esiti = []


def prova(ok, nome, dettaglio=''):
    esiti.append((bool(ok), nome, dettaglio))


NOSTRI = ['a1b2c3.trackdata.txt', 'a1b2c3.wav', 'a1b2c3.wdef.txt',
          'Best Workout 1.workoutplaylist.txt', 'a1b2c3.actionlist.json']
ALTRUI = ['appunti.txt', 'copertina.jpg', 'note personali.md']


def main():
    base = tempfile.mkdtemp(prefix='prova_risultati_')
    gen = os.path.join(base, 'brani_genera', 'generati')
    cor = os.path.join(base, 'brani_correggi', 'corretti')
    for d in (gen, cor):
        os.makedirs(d, exist_ok=True)
        for nome in NOSTRI + ALTRUI:
            with open(os.path.join(d, nome), 'wb') as f:
                f.write(b'\0' * 4096)
    # una cartella che NON esiste: non deve far saltare niente
    mancante = os.path.join(base, 'mai_creata', 'generati')

    # Fotografia di TUTTE le cartelle vere che la funzione sotto prova
    # potrebbe toccare: quelle configurate E quelle di ripiego sotto il
    # profilo utente. La prima versione guardava solo le configurate, e
    # infatti ha dichiarato "non sfiorate" una corsa che aveva appena
    # cancellato 76 file dal ripiego.
    vero = percorsi.cartella_output
    prima_vere = {}
    _appdata = os.environ.get('APPDATA') or ''
    for quale in ('genera', 'correggi'):
        candidate = []
        try:
            candidate.append(vero(quale))
        except Exception:                  # noqa: BLE001
            pass
        if _appdata:
            candidate.append(os.path.join(
                _appdata, 'BoxVR Level Fixer', 'brani_' + quale,
                'generati' if quale == 'genera' else 'corretti'))
        for d in candidate:
            prima_vere[d] = sorted(os.listdir(d)) if os.path.isdir(d) else None

    # si sostituiscono TUTTE E DUE le sorgenti che la pulizia consulta: la
    # cartella configurata e quella di ripiego sotto il profilo utente. La
    # seconda e' quella che, sulla macchina dove il difetto e' stato
    # misurato, conteneva i 715 MB mentre la prima era un'altra: una prova
    # che ne sostituisse una sola non avrebbe visto la meta' del lavoro.
    percorsi.cartella_output = lambda quale, sorgente=None: (
        gen if quale == 'genera' else cor)
    appdata_vero = os.environ.get('APPDATA')
    os.environ['APPDATA'] = os.path.join(base, 'finto_appdata')
    rip_gen = os.path.join(base, 'finto_appdata', 'BoxVR Level Fixer',
                           'brani_genera', 'generati')
    os.makedirs(rip_gen, exist_ok=True)
    for nome in NOSTRI + ALTRUI:
        with open(os.path.join(rip_gen, nome), 'wb') as f:
            f.write(b'x' * 4096)
    try:
        quanti, byte = pulizia_temp.svuota_risultati()
    finally:
        percorsi.cartella_output = vero
        if appdata_vero:
            os.environ['APPDATA'] = appdata_vero

    prova(quanti == len(NOSTRI) * 3,
          'toglie i file prodotti da tutte le cartelle dei risultati',
          'attesi %d (genera + correggi + ripiego), tolti %d (%.0f KB)'
          % (len(NOSTRI) * 3, quanti, byte / 1024))
    prova(sorted(os.listdir(rip_gen)) == sorted(ALTRUI),
          "anche la cartella di RIPIEGO viene svuotata: e' quella dove i "
          "715 MB si erano accumulati, mentre la configurata era un'altra",
          'rimasti: %s' % sorted(os.listdir(rip_gen)))
    rimasti_gen = sorted(os.listdir(gen))
    rimasti_cor = sorted(os.listdir(cor))
    prova(rimasti_gen == sorted(ALTRUI) and rimasti_cor == sorted(ALTRUI),
          "cio' che non abbiamo prodotto noi resta dov'e'",
          'rimasti in generati: %s' % rimasti_gen)
    prova(not any(n.endswith(('.wav', '.trackdata.txt', '.wdef.txt'))
                  for n in rimasti_gen + rimasti_cor),
          'nessun brano generato sopravvive', '')

    # Cartella inesistente: nessuna eccezione, nessun danno.
    #
    # ATTENZIONE, e c'e' una storia. La prima versione di questo blocco
    # sostituiva solo `cartella_output` e lasciava APPDATA quello vero: ma
    # `svuota_risultati` guarda DUE sorgenti, e la seconda e' proprio
    # APPDATA. Risultato: il test ha cancellato per davvero 76 file (715 MB)
    # dalla cartella dei risultati dell'autore. Erano file che andavano
    # cancellati comunque - e' cio' che questa funzione esiste per fare - ma
    # non e' un test a doverlo decidere.
    #
    # Le sostituzioni devono coprire TUTTO cio' che la funzione sotto prova
    # va a leggere. Se domani `svuota_risultati` imparasse a guardare una
    # terza cartella, questo blocco andrebbe aggiornato con lei.
    percorsi.cartella_output = lambda quale, sorgente=None: mancante
    os.environ['APPDATA'] = os.path.join(base, 'finto_appdata_vuoto')
    try:
        q2, _ = pulizia_temp.svuota_risultati()
        senza_eccezioni = True
    except Exception as e:                 # noqa: BLE001
        senza_eccezioni = False
        q2 = str(e)
    finally:
        percorsi.cartella_output = vero
        if appdata_vero:
            os.environ['APPDATA'] = appdata_vero
    prova(senza_eccezioni and q2 == 0,
          'una cartella che non esiste non fa saltare niente',
          'tolti %s' % q2)

    # e le cartelle VERE non sono state toccate
    intatte = True
    for d, prima in prima_vere.items():
        dopo = sorted(os.listdir(d)) if os.path.isdir(d) else None
        if prima != dopo:
            intatte = False
    prova(intatte, "le cartelle VERE dell'utente non sono state sfiorate",
          'confrontate prima e dopo: %s' % ', '.join(prima_vere) or '(nessuna)')

    shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    main()
    print('===== PULIZIA DEI RISULTATI =====')
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
