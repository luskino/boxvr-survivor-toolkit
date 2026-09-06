# Il ruolo dell'intelligenza artificiale in questo progetto

*[English version](../ai.md)*

## In breve

**La quasi totalità del codice e dell'interfaccia è stata scritta da un
modello linguistico** (Claude, di Anthropic), in sessioni di lavoro durate
settimane, sotto la direzione dell'autore del progetto.

Non è una nota a piè di pagina. Se stai valutando se fidarti di questo
software — o se vuoi contribuirci — è una delle cose più importanti da sapere,
e merita di essere detta per intero invece che accennata.

## Chi ha fatto cosa

**L'autore** ha deciso cosa costruire e perché: gli obiettivi, l'ambito di
ogni strumento, le scelte di prodotto, il disegno dell'interfaccia in Figma. E
soprattutto ha fatto l'unica cosa che nessun modello può fare al posto suo:
**provare gli allenamenti in visore** e dire cosa non funzionava. Quasi ogni
correzione importante di questo progetto nasce da lì.

**Il modello** ha scritto il codice, i test, gli strumenti di verifica e
questa documentazione; ha fatto il reverse engineering del formato dei file e
del comportamento del gioco; ha proposto soluzioni e, in diversi casi, ha
proposto quelle sbagliate prima di quelle giuste.

## Cosa è stato fatto per non fidarsi ciecamente

Un modello linguistico produce codice plausibile con la stessa facilità con cui
produce codice corretto. La differenza non si vede leggendo. Le contromisure
adottate, in ordine di utilità:

**Misurare invece di dedurre.** Dove si poteva verificare un'affermazione, si
è verificata: le misure dell'interfaccia lette dal DOM reale a runtime invece
che stimate dal codice; il contrasto dei colori calcolato invece che valutato
a occhio; il comportamento del motore di generazione simulato su casi
concreti invece che dedotto dai commenti.

**Test automatici estesi**, sia sulla logica (il motore sidecar ha oltre 100
controlli) sia sull'interfaccia (audit di codice, icone, misure contro il
wireframe, leggibilità in entrambi i temi, accessibilità).

**Verificare il binario, non solo i sorgenti.** Ogni eseguibile viene
ricostruito e poi ispezionato byte per byte, per confermare che le correzioni
siano davvero finite dentro. Almeno una volta lo erano nei sorgenti e non
nell'exe.

**Provare i controlli iniettando il difetto.** Un controllo che non ha mai
visto fallire nulla non è un controllo: è una rassicurazione. Almeno una volta
un audit è risultato verde perché era rotto, non perché il codice fosse sano.

## Errori tipici che si sono presentati

Detti apertamente, perché sono la parte istruttiva:

- **Copie divergenti della stessa regola.** Più volte la stessa logica è
  finita scritta in due posti, e le due copie hanno preso strade diverse: una
  volta l'interfaccia annunciava un comportamento che il motore non aveva. Il
  rimedio è sempre lo stesso — una funzione sola, usata da entrambi.
- **Verifiche mal poste.** Controlli che cercavano una cosa nel posto
  sbagliato e rispondevano "manca" senza che mancasse niente.
- **Correzioni plausibili ma non misurate**, smentite alla prima misurazione
  vera.
- **Sicurezza mal riposta nei propri commenti.** Un commento che dice
  "identico a X" non rende il codice identico a X.

## Cosa questo significa per te

- **Il codice è leggibile e commentato in modo insolitamente esteso**: i
  commenti spiegano *perché* una scelta è stata fatta e cosa era stato provato
  prima. È materiale utile se vuoi capirlo o modificarlo.
- **Non dare per buona nessuna affermazione senza verificarla**, incluse
  quelle di questa documentazione. Dove un numero è misurato, è detto; dove è
  una scelta, è detto anche quello.
- **Il software tocca i dati di un gioco che hai pagato.** Fai un backup. Le
  cautele descritte nella documentazione sono reali e implementate, ma non
  sostituiscono un backup tuo.

## Sulla proprietà del risultato

Il codice è pubblicato sotto GNU General Public License v3.0 dall'autore del
progetto. La questione di chi detenga il diritto d'autore su codice generato
da un modello è, alla data di pubblicazione, non del tutto risolta in molte
giurisdizioni — più di un ufficio del copyright ha sostenuto che un'opera
generata senza sufficiente apporto umano non sia proteggibile.

Vale la pena dirlo invece di sorvolarci, perché una licenza copyleft poggia
sul diritto d'autore: dove non si detiene un diritto, non si può imporre una
condizione. Riguarda qualunque licenza si scelga, non solo questa.

Quello che non è incerto è l'apporto umano: gli obiettivi, l'ambito di ogni
strumento, il disegno dell'interfaccia, le scelte di prodotto, e le prove in
visore da cui è nata quasi ogni correzione importante. Selezione,
organizzazione e direzione sono paternità dell'opera. La licenza dichiara
l'intenzione senza ambiguità — questo resta aperto, e nessuno lo chiude — ed è
l'intenzione il punto.
