# Changelog

*[English version](CHANGELOG.md) — la versione inglese è quella pubblicata; questa è la traduzione.*

Ogni voce dice **cosa era sbagliato** e **come si è misurato**, non solo cosa
è cambiato: un difetto trovato in VR e uno sospettato sulla carta non hanno
lo stesso peso, e chi legge deve poterli distinguere.

Le note di release su GitHub si scrivono da qui.

Il formato delle versioni è `MAJOR.MINOR.PATCH`. Durante la beta cresce il
PATCH; il MINOR segna un confine (la 1.1.0 è la prima uscita pubblica).

---

## Come si arriva a una release

Quattro passi, in quest'ordine, senza saltarne nessuno.

1. **Bugfixing.** Le correzioni, ciascuna con la misura che dice cos'era
   sbagliato e di quanto.
2. **Changelog ed eseguibile.** Si aggiorna questo file — è da qui che si
   scrivono le note di release — e si costruisce l'exe, verificando che le
   correzioni siano *dentro il binario*, non solo nei sorgenti.
3. **Testing.** Lo prova una persona, in VR.
4. **Conferma e pubblicazione.** Solo dopo un sì esplicito.

Il terzo passo non è una formalità burocratica, ed è quello che si è più
tentati di saltare perché i test automatici sono verdi. Ma i test possono
dire solo se il programma fa quello che gli è stato chiesto, mai se quello
che gli è stato chiesto ha senso:

- il combo **schivata + pugno simultaneo** passava otto controlli scritti
  bene, ed era fisicamente ineseguibile — il corpo è spostato di lato e metà
  dello spazio è occupata dall'ostacolo;
- **«Estendi» appiattiva le proporzioni del ritmo** su una sola
  suddivisione, e il test che doveva accorgersene ne guardava una alla volta:
  non poteva vedere il difetto.

Tutti e due sono stati trovati in visore, da qualcuno che si stava
allenando.

### Due numeri, non uno

`VERSION_WEB` è quello che vede chi scarica, e si muove **solo quando esce
davvero una release**. `BUILD` è il contatore interno: avanza a ogni
ricostruzione e si azzera quando si pubblica. Il file si chiama
`BoxVR SrvToolkit 1.2.0 build 6.exe` mentre si lavora, e
`BoxVR SrvToolkit 1.2.0 Public Beta.exe` quando è quello che si pubblica.

Esiste perché per due giorni il numero pubblico è avanzato a ogni
ricostruzione: 1.2.0, 1.3.0, 1.3.1, 1.3.2, 1.3.3 — cinque versioni che nessuno
ha mai visto. Chi legge avrebbe trovato cinque voci per quello che dal suo lato
è un cambiamento solo, e i numeri mancanti fra due release sarebbero sembrati
versioni ritirate. Il numero pubblico non è mai servito a distinguere le build:
serviva solo a non sovrascrivere un file, ed è per quello che c'è `BUILD`.

Lo stesso vale per questo file: il lavoro fra una release e l'altra si accumula
sotto l'unica voce *non ancora pubblicata*, ed è da quella sola voce che si
scrivono le note della release.

---

## 1.2.0 — 8 settembre 2026

La tabella di tuning, e un pannello per usarla: i numeri che decidono come si
*sente* un workout sono adesso visibili, regolabili, e l'effetto lo vedi
mentre li cambi. Più quattro difetti trovati durante un allenamento vero in
VR.

### Aggiunto

- **Il tuning è una funzione, non una botola di debug.** Sta dietro il
  pulsante **Avanzate** nell'anteprima workout, segue la lingua dell'app come
  tutto il resto — tutti i 25 nomi, le descrizioni, i titoli dei blocchi e le
  etichette di provenienza — e ha una guida sua:
  [docs/it/tuning.md](docs/it/tuning.md).
- **Scorri il brano con la rotella del mouse** stando sopra l'anteprima. Il
  passo è musicale, non un tempo fisso: un beat per scatto, un quarto di beat
  con Shift — perché quello che stai guardando è la distanza fra due colpi, e
  quella distanza è in beat in tutto il resto del programma.
- **Lo spazio mette in pausa l'anteprima**, come in qualunque lettore — ma mai
  mentre scrivi nel pannello, dove uno spazio è uno spazio.
- **Due numerazioni.** `VERSION_WEB` è quello che vede chi scarica e si muove
  solo quando esce una release; `BUILD` è il contatore interno. In due giorni
  il numero pubblico aveva bruciato cinque versioni che nessuno ha mai visto.
  `rilascia.py` promuove una build interna a release pubblica.

