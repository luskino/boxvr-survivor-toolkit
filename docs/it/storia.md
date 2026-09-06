# Storia del progetto

*[English version](../history.md)*

Non è un cambiamento di rotta continuo: è la stessa domanda che si allarga,
man mano che ogni risposta scopre il limite successivo.

---

## Il punto di partenza: un livello sbagliato

Tutto nasce da un'osservazione in visore. Un brano importato in BoxVR, un
ritornello pieno, e a schermo non succede niente. Il gioco aveva etichettato
quel tratto come poco intenso.

La prima domanda era quindi solo: **si può correggere quel numero?**

Aprire un `.trackdata.txt` ha dato la risposta. È JSON leggibile, e dentro c'è
una cosa sola che conta davvero: `beat._segment._energyLevel`, un intero fra 0
e 3. Da lì nasce **Correggi**: rileggere l'audio vero, calcolarne l'energia
battuta per battuta, e sistemare le etichette chiaramente sbagliate senza
toccare la struttura che il gioco aveva riconosciuto.

## Il primo limite: non c'è sempre qualcosa da correggere

Misurando la copertura dei file reali è emerso che i segmenti **non coprono
tutta la canzone**. Buchi di 6 secondi e più, e in un caso gli ultimi ~15
secondi scoperti del tutto.

Nessuna correzione può riempirli: non esiste segmento su cui agire. Serviva
costruire il `trackdata` da zero. Da qui **Genera**, e con esso il problema
del beat-tracking — che ha portato a librosa, poi a madmom quando librosa non
bastava, e infine ai due motori affiancati con passaggio automatico.

## Capire come ragiona il gioco

Per generare qualcosa di credibile bisognava sapere cosa fa BoxVR davvero, non
immaginarlo. La build risultava leggibile, e ne è uscito un quadro a due
livelli:

- il **trackdata** dice soltanto *"questa sezione è carica così"*;
- la coreografia vera e propria viene decisa **a runtime**, pescando pattern
  da un repertorio interno in base all'intensità.

Questa scoperta ha spostato l'ambizione. Se i pattern esistono già ed è il
gioco a sceglierli a caso, si può scriverli noi — ed è nata la **coreografia
esplicita**, che sblocca squat, schivate e parate, inesprimibili con il solo
`_energyLevel`. Al prezzo di [una patch](patch.md), perché il gioco rigenera e
scarta la nostra lista.

## Verificare invece di credere

Alcune convinzioni comode si sono rivelate false, e vale la pena dirlo:

- **La stabilità della griglia dei beat non predice la qualità percepita.**
  È un segnale utile e a basso costo per scegliere il motore, ma un brano con
  griglia stabile può risultare comunque brutto da ballare. L'unico giudice è
  la prova in visore.
- **Uno studio di correlazione su 20 brani** (confrontando il posizionamento
  dei colpi con quello di un generatore esterno) ha dato una correlazione
  media modesta e ha **falsificato** l'ipotesi con cui era partito. Il
  risultato negativo è servito quanto uno positivo: ha chiuso una strada.
- **"Non ci sono buchi reali"** era stato dato per assodato, e aveva
  un'eccezione vera. Corretta.

## Il sidecar

Un generatore automatico, per quanto buono, decide tutto lui. La domanda
successiva era: **e se i colpi li mettessi io?**

Il [sidecar](sidecar.md) nasce così, ed è la parte che ha richiesto più giri:
prima far convivere i colpi umani con quelli generati, poi correggere
l'imprecisione, poi agganciarli alla griglia, poi far *imparare* al tool la
cadenza e il ritmo dell'utente — e infine accorgersi che il modello dietro la
modalità "Estendi" era sbagliato in un caso frequente, e rifarlo.

## Dall'interfaccia di servizio a un'interfaccia vera

Per molto tempo l'interfaccia è stata Tkinter: funzionale, ma con un tetto
basso. Sono nati dei wireframe in Figma, e da lì la migrazione a
un'interfaccia web dentro una finestra nativa (pywebview + WebView2), con
quattro schermate.

Non è stata una riscrittura da zero: la logica — analisi, generazione,
installazione — è rimasta la stessa, verificata dagli stessi test. È cambiato
quello che ci sta sopra.

---

## Dove siamo

| componente | stato |
|---|---|
| Correggi | maturo, in uso |
| Genera (trackdata) | maturo, in uso |
| Coreografia esplicita + patch | funzionante, richiede prove in visore |
| Sidecar | funzionante; tre soglie ancora da tarare |
| Interfaccia web | beta |
| Gestione playlist | "gestione base" completa |

Due numerazioni convivono: gli eseguibili storici Tkinter (`1.29.x`) e il
toolkit sull'interfaccia nuova, ripartito da `1.0` (`BoxVR SrvToolkit`).

## Cosa resta aperto

- Le soglie del sidecar vanno tarate su prove reali, non su statistiche: nei
  workout ufficiali un "marker umano" non esiste.
- La coreografia generata **sposta** i colpi automatici sulla firma ritmica
  dell'utente; sarebbe meglio generarli direttamente su quella griglia.
- Il tool è stato collaudato soprattutto su brani ad alti BPM.
