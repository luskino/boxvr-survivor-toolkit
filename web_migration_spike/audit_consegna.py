# -*- coding: utf-8 -*-
"""Secondo giro di controllo qualita': la richiesta e' arrivata NELL'EXE?

Angolazione diversa da audit_coerenza.py, di proposito. Quello guarda se il
progetto e' coerente con se stesso; questo guarda se cio' che e' stato
chiesto e' finito davvero nell'eseguibile che l'utente apre.

Serve perche' fra "corretto nel sorgente" e "presente nell'exe" ci sono tre
passaggi che possono perdere qualcosa senza dire niente: la rigenerazione
delle pagine composte, la copia nella cartella di servizio, e il bundle di
PyInstaller. Ognuno dei tre ha gia' perso qualcosa almeno una volta.

Il controllo si fa sull'eseguibile: le pagine vengono lette dal server che
l'app stessa espone, i moduli Python dall'archivio interno del bundle.

    python audit_consegna.py [percorso\\dell.exe]
"""
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

QUI = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Il nome dell'eseguibile PORTA la versione, quindi qui non si puo'
# scriverlo a mano: si legge la stessa VERSION_WEB che usa lo spec, cosi'
# l'audit segue automaticamente ogni cambio di numerazione invece di
# cercare un file che non esiste piu'.
sys.path.insert(0, os.path.dirname(QUI))
from version import VERSION_WEB

NOME_EXE = 'BoxVR SrvToolkit %s Beta' % VERSION_WEB
EXE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(QUI), 'dist_web', NOME_EXE + '.exe')

# (etichetta, pagina, cosa deve esserci, perche')
ATTESI_PAGINE = [
    ('drag & drop', 'genera', 'trascinamento di file e cartelle',
     'la parte visiva del drop'),
    ('drag & drop', 'correggi', 'trascinamento di file e cartelle', ''),
    ('zoom 0 rimosso', 'genera', None, 'id="zoom-0" non deve esistere'),
    ('muto sul volume', 'genera', 'id="vol-muto"', ''),
    ('percentuale pugni', 'genera', 'row-pugni', ''),
    ('percentuale pugni', 'correggi', 'row-pugni', ''),
    ('lingua e tema sui dialoghi', 'index', 'dash-controlli', ''),
    ('interruttori a 12px', 'genera', 'font-size: 12px; gap: 3px', ''),
    ('backup collegato', 'correggi', 'install_run(salta,', ''),
]

MODULI_ATTESI = ['trascina', 'percorsi', 'installa', 'boxvr_install',
                 'boxvr_choreo', 'boxvr_generator', 'version']

esiti = []


def prova(nome, ok, dettaglio=''):
    esiti.append((bool(ok), nome, dettaglio))


