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

"""Da dove i test prendono un brano su cui lavorare.

Un tempo lo prendevano da `training data/mp3/`, cioe' musica commerciale sul
disco di chi sviluppa, citata per nome dentro il sorgente. Su un repository
pubblico non funziona: quella cartella non c'e' e non puo' esserci, quindi
i test sarebbero rossi per tutti tranne che per una persona.

Qui c'e' un solo punto che risponde alla domanda "dammi un brano":

    from brano_di_prova import audio_di_prova
    mp3 = audio_di_prova()          # un percorso utilizzabile, sempre

Se la cartella dell'autore c'e' ancora, si usa quella (i test continuano a
girare su musica vera su questa macchina). Altrimenti si sintetizza un brano
con `web_migration_spike/fixture_brano.py`: onda con i colpi a tempo e un
profilo di energia a gradini, che e' abbastanza per tutto cio' che questi
test verificano - griglia dei beat, segmenti, densita', marker.
"""
import os
import sys

RADICE = os.path.dirname(os.path.abspath(__file__))
CARTELLA_AUTORE = os.path.join(RADICE, 'training data', 'mp3')

_sintetico = None


def _sintetizza():
    """Un brano fabbricato, creato una volta sola per processo."""
    global _sintetico
    if _sintetico and os.path.isfile(_sintetico):
        return _sintetico
    import tempfile
    sys.path.insert(0, os.path.join(RADICE, 'web_migration_spike'))
    import fixture_brano
    d = tempfile.mkdtemp(prefix='boxvr_brano_di_prova_')
    _, _, wav = fixture_brano.crea(d)
    _sintetico = wav
    return _sintetico


def audio_di_prova(preferito=None):
    """Il percorso di un file audio su cui far girare un test.

    `preferito` e' il nome di un brano dell'autore (per esempio
    'Chop Suey!.mp3'): se c'e' lo si usa, cosi' su questa macchina i test
    restano identici a prima. Se non c'e' - cioe' ovunque tranne qui - si
    ottiene un brano sintetico, e il test gira lo stesso.
    """
    if preferito:
        p = os.path.join(CARTELLA_AUTORE, preferito)
        if os.path.isfile(p):
            return p
    if os.path.isdir(CARTELLA_AUTORE):
        for f in sorted(os.listdir(CARTELLA_AUTORE)):
            if f.lower().endswith(('.mp3', '.wav')):
                return os.path.join(CARTELLA_AUTORE, f)
    return _sintetizza()


def e_sintetico(percorso):
    """True se il brano e' quello fabbricato: serve ai test che vogliono
    allentare un'attesa scritta guardando un brano vero (per esempio un
    numero di sezioni musicali) quando girano sul sintetico."""
    return os.path.normpath(percorso) == os.path.normpath(_sintetico or '')
