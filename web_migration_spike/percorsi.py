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

"""Unico posto dove si risolvono i percorsi del port.

Prima ogni `app.py` aveva cablato `F:\\BoxVR Songs Tool\\...`: va bene finche'
si lancia dai sorgenti su QUESTO pc, ma un eseguibile distribuito non trova
nulla. Qui i percorsi si ricavano da dove sta il file (o da `sys._MEIPASS`
quando si gira dentro un bundle PyInstaller).

Uso tipico, in cima a un app.py:

    from percorsi import RADICE, SPIKE, MOCKUPS, cartella_brani

Le cartelle dei brani sono CONFIGURABILI (`settings.json`), con le cartelle
di test come ripiego: cosi' il tool distribuito puo' lavorare sulla libreria
vera senza toccare il codice.
"""
import json
import os
import sys

# --- radici -----------------------------------------------------------------

def _in_bundle():
    """True quando si gira dentro un eseguibile PyInstaller."""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


if _in_bundle():
    # In un bundle PyInstaller i dati dichiarati nello .spec finiscono in
    # _MEIPASS mantenendo la struttura di cartelle: la radice del progetto e'
    # _MEIPASS stesso, e le pagine stanno in _MEIPASS/web_migration_spike.
    RADICE = sys._MEIPASS
    SPIKE = os.path.join(sys._MEIPASS, 'web_migration_spike')
else:
    SPIKE = os.path.dirname(os.path.abspath(__file__))
    RADICE = os.path.dirname(SPIKE)

MOCKUPS = os.path.join(SPIKE, 'mockups')
ASSETS_SFX = os.path.join(RADICE, 'assets', 'sfx')
CORREGGI_DIR = os.path.join(SPIKE, 'correggi_real')
GENERA_DIR = os.path.join(SPIKE, 'genera_real')
PLAYLIST_DIR = os.path.join(SPIKE, 'playlist_real')
DASHBOARD_DIR = os.path.join(SPIKE, 'dashboard_real')


def prepara_sys_path():
    """Rende importabili i moduli del progetto (boxvr_fixer, version, ...)
    sia dai sorgenti sia da un bundle."""
    for p in (RADICE, SPIKE):
        if p and p not in sys.path:
            sys.path.insert(0, p)


# --- cartelle dei brani, configurabili --------------------------------------

def _settings_path():
    base = os.environ.get('APPDATA') or RADICE
    return os.path.join(base, 'BoxVR Level Fixer', 'settings.json')


