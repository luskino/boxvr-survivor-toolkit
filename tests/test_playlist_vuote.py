"""Verifica del bug delle playlist con coreografia vuota (25/08).

Sintomo reale osservato sul PC dell'utente: nessuna playlist visibile in gioco,
e nel log del gioco NullReferenceException in PlaylistManagerView.SetPlaylistPage.
Causa: la playlist "Media" aveva 13 brani con actionList vuote; a patch attiva
il gioco non le rigenera e la schermata muore prima di disegnare la lista -
quindi spariscono anche le playlist sane.
"""
import json
import os
import shutil
import sys
import tempfile

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
# la radice del progetto: questo file sta in tests/
RADICE_PROGETTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
gen_dir = os.path.join(tmp, 'generati')
os.makedirs(gen_dir)
TID_GEN, TID_COR = 'a' * 32, 'b' * 32

# un brano GENERATO: ha la coreografia salvata accanto
azioni = {'actionList': [{'musicActionType': 0, 'musicActionJSON': '{"startTime":1.0}'}]}
with open(os.path.join(gen_dir, f'{TID_GEN}.actionlist.json'), 'w', encoding='utf-8') as f:
    json.dump(azioni, f)
for tid in (TID_GEN, TID_COR):
    with open(os.path.join(gen_dir, f'{tid}.trackdata.txt'), 'w', encoding='utf-8') as f:
        json.dump({'duration': 100.0, 'trackId': {'trackId': tid}}, f)

print("1. add_to_playlist recupera la coreografia dei brani generati")
pl_path = os.path.join(tmp, 'Prova.workoutplaylist.txt')
pl = inst.add_to_playlist(pl_path, [TID_GEN], 'Prova', gen_dir, trackdata_dir=gen_dir)
song = next(s for s in pl['songs'] if s['trackDataName'] == TID_GEN)
check("il brano generato NON ha la lista vuota",
      bool(song['serialisedActionList'].get('actionList')))

print("\n2. Un brano corretto (senza file di coreografia) resta con lista vuota")
pl = inst.add_to_playlist(pl_path, [TID_COR], 'Prova', gen_dir, trackdata_dir=gen_dir)
song = next(s for s in pl['songs'] if s['trackDataName'] == TID_COR)
check("comportamento invariato per i brani corretti",
      song['serialisedActionList'] == {'actionList': []})

print("\n3. Un file di coreografia illeggibile non fa fallire l'installazione")
TID_ROTTO = 'c' * 32
with open(os.path.join(gen_dir, f'{TID_ROTTO}.actionlist.json'), 'w', encoding='utf-8') as f:
    f.write('{ questo non e json')
with open(os.path.join(gen_dir, f'{TID_ROTTO}.trackdata.txt'), 'w', encoding='utf-8') as f:
    json.dump({'duration': 50.0, 'trackId': {'trackId': TID_ROTTO}}, f)
try:
    pl = inst.add_to_playlist(pl_path, [TID_ROTTO], 'Prova', gen_dir, trackdata_dir=gen_dir)
    song = next(s for s in pl['songs'] if s['trackDataName'] == TID_ROTTO)
    check("ripiega sulla lista vuota senza sollevare eccezioni",
          song['serialisedActionList'] == {'actionList': []})
except Exception as e:
    check(f"ripiega sulla lista vuota senza sollevare eccezioni (invece: {e})", False)

print("\n4. playlists_without_choreography segnala le playlist a rischio")
pls = os.path.join(tmp, 'playlists')
os.makedirs(pls)
with open(os.path.join(pls, 'Sana.workoutplaylist.txt'), 'w', encoding='utf-8') as f:
    json.dump({'definition': {}, 'songs': [{'trackDataName': TID_GEN,
                                            'serialisedActionList': azioni}]}, f)
with open(os.path.join(pls, 'Vuota.workoutplaylist.txt'), 'w', encoding='utf-8') as f:
    json.dump({'definition': {}, 'songs': [{'trackDataName': TID_COR,
                                            'serialisedActionList': {'actionList': []}}]}, f)
fuori = inst.playlists_without_choreography(pls)
nomi = [f[0] for f in fuori]
check("segnala quella vuota", 'Vuota.workoutplaylist.txt' in nomi)
check("NON segnala quella sana", 'Sana.workoutplaylist.txt' not in nomi)

print("\n5. Il caso reale: la playlist archiviata 'Media' verrebbe segnalata")
media = os.path.join(RADICE_PROGETTO, 'archivio libreria gioco', 'WorkoutPlaylists', 'Media.workoutplaylist.txt')
if os.path.isfile(media):
    d = os.path.join(tmp, 'reale')
    os.makedirs(d)
    shutil.copy2(media, os.path.join(d, 'Media.workoutplaylist.txt'))
    fuori = inst.playlists_without_choreography(d)
    check(f"Media segnalata ({fuori[0][1]}/{fuori[0][2]} brani senza coreografia)"
          if fuori else "Media segnalata", bool(fuori))
else:
    print("  (Media non trovata in archivio, salto)")

shutil.rmtree(tmp, ignore_errors=True)
print("\n" + "=" * 56)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
