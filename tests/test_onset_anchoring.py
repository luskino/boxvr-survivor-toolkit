"""Verifica l'ancoraggio dei colpi agli accenti reali (25/08 sera).

Copre la catena completa che ha richiesto piu' iterazioni per essere corretta:
1. _place_moves_on_onsets piazza sugli accenti quando ce ne sono abbastanza.
2. Le azioni marcate '_exact' sopravvivono a enforce_playability invece di
   essere rimesse sulla griglia (il bug principale di stasera).
3. _strip_overlaps non toglie le azioni esatte per far posto a figure iniettate.
4. _apply_rhythm_events e _apply_section_accents rispettano skip_spans, cosi'
   non iniettano figure ridondanti dentro un segmento gia' ancorato.
5. Caso reale: il riff di Master Of Puppets, sul percorso di produzione vero.
"""
import os
import sys

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brano_di_prova import audio_di_prova
import boxvr_choreo as c

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


def fake_beats(bpm=120.0, n=40):
    bl = 60.0 / bpm
    return [{'_triggerTime': i * bl, '_beatLength': bl} for i in range(n)]


print("1. _place_moves_on_onsets: abbastanza accenti -> piazza ed esce True")
beats = fake_beats()
actions = []
onsets = [0.10, 0.55, 1.30, 2.05]  # 4 accenti, sopra MIN_ONSET_COUNT
# move_defs ora e' (moveType, posizione relativa nel pattern), non piu'
# (moveType, moveChannel) - vedi la correzione del 25/08 notte sulla forma
# del pattern.
move_defs = [(c.MOVE_JAB, 0), (c.MOVE_HOOK, 1)]
ok = c._place_moves_on_onsets(actions, onsets, 0.0, 3.0, target_n=8,
                              move_defs=move_defs, beats=beats, n_beats=len(beats))
check("ritorna True", ok is True)
check(f"piazza tutti gli accenti disponibili quando sono meno del target ({len(actions)})",
      len(actions) == len(onsets))
check("ogni azione e' marcata _exact",
      all(a.get('_exact') for a in actions))
check("gli startTime coincidono ESATTAMENTE con gli onset (nessun arrotondamento)",
      sorted(a['startTime'] for a in actions) == sorted(onsets))

print("\n2. Sotto MIN_ONSET_COUNT: ripiega, non tocca `actions`")
actions2 = []
ok2 = c._place_moves_on_onsets(actions2, [0.10, 0.55], 0.0, 3.0, target_n=8,
                               move_defs=move_defs, beats=beats, n_beats=len(beats))
check("ritorna False con solo 2 accenti (sotto MIN_ONSET_COUNT=3)", ok2 is False)
check("non ha scritto nulla in actions", actions2 == [])

print("\n3. Mosse centrali (Block/Squat/Dodge) restano SEMPRE al centro")
actions3 = []
move_defs_centro = [(c.MOVE_SQUAT, 0), (c.MOVE_JAB, 1)]
c._place_moves_on_onsets(actions3, [0.1, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5], 0.0, 4.0, target_n=8,
                         move_defs=move_defs_centro, beats=beats, n_beats=len(beats))
squats = [a for a in actions3 if a['moveType'] == c.MOVE_SQUAT]
check(f"gli squat sono su CH_CENTER anche se il pattern diceva CH_FRONT ({[a['moveChannel'] for a in squats]})",
      squats and all(a['moveChannel'] == c.CH_CENTER for a in squats))
jabs = [a for a in actions3 if a['moveType'] == c.MOVE_JAB]
check("i jab alternano CH_FRONT/CH_BACK (non ereditano CH_FRONT fisso dal pattern)",
      len(set(a['moveChannel'] for a in jabs)) > 1)

print("\n4. enforce_playability NON rimette sulla griglia le azioni '_exact'")
beats2 = fake_beats(bpm=120.0, n=20)  # beat_len = 0.5s, quindi la griglia sta su 0.0/0.25/0.5/...
esatta = {'startTime': 0.313, 'beatNumber': 0.6, 'moveType': c.MOVE_JAB,
          'moveChannel': c.CH_FRONT, '_exact': True}
