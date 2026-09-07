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

---

## 1.2.0 — 7 settembre 2026

Quattro difetti trovati in un allenamento vero, e la tabella di tuning che
nasce da come sono stati corretti.

### Corretto

- **I colpi bassi non esistevano.** Non pochi: **zero**, su ogni preset e in
  ogni modalità, contro il 4,3% del gioco. Né ganci al corpo né parate
  basse. Ora seguono le proporzioni misurate sul repertorio ufficiale — Block
  21% bassi, Hook 9%, Jab e Uppercut mai — verificate su dodici generazioni:
  ganci bassi all'8,8%.
- **Dopo un gancio o un montante i colpi erano troppo vicini.** Il 44-50% di
  quelli successivi stava sotto il beat, con minimi di **0,00** — un montante
  e un jab nello stesso identico istante. La regola dei 1,5 beat valeva solo
  sullo stesso braccio; a lati alternati bastava mezzo beat. Ora sono 0,75
  beat, cioè +125 ms a 120 bpm: sotto il beat pieno è sceso al 6%.
  *Volutamente meno del beat pieno che usa il gioco: copiarlo renderebbe le
  nostre coreografie rade come le sue.*
- **«Nessun ostacolo» funzionava a metà.** Arrivava solo ai marker
  dell'utente, mentre gli squat del livello automatico restavano tutti:
  misurati 11 in Armonizza e 5 in «Solo marker», con una catena da otto. Ora
  spariscono, e il combo scudo+squat se ne va intero — lo scudo con lo squat
  conta come squat.
- **Le catene di squat non avevano un limite.** Misurate fino a otto di fila;
  il repertorio ufficiale arriva a sedici ma con una mediana di uno. Oltre il
  limite lo squat diventa un colpo: l'istante resta, cambia la mossa.
- **«Estendi» imparava dove colpisci, non quanto.** Se marchi due colpi per
  beat fai 241 colpi/min e il preset più intenso ne punta 88: un divario di
  **2,7 volte**, ricondotto ogni volta al tetto. È il motivo per cui «non
  riusciva a imparare i colpi in rapida successione». Ora, quando batti più
  fitto del preset più intenso, segue la tua cadenza.

### Aggiunto

- **Tabella di tuning** (`tuning.json`): 24 valori regolabili senza toccare
  il codice, ciascuno con un intervallo che rifiuta l'assurdo e con scritto
  **da dove viene** — misurato sul gioco, provato in VR, o scelto e mai
  verificato. Si scrive solo ciò che si cambia; il resto resta di fabbrica.
- **`confronta_tuning.py`**: rigenera lo stesso brano con e senza il tuo
  tuning e mette le misure a confronto. È la metà che conta: una tabella
  senza un modo di vedere l'effetto non toglie il tentoni, lo sposta
  sull'utente.

### Corretto nei test

- Due controlli verificavano **la cosa sbagliata, e la verificavano bene**:
  uno confrontava le corsie esatte invece dei lati (falliva su una
  coreografia corretta appena un gancio poteva essere basso), l'altro
  contava come violazione una distanza che il programma permette di
  proposito con lo slider.

### Resta aperto

- Fra due marker dell'utente si misurano ancora distanze di 0,00 beat.
  Sospetto sia l'aggancio magnetico che porta due colpi vicini sullo stesso
  punto della griglia — **non verificato, quindi non corretto**.
- `tests/test_onset_anchoring.py` sez. 7 è rosso da prima di questo giro.
- Tre test che aprono una finestra Tkinter vanno in timeout in modo
  intermittente, da prima di questo giro.

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

