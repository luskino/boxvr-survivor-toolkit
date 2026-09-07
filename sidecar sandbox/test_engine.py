"""Verifica del motore prototipo della sidecar (Fase B, sandbox).

Non prova l'interazione vera (registrazione dal vivo, calibrazione audio) -
quella e' materia della Fase B1/B2 (registratore + verifica su dati reali),
non ancora costruita. Prova il MOTORE DI PIAZZAMENTO in isolamento, dati
degli istanti gia' pronti - la parte gia' scritta stanotte."""
import random
import os
import sys

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sidecar sandbox'))
from brano_di_prova import audio_di_prova
import boxvr_choreo as choreo
import engine

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


def fake_beats(bpm=120.0, n=200):
    bl = 60.0 / bpm
    return [{'_triggerTime': i * bl, '_beatLength': bl, '_beatInBar': (i % 4) + 1}
            for i in range(n)]


print("1. Piazzamento base: N istanti -> N azioni (nessun filtro applicabile)")
beats = fake_beats()
markers = [1.0, 2.5, 4.0, 6.5, 9.0]   # spazio ampio, nessuno sotto il limite fisico
out = engine.place_moves_on_markers(markers, beats, rng=random.Random(1))
check(f"produce un'azione per ogni marker (trovate {len(out)}/5)", len(out) == 5)
check("tutte le azioni sono '_exact' (mai riquantizzate)",
      all(a.get('_exact') for a in out))
check("tutte le azioni sono marcate '_sidecar'", all(a.get('_sidecar') for a in out))
check("gli startTime coincidono ESATTAMENTE con i marker dati",
      sorted(a['startTime'] for a in out) == sorted(markers))

print("\n2. Il filtro del limite fisico scarta input troppo vicini (<170ms)")
markers2 = [1.000, 1.050, 1.500]   # il secondo e' a 50ms dal primo, sotto i 170ms
out2 = engine.place_moves_on_markers(markers2, beats, rng=random.Random(1))
check(f"il secondo input (troppo vicino) sparisce, restano 2 azioni (trovate {len(out2)})",
      len(out2) == 2)
check("i due rimasti sono il primo e il terzo marker originale",
      sorted(round(a['startTime'], 3) for a in out2) == [1.0, 1.5])

print("\n3. Le mosse centrali stanno SEMPRE al centro, le laterali MAI")
markers3 = [i * 0.5 for i in range(1, 40)]   # tanti marker, spazio ampio (1 beat)
out3 = engine.place_moves_on_markers(markers3, beats, rng=random.Random(7))
centro_moves = [a for a in out3 if a['moveType'] in (choreo.MOVE_BLOCK, choreo.MOVE_SQUAT, choreo.MOVE_DODGE)]
lateral_moves = [a for a in out3 if a['moveType'] in (choreo.MOVE_JAB, choreo.MOVE_HOOK, choreo.MOVE_UPPERCUT)]
check(f"trovate sia mosse centrali ({len(centro_moves)}) che laterali ({len(lateral_moves)}) "
      "su un campione ampio", centro_moves and lateral_moves)
check("le mosse centrali sono SEMPRE su CH_CENTER",
      all(a['moveChannel'] == choreo.CH_CENTER for a in centro_moves))
check("le mosse laterali non usano MAI CH_CENTER",
      all(a['moveChannel'] != choreo.CH_CENTER for a in lateral_moves))

print("\n4. Raffica fitta di input ravvicinati -> combo VARIEGATA, non un solo tipo")
print("   (l'esempio esplicito dell'utente: 10 pressioni di fila)")
# ogni 0.3s (0.6 beat a 120bpm) - abbastanza sopra i 170ms del filtro fisico,
# ma una vera raffica rispetto alla cadenza tipica di 1 beat
markers4 = [10.0 + i * 0.3 for i in range(10)]
out4 = engine.place_moves_on_markers(markers4, beats, rng=random.Random(3))
tipi4 = set(a['moveType'] for a in out4)
check(f"la raffica produce piu' di un tipo di mossa (trovati tipi {sorted(tipi4)}, "
      "non solo un tipo ripetuto come farebbe l'alternanza fissa)",
      len(tipi4) > 1)

print("\n5. Nessuna violazione di giocabilita' nel risultato finale (rete di sicurezza)")
import bisect


def audit(actions, beats):
    grid = choreo._grid_times(beats)
    grid_index = {round(g, 6): i for i, g in enumerate(grid)}

    def steps(t):
        exact = grid_index.get(round(t, 6))
        if exact is not None:
            return exact
        i = bisect.bisect_left(grid, t)
        if i <= 0:
            return 0.0
        if i >= len(grid):
            return float(len(grid) - 1)
        lo, hi = grid[i - 1], grid[i]
        span = hi - lo
        return (i - 1) + ((t - lo) / span if span > 0 else 0.0)
    violations = []
    for i in range(len(actions) - 1):
        p, c = actions[i], actions[i + 1]
        if abs(p['startTime'] - c['startTime']) < 1e-6:
            if frozenset((p['moveType'], c['moveType'])) not in choreo.LEGAL_SIMULTANEOUS:
                violations.append(('sim', p, c))
            continue
        # La deroga dello slider: due colpi ENTRAMBI dell'utente e non
        # ostacoli possono stare vicini quanto lui ha chiesto (30/08). Non
        # e' una violazione, e' la funzione che quella deroga svolge - qui
        # si salta, come fa il programma.
        if (p.get('_sidecar') and c.get('_sidecar')
                and p['moveType'] not in choreo.OBSTACLE_MOVES
                and c['moveType'] not in choreo.OBSTACLE_MOVES):
            continue
        need = choreo._required_gap_beats(p, c)
        si, sj = steps(p['startTime']), steps(c['startTime'])
        eps = 2 * choreo.ONSET_JITTER_TOLERANCE_BEATS
        if abs(sj - si) < need * 2 - eps:
            violations.append((round((sj - si) / 2, 3), need))
    return violations


out5 = sorted(out4, key=lambda a: a['startTime'])
v = audit(out5, beats)
check(f"la raffica risultante rispetta i vincoli fisici (0 violazioni attese, trovate {len(v)})",
      not v)
v3 = audit(sorted(out3, key=lambda a: a['startTime']), beats)
check(f"anche il campione ampio del test 3 rispetta i vincoli fisici (trovate {len(v3)})",
      not v3)

print("\n6. Statistica: beatInBar=1 favorisce il centro piu' di beatInBar=2")
beats6 = fake_beats(bpm=120.0, n=4000)
markers6 = [i * 4 * 0.5 for i in range(1, 400)]   # ogni marker cade sul beat 1 (inizio battuta)
out6a = engine.place_moves_on_markers(markers6, beats6, rng=random.Random(11))
n_centro_b1 = sum(1 for a in out6a if a['moveType'] in (choreo.MOVE_BLOCK, choreo.MOVE_SQUAT, choreo.MOVE_DODGE))
markers6b = [i * 4 * 0.5 + 0.5 for i in range(1, 400)]  # ogni marker cade sul beat 2
out6b = engine.place_moves_on_markers(markers6b, beats6, rng=random.Random(11))
n_centro_b2 = sum(1 for a in out6b if a['moveType'] in (choreo.MOVE_BLOCK, choreo.MOVE_SQUAT, choreo.MOVE_DODGE))
check(f"beat 1 produce piu' mosse centrali di beat 2 su 400 marker "
      f"(beat1: {n_centro_b1}, beat2: {n_centro_b2})",
      n_centro_b1 > n_centro_b2)

print("\n7. Copertura PARZIALE (26/08, seconda meta' della notte): i marker")
print("   sono una base, non l'intero brano - il livello automatico riempie")
print("   il resto, anche vicino a marker radi")

