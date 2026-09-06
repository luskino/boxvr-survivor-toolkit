"""Test di read_correct_item (boxvr_fixer.py) e read_generate_item
(boxvr_generator.py): la decisione "e' un file valido? con quale nome va
mostrato in lista?" tirata fuori da SongBrowserPanel._add_correct_item/
_add_generate_item - prima verificabile solo trascinando un file nella
finestra vera.
"""
import json
import os
import sys
import tempfile

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boxvr_fixer as bf
import boxvr_generator as bg

ok = fail = 0


def check(desc, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK   {desc}")
    else:
        fail += 1
        print(f"  FAIL {desc}")


print("read_correct_item")
with tempfile.TemporaryDirectory() as tmp:
    tid = "abc123"
    txt = os.path.join(tmp, f"{tid}.trackdata.txt")
    wav = os.path.join(tmp, f"{tid}.wav")

    # senza il wav: non valido, a prescindere dal contenuto del txt
    with open(txt, 'w', encoding='utf-8') as f:
        json.dump({"originalTrackName": "Brano", "originalArtist": "Autore", "bpm": 128.0}, f)
    check("manca il wav -> None (non valido)", bf.read_correct_item(txt) is None)

    # con il wav: valido, e legge nome/artista/bpm dal JSON
    open(wav, 'w').close()
    item = bf.read_correct_item(txt)
    check("con il wav -> valido", item is not None)
    check("key = track id derivato dal nome file", item['key'] == tid)
    check("legge il nome", item['name'] == "Brano")
    check("legge l'artista", item['artist'] == "Autore")
    check("formatta il bpm (128.0 -> '128')", item['bpm_text'] == "128")
    check("wav_path punta al file giusto", item['wav_path'] == wav)

    # JSON senza quei campi -> ripiega su segnaposto, ma resta valido
    tid2 = "def456"
    txt2 = os.path.join(tmp, f"{tid2}.trackdata.txt")
    wav2 = os.path.join(tmp, f"{tid2}.wav")
    with open(txt2, 'w', encoding='utf-8') as f:
        json.dump({}, f)
    open(wav2, 'w').close()
    item2 = bf.read_correct_item(txt2)
    check("campi mancanti -> nome ripiega sul track id", item2['name'] == tid2)
    check("campi mancanti -> artista '?'", item2['artist'] == '?')
    check("campi mancanti -> bpm '?'", item2['bpm_text'] == '?')

    # JSON illeggibile (corrotto) -> ripiega comunque, resta valido (il file
    # potrebbe essere proprio quello da correggere, non deve sparire)
    tid3 = "ghi789"
    txt3 = os.path.join(tmp, f"{tid3}.trackdata.txt")
    wav3 = os.path.join(tmp, f"{tid3}.wav")
    with open(txt3, 'w', encoding='utf-8') as f:
        f.write("{ non e' json valido")
    open(wav3, 'w').close()
    item3 = bf.read_correct_item(txt3)
    check("JSON corrotto -> comunque valido (non None)", item3 is not None)
    check("JSON corrotto -> ripiega sul track id come nome", item3['name'] == tid3)

    # bpm come stringa (non numero) -> trattato come mancante, non un errore
    tid4 = "jkl012"
    txt4 = os.path.join(tmp, f"{tid4}.trackdata.txt")
    wav4 = os.path.join(tmp, f"{tid4}.wav")
    with open(txt4, 'w', encoding='utf-8') as f:
        json.dump({"bpm": "non un numero"}, f)
    open(wav4, 'w').close()
    item4 = bf.read_correct_item(txt4)
    check("bpm non numerico -> bpm_text '?' (non solleva)", item4['bpm_text'] == '?')

print("\nread_generate_item")
with tempfile.TemporaryDirectory() as tmp:
    # nessun tag ID3 (file non e' un mp3 vero) -> ripiega sul nome del file
    fake = os.path.join(tmp, "La Mia Canzone.mp3")
    open(fake, 'w').close()
    item = bg.read_generate_item(fake)
    check("key = percorso del file", item['key'] == fake)
    check("audio_path = percorso del file", item['audio_path'] == fake)
    check("senza tag leggibili -> nome dal filename", item['name'] == "La Mia Canzone")
    check("senza tag leggibili -> artista '?'", item['artist'] == '?')
    check("non solleva mai (nessun requisito di validita')", item is not None)

print(f"\n{'=' * 50}\n{ok} passati, {fail} falliti")
sys.exit(1 if fail else 0)
