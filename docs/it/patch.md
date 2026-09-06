# La patch al gioco

*[English version](../patch.md)*

> **Serve solo per la coreografia scritta.** Correggi, Genera (trackdata) e la
> gestione playlist funzionano senza toccare niente del gioco. Se non ti
> interessa scrivere le coreografie colpo per colpo, puoi ignorare questa
> pagina.

## Perché serve

BoxVR memorizza, dentro una playlist utente, un campo `musicActionList`: la
lista di azioni colpo per colpo. Il tool sa scriverlo (vedi
[Genera §5](genera.md#5-il-livello-in-più-la-coreografia-scritta)).

Il problema è che il gioco **la rigenera a ogni avvio e butta via la nostra**.
In `GameStateTraining.OnEnableGameState` la sequenza è, in sostanza:

```csharp
List<MusicAction> lista = null;
if (lista != null) goto PLAY;                            // condizione morta
MusicActionFactory.instance.GenerateActionSequence(...); // ← scrive dentro musicActionList
lista = playlist.songs[i].musicActionList;               // ← e la riga dopo la rilegge
PLAY:
sequencer.PlaySequence(lista);
```

`GenerateActionSequence` scrive dentro `songs[i].musicActionList`, e la riga
successiva rilegge da lì. Neutralizzando la sola chiamata, quella riga legge
invece la lista che il caricatore della playlist ha già deserializzato dal
nostro file.

## Cosa cambia esattamente

**42 byte sostituiti con NOP**, all'offset `0xFE47` di `Assembly-CSharp.dll`.
Niente altro.

Perché è un intervento contenuto:

- **Stessa lunghezza**: 42 byte dentro, 42 byte fuori. Nessun offset si
  sposta, nessuna tabella va ricalcolata.
- **Effetto netto sullo stack: zero.** Il blocco contiene soltanto il
  caricamento degli argomenti e la chiamata a un metodo `void`. Prima e dopo,
  lo stack è identico.
- **Il tool verifica i byte prima di scrivere.** Se non trova esattamente la
  sequenza attesa, si ferma: significa che la versione del gioco è diversa da
  quella su cui la patch è stata costruita.

## Come si annulla

Due strade indipendenti, entrambe funzionanti:

1. **Il backup del tool.** Prima di scrivere viene salvata una copia con data
   e ora. Comando: `python "patch boxvr/patch_boxvr.py" --revert` (ripristina dal backup più
   recente), oppure il pulsante corrispondente nell'interfaccia.
2. **Steam.** "Verifica integrità dei file di gioco" ripristina l'originale in
   qualunque momento, anche se hai perso i backup.

Per sapere solo com'è messo adesso: `python "patch boxvr/patch_boxvr.py" --check`.

## Il repertorio di pattern

La coreografia scritta usa il vocabolario di movimenti **originale** di BoxVR:
47 sequenze di 16 beat (4 battute) ciascuna, organizzate per intensità 0-5.
Non sono inventate: sono gli stessi pattern che il gioco userebbe.

Quel repertorio è **contenuto creativo di FitXR e non viene distribuito con
questo tool**. Il tool contiene invece l'**estrattore**, che lo ricava dalla
tua copia installata del gioco: sta in `BoxVR_Data/resources.assets` come
TextAsset Unity in chiaro, preceduto dalla propria lunghezza in 4 byte
little-endian — quindi si legge esattamente, senza bilanciare le graffe e
senza librerie per asset Unity.

È il pattern standard del modding: si distribuisce lo strumento, non l'opera
altrui. Ha anche un vantaggio pratico: se un aggiornamento del gioco cambiasse
il repertorio, basta riestrarlo.

## Rischi, detti chiaramente

- **Modificare i file di un gioco può violarne i termini di servizio.** È una
  tua decisione e una tua responsabilità.
- Un **aggiornamento del gioco** sovrascrive la DLL: la patch va riapplicata,
  e se il codice è cambiato potrebbe non applicarsi più.
- La patch non tocca nulla che riguardi anticheat, rete o acquisti. Modifica
  una sola chiamata di generazione procedurale in locale.
- **Fai un backup della tua libreria BoxVR** prima di cominciare.
