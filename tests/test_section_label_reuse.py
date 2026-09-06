"""Verifica un bug reale trovato il 30/08 mentre si misurava l'affidabilita'
delle etichette strutturali per la ripetizione di ritornelli: quando la
generazione reale riusa i confini di sezione gia' calcolati nell'anteprima
(`boundary_bars`, per coerenza - qm-segmenter non e' deterministico), le
ETICHETTE (`_sectionLabel`) non venivano rilette insieme ai confini e
restavano SEMPRE None - un peggioramento silenzioso per qualunque logica in
boxvr_choreo.py che cerca sezioni ricorrenti (es. stessa combo su un
ritornello che si ripete), presente solo nella generazione vera, mai
nell'anteprima (dove le etichette si calcolano sempre da zero)."""
import os
import sys

# La radice si ricava da dove sta questo file, e il brano da
# brano_di_prova: cablare l'una e l'altro funzionava solo sul
# computer di chi li ha scritti (vedi brano_di_prova.py).
# la radice del progetto: questo file sta in tests/, i moduli
# stanno un livello sopra
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brano_di_prova import audio_di_prova
import boxvr_generator as gen

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        print(f"  OK   {label}")
        passed += 1
    else:
        print(f"  FAIL {label}")
        failed += 1


mp3 = audio_di_prova('Chop Suey!.mp3')

# passo 1: analisi come farebbe l'ANTEPRIMA (nessun boundary_bars dato,
# section_rows calcolato da zero) - qui le etichette funzionano gia'
preview_analysis = gen.generate_song_analysis(mp3, structural_segments=True)
check("anteprima: modalita' strutturale raggiunta",
      preview_analysis['seg_mode'] == 'structural')
labels_preview = [s.get('_sectionLabel') for s in preview_analysis['segs']]
check(f"anteprima: le etichette sono valorizzate (non tutte None) "
      f"(trovate: {sorted(set(labels_preview))})",
      any(l is not None for l in labels_preview))

# passo 2: la GENERAZIONE VERA riusa i confini dell'anteprima, esattamente
# come fa _start_processing (boundary_bars=analysis.get('seg_boundary_bars'))
real_analysis = gen.generate_song_analysis(
    mp3, structural_segments=True, boundary_bars=preview_analysis['seg_boundary_bars'])
check("generazione reale: modalita' strutturale raggiunta (confini riusati)",
      real_analysis['seg_mode'] == 'structural')
labels_real = [s.get('_sectionLabel') for s in real_analysis['segs']]
check(f"generazione reale: le etichette sono valorizzate ANCHE QUI, non tutte None "
      f"(trovate: {sorted(set(labels_real))}) - QUESTO era il bug",
      any(l is not None for l in labels_real))

# le etichette devono essere le STESSE viste in anteprima, non un
# ricalcolo diverso (la cache garantisce ripetibilita')
check("le etichette recuperate coincidono esattamente con quelle dell'anteprima",
      labels_real == labels_preview)

# caso limite: se la cache non ha nulla per questo brano (chiave sconosciuta),
# il fallback resta 'tutte None' come prima del fix - nessun crash
fake_boundary_bars = preview_analysis['seg_boundary_bars']
import boxvr_generator as gen2
orig_load = gen2.load_cached_sections
gen2.load_cached_sections = lambda key: None
try:
    degraded_analysis = gen2.generate_song_analysis(
        mp3, structural_segments=True, boundary_bars=fake_boundary_bars)
    check("cache assente: nessuna eccezione, fallback a 'tutte None' come prima del fix",
          all(s.get('_sectionLabel') is None for s in degraded_analysis['segs']))
finally:
    gen2.load_cached_sections = orig_load

print(f"\n{'====================================================' }")
print(f"{passed} passati, {failed} falliti")
sys.exit(1 if failed else 0)
