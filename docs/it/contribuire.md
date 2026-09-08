# Contribuire

*[English version](../contributing.md)*

## Far girare il progetto dai sorgenti

Serve **Python 3.14** (il motore opzionale madmom è l'unica parte che ne
richiede uno più vecchio, e vive fuori — vedi sotto).

```bash
pip install -r requirements.txt
```

Interfaccia nuova (web, dentro una finestra nativa):

```bash
python web_migration_spike/main.py
```

Interfaccia storica (Tkinter):

```bash
python boxvr_fixer_gui.py
```

Su Windows serve il **WebView2 Runtime** per l'interfaccia nuova; di norma è
già presente su Windows 10/11.

## Prima di aprire una pull request

Il progetto ha una quantità di verifiche automatiche superiore alla media, ed
è deliberato: gran parte del codice è stato scritto da un modello linguistico
(vedi [docs/ia.md](ia.md)), e i controlli sono la contromisura.

```bash
python "sidecar sandbox/test_engine.py"     # il motore del sidecar
python web_migration_spike/verifica.py      # tutti i controlli sull'interfaccia
python tests/test_playability.py            # uno dei test della logica
```

`verifica.py` copre: analisi statica del codice, icone, misure e colori contro
i wireframe, leggibilità in tema chiaro **e** scuro, accessibilità, parità fra
le pagine, e un controllo a finestra aperta che lo script della pagina non sia
rotto.

I test della logica principale sono i `test_*.py` in [`tests/`](../../tests).

## Come sono composte le pagine dell'interfaccia

Attenzione, è la fonte di errore più comune del progetto: **Correggi,
Dashboard e Playlist sono generate** a partire da `genera_real/index.html`
dagli script in `web_migration_spike/_build_correggi/`.

Se modifichi la pagina Genera, ricomponi le altre:

```bash
python web_migration_spike/rigenera.py
```

E **guarda l'output**: `rigenera.py` controlla il codice di uscita, ma se lo
scarti non te ne accorgi. È già successo.

L'estrazione avviene **per nome**: blocchi anonimi e `const`/`let` nudi non
viaggiano. Se aggiungi una funzione che deve stare anche nelle altre pagine,
va aggiunta alle liste di estrazione.

## Costruire l'eseguibile

Alza `VERSION_WEB` in `version.py` **prima** di compilare — il numero finisce
nel nome del file, ed è così che si evita di sovrascrivere una build
precedente.

```bash
python -m PyInstaller --noconfirm --distpath dist_web --workpath build_web BoxVR_Toolkit_web.spec
```

Il motore madmom (`madmom_worker.exe`) è opzionale, non versionato, e si
ricompila a parte: vedi `madmom_worker/BUILD.md`.

## Stile

- **Commenti in italiano**, come il resto del progetto.
- I commenti spiegano il **perché**, non il cosa: cosa era stato provato
  prima, quale misura ha portato a quella scelta, quale difetto reale ha
  causato quella riga. È la convenzione più forte del progetto ed è quello che
  lo rende leggibile a distanza di settimane.
- Dove un numero è **misurato**, dillo e di' su cosa. Dove è una **scelta**,
  dillo anche quello.

## Cosa non mandare mai

Niente dati di BoxVR: brani, mappe ufficiali, il repertorio di pattern, gli
assembly del gioco. Sono di FitXR, e il `.gitignore` li esclude apposta.
Niente musica commerciale nelle cartelle di test.

---

## La tabella di tuning

I valori che decidono come si *sente* la coreografia — quanto respiro dopo un
gancio, quanti ganci vanno al corpo, quanti squat di fila — stanno in
`tuning.py` e si regolano da un file `tuning.json` accanto all'eseguibile,
senza toccare il codice.

```bash
python tuning.py                       # scrive tuning.esempio.json, completo
cp tuning.esempio.json tuning.json     # e poi si cambia quello che serve
```

