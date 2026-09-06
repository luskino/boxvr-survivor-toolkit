#!/usr/bin/env python3
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

r"""
Patch al gioco BoxVR
====================
Fa smettere a BoxVR di rigenerare la coreografia procedurale a ogni avvio di
una playlist utente, cosi' usa quella scritta da noi nella playlist stessa.

COSA FA, IN CONCRETO. In GameStateTraining.OnEnableGameState il gioco fa:

    List<MusicAction> lista = null;
    if (lista != null) goto PLAY;                 // condizione morta nel binario
    MusicActionFactory.instance.GenerateActionSequence(...);  // <-- azzerata
    lista = playlist.songs[i].musicActionList;    // rilegge da li'
  PLAY:
    sequencer.PlaySequence(lista);

GenerateActionSequence SCRIVE dentro songs[i].musicActionList e la riga
successiva la rilegge. Neutralizzando la sola chiamata, quella lettura prende
la lista che WorkoutPlaylist.LoadFromJSON ha gia' deserializzato dal nostro
file. Vedi [[boxvr-internals]] per come ci si e' arrivati.

PERCHE' E' SICURA
  - si sostituiscono 42 byte con NOP: stessa lunghezza, nessun offset si sposta;
  - il blocco contiene solo il caricamento degli argomenti e una chiamata a un
    metodo void, quindi l'effetto netto sullo stack e' zero;
  - i byte attesi vengono verificati PRIMA di scrivere: se non corrispondono la
    patch si rifiuta invece di rovinare il file;
  - viene sempre creato un backup con data e ora, e "Verifica integrita' dei
    file" di Steam ripristina comunque l'originale.

CONSEGUENZA DA DIRE ALL'UTENTE: a patch attiva il gioco suona ESATTAMENTE la
lista di azioni della playlist. Le playlist con lista vuota - tutte quelle
generate prima di questa funzione - suonano quindi SENZA PUGNI. Non e' un
guasto.
"""

import glob
import os
import shutil
import time

# Offset e byte attesi per la build 5054303 (l'unica esistente: il gioco e'
# abbandonato dal 2019). La verifica sui byte rende innocuo il caso in cui la
# build fosse diversa: la patch semplicemente si rifiuta.
PATCH_OFFSET = 0xFE47
PATCH_LENGTH = 42
ORIGINAL_BYTES = bytes.fromhex(
    "7ef1400004"    # ldsfld   MusicActionFactory.instance
    "16"            # ldc.i4.0 (GameMode.BoxVR_Training)
    "02"            # ldarg.0
    "7b91030004"    # ldfld    playlist
    "286f4f0006"    # call     get_instance
    "6f734f0006"    # callvirt get_currentProfile
    "7ba0400004"    # ldfld    settings
    "7bc3400004"    # ldfld    boxVR
    "7bc8400004"    # ldfld    trainingDifficulty
    "6ff24f0006"    # callvirt GenerateActionSequence
)
PATCHED_BYTES = b"\x00" * PATCH_LENGTH

STATE_ORIGINAL = 'original'
STATE_PATCHED = 'patched'
STATE_UNKNOWN = 'unknown'
STATE_MISSING = 'missing'


def dll_path(game_dir):
    if not game_dir:
        return None
    return os.path.join(game_dir, 'BoxVR_Data', 'Managed', 'Assembly-CSharp.dll')


def looks_like_game_dir(path):
    """Riconosce una cartella di installazione valida senza dipendere da come
    e' stata installata (Steam, Oculus, Viveport: cambia il percorso, non il
    contenuto)."""
    if not path or not os.path.isdir(path):
        return False
    return os.path.isfile(os.path.join(path, 'BoxVR_Data', 'Managed', 'Assembly-CSharp.dll'))


def state(game_dir):
    p = dll_path(game_dir)
    if not p or not os.path.isfile(p):
        return STATE_MISSING
    try:
        with open(p, 'rb') as f:
            f.seek(PATCH_OFFSET)
            cur = f.read(PATCH_LENGTH)
    except OSError:
        return STATE_MISSING
    if cur == ORIGINAL_BYTES:
        return STATE_ORIGINAL
    if cur == PATCHED_BYTES:
        return STATE_PATCHED
    return STATE_UNKNOWN


def is_game_running():
    """La DLL non va toccata mentre il gioco gira: la terrebbe aperta e in ogni
    caso leggerebbe la versione vecchia gia' caricata in memoria."""
    try:
        import subprocess
        # CREATE_NO_WINDOW (27/08) - stessa correzione di boxvr_generator.py,
        # questa chiamata mancava ancora la soppressione della console.
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq BoxVR.exe'],
                             capture_output=True, text=True, timeout=15, creationflags=flags)
        return 'BoxVR.exe' in out.stdout
    except Exception:
        return False


