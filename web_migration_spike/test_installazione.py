# -*- coding: utf-8 -*-
"""Installazione in BoxVR percorsa TUTTA, ma su una libreria finta.

Perche' esiste
--------------
"Installa in BoxVR" e' rimasta morta a lungo senza che nessuno se ne
accorgesse: la Dashboard non delegava `install_preview` e `install_run`, e
il proxy della pagina rifiutava la promessa in silenzio. I test che c'erano
chiamavano le Api dirette dei moduli, cioe' proprio la strada che l'utente
NON percorre.

Qui si passa dalla `Api` della Dashboard, che e' l'oggetto vero dietro
l'interfaccia quando si arriva a Correggi o Genera dalla schermata iniziale.
L'unica cosa che manca rispetto a un test manuale sono i clic.

`boxvr_install.boxvr_dirs` viene reindirizzata a una cartella temporanea: la
libreria vera non viene toccata, e nemmeno letta.

    python test_installazione.py
"""
import os
import shutil
import sys
import tempfile

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import boxvr_install

esiti = []


def prova(nome, condizione, dettaglio=''):
    esiti.append((bool(condizione), nome, dettaglio))


def main():
    finta = tempfile.mkdtemp(prefix='boxvr_libreria_finta_')
    td = os.path.join(finta, 'TrackData')
    tdef = os.path.join(finta, 'TrackDefinitions')
    plist = os.path.join(finta, 'WorkoutPlaylists', 'BoxVR')
    for d in (td, tdef, plist):
        os.makedirs(d)

    vere = boxvr_install.boxvr_dirs
    boxvr_install.boxvr_dirs = lambda: (td, tdef, plist)
    try:
        sys.path.insert(0, os.path.join(QUI, 'dashboard_real'))
        import app as dash
        import fixture_brano

        # Il brano di prova se lo fabbrica il test: audio sintetico e
        # trackdata corrispondente, in una cartella temporanea. Prima si
        # leggeva la cartella di lavoro dell'autore - musica commerciale, che
        # non sta nel repository: chiunque clonasse trovava questo test rosso
        # senza avere modo di farlo passare.
        brani_finti = tempfile.mkdtemp(prefix='boxvr_brani_finti_')
        fixture_brano.crea(brani_finti)
        dash.correggi_app.TEST_DIR = brani_finti

        wd = dash.build_serving_dir()
        dash.correggi_app._work_dir = wd
        dash.correggi_app._init_songs()
        api = dash.Api()

        brani = api.list_songs()
        prova('la Dashboard elenca i brani di Correggi', bool(brani),
              '%d brani' % len(brani))
        if not brani:
            return
        tid = brani[0]['id']

        # 1. correzione vera (scrive fuori dalla libreria)
        r = api.run_correction(tid, 12, 50)
        prova('correzione eseguita dalla Dashboard', r.get('ok'), r.get('error', ''))
        if not r.get('ok'):
            return
        prova("la correzione NON scrive nella libreria",
              os.path.abspath(r['output_folder']) != os.path.abspath(td)
              and not os.listdir(td),
              'cartella di uscita: %s' % r['output_folder'])

        # 2. anteprima dell'installazione
        a = api.install_preview()
        prova('anteprima disponibile dalla Dashboard', a.get('ok'), a.get('error', ''))
        prova("l'anteprima non scrive niente", not os.listdir(td))
        prova("l'anteprima indica la cartella giusta",
              a.get('trackdata_dir') == td, str(a.get('trackdata_dir')))

        # 3. installazione vera, primo giro: il brano non c'era
        r1 = api.install_run(None, True)
        prova('installazione eseguita', r1.get('ok'), r1.get('error', ''))
        scritti = [f for f in os.listdir(td) if f.endswith('.trackdata.txt')]
        prova('il file e\' nella libreria', bool(scritti), str(scritti))
        prova('nessun backup per un brano nuovo', not r1.get('backup_dir'),
              str(r1.get('backup_dir')))

        # 4. secondo giro: ora il brano c'e' gia', quindi va salvato prima
        primo = os.path.join(td, scritti[0])
        with open(primo, 'w', encoding='utf-8') as f:
            f.write('CONTENUTO PRECEDENTE')
        r2 = api.install_run(None, True)
        prova('seconda installazione eseguita', r2.get('ok'), r2.get('error', ''))
        bk = r2.get('backup_dir')
        prova('backup creato sovrascrivendo', bool(bk), str(bk))
        if bk:
            salvato = os.path.join(bk, scritti[0] + '.bak')
            prova('il backup contiene la versione precedente',
                  os.path.isfile(salvato)
                  and open(salvato, encoding='utf-8').read() == 'CONTENUTO PRECEDENTE')
            prova('istruzioni di ripristino accanto al backup',
                  os.path.isfile(os.path.join(os.path.dirname(bk),
                                              'COME RIPRISTINARE.txt')))
        prova('il file in libreria e\' stato aggiornato',
              open(primo, encoding='utf-8').read() != 'CONTENUTO PRECEDENTE')

        # 5. col backup disattivato non deve salvare niente
        with open(primo, 'w', encoding='utf-8') as f:
            f.write('SECONDA VERSIONE PRECEDENTE')
        r3 = api.install_run(None, False)
        prova('installazione senza backup eseguita', r3.get('ok'), r3.get('error', ''))
        prova('con il backup spento non salva niente', not r3.get('backup_dir'))

        shutil.rmtree(wd, ignore_errors=True)
    finally:
        boxvr_install.boxvr_dirs = vere
        shutil.rmtree(finta, ignore_errors=True)


if __name__ == '__main__':
    main()
    print('===== INSTALLAZIONE (libreria finta) =====')
    rossi = 0
    for ok, nome, dettaglio in esiti:
        print(('  ok      ' if ok else '  FALLITO ') + nome)
        if dettaglio:
            print('            %s' % dettaglio)
        if not ok:
            rossi += 1
    print('  %d/%d superati' % (len(esiti) - rossi, len(esiti)))
    print('\nNON coperto: i clic veri sui pulsanti. Il percorso dell\'API e\' lo')
    print('stesso che usa l\'interfaccia (Api della Dashboard, deleghe comprese).')
    sys.exit(1 if rossi else 0)