def porta_di(_pid=None):
    """La porta in ascolto, via netstat: l'app la sceglie da sola a ogni
    avvio, non e' fissa.

    Non basta guardare il PID che abbiamo lanciato: un eseguibile PyInstanel
    in un file solo si sdoppia (padre che scompatta, figlio che lavora), e a
    mettersi in ascolto e' il figlio. Quindi si prendono TUTTI i processi
    con quel nome."""
    try:
        pids = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "(Get-Process '%s' -EA SilentlyContinue).Id" % NOME_EXE],
            capture_output=True, text=True, timeout=30).stdout.split()
        out = subprocess.run(['netstat', '-ano', '-p', 'TCP'],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return None
    nostri = set(pids)
    for riga in out.splitlines():
        campi = riga.split()
        if len(campi) >= 5 and campi[3] == 'LISTENING' and campi[4] in nostri:
            m = re.search(r':(\d+)$', campi[1])
            if m:
                return int(m.group(1))
    return None


def main():
    if not os.path.isfile(EXE):
        print('eseguibile non trovato:', EXE)
        return 2

    # --- 1. i moduli dentro il bundle ------------------------------------
    try:
        from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader
        a = CArchiveReader(EXE)
        d = a.extract('PYZ.pyz')
        if isinstance(d, tuple):
            d = d[1]
        t = os.path.join(tempfile.gettempdir(), '_consegna.pyz')
        open(t, 'wb').write(d)
        z = ZlibArchiveReader(t)
        # La GUI Tkinter NON deve stare nell'eseguibile web: e' il codice
        # che il port sostituisce. Ci finiva dentro di rimbalzo, perche'
        # boxvr_visual_preview (dichiarato negli hiddenimports ma mai usato
        # dal port) fa "from boxvr_fixer_gui import SongPlayer".
        prova("la GUI Tkinter NON e nell eseguibile web",
              "boxvr_fixer_gui" not in z.toc,
              "e il codice che questo port sostituisce")
        mancanti = [m for m in MODULI_ATTESI if m not in z.toc]
        prova('tutti i moduli del progetto sono nel bundle', not mancanti,
              'mancano: %s' % mancanti if mancanti else '%d moduli' % len(MODULI_ATTESI))
        co = z.extract('version')
        ver = [c for c in co.co_consts if isinstance(c, str) and c.count('.') == 2]
        prova('la versione e\' leggibile nel bundle', bool(ver), str(ver))
    except Exception as e:
        prova('lettura del bundle', False, str(e))

    # --- 2. le pagine servite dall'app in esecuzione ----------------------
    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    try:
        porta = None
        for _ in range(40):
            time.sleep(2)
            porta = porta_di()
            if porta:
                break
        prova('l\'app parte ed espone le sue pagine', bool(porta),
              'porta %s' % porta)
        if not porta:
            return 1

        pagine = {}
        for nome in ('index', 'genera', 'correggi', 'playlist'):
            try:
                with urllib.request.urlopen('http://127.0.0.1:%d/%s.html'
                                            % (porta, nome), timeout=20) as r:
                    pagine[nome] = r.read().decode('utf-8', 'replace')
            except Exception as e:
                pagine[nome] = ''
                prova('pagina %s servita' % nome, False, str(e))
        prova('tutte e quattro le pagine sono servite',
              all(pagine.get(n) for n in ('index', 'genera', 'correggi', 'playlist')))

        for etichetta, pagina, cosa, perche in ATTESI_PAGINE:
            testo = pagine.get(pagina, '')
            if not testo:
                continue
            if cosa is None:
                prova('%s (%s)' % (etichetta, pagina), 'id="zoom-0"' not in testo, perche)
            else:
                prova('%s (%s)' % (etichetta, pagina), cosa in testo, perche)

        # il tema scuro sta nel foglio di stile, non nelle pagine: cercarlo
        # nell'HTML era un difetto del controllo, non del prodotto
        try:
            with urllib.request.urlopen('http://127.0.0.1:%d/styles.css' % porta,
                                        timeout=20) as r:
                foglio = r.read().decode('utf-8', 'replace')
        except Exception:
            foglio = ''
        prova('tema scuro dal Figma nel foglio di stile',
              '#1A1A2E' in foglio and '#33334C' in foglio,
              'fondo pagina e pillola Silenzio misurati sul frame')

        # il dizionario deve essere lo STESSO su tutte le pagine
        conteggi = {}
        for nome, testo in pagine.items():
            i = testo.find('const TRAD = {')
            conteggi[nome] = testo[i:testo.find('};', i)].count(':') if i >= 0 else 0
        prova('stesso dizionario su tutte le pagine',
              len(set(conteggi.values())) == 1 and min(conteggi.values()) > 100,
              str(conteggi))
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=20)
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    codice = main()
    print('===== CONSEGNA: cosa e\' arrivato nell\'exe =====')
    rossi = 0
    for ok, nome, dettaglio in esiti:
        print(('  ok      ' if ok else '  FALLITO ') + nome)
        if dettaglio:
            print('            %s' % dettaglio)
        if not ok:
            rossi += 1
    print('  %d/%d superati' % (len(esiti) - rossi, len(esiti)))
    sys.exit(1 if (rossi or codice) else 0)
