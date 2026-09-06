@echo off
REM Crea BoxVR_Level_Fixer_v<versione>.exe in dist\ a partire da boxvr_fixer_gui.py
REM
REM Un solo eseguibile: correzione e generazione condividono timeline,
REM riproduttore, anteprima e temi, e ormai vogliono anche stati OPPOSTI del
REM gioco (la correzione ha effetto solo con il gioco non patchato, la
REM generazione solo con quello patchato) - quindi non si distinguono piu' con
REM due file diversi, ma con una schermata di ingresso che l'utente sceglie
REM ogni volta all'avvio (vedi BoxVRFixerApp._build_mode_chooser).
REM
REM Ogni build usa version.py per il numero di versione, cosi' non sovrascrive
REM mai un eseguibile gia' creato in precedenza - per una nuova release, alza
REM VERSION in version.py PRIMA di lanciare questo script.
REM Richiede: pip install numpy scipy tkinterdnd2 sounddevice librosa soundfile mutagen customtkinter pyinstaller

cd /d "%~dp0"

for /f "delims=" %%v in ('python -c "from version import VERSION; print(VERSION)"') do set VERSION=%%v

pyinstaller --noconfirm --onefile --windowed ^
    --name "BoxVR_Level_Fixer_v%VERSION%" ^
    --collect-all tkinterdnd2 ^
    --collect-all sounddevice ^
    --collect-all librosa ^
    --collect-all soundfile ^
    --collect-all mutagen ^
    --collect-all customtkinter ^
    --add-data "fonts;fonts" ^
    --add-data "data\icons;data\icons" ^
    --add-data "data\training_sequences.json;data" ^
    --add-data "assets\sfx;assets\sfx" ^
    --add-data "sidecar sandbox\engine.py;sidecar sandbox" ^
    --hidden-import boxvr_extract ^
    boxvr_fixer_gui.py

REM --add-data "sidecar sandbox\engine.py" (26/08 notte): il motore della
REM sidecar viene caricato a RUNTIME da generate_track (sys.path.insert su
REM 'sidecar sandbox' accanto a boxvr_generator.py, poi `import engine`),
REM non con un import normale in cima a un file - PyInstaller lo analizza
REM staticamente per capire cosa impacchettare, quindi un import cosi' non
REM sarebbe MAI stato incluso da solo (verificato: --hidden-import non basta,
REM serve il FILE vero, perche' generate_track lo importa per nome di modulo
REM da un percorso, non da un pacchetto Python normale). Senza questa riga
REM l'exe si sarebbe avviato ed eseguito normalmente, e sarebbe fallito SOLO
REM quando un utente prova davvero a generare con marker sidecar attivi -
REM il tipo di buco che si scopre solo provando la funzione, non compilando.

pyinstaller --noconfirm --onefile --windowed ^
    --name "BoxVR_Playlist_Manager_v%VERSION%" ^
    --collect-all customtkinter ^
    boxvr_playlist_manager_gui.py

REM BoxVR_Playlist_Manager (30/08 notte): tool SEPARATO per gestire le
REM playlist gia' installate (rinomina/riordina/rimuovi brani/elimina) -
REM deliberatamente un secondo eseguibile a se stante, non una scheda in
REM piu' dentro l'app principale, coerente con "tool separato" della
REM roadmap. Non ha bisogno di tkinterdnd2/sounddevice/librosa/soundfile/
REM mutagen (nessuna analisi audio ne' drag&drop qui) - solo customtkinter,
REM quindi un --collect-all minimo invece di ripetere l'elenco completo.

copy /Y "%~dp0madmom_worker.exe" "%~dp0dist\madmom_worker.exe" >nul
REM madmom_worker.exe (motore beat-tracking "Precisione extra", opzionale) va
REM SEMPRE accanto all'exe principale in dist\ - e' un eseguibile a se' stante
REM (compilato da un venv Python 3.10 separato, madmom non supporta 3.14),
REM non viene bundlato dentro l'exe di sopra. Se manca in madmom_worker.exe
REM nella root del progetto, vedi madmom_worker\BUILD.md per ricompilarlo -
REM l'app resta comunque funzionante senza, il motore si disabilita da solo.

REM --add-data: si impacchetta SOLO cio' che viene letto a runtime, non l'intera
REM cartella data\. Fino al 25/08 la riga era --add-data "data;data", che ci
REM infilava dentro anche data\official_workouts\ (27MB) e data\reference_maps\
REM (6.9MB): materiale di RICERCA, con zero riferimenti nei sorgenti - 34MB di
REM eseguibile per file che nessuno apre mai. Verificato con un grep prima di
REM toglierli. Quello che resta:
REM   - data\icons\ (168KB): le icone dell'anteprima visiva (pugni, montanti,
REM     ganci, parata), convertite una volta sola da SVG a PNG in fase di
REM     sviluppo - niente libreria SVG a runtime dentro l'eseguibile.
REM   - data\training_sequences.json (44KB): il repertorio ufficiale dei pattern.
REM     Da qui in poi il tool sa ESTRARLO da solo dalla copia del gioco
REM     dell'utente quando si installa la patch (boxvr_extract.py), quindi qui
REM     resta solo come ripiego per chi aggiorna senza riapplicare la patch.
REM     >>> ALLA PUBBLICAZIONE OPEN SOURCE VA TOLTO: e' contenuto creativo di
REM     FitXR e non va ridistribuito. Vedi STATO E ROADMAP.md, sezione 3-bis.
REM
REM --hidden-import boxvr_extract: boxvr_patch lo importa DENTRO una funzione
REM (import pigro, cosi' gli script di analisi che usano boxvr_choreo non se lo
REM tirano dietro). Dichiararlo esplicitamente evita di dipendere dal fatto che
REM l'analisi statica di PyInstaller peschi anche gli import annidati.

echo.
echo Eseguibili creati in:
echo   %~dp0dist\BoxVR_Level_Fixer_v%VERSION%.exe
echo   %~dp0dist\BoxVR_Playlist_Manager_v%VERSION%.exe
pause
