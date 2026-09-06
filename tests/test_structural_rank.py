"""Verifica il percentile a due livelli (macroblocco + locale),
2026-08-25: sostituisce il solo percentile sull'intero brano per decidere
quali momenti diventano vero silenzio - nato dal caso reale di Master Of
Puppets (l'intro forte finiva al 9 percentile del brano intero e veniva
zittita)."""
import sys

# La radice del progetto si ricava da dove sta questo file - che sta in
# tests/, quindi i moduli stanno un livello sopra. Cablare un percorso
# assoluto qui funzionerebbe solo sul computer di chi lo ha scritto.
import os
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brano_di_prova import audio_di_prova
import boxvr_choreo as m

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


def fake_analysis(labels, seg_mode='structural'):
    segs = [{'_sectionLabel': lab, '_index': i} for i, lab in enumerate(labels)]
    return {'segs': segs, 'seg_mode': seg_mode}


print("1. _percentile_ranks: casi base")
r = m._percentile_ranks([('a', 1.0), ('b', 3.0), ('c', 2.0)])
check("ordina correttamente (a=0, c=0.5, b=1)", r == {'a': 0.0, 'c': 0.5, 'b': 1.0})
check("una sola voce -> rank 1.0 (non forzata al silenzio)",
      m._percentile_ranks([('x', 0.001)]) == {'x': 1.0})
check("lista vuota -> dict vuoto", m._percentile_ranks([]) == {})

print("\n2. structural_energy_rank: ricalca il caso reale di Master Of Puppets")
# stessa struttura del brano vero: gruppo 'A' = intro (3 occorrenze),
# altri gruppi piu' carichi -> l'intro finisce bassa sul percentile GLOBALE
labels = ['A', 'A', 'C', 'D', 'D', 'F', 'F', 'B', 'C', 'D', 'E', 'G', 'G',
          'B', 'C', 'C', 'A', 'B', 'B', 'C', 'D', 'E', 'B']
energies = [0.101, 0.137, 0.157, 0.154, 0.163, 0.144, 0.150, 0.158, 0.153,
            0.154, 0.139, 0.099, 0.172, 0.202, 0.199, 0.191, 0.196, 0.145,
            0.193, 0.187, 0.180, 0.162, 0.164]
a = fake_analysis(labels)
rank = m.structural_energy_rank(a, energies)

flat = m._percentile_ranks(list(enumerate(energies)))
flat_rank_seg1 = flat[1]
check(f"col percentile PIATTO il riff (indice 1) sarebbe basso (misurato {flat_rank_seg1:.2f}, atteso circa 0.09)",
      flat_rank_seg1 < 0.15)
check(f"col rank a DUE LIVELLI il riff (indice 1) supera la soglia di silenzio 0.15 (misurato {rank[1]:.2f})",
      rank[1] >= 0.15)
check(f"l'apertura genuinamente muta (indice 0) resta sotto soglia (misurato {rank[0]:.2f})",
      rank[0] < 0.15)

print("\n3. Ricadute (fallback) quando il livello macro non ha senso")
a_fixed = fake_analysis(['A', 'B', 'C'], seg_mode='fixed')
r_fixed = m.structural_energy_rank(a_fixed, [0.1, 0.5, 0.9])
r_flat_expected = [m._percentile_ranks(list(enumerate([0.1, 0.5, 0.9])))[i] for i in range(3)]
check("seg_mode fisso -> ricade sul percentile piatto (nessun gruppo macro)",
      r_fixed == r_flat_expected)

a_one_group = fake_analysis(['X', 'X', 'X'], seg_mode='structural')
r_one = m.structural_energy_rank(a_one_group, [0.1, 0.5, 0.9])
check("un solo gruppo -> ricade sul percentile piatto (nessuna info macro da aggiungere)",
      r_one == r_flat_expected)

check("lista vuota -> lista vuota", m.structural_energy_rank(fake_analysis([]), []) == [])

print("\n4. energies_to_intensities: il parametro rank opzionale non rompe l'uso esistente")
old_style = m.energies_to_intensities([0.1, 0.5, 0.9], preset='medium')
check("senza rank esplicito, comportamento identico a prima (nessuna regressione)",
      len(old_style) == 3 and old_style[0] == 0)  # il piu' basso resta silenzio come sempre
custom = m.energies_to_intensities([0.1, 0.5, 0.9], preset='medium', rank=[0.9, 0.5, 0.1])
check("con un rank esplicito, lo usa invece di ricalcolarlo dal valore assoluto",
      custom[0] != old_style[0] or custom[2] != old_style[2])

print("\n5. Integrazione end-to-end: Master Of Puppets reale, l'intro ora riceve mosse")
import boxvr_generator as gen
MP3 = audio_di_prova('Master Of Puppets.mp3')
import os
if os.path.exists(MP3):
    analysis = gen.generate_song_analysis(MP3)
    actions = m.build_move_actions(analysis, preset='medium')
    first_30s = [act for act in actions if act['startTime'] < 30.0]
    check(f"i primi 30s ora contengono almeno una mossa (trovate {len(first_30s)}, prima erano ~0)",
          len(first_30s) > 0)
else:
    print("  (mp3 non trovato, saltato)")

print("\n" + "=" * 52)
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
