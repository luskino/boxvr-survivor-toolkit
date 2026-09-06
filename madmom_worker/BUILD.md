# madmom_worker.exe — come ricompilarlo

Sottoprocesso esterno usato da `boxvr_generator.py` (motore beat-tracking
"madmom", opzionale) quando l'utente sceglie il motore piu' lento ma piu'
robusto ai cambi di tempo locali. Vive fuori dall'ambiente Python del tool
principale perche' **madmom non supporta Python 3.14** (il progetto gira su
3.14, madmom si ferma a 3.9-3.12) — vedi `boxvr_generator.md` in memoria per
il dettaglio completo e i dati di validazione.

## Serve solo per ricompilare da zero (raro)

L'exe compilato vive già in `madmom_worker.exe` (accanto a questa cartella,
nella root del progetto) — questi passaggi servono solo se va rifatto da capo
(es. dopo un aggiornamento di madmom, o se l'exe viene perso).

1. **Serve un compilatore C++** (Visual C++ Build Tools 2022, workload
   "Desktop development with C++" / `Microsoft.VisualStudio.Workload.VCTools`)
   — richiede privilegi di amministratore per l'installazione (UAC), non
   automatizzabile da un agente non interattivo.
2. **Serve Python 3.10** (non 3.14), installato a parte rispetto
   all'interprete con cui gira il tool.
3. Creare un venv Python 3.10 dedicato, installare `numpy>2 scipy>=1.13
   cython wheel setuptools mido soundfile pyinstaller`.
4. Clonare madmom **dal sorgente git**, non da PyPI (la release PyPI del 2018
   e' rotta su Python/numpy moderni): `git clone --recursive
   https://github.com/CPJKU/madmom.git` — il flag `--recursive` è
   obbligatorio, `madmom/models` è un submodule separato con i pesi
   pre-addestrati.
5. Compilare madmom dentro un ambiente MSVC inizializzato (`vcvars64.bat`),
   NON semplicemente `pip install madmom` dal venv nudo — l'auto-detection di
   setuptools per MSVC in questo ambiente non trova da sola le variabili
   INCLUDE/LIB necessarie:
   ```bat
   call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
   <path-al-venv>\Scripts\python.exe -m pip install --no-build-isolation <path-al-clone-madmom>
   ```
6. Compilare `madmom_worker.py` in un exe standalone:
   ```bat
   <path-al-venv>\Scripts\python.exe -m PyInstaller --noconfirm --onefile --console --name "madmom_worker" --collect-all madmom madmom_worker.py
   ```
7. Copiare `dist\madmom_worker.exe` nella root del progetto (accanto a
   `boxvr_generator.py`) **e** in `dist\` accanto all'exe principale quando si
   fa una build di release — il worker va distribuito insieme all'app, non è
   bundlato dentro l'exe principale (PyInstaller separati, uno per Python 3.14
   e uno per Python 3.10, non possono fondersi in un solo file).

## Dove il codice lo cerca

`boxvr_generator.py:_find_madmom_worker()` cerca, in ordine: accanto
all'eseguibile principale (build compilata), nella cartella del progetto
(esecuzione da sorgente), poi `madmom_worker/dist/`. Se non lo trova, la
modalità madmom viene trattata come non disponibile (mai un crash) — vedi
`MadmomUnavailableError`.
