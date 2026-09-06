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

"""«Installa in BoxVR» porta in gioco anche le playlist?

DIFETTO VERO, 06/09/2026. L'utente genera dei brani, spezza la playlist in
blocchi da trenta minuti, preme «Installa in BoxVR» - e in gioco non trova
niente. Guardando la libreria vera: `TrackData` e `TrackDefinitions` scritti
quel giorno alle 17:29, `WorkoutPlaylists` ferma a una settimana prima. I
brani erano arrivati; le playlist erano rimaste nella cartella dei generati.

Due difetti sovrapposti:

  1. `esegui_installazione` copiava solo trackdata/wav/wdef. Nessuno copiava
     il `.workoutplaylist.txt`: il log si limitava a dire di spostarlo a
     mano, cosa vera prima che «Installa in BoxVR» automatizzasse il resto.
  2. `generate_batch` restituiva `playlist_paths[0]`, cioe' SOLO LA PRIMA.
     Con un limite di durata le playlist sono piu' d'una - il caso della
     segnalazione - e le altre non erano nominate da nessuna parte.

NIENTE TOCCA LA LIBRERIA VERA. `boxvr_dirs` viene sostituita con tre
cartelle temporanee prima di ogni chiamata, e alla fine il test verifica che
le cartelle vere non siano state nemmeno sfiorate.
"""
import os
import shutil
import sys
import tempfile

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import boxvr_install                                            # noqa: E402
import installa                                                 # noqa: E402

esiti = []


def prova(ok, nome, dettaglio=''):
    esiti.append((bool(ok), nome, dettaglio))


def main():
    base = tempfile.mkdtemp(prefix='prova_installa_')
    generati = os.path.join(base, 'generati')
    td = os.path.join(base, 'gioco', 'TrackData')
    tdef = os.path.join(base, 'gioco', 'TrackDefinitions')
    plist = os.path.join(base, 'gioco', 'WorkoutPlaylists', 'BoxVR')
    for d in (generati, td, tdef, plist):
        os.makedirs(d, exist_ok=True)

    # due brani finti e DUE playlist, come quando c'e' un limite di durata
    ids = ['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb2']
    for tid in ids:
        for suf in ('.trackdata.txt', '.wav', '.wdef.txt'):
            with open(os.path.join(generati, tid + suf), 'w', encoding='utf-8') as f:
                f.write('{"trackId": "%s"}' % tid)
    playlist = ['Best Workout (1).workoutplaylist.txt',
                'Best Workout (2).workoutplaylist.txt']
    for nome in playlist:
        with open(os.path.join(generati, nome), 'w', encoding='utf-8') as f:
            f.write('{"playlist": "%s"}' % nome)
    percorsi_playlist = [os.path.join(generati, n) for n in playlist]

    # la libreria vera resta fuori: si guardera' alla fine che non sia stata
    # toccata, non ci si fida della sostituzione e basta
    vere = boxvr_install.boxvr_dirs()
    istantanea_vera = {}
    for d in vere:
        istantanea_vera[d] = (sorted(os.listdir(d)) if d and os.path.isdir(d) else None)
    boxvr_install.boxvr_dirs = lambda: (td, tdef, plist)

    # ------------------------------------------------------- anteprima
    a = installa.anteprima_installazione(generati, ids, percorsi_playlist)
    prova(a.get('n_playlist') == 2,
          "l'anteprima annuncia tutte le playlist, non solo la prima",
          'n_playlist=%s' % a.get('n_playlist'))
    prova(a.get('playlists_dir') == plist,
          "e dice in quale cartella andranno", str(a.get('playlists_dir')))

    # ---------------------------------------------------- installazione
    r = installa.esegui_installazione(generati, ids, playlist_paths=percorsi_playlist)
    prova(r.get('ok'), "l'installazione riesce", r.get('error') or '')
    installate = sorted(os.listdir(plist))
    prova(installate == sorted(playlist),
          'le playlist arrivano DAVVERO in WorkoutPlaylists',
          'trovate: %s' % (installate or '(niente)'))
    prova(r.get('n_playlist') == 2,
          'e il risultato le conta', 'n_playlist=%s' % r.get('n_playlist'))
    prova(len(os.listdir(td)) == 4 and len(os.listdir(tdef)) == 2,
          'i brani continuano ad arrivare come prima',
          'TrackData=%d TrackDefinitions=%d' % (len(os.listdir(td)), len(os.listdir(tdef))))

    # -------- niente playlist: non deve inventarsele ne' rompersi
    plist2 = os.path.join(base, 'gioco2', 'WorkoutPlaylists', 'BoxVR')
    td2 = os.path.join(base, 'gioco2', 'TrackData')
    tdef2 = os.path.join(base, 'gioco2', 'TrackDefinitions')
    for d in (plist2, td2, tdef2):
        os.makedirs(d, exist_ok=True)
    boxvr_install.boxvr_dirs = lambda: (td2, tdef2, plist2)
    r2 = installa.esegui_installazione(generati, ids)
    prova(r2.get('ok') and r2.get('n_playlist') == 0 and not os.listdir(plist2),
          'senza playlist installa i soli brani, senza errori',
          'n_playlist=%s, cartella playlist vuota=%s'
          % (r2.get('n_playlist'), not os.listdir(plist2)))

    # ---------------------------------- la libreria vera non e' stata toccata
    intatta = True
    for d, prima in istantanea_vera.items():
        dopo = (sorted(os.listdir(d)) if d and os.path.isdir(d) else None)
        if prima != dopo:
            intatta = False
    prova(intatta, 'la libreria VERA del gioco non e\' stata toccata',
          'confrontate tutte e tre le cartelle, prima e dopo')

    shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    main()
    print('===== INSTALLA: ANCHE LE PLAYLIST =====')
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
