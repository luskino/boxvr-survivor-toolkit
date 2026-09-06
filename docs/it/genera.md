# Genera: costruire un allenamento da un mp3

*[English version](../generate.md)*

Mentre [Correggi](boxvr-e-correggi.md) sistema quello che il gioco ha già
prodotto, **Genera** parte da un file audio e costruisce l'analisi da zero —
con una garanzia che il gioco non dà: **copertura completa della canzone,
senza buchi**, perché i segmenti li disegna il tool e li fa combaciare per
costruzione.

---

## 1. La lista dei brani

Trascini una cartella di mp3 o wav, e ogni brano entra in elenco con artista,
titolo e BPM. I metadati vengono dai tag del file; se mancano, si ripiega sul
nome del file.

L'analisi di ogni brano parte **in background** appena il brano entra in
elenco. È una scelta precisa: analizzare un brano richiede secondi, e bloccare
l'interfaccia mentre lo fa renderebbe il tool inutilizzabile con una cartella
piena. Finché l'analisi non è pronta, i comandi che dipendono da essa
restano spenti e lo dichiarano, invece di dare numeri inventati.

---

## 2. La timeline del brano

![L'anteprima del brano: forma d'onda, fasi colorate e la curva di carica ciano sulla stessa scala temporale](../img/track-preview.png)

Il pannello di anteprima mostra, sovrapposti sulla stessa scala temporale:

- la **forma d'onda** reale del brano;
- le **fasi** colorate, cioè i segmenti generati e la loro intensità;
- la **curva di carica** — l'energia continua misurata battuta per battuta,
  che è il dato da cui la coreografia si decide;
- i **marker** che hai battuto tu, se stai usando il [Sidecar](sidecar.md);
- la **griglia dei beat** ("Base beat"), ascoltabile come click a tempo.

Lo zoom va da tutta la canzone a un ingrandimento in cui i singoli beat si
distinguono. Cambiare zoom **ricentra sul punto che stai guardando**, invece
di lasciare la vista dov'era: ingrandendo, altrimenti, sparirebbe proprio il
punto che stavi osservando.

Il click a tempo suona sui **beat veri rilevati**, non su una griglia
ricalcolata dal BPM medio. È l'unico modo per accorgersi a orecchio se il
rilevamento ha sbagliato.

---

## 3. I BPM, e i due motori di analisi

Il BPM è la fondazione di tutto: se la griglia dei beat è sbagliata, ogni
colpo cade fuori tempo, e nessun'altra qualità del tool può rimediare.

### Perché due motori

