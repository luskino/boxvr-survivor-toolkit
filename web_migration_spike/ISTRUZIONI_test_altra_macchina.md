# Istruzioni per Claude — test su una macchina diversa

Questo file, insieme a `webview2_check.py` e `audio_latency_test.py`, ti è
stato copiato su un computer diverso da quello dove è nato il progetto
"BoxVR Songs Tool". Non hai (e non ti serve) il resto del progetto: questi
due script sono completamente autosufficienti.

## Contesto (breve, tanto quanto basta)

Un progetto Python sta migrando un tool desktop da un'interfaccia Tkinter a
una web-based (pywebview, cioè una finestra nativa che mostra HTML/JS con
un ponte verso Python). Due rischi tecnici erano rimasti aperti e non
verificabili sulla macchina di sviluppo originale perché troppo "sporca"
(headset VR Oculus, Steam Streaming, Virtual Desktop — tanti dispositivi
audio virtuali che confondevano le misure):

1. **WebView2 Runtime**: pywebview su Windows si appoggia al runtime
   "Microsoft Edge WebView2". Sulla macchina originale era già installato,
   quindi non era possibile verificare cosa succede quando MANCA, né
   testare per davvero l'installazione automatica silenziosa già scritta.
2. **Latenza audio reale**: quanto tempo passa fra "il browser dice di
   suonare un click" e "il click arriva davvero al microfono/altoparlante".
   Sulla macchina originale il risultato era ~355ms, sospettosamente alto,
   e il test di controllo continuava a fallire per colpa dei troppi
   dispositivi audio virtuali in competizione.

Il tuo compito: eseguire questi due script su QUESTA macchina (si spera più
semplice/pulita) e riportare i risultati esatti all'utente, che li girerà
alla sessione Claude originale per l'interpretazione finale. Non devi
interpretare tu i numeri nel dettaglio — riportali fedelmente, con il
contesto che hai raccolto (quali dispositivi hai scelto, se qualcosa è
fallito, ecc.).

## Passo 1 — prerequisiti

Verifica se Python è installato (`python --version`, deve essere 3.9+). Se
manca, installalo prima di procedere (chiedi conferma all'utente prima di
scaricare/installare qualunque cosa, come da tua prassi normale).

Poi installa le dipendenze:
```bash
pip install pywebview sounddevice soundfile numpy
```

## Passo 2 — test WebView2

```bash
cd <cartella dove hai copiato i due file>
python webview2_check.py
```

- Se dice **"TROVATO"**: questa macchina ha già WebView2 - non è utile per
  testare lo scenario "runtime mancante". Riportalo all'utente e basta,
  nessun altro comando da lanciare per questa parte.
- Se dice **"NON TROVATO"**: ecco lo scenario interessante. Chiedi
  esplicitamente conferma all'utente prima di procedere (questo script,
  con `--install`, scarica ~2MB da Microsoft ed esegue un'installazione
  silenziosa sul sistema - è un'azione reale, non va lanciata senza che
  l'utente sappia cosa succede):
  ```bash
  python webview2_check.py --install
  ```
  Riporta l'esito esatto (successo/fallimento, eventuali errori stampati).

## Passo 3 — test latenza audio

```bash
python audio_latency_test.py --list-devices
```

Chiedi all'utente di indicarti (o di scegliere lui stesso) quale
microfono è fisicamente vicino agli altoparlanti reali di questa
macchina — su un portatile normale probabilmente basta il microfono
integrato, che spesso è già vicino agli altoparlanti integrati. Poi:

```bash
python audio_latency_test.py --input-device "parte del nome del microfono"
```

(Lo script cerca per sottostringa nel nome, non per numero — gli indici
numerici dei dispositivi audio si sono dimostrati instabili fra
un'esecuzione e l'altra sulla macchina originale, meglio il nome.)

Lo script fa partire 5 click brevi in sequenza (~15 secondi) e stampa un
riepilogo JSON con la latenza media/mediana/min/max in millisecondi,
salvato anche in `audio_latency_result.json` nella stessa cartella.

**Se lo script dice "nessun suono rilevato"**: il microfono scelto non sta
sentendo gli altoparlanti (troppo lontano, volume basso, o è il
dispositivo sbagliato). Riprova con `--list-devices` e un altro
microfono, o chiedi all'utente di alzare il volume/avvicinare il
microfono.

**Se i numeri sembrano assurdi** (enormi, tipo `1e+37` o simili): è un bug
noto già scoperto e capito sulla macchina originale - succede SOLO quando
`sounddevice` registra e riproduce audio contemporaneamente tramite le sue
funzioni semplificate (non è un problema di questa macchina). Se capita,
segnalalo così com'è, non serve indagare oltre: è già documentato nel
progetto originale.

## Passo 4 — riporta i risultati

Riassumi per l'utente, in modo che possa incollarlo/riportarlo alla
sessione Claude originale:
- Esito del test WebView2 (trovato/non trovato, esito dell'installazione se tentata)
- Esito del test di latenza: quale microfono è stato usato, quanti trial validi su 5, media/mediana/min/max in ms
- Qualunque anomalia incontrata (nessun suono rilevato, valori assurdi, errori)

Non serve che tu tragga conclusioni definitive sul significato dei numeri
per il progetto più ampio — quello lo fa la sessione che ha tutto il
contesto storico. Il tuo valore qui è eseguire i test con cura e riportare
dati puliti e onesti, comprese le cose andate storte.