def _ensure_vocabulary(game_dir, force=False):
    """Estrae il repertorio dei pattern dalla copia del gioco dell'utente.

    Agganciato qui perche' questo e' l'unico momento in cui sappiamo con
    certezza dove sta il gioco, ed e' anche il momento giusto: la patch e' il
    prerequisito della modalita' Genera, che e' l'unica che usa il repertorio.
    Cosi' l'utente indica il gioco una volta sola e ottiene entrambe le cose.

    NON deve mai far fallire la patch: l'operazione principale e' quella, e una
    patch applicata con il repertorio mancante e' comunque uno stato utile
    (Genera lo dira' con un messaggio chiaro, vedi VocabularyMissing). Per
    questo qualunque errore qui torna solo come nota aggiuntiva."""
    try:
        import boxvr_extract
    except ImportError:
        return ""
    try:
        if not force and boxvr_extract.is_available():
            return ""
        ok, msg = boxvr_extract.write_training_sequences(game_dir)
        return f" {msg}" if ok else f" Repertorio non estratto: {msg}"
    except Exception as e:   # non deve mai propagare: vedi docstring
        return f" Repertorio non estratto ({type(e).__name__})."


def apply(game_dir):
    """Applica la patch. Ritorna (ok, messaggio)."""
    st = state(game_dir)
    if st == STATE_MISSING:
        return False, "Assembly-CSharp.dll non trovata: controlla il percorso del gioco."
    if st == STATE_PATCHED:
        # gia' patchato non vuol dire gia' pronto: il repertorio potrebbe
        # mancare (prima installazione del tool su un gioco gia' patchato, o
        # cartella dati utente ripulita). Riapplicare la patch e' il gesto
        # naturale con cui l'utente prova a rimettere le cose a posto.
        return True, "La patch era gia' applicata." + _ensure_vocabulary(game_dir)
    if st == STATE_UNKNOWN:
        return False, ("I byte da modificare non corrispondono a quelli attesi: questa build del "
                       "gioco e' diversa da quella su cui la patch e' stata calcolata. "
                       "Non tocco nulla.")
    if is_game_running():
        return False, "BoxVR e' in esecuzione: chiudilo prima di applicare la patch."
    p = dll_path(game_dir)
    bak = f"{p}.backup_{time.strftime('%Y%m%d_%H%M%S')}"
    try:
        shutil.copy2(p, bak)
        with open(p, 'r+b') as f:
            f.seek(PATCH_OFFSET)
            f.write(PATCHED_BYTES)
    except OSError as e:
        return False, f"Scrittura non riuscita ({e}). Serve forse avviare come amministratore?"
    return True, (f"Patch applicata. Backup: {os.path.basename(bak)}."
                  + _ensure_vocabulary(game_dir))


def revert(game_dir):
    """Ripristina dal backup piu' recente; se non ce ne sono, riscrive i byte
    originali (che conosciamo comunque)."""
    p = dll_path(game_dir)
    if not p or not os.path.isfile(p):
        return False, "Assembly-CSharp.dll non trovata."
    if is_game_running():
        return False, "BoxVR e' in esecuzione: chiudilo prima di ripristinare."
    baks = sorted(glob.glob(p + ".backup_*"))
    try:
        if baks:
            shutil.copy2(baks[-1], p)
            return True, f"Ripristinato da {os.path.basename(baks[-1])}"
        with open(p, 'r+b') as f:
            f.seek(PATCH_OFFSET)
            f.write(ORIGINAL_BYTES)
        return True, "Ripristinati i byte originali (nessun backup trovato)."
    except OSError as e:
        return False, f"Ripristino non riuscito ({e})."