def _settings():
    try:
        with open(_settings_path(), encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


# ripieghi: le cartelle di test usate finora
_RIPIEGO = {
    'correggi': os.path.join(RADICE, 'file di test da correggere wav'),
    'genera': os.path.join(RADICE, 'File di test da correggere mp3'),
}


def _trackdata_libreria():
    """La cartella TrackData della libreria di BoxVR, se esiste."""
    try:
        import boxvr_install
        d = boxvr_install.boxvr_dirs()[0]
    except Exception:
        return None
    return d if d and os.path.isdir(d) else None


def dentro_la_libreria(percorso):
    """True se `percorso` sta dentro l'albero della libreria di BoxVR.
    Serve a non scriverci per sbaglio quando la sorgente e' la libreria."""
    if not percorso:
        return False
    try:
        import boxvr_install
        radici = [d for d in boxvr_install.boxvr_dirs() if d]
    except Exception:
        return False
    p = os.path.normcase(os.path.abspath(percorso))
    for r in radici:
        r = os.path.normcase(os.path.abspath(os.path.dirname(r)))
        if p == r or p.startswith(r + os.sep):
            return True
    return False


def cartella_output(quale, sorgente=None):
    """Dove finiscono i file prodotti. MAI dentro la libreria del gioco.

    Prima era semplicemente `<sorgente>/corretti`. Va bene finche' la
    sorgente e' una cartella di lavoro; da quando puo' essere la libreria di
    BoxVR non va piu' bene per niente, perche' produrrebbe scritture dentro
    l'albero del gioco senza che nessuno le abbia chieste.
    """
    sorgente = sorgente or cartella_brani(quale)
    nome = 'corretti' if quale == 'correggi' else 'generati'
    if not dentro_la_libreria(sorgente):
        return os.path.join(sorgente, nome)
    base = os.environ.get('APPDATA') or RADICE
    fuori = os.path.join(base, 'BoxVR Level Fixer', nome)
    os.makedirs(fuori, exist_ok=True)
    return fuori


def cartella_brani(quale):
    """Cartella sorgente dei brani per 'correggi' o 'genera'.

    Ordine: quella scelta dall'utente (settings.json, chiavi
    `source_dir_correggi` / `source_dir_genera`), poi la cartella di test,
    poi - solo per Correggi - la libreria vera di BoxVR.

    Fino al 03/09 qui c'era scritto il contrario ("NON punta mai da sola
    alla libreria"), e la ragione era buona: scriverci dentro dev'essere una
    scelta esplicita. Quella ragione vale ancora, ma riguarda la SCRITTURA:
    leggere dalla libreria e' innocuo, ed e' quello che serve a Correggi.
    Cio' che si produce non ci finisce mai per ripiego - vedi
    cartella_output(), che la libreria la esclude per costruzione, e
    "Installa in BoxVR", che chiede conferma e fa il backup.
    """
    scelta = _settings().get('source_dir_' + quale)
    if scelta and os.path.isdir(scelta):
        return scelta
    if os.path.isdir(_RIPIEGO[quale]):
        return _RIPIEGO[quale]
    # Correggi lavora sui workout che il gioco ha gia': la libreria e' la
    # sorgente naturale, e trovarcela gia' puntata evita all'utente di
    # doverla cercare (scelta dell'utente, 03/09). Solo LETTURA: i file
    # corretti finiscono in cartella_output(), che la libreria la esclude
    # per costruzione.
    # Genera no: la sua sorgente sono mp3 da cui creare, mentre nella
    # libreria ci sono wav gia' lavorati.
    if quale == 'correggi':
        libreria = _trackdata_libreria()
        if libreria:
            return libreria
    # Ne' una scelta dell'utente ne' le cartelle di test (che in un
    # eseguibile distribuito NON esistono): uso una cartella dati sotto il
    # profilo utente. Parte vuota, e l'utente aggiunge i brani con
    # "Aggiungi brani +" - lo stato "elenco vuoto" e' gia' previsto dal
    # wireframe.
    base = os.environ.get('APPDATA') or RADICE
    dati = os.path.join(base, 'BoxVR Level Fixer', 'brani_' + quale)
    os.makedirs(dati, exist_ok=True)
    return dati


def salva_impostazione(chiave, valore):
    """Scrive una singola impostazione, lasciando intatte le altre.

    Un punto solo per scrivere: cosi' due salvataggi diversi non si
    sovrascrivono a vicenda rileggendo e riscrivendo il file ciascuno a
    modo suo.
    """
    p = _settings_path()
    dati = _settings()
    dati[chiave] = valore
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(dati, f, indent=2)
    return valore


def imposta_cartella_brani(quale, percorso):
    """Salva la cartella scelta dall'utente."""
    if quale not in _RIPIEGO:
        raise ValueError('quale dev\'essere "correggi" o "genera"')
    p = _settings_path()
    dati = _settings()
    dati['source_dir_' + quale] = percorso
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(dati, f, indent=2)
    return percorso


if __name__ == '__main__':
    print('in bundle      :', _in_bundle())
    print('RADICE         :', RADICE, '   esiste:', os.path.isdir(RADICE))
    print('SPIKE          :', SPIKE, '   esiste:', os.path.isdir(SPIKE))
    print('MOCKUPS        :', MOCKUPS, '   esiste:', os.path.isdir(MOCKUPS))
    print('ASSETS_SFX     :', ASSETS_SFX, '   esiste:', os.path.isdir(ASSETS_SFX))
    for q in ('correggi', 'genera'):
        c = cartella_brani(q)
        print('brani %-9s: %s   esiste: %s' % (q, c, os.path.isdir(c)))
