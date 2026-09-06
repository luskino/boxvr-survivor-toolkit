"""Test di boxvr_install: gira su cartelle temporanee, non tocca MAI la
libreria vera del gioco. E' il motivo per cui questa logica e' stata tirata
fuori dalla GUI - prima non era verificabile senza aprire una finestra.
"""
import os
import shutil
import sys
import tempfile

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import boxvr_install as bi

ok = fail = 0


def check(desc, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  OK   {desc}")
    else:
        fail += 1
        print(f"  FAIL {desc}")


def make_src(tmp, tids):
    src = os.path.join(tmp, 'out')
    os.makedirs(src, exist_ok=True)
    for tid in tids:
        for suf in ('.trackdata.txt', '.wav', '.wdef.txt'):
            with open(os.path.join(src, tid + suf), 'w', encoding='utf-8') as f:
                f.write('{"originalTrackName": "Brano %s", "originalArtist": "Tizio"}' % tid
                        if suf == '.trackdata.txt' else 'x')
    return src


print("scan_generated")
with tempfile.TemporaryDirectory() as tmp:
    src = make_src(tmp, ['aaa', 'bbb'])
    data, wdef, tids = bi.scan_generated(src)
    check("trova 4 file dati (2 trackdata + 2 wav)", len(data) == 4)
    check("trova 2 wdef", len(wdef) == 2)
    check("deduce gli id giusti", tids == ['aaa', 'bbb'])
    check("cartella inesistente -> vuoto, non errore",
          bi.scan_generated(os.path.join(tmp, 'nope')) == ([], [], []))
    check("cartella vuota -> vuoto", bi.scan_generated(tmp) == ([], [], []))

print("\ntrack_display_name")
with tempfile.TemporaryDirectory() as tmp:
    src = make_src(tmp, ['aaa'])
    check("legge nome e artista", bi.track_display_name(src, 'aaa') == "Brano aaa — Tizio")
    check("id sconosciuto -> ripiega sull'id", bi.track_display_name(src, 'zzz') == 'zzz')

print("\nfind_conflicts")
with tempfile.TemporaryDirectory() as tmp:
    src = make_src(tmp, ['aaa', 'bbb', 'ccc'])
    td = os.path.join(tmp, 'TrackData'); os.makedirs(td)
    tdef = os.path.join(tmp, 'TrackDefinitions'); os.makedirs(tdef)
    # 'aaa' gia' installato interamente, 'bbb' solo il wav, 'ccc' assente
    for suf in ('.trackdata.txt', '.wav'):
        shutil.copy2(os.path.join(src, 'aaa' + suf), os.path.join(td, 'aaa' + suf))
    shutil.copy2(os.path.join(src, 'bbb.wav'), os.path.join(td, 'bbb.wav'))
    conf = bi.find_conflicts(['aaa', 'bbb', 'ccc'], td, tdef)
    check("rileva conflitto completo (aaa)", 'aaa' in conf)
    check("rileva conflitto PARZIALE, solo il wav (bbb)", 'bbb' in conf)
    check("non segnala un id assente (ccc)", 'ccc' not in conf)

print("\ninstall_files - percorso normale")
with tempfile.TemporaryDirectory() as tmp:
    src = make_src(tmp, ['aaa'])
    td = os.path.join(tmp, 'TrackData')
    tdef = os.path.join(tmp, 'TrackDefinitions')
    data, wdef, _ = bi.scan_generated(src)
    n = bi.install_files(src, data, wdef, td, tdef)
    check("copia tutti e 3 i file", n == 3)
    check("trackdata a destinazione", os.path.isfile(os.path.join(td, 'aaa.trackdata.txt')))
    check("wav a destinazione", os.path.isfile(os.path.join(td, 'aaa.wav')))
    check("wdef nella cartella giusta", os.path.isfile(os.path.join(tdef, 'aaa.wdef.txt')))
    check("crea le cartelle se mancanti", os.path.isdir(td) and os.path.isdir(tdef))

print("\ninstall_files - ROLLBACK su copia fallita a meta'")
with tempfile.TemporaryDirectory() as tmp:
    src = make_src(tmp, ['aaa'])
    td = os.path.join(tmp, 'TrackData')
    tdef = os.path.join(tmp, 'TrackDefinitions')
    data, wdef, _ = bi.scan_generated(src)
    # sabota la seconda copia
    real_copy = shutil.copy2
    calls = {'n': 0}

    def flaky(s, d, *a, **k):
        calls['n'] += 1
        if calls['n'] == 2:
            raise OSError("disco pieno (simulato)")
        return real_copy(s, d, *a, **k)

    bi.shutil.copy2 = flaky
    try:
        bi.install_files(src, data, wdef, td, tdef)
        check("solleva l'errore invece di ingoiarlo", False)
    except OSError:
        check("solleva l'errore invece di ingoiarlo", True)
    finally:
        bi.shutil.copy2 = real_copy
    leftovers = (os.listdir(td) if os.path.isdir(td) else []) + \
                (os.listdir(tdef) if os.path.isdir(tdef) else [])
    check("NESSUN file nuovo lasciato a meta' nella libreria", leftovers == [])

print("\ninstall_files - un file SOVRASCRITTO non viene rimosso dal rollback")
with tempfile.TemporaryDirectory() as tmp:
    src = make_src(tmp, ['aaa'])
    td = os.path.join(tmp, 'TrackData'); os.makedirs(td)
    tdef = os.path.join(tmp, 'TrackDefinitions'); os.makedirs(tdef)
    # esisteva gia': l'utente ha approvato la sovrascrittura, non abbiamo backup
    with open(os.path.join(td, 'aaa.trackdata.txt'), 'w') as f:
        f.write('preesistente')
    data, wdef, _ = bi.scan_generated(src)
    real_copy = shutil.copy2
    calls = {'n': 0}

    def flaky2(s, d, *a, **k):
        calls['n'] += 1
        if calls['n'] == 2:
            raise OSError("errore simulato")
        return real_copy(s, d, *a, **k)

    bi.shutil.copy2 = flaky2
    try:
        bi.install_files(src, data, wdef, td, tdef)
    except OSError:
        pass
    finally:
        bi.shutil.copy2 = real_copy
    check("il file preesistente e' ancora li'", os.path.isfile(os.path.join(td, 'aaa.trackdata.txt')))

print("\nadd_to_playlist - crea nuova")
with tempfile.TemporaryDirectory() as tmp:
    src = make_src(tmp, ['aaa', 'bbb'])
    with open(os.path.join(src, 'aaa.trackdata.txt'), 'w', encoding='utf-8') as f:
        f.write('{"duration": 180.0}')
    with open(os.path.join(src, 'bbb.trackdata.txt'), 'w', encoding='utf-8') as f:
        f.write('{"duration": 200.0}')
    pl_path = os.path.join(tmp, 'Playlists', 'WorkoutPlaylists', 'BoxVR', 'Test.workoutplaylist.txt')
    pl = bi.add_to_playlist(pl_path, ['aaa', 'bbb'], 'Test', src)
    check("crea il file su disco (incluse le cartelle mancanti)", os.path.isfile(pl_path))
    check("2 brani in playlist", len(pl['songs']) == 2)
    check("durata totale corretta (180+200)", pl['definition']['duration'] == 380.0)
    check("actionList vuota (brano CORRETTO, non generato)",
          pl['songs'][0]['serialisedActionList']['actionList'] == [])
    check("nome nel definition", pl['definition']['workoutName'] == 'Test')

print("\nadd_to_playlist - aggiunge a playlist esistente senza toccare le voci gia' presenti")
with tempfile.TemporaryDirectory() as tmp:
    src1 = make_src(tmp, ['aaa'])
    with open(os.path.join(src1, 'aaa.trackdata.txt'), 'w', encoding='utf-8') as f:
        f.write('{"duration": 100.0}')
    pl_path = os.path.join(tmp, 'Test.workoutplaylist.txt')
    bi.add_to_playlist(pl_path, ['aaa'], 'Test', src1)

    # seconda sessione: 'aaa' e' ora un brano "gia' in playlist" da rileggere
    # dalla libreria live (trackdata_dir), non dalla cartella di output nuova
    live_td = os.path.join(tmp, 'live_trackdata')
    os.makedirs(live_td)
    with open(os.path.join(live_td, 'aaa.trackdata.txt'), 'w', encoding='utf-8') as f:
        f.write('{"duration": 100.0}')
    src2 = make_src(tmp, ['ccc'])
    with open(os.path.join(src2, 'ccc.trackdata.txt'), 'w', encoding='utf-8') as f:
        f.write('{"duration": 50.0}')
    pl = bi.add_to_playlist(pl_path, ['ccc'], 'Test', src2, trackdata_dir=live_td)
    check("aaa preesistente resta in playlist", any(s['trackDataName'] == 'aaa' for s in pl['songs']))
    check("ccc aggiunto", any(s['trackDataName'] == 'ccc' for s in pl['songs']))
    check("2 brani totali, non duplicati", len(pl['songs']) == 2)
    check("durata somma aaa (dalla libreria) + ccc (dalla nuova cartella)",
          pl['definition']['duration'] == 150.0)

    # rilancio con lo stesso id 'ccc': non deve duplicarsi
    pl2 = bi.add_to_playlist(pl_path, ['ccc'], 'Test', src2, trackdata_dir=live_td)
    check("stesso id ri-aggiunto -> nessun duplicato", len(pl2['songs']) == 2)

print("\ntrack_duration")
with tempfile.TemporaryDirectory() as tmp:
    src = make_src(tmp, ['aaa'])
    with open(os.path.join(src, 'aaa.trackdata.txt'), 'w', encoding='utf-8') as f:
        f.write('{"duration": 123.5}')
    check("legge la durata", bi.track_duration(src, 'aaa') == 123.5)
    check("id sconosciuto -> 0.0, non errore", bi.track_duration(src, 'zzz') == 0.0)

print("\nboxvr_dirs")
td, tdef, pl = bi.boxvr_dirs()
check("TrackData nel percorso giusto", td.endswith(os.path.join('Playlists', 'TrackData')))
check("TrackDefinitions nel percorso giusto", tdef.endswith(os.path.join('Playlists', 'TrackDefinitions')))
check("playlist nella sottocartella BoxVR", pl.endswith(os.path.join('WorkoutPlaylists', 'BoxVR')))
check("percorso espanso (niente %USERPROFILE% letterale)", '%' not in td)

print(f"\n{'=' * 50}\n{ok} passati, {fail} falliti")
sys.exit(1 if fail else 0)
