# -*- coding: utf-8 -*-
"""Prova la pulizia con cartelle finte, invece di darla per buona.

Tre casi che devono comportarsi in modo diverso:
  vecchia nostra  -> cancellata
  recente nostra  -> tenuta (potrebbe essere una finestra aperta adesso)
  vecchia altrui  -> tenuta (in %TEMP% c'e' roba di tutti)
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pulizia_temp import pulisci_vecchie_cartelle          # noqa: E402

T = tempfile.gettempdir()
VECCHIA = time.time() - 48 * 3600

casi = {
    'boxvr_prova_vecchia_xyz': VECCHIA,
    'boxvr_prova_recente_xyz': time.time(),
    'altroprogramma_vecchio_xyz': VECCHIA,
}
for nome, quando in casi.items():
    p = os.path.join(T, nome)
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, 'zavorra.bin'), 'wb') as f:
        f.write(b'\0' * 1024 * 512)          # mezzo MB, per pesare qualcosa
    os.utime(p, (quando, quando))

quante, byte = pulisci_vecchie_cartelle()
print('cancellate %d cartelle, %.1f MB' % (quante, byte / 1048576))

atteso = {
    'boxvr_prova_vecchia_xyz': False,        # deve sparire
    'boxvr_prova_recente_xyz': True,         # deve restare
    'altroprogramma_vecchio_xyz': True,      # deve restare
}
ok = True
for nome, deve_restare in atteso.items():
    c_e = os.path.isdir(os.path.join(T, nome))
    esito = 'ok   ' if c_e == deve_restare else 'SBAGLIATO'
    print('  %s %-30s %s' % (esito, nome,
                             'presente' if c_e else 'rimossa'))
    ok = ok and (c_e == deve_restare)

# pulizia delle finte rimaste
import shutil
for nome in casi:
    shutil.rmtree(os.path.join(T, nome), ignore_errors=True)

print('ESITO:', 'la pulizia si comporta come deve' if ok else 'COMPORTAMENTO SBAGLIATO')
sys.exit(0 if ok else 1)
