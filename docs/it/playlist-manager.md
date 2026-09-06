# Gestione playlist

*[English version](../playlist-manager.md)*

Strumento separato dal resto, per mettere in ordine le playlist **già
installate** nella libreria di BoxVR — l'alternativa ad aprire i
`.workoutplaylist.txt` con un editor di testo e sperare di non sbagliare una
virgola.

## Cosa fa

- **Vede** le playlist installate, con i brani che contengono, il titolo reale
  di ciascuno e la durata.
- **Rinomina** una playlist.
- **Riordina** i brani, o ne **rimuove** qualcuno.
- **Cancella** una playlist intera.

## Cosa non fa, di proposito

L'ambito è stato deciso esplicitamente e si chiama *"gestione base"*: solo
operazioni sulla struttura della playlist. **Niente** unione di playlist,
**niente** rilevamento di duplicati fra playlist diverse. Sono cose sensate,
ma appartengono a una eventuale "gestione avanzata" futura, e mescolarle qui
avrebbe reso lo strumento più difficile da capire e da verificare.

## Come è fatto

Riusa i moduli dell'installazione (percorsi della libreria, nome visualizzato
di un brano, durata) invece di duplicare per la terza volta nel progetto i
percorsi e lo schema del file. Come l'installatore, la logica non sa nulla di
interfaccia: **decide, non chiede**. Le conferme restano a chi la chiama.

Vale la stessa cautela di tutto ciò che tocca la libreria vera: backup prima
di scrivere, e nessuna operazione lasciata a metà.
