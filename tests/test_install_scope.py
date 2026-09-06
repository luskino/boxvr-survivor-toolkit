"""Verifica dei due bug segnalati dall'utente il 25/08:
1. 'Installa' pescava tutta la cartella 'generati', non solo i brani appena
   costruiti - corretto con files_for_track_ids + generate_songs/
   process_songs_with_presets che ora ritornano 'track_ids'.
2. La playlist creata dal bottone Installa poteva finire muta - ora riusa la
   coreografia GIA' VERA scritta da generate_songs (action_lists_from_playlist),
   con .actionlist.json come ripiego.
"""
import json
import os
import shutil
import sys
import tempfile

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brano_di_prova import audio_di_prova
import boxvr_generator as gen
import boxvr_install as inst

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


tmp = tempfile.mkdtemp()

print("1. generate_songs ritorna SOLO gli id di questa chiamata")
TID_VECCHIO = 'a' * 32
for suf, content in (('.trackdata.txt', json.dumps({'duration': 10.0})),
                     ('.wav', 'x'), ('.wdef.txt', json.dumps({'tagLibTitle': 'vecchio'}))):
    with open(os.path.join(tmp, TID_VECCHIO + suf), 'w', encoding='utf-8') as f:
        f.write(content)
mp3 = audio_di_prova('Riff MoP diretti.wav')
if not os.path.isfile(mp3):
    mp3 = audio_di_prova('Master Of Puppets.mp3')
items = [{'audio_path': mp3, 'ratio': 0.5, 'density': 1.0}]
result = gen.generate_songs(items, tmp, dry_run=False, playlist_name="ZZ_test_scope")
check("track_ids presente nel risultato", 'track_ids' in result)
check(f"contiene solo il brano appena generato ({result.get('track_ids')})",
      len(result.get('track_ids', [])) == 1 and TID_VECCHIO not in result['track_ids'])
nuovo_tid = result['track_ids'][0]

print("\n2. files_for_track_ids prende SOLO i track_ids passati, non tutta la cartella")
data_files, wdef_files = inst.files_for_track_ids(tmp, result['track_ids'])
tutti_gli_id = {f.split('.')[0] for f in data_files + wdef_files}
check(f"il vecchio brano ({TID_VECCHIO[:8]}...) NON e' incluso", TID_VECCHIO not in tutti_gli_id)
check(f"il nuovo brano E' incluso", nuovo_tid in tutti_gli_id)
check("scan_generated (il vecchio comportamento) lo includerebbe invece",
      TID_VECCHIO in inst.scan_generated(tmp)[2])

print("\n3. action_lists_from_playlist legge la coreografia VERA gia' scritta")
al = inst.action_lists_from_playlist(result['playlist_path'])
check(f"contiene il brano generato", nuovo_tid in al)
check(f"con azioni non vuote ({len(al.get(nuovo_tid, {}).get('actionList', []))} azioni)",
      bool(al.get(nuovo_tid, {}).get('actionList')))

print("\n4. add_to_playlist con action_lists produce una playlist NON muta")
pl_path = os.path.join(tmp, 'ZZ_test_finale.workoutplaylist.txt')
pl = inst.add_to_playlist(pl_path, result['track_ids'], 'ZZ_test_finale', tmp, trackdata_dir=tmp,
                          action_lists=al)
song = next(s for s in pl['songs'] if s['trackDataName'] == nuovo_tid)
check("la playlist creata dal bottone Installa ha coreografia vera",
      bool(song['serialisedActionList'].get('actionList')))
check("uguale a quella scritta dalla generazione (stessa fonte, non ricostruita)",
      song['serialisedActionList'] == al[nuovo_tid])

print("\n5. senza action_lists, ripiega su .actionlist.json (comportamento di ieri)")
pl2_path = os.path.join(tmp, 'ZZ_test_ripiego.workoutplaylist.txt')
pl2 = inst.add_to_playlist(pl2_path, result['track_ids'], 'ZZ_test_ripiego', tmp, trackdata_dir=tmp)
song2 = next(s for s in pl2['songs'] if s['trackDataName'] == nuovo_tid)
check("ripiego su .actionlist.json funziona ancora ed e' non vuoto",
      bool(song2['serialisedActionList'].get('actionList')))

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + "=" * 56)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
