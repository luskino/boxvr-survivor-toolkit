# -*- mode: python ; coding: utf-8 -*-
"""Eseguibile del toolkit sul NUOVO framework (pywebview), non la GUI Tkinter.

Differenze rispetto a BoxVR_Level_Fixer_*.spec:
  - il punto di ingresso e' web_migration_spike/main.py (avvia la Dashboard,
    che porta con se' Correggi, Genera e Gestione playlist nella stessa
    finestra);
  - niente tkinterdnd2/customtkinter: qui l'interfaccia e' HTML;
  - in piu' `pywebview`, e le PAGINE con i loro CSS/icone/suoni, che a
    runtime vengono copiati nella cartella di servizio.

Da compilare cosi', dalla radice del progetto:

    pyinstaller BoxVR_Toolkit_web.spec --noconfirm

NOTA sul runtime WebView2: NON viene incluso qui. Windows 10/11 aggiornati
lo hanno gia'; su una macchina senza, il programma lo segnala all'avvio -
`webview2_check.ensure_webview2_or_exit()` e' gia' chiamato da ogni main().
Va verificato su una macchina pulita prima di distribuire.
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all

SPIKE = 'web_migration_spike'

datas = [
    # le quattro pagine + i loro app.py (vengono importati a runtime dalla
    # Dashboard tramite importlib, quindi devono esistere come FILE)
    (os.path.join(SPIKE, 'correggi_real'), os.path.join(SPIKE, 'correggi_real')),
    (os.path.join(SPIKE, 'genera_real'), os.path.join(SPIKE, 'genera_real')),
    (os.path.join(SPIKE, 'dashboard_real'), os.path.join(SPIKE, 'dashboard_real')),
    (os.path.join(SPIKE, 'playlist_real'), os.path.join(SPIKE, 'playlist_real')),
    # foglio di stile condiviso, icone, pattern
    # Di `mockups/` servono SOLO il foglio di stile e gli assets: le pagine
    # vere li copiano nella cartella di servizio (vedi build_serving_dir).
    # Le cinque pagine HTML li' dentro sono i DISEGNI di partenza, con dati
    # finti, e non le apre nessuno: portarsele nell'eseguibile era peso
    # inutile, e in un repository pubblico sarebbero cinque file che
    # sembrano l'applicazione senza esserlo.
    (os.path.join(SPIKE, 'mockups', 'styles.css'), os.path.join(SPIKE, 'mockups')),
    (os.path.join(SPIKE, 'mockups', 'assets'), os.path.join(SPIKE, 'mockups', 'assets')),
    # campione del suono dei colpi usato dall'anteprima del visualizzatore
    ('assets/sfx', 'assets/sfx'),
    ('fonts', 'fonts'),
    ('data/icons', 'data/icons'),
    # NON si impacchetta data/training_sequences.json: e' il repertorio di
    # pattern di FitXR, contenuto del gioco. L'exe lo cerca prima nella
    # copia estratta dall'utente (boxvr_extract, che gira quando si applica
    # la patch) e senza solleva VocabularyMissing, che dice come ottenerlo.
    # Spedirlo dentro l'exe avrebbe annullato la cura messa nel .gitignore:
    # il file che la gente scarica davvero e' questo, non il repository.
    ('sidecar sandbox/engine.py', 'sidecar sandbox'),
]
binaries = []
# I moduli del progetto vengono importati DINAMICAMENTE (la Dashboard carica
# i tre app.py con importlib), quindi PyInstaller non li scopre da solo: senza
# questo elenco l'exe parte e muore con "No module named 'boxvr_patch'".
hiddenimports = [
    'percorsi', 'installa', 'trascina',
    'boxvr_fixer', 'boxvr_generator', 'boxvr_choreo', 'boxvr_extract',
    'boxvr_install', 'boxvr_patch', 'boxvr_playlist_manager',
    # boxvr_visual_preview NON va incluso: il port non lo usa (lo nomina solo
    # un commento), ma lui fa `from boxvr_fixer_gui import SongPlayer` e si
    # trascinava dentro l'eseguibile l'INTERA GUI Tkinter - 336 KB di codice
    # sostituito, piu' le sue dipendenze. Il visualizzatore del port e' suo,
    # disegnato su canvas, e non ha niente a che vedere con quello vecchio.
    'version', 'webview2_check',
    'pulizia_temp',
    # la tabella di tuning: le costanti dei motori la leggono all'import, e
    # senza di lei ricadrebbero sui numeri scritti a mano senza dirlo
    'tuning',
]

for modulo in ('pywebview', 'librosa', 'soundfile', 'mutagen', 'sounddevice'):
    try:
        d, b, h = collect_all(modulo)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        # pywebview si chiama "webview" per l'import: provo anche cosi'
        pass

for modulo in ('webview',):
    d, b, h = collect_all(modulo)
    datas += d
    binaries += b
    hiddenimports += h


a = Analysis(
    [os.path.join(SPIKE, 'main.py')],
    pathex=['.', SPIKE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinterdnd2', 'customtkinter'],
    noarchive=False,
    optimize=0,
)
# Il nome PORTA la versione: due build diverse non possono piu'
# sovrascriversi. Prima lo spec produceva sempre "BoxVR_Toolkit_web.exe" e
# ogni ricostruzione cancellava la precedente - cosi' e' andata persa la
# 1.29.1. VERSION_WEB e' la numerazione del toolkit web, ripartita da 1.0
# con il nome nuovo; VERSION resta ai due eseguibili Tkinter storici.
sys.path.insert(0, os.path.abspath('.'))
from version import VERSION_WEB
try:
    from version import BUILD
except ImportError:
    BUILD = 0
# Finche' si sta lavorando il nome porta il numero di build, cosi' due
# ricostruzioni non si sovrascrivono; a BUILD 0 il file prende il nome
# pubblico ed e' quello che si allega alla release.
NOME_EXE = ('BoxVR SrvToolkit %s Public Beta' % VERSION_WEB if not BUILD
            else 'BoxVR SrvToolkit %s build %d' % (VERSION_WEB, BUILD))

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=NOME_EXE,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
