# -*- coding: utf-8 -*-
"""Controlla che lo .spec di PyInstaller dichiari TUTTO il necessario.

Perche' esiste: i moduli del progetto vengono importati dinamicamente (la
Dashboard carica i tre app.py con importlib), quindi PyInstaller non li
scopre da solo. Il risultato e' un eseguibile che si compila senza un
avviso e poi muore all'avvio con "No module named 'X'". E' gia' successo
due volte: prima con `boxvr_patch`, poi con `installa`.

Questo controllo confronta i moduli DAVVERO importati dai file del port con
quelli dichiarati nello .spec, e si esegue in un secondo - senza compilare.

    python audit_bundle.py
"""
import io
import os
import re
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
RADICE = os.path.dirname(QUI)
SPEC = os.path.join(RADICE, 'BoxVR_Toolkit_web.spec')

# i file del port di cui guardare gli import
SORGENTI = [os.path.join(QUI, 'main.py'), os.path.join(QUI, 'percorsi.py'),
            os.path.join(QUI, 'installa.py')]
for c in ('correggi_real', 'genera_real', 'dashboard_real', 'playlist_real'):
    SORGENTI.append(os.path.join(QUI, c, 'app.py'))

# moduli locali del progetto (quelli che PyInstaller potrebbe non trovare)
LOCALI = set()
for cartella in (RADICE, QUI):
    for f in os.listdir(cartella):
        if f.endswith('.py') and not f.startswith('test_'):
            LOCALI.add(f[:-3])

importati = set()
for p in SORGENTI:
    if not os.path.isfile(p):
        continue
    testo = io.open(p, encoding='utf-8').read()
    for m in re.finditer(r'^\s*import\s+([\w.]+)', testo, re.M):
        importati.add(m.group(1).split('.')[0])
    for m in re.finditer(r'^\s*from\s+([\w.]+)\s+import', testo, re.M):
        importati.add(m.group(1).split('.')[0])

serve = {m for m in importati if m in LOCALI}

if not os.path.isfile(SPEC):
    print('===== AUDIT BUNDLE =====')
    print('  PROBLEMA  .spec non trovato:', SPEC)
    sys.exit(1)

spec = io.open(SPEC, encoding='utf-8').read()
i = spec.index('hiddenimports = [')
j = spec.index(']', i)
dichiarati = set(re.findall(r"'([\w.]+)'", spec[i:j]))

mancanti = sorted(serve - dichiarati)
inutili = sorted(d for d in dichiarati if d in LOCALI and d not in serve)

print('===== AUDIT BUNDLE =====')
print('  moduli locali importati dal port : %d' % len(serve))
print('  dichiarati in hiddenimports      : %d' % len(dichiarati & LOCALI))
if mancanti:
    for m in mancanti:
        print("  PROBLEMA  '%s' e' importato ma NON e' negli hiddenimports "
              "-> l'exe morira' all'avvio" % m)
else:
    print('  ok    tutti i moduli importati sono dichiarati')
if inutili:
    print('  nota      dichiarati ma non importati da questi file: %s'
          % ', '.join(inutili))

# le cartelle dei dati devono esistere
print()
for etichetta, rel in [('pagine correggi', 'web_migration_spike/correggi_real'),
                       ('pagine genera', 'web_migration_spike/genera_real'),
                       ('pagine dashboard', 'web_migration_spike/dashboard_real'),
                       ('pagine playlist', 'web_migration_spike/playlist_real'),
                       ('css e icone', 'web_migration_spike/mockups'),
                       ('suoni', 'assets/sfx')]:
    p = os.path.join(RADICE, rel.replace('/', os.sep))
    stato = 'ok   ' if os.path.isdir(p) else 'MANCA'
    # lo spec costruisce i percorsi con os.path.join(SPIKE, '...'), quindi
    # non compaiono come stringa intera: cerco l'ultimo pezzo del percorso
    foglia = rel.rstrip('/').split('/')[-1]
    dichiarato = ("'%s'" % foglia) in spec or rel in spec
    print('  %s %-18s %s  (nello spec: %s)'
          % (stato, etichetta, p, 'si' if dichiarato else 'NO'))

# Il nome dell'eseguibile deve PORTARE la versione, altrimenti ogni build
# sovrascrive la precedente e il vecchio binario sparisce senza finire in
# "dist/OLD Ver.zip" - e' esattamente cosi' che si e' persa la 1.29.1.
# Qui si controlla che lo spec non torni a un nome fisso.
print()
sys.path.insert(0, RADICE)
from version import VERSION_WEB

atteso = 'BoxVR SrvToolkit %s Public Beta' % VERSION_WEB
nome_fisso = "name='BoxVR" in spec or 'name="BoxVR' in spec
versionato = 'VERSION_WEB' in spec and 'name=NOME_EXE' in spec
if nome_fisso:
    print('  PROBLEMA  lo spec ha di nuovo un nome FISSO per l eseguibile: '
          'la prossima build sovrascrivera la precedente')
elif not versionato:
    print('  PROBLEMA  il nome dell eseguibile non deriva da VERSION_WEB')
else:
    print('  ok    il nome dell eseguibile porta la versione: %s.exe' % atteso)

# e il binario davvero costruito deve chiamarsi cosi'
costruito = os.path.join(RADICE, 'dist_web', atteso + '.exe')
if os.path.isfile(costruito):
    print('  ok    in dist_web c e %s.exe' % atteso)
else:
    presenti = []
    d = os.path.join(RADICE, 'dist_web')
    if os.path.isdir(d):
        presenti = [f for f in os.listdir(d) if f.endswith('.exe')]
    print('  nota      nessun %s.exe in dist_web (presenti: %s)'
          % (atteso, ', '.join(presenti) or 'nessuno'))

sys.exit(1 if (mancanti or nome_fisso or not versionato) else 0)
