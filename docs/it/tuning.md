# Regolare l'algoritmo

*[English version](../tuning.md)*

Il toolkit costruisce le coreografie con delle regole che hanno dentro dei
numeri: quanto respiro dopo un gancio, quanti ganci vanno al corpo, quanti
squat di fila. Quei numeri sono visibili e regolabili, e l'effetto lo vedi
mentre li cambi.

Non ti serve per usare il tool. Serve quando un workout è quasi giusto e sai
dire cosa non va.

---

## Come si apre

Apri l'**anteprima workout** di un brano e premi **Avanzate** (oppure
`Ctrl+Shift+T`). Accanto all'anteprima si apre un pannello.

Muovi uno slider: la coreografia si rigenera — 33 ms misurati — e la vedi lì,
nel punto in cui stavi già guardando. Sul disco non si scrive niente finché non
premi **Salva su file**.

## Cosa vogliono dire i tre blocchi

I valori sono raggruppati per **su cosa agiscono**, perché è la prima domanda
quando qualcosa non va e non sai quale slider toccare. Il raggruppamento è
stato *misurato*, non dedotto: ogni valore è stato portato a un estremo e il
risultato confrontato su tutti e tre i modi di generare.

| Blocco | Agisce su |
|---|---|
| **Su tutti i tipi di workout** | automatico, misto e solo marker allo stesso modo |
| **Solo sulla parte generata dal tool** | il livello automatico: Automatica, Armonizza, Estendi — *non* «Solo marker» |
| **Solo sui colpi che batti tu** | come i tuoi marker vengono filtrati, agganciati, e quanto possono infischiarsene delle regole |

Ogni blocco si apre e si chiude per conto suo. Uno che contiene un valore
modificato lo dice anche da chiuso, e si apre da solo quando carichi un assetto
che lo tocca.

## L'etichetta accanto a ogni valore

È la cosa più importante del pannello, ed è il motivo per cui si può mettere in
mano a chiunque:

| Etichetta | Cosa vuol dire |
|---|---|
| **misurato** | preso dai file del gioco, o dai 465 workout ufficiali. Cambiandolo ti allontani da come si comporta BoxVR. |
| **provato** | scelto da noi e poi provato in una sessione VR. |
| **scelto** | scelto da noi e mai verificato nel visore. È qui che c'è più margine per giocare. |

Un valore fuori dall'intervallo ammesso viene rifiutato con un messaggio che
dice perché, non ignorato in silenzio. Sono gli intervalli a impedire un
assetto inutilizzabile: il pannello è aperto a tutti proprio perché le
protezioni stanno dentro i valori.

## L'avvertenza, detta chiara

Un assetto può essere sbagliato in un modo che sullo schermo non si vede.
`respiro minimo` a 0,25 non dà nessun errore e produce una coreografia
fisicamente impossibile da stare dietro — e te ne accorgi dopo venti minuti di
allenamento.

L'anteprima ti dice se un numero ha spostato le cose nel verso che volevi. Solo
il visore ti dice se il risultato è *bello*.

Per tornare indietro, **Azzera** rimette tutto di fabbrica, e la piccola ↺
accanto a ogni slider rimette solo quello — utile, perché mentre cerchi un
valore te ne ritrovi cinque spostati.

---

## I metodi: un assetto con un nome

Un assetto solo basta finché cerchi *quell'* assetto. Cercando se ne trovano di
diversi buoni per cose diverse — uno più rado per i brani lenti, uno fitto per
i pezzi tirati — e con un file solo il secondo cancella il primo.

Un **metodo** è un assetto con un nome, in una cartella `tuning/` accanto
all'eseguibile. La tendina in cima al pannello ne sceglie uno; **Predefinito**
è semplicemente l'assenza di scelta, cioè i valori di fabbrica.

- **Salva come…** salva quello che stai provando, col tuo nome e una nota su
  per cosa va bene.
- **⬆** lo esporta in un file che scegli tu.
- **⬇** ne importa uno che ti hanno dato, e lo applica subito.
- **🗑** elimina il metodo selezionato.

Ogni metodo porta con sé chi lo ha fatto, per cosa, quando e con quale versione
del tool. Non è burocrazia: un sacchetto di numeri ricevuto da uno sconosciuto
non dice se vale ancora per la versione che hai in mano. Importandolo ti viene
detto cosa la tua versione non riconosce, invece di applicartelo a metà in
silenzio.

**I metodi sono fatti per girare.** Se trovi un assetto che regge in VR,
mandalo: un metodo fatto bene può finire in una release.

---

## Senza il pannello

Gli stessi valori si possono scrivere in un file `tuning.json` accanto
all'eseguibile — ed è esattamente quello che è un file di metodo.
`tuning.esempio.json`, scritto a ogni avvio, li elenca tutti con intervallo,
descrizione ed etichetta. Scrivi **solo quello che cambi**: tutto il resto
resta di fabbrica, così il file non invecchia quando si aggiungono valori
nuovi. Le modifiche fatte così valgono dal riavvio successivo.

Per misurare l'effetto da terminale, senza visore, vedi
[contribuire.md](contribuire.md).