out = c.enforce_playability([esatta], beats2)
check(f"lo startTime resta 0.313, non arrotondato a un punto di griglia ({out[0]['startTime'] if out else 'SCARTATA'})",
      len(out) == 1 and out[0]['startTime'] == 0.313)

print("\n5. _strip_overlaps non toglie le azioni '_exact'")
esatta2 = dict(esatta)
figura_iniettata = [{'startTime': 0.30, 'moveType': c.MOVE_HOOK, 'moveChannel': c.CH_BACK, '_injected': True}]
kept = c._strip_overlaps([esatta2], figura_iniettata, [b['_triggerTime'] for b in beats2])
check("l'azione esatta sopravvive anche se una figura iniettata cade a 10ms di distanza",
      esatta2 in kept)

print("\n6. Coesistenza (25/08, sostituisce skip_spans): _apply_rhythm_events PUO'")
print("   iniettare dentro una zona gia' ancorata, ma enforce_playability non")
print("   sposta mai l'accento vero per farle posto")
events = [{'type': 'burst', 'start': 0.30, 'end': 0.60, 'onsets': [0.30, 0.40, 0.50]}]
out2 = c._apply_rhythm_events([dict(esatta)], events, beats2, preset='medium')
check(f"la raffica inietta normalmente anche vicino a un accento esatto (trovate {len(out2)} azioni)",
      len(out2) > 1)
final2 = c.enforce_playability(out2, beats2)
esatta_sopravvive = [a for a in final2 if a.get('_exact')]
check(f"l'accento esatto resta AL SUO istante originale dopo enforce_playability "
      f"(trovato: {[round(a['startTime'],3) for a in esatta_sopravvive]}, atteso {esatta['startTime']})",
      len(esatta_sopravvive) == 1 and esatta_sopravvive[0]['startTime'] == esatta['startTime'])

print("\n7. Caso reale: il riff di Master Of Puppets sul percorso di produzione")
import os
import boxvr_generator as gen
mp3 = audio_di_prova('MoP intro riff.wav')
if os.path.isfile(mp3):
    r = gen.analyze_for_generate(mp3, engine_mode='auto')
    a = r['analysis']
    acts = c.build_move_actions(a, preset='medium')
    veri = [0.311, 1.425, 1.756, 2.038]
    trovati = sum(1 for v in veri if any(abs(x['startTime'] - v) < 0.01 for x in acts))
    check(f"tutti e 4 gli accenti reali del riff sono esatti al millisecondo (trovati {trovati}/4)",
          trovati == 4)
else:
    print("  (clip di test non trovata, salto - non e' un fallimento del codice)")

print("\n8. Block prima di un gancio/montante richiede il gap pieno (misurato: 1.0 beat, non 0.5)")
blocco = {'moveType': c.MOVE_BLOCK, 'moveChannel': c.CH_CENTER}
check("Block -> Hook richiede MIN_GAP_ARM_BEATS",
      c._required_gap_beats(blocco, {'moveType': c.MOVE_HOOK, 'moveChannel': c.CH_FRONT}) == c.MIN_GAP_ARM_BEATS)
check("Block -> Uppercut richiede MIN_GAP_ARM_BEATS",
      c._required_gap_beats(blocco, {'moveType': c.MOVE_UPPERCUT, 'moveChannel': c.CH_BACK}) == c.MIN_GAP_ARM_BEATS)
check("Block -> Jab resta al gap base (comportamento invariato)",
      c._required_gap_beats(blocco, {'moveType': c.MOVE_JAB, 'moveChannel': c.CH_FRONT}) == c.MIN_GAP_BEATS)

