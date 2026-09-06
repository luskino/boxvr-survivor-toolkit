"""Test dell'estrazione del repertorio dal gioco dell'utente e del suo aggancio
all'installazione della patch (25/08).

Verifica soprattutto le cose che romperebbero in silenzio: l'asset sbagliato
scelto fra i due presenti, la scrittura in una cartella temporanea che sparisce,
e un errore dell'estrazione che fa fallire la patch (che deve invece riuscire
comunque)."""
import json
import os
import shutil
import sys
import tempfile

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
# la radice del progetto: questo file sta in tests/
RADICE_PROGETTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boxvr_extract as ex
import boxvr_choreo as ch
import boxvr_patch as patch

GAME = r"E:\SteamLibrary\steamapps\common\BOXVR"
ATTESO = os.path.join(RADICE_PROGETTO, 'data', 'training_sequences.json')

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


print("1. Estrazione dal gioco reale")
data, msg = ex.extract_training_sequences(GAME)
check("estrae qualcosa", data is not None)
check(f"sceglie l'asset Training, non Survival ({msg[:60]}...)",
      data is not None and 'Training' in msg)
atteso = json.load(open(ATTESO, encoding='utf-8'))
check("il contenuto e' identico al file finora spedito a mano", data == atteso)
check("ha 7 liste e 47 pattern",
      data is not None and len(data['sequenceLists']) == 7
      and sum(len(l.get('sequenceList', [])) for l in data['sequenceLists']) == 47)

print("\n2. Accetta sia la radice del gioco sia BoxVR_Data")
d2, _ = ex.extract_training_sequences(os.path.join(GAME, 'BoxVR_Data'))
check("stesso risultato passando BoxVR_Data", d2 == data)

print("\n3. Errori previsti: messaggio utile, nessuna eccezione")
for path, atteso_txt in ((r"C:\NonEsiste", 'non trovato'),
                         (tempfile.gettempdir(), 'non trovato')):
    d3, m3 = ex.extract_training_sequences(path)
    check(f"{path[:28]:30s} -> None + messaggio ('{m3[:34]}...')",
          d3 is None and isinstance(m3, str) and len(m3) > 10)

print("\n4. Scrittura nella cartella dati utente (non in una temporanea)")
dest = ex.user_data_path()
check("il percorso e' sotto APPDATA, non sotto _MEIPASS/temp",
      'BoxVR Level Fixer' in dest and tempfile.gettempdir().lower() not in dest.lower())
tmp_dest = os.path.join(tempfile.mkdtemp(), 'sub', 'training_sequences.json')
ok, msg = ex.write_training_sequences(GAME, tmp_dest)
check("scrive creando le cartelle mancanti", ok and os.path.isfile(tmp_dest))
if os.path.isfile(tmp_dest):
    check("il file scritto si rilegge identico",
          json.load(open(tmp_dest, encoding='utf-8')) == atteso)
    shutil.rmtree(os.path.dirname(os.path.dirname(tmp_dest)), ignore_errors=True)

print("\n5. load_vocabulary trova il repertorio e da' un errore chiaro se manca")
vocab = ch.load_vocabulary()
check(f"carica il repertorio ({len(vocab)} livelli di intensita')", len(vocab) > 0)
try:
    ch.load_vocabulary(os.path.join(tempfile.gettempdir(), 'non_esiste_affatto.json'))
    check("solleva VocabularyMissing quando il file manca", False)
except ch.VocabularyMissing as e:
    check("solleva VocabularyMissing con istruzioni per l'utente",
          'patch' in str(e).lower())
except FileNotFoundError:
    check("solleva VocabularyMissing (non un FileNotFoundError generico)", False)

print("\n6. L'estrazione non puo' far fallire la patch")
orig = ex.write_training_sequences


def esplode(*a, **k):
    raise RuntimeError("guasto simulato")


ex.write_training_sequences = esplode
ex_avail = ex.is_available
ex.is_available = lambda: False
try:
    nota = patch._ensure_vocabulary(GAME)
    check(f"un guasto dell'estrazione torna una nota, non un'eccezione ('{nota.strip()[:40]}')",
          isinstance(nota, str))
finally:
    ex.write_training_sequences = orig
    ex.is_available = ex_avail

check("stato della patch invariato (nessuna scrittura sulla DLL nei test)",
      patch.state(GAME) in (patch.STATE_PATCHED, patch.STATE_ORIGINAL))

print("\n" + "=" * 56)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