| motore | libreria | quando conviene |
|---|---|---|
| **Veloce** | [librosa](https://librosa.org/) | brani a tempo stabile — la stragrande maggioranza |
| **Precisa** | [madmom](https://github.com/CPJKU/madmom) | brani con cambi di tempo, rallentando, tempo suonato a mano |

madmom usa reti neurali ricorrenti addestrate sul beat-tracking ed è più
robusto quando il tempo non è costante; è anche molto più lento. librosa è
puro Python, veloce, e sui brani a griglia stabile dà praticamente lo stesso
risultato — verificato su brani reali del progetto: 107,66 BPM contro i 107,14
del gioco, 267 beat contro 268.

Il tool prova per primo il veloce e **passa da solo al preciso** quando la
griglia risulta instabile o quando la copertura finale presenta buchi. Puoi
comunque forzare l'uno o l'altro.

> **Nota tecnica.** madmom non supporta Python 3.13+, mentre il tool gira su
> 3.14. Per questo il motore preciso vive in un **eseguibile separato**
> (`madmom_worker.exe`), invocato come sottoprocesso. Se non è presente, il
> tool funziona lo stesso con il solo motore veloce. Le istruzioni per
> ricompilarlo sono in `madmom_worker/BUILD.md`.

### BPM a mano

Se entrambi i motori sbagliano — capita su brani con un'introduzione fuori
tempo — puoi scrivere il BPM tu. **Non è un'etichetta**: il valore viene
passato al beat-tracking, che ricostruisce l'intera griglia a partire da quel
tempo, e tutta l'analisi riparte da zero.

C'è anche una scorciatoia per cercare il BPM ufficiale di un brano online,
quando il rilevamento viene segnalato come sospetto.

---

## 4. L'algoritmo di generazione

### I segmenti

A differenza della correzione, qui i segmenti non esistono: li crea il tool, a
blocchi contigui di battute (4 per impostazione predefinita, in linea con le
lunghezze osservate nei file reali del gioco, circa 6-12 secondi). Coprono
`[0, durata]` senza interruzioni.

### L'intensità

Ogni segmento riceve un `_energyLevel` calcolato sulla curva di energia del
brano, con la stessa logica a fasce usata dalla correzione. Poi entra in gioco
il **preset**, che sposta il rapporto fra sezioni "solo pugni" e sezioni miste
(con squat, schivate e parate), e lo **slider percentuale** per un controllo
fine su ogni singolo brano.

I bersagli di densità non sono a intuito: sono **misurati** sui workout
ufficiali del gioco.

| preset | eventi al minuto (bersaglio) | intervallo osservato |
|---|---|---|
| Leggero | 42 | 32 – 58 |
| Medio | 74 | 61 – 103 |
| Aggressivo | 88 | 65 – 119 |

### Cosa esce

Tre file, negli stessi formati che il gioco si aspetta:

```
<hash>.trackdata.txt     l'analisi (beat, battute, segmenti, livelli)
<hash>.wav               l'audio decodificato
<hash>.wdef.txt          l'indice per l'elenco brani del gioco
```

L'`hash` è un UUID a 32 caratteri esadecimali, lo stesso formato dei file veri.

---

## 5. Il livello in più: la coreografia scritta

Tutto quanto sopra produce un `trackdata`, cioè *"questa sezione è carica
così"*. Quali pugni far comparire lo decide poi BoxVR a runtime, pescando a
caso dal suo repertorio.

Il tool sa fare un passo oltre: scrivere una **MusicActionList**, la lista di
azioni colpo per colpo — tipo di mossa, lato, posizione, istante esatto.
Questo sblocca squat, schivate, parate e cambi di guardia, che con il solo
`_energyLevel` erano inesprimibili.

Due cose da sapere:

1. **Il vocabolario non è inventato.** I pattern vengono dal repertorio
   ufficiale di BoxVR (47 sequenze di 16 beat, organizzate per intensità 0-5),
   estratto dagli asset Unity della **tua** copia del gioco — vedi
   [la nota sulla patch](patch.md#il-repertorio-di-pattern).
2. **Serve la patch.** Senza, il gioco rigenera la coreografia a ogni avvio e
   butta via la nostra: la lista viene semplicemente ignorata, e l'allenamento
   generato in VR non arriva mai. Siccome tutto il senso di Genera è quella
   lista, senza patch il tool non ci fa nemmeno entrare - la card **Crea
   Workout da Mp3** resta chiusa nella schermata iniziale, e premendola
   propone di installare la patch.

### L'idea in più rispetto al gioco

Il generatore di BoxVR pesca un pattern a caso a ogni cambio di intensità:
due ritornelli identici ricevono coreografie diverse. Qui invece si usano le
**etichette delle sezioni musicali** — che si ripetono quando la sezione
torna — per dare alla stessa sezione la **stessa combinazione** ogni volta che
ricompare.

È questo che fa percepire un allenamento come *composto* invece che casuale.

---

## 6. L'anteprima workout

Prima di mettersi il visore si può guardare la coreografia scorrere: i colpi
arrivano in prospettiva con le icone reali del gioco, il colore dice il lato
(blu sinistra, magenta destra), la forma dice la direzione (jab, gancio,
montante), e c'è il suono d'impatto a tempo.

Serve a rispondere a una domanda sola, che nessun test automatico può
sostituire: *questo allenamento ha senso da ballare?*

---

## 7. Esportazione diretta nei file di gioco

Il tool sa scrivere direttamente nella libreria live di BoxVR: copia i tre
file nelle cartelle giuste e, se vuoi, crea la playlist che li contiene.

Le regole che si è dato:

- **Non scrive mai senza conferma esplicita**, e mostra prima cosa sta per
  fare.
- **Fa un backup** di quello che sta per sovrascrivere.
- **O tutto o niente**: se qualcosa va storto a metà, non lascia una
  libreria in stato intermedio.
- La logica di installazione è un modulo separato che *decide* senza
  *chiedere*: così le stesse regole valgono identiche dall'interfaccia, da uno
  script o da un test — ed è verificabile senza aprire una finestra. È il
  codice che tocca i dati reali del gioco, cioè esattamente quello che più
  merita di essere testato.
