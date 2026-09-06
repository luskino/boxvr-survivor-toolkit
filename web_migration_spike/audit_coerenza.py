# -*- coding: utf-8 -*-
"""Primo giro di controllo qualita': coerenza INTERNA del progetto.

Gli altri audit guardano il prodotto (la pagina si apre? i colori sono
quelli? i testi si leggono?). Questo guarda il progetto: pezzi che non
combaciano piu' fra loro dopo una serie di modifiche.

Sono tutte cose che non rompono niente subito e si notano mesi dopo:

  1. token CSS dichiarati e mai usati, o usati e mai dichiarati;
  2. nomi nelle whitelist di estrazione che in genera_real non esistono piu'
     (l'estrattore fallisce, ma solo quando qualcuno rigenera);
  3. pagine composte piu' vecchie dei pezzi da cui nascono - cioe' qualcuno
     ha modificato un .part e non ha rigenerato;
  4. commenti che affermano cose smentite dal codice accanto.

Il quarto non e' automatizzabile in generale: qui si controllano le
affermazioni PRECISE che oggi sarebbero false, elencate a mano.

    python audit_coerenza.py
"""
import io
import os
import re
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
PAGINE = ['genera_real', 'correggi_real', 'dashboard_real', 'playlist_real']

problemi, note, ok = [], [], 0


def leggi(p):
    return io.open(p, encoding='utf-8').read() if os.path.isfile(p) else ''


# ---- 1. token CSS: dichiarati vs usati -----------------------------------
css = leggi(os.path.join(QUI, 'mockups', 'styles.css'))
testo_tutto = css + ''.join(leggi(os.path.join(QUI, p, 'index.html')) for p in PAGINE)
# le dichiarazioni non stanno solo nel foglio condiviso: --extra e
# --toggle-color nascono dentro il CSS delle pagine. Cercarle solo in
# styles.css li faceva risultare "usati e mai dichiarati" - falso allarme
# prodotto dal controllo stesso.
# Una dichiarazione non e' per forza a inizio riga: `.toggle.tg-basebeat { --toggle-color: #0071DA; }`
# sta tutta su una riga sola. Basta escludere le occorrenze dentro var(), che sono usi.
dichiarati = set(re.findall(r'(?<!\()(--[\w-]+)\s*:', testo_tutto))
usati = set(re.findall(r'var\((--[\w-]+)', testo_tutto))

# Token scritti da JavaScript a ogni ridimensionamento, non dal CSS: le
# quote della disposizione impilata dipendono da quanto e' alto davvero il
# testo dell'intestazione, che cambia con la lingua. Il valore di scorta
# nel var() e' il fallback voluto, non una dimenticanza - e sono l'unica
# eccezione ammessa, quindi vanno elencati qui uno per uno.
SCRITTI_DA_JS = {'--y-brani', '--y-anteprima', '--y-genera'}

mai_usati = sorted(dichiarati - usati)
mai_dichiarati = sorted(usati - dichiarati - SCRITTI_DA_JS)
if mai_dichiarati:
    problemi.append('token usati ma MAI dichiarati (var() che ripiega sul '
                    'valore di scorta, quindi il difetto non si vede): %s'
                    % ', '.join(mai_dichiarati))
else:
    ok += 1
if mai_usati:
    note.append('token dichiarati e mai usati: %s' % ', '.join(mai_usati))


# ---- 2. whitelist di estrazione vs funzioni davvero presenti -------------
sorgente = leggi(os.path.join(QUI, 'genera_real', 'index.html'))
definite = set(re.findall(r'function\s+(\w+)', sorgente))
definite |= set(re.findall(r'(?:const|let|var)\s+(\w+)\s*=', sorgente))
for nome in ('estrai_js_condiviso.py', 'estrai_js_playlist.py'):
    p = os.path.join(QUI, '_build_correggi', nome)
    t = leggi(p)
    m = re.search(r'VOLUTI\s*=\s*"""(.*?)"""', t, re.S)
    if not m:
        continue
    voluti = m.group(1).split()
    assenti = [v for v in voluti if v not in definite]
    if assenti:
        problemi.append('%s: chiede blocchi che in genera_real non esistono '
                        'piu\' (la prossima rigenerazione fallisce): %s'
                        % (nome, ', '.join(assenti)))
    else:
        ok += 1


# ---- 3. pagine composte piu' vecchie dei loro pezzi ----------------------
pezzi = []
build = os.path.join(QUI, '_build_correggi')
if os.path.isdir(build):
    for f in os.listdir(build):
        if f.endswith(('.part', '.py')):
            pezzi.append(os.path.join(build, f))
pezzi.append(os.path.join(QUI, 'genera_real', 'index.html'))
pezzi.append(os.path.join(QUI, 'mockups', 'styles.css'))
piu_recente = max((os.path.getmtime(p) for p in pezzi if os.path.isfile(p)), default=0)
vecchie = []
for p in ('correggi_real', 'dashboard_real', 'playlist_real'):
    f = os.path.join(QUI, p, 'index.html')
    if os.path.isfile(f) and os.path.getmtime(f) < piu_recente - 2:
        vecchie.append(p.replace('_real', ''))
if vecchie:
    problemi.append('pagine composte piu\' vecchie dei pezzi da cui nascono '
                    '(manca un `python rigenera.py`): %s' % ', '.join(vecchie))
else:
    ok += 1


# ---- 4. affermazioni nei commenti oggi false ----------------------------
# Elencate a mano: sono quelle che le modifiche recenti hanno reso obsolete.
FALSE = [
    (os.path.join(QUI, 'percorsi.py'),
     'NON punta mai da sola alla libreria di BoxVR',
     'ora Correggi ci punta di proposito (scelta del 03/09)'),
    (os.path.join(QUI, 'correggi_real', 'app.py'),
     'mai nella libreria live',
     'ora il risultato ci finisce, passando da "Installa in BoxVR"'),
    (os.path.join(os.path.dirname(QUI), 'boxvr_install.py'),
     'non ne abbiamo un backup da ripristinare',
     'il backup ora esiste (install_files_con_backup)'),
]
trovate = []
for percorso, frase, perche in FALSE:
    if frase in leggi(percorso):
        trovate.append('%s: "%s" - %s' % (os.path.basename(percorso), frase, perche))
if trovate:
    problemi.append('commenti che affermano cose non piu\' vere:\n      - '
                    + '\n      - '.join(trovate))
else:
    ok += 1


if __name__ == '__main__':
    print('===== COERENZA INTERNA =====')
    for n in note:
        print('  nota      %s' % n)
    if not problemi:
        print('  nessun problema trovato (%d controlli superati)' % ok)
        sys.exit(0)
    for p in problemi:
        print('  PROBLEMA  %s' % p)
    print('  %d controlli superati, %d problemi' % (ok, len(problemi)))
    sys.exit(1)