- **Pannello di tuning.** Apri l'anteprima workout di un brano e premi
  **Avanzate** (oppure `Ctrl+Shift+T`): 25 valori regolabili compaiono come
  slider accanto all'anteprima. Ne muovi uno e la coreografia si rigenera — 33
  ms misurati — così l'effetto lo vedi invece di immaginarlo. Sul disco non si
  scrive niente finché non premi Salva. Guida completa:
  [docs/it/tuning.md](docs/it/tuning.md).
- **Ogni valore porta la sua provenienza** — *misurato* sul gioco, *provato* in
  VR, oppure *scelto* e mai verificato — e un intervallo che rifiuta l'assurdo
  dicendo perché, invece di ignorarlo in silenzio. È questo che rende il
  pannello consegnabile a chiunque: le protezioni stanno nei valori, non nel
  nascondere il pannello.
- **Valori raggruppati per su cosa agiscono**, in tre blocchi richiudibili: su
  tutti i tipi di workout, solo sulla parte generata dal tool, solo sui colpi
  che batti tu. Il raggruppamento è stato *misurato*, non dedotto leggendo il
  codice: ogni valore portato a un estremo e il risultato confrontato su tutte
  e tre le modalità.
- **Un azzera accanto a ogni slider**, non solo uno per tutto: mentre cerchi un
  valore te ne ritrovi cinque spostati, e quando uno è andato troppo in là vuoi
  tornare indietro su quello senza perdere gli altri quattro.
- **I metodi**: un assetto con un nome, in una cartella `tuning/` accanto
  all'eseguibile, scelto da una tendina. Import ed export passano dal selettore
  di file del sistema, e ogni metodo porta con sé chi lo ha fatto, per cosa,
  quando e con quale versione — un sacchetto di numeri ricevuto da uno
  sconosciuto non dice se vale ancora per la versione che hai in mano.
  Importandolo ti viene detto cosa la tua versione non riconosce, invece di
  applicartelo a metà in silenzio. **Un metodo che regge in VR può finire in
  una release.**
- **`confronta_tuning.py`**: rigenera lo stesso brano con e senza il tuo tuning
  e mette le misure a confronto, mediando su più generazioni. Una tabella senza
  un modo di vedere l'effetto non toglie il tentoni: lo sposta da chi scrive il
  codice a chi lo usa.

### Corretto — quello che è saltato fuori usando il pannello

Ognuna di queste è stata trovata muovendo gli slider e guardando l'anteprima,
che è esattamente il motivo per cui il pannello esiste.

- **La regola parte adesso dal posizionamento.** Fino a ieri l'unica risposta
  a «questi due non ci stanno» era spostare la mossa o scartarla. Adesso:

      c'è spazio per due SWING?    sì → restano    no ↓
      diventano due DIRETTI
      c'è spazio per due DIRETTI?  sì → restano    no → il secondo decade

  Lo stesso principio già usato per le catene di squat — l'istante resta, la
  mossa cambia — portato dove serviva di più. Misurato con marker fitti:
  **0 violazioni** su quattro combinazioni di respiro e deroga, contro le 19
  di prima.
- **Alzare il respiro toglieva i colpi sbagliati.** Con la deroga piena sui
  marker, le regole di respiro non toccavano i tuoi colpi: alzando il valore
  sparivano 12 colpi automatici — che non danno fastidio — e restavano 13
  coppie ravvicinate, tutte tue. La deroga adesso vale per i pugni dritti ma
  non per ganci e montanti, che sono movimenti ampi e vicini non si fanno.
  Costo misurato con marker realistici: **nessuno**, 115 marker su 115
  conservati.
- **La deroga guardava solo il primo dei due colpi.** Un gancio subito dopo un
  diretto passava, e nessuno slider poteva allontanarlo. Verificato in
  runtime. Adesso guarda tutti e due: un movimento ampio conta che ci sia, non
  che venga prima o dopo.
