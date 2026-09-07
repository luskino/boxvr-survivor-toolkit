# BoxVR Survivor Toolkit

*[Read in English](README.md)*

Strumenti per creare e correggere allenamenti personalizzati per **BoxVR**
(FitXR) su PC, partendo dai tuoi mp3.

> **Progetto di modding non ufficiale.** Non è affiliato, sponsorizzato né
> approvato da FitXR. "BoxVR" e i marchi correlati appartengono ai rispettivi
> titolari. Vedi [Avvertenze](#avvertenze) prima di usarlo.

![La schermata iniziale con la patch installata: Correggi è chiusa, Crea un allenamento da MP3 è aperta](docs/img/dashboard-patched.png)
![La schermata iniziale senza patch: Crea un allenamento da MP3 è chiusa e propone di installarla](docs/img/dashboard-unpatched.png)

*La schermata iniziale, con la patch (sopra) e senza (sotto). **Delle due
porte ne è aperta una sola per volta**, e a decidere è la patch del gioco.
**Correggi** lavora sui livelli di intensità che ha scritto BoxVR, quindi
resta chiusa finché la patch è attiva — con la patch il gioco legge la
coreografia esplicita, e quei livelli non decidono più niente. **Genera** è il
contrario: la coreografia che scrive la legge solo un gioco patchato, quindi
senza patch resta chiusa e propone di installarla, invece di lasciarti
generare un allenamento che in VR non arriverebbe mai.*

---

## Cosa fa

BoxVR sa importare una tua canzone, ma il risultato è spesso deludente: il
gioco analizza il brano da solo, e la mappa che ne esce può avere tratti
piatti dove la musica è carica, oppure buchi in cui non succede niente. Questo
toolkit interviene su quel punto, in tre modi diversi.

| strumento | cosa fa | serve la patch? |
|---|---|---|
| **Correggi** | rilegge l'audio di un brano già importato dal gioco e sistema i livelli di intensità sbagliati | no |
| **Genera** | costruisce un brano nuovo da un mp3, con copertura completa e senza buchi | **sì** |
| **Gestione playlist** | rinomina, riordina e ripulisce le playlist già installate | no |

![La pagina Correggi: anteprima del brano con forma d'onda, curva di carica e le fasi assegnate da BoxVR](docs/img/fix-page.png)

*__Correggi__. La forma d'onda e' l'audio vero; le bande colorate sono le fasi che ha assegnato BoxVR, e la linea ciano e' l'energia misurata dal tool. Dove le due non vanno d'accordo, li' l'allenamento sembra sbagliato.*

![La pagina Genera: la stessa anteprima, piu' il pannello di generazione e l'elenco dei brani](docs/img/generate-page.png)

*__Genera__. Stessa anteprima, ma qui le fasi si costruiscono da zero e coprono tutto il brano. I contatori sotto il cursore dell'intensita' sono il conteggio vero di cio' che verra' generato, non una stima che poi cambia.*

![Il pannello di generazione: preset di intensita', cursore dei soli pugni e i contatori delle fasi](docs/img/panel-automatic.png)

*Il pannello di generazione. Il preset sceglie il repertorio delle mosse e la cadenza di riferimento, misurata sugli allenamenti del gioco stesso, che stanno in media a 82 colpi al minuto.*

E, dentro Genera:

- **Sidecar** — batti a tempo tu i colpi che vuoi, il tool costruisce
  l'allenamento attorno ai tuoi.
- **Anteprima workout** — guardi la coreografia scorrere prima di metterti il
  visore.

![Registrazione sidecar: i marker viola battuti a mano, sopra la forma d'onda](docs/img/sidecar-recording.png)

*__Sidecar__. Le righe viola sono colpi battuti a mano mentre il brano suona.
Tre modalità decidono cosa succede dopo: tenere solo i tuoi, intrecciarli con
quelli generati, oppure imparare il tuo ritmo e portarlo avanti per il resto
del brano.*

![Il selettore di modalità con Estendi spento, e un riquadro che spiega che servono 45 secondi e 8 colpi](docs/img/extend-locked.png)

*__Estendi__ resta spento finché non ha qualcosa da cui imparare. Imita la
cadenza e il ritmo dei colpi che hai marcato, e quattro colpi non sono un
ritmo — così, invece di ripiegare in silenzio su un allenamento generico sotto
un nome che promette altro, il pulsante dice cosa gli serve e a che punto sei.*

![L'anteprima workout: colpi e un ostacolo che arrivano verso chi guarda](docs/img/workout-preview.png)

*__Anteprima workout__. La coreografia, prima del visore: i colpi che arrivano a tempo, gli ostacoli da schivare o parare, e i segni gialli che mostrano dove sono caduti i tuoi colpi.*

---

## Da dove si comincia

1. Scarica l'ultima versione da [Releases](../../releases).
2. Serve **Microsoft Edge WebView2 Runtime** (di solito già presente su
   Windows 10/11; se manca, l'app lo dice e ti indirizza).
3. Avvia l'exe. Non richiede installazione e non tocca niente finché non
   glielo chiedi tu.

Per usarlo dai sorgenti: vedi [CONTRIBUTING.md](docs/it/contribuire.md).

---

## Documentazione

| documento | argomento |
|---|---|
| [Come funziona BoxVR](docs/it/boxvr-e-correggi.md) | il formato `trackdata`, perché i livelli sbagliano, cosa fa **Correggi** |
| [Genera](docs/it/genera.md) | analisi del brano, BPM, motori librosa/madmom, algoritmo di generazione, esportazione |
| [Sidecar](docs/it/sidecar.md) | marcare i colpi a mano e farli convivere con quelli automatici |
| [La patch al gioco](docs/it/patch.md) | perché serve, cosa cambia esattamente, come si annulla |
| [Gestione playlist](docs/it/playlist-manager.md) | lo strumento separato per le playlist installate |
| [Storia del progetto](docs/it/storia.md) | da dov'è partito, come ci è arrivato |
| [Il ruolo dell'IA](docs/it/ia.md) | quanto di questo codice è stato scritto da un'IA, e come |
| [Licenze di terze parti](THIRD_PARTY_NOTICES.md) | ogni libreria, font e suono incluso, con la sua licenza |
| [Changelog](CHANGELOG.it.md) | cosa è cambiato in ogni versione, e come è stato misurato |

---

## Avvertenze

**Fai un backup della tua libreria BoxVR prima di usare gli strumenti che
scrivono nel gioco.** Il tool ne fa uno per conto suo, ma un backup tuo è
un'altra cosa.

- **Il tool scrive nella cartella dati di BoxVR** solo quando glielo chiedi
  esplicitamente, e ti mostra prima cosa sta per fare.
- **La patch modifica un file del gioco** (`Assembly-CSharp.dll`). È
  reversibile in due modi: il tool tiene un backup con data e ora, e
  "Verifica integrità dei file" di Steam ripristina comunque l'originale.
  Vedi [docs/patch.md](docs/it/patch.md).
- **Non distribuire i file generati che contengono musica altrui.** Il tool
  produce anche un `.wav` del tuo brano: è la tua copia della tua musica, e
  resta tale.
- **Testato principalmente con allenamenti ad alti BPM.** Su brani lenti il
  risultato è meno collaudato.

---

## Licenza

**GNU General Public License v3.0** — vedi [LICENSE](LICENSE).

    BoxVR Survivor Toolkit
    Copyright (C) 2026 Luca Giuseppe Buttacavoli

    Questo programma è software libero: puoi ridistribuirlo e/o modificarlo
    secondo i termini della GNU General Public License come pubblicata dalla
    Free Software Foundation, nella versione 3 della licenza o (a tua scelta)
    in una versione successiva.

    Questo programma è distribuito nella speranza che sia utile, ma SENZA
    ALCUNA GARANZIA; senza neppure la garanzia implicita di COMMERCIABILITÀ o
    IDONEITÀ PER UNO SCOPO PARTICOLARE. Vedi la GNU General Public License per
    maggiori dettagli.

In parole semplici: usalo, modificalo, condividilo. Se lo distribuisci —
modificato o no — devi passare avanti anche il sorgente, sotto la stessa
licenza. Nessuno può chiuderlo dentro un prodotto proprietario.

Le librerie, i font e i suoni di terze parti hanno licenze proprie, elencate in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); sono tutte compatibili con
la GPL.

**Cosa NON è in questo repository, di proposito:** nessun dato di BoxVR. Non
i brani, non le mappe ufficiali, non il repertorio di pattern del gioco, non
gli assembly. Quei dati appartengono a FitXR. Dove servono, il tool li ricava
dalla **tua** copia legittima del gioco, con lo strumento di estrazione
incluso — è il modo in cui si fa modding senza ridistribuire l'opera altrui.

---

## Trasparenza sull'IA

Gran parte di questo codice e dell'interfaccia è stata scritta da un modello
linguistico (Claude, Anthropic) sotto la direzione dell'autore, in sessioni di
lavoro durate settimane. Non è un dettaglio da nascondere in fondo a un file:
vedi [docs/ia.md](docs/it/ia.md) per cosa significa in pratica, cosa è stato
verificato e come, e dove stanno i limiti.
