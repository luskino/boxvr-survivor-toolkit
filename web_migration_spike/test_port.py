# -*- coding: utf-8 -*-
"""Test funzionali del port web: esercita le API come farebbe la pagina.

Finora il port aveva solo controlli STATICI (audit_codice/icone/bundle) e
misure dell'interfaccia. Qui si verifica che le funzioni facciano davvero
quello che dicono, compresi i casi limite e le cose che NON devono succedere
(scritture indesiderate, elenchi che schiantano su una cartella assente...).

    python test_port.py            tutti
    python test_port.py correggi   solo un gruppo

Nessun test scrive nella libreria di BoxVR.
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import traceback

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))

esiti = []


class Saltato(Exception):
    """Il test non puo' girare qui, e non e' un difetto del programma."""


def prova(nome):
    """decoratore: registra l'esito ed evita che un errore fermi la suite"""
    def deco(fn):
        def wrap():
            try:
                fn()
                esiti.append((True, nome, ''))
            except Saltato as e:
                esiti.append((None, nome, str(e)))
            except AssertionError as e:
                esiti.append((False, nome, str(e) or 'asserzione fallita'))
            except Exception as e:
                # Il repertorio di pattern di BoxVR non e' nel repository di
                # proposito (e' contenuto di FitXR: si estrae dalla propria
                # copia del gioco applicando la patch). I test che ne hanno
                # bisogno vanno SALTATI, non falliti: un rosso direbbe "c'e'
                # un difetto qui", e manderebbe a cercare un guasto che non
                # esiste.
                if type(e).__name__ == 'VocabularyMissing':
                    esiti.append((None, nome,
                                  'serve il repertorio di pattern: si ottiene '
                                  'applicando la patch alla propria copia di BoxVR'))
                else:
                    esiti.append((False, nome, '%s: %s' % (type(e).__name__, e)))
        wrap._nome = nome
        return wrap
    return deco


_CACHE = {}


