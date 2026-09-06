# -*- coding: utf-8 -*-
"""Rigenera correggi_real/index.html e dashboard_real/index.html.

PERCHE' ESISTE
--------------
Quelle due pagine non sono scritte a mano: sono COMPOSTE da pezzi presi da
`genera_real/index.html` (CSS, testata, card "Anteprima brano", pannello
brani e una lista di funzioni JS condivise). E' una scelta voluta - cosi' la
logica comune resta UNA sola implementazione invece di tre copie destinate a
divergere - ma ha un effetto collaterale: **toccare genera_real non aggiorna
le altre due pagine finche' non si rigenera**.

E' gia' successo due volte di dimenticarsene, e ogni volta l'errore e'
comparso solo in Correggi (misure della riga brano, X di rimozione, pillola
"Rimuovi", stato "Rimuovi" al passaggio del mouse). Questo script esegue
tutta la catena nell'ordine giusto, in un colpo solo:

    python rigenera.py

Ogni passo e' idempotente: si puo' rilanciare quante volte si vuole.
"""
import os
import subprocess
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(QUI, '_build_correggi')

PASSI = [
    ('estrai_pezzi_genera.py', 'CSS e HTML condivisi da genera_real'),
    ('estrai_js_condiviso.py', 'blocchi JS condivisi (whitelist per nome)'),
    ('collega_i18n.py', 'dizionario di traduzione'),
    ('completa_i18n.py', 'ritraduzione automatica + avvio lingua'),
    ('fix_init_correggi.py', 'attesa di pywebviewready + proxy API'),
    ('aggiungi_raccogli_errori.py', 'raccoglitore di errori JS'),
    ('estrai_js_playlist.py', 'blocchi JS ridotti per il Playlist Manager'),
    ('componi_correggi.py', '-> correggi_real/index.html'),
    ('componi_dashboard.py', '-> dashboard_real/index.html'),
    ('componi_playlist.py', '-> playlist_real/index.html'),
]


def main():
    py = sys.executable
    for script, cosa in PASSI:
        percorso = os.path.join(BUILD, script)
        if not os.path.isfile(percorso):
            print('  MANCA %-28s (%s)' % (script, cosa))
            return 1
        r = subprocess.run([py, percorso], capture_output=True, text=True)
        stato = 'ok  ' if r.returncode == 0 else 'FALLITO'
        print('  %s %-28s %s' % (stato, script, cosa))
        if r.returncode != 0:
            print(r.stdout)
            print(r.stderr)
            return r.returncode
    print('\nFatto. Ricordati di rilanciare anche l\'audit:')
    print('  cd genera_real   && python ../audit_figma.py genera')
    print('  cd correggi_real && python ../audit_figma.py correggi')
    print('  cd dashboard_real && python ../audit_figma.py dashboard')
    return 0


if __name__ == '__main__':
    sys.exit(main())
