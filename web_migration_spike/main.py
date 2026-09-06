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

"""Punto di ingresso unico del toolkit (nuovo framework).

Avvia la **Dashboard**, che e' gia' la porta d'accesso alle altre tre pagine:
Correggi, Genera e Gestione playlist vivono nella stessa finestra e nella
stessa sessione pywebview (vedi `dashboard_real/app.py`, che copia tutte le
pagine in un'unica cartella di servizio).

    python main.py

E' anche il file da dare a PyInstaller: vedi `boxvr_toolkit.spec`.
"""
import os
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
for p in (QUI, os.path.dirname(QUI)):
    if p not in sys.path:
        sys.path.insert(0, p)

import percorsi  # noqa: E402  (deve venire dopo l'aggiustamento di sys.path)
percorsi.prepara_sys_path()
sys.path.insert(0, percorsi.DASHBOARD_DIR)


def main():
    import app as dashboard          # dashboard_real/app.py
    return dashboard.main()


if __name__ == '__main__':
    sys.exit(main() or 0)