def _api(pagina):
    """Carica app.py della pagina. In cache: ricaricarlo ad ogni test
    ripeterebbe l'analisi audio e falserebbe i test sullo stato."""
    if pagina in _CACHE:
        return _CACHE[pagina]
    d = os.path.join(QUI, pagina + '_real')
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(pagina + '_app', os.path.join(d, 'app.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pagina + '_app'] = mod
    spec.loader.exec_module(mod)
    _brani_di_prova(pagina, mod)
    _CACHE[pagina] = mod
    return mod


_BRANI_FINTI = {}


def _brani_di_prova(pagina, mod):
    """Ogni pagina lavora su un brano FABBRICATO, non su quello dell'autore.

    Prima si leggeva la cartella indicata in settings.json: musica
    commerciale sul disco di chi sviluppa, che non sta nel repository. I
    test erano quindi irriproducibili altrove - e un test dei preset e'
    davvero passato qui e fallito su un clone pulito, a parita' di codice,
    solo perche' pescava un brano diverso.
    """
    if not hasattr(mod, 'TEST_DIR'):
        return
    if pagina not in _BRANI_FINTI:
        import tempfile
        import fixture_brano
        d = tempfile.mkdtemp(prefix='boxvr_prova_%s_' % pagina)
        # Correggi vuole la coppia trackdata+wav; Genera parte dal solo
        # audio. La fixture produce entrambi, quindi va bene per tutte e due.
        tid, td, wav = fixture_brano.crea(d)
        if pagina != 'correggi':
            os.remove(td)          # a Genera il trackdata non serve: lo crea lui
        _BRANI_FINTI[pagina] = d
    mod.TEST_DIR = _BRANI_FINTI[pagina]


# ============================ percorsi =====================================

@prova('percorsi: si risolvono e le cartelle esistono')
def t_percorsi():
    import percorsi
    assert os.path.isdir(percorsi.RADICE), 'RADICE inesistente'
    assert os.path.isdir(percorsi.SPIKE), 'SPIKE inesistente'
    assert os.path.isdir(percorsi.MOCKUPS), 'MOCKUPS inesistente'


@prova('percorsi: nessun percorso assoluto cablato negli app.py')
def t_niente_cablati():
    trovati = []
    for c in ('correggi_real', 'genera_real', 'dashboard_real', 'playlist_real'):
        p = os.path.join(QUI, c, 'app.py')
        testo = open(p, encoding='utf-8').read()
        if 'F:\\BoxVR Songs Tool' in testo:
            trovati.append(c)
    assert not trovati, 'percorsi cablati ancora in: %s' % trovati


@prova('percorsi: cartella brani inesistente -> ripiego utilizzabile')
def t_ripiego():
    import percorsi
    for quale in ('correggi', 'genera'):
        c = percorsi.cartella_brani(quale)
        assert c and isinstance(c, str), 'nessuna cartella per %s' % quale


# ============================ correggi =====================================

@prova('correggi: elenca i brani reali')
def t_correggi_lista():
    ca = _api('correggi')
    ca._init_songs()
    songs = ca.Api().list_songs()
    assert songs, 'nessun brano trovato'
    for campo in ('id', 'name', 'artist', 'bpm', 'preset'):
        assert campo in songs[0], 'manca il campo %s' % campo


@prova('correggi: il dettaglio ha forma d\'onda e segmenti coerenti')
def t_correggi_dettaglio():
    ca = _api('correggi')
    ca._init_songs()
    d = ca.Api().get_song_detail(ca.Api().list_songs()[0]['id'])
    assert len(d['waveform_peaks']) == 1400, 'picchi attesi 1400, trovati %d' % len(d['waveform_peaks'])
    assert max(d['waveform_peaks']) <= 1.0, 'picchi non normalizzati'
    assert len(d['segments']) == d['n_segments'], 'segmenti incoerenti col conteggio'
    assert len(d['original_segments']) == d['n_segments'], 'struttura originale incoerente'
    assert sum(d['counts'].values()) == d['n_segments'], 'somma dei livelli != n segmenti'


@prova('correggi: cambiare preset cambia davvero i livelli')
def t_correggi_ricalcolo():
    ca = _api('correggi')
    ca._init_songs()
    tid = ca.Api().list_songs()[0]['id']
    a = ca.Api().recompute(tid, 12, 20)
    b = ca.Api().recompute(tid, 12, 80)
    assert a['counts'] != b['counts'], 'preset 20%% e 80%% danno lo stesso risultato'
    assert a['n_segments'] == b['n_segments'], 'il numero di segmenti non deve cambiare'


@prova('correggi: la correzione scrive un file valido FUORI dalla libreria')
def t_correggi_scrittura():
    import json
    ca = _api('correggi')
    ca._init_songs()
    tid = ca.Api().list_songs()[0]['id']
    r = ca.Api().run_correction(tid, 12, 50)
    assert r['ok'], 'correzione fallita: %s' % r.get('error')
    out = r['output_folder']
    assert 'LocalLow' not in out, 'ATTENZIONE: ha scritto dentro la libreria del gioco!'
    f = os.path.join(out, tid + '.trackdata.txt')
    assert os.path.isfile(f), 'file corretto non trovato: %s' % f
    with open(f, encoding='utf-8') as fh:
        json.load(fh)          # deve essere JSON valido


@prova('correggi: rimuovere un brano non cancella nessun file')
def t_correggi_rimozione():
    ca = _api('correggi')
    ca._init_songs()
    songs = ca.Api().list_songs()
    tid = songs[-1]['id']
    percorso = ca._song_paths[tid][0]
    ca.Api().remove_song(tid)
    assert os.path.isfile(percorso), 'la rimozione ha CANCELLATO il file!'
    assert len(ca.Api().list_songs()) == len(songs) - 1, 'il brano non e\' uscito dalla lista'


# ============================ genera =======================================

@prova('genera: elenco e stato di analisi')
def t_genera_lista():
    ga = _api('genera')
    ga._init_songs()
    songs = ga.Api().list_songs()
    assert isinstance(songs, list), 'list_songs non ritorna una lista'
    if songs:
        assert 'analysis_status' in songs[0], 'manca analysis_status'


@prova('genera: cartella dei brani assente -> elenco vuoto, nessun errore')
def t_genera_cartella_assente():
    ga = _api('genera')
    vecchia = ga.TEST_DIR
    try:
        ga.TEST_DIR = os.path.join(tempfile.gettempdir(), 'cartella_che_non_esiste_xyz')
        assert ga.discover_songs() == [], 'doveva tornare una lista vuota'
    finally:
        ga.TEST_DIR = vecchia


@prova('anteprima: la coreografia c\'e\' senza aver generato niente')
def t_choreo_senza_generare():
    """E' il blocco d'uso segnalato: prima bisognava dare un nome alla
    playlist e generare per poter guardare l'anteprima."""
    ga = _api('genera')
    if not ga._work_dir:
        ga._work_dir = ga.build_serving_dir()
    ga._init_songs()
    songs = ga.Api().list_songs()
    if not songs:
        return
    key = songs[0]['id']
    ga.get_analysis(key)          # come quando si apre il brano in anteprima
    r = ga.Api().get_action_list(key)
    assert r['ok'], 'nessuna coreografia: %s' % r.get('error')
    assert r['events'], 'coreografia vuota'
    assert all('time' in e and 'moveType' in e for e in r['events'][:20]), \
        'eventi senza tempo o tipo'
    assert r['duration'] > 0, 'durata non valorizzata'


@prova('anteprima: non scrive nessun file')
def t_choreo_non_scrive():
    ga = _api('genera')
    if not ga._work_dir:
        ga._work_dir = ga.build_serving_dir()
    ga._init_songs()
    songs = ga.Api().list_songs()
    if not songs:
        return
    key = songs[0]['id']
    ga.get_analysis(key)
    generati = os.path.join(ga.TEST_DIR, 'generati')
    prima = set(os.listdir(generati)) if os.path.isdir(generati) else set()
    ga.Api().get_action_list(key)
    dopo = set(os.listdir(generati)) if os.path.isdir(generati) else set()
    assert prima == dopo, 'l\'anteprima ha scritto in %s' % generati


@prova('anteprima: aggiungere un marker la fa ricostruire')
def t_choreo_marker():
    ga = _api('genera')
    if not ga._work_dir:
        ga._work_dir = ga.build_serving_dir()
    ga._init_songs()
    songs = ga.Api().list_songs()
    if not songs:
        return
    key = songs[0]['id']
    ga.get_analysis(key)
    ga.Api().get_action_list(key)
    assert key in ga._anteprima_choreo, 'anteprima non messa in cache'
    firma_prima = ga._anteprima_choreo[key][0]
    ga.Api().sidecar_start_record(key, 0.0)
    ga.Api().sidecar_mark(key, 5.0)
    assert key not in ga._anteprima_choreo, 'la cache non e\' stata buttata'
    ga.Api().get_action_list(key)
    assert ga._anteprima_choreo[key][0] != firma_prima, \
        'la firma non e\' cambiata pur avendo aggiunto un marker'
    ga.Api().sidecar_clear(key)


# ============================ playlist =====================================

@prova('playlist: elenca le playlist installate senza modificarle')
def t_playlist_lista():
    pa = _api('playlist')
    pls = pa.Api().list_playlists()
    assert isinstance(pls, list), 'non ritorna una lista'
    for p in pls:
        assert os.path.isfile(p['path']), 'playlist inesistente: %s' % p['path']


@prova('playlist: leggere una playlist non la tocca')
def t_playlist_lettura():
    pa = _api('playlist')
    pls = pa.Api().list_playlists()
    if not pls:
        return
    p = pls[0]['path']
    prima = os.path.getmtime(p), os.path.getsize(p)
    r = pa.Api().get_playlist(p)
    assert r['ok'], 'lettura fallita: %s' % r.get('error')
    dopo = os.path.getmtime(p), os.path.getsize(p)
    assert prima == dopo, 'la sola lettura ha modificato il file!'


# ============================ installazione ================================

@prova('installa: senza esecuzione precedente non installa nulla')
def t_installa_vuoto():
    ca = _api('correggi')
    ca._ultima_correzione.clear()
    r = ca.Api().install_preview()
    assert r['ok'] is False, 'ha detto di avere qualcosa da installare senza esecuzioni'


@prova('installa: anteprima non scrive nella libreria')
def t_installa_anteprima():
    import boxvr_install
    ca = _api('correggi')
    ca._init_songs()
    tid = ca.Api().list_songs()[0]['id']
    ca.Api().run_correction(tid, 12, 50)
    trackdata_dir, _, _ = boxvr_install.boxvr_dirs()
    prima = set(os.listdir(trackdata_dir)) if os.path.isdir(trackdata_dir) else set()
    a = ca.Api().install_preview()
    dopo = set(os.listdir(trackdata_dir)) if os.path.isdir(trackdata_dir) else set()
    assert prima == dopo, 'l\'ANTEPRIMA ha scritto nella libreria!'
    assert a['ok'], 'anteprima non riuscita'
    assert a['n_brani'] == 1, 'attesi 1 brano, trovati %s' % a['n_brani']
    assert 'LocalLow' in a['trackdata_dir'], 'destinazione inattesa: %s' % a['trackdata_dir']


@prova('installa: rileva se BoxVR e\' in esecuzione')
def t_installa_gioco():
    import installa
    assert isinstance(installa.gioco_in_esecuzione(), bool), 'non ritorna un booleano'


@prova('backup: salva le versioni esistenti prima di sovrascriverle')
def t_backup_sovrascrive():
    """Su una libreria FINTA in una cartella temporanea: questa prova non
    tocca la libreria vera del gioco, che nessun test deve toccare."""
    import boxvr_install
    base = tempfile.mkdtemp(prefix='boxvr_backup_')
    try:
        td = os.path.join(base, 'TrackData')
        tdef = os.path.join(base, 'TrackDefinitions')
        sorgente = os.path.join(base, 'nuovi')
        for d in (td, tdef, sorgente):
            os.makedirs(d)
        # un brano gia' nella libreria, e la sua versione nuova
        nome = 'abc123.trackdata.txt'
        with open(os.path.join(td, nome), 'w', encoding='utf-8') as f:
            f.write('VERSIONE ORIGINALE')
        with open(os.path.join(sorgente, nome), 'w', encoding='utf-8') as f:
            f.write('VERSIONE CORRETTA')

        n, backup = boxvr_install.install_files_con_backup(
            sorgente, [nome], [], td, tdef, fai_backup=True)

        assert n == 1, 'file copiati attesi 1, ottenuti %s' % n
        assert backup, 'nessuna cartella di backup creata'
        salvato = os.path.join(backup, nome + '.bak')
        assert os.path.isfile(salvato), 'il file originale non e\' nel backup'
        with open(salvato, encoding='utf-8') as f:
            assert f.read() == 'VERSIONE ORIGINALE', 'il backup non contiene l\'originale'
        with open(os.path.join(td, nome), encoding='utf-8') as f:
            assert f.read() == 'VERSIONE CORRETTA', 'la libreria non e\' stata aggiornata'
        istruzioni = os.path.join(os.path.dirname(backup), 'COME RIPRISTINARE.txt')
        assert os.path.isfile(istruzioni), 'manca il file con le istruzioni di ripristino'
    finally:
        shutil.rmtree(base, ignore_errors=True)


@prova('backup: un brano NUOVO non produce backup a vuoto')
def t_backup_nuovo():
    import boxvr_install
    base = tempfile.mkdtemp(prefix='boxvr_backup2_')
    try:
        td = os.path.join(base, 'TrackData')
        tdef = os.path.join(base, 'TrackDefinitions')
        sorgente = os.path.join(base, 'nuovi')
        for d in (td, tdef, sorgente):
            os.makedirs(d)
        nome = 'nuovo999.trackdata.txt'
        with open(os.path.join(sorgente, nome), 'w', encoding='utf-8') as f:
            f.write('BRANO NUOVO')
        n, backup = boxvr_install.install_files_con_backup(
            sorgente, [nome], [], td, tdef, fai_backup=True)
        assert n == 1
        assert backup is None, 'creata una cartella di backup senza niente da salvare'
    finally:
        shutil.rmtree(base, ignore_errors=True)


@prova('backup: si puo\' disattivare')
def t_backup_disattivato():
    import boxvr_install
    base = tempfile.mkdtemp(prefix='boxvr_backup3_')
    try:
        td = os.path.join(base, 'TrackData')
        tdef = os.path.join(base, 'TrackDefinitions')
        sorgente = os.path.join(base, 'nuovi')
        for d in (td, tdef, sorgente):
            os.makedirs(d)
        nome = 'abc123.trackdata.txt'
        for cartella, testo in ((td, 'ORIGINALE'), (sorgente, 'NUOVO')):
            with open(os.path.join(cartella, nome), 'w', encoding='utf-8') as f:
                f.write(testo)
        n, backup = boxvr_install.install_files_con_backup(
            sorgente, [nome], [], td, tdef, fai_backup=False)
        assert n == 1
        assert backup is None, 'ha fatto il backup pur essendo disattivato'
        assert not os.path.isdir(os.path.join(td, boxvr_install.BACKUP_DIRNAME))
    finally:
        shutil.rmtree(base, ignore_errors=True)


# ============================ pagine =======================================

@prova('pagine: tutte e quattro esistono e hanno lo script')
def t_pagine():
    for c in ('correggi_real', 'genera_real', 'dashboard_real', 'playlist_real'):
        p = os.path.join(QUI, c, 'index.html')
        assert os.path.isfile(p), 'manca %s' % p
        testo = open(p, encoding='utf-8').read()
        assert '<script>' in testo, '%s senza script' % c
        assert 'window.__errs' in testo, '%s senza raccoglitore di errori' % c


@prova('pagine: la cartella di servizio contiene tutto il necessario')
def t_serving():
    da = _api('dashboard')
    wd = da.build_serving_dir()
    try:
        file = set(os.listdir(wd))
        for atteso in ('index.html', 'correggi.html', 'genera.html', 'playlist.html', 'styles.css'):
            assert atteso in file, 'manca %s nella cartella di servizio' % atteso
        assert os.path.isdir(os.path.join(wd, 'assets')), 'mancano gli assets'
    finally:
        shutil.rmtree(wd, ignore_errors=True)


# ============================ esecuzione ===================================

GRUPPI = {
    'percorsi': [t_percorsi, t_niente_cablati, t_ripiego],
    'correggi': [t_correggi_lista, t_correggi_dettaglio, t_correggi_ricalcolo,
                 t_correggi_scrittura, t_correggi_rimozione],
    'genera': [t_genera_lista, t_genera_cartella_assente,
               t_choreo_senza_generare, t_choreo_non_scrive, t_choreo_marker],
    'playlist': [t_playlist_lista, t_playlist_lettura],
    'installa': [t_installa_vuoto, t_installa_anteprima, t_installa_gioco,
                 t_backup_sovrascrive, t_backup_nuovo, t_backup_disattivato],
    'pagine': [t_pagine, t_serving],
}

if __name__ == '__main__':
    scelti = sys.argv[1:] or list(GRUPPI)
    for g in scelti:
        if g not in GRUPPI:
            print('gruppo sconosciuto: %s (disponibili: %s)' % (g, ', '.join(GRUPPI)))
            sys.exit(2)
        for t in GRUPPI[g]:
            t()

    print('===== TEST FUNZIONALI DEL PORT =====')
    for ok, nome, msg in esiti:
        # ok=True superato, ok=False fallito, ok=None saltato (non poteva
        # girare qui, e non e' un difetto: vedi la classe Saltato)
        etichetta = '  ok    ' if ok else ('  saltato ' if ok is None else '  FALLITO  ')
        print(etichetta + nome)
        if ok is not True:
            print('           %s' % msg)
    n_ok = sum(1 for e in esiti if e[0] is True)
    n_salt = sum(1 for e in esiti if e[0] is None)
    n_ko = sum(1 for e in esiti if e[0] is False)
    coda = (' (%d saltati)' % n_salt) if n_salt else ''
    print('  %d/%d superati%s' % (n_ok, len(esiti) - n_salt, coda))
    sys.exit(0 if n_ko == 0 else 1)
