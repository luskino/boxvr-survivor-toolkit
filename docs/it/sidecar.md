# Sidecar: i tuoi colpi dentro l'allenamento

*[English version](../sidecar.md)*

Il generatore automatico decide tutto da solo. Il **sidecar** ribalta la cosa:
ascolti il brano, batti a tempo i colpi che vuoi dove li vuoi, e il tool
costruisce l'allenamento attorno ai tuoi.

## Come si marca

Premi play e batti. Ogni battuta lascia un **marker**, cioè un istante. Il
blocco marker mostra la forma d'onda ingrandita con la griglia dei beat sotto,
così vedi se stai cadendo sul colpo o accanto.

Due aiuti, entrambi disattivabili:

- **Correzione dell'imprecisione** — il marker si sposta sull'attacco sonoro
  più vicino, se c'è. Nessuno batte a tempo perfetto.
- **Aggancio magnetico alla griglia** — il marker si allinea alla suddivisione
  del beat più vicina, entro una frazione di beat. Senza, i tuoi colpi
  suonerebbero "sporchi" accanto a quelli generati, ed è una differenza che si
  sente subito.

C'è anche una **soglia minima fra due colpi**: sotto quella distanza il
secondo viene scartato, perché fisicamente non è tirabile. Il pannello ti dice
quanti ne restano fuori.

---

## Le tre modalità

### Armonizza

I tuoi colpi e quelli automatici convivono. Il tool continua a generare la sua
coreografia su tutto il brano, e dove hai marcato tu il tuo colpo vince il
conflitto.

Utile quando vuoi *aggiungere* accenti a un allenamento che ti va già bene.

### Solo marker

Nient'altro che i tuoi colpi, più gli ostacoli automatici (squat e schivate,
che non si marcano). Il resto del brano resta silenzioso.

Utile quando vuoi il controllo totale, e sei disposto a marcare tutto.

### Estendi

*"Ti do il primo minuto e mezzo di tre, il tool gestisce il resto."*

È la modalità più ambiziosa, ed è quella che ha richiesto più giri di
correzione. Oggi funziona così: **non guarda solo dove hai marcato, ma come**.

I marker vengono raggruppati, e ogni gruppo viene classificato:

| zona | trattamento |
|---|---|
| **blocco ritmico** — 4 o più colpi ravvicinati | stai dettando un ritmo: lì il tool non mette niente di suo |
| **accento isolato** — gruppi più corti | stai mettendo un punto fermo: lì l'automatico continua a scorrere, e il tuo colpo vince in quell'istante |
| **tutto il resto** | generato dal tool, imitando cadenza e ritmo dei tuoi blocchi |

I tre trattamenti convivono nello stesso brano.

#### Perché la distinzione conta

Prima, "il tratto marcato" era definito come l'intervallo dal primo all'ultimo
marker. Il modello degenerava in modo prevedibile: bastava **marcare l'inizio
e la fine della canzone** perché l'intervallo coprisse tutto, non restasse
niente da estendere, e la modalità diventasse identica a "Solo marker",
silenzio in mezzo compreso.

Distinguere ritmo da accento risolve il caso senza aggiungere un ramo di
codice: gli accenti, non stando dentro nessun blocco, ricevono il livello
automatico **per costruzione**.

#### La soglia di stacco è tua, non nostra

Quando si considera che tu abbia *smesso* di marcare non è un numero fisso di
secondi: è **sei volte il tuo intervallo tipico** (con un minimo di 2 e un
massimo di 8 battute). Chi tira raffiche di sedicesimi e chi segna un colpo a
battuta hanno due idee diverse di "pausa", e una costante avrebbe dato ragione
solo a uno dei due.

#### Cosa impara, e cosa non può imparare

Dai tuoi blocchi ricava due cose:

1. **La cadenza** — quanti colpi al minuto tiri.
2. **La firma ritmica** — dove cadono dentro il beat: sul battere, sul levare,
   sui sedicesimi.

È la seconda che si sente. Due tratti con lo stesso numero di colpi al minuto
suonano lontanissimi se uno sta sul battere e l'altro sui levare.

**Quello che non può imparare**: quale colpo. Un marker dice solo *quando*. Il
tipo di mossa, la mano e l'altezza li decide comunque il motore. Estendi
riproduce il tuo **timing**, mai le tue combinazioni.

#### La soglia dei 45 secondi

Per imitarti servono almeno 45 secondi di blocchi ritmici — sommati, non
"dal primo all'ultimo marker". Da meno non si impara un modo di colpire: si
fotografano quattro colpi.

Sotto quella soglia il resto del brano viene generato normalmente. Non è un
errore, ed è dichiarato: la riga sotto il selettore di modalità dice cosa il
tool ha visto, e una **banda colorata** sulla pista dei marker lo mostra —
viola i blocchi ritmici, ambra gli accenti isolati, niente dove genera il
tool.

Questa parte visibile non è decorativa. Con gli stessi marker la modalità può
comportarsi in due modi diversi a seconda di come sono distribuiti: senza
mostrarlo, otterresti risultati diversi senza capire perché, e sembrerebbe
colpa tua.

---

## Da tarare

Tre numeri della classificazione sono scelte dichiarate, non misure: quanti
colpi minimi fanno un blocco (4), quanto deve durare (1 battuta), e il
moltiplicatore della pausa di stacco (6×). Nei workout ufficiali del gioco un
"marker umano" non esiste, quindi non c'è niente da cui ricavarli
statisticamente: vanno tarati provando in visore.