Nel file si scrive **solo ciò che si cambia**: il resto resta di fabbrica,
quindi non invecchia quando se ne aggiungono di nuovi. Un valore fuori
dall'intervallo ammesso viene rifiutato con un messaggio che dice il perché,
non ignorato in silenzio. Si applica al riavvio.

Ogni valore porta scritto **da dove viene**, ed è la cosa più importante
della tabella:

| provenienza | significa |
|---|---|
| `misurato` | preso dai file del gioco o dai 465 workout ufficiali. Cambiandolo ci si allontana da come si comporta BoxVR. |
| `provato` | scelto da noi e poi confermato da una sessione in VR. |
| `scelto` | scelto da noi e mai verificato in visore. Qui c'è più margine. |

### Vedere l'effetto senza il visore

```bash
python confronta_tuning.py "un brano.mp3"
```

Rigenera lo stesso brano con e senza il tuo tuning e mette le misure a
confronto — densità, corsie basse, catene di squat, distanze dopo uno swing.

Questa metà non è un accessorio. Una tabella di valori regolabili, da sola,
non toglie il *tentoni*: lo sposta da chi scrive il codice a chi lo usa. Il
7 settembre è successo esattamente questo, all'autore: per il difetto dei
colpi bassi ha fatto tre giri di modifiche misurando ogni volta su un brano
solo, e al terzo ha scoperto che il fix funzionava già dal primo — stava
inseguendo il rumore di un campione singolo. Per questo `confronta_tuning`
media più generazioni, e non una.

Il visore resta necessario per dire se la coreografia è *bella*. Non per
sapere se un numero si è mosso nella direzione voluta.

### Regolare mentre guardi

`tuning.json` funziona col patto «cambia e riavvia». Va bene per una
regolazione ogni tanto, ed è inutilizzabile per venti tentativi di fila —
che è quello che cercare un valore richiede davvero.

Apri l'**anteprima workout** di un brano e premi **Avanzate** (oppure
`Ctrl+Shift+T`). Accanto all'anteprima si apre un pannello con gli stessi 24
valori sotto forma di slider. Ne muovi uno: la coreografia si rigenera — 33 ms
misurati — e la vedi lì accanto. Sul disco non si scrive niente finché non
premi Salva.

I valori sono raggruppati per **su cosa agiscono**, perché è la prima domanda
quando qualcosa non va e non sai quale slider toccare:

| blocco | agisce su |
|---|---|
| su tutti i tipi di workout | automatico, misto e solo marker allo stesso modo |
| solo sulla parte generata dal tool | il livello automatico: Automatica, Armonizza, Estendi — non «Solo marker» |
| solo sui colpi che batti tu | come i tuoi marker vengono filtrati, agganciati, e quanto possono infischiarsene delle regole |

Ogni blocco si apre e si chiude per conto suo; uno che contiene un valore
modificato lo dice anche da chiuso, e si apre da solo quando carichi un
assetto che lo tocca.

### I metodi: un assetto con un nome

Un `tuning.json` solo basta finché cerchi *un* assetto. Ma cercando se ne
trovano di diversi buoni per cose diverse — uno più rado per i brani lenti,
uno fitto per i pezzi tirati — e con un file solo il secondo cancella il
primo.

Un **metodo** è lo stesso formato, con un nome, in una cartella `tuning/`
accanto all'eseguibile. La tendina in cima al pannello ne sceglie uno;
«Predefinito» è semplicemente l'assenza di scelta, cioè i valori di fabbrica.

I metodi sono fatti per **girare**. Import ed export passano dal selettore di
file del sistema e non da una cartella nascosta, perché un file che sai dov'è
è un file che puoi allegare a un messaggio. Ognuno porta con sé chi lo ha
fatto, per cosa, quando e con quale versione del tool — un sacchetto di numeri
ricevuto da uno sconosciuto non dice nemmeno se vale ancora per la versione
che hai in mano. Importandolo ti viene detto che cosa la tua versione non
riconosce, invece di applicartelo a metà in silenzio.

Se trovi un assetto che regge in VR, mandalo: un metodo fatto bene può finire
in una release.
