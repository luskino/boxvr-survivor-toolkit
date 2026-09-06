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

"""Patch chirurgica ad Assembly-CSharp.dll di BoxVR: fa smettere al gioco di
rigenerare la coreografia procedurale a ogni avvio di una playlist utente,
cosi' usa la lista di azioni scritta da noi nella playlist stessa.

CONTESTO (vedi [[boxvr-internals]]). In GameStateTraining.OnEnableGameState:

    List<MusicAction> lista = null;
    if (lista != null) goto PLAY;                  // condizione morta nel binario
    MusicActionFactory.instance.GenerateActionSequence(...);   // <-- SI AZZERA QUESTA
    lista = playlist.songs[i].musicActionList;     // rilegge da li'
  PLAY:
    sequencer.PlaySequence(lista);

GenerateActionSequence SCRIVE dentro songs[i].musicActionList, e la riga dopo la
rilegge. Neutralizzando la sola chiamata, quella riga legge invece la lista che
WorkoutPlaylist.LoadFromJSON ha gia' deserializzato dal nostro file.

Perche' e' sicuro:
  - si sostituiscono 42 byte con NOP: stessa lunghezza, nessun offset si sposta;
  - il blocco contiene SOLO il caricamento degli argomenti e la callvirt a un
    metodo void, quindi l'effetto netto sullo stack e' zero prima e dopo;
  - viene fatto un backup con timestamp, e "Verifica integrita' file" di Steam
    ripristina comunque l'originale in qualunque momento.

Uso:  python patch_boxvr.py            (applica)
      python patch_boxvr.py --revert   (ripristina dal backup piu' recente)
      python patch_boxvr.py --check    (dice solo lo stato attuale)
"""
import os, sys, shutil, time, glob

# Il percorso del gioco NON e' cablato: era quello della macchina di chi ha
# scritto lo script, e su qualunque altro computer puntava nel vuoto. Si
# riusa l'autorilevamento gia' presente in boxvr_patch.py (legge le librerie
# Steam), e si puo' comunque passare la cartella come argomento.
def _trova_dll():
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[-1]):
        radice = sys.argv[-1]
    else:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import boxvr_patch
        radice = boxvr_patch.autodetect_game_dir()
    if not radice:
        print("BoxVR non trovato. Passa la cartella del gioco come argomento:")
        print("   python patch_boxvr.py \"C:\\...\\common\\BOXVR\"")
        sys.exit(2)
    return os.path.join(radice, 'BoxVR_Data', 'Managed', 'Assembly-CSharp.dll')


DLL = _trova_dll()
OFFSET = 0xFE47
LENGTH = 42
ORIGINAL = bytes.fromhex(
    "7e f1 40 00 04 16 02 7b 91 03 00 04 28 6f 4f 00 06 6f 73 4f 00 06 "
    "7b a0 40 00 04 7b c3 40 00 04 7b c8 40 00 04 6f f2 4f 00 06".replace(' ', '')
)
PATCHED = b"\x00" * LENGTH
assert len(ORIGINAL) == LENGTH


def read_block():
    with open(DLL, 'rb') as f:
        f.seek(OFFSET)
        return f.read(LENGTH)


def state():
    cur = read_block()
    if cur == ORIGINAL:
        return 'originale'
    if cur == PATCHED:
        return 'patchato'
    return 'sconosciuto'


def apply_patch():
    st = state()
    if st == 'patchato':
        print("Gia' patchato, non faccio nulla.")
        return
    if st != 'originale':
        print("ATTENZIONE: i byte a quell'offset non corrispondono ne' all'originale "
              "ne' alla patch. Il gioco potrebbe essere di una versione diversa. Interrompo.")
        print("   trovato:", read_block().hex(' '))
        return
    bak = DLL + f".backup_{time.strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(DLL, bak)
    with open(DLL, 'r+b') as f:
        f.seek(OFFSET)
        f.write(PATCHED)
    print(f"Patch applicata. Backup: {os.path.basename(bak)}")
    print("Ora le playlist con azioni scritte da noi dovrebbero essere eseguite tali e quali.")


def revert():
    baks = sorted(glob.glob(DLL + ".backup_*"))
    if not baks:
        print("Nessun backup trovato. Usa 'Verifica integrita' dei file' su Steam.")
        return
    shutil.copy2(baks[-1], DLL)
    print(f"Ripristinato da {os.path.basename(baks[-1])}")


if __name__ == '__main__':
    if not os.path.isfile(DLL):
        raise SystemExit(f"DLL non trovata: {DLL}")
    arg = sys.argv[1] if len(sys.argv) > 1 else ''
    if arg == '--revert':
        revert()
    elif arg == '--check':
        print("stato attuale:", state())
    else:
        apply_patch()
