# Come funziona BoxVR, e perché esiste "Correggi"

*[English version](../boxvr-and-fix.md)*

## Cosa succede quando importi una canzone

BoxVR permette di aggiungere musica propria. Quando lo fai, il gioco analizza
il brano e produce due file nella sua libreria:

```
%AppData%/LocalLow/FITXR/BoxVR/Playlists/
├── TrackData/<hash>.trackdata.txt   ← l'analisi del brano
├── TrackData/<hash>.wav             ← l'audio decodificato
└── TrackDefinitions/<hash>.wdef.txt ← l'indice: artista, titolo, durata, BPM
```

Il `.trackdata.txt` è un JSON. Dentro c'è la griglia dei **beat** rilevati,
raggruppati in **battute** (`bars`), e — la parte che conta davvero — una
struttura di **segmenti** (`segs`), cioè le sezioni musicali che il gioco ha
riconosciuto: intro, strofa, ritornello, break.

Ogni beat porta un riferimento al segmento a cui appartiene, e ogni segmento
porta un solo numero:

```
beat._segment._energyLevel   →   0, 1, 2 o 3
```

**È quel numero a decidere l'allenamento.** Non c'è nient'altro: BoxVR non
memorizza quali pugni comparire dove. A runtime pesca pattern di movimenti da
un repertorio interno, scegliendoli in base all'intensità del segmento in cui
si trova.

| valore | cosa succede a schermo |
|---|---|
| 0 | silenzio: nessun evento |
| 1 | pochi colpi, ritmo lento |
| 2 | intensità media |
| 3 | massima densità |

## Il primo problema: livelli sbagliati

L'analisi automatica del gioco a volte sbaglia di grosso. Capita di trovare un
ritornello pieno etichettato come `1`, o un ponte tranquillo come `3`. Il
risultato in visore è un allenamento che non segue la canzone: ti fermi mentre
la musica esplode, tiri pugni durante la pausa.

**Correggi** interviene esattamente qui, e solo qui.

### Cosa fa Correggi

1. Trova la coppia `<hash>.trackdata.txt` + `<hash>.wav` di ogni brano.
2. Rianalizza l'audio vero: energia dei **bassi** (sotto 250 Hz) e volume
   **RMS**, battuta per battuta.
3. Divide l'energia del brano in quattro fasce, usando la distribuzione del
   brano stesso — ogni canzone viene giudicata sulla propria scala, non su una
   soglia assoluta valida per tutti.
4. Corregge `_energyLevel` **solo** se il punteggio è chiaramente oltre il
   confine fra due fasce (margine di confidenza, 12% per impostazione
   predefinita). Nel dubbio, lascia il valore che aveva calcolato il gioco.
5. **Non tocca mai i confini dei segmenti né la loro struttura.** Cambia
   soltanto l'etichetta di intensità.

Questa cautela è deliberata: il gioco ha comunque analizzato la struttura
musicale con i suoi strumenti, e riscriverla da fuori sulla base della sola
energia produrrebbe un risultato peggiore, non migliore.

### Il preset di intensità

Oltre a correggere, si può spostare il **rapporto** fra sezioni "solo pugni" e
sezioni miste (con squat, schivate, parate), scegliendo fra tre preset. Non
inventa niente: ridistribuisce i livelli sulla stessa curva di energia già
misurata.

## Il secondo problema: i buchi

Correggi ha un limite invalicabile: **agisce sui segmenti che esistono**. Se
il gioco non ha definito nessun segmento in un tratto della canzone, lì non
c'è niente da correggere.

E i buchi esistono davvero. Verificato su brani reali della libreria: vuoti di
6 secondi e più fra un segmento e l'altro, e in un caso gli ultimi ~15 secondi
della canzone completamente scoperti. In gioco quei tratti sono silenzio,
per quanto carica sia la musica.

Nessuna correzione può riempirli, perché non c'è alcun segmento su cui agire.
Da qui nasce l'altro strumento: **[Genera](genera.md)**, che costruisce il
`trackdata` da zero, con copertura completa dell'intera canzone per
costruzione.
