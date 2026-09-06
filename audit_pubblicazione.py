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

"""Cosa finirebbe DAVVERO su GitHub, e cosa c'e' dentro.

Da lanciare prima di ogni pubblicazione:

    python audit_pubblicazione.py

Fa due cose che il solo `.gitignore` non garantisce:

  1. Chiede a GIT quali file includerebbe - non si legge il .gitignore
     sperando di interpretarlo bene. Il 06/09/2026 quattordici sue righe
     erano scritte fra virgolette, che non sono sintassi valida: sembrava
     giusto e non escludeva niente. Sarebbero finiti online 2442 file
     invece di 353, libreria del gioco e musica commerciale comprese.
  2. Guarda i PRIMI BYTE di ogni file, non l'estensione. Un mp3 rinominato
     .txt resta un mp3, e un'estensione non e' una prova.

Uscita 0 se e' pubblicabile, 1 altrimenti.
"""
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

RADICE = os.path.dirname(os.path.abspath(__file__))

# L'unico file audio ammesso, e il motivo per cui lo e'
AUDIO_AMMESSO = {
    'assets/sfx/hit_punch.wav':
        'effetto Mixkit, licenza libera - vedi assets/sfx/SOURCE.md',
}

FIRME_AUDIO = [
    (b'RIFF', 'WAV/RIFF'), (b'ID3', 'MP3 con tag ID3'),
    (b'OggS', 'Ogg'), (b'fLaC', 'FLAC'), (b'\xff\xfb', 'MPEG audio'),
    (b'\xff\xf3', 'MPEG audio'), (b'\xff\xf2', 'MPEG audio'),
    (b'\x00\x00\x00\x20ftyp', 'MP4/M4A'),
]

# Campi che compaiono nei file di BoxVR e in nient'altro
SPIE_BOXVR = [
    ('_energyLevel', 'trackdata di BoxVR'),
    ('_beatInBar', 'trackdata di BoxVR'),
    ('musicActionList', 'playlist/coreografia di BoxVR'),
    # Il repertorio di pattern: i campi che il file estratto ha DAVVERO.
    # Prima si cercava 'sequencecollection', che e' il nome dell'asset Unity
    # di origine e dentro al JSON non compare: una copia del repertorio
    # sotto un altro nome passava per pubblicabile. Trovato iniettandola.
    ('sequenceLists', 'repertorio di pattern di BoxVR'),
    ('sequenceIntensity', 'repertorio di pattern di BoxVR'),
    ('moveActions', 'repertorio di pattern di BoxVR'),
]

LIMITE_GITHUB = 100 * 1024 * 1024      # oltre, GitHub rifiuta il file


def file_che_git_pubblicherebbe():
    """Lo si chiede a git, non lo si deduce dal .gitignore."""
    git = os.path.join(RADICE, '.git')
    temporaneo = not os.path.isdir(git)
    if temporaneo:
        subprocess.run(['git', 'init', '-q'], cwd=RADICE, check=True)
    try:
        out = subprocess.run(['git', 'add', '-A', '--dry-run'], cwd=RADICE,
                             capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
        fuori = []
        for riga in out.stdout.split('\n'):
            riga = riga.strip()
            if riga.startswith("add '") and riga.endswith("'"):
                fuori.append(riga[5:-1])
        return fuori
    finally:
        if temporaneo:
            shutil.rmtree(git, ignore_errors=True)


def esamina(percorso, rel):
    problemi = []
    try:
        with open(percorso, 'rb') as f:
            testa = f.read(64)
    except OSError:
        return problemi

    for firma, nome in FIRME_AUDIO:
        if testa.startswith(firma):
            if rel not in AUDIO_AMMESSO:
                problemi.append('FILE AUDIO (%s)' % nome)
            break

    if testa.startswith(b'MZ'):
        problemi.append('ESEGUIBILE/DLL Windows')

    est = os.path.splitext(rel)[1].lower()
    if est == '.json' or rel.endswith(('.trackdata.txt', '.wdef.txt')):
        try:
            with open(percorso, encoding='utf-8', errors='replace') as f:
                testo = f.read()
        except OSError:
            testo = ''
        for spia, cosa in SPIE_BOXVR:
            if spia in testo:
                problemi.append('DATI DEL GIOCO (%s)' % cosa)
                break

    if os.path.getsize(percorso) > LIMITE_GITHUB:
        problemi.append('OLTRE I 100 MB: GitHub lo rifiuta')

    return problemi


def main():
    elenco = file_che_git_pubblicherebbe()
    trovati, ammessi, peso = [], [], 0

    for rel in elenco:
        p = os.path.join(RADICE, rel.replace('/', os.sep))
        if not os.path.isfile(p):
            continue
        peso += os.path.getsize(p)
        if rel in AUDIO_AMMESSO:
            ammessi.append(rel)
        for problema in esamina(p, rel):
            trovati.append((rel, problema))

    print('File che git pubblicherebbe: %d  (%.1f MB)'
          % (len(elenco), peso / 1048576))
    print()
    if ammessi:
        print('Audio ammesso di proposito:')
        for a in ammessi:
            print('   %-40s %s' % (a, AUDIO_AMMESSO[a]))
        print()

    if trovati:
        print('DA NON PUBBLICARE (%d):' % len(trovati))
        for rel, problema in trovati:
            print('   %-55s %s' % (rel, problema))
    else:
        print('Nessun mp3, nessun binario del gioco, nessun dato di BoxVR,')
        print('nessun file oltre il limite di GitHub.')

    print()
    print('ESITO:', 'pubblicabile' if not trovati else 'NON PUBBLICABILE')
    return 1 if trovati else 0


def autoprova():
    """Il controllo riconosce davvero cio' che dice di riconoscere?

    Un controllo che non ha mai visto fallire nulla non e' un controllo. Si
    scrive un file con i campi del repertorio di FitXR in un posto
    pubblicato, si verifica che venga bloccato, e lo si rimuove.
    """
    import json
    finto = os.path.join(RADICE, 'docs', '_autoprova_repertorio.json')
    os.makedirs(os.path.dirname(finto), exist_ok=True)
    with open(finto, 'w', encoding='utf-8') as f:
        json.dump({'sequenceLists': [{'sequenceIntensity': 0,
                                      'sequenceList': [{'moveActions': []}]}]}, f)
    try:
        problemi = esamina(finto, 'docs/_autoprova_repertorio.json')
        ok = any('DATI DEL GIOCO' in p for p in problemi)
    finally:
        os.remove(finto)
    print('autoprova: il controllo riconosce il repertorio ->',
          'SI' if ok else 'NO, il controllo non protegge')
    return 0 if ok else 1


if __name__ == '__main__':
    if '--autoprova' in sys.argv:
        sys.exit(autoprova())
    sys.exit(main())