print("\n9. Spazio stretto verso un accento -> Jab forzato al posto di gancio/montante")
beats9 = fake_beats(bpm=120.0, n=20)  # beat_len = 0.5s
# tre onset (sopra MIN_ONSET_COUNT per ingaggiare l'ancoraggio): i primi due
# larghi, il terzo a 0.49 beat dal secondo (poco sotto il minimo 0.5) - il
# pattern vorrebbe un Hook li', deve diventare un Jab.
onsets9 = [0.10, 0.60, 0.60 + 0.49 * 0.5]
actions9 = []
# posizione k=2 (il terzo onset, quello con lo spazio stretto) e' un Hook nel
# pattern originale - deve diventare Jab una volta piazzato. span_beats=3
# esplicito (non il default 16 dei pattern veri) perche' qui vogliamo che le
# 3 posizioni relative 0/1/2 coprano l'intero segmento di test, non solo il
# suo primissimo ottavo.
move_defs9 = [(c.MOVE_JAB, 0), (c.MOVE_JAB, 1), (c.MOVE_HOOK, 2)]
c._place_moves_on_onsets(actions9, onsets9, 0.0, 1.5, target_n=3,
                         move_defs=move_defs9, beats=beats9, n_beats=len(beats9), span_beats=3)
check(f"il terzo colpo diventa Jab invece di Hook quando lo spazio e' sotto 0.6 beat "
      f"(trovati {len(actions9)} colpi, tipi {[a['moveType'] for a in actions9]})",
      len(actions9) == 3 and actions9[2]['moveType'] == c.MOVE_JAB)

print("\n10. Tolleranza jitter: due accenti veri a 0.495 beat (poco sotto il minimo 0.5) "
      "restano ENTRAMBI esatti")
beats10 = fake_beats(bpm=107.0, n=30)
bl10 = 60.0 / 107.0
a1 = {'startTime': 1.0, 'beatNumber': 2.0, 'moveType': c.MOVE_JAB, 'moveChannel': c.CH_FRONT, '_exact': True}
a2 = {'startTime': 1.0 + 0.495 * bl10, 'beatNumber': 2.495, 'moveType': c.MOVE_JAB,
      'moveChannel': c.CH_BACK, '_exact': True}
out10 = c.enforce_playability([a1, a2], beats10)
check(f"entrambi restano ai loro istanti esatti (trovati {len(out10)}: "
      f"{[round(x['startTime'],3) for x in out10]}, attesi {[round(a1['startTime'],3), round(a2['startTime'],3)]})",
      len(out10) == 2 and {round(x['startTime'], 3) for x in out10} ==
      {round(a1['startTime'], 3), round(a2['startTime'], 3)})

print("\n11. Livello di priorita' nuovo (25/08): un'azione '_exact' NON '_protected'")
print("    non viene mai spostata dal passaggio 3, nemmeno per fare posto a una")
print("    figura protetta vicina - prima di questa correzione finiva nell'ultimo")
print("    livello (sposta-o-scarta) insieme al resto, protetta solo per caso da")
print("    skip_spans quando le due cose non potevano mai incontrarsi")
beats11 = fake_beats(bpm=120.0, n=20)  # beat_len = 0.5s
esatta11 = {'startTime': 1.0, 'beatNumber': 2.0, 'moveType': c.MOVE_JAB,
            'moveChannel': c.CH_FRONT, '_exact': True}
# una figura protetta con un colpo troppo vicino (0.1 beat) - in conflitto
# diretto con l'accento vero. Nel design vecchio (2 livelli) l'accento vero
# stava nello stesso livello "tutto il resto" e poteva essere quello scartato
# o spostato a seconda dell'ordine di iterazione; nel nuovo design (3 livelli)
# l'accento vero e' sempre gia' piazzato prima che la figura protetta venga
# valutata, quindi e' SEMPRE la figura a cedere.
figura_vicina = {'startTime': 1.05, 'beatNumber': 2.1, 'moveType': c.MOVE_JAB,
                  'moveChannel': c.CH_BACK, '_protected': True, '_figure': 'jab_combo'}
out11 = c.enforce_playability([esatta11, figura_vicina], beats11)
esatta_out = [a for a in out11 if a.get('_exact')]
check(f"l'accento vero resta ESATTAMENTE al suo istante (trovato {[round(a['startTime'],3) for a in esatta_out]})",
      len(esatta_out) == 1 and esatta_out[0]['startTime'] == 1.0)