def _steam_roots():
    """Tutte le radici di libreria Steam plausibili, in ordine di fiducia.

    Tre fonti invece di una. La prima versione leggeva solo
    libraryfolders.vdf da due percorsi cablati: bastava che Steam fosse
    installato altrove, o che quel file non ci fosse ancora, per non trovare
    piu' niente - e il chiamante non aveva modo di distinguere "gioco
    assente" da "non ho saputo guardare".
    """
    import re
    radici = []

    def aggiungi(p):
        if p and p not in radici:
            radici.append(p)

    # 1. dove Steam dice di essere, secondo il registro
    try:
        import winreg
        for hive, chiave, valore in (
                (winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam', 'InstallPath')):
            try:
                with winreg.OpenKey(hive, chiave) as k:
                    aggiungi(os.path.normpath(winreg.QueryValueEx(k, valore)[0]))
            except OSError:
                continue
    except ImportError:
        pass

    # 2. i percorsi predefiniti, anche se il registro non ha detto niente
    for base in (os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
                 os.environ.get('ProgramFiles', r'C:\Program Files')):
        aggiungi(os.path.join(base, 'Steam'))

    # 3. le librerie aggiuntive dichiarate da ogni Steam trovato sopra
    for base in list(radici):
        vdf = os.path.join(base, 'steamapps', 'libraryfolders.vdf')
        if not os.path.isfile(vdf):
            continue
        try:
            with open(vdf, encoding='utf-8', errors='ignore') as f:
                testo = f.read()
        except OSError:
            continue
        for m in re.finditer(r'"path"\s+"([^"]+)"', testo):
            aggiungi(os.path.normpath(m.group(1).replace('\\\\', '\\')))
    return radici


def autodetect_game_dir():
    """Proposta di percorso da precompilare nel selettore. Guarda le librerie
    di Steam (registro, percorsi predefiniti, libraryfolders.vdf); per le
    edizioni Oculus/Viveport non trovera' nulla, ed e' proprio per questo che
    la scelta manuale resta."""
    for r in _steam_roots():
        cand = os.path.join(r, 'steamapps', 'common', 'BOXVR')
        if looks_like_game_dir(cand):
            return cand
    return None


def find_all_installs():
    """Trova OGNI installazione di BoxVR sulla macchina, non solo quella che
    autodetect_game_dir() propone (che guarda solo le librerie Steam
    dichiarate in libraryfolders.vdf - su questa macchina ne esistono altre
    due fuori da li'). Nato da un incidente reale il 2026-08-24: una diagnosi
    e' stata fatta guardando la cartella sbagliata (D:\\Games\\BOXVR, non
    patchata) mentre l'utente stava giocando su quella giusta
    (E:\\SteamLibrary\\...), perche' non esisteva un modo per elencarle TUTTE
    e vedere a colpo d'occhio quale fosse quella patchata.

    Ritorna una lista di dict {'path', 'state'}, una voce per installazione
    trovata (stato da `state()`: 'patched'/'original'/'unknown'/'missing').
    Lento (cammina il filesystem fino a profondita' 5 sotto ogni cartella di
    primo livello di ogni drive) - va usato come controllo esplicito prima di
    generare/installare qualcosa di reale, non in un ciclo caldo o all'avvio
    dell'app."""
    import string

    candidates = set()
    auto = autodetect_game_dir()
    if auto:
        candidates.add(os.path.normpath(auto))

    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if not os.path.isdir(drive):
            continue
        try:
            top_entries = os.listdir(drive)
        except OSError:
            continue
        for entry in top_entries:
            top = os.path.join(drive, entry)
            if not os.path.isdir(top):
                continue
            for depth_root, dirs, _files in os.walk(top):
                rel = os.path.relpath(depth_root, top)
                depth = 0 if rel == '.' else rel.count(os.sep) + 1
                if depth >= 5:
                    dirs[:] = []
                    continue
                if 'BoxVR_Data' in dirs:
                    if looks_like_game_dir(depth_root):
                        candidates.add(os.path.normpath(depth_root))
                    dirs[:] = [d for d in dirs if d != 'BoxVR_Data']

    return [{'path': p, 'state': state(p)} for p in sorted(candidates)]


def find_the_patched_install():
    """Fra tutte le installazioni trovate, quella (e deve essere UNA sola)
    con la patch attiva - il target giusto per qualunque generazione/test
    reale. Ritorna (path, warning): `path` e' None se il risultato non e'
    univoco (zero o piu' di una patchata), nel qual caso `warning` spiega
    perche' e va mostrato/loggato invece di indovinare da soli."""
    installs = find_all_installs()
    patched = [i for i in installs if i['state'] == STATE_PATCHED]
    if len(patched) == 1:
        return patched[0]['path'], None
    if not installs:
        return None, "Nessuna installazione di BoxVR trovata sulla macchina."
    if not patched:
        return None, (f"Trovate {len(installs)} installazioni, NESSUNA patchata: "
                       + "; ".join(f"{i['path']} ({i['state']})" for i in installs))
    return None, (f"Trovate {len(patched)} installazioni patchate contemporaneamente, "
                   "ambiguo quale sia quella giocata: "
                   + "; ".join(i['path'] for i in patched))
