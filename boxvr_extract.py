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

"""Estrae dal gioco installato i dati che il tool NON puo' ridistribuire.

Perche' esiste: `data/training_sequences.json` e' il repertorio ufficiale dei
pattern di BoxVR (47 sequenze), necessario alla modalita' Genera - ma e'
contenuto creativo di FitXR e non va spedito insieme al tool. Il pattern
standard del modding e' spedire l'ESTRATTORE e lasciare che ogni utente ricavi
i dati dalla propria copia legittima del gioco.

Vantaggio anche per noi: il file non e' piu' preparato a mano una volta sola, si
puo' rigenerare in qualunque momento (per esempio se un aggiornamento del gioco
cambiasse il repertorio).

DOVE STA (scoperto 25/08, non era documentato - il registro attribuiva tutto ai
.fdb, che invece contengono i workout, non il repertorio):
`BoxVR_Data/resources.assets`, come TextAsset Unity in CHIARO. Il JSON e'
preceduto dalla sua lunghezza in 4 byte little-endian, quindi non serve
bilanciare le graffe ne' indovinare dove finisce: si legge la lunghezza e si
prende esattamente quella. Nessuna libreria per asset Unity necessaria.

ATTENZIONE - dentro resources.assets ci sono DUE repertori, e prendere quello
sbagliato non da' nessun errore visibile, solo una coreografia diversa:
  * `Training.sequencecollection` - 7 liste, 47 pattern. **E' questo quello
    giusto**, identico al file finora spedito a mano;
  * `Survival.sequencecollection` - 8 liste, 50 pattern, intensita' fino a 7
    invece che a 5, con 7 pattern per livello in modo sospettosamente uniforme.
    E' il repertorio della modalita' Survival del gioco, non quella su cui il
    tool e' tarato.
Per questo la scelta si fa sul NOME dell'asset, che precede il JSON nel file.
Una prima versione sceglieva "quello con piu' pattern" e prendeva Survival.
"""
import json
import os
import struct

MARKER = b'{"sequenceLists"'
FILENAME = 'training_sequences.json'
# Un repertorio plausibile sta ampiamente sotto questa soglia (il reale e' ~42KB).
# Serve solo a non fidarsi ciecamente di 4 byte letti dal file: se la lunghezza
# dichiarata e' assurda, meglio accorgersene qui che allocare mezzo giga.
MAX_LEN = 8 * 1024 * 1024


def _game_data_dir(game_root):
    """`BoxVR_Data` dentro la cartella di installazione. Accetta sia la radice
    del gioco sia direttamente BoxVR_Data, cosi' chi chiama non deve saperlo."""
    if os.path.basename(game_root).lower() == 'boxvr_data':
        return game_root
    return os.path.join(game_root, 'BoxVR_Data')


def find_assets_file(game_root):
    path = os.path.join(_game_data_dir(game_root), 'resources.assets')
    return path if os.path.isfile(path) else None


WANTED_ASSET = 'training'      # Training.sequencecollection - vedi il modulo


def _asset_name_before(raw, json_start):
    """Nome dell'asset Unity che precede il JSON.

    Il layout e' <nome><NUL padding><lunghezza:4><json>, quindi il nome e'
    l'ultima stringa stampabile prima dei 4 byte di lunghezza."""
    back = raw[max(0, json_start - 96):json_start - 4]
    parts = [p for p in back.split(b'\x00') if p]
    if not parts:
        return ''
    try:
        return parts[-1].decode('ascii', 'ignore').strip()
    except Exception:
        return ''


def extract_training_sequences(game_root, wanted=WANTED_ASSET):
    """Ritorna (dati, messaggio). `dati` e' il dict del repertorio, o None.

    Non solleva eccezioni per i casi previsti (gioco non trovato, asset
    mancante, formato inatteso): chi chiama e' l'installazione della patch, che
    deve poter riferire un problema all'utente senza interrompersi."""
    assets = find_assets_file(game_root)
    if assets is None:
        return None, ("resources.assets non trovato: il percorso indicato non "
                      "sembra un'installazione di BoxVR.")
    try:
        raw = open(assets, 'rb').read()
    except OSError as e:
        return None, f"impossibile leggere resources.assets ({e})."

    trovati = []
    start = 0
    while True:
        i = raw.find(MARKER, start)
        if i < 0:
            break
        start = i + 1
        if i < 4:
            continue
        # i 4 byte che precedono il JSON sono la sua lunghezza (TextAsset Unity)
        (declared,) = struct.unpack_from('<I', raw, i - 4)
        if not (0 < declared <= MAX_LEN):
            continue
        blob = raw[i:i + declared]
        try:
            data = json.loads(blob.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        lists = data.get('sequenceLists')
        if not isinstance(lists, list) or not lists:
            continue
        trovati.append((_asset_name_before(raw, i), data, lists))

    if not trovati:
        return None, ("repertorio non trovato dentro resources.assets: il "
                      "formato del gioco potrebbe essere cambiato.")

    # scelta per NOME, non per dimensione: vedi la nota in cima al modulo
    scelti = [t for t in trovati if wanted in t[0].lower()]
    if not scelti:
        nomi = ', '.join(t[0] or '?' for t in trovati)
        return None, (f"trovati {len(trovati)} repertori ({nomi}) ma nessuno "
                      f"corrisponde a '{wanted}': il gioco potrebbe averli "
                      f"rinominati.")
    nome, data, lists = scelti[0]
    n_patterns = sum(len(l.get('sequenceList', [])) for l in lists)
    scartati = [t[0] for t in trovati if t is not scelti[0]]
    extra = f" (ignorati: {', '.join(scartati)})" if scartati else ""
    return data, (f"repertorio estratto da {nome}: {len(lists)} liste, "
                  f"{n_patterns} pattern{extra}.")


def user_data_path():
    """Dove finisce il repertorio estratto: %APPDATA%\\BoxVR Level Fixer\\.

    NON accanto all'eseguibile: con --onefile quella e' una cartella temporanea
    diversa a ogni avvio, cancellata alla chiusura - un file scritto li'
    sparirebbe. E' la stessa cartella gia' usata per le preferenze e per la
    cache di segmentazione, l'unica scrivibile senza permessi di amministratore
    e stabile fra un avvio e l'altro."""
    base = os.environ.get('APPDATA') or os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, 'BoxVR Level Fixer')
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return os.path.join(d, FILENAME)


def is_available():
    """True se il repertorio e' gia' disponibile (estratto o spedito)."""
    if os.path.isfile(user_data_path()):
        return True
    bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'data', FILENAME)
    return os.path.isfile(bundled)


def write_training_sequences(game_root, dest_path=None):
    """Estrae e scrive il repertorio. Ritorna (ok, messaggio).

    Senza `dest_path` scrive nella cartella dati utente - il caso normale."""
    dest_path = dest_path or user_data_path()
    data, msg = extract_training_sequences(game_root)
    if data is None:
        return False, msg
    try:
        parent = os.path.dirname(dest_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(dest_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    except OSError as e:
        return False, f"estratto ma non scrivibile in {dest_path} ({e})."
    return True, msg


if __name__ == '__main__':
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else \
        r"E:\SteamLibrary\steamapps\common\BOXVR"
    data, msg = extract_training_sequences(root)
    print(msg)
    if data is None:
        sys.exit(1)
    for l in data['sequenceLists']:
        print(f"  type={l.get('sequenceType')} intensity={l.get('sequenceIntensity')} "
              f"n={len(l.get('sequenceList', []))}")