check(f"la figura protetta in conflitto viene scartata, non l'accento vero (azioni finali: {len(out11)})",
      len(out11) == 1)

print("\n12. Preservazione della FORMA del pattern (25/08 notte): il difetto reale")
print("    segnalato in VR - 'AutoSeq_Compl_3_D, 8 montanti a coppie, si")
print("    comprime in una raffica su accenti fitti' - non deve piu' accadere")
beats12 = fake_beats(bpm=120.0, n=20)  # beat_len = 0.5s
# Il pattern VERO estratto dal gioco: 8 montanti a coppie, beat 0,1 - pausa
# di 3 beat - 4,5 - pausa - 8,9 - pausa - 12,13 (vedi STATO E ROADMAP.md).
move_defs12 = [(c.MOVE_UPPERCUT, 0), (c.MOVE_UPPERCUT, 1), (c.MOVE_UPPERCUT, 4), (c.MOVE_UPPERCUT, 5),
               (c.MOVE_UPPERCUT, 8), (c.MOVE_UPPERCUT, 9), (c.MOVE_UPPERCUT, 12), (c.MOVE_UPPERCUT, 13)]
# accenti reali DENSI su tutto il segmento (8s = 16 beat) - il caso "raffica"
# che comprimeva le coppie: un accento ogni 0.2s, 40 in tutto.
onsets12 = [round(0.2 * i, 3) for i in range(40)]
actions12 = []
ok12 = c._place_moves_on_onsets(actions12, onsets12, 0.0, 8.0, target_n=8,
                                move_defs=move_defs12, beats=beats12, n_beats=len(beats12),
                                span_beats=16)
times12 = sorted(a['startTime'] for a in actions12)
gaps12 = [(times12[i + 1] - times12[i]) / 0.5 for i in range(len(times12) - 1)]
check(f"piazza tutti e 8 i montanti (trovati {len(actions12)})", len(actions12) == 8)
pair_gaps = gaps12[0::2]    # dentro ogni coppia: 0-1, 2-3, 4-5, 6-7
pause_gaps = gaps12[1::2]   # fra una coppia e la successiva: 1-2, 3-4, 5-6
check(f"le distanze DENTRO ogni coppia restano corte (trovate {[round(g,2) for g in pair_gaps]} beat, "
      f"attese < 1.2, contro il pattern originale di 1.0)",
      all(g < 1.2 for g in pair_gaps))
check(f"le distanze FRA una coppia e la successiva restano lunghe, non compresse "
      f"(trovate {[round(g,2) for g in pause_gaps]} beat, attese > 2.0, contro il pattern originale di 3.0)",
      all(g > 2.0 for g in pause_gaps))

print("\n13. Caso reale: il riff dell'intro di Master Of Puppets sul BRANO INTERO")
print("    (non la clip di test) - 'sono stato fermo tutto il tempo... il")
print("    riff nemmeno tracciato', ancora silenziato dopo structural_energy_rank")
mp3_full = audio_di_prova('Master Of Puppets.mp3')
if os.path.isfile(mp3_full):
    analysis_full = gen.generate_song_analysis(mp3_full)
    seg_energies = c.segment_energies(analysis_full)
    rank_full = c.structural_energy_rank(analysis_full, seg_energies)
    intensities_full = c.energies_to_intensities(seg_energies, 'medium', rank=rank_full)
    check("il segmento dell'intro (indice 0) e' ancora classificato 'silenzio vero' "
          "dalla sola energia (precondizione del test, non l'esito)",
          intensities_full[0] == 0)
    acts_full = c.build_move_actions(analysis_full, preset='medium')
    intro_acts = [a for a in acts_full if a['startTime'] < 18.0]
    check(f"il pavimento di attivita' reale forza il segmento ad attivarsi comunque "
          f"(trovate {len(intro_acts)} azioni nei primi 18s, erano 0 prima della correzione)",
          len(intro_acts) >= c.MIN_ONSET_COUNT)
else:
    print("  (mp3 di prova non trovato, salto - non e' un fallimento del codice)")

print("\n" + "=" * 56)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