mp3 = audio_di_prova('Baddadan (feat. IRAH, Flowdan, Trigga & Takura).mp3')
import os
if os.path.isfile(mp3):
    import boxvr_generator as gen
    analysis = gen.generate_song_analysis(mp3)

    print("\n7a. Zero marker -> identico alla generazione automatica pura")
    auto_only = choreo.build_move_actions(analysis, preset='medium')
    via_engine_empty = engine.build_choreography(analysis, [], preset='medium')
    check(f"stesso numero di azioni (auto={len(auto_only)}, sidecar-vuoto={len(via_engine_empty)})",
          len(auto_only) == len(via_engine_empty))
    check("stessi istanti (nessun marker per definizione non cambia nulla)",
          sorted(a['startTime'] for a in auto_only) == sorted(a['startTime'] for a in via_engine_empty))

    print("\n7b. Marker radi (pochi, sparsi) -> presenti E il resto del brano")
    print("    resta pieno di azioni automatiche, non solo quei pochi punti")
    sparse_markers = [10.0, 45.0, 90.0]   # 3 soli marker su un brano di 3 minuti
    # aggancio magnetico spento: qui si prova la PRESENZA dei marker radi,
    # non dove finiscono - la griglia ha la sua sezione (7h)
    out7b = engine.build_choreography(analysis, sparse_markers, preset='medium',
                                      rng=random.Random(9), aggancio_magnetico=False)
    sidecar_actions = [a for a in out7b if a.get('_sidecar')]
    auto_actions = [a for a in out7b if not a.get('_sidecar')]
    check(f"i 3 marker sono presenti (trovati {len(sidecar_actions)} '_sidecar')",
          len(sidecar_actions) == 3)
    check(f"il resto del brano e' comunque pieno di azioni automatiche "
          f"(trovate {len(auto_actions)}, non solo i 3 marker)",
          len(auto_actions) > 100)
    check("i marker restano esattamente ai loro istanti originali",
          sorted(round(a['startTime'], 3) for a in sidecar_actions) == sparse_markers)

    print("\n7c. Un marker dell'utente vince SEMPRE, anche contro un accento audio")
    print("    reale vicino (non solo contro le nostre figure iniettate)")
    onsets = sorted(analysis.get('onsets') or [])
    # sceglie un accento audio vero qualunque e piazza un marker a pochi
    # millisecondi di distanza - troppo vicino perche' entrambi sopravvivano
    real_onset = onsets[50]
    conflicting_marker = real_onset + 0.03
    out7c = engine.build_choreography(analysis, [conflicting_marker], preset='medium',
                                      rng=random.Random(3), aggancio_magnetico=False)
    sidecar_here = [a for a in out7c if a.get('_sidecar')]
    check(f"il marker dell'utente e' presente al suo istante esatto "
          f"(trovato: {[round(a['startTime'],3) for a in sidecar_here]}, atteso {round(conflicting_marker,3)})",
          len(sidecar_here) == 1 and abs(sidecar_here[0]['startTime'] - conflicting_marker) < 1e-6)
    onset_still_there = [a for a in out7c if not a.get('_sidecar')
                         and abs(a['startTime'] - real_onset) < 0.01]
    check(f"l'accento audio in conflitto NON sopravvive al suo istante originale "
          f"(trovate {len(onset_still_there)} azioni li', atteso 0)",
          len(onset_still_there) == 0)

    print("\n7d. Nessuna violazione di giocabilita' nel risultato misto (auto+sidecar)")
    v7 = audit(sorted(out7b, key=lambda a: a['startTime']), analysis['beats'])
    check(f"copertura parziale rispetta i vincoli fisici (trovate {len(v7)} violazioni)",
          not v7)

    print("\n7e. Le modalita' (27/08, richieste esplicitamente; MODE_AUTOMATIC")
    print("    rimosso il 30/08 - ridondante da quando esiste lo strumento")
    print("    top-level 'Automatica', separato dalla sidecar, per lo stesso")
    print("    identico risultato)")
    markers_7e = [10.0, 45.0, 90.0, 130.0]

    print("  MODE_HARMONIZE (default): comportamento di sempre, gia' provato sopra (7b)")
    check("MODE_HARMONIZE esplicito == default implicito",
          sorted(a['startTime'] for a in
                 engine.build_choreography(analysis, markers_7e, preset='medium',
                                           mode=engine.MODE_HARMONIZE, rng=random.Random(9))) ==
          sorted(a['startTime'] for a in
                 engine.build_choreography(analysis, markers_7e, preset='medium', rng=random.Random(9))))

    print("  MODE_MARKERS_ONLY: niente pattern automatico, MA gli ostacoli restano")
    out_only = engine.build_choreography(analysis, markers_7e, preset='medium',
                                         mode=engine.MODE_MARKERS_ONLY, rng=random.Random(5))
    sidecar_only = [a for a in out_only if a.get('_sidecar')]
    non_sidecar_only = [a for a in out_only if not a.get('_sidecar')]
    check(f"i 4 marker sono presenti anche in MODE_MARKERS_ONLY (trovati {len(sidecar_only)})",
          len(sidecar_only) == 4)
    check(f"il resto (non-marker) e' composto SOLO da ostacoli (Squat/Dodge, piu' un "
          f"eventuale Block SOLO se in combo con uno Squat allo stesso istante - vedi "
          f"_keep_auto_obstacles, 30/08 sera) - trovati tipi: "
          f"{sorted(set(a['moveType'] for a in non_sidecar_only))}",
          all(a['moveType'] in (choreo.MOVE_SQUAT, choreo.MOVE_DODGE, choreo.MOVE_BLOCK)
              for a in non_sidecar_only))
    out_harmonize_same_markers = engine.build_choreography(
        analysis, markers_7e, preset='medium', rng=random.Random(5))
    check(f"MODE_MARKERS_ONLY produce MOLTE meno azioni di MODE_HARMONIZE "
          f"(only={len(out_only)}, harmonize={len(out_harmonize_same_markers)})",
          len(out_only) < len(out_harmonize_same_markers))

    print("\n7e-bis. MODE_EXTEND, marker RADI = accenti isolati (04/09): non")
    print("    sono un ritmo, sono punti fermi - l'automatico ci scorre")
    print("    attraverso invece di lasciare il brano vuoto in mezzo, che era")
    print("    il difetto lamentato ('estendi non fa nessuna differenza')")
    duration = analysis['duration']
    assert duration > markers_7e[-1] + 20, \
        "il brano di test deve essere piu' lungo dell'ultimo marker per verificare 'il resto'"
    out_extend = engine.build_choreography(analysis, markers_7e, preset='medium',
                                           mode=engine.MODE_EXTEND, rng=random.Random(5))
    span_start, span_end = markers_7e[0], markers_7e[-1]
    marcatura = engine.classifica_marcatura(sorted(markers_7e), analysis['beats'])
    check(f"quattro marker a quaranta secondi l'uno dall'altro sono ACCENTI, "
          f"non blocchi ritmici (blocchi={len(marcatura['blocchi'])}, "
          f"accenti={len(marcatura['accenti'])})",
          not marcatura['blocchi'] and len(marcatura['accenti']) == 4)
    in_mezzo = [a for a in out_extend if span_start < a['startTime'] < span_end
                and not a.get('_sidecar')
                and a['moveType'] in (choreo.MOVE_JAB, choreo.MOVE_HOOK, choreo.MOVE_UPPERCUT)]
    check(f"FRA un accento e l'altro la coreografia c'e' (trovati {len(in_mezzo)} pugni "
          f"automatici): prima quel tratto restava silenzioso",
          len(in_mezzo) > 50)
    check(f"i 4 marker sono comunque tutti presenti (trovati "
          f"{sum(1 for a in out_extend if a.get('_sidecar'))})",
          sum(1 for a in out_extend if a.get('_sidecar')) == 4)

    print("\n7e-quater. MODE_EXTEND, BLOCCO CONTIGUO: li' dentro l'utente sta")
    print("    dettando un ritmo, e il tool non ci mette niente di suo")
    bt_7e = [b['_triggerTime'] for b in analysis['beats']]
    blocco = [bt_7e[i] for i in range(40, 120)]          # ottanta colpi di fila
    out_blocco = engine.build_choreography(analysis, blocco, preset='medium',
                                           mode=engine.MODE_EXTEND,
                                           correct_imprecision=False, rng=random.Random(5))
    m_blocco = engine.classifica_marcatura(sorted(blocco), analysis['beats'])
    check(f"ottanta colpi di fila sono UN blocco ritmico (blocchi="
          f"{len(m_blocco['blocchi'])}, copertura {m_blocco['copertura']:.0f} s)",
          len(m_blocco['blocchi']) == 1 and not m_blocco['accenti'])
    a_blocco, b_blocco = m_blocco['intervalli'][0]
    dentro_intrusi = [a for a in out_blocco
                      if a_blocco <= a['startTime'] <= b_blocco and not a.get('_sidecar')
                      and a['moveType'] not in (choreo.MOVE_SQUAT, choreo.MOVE_DODGE,
                                                choreo.MOVE_BLOCK)]
    check(f"dentro il blocco nessun colpo automatico non richiesto (trovati "
          f"{len(dentro_intrusi)}, ammessi solo marker e ostacoli)",
          not dentro_intrusi)
    fuori_blocco = [a for a in out_blocco if a['startTime'] > b_blocco + 1
                    and a['moveType'] not in (choreo.MOVE_SQUAT, choreo.MOVE_DODGE)]
    check(f"e fuori dal blocco il resto del brano viene generato per intero "
          f"(trovate {len(fuori_blocco)} mosse non-ostacolo)",
          len(fuori_blocco) > 0)

    print("\n7e-quinquies. Marcature MISTE: un blocco e due accenti nello")
    print("    stesso brano ricevono trattamenti diversi")
    misto = blocco[:60] + [bt_7e[300], bt_7e[340]]
    m_misto = engine.classifica_marcatura(sorted(misto), analysis['beats'])
    check(f"riconosce 1 blocco e 2 accenti (blocchi={len(m_misto['blocchi'])}, "
          f"accenti={len(m_misto['accenti'])})",
          len(m_misto['blocchi']) == 1 and len(m_misto['accenti']) == 2)
    check("la copertura conta SOLO il blocco, non la distanza fino agli accenti "
          f"({m_misto['copertura']:.0f} s, non {max(misto) - min(misto):.0f})",
          m_misto['copertura'] < (max(misto) - min(misto)) / 2)

    print("\n7e-ter. MODE_EXTEND 'aggressiva' (30/08, dopo la prima prova reale:")
    print("    'deve essere piu' aggressiva, continua a fare coreografie")
    print("    classiche BoxVR' - il tratto fuori dallo span ora usa il preset")
    print("    la cui cadenza MISURATA somiglia di piu' a quella dei marker,")
    print("    non piu' semplicemente quello gia' configurato sul brano")
    check("light: cadenza bassissima (2 marker/min) -> stima 'light'",
          engine._infer_preset_from_marker_density([0.0, 30.0], 0.0, 30.0) == 'light')
    # ~74 epm su uno span di 1 minuto = target esatto di 'medium'
    dense_medium = [i * (60.0 / 74) for i in range(74)]
    check("medium: cadenza vicina al target misurato (74/min) -> stima 'medium'",
          engine._infer_preset_from_marker_density(dense_medium, 0.0, 60.0) == 'medium')
    # ~88 epm = target esatto di 'high'
    dense_high = [i * (60.0 / 88) for i in range(88)]
    check("high: cadenza vicina al target misurato (88/min) -> stima 'high'",
          engine._infer_preset_from_marker_density(dense_high, 0.0, 60.0) == 'high')
    check("span degenere (un solo marker, durata zero) -> None, nessuna stima priva di senso",
          engine._infer_preset_from_marker_density([10.0], 10.0, 10.0) is None)
    check("nessun marker filtrato -> None",
          engine._infer_preset_from_marker_density([], 0.0, 60.0) is None)

    # integrazione: la stessa chiamata a build_choreography con preset='medium'
    # esplicito deve comunque produrre un tratto FUORI dallo span piu' rado se
    # i marker DENTRO lo span erano rarefatti (implica 'light'), e piu' fitto
    # se erano fittissimi (implica 'high') - la densita' osservata nei marker
    # deve davvero cambiare cosa succede fuori, non solo la funzione isolata.
    sparse_markers = [10.0, 45.0, 90.0, 130.0]   # ~2/min, gia' usato sopra (7e-bis)
    tight_markers = [10.0 + i * (60.0 / 88) for i in range(80)]   # ~88/min, come 'high'
    out_extend_sparse = engine.build_choreography(analysis, sparse_markers, preset='medium',
                                                   mode=engine.MODE_EXTEND, rng=random.Random(5))
    out_extend_tight = engine.build_choreography(analysis, tight_markers, preset='medium',
                                                  mode=engine.MODE_EXTEND, rng=random.Random(5))
    outside_sparse = [a for a in out_extend_sparse
                       if not (sparse_markers[0] <= a['startTime'] <= sparse_markers[-1])
                       and a['moveType'] not in (choreo.MOVE_SQUAT, choreo.MOVE_DODGE)]
    outside_tight = [a for a in out_extend_tight
                      if not (tight_markers[0] <= a['startTime'] <= tight_markers[-1])
                      and a['moveType'] not in (choreo.MOVE_SQUAT, choreo.MOVE_DODGE)]
    epm_outside_sparse = len(outside_sparse) / ((duration - sparse_markers[-1]) / 60.0)
    epm_outside_tight = len(outside_tight) / ((duration - tight_markers[-1]) / 60.0)
    check(f"con marker rarefatti (implica 'light') il tratto fuori dallo span e' meno denso "
          f"di quello con marker fittissimi (implica 'high'), a parita' di preset='medium' passato "
          f"(epm fuori: rarefatti={epm_outside_sparse:.1f}, fittissimi={epm_outside_tight:.1f})",
          epm_outside_sparse < epm_outside_tight)

    print("\n7f. 'Solo hit marker' (exclude_obstacles): mai Squat/Dodge su un marker")
    # gap corto forzato (marker fittissimi) cosi' la probabilita' di scegliere
    # centro e' comunque diversa da zero e il test e' significativo
    tight_markers = [20.0 + i * 0.4 for i in range(60)]
    out_excl = engine.build_choreography(analysis, tight_markers, preset='medium',
                                         mode=engine.MODE_HARMONIZE, exclude_obstacles=True,
                                         rng=random.Random(7))
    sidecar_excl = [a for a in out_excl if a.get('_sidecar')]
    obstacle_markers = [a for a in sidecar_excl if a['moveType'] in (choreo.MOVE_SQUAT, choreo.MOVE_DODGE)]
    check(f"con 'solo hit marker' nessun marker diventa Squat/Dodge "
          f"(trovati {len(obstacle_markers)} su {len(sidecar_excl)} marker sopravvissuti)",
          not obstacle_markers)
    centro_markers = [a for a in sidecar_excl if a['moveChannel'] == choreo.CH_CENTER]
    check(f"quando un marker e' centrale con 'solo hit marker', e' sempre Block "
          f"(trovati {sorted(set(a['moveType'] for a in centro_markers))})",
          all(a['moveType'] == choreo.MOVE_BLOCK for a in centro_markers))

    print("\n7g. Correzione delle imprecisioni (27/08, richiesta esplicita)")
    onsets_sorted = sorted(analysis.get('onsets') or [])
    # sceglie un accento vero isolato (nessun altro accento entro 4 finestre,
    # cosi' ne' il marker "vicino" ne' quello "lontano" rischiano di
    # agganciarsi per caso a un accento DIVERSO da quello scelto) e marca
    # leggermente accanto - entro/fuori la finestra di correzione
    margin = engine.MARKER_SNAP_WINDOW_S * 4
    isolated = [t for i, t in enumerate(onsets_sorted)
               if (i == 0 or t - onsets_sorted[i - 1] > margin)
               and (i == len(onsets_sorted) - 1 or onsets_sorted[i + 1] - t > margin)]
    real_onset_g = isolated[len(isolated) // 2]
    near_marker = real_onset_g + engine.MARKER_SNAP_WINDOW_S * 0.6   # dentro la finestra
    far_marker = real_onset_g + engine.MARKER_SNAP_WINDOW_S * 3.0    # fuori, zona isolata per costruzione

    out_corrected = engine.build_choreography(analysis, [near_marker], preset='medium',
                                              correct_imprecision=True, rng=random.Random(11))
    sidecar_corrected = [a for a in out_corrected if a.get('_sidecar')]
    check(f"un marker vicino (entro la finestra) viene spostato ESATTAMENTE sull'accento vero "
          f"(marker={near_marker:.3f}, accento={real_onset_g:.3f}, "
          f"trovato={sidecar_corrected[0]['startTime']:.3f})",
          len(sidecar_corrected) == 1 and abs(sidecar_corrected[0]['startTime'] - real_onset_g) < 1e-6)

    out_uncorrected = engine.build_choreography(analysis, [near_marker], preset='medium',
                                                correct_imprecision=False, rng=random.Random(11),
                                                aggancio_magnetico=False)
    sidecar_uncorrected = [a for a in out_uncorrected if a.get('_sidecar')]
    check(f"lo stesso marker SENZA la correzione resta al suo istante originale "
          f"(trovato={sidecar_uncorrected[0]['startTime']:.3f}, atteso={near_marker:.3f})",
          len(sidecar_uncorrected) == 1 and abs(sidecar_uncorrected[0]['startTime'] - near_marker) < 1e-6)

    out_far = engine.build_choreography(analysis, [far_marker], preset='medium',
                                        correct_imprecision=True, rng=random.Random(11),
                                        aggancio_magnetico=False)
    sidecar_far = [a for a in out_far if a.get('_sidecar')]
    check(f"un marker LONTANO da ogni accento non viene toccato anche con la correzione attiva "
          f"(trovato={sidecar_far[0]['startTime']:.3f}, atteso={far_marker:.3f})",
          len(sidecar_far) == 1 and abs(sidecar_far[0]['startTime'] - far_marker) < 1e-6)

    print("\n7h. Aggancio magnetico alla griglia (richiesto: i colpi propri e")
    print("    quelli del tool non devono sentirsi come due cose diverse)")
    beats_veri = analysis['beats']
    griglia = engine.griglia_metrica(beats_veri)
    su_griglia = griglia[40][0]
    passo = griglia[1][0] - griglia[0][0]
    poco_fuori = su_griglia + passo * 0.15                     # dentro la calamita
    molto_fuori = su_griglia + passo * 0.5                    # scelta, non sbavatura

    agganciati = engine.aggancia_marker_alla_griglia([poco_fuori], beats_veri)
    check(f"un colpo appena fuori griglia ci finisce sopra "
          f"(da {poco_fuori:.3f} a {agganciati[0]:.3f}, griglia {su_griglia:.3f})",
          abs(agganciati[0] - su_griglia) < 1e-6)

    lontani = engine.aggancia_marker_alla_griglia([molto_fuori], beats_veri)
    check(f"un colpo messo APPOSTA fuori griglia non viene spostato "
          f"(atteso {molto_fuori:.3f}, trovato {lontani[0]:.3f})",
          abs(lontani[0] - molto_fuori) < 1e-6)

    onsets_g = sorted(analysis.get('onsets') or [])
    if onsets_g:
        sopra_accento = onsets_g[60]
        fermi = engine.aggancia_marker_alla_griglia([sopra_accento], beats_veri,
                                                    onsets=onsets_g)
        check("un colpo gia' su un accento VERO del brano non viene spostato dalla "
              "griglia (l'accento e' il brano, la griglia e' la nostra "
              "approssimazione del brano)",
              abs(fermi[0] - sopra_accento) < 1e-6)

    print("\n7i. «Estendi» impara DOVE colpisce l'utente, non solo quanto spesso")
    # marker tutti sul levare (meta' fra un beat e l'altro): una firma
    # ritmica netta, che nella coreografia automatica non c'e'
    bt = [b['_triggerTime'] for b in beats_veri]
    levare = [(bt[i] + bt[i + 1]) / 2.0 for i in range(20, 240, 2)]  # oltre 45 s marcati
    firma = engine.firma_ritmica(levare, beats_veri)
    fasi = engine.fasi_preferite(firma)
    check(f"la firma riconosce che l'utente sta sul levare (fasi usate: {sorted(fasi)}, "
          f"attesa la 2 su 4)", fasi == {2})

    battere = [bt[i] for i in range(20, 240, 2)]
    check("e riconosce il battere quando i colpi stanno li'",
          engine.fasi_preferite(engine.firma_ritmica(battere, beats_veri)) == {0})

    print("\n7l. Copertura minima: si contano i BLOCCHI RITMICI, non la")
    print("    distanza fra il primo e l'ultimo marker")
    corta = engine.copertura_marcata([bt[i] for i in range(20, 60, 2)],
                                     beats=beats_veri)
    check(f"un blocco troppo corto non basta (copertura {corta['secondi']:.0f} s, "
          f"minimo {corta['minimo']:.0f})", not corta['sufficiente'])
    lunga = engine.copertura_marcata(levare, beats=beats_veri)
    check(f"un blocco lungo basta (copertura {lunga['secondi']:.0f} s, "
          f"{lunga['marker']} colpi nei blocchi, {lunga['blocchi']} blocco/i)",
          lunga['sufficiente'])

    # e il conto e' lo stesso che fa il motore: stessa pipeline, mai due copie
    check("i marker si contano dopo il filtro del limite fisico, non prima",
          engine.copertura_marcata([1.0, 1.05, 1.10, 40.0],
                                   beats=beats_veri)['marker_totali'] == 2)

    # Difetto reale del 04/09: il motore chiedeva 45 s E almeno 8 marker, la
    # funzione che alimenta il pannello guardava solo i secondi. Con due
    # marker agli estremi del brano il pannello annunciava "Estendi usera'
    # la tua cadenza" mentre il motore ricadeva sul preset. Una regola sola.
    estremi = engine.copertura_marcata([5.0, 170.0], beats=beats_veri)
    check(f"due marker agli estremi non sono un blocco: copertura "
          f"{estremi['secondi']:.0f} s, {estremi['accenti']} accenti -> NON sufficiente",
          not estremi['sufficiente'] and estremi['blocchi'] == 0)
    check("il pannello e il motore usano la stessa identica regola",
          engine.ha_imparato(estremi['secondi'], estremi['marker']) is False
          and engine.ha_imparato(60.0, 20) is True)

    check("senza l'analisi del brano non si inventa un numero: lo dichiara",
          engine.copertura_marcata(levare)['analisi_pronta'] is False)

    print("\n7m. e la coreografia FUORI dal tratto marcato segue quella firma")
    out_firma = engine.build_choreography(analysis, levare, preset='medium',
                                          mode=engine.MODE_EXTEND,
                                          correct_imprecision=False, rng=random.Random(4))
    span_a, span_b = min(levare), max(levare)
    fuori = [a for a in out_firma
             if not a.get('_sidecar') and not (span_a <= a['startTime'] <= span_b)
             and a['moveType'] in (choreo.MOVE_JAB, choreo.MOVE_HOOK, choreo.MOVE_UPPERCUT)]
    quota_levare = 0.0
    if fuori:
        firma_fuori = engine.firma_ritmica([a['startTime'] for a in fuori], beats_veri)
        quota_levare = firma_fuori[2] if firma_fuori else 0.0
    check(f"i pugni generati fuori dal tratto marcato stanno sul levare come i suoi "
          f"({quota_levare * 100:.0f}% sulla fase 2, su {len(fuori)} pugni)",
          len(fuori) > 20 and quota_levare > 0.8)

    # e con poca copertura NON si allinea niente: meglio una coreografia
    # BoxVR onesta che una "personalizzata" su quattro colpi
    pochi = [(bt[i] + bt[i + 1]) / 2.0 for i in range(20, 30, 2)]
    out_pochi = engine.build_choreography(analysis, pochi, preset='medium',
                                          mode=engine.MODE_EXTEND,
                                          correct_imprecision=False, rng=random.Random(4))
    fuori_p = [a for a in out_pochi
               if not a.get('_sidecar') and a['startTime'] > max(pochi) + 1
               and a['moveType'] in (choreo.MOVE_JAB, choreo.MOVE_HOOK, choreo.MOVE_UPPERCUT)]
    firma_p = engine.firma_ritmica([a['startTime'] for a in fuori_p], beats_veri)
    check(f"con pochi secondi marcati la coreografia resta quella automatica "
          f"(sul levare solo il {(firma_p[2] if firma_p else 0) * 100:.0f}%)",
          not firma_p or firma_p[2] < 0.8)

    print("\n7n. e ne rispetta le PROPORZIONI, non solo le suddivisioni")
    print("    (06/09: il difetto che 7m non vedeva - con una marcatura su")
    print("    due suddivisioni diverse, il vecchio metodo le appiattiva")
    print("    tutte sulla piu' vicina, cioe' sul battere: 'scivolano nello")
    print("    standard BoxVR')")

    # marcatura che usa DUE suddivisioni in proporzioni diverse: due colpi
    # sul battere ogni uno sul levare. E' il caso in cui il vecchio metodo
    # sbagliava, e quello che 7m non poteva vedere perche' guarda una fase
    # sola.
    misto = []
    for i in range(40, 260):
        misto.append(bt[i])                          # battere
        if i % 3 == 0:
            misto.append((bt[i] + bt[i + 1]) / 2.0)  # levare, un terzo delle volte
    misto.sort()
    firma_misto = engine.firma_ritmica(misto, beats_veri)
    check(f"la marcatura di prova usa davvero due suddivisioni "
          f"({' '.join('%.2f' % x for x in firma_misto)})",
          firma_misto and sum(1 for q in firma_misto if q >= 0.1) == 2)

    auto_finto = [{'startTime': t, 'beatNumber': float(i), 'moveType': choreo.MOVE_JAB,
                   'moveChannel': choreo.CH_FRONT if i % 2 else choreo.CH_BACK}
                  for i, t in enumerate(bt[300:600])]
    ritmato = engine.ritma_come_utente(auto_finto, beats_veri, firma_misto)
    check(f"la densita' non cambia: era decisa dal preset, non da qui "
          f"({len(auto_finto)} -> {len(ritmato)})",
          len(ritmato) == len(auto_finto))

    firma_uscita = engine.firma_ritmica([a['startTime'] for a in ritmato], beats_veri)
    scarto = max(abs(a - b) for a, b in zip(firma_misto, firma_uscita))
    check(f"le proporzioni generate ricalcano le sue "
          f"(sue: {' '.join('%.2f' % x for x in firma_misto)} | "
          f"generate: {' '.join('%.2f' % x for x in firma_uscita)} | "
          f"scarto massimo {scarto:.2f})",
          scarto < 0.08)

    # e il vecchio metodo, sugli stessi dati, sbagliava: si tiene qui come
    # promemoria di cosa NON deve tornare
    fasi_misto = engine.fasi_preferite(firma_misto)
    vecchio = engine.allinea_azioni_alla_firma(auto_finto, beats_veri, fasi_misto)
    firma_vecchia = engine.firma_ritmica([a['startTime'] for a in vecchio], beats_veri)
    scarto_vecchio = max(abs(a - b) for a, b in zip(firma_misto, firma_vecchia))
    check(f"(controprova) il metodo precedente le appiattiva davvero "
          f"(generate: {' '.join('%.2f' % x for x in firma_vecchia)} | "
          f"scarto {scarto_vecchio:.2f}, molto peggiore di {scarto:.2f})",
          scarto_vecchio > scarto + 0.15)

    # ARMONIZZA impara anche lei, dal 06/09: prima il suo livello automatico
    # era il repertorio cosi' com'e', senza guardare una volta dove colpisce
    # chi sta giocando
    out_arm = engine.build_choreography(analysis, misto, preset='medium',
                                        mode=engine.MODE_HARMONIZE,
                                        correct_imprecision=False, rng=random.Random(4))
    pugni_arm = [a['startTime'] for a in out_arm
                 if not a.get('_sidecar')
                 and a['moveType'] in (choreo.MOVE_JAB, choreo.MOVE_HOOK, choreo.MOVE_UPPERCUT)]
    firma_arm = engine.firma_ritmica(pugni_arm, beats_veri) if pugni_arm else None
    scarto_arm = (max(abs(a - b) for a, b in zip(firma_misto, firma_arm))
                  if firma_arm else 1.0)
    check(f"anche in ARMONIZZA i colpi del tool seguono il ritmo dell'utente "
          f"(sue: {' '.join('%.2f' % x for x in firma_misto)} | "
          f"tool: {' '.join('%.2f' % x for x in firma_arm) if firma_arm else '-'} | "
          f"scarto {scarto_arm:.2f}, su {len(pugni_arm)} pugni)",
          len(pugni_arm) > 20 and scarto_arm < 0.20)


else:
    print("  (mp3 di prova non trovato, salto - non e' un fallimento del codice)")

print("\n7h. _snap_marker_to_onset in isolamento (nessun mp3 necessario)")
fake_onsets = [1.0, 2.0, 5.0]
check("dentro la finestra -> aggancia esattamente all'accento",
      engine._snap_marker_to_onset(2.0 + engine.MARKER_SNAP_WINDOW_S * 0.5, fake_onsets) == 2.0)
check("appena fuori dalla finestra -> resta invariato",
      abs(engine._snap_marker_to_onset(2.0 + engine.MARKER_SNAP_WINDOW_S * 1.5, fake_onsets)
          - (2.0 + engine.MARKER_SNAP_WINDOW_S * 1.5)) < 1e-9)
check("lista di accenti vuota -> resta invariato, nessuna eccezione",
      engine._snap_marker_to_onset(3.0, []) == 3.0)
check("sceglie il PIU' VICINO fra due accenti candidati entrambi in finestra, non il primo trovato",
      engine._snap_marker_to_onset(2.02, [2.00, 2.03, 5.0]) == 2.03)

print("\n8. Tipo di mossa centrale condizionato al GAP (26/08, punto 8)")
print("   misurato sui 465 workout: con poco spazio la schivata non compare MAI")
for bucket, probs in engine.CENTRO_TYPE_PROBS_BY_GAP.items():
    total = sum(probs.values())
    check(f"la riga '{bucket}' somma a 1.0 (trovato {total:.3f})", abs(total - 1.0) < 1e-6)
check("con poco spazio ('short') la probabilita' TABELLARE diretta di Dodge e' esattamente 0 "
      "(prima della ripartizione Squat->Dodge richiesta il 30/08 notte, che si applica DOPO "
      "questa tabella - vedi sez. 14)",
      engine.CENTRO_TYPE_PROBS_BY_GAP['short'][choreo.MOVE_DODGE] == 0.0)

# Prova end-to-end su marker FITTI (0.5 beat, gap 'short' per costruzione).
#
# Dal 30/08 al 06/09 questo controllo pretendeva il CONTRARIO di quanto
# scritto due righe sopra: che una schivata comparisse lo stesso, perche' la
# ripartizione Squat->Dodge la infilava li' insieme a un pugno. C'era pure
# scritto: «il vecchio "mai" non vale piu' di proposito». Era una scelta,
# non una scoperta - si volevano piu' schivate, e per averle si e' scavalcata
# una misura fatta su 465 allenamenti veri.
#
# La prova in VR del 06/09 ha dato ragione alla misura: dove non c'e' spazio,
# la schivata non si esegue. Il controllo torna a chiedere cio' che il gioco
# fa davvero. Le schivate non spariscono - vedi subito sotto, dove lo spazio
# c'e'.
beats8 = fake_beats(bpm=120.0, n=2000)
tight = [20.0 + i * 0.25 for i in range(300)]    # 0.5 beat di distanza -> 'short'
out_tight = engine.place_moves_on_markers(tight, beats8, rng=random.Random(5))
dodges_tight = [a for a in out_tight if a['moveType'] == choreo.MOVE_DODGE]
check(f"marker fitti (0.5 beat): NESSUNA schivata, come nei 465 workout "
      f"ufficiali - non c'e' un beat libero in cui spostare il corpo di lato "
      f"(trovate {len(dodges_tight)} su {len(out_tight)} azioni)",
      len(dodges_tight) == 0)

# E dove lo spazio c'e', la schivata compare: e' il problema per cui esiste
# la ripartizione Squat->Dodge (dopo un allenamento intero senza nemmeno una
# schivata). Marker a due beat di distanza, cioe' una marcatura umana normale
# invece che una raffica da metronomo.
larghi = [20.0 + i * 1.0 for i in range(300)]     # 2 beat a 120 bpm
out_larghi = engine.place_moves_on_markers(larghi, beats8, rng=random.Random(5))
dodges_larghi = [a for a in out_larghi if a['moveType'] == choreo.MOVE_DODGE]
check(f"marker a due beat: le schivate ci sono ({len(dodges_larghi)} su "
      f"{len(out_larghi)} azioni) - il difetto 'zero schivate in tutta la "
      f"playlist' non torna",
      len(dodges_larghi) > 0)

wide = [20.0 + i * 1.5 for i in range(300)]      # 3 beat di distanza -> 'long'
out_wide = engine.place_moves_on_markers(wide, beats8, rng=random.Random(5))
centro_wide = [a for a in out_wide if a['moveChannel'] == choreo.CH_CENTER]
dodges_wide = [a for a in out_wide if a['moveType'] == choreo.MOVE_DODGE]
check(f"marker larghi (3 beat) producono anche schivate "
      f"(trovate {len(dodges_wide)} su {len(centro_wide)} mosse centrali)",
      len(dodges_wide) > 0)

print("\n9. Tipo di mossa centrale condizionato al GAP *e* alla mossa PRECEDENTE")
print("   (26/08, seconda misura - tabella a due entrate, solo celle con n>=200)")
for key, probs in engine.CENTRO_TYPE_PROBS_BY_GAP_AND_PREV.items():
    total = sum(probs.values())
    # i valori misurati sono arrotondati a 3 decimali (measure_centro_type_2d.py):
    # tolleranza piu' larga della tabella 1D, che invece somma esatto.
    check(f"la cella {key} somma a 1.0 (trovato {total:.3f})", abs(total - 1.0) < 2e-3)

# il caso piu' netto misurato: con gap corto, dopo uno Squat il prossimo
# centrale e' SEMPRE un altro Squat (100.0% su 1553 osservazioni reali) -
# diverso dalla media 'short' 1D (86.1% Squat), che mediava questo caso con
# quello, molto piu' vario, "dopo un Jab" (74.1% Block). Costruito apposta:
# ogni marker cade a 0.5 beat dal precedente E forziamo la prima mossa
# centrale a Squat leggendo l'azione reale prodotta, poi verificando quelle
# successive con lo stesso gap corto.
#
# AGGIORNATO 30/08 notte: la tabella continua a dare SEMPRE Squat qui (0%
# per qualunque altra cosa, Dodge compreso) - ma la ripartizione
# Squat->Dodge (SQUAT_TO_DODGE_COMBO_PROB) si applica DOPO aver consultato
# la tabella, quindi un Dodge come "prossimo centrale" e' ora un esito
# atteso (la conversione di uno Squat), non piu' una violazione - l'unica
# vera violazione resterebbe un Block, che la tabella non assegna mai qui.
beats9 = fake_beats(bpm=120.0, n=2000)
close_markers = [20.0 + i * 0.25 for i in range(400)]   # 0.5 beat -> 'short'
out9 = engine.place_moves_on_markers(close_markers, beats9, rng=random.Random(3))
# isola le sequenze "centrale dopo un centrale Squat con gap corto": per
# costruzione del test (gap 0.5 beat fissi) ogni centrale ha il gap corto
# rispetto al precedente, quindi basta guardare le coppie consecutive.
violations = []
for i in range(1, len(out9)):
    prev, cur = out9[i - 1], out9[i]
    if (prev['moveType'] == choreo.MOVE_SQUAT and cur['moveChannel'] == choreo.CH_CENTER
            and cur['moveType'] not in (choreo.MOVE_SQUAT, choreo.MOVE_DODGE)):
        violations.append((prev, cur))
check(f"con gap corto, dopo uno Squat il prossimo centrale e' sempre Squat "
      f"o un Dodge (la sola conversione ammessa dalla ripartizione, mai un "
      f"Block) (trovate {len(violations)} eccezioni)", not violations)

print("\n10. I due livelli ora condividono la memoria del ritmo (26/08, punto 3)")
print("    prima un marker non 'vedeva' le mosse automatiche vicine")
beats10 = fake_beats(bpm=120.0, n=100)
marker_t = 5.15   # beat 10.3 (beatInBar 3): 0.3 beat dopo una mossa a beat 10.0

# scenario A: contesto = un Jab automatico laterale, gap corto (0.3 beat) ->
# CENTRO_PROB_TABLE[(3,'short')] = 0.016, quasi sempre laterale - e quando lo
# e', il lato deve alternare rispetto al Jab automatico, non a un contatore
# separato che ignora il livello automatico (il difetto corretto qui).
context_lateral = [{'beatNumber': 10.0, 'moveType': choreo.MOVE_JAB, 'moveChannel': choreo.CH_FRONT}]
alternated = same_side = centro_hits = 0
for seed in range(200):
    out = engine._place_on_markers([marker_t], beats10, random.Random(seed),
                                    context_actions=context_lateral)
    a = out[0]
    if a['moveChannel'] == choreo.CH_CENTER:
        centro_hits += 1
    elif a['moveChannel'] == choreo.CH_BACK:
        alternated += 1
    else:
        same_side += 1
check(f"quando sceglie laterale, alterna SEMPRE rispetto al Jab automatico "
      f"appena prima (alternato {alternated}, stesso lato {same_side}, "
      f"centrale {centro_hits}/200)", same_side == 0 and alternated > 0)

# scenario B: contesto = uno Squat automatico (nessun laterale prima -> A4
# usa il bucket 'none', p_centro alto per bib=3: 0.723), gap corto (0.3 beat)
# dal marker - CENTRO_TYPE_PROBS_BY_GAP_AND_PREV[('short', Squat)] impone
# Squat al 100%: se il marker sceglie centro, la TABELLA da' sempre Squat.
#
# AGGIORNATO 30/08 notte: la ripartizione Squat->Dodge si applica dopo la
# tabella, quindi su 500 semi ci si aspetta di vedere anche qualche Dodge
# (la conversione) oltre allo Squat diretto - mai un Block, che la tabella
# non assegna mai in questa cella.
context_squat = [{'beatNumber': 10.0, 'moveType': choreo.MOVE_SQUAT, 'moveChannel': choreo.CH_CENTER}]
centro_types = set()
for seed in range(500):
    out = engine._place_on_markers([marker_t], beats10, random.Random(seed),
                                    context_actions=context_squat)
    a = out[0]
    if a['moveChannel'] == choreo.CH_CENTER:
        centro_types.add(a['moveType'])
check(f"dopo uno Squat automatico con gap corto, la mossa centrale del "
      f"marker e' sempre Squat o la sua conversione in Dodge, mai un Block "
      f"(tipi trovati: {centro_types})",
      centro_types <= {choreo.MOVE_SQUAT, choreo.MOVE_DODGE})
check(f"su 500 semi la ripartizione Squat->Dodge si manifesta davvero "
      f"(non e' rimasta lettera morta) - trovati tipi {centro_types}",
      choreo.MOVE_DODGE in centro_types)

# senza contesto, lo stesso marker isolato non ha nulla da alternare - il
# comportamento di place_moves_on_markers (usato nei test precedenti) resta
# quello di prima, non e' stato toccato da questa modifica.
out_no_ctx = engine._place_on_markers([marker_t], beats10, random.Random(0))
check("senza contesto il marker isolato usa i default (nessun laterale prima)",
      out_no_ctx[0]['moveChannel'] in (choreo.CH_FRONT, choreo.CH_CENTER))

print("\n11. min_gap_s sovrascrivibile (30/08, slider soglia richiesto")
print("    esplicitamente dopo aver scoperto marker scartati in silenzio)")
# BPM ESTREMO (2000) apposta: enforce_playability ha un SECONDO vincolo di
# spaziatura, indipendente da MIN_INPUT_GAP_S/min_gap_s - il recupero braccio
# generale (MIN_GAP_BEATS=0.5 beat, boxvr_choreo.py), piu' severo se le due
# mosse finiscono sullo STESSO braccio (MIN_GAP_ARM_BEATS=1.0) o dopo certi
# tipi di colpo (MIN_GAP_AFTER_SWING_BEATS=1.5) - a un BPM realistico anche
# solo "veloce" (provato inizialmente a 600) quel vincolo puo' comunque
# dominare per caso a seconda di quale lato/tipo viene assegnato ai due
# marker, mascherando l'effetto di min_gap_s che si vuole isolare qui. Solo
# a un tempo cosi' estremo (1.5 beat = 45ms) quel vincolo scende
# sicuramente sotto ai 90ms di distanza scelti per il test, qualunque lato
# venga assegnato. A un tempo di canzone reale il vincolo di recupero
# braccio domina PRIMA che min_gap_s conti qualcosa - visto scrivendo
# test_marker_snap_wiring.py: a 127 BPM un gap di 90ms viene comunque unito
# da quel vincolo, non da MIN_INPUT_GAP_S, quindi abbassare la sola soglia
# marker li' non cambia l'esito finale.
fast_beats = fake_beats(bpm=2000.0)
close_markers = [1.000, 1.090]   # 90ms di distanza - sotto il default (170ms)

out_default = engine.place_moves_on_markers(close_markers, fast_beats, rng=random.Random(3))
check(f"soglia di default (170ms): il secondo marker (90ms dal primo) viene scartato "
      f"(trovate {len(out_default)} azioni)", len(out_default) == 1)

out_loose = engine.place_moves_on_markers(close_markers, fast_beats, rng=random.Random(3),
                                          min_gap_s=0.05)
check(f"soglia abbassata a 50ms: entrambi i marker a 90ms sopravvivono "
      f"(trovate {len(out_loose)} azioni)", len(out_loose) == 2)

check(f"snap_and_filter_markers conta gli stessi sopravvissuti usati da place_moves_on_markers "
      f"(coerenza fra la funzione di solo conteggio e quella vera)",
      len(engine.snap_and_filter_markers(close_markers, min_gap_s=0.05)) == 2 and
      len(engine.snap_and_filter_markers(close_markers)) == 1)

print("\n12. sidecar_min_gap_s in enforce_playability (30/08, bug reale segnalato:")
print("    'la modalita' Estendi non sta usando la soglia minima definita")
print("    dall'utente' - vero, ma non dove sembrava). A un tempo REALISTICO")
print("    (172 BPM, non l'estremo di prima) 0.5 beat = 174ms: anche dopo che")
print("    il filtro sui marker (sezione 11 sopra) lascia passare due marker a")
print("    90ms, il vincolo di recupero braccio di enforce_playability - pensato")
print("    per le COMBO GENERATE DA NOI, non per due decisioni indipendenti")
print("    dell'utente - li univa comunque in silenzio")
moderate_beats = fake_beats(bpm=172.0)   # tempo realistico, non l'estremo usato in sezione 11
close_markers_realistic = [10.000, 10.090]

raw_loose = engine._place_on_markers(close_markers_realistic, moderate_beats, random.Random(0), min_gap_s=0.05)
check(f"il filtro sui marker lascia passare entrambi (base per il test - gia' provato in sez. 11) "
      f"(trovate {len(raw_loose)} azioni)", len(raw_loose) == 2)

without_override = choreo.enforce_playability(raw_loose, moderate_beats, snap_to_grid=False)
check(f"SENZA sidecar_min_gap_s passato a enforce_playability: il vincolo di recupero "
      f"braccio (0.5 beat=174ms) vince comunque sulla soglia gia' allentata a monte, "
      f"un marker sparisce (trovate {len(without_override)} azioni) - questo era il bug",
      len(without_override) == 1)

with_override = choreo.enforce_playability(raw_loose, moderate_beats, snap_to_grid=False,
                                           sidecar_min_gap_s=0.05)
check(f"CON sidecar_min_gap_s=0.05 passato: entrambi i marker sopravvivono ESATTAMENTE "
      f"ai loro istanti originali, non solo 'sopravvivono da qualche parte' (trovate "
      f"{len(with_override)} azioni a {[round(a['startTime'], 3) for a in with_override]})",
      len(with_override) == 2 and
      sorted(round(a['startTime'], 3) for a in with_override) == close_markers_realistic)

# stesso vincolo per una coppia AUTOMATICA (non marcata _sidecar) allo stesso tempo,
# stessa distanza: deve restare intatto - l'eccezione vale SOLO per marker-vs-marker
auto_pair = [{'startTime': 10.000, 'beatNumber': 0.0, 'moveType': choreo.MOVE_JAB, 'moveChannel': 0,
              '_injected': True},
             {'startTime': 10.090, 'beatNumber': 0.0, 'moveType': choreo.MOVE_JAB, 'moveChannel': 4,
              '_injected': True}]
auto_with_override = choreo.enforce_playability(auto_pair, moderate_beats, snap_to_grid=False,
                                                sidecar_min_gap_s=0.05)
check(f"una coppia automatica (non marker) alla stessa distanza NON beneficia "
      f"dell'eccezione, anche passando sidecar_min_gap_s - resta soggetta al normale "
      f"recupero braccio (trovate {len(auto_with_override)} azioni, atteso 1 o 2 spostata "
      f"ma mai identica alla coppia marker)",
      not (len(auto_with_override) == 2 and
           sorted(round(a['startTime'], 3) for a in auto_with_override) == [10.0, 10.09]))

# integrazione end-to-end attraverso place_moves_on_markers, il vero punto
# d'ingresso usato dalla sidecar - non solo la funzione interna
end_to_end = engine.place_moves_on_markers(close_markers_realistic, moderate_beats,
                                           rng=random.Random(0), min_gap_s=0.05)
check(f"end-to-end via place_moves_on_markers: entrambi i marker sopravvivono ai loro "
      f"istanti esatti (trovate {len(end_to_end)} azioni a "
      f"{[round(a['startTime'], 3) for a in end_to_end]})",
      len(end_to_end) == 2 and
      sorted(round(a['startTime'], 3) for a in end_to_end) == close_markers_realistic)

print("\n12bis. OBSTACLE_MOVES esclusi dalla deroga sidecar_min_gap_s (30/08 sera,")
print("       bug reale in VR: 'non permettere mai uno scudo subito dopo un altro")
print("       scudo, dare almeno 200ms di spazio' - con lo slider abbassato molto")
print("       due marker classificati Block/Squat finivano a 90ms l'uno dall'altro)")
raw_obstacles = engine._place_on_markers(close_markers_realistic, moderate_beats,
                                         random.Random(3), min_gap_s=0.05)
check(f"seed di controllo: i due marker vengono classificati come mosse centrali "
      f"(Block/Squat), non pugni (trovati tipi {[a['moveType'] for a in raw_obstacles]})",
      {a['moveType'] for a in raw_obstacles} <= {choreo.MOVE_BLOCK, choreo.MOVE_SQUAT, choreo.MOVE_DODGE})

with_override_obstacles = choreo.enforce_playability(raw_obstacles, moderate_beats, snap_to_grid=False,
                                                      sidecar_min_gap_s=0.05)
check(f"CON sidecar_min_gap_s=0.05 passato, una coppia Block/Squat NON beneficia "
      f"della deroga - resta soggetta al normale recupero braccio (>= 1 beat), un "
      f"marker sparisce esattamente come SENZA l'eccezione (trovate "
      f"{len(with_override_obstacles)} azioni)",
      len(with_override_obstacles) == 1)

end_to_end_obstacles = engine.place_moves_on_markers(close_markers_realistic, moderate_beats,
                                                      rng=random.Random(3), min_gap_s=0.05)
check(f"end-to-end: due marker Block/Squat a 90ms non sopravvivono entrambi anche "
      f"con lo slider abbassato (trovate {len(end_to_end_obstacles)} azioni) - "
      f"la deroga resta riservata ai pugni",
      len(end_to_end_obstacles) == 1)

print("\n13. _keep_auto_obstacles preserva il combo Squat+Block (30/08 sera,")
print("    bug reale in VR: 'gli scudi che normalmente erano sotto uno squat,")
print("    ora erano sempre alti e sempre poco prima dello squat, rendendo")
print("    difficile pararsi e abbassarsi'). Squat+Block simultaneo e' un combo")
print("    VERO e comune del repertorio ufficiale (5/11 famiglie di pattern")
print("    Normal a intensita' alta ce l'hanno) - il vecchio filtro (solo")
print("    moveType in Squat/Dodge) scartava sempre il Block, lasciando lo")
print("    squat orfano del suo compagno di combo")
synthetic_auto = [
    {'startTime': 5.0, 'beatNumber': 10.0, 'moveType': choreo.MOVE_SQUAT, 'moveChannel': choreo.CH_CENTER},
    {'startTime': 5.0, 'beatNumber': 10.0, 'moveType': choreo.MOVE_BLOCK, 'moveChannel': choreo.CH_CENTER},
    {'startTime': 8.0, 'beatNumber': 16.0, 'moveType': choreo.MOVE_BLOCK, 'moveChannel': choreo.CH_CENTER},
    {'startTime': 12.0, 'beatNumber': 24.0, 'moveType': choreo.MOVE_SQUAT, 'moveChannel': choreo.CH_CENTER},
    {'startTime': 15.0, 'beatNumber': 30.0, 'moveType': choreo.MOVE_DODGE, 'moveChannel': choreo.CH_CENTER},
    {'startTime': 20.0, 'beatNumber': 40.0, 'moveType': choreo.MOVE_JAB, 'moveChannel': choreo.CH_FRONT},
]
kept = engine._keep_auto_obstacles(synthetic_auto)
kept_by_time = {}
for a in kept:
    kept_by_time.setdefault(round(a['startTime'], 6), set()).add(a['moveType'])

check("il combo Squat+Block a t=5.0 sopravvive INTERO (entrambe le mosse)",
      kept_by_time.get(5.0) == {choreo.MOVE_SQUAT, choreo.MOVE_BLOCK})
check("il Block isolato a t=8.0 (nessuno Squat/Dodge allo stesso istante) viene scartato "
      "come sempre - gli ostacoli restano una scelta esclusiva dell'automatico",
      8.0 not in kept_by_time)
check("lo Squat isolato a t=12.0 sopravvive da solo, come sempre",
      kept_by_time.get(12.0) == {choreo.MOVE_SQUAT})
check("la Dodge isolata a t=15.0 sopravvive da sola, come sempre",
      kept_by_time.get(15.0) == {choreo.MOVE_DODGE})
check("il Jab a t=20.0 non e' un ostacolo e non viene mai tenuto da questa funzione",
      20.0 not in kept_by_time)
check("nessun'altra mossa oltre alle 4 attese (5.0 doppio, 12.0, 15.0)",
      len(kept) == 4)

print("\n14. Ripartizione Squat -> Dodge (RIVISTA il 06/09 dopo la prova")
print("    in VR: la schivata resta una mossa SOLA, con il suo spazio)")

# Storia di questa sezione, perche' e' istruttiva. Dal 30/08 al 06/09 qui si
# verificava che ogni schivata avesse un pugno simultaneo: la quota del 40%,
# l'abbinamento uno a uno, che il pugno fosse solo Jab o Gancio, e che la
# coppia sopravvivesse intera a enforce_playability. Tutti controlli scritti
# bene, tutti verdi - e tutti a verificare un comportamento che in VR e'
# risultato ineseguibile ("impossibili da colpire: se schivo verso sinistra
# devo avere il colpo a sinistra perche' la destra e' occupata").
#
# Una prova automatica puo' dire solo se il programma fa quello che gli
# abbiamo chiesto, mai se quello che gli abbiamo chiesto ha senso. Quello lo
# dice il visore. Qui sotto si verifica il comportamento nuovo E il motivo
# per cui il vecchio era sbagliato, cosi' se rientra il test lo ferma.

check(f"la quota resta 0.40 ({engine.SQUAT_TO_DODGE_PROB})",
      abs(engine.SQUAT_TO_DODGE_PROB - 0.40) < 1e-9)

check("Dodge+Jab NON e' piu' una combinazione legale (ineseguibile in VR: "
      "il corpo e' spostato di lato e meta' dello spazio e' occupata)",
      frozenset((choreo.MOVE_DODGE, choreo.MOVE_JAB)) not in choreo.LEGAL_SIMULTANEOUS)
check("Dodge+Hook nemmeno",
      frozenset((choreo.MOVE_DODGE, choreo.MOVE_HOOK)) not in choreo.LEGAL_SIMULTANEOUS)
check("Block+Squat resta legale: e' l'unica coppia simultanea che esiste "
      "davvero nel repertorio del gioco (12 volte sui 47 pattern)",
      frozenset((choreo.MOVE_BLOCK, choreo.MOVE_SQUAT)) in choreo.LEGAL_SIMULTANEOUS)

# marker molto fitti, tutti a gap 'short' per costruzione (0.5 beat), dove
# la tabella diretta da' Squat al 86.1%/100% a seconda della cella - un
# campione ampio rende la proporzione osservata stabile.
beats14 = fake_beats(bpm=120.0, n=20000)
many_markers = [20.0 + i * 0.25 for i in range(8000)]
out14 = engine.place_moves_on_markers(many_markers, beats14, rng=random.Random(11))
squats14 = [a for a in out14 if a['moveType'] == choreo.MOVE_SQUAT]
dodges14 = [a for a in out14 if a['moveType'] == choreo.MOVE_DODGE]

check(f"le schivate compaiono davvero ({len(dodges14)} su "
      f"{len(squats14) + len(dodges14)} 'squat originali') - e' il problema "
      f"che questa ripartizione esiste per risolvere",
      len(dodges14) > 0)

# LA COSA CHE PRIMA NON ANDAVA: niente allo stesso istante di una schivata.
per_istante = {}
for a in out14:
    per_istante.setdefault(round(a['startTime'], 6), []).append(a)
simultanee_alla_schivata = [
    (t, [x['moveType'] for x in g]) for t, g in per_istante.items()
    if len(g) > 1 and any(x['moveType'] == choreo.MOVE_DODGE for x in g)]
check(f"nessuna schivata ha qualcosa nel suo stesso istante "
      f"(trovate {len(simultanee_alla_schivata)} sovrapposizioni)",
      not simultanee_alla_schivata)

# E NEMMENO TROPPO VICINO: un beat intero libero, come nel repertorio.
ordinate = sorted(out14, key=lambda a: a['beatNumber'])
troppo_vicine = []
for prima, dopo in zip(ordinate, ordinate[1:]):
    if choreo.MOVE_DODGE not in (prima['moveType'], dopo['moveType']):
        continue
    if (dopo['beatNumber'] - prima['beatNumber']) < choreo.MIN_GAP_DODGE_BEATS - 1e-6:
        troppo_vicine.append((prima['beatNumber'], dopo['beatNumber']))
check(f"ogni schivata ha almeno {choreo.MIN_GAP_DODGE_BEATS} beat liberi da "
      f"cio' che le sta accanto, come le dieci schivate ufficiali del gioco "
      f"(violazioni: {len(troppo_vicine)})",
      not troppo_vicine)

# e la coppia, se qualcuno prova a costruirla a mano, NON deve sopravvivere
coppia_a_mano = [
    {'startTime': 30.0, 'beatNumber': 60.0, 'moveType': choreo.MOVE_DODGE,
     'moveChannel': choreo.CH_CENTER, '_exact': True, '_sidecar': True},
    {'startTime': 30.0, 'beatNumber': 60.0, 'moveType': choreo.MOVE_JAB,
     'moveChannel': choreo.CH_FRONT, '_exact': True, '_sidecar': True},
]
risolta = choreo.enforce_playability(coppia_a_mano, fake_beats(bpm=120.0, n=200),
                                     snap_to_grid=False)
check(f"una coppia Dodge+Jab costruita a mano viene ridotta a una mossa sola "
      f"da enforce_playability (rimaste {len(risolta)}, attesa 1)",
      len(risolta) == 1)

print("\n" + "=" * 52)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
