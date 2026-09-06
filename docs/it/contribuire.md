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