- **Non c'era nessun respiro *prima* di uno swing.** Guardavamo solo il colpo
  che veniva prima, quindi `gancio → jab` chiedeva la regola degli swing
  mentre `jab → gancio` chiedeva quella normale. Il repertorio ufficiale non fa
  questa distinzione: un beat pieno di minimo in tutti e quattro i casi (prima
  di uno swing, 8 casi sullo stesso braccio e 141 sull'altro; dopo, 4 e 154).
  Valore nuovo, `respiro prima di uno swing`.
- **Un respiro separato per i tuoi colpi.** 1.225 va bene fra due colpi che
  hai marcato, ma imporlo a tutto rendeva non più eseguibili due figure del
  catalogo euclideo — tresillo e cinquillo largo stanno a 1 beat esatto, come
  il repertorio ufficiale. Il livello automatico costruisce sulle figure del
  gioco; i tuoi marker no.
- **L'anteprima rifiutava di rigenerare sui brani già generati.** Che sono
  esattamente quelli che la tendina elenca, e all'avvio nessuno di quelli ha
  un'analisi in memoria: quindi ogni slider non faceva niente. Adesso
  l'analisi si calcola quando muovi uno slider.
- **Nel visualizzatore ogni scudo aveva uno squat sotto.** Lo scudo disegnava
  una barra — la stessa forma usata per lo squat — più l'icona poco sotto,
  quindi si leggeva sempre come *squat + scudo*, e avvicinandosi i due si
  separavano. Nei dati gli scudi simultanei a uno squat erano **zero**: non
  era uno squat, era la sua forma. Lo scudo da solo adesso disegna solo lo
  scudo; la barra resta per il combo squat+scudo, dove è vera.
- **Via il nome del brano dalla barra di riproduzione.** Ripeteva quello che
  la tendina sopra diceva già e costava fino a 260px — proprio quelli che
  servono al cursore di posizione, l'unico comando lì dentro la cui precisione
  dipende da quanto è lungo.

### Corretto — trovato durante un allenamento vero in VR

- **I colpi bassi non esistevano.** Non rari: **zero**, su ogni preset e in
  ogni modalità, contro il 4,3% del gioco stesso. Nessun gancio al corpo,
  nessuno scudo basso. Adesso seguono le proporzioni misurate sul repertorio
  ufficiale, verificate su dodici generazioni: ganci bassi all'8,8%.
- **I pugni arrivavano troppo presto dopo un gancio o un montante.** Il 44–50%
  delle mosse successive cadeva sotto un beat, con minimi di **0,00** — un
  montante e un diretto nello stesso identico istante. La regola da 1,5 beat
  valeva solo per lo stesso braccio; alternando i lati bastava mezzo beat.
  Adesso è 0,75 beat, cioè +125 ms a 120 bpm, e le mosse sotto il beat sono
  scese al 6%. *Volutamente meno del beat pieno che usa il gioco: copiarlo
  renderebbe le nostre coreografie rade come le sue.*
- **Uno scudo alto accanto a uno squat.** Segnalato due volte a sei settimane
  di distanza. La regola vera è **deterministica**, misurata senza una sola
  eccezione: lo scudo in combo con uno squat è basso 12 volte su 12, lo scudo
  da solo è alto 44 su 44. Ti abbassi e pari basso, oppure stai in piedi e pari
  alto — uno scudo alto mentre sei accosciato è una posizione che non esiste.
  Un primo tentativo usava una quota casuale del 21%: il numero giusto col
  meccanismo sbagliato, perché estrarre a caso produce proprio le due cose che
  nel gioco non capitano mai.
- **«Niente ostacoli» funzionava a metà.** Arrivava ai tuoi marker ma non al
  livello automatico, quindi i suoi squat sopravvivevano tutti: 11 misurati in
  Armonizza e 5 in «Solo marker», con una catena da otto. Adesso se ne vanno, e
  con loro il combo scudo+squat.
- **Le catene di squat non avevano limite.** Misurate fino a otto di fila; il
  repertorio ufficiale arriva a sedici ma con una mediana di uno. Oltre il
  limite lo squat diventa un pugno: l'istante resta, la mossa cambia.
- **Estendi imparava dove colpisci, non quanto.** Marcare due colpi per beat fa
  241 colpi/min mentre il preset più intenso ne punta 88 — un divario di
  **2,7×**, riportato ogni volta al tetto. È per questo che «non riusciva a
  imparare i colpi in rapida successione». Adesso segue la tua cadenza quando
  sei tu a dettare un passo più veloce del preset.
- **Un montante e un gancio dello stesso braccio, quasi attaccati.** I tuoi
  marker sono esenti dalle regole di distanza — è ciò che rende vero «un marker
  vince sempre» — ma l'esenzione era tutto-o-niente, quindi nessun valore
  poteva allontanarli. Quanto sia larga adesso lo scegli tu, perché le due
  richieste in gioco sono tutte e due legittime e in conflitto: *voglio poter
  infittire i miei colpi* contro *questi due sono troppo vicini*.

### Corretto — lo stesso brano dà adesso la stessa coreografia

Generando due volte un brano, con gli stessi marker, uscivano due workout
diversi: il seme veniva dall'orologio. Il livello automatico puro non ha mai
avuto questo problema — deriva il seme da titolo|artista apposta — ma la strada
che usa i tuoi marker non lo rispettava. Nessuno se n'era accorto, perché non
c'è motivo di generare due volte lo stesso brano, finché non arriva un pannello
che lo fa venti volte di fila. Adesso muovendo uno slider cambia solo ciò che
quello slider governa: **236 istanti su 278 restano intatti** invece di
rimescolare tutto.

### Corretto — negli strumenti stessi

- **Il pannello non rigenerava mai niente.** Una cache un livello sotto la
  richiesta si teneva sulle impostazioni del *brano*, senza niente del tuning
  dentro: muovi uno slider, la chiave non cambia, torna la coreografia di
  prima. Misurato: 279 colpi prima e 279 dopo, agli stessi istanti al
  millesimo. Non era un valore: erano tutti.
- **Il pannello falliva in silenzio.** Quando una ricostruzione non riusciva,
  il gestore usciva e basta, senza lasciare traccia da nessuna parte. È la
  ragione per cui il difetto qui sopra è sopravvissuto a due giorni d'uso.
- **Dodici valori erano congelati all'import**, presi come *default* di un
  parametro, che in Python si valuta una volta sola alla definizione. Regolare
  dal file funzionava; regolare dal pannello non faceva niente.
- **L'anteprima workout si stringeva** all'apertura del pannello, e il nome del
  brano nella barra ripeteva quello che la tendina diceva già, togliendo al
  cursore di posizione la larghezza che gli serve.

### Sui test

Diversi controlli verificavano **la cosa sbagliata, e la verificavano bene**:
uno confrontava le corsie esatte invece dei lati, un altro contava come
violazione uno spazio che il programma concede apposta. La guardia contro le
manopole morte controllava che un valore fosse *letto*, non che fosse letto
*ogni volta*. E la guardia fra le costanti dei motori e ciò che compare
davvero sullo schermo non esisteva affatto — ed è così che un pannello che non
rigenerava niente è rimasto verde per due giorni.

---

## 1.1.2 — 6 settembre 2026

### Corretto

- **I brani generati restavano sul disco per sempre.** Misurati **715 MB in
  76 file** nella cartella dei risultati. La pulizia esistente si occupava
  delle cartelle temporanee di servizio, che sono un'altra cosa. Ora si
  svuotano alla chiusura e all'avvio, cancellando per estensione: ciò che
  non abbiamo prodotto noi resta dov'è.

### Aggiunto

- Screenshot nei due README, e le due schermate di apertura accostate — con
  e senza patch — perché la regola delle due porte si legga in un colpo
  d'occhio.

---

## 1.1.1 — 6 settembre 2026

### Corretto

- **Schivata con pugno simultaneo: ineseguibile.** Segnalato in VR. La
  correzione ovvia — mettere il colpo dal lato libero — non è possibile: la
  direzione della schivata **non esiste nel formato**, la sceglie il gioco.
  Il combo è ritirato; la stessa quota di squat diventa una schivata sola,
  con il beat libero attorno che le dà il gioco.
- **Armonizza ed Estendi «scivolavano nello standard BoxVR».** Estendi
  imparava il ritmo e poi lo appiattiva: spostava ogni colpo sulla
  suddivisione più *vicina*, e una marcatura 32%/68% usciva 100%/0%.
  Armonizza non imparava affatto. Ora si piazza *dal* ritmo invece di
  avvicinarsi al ritmo, a densità invariata.

---

## 1.1.0 — 6 settembre 2026 — prima uscita pubblica

### Corretto

- **«Estendi» era premibile prima di poter funzionare**, e la spiegazione
  del perché era irraggiungibile proprio a chi la cercava. Ora resta spento
  finché non ha materiale da cui imparare, e dice soglia e conteggio.
- **La curva di carica non arrivava ai bordi**: misurato 12,7% vuoto a
  sinistra e 13,6% a destra, un quarto dell'anteprima.
- **Senza patch si poteva entrare in Genera**, generare tutto, e scoprire in
  VR che non era cambiato niente. Metà di questo blocco esisteva nella GUI
  Tkinter e si era persa nel port.
- **«Installa in BoxVR» non installava le playlist.** Verificato sui file:
  TrackData scritto, WorkoutPlaylists fermo a una settimana prima. In più ne
  restituiva solo la prima, e con i blocchi da 30 minuti sono più d'una.
- Tredici frasi restavano in italiano in modalità inglese.

### Aggiunto

- **«Cartella BoxVR» sempre raggiungibile** in testata, non solo dopo
  un'operazione riuscita.

