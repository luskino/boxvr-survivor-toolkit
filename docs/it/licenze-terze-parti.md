# Licenze di terze parti

*[English version](../../THIRD_PARTY_NOTICES.md)*

Il codice di questo progetto è distribuito sotto **GNU General Public License
v3.0** ([LICENSE](../../LICENSE)). Questo file elenca tutto ciò che è di altri: librerie,
font, suoni, e i dati che **non** vengono distribuiti affatto.

---

## Una nota su mutagen, ormai risolta

`mutagen` è GPL-2.0-or-later, e per un po' è stata l'unica dipendenza fuori
posto: un eseguibile sotto MIT che la includesse sarebbe diventato un'opera
derivata soggetta a GPL, cosa che il solo MIT non copriva.

Da quando il progetto è passato a **GPL-3.0** il conflitto non esiste più:
GPL-2.0-**or later** è compatibile con la GPL-3.0, quindi non c'è niente da
sostituire e nessuna dichiarazione aggiuntiva da fare. Tutte le dipendenze qui
sotto sono compatibili con la GPL.

## Librerie Python

| libreria | licenza | ruolo |
|---|---|---|
| numpy | BSD-3-Clause | calcolo numerico |
| scipy | BSD-3-Clause | filtri e analisi del segnale |
| librosa | ISC | beat-tracking "veloce", analisi audio |
| soundfile (libsndfile) | BSD-3-Clause | lettura/scrittura audio, incluso mp3 |
| mutagen | GPL-2.0-or-later | tag ID3 — compatibile, vedi la nota sopra |
| sounddevice (PortAudio) | MIT | riproduzione audio |
| tkinterdnd2 | MIT | trascinamento file (interfaccia storica) |
| customtkinter | MIT | widget (interfaccia storica) |
| pywebview | BSD-3-Clause | finestra nativa per l'interfaccia web |
| bottle | MIT | server locale usato da pywebview |
| proxy_tools | MIT | dipendenza di pywebview |
| numba / llvmlite | BSD-2-Clause | accelerazione usata da librosa |
| scikit-learn, joblib, threadpoolctl | BSD-3-Clause | dipendenze di librosa |
| pooch, soxr, msgpack, decorator, lazy_loader | BSD / Apache-2.0 | dipendenze di librosa |
| cffi / pycparser | MIT | dipendenze di soundfile |
| pythonnet / clr_loader | MIT | dipendenze Windows di pywebview |

**PyInstaller** (usato per costruire l'eseguibile, non incluso in esso) è
GPL-2.0-or-later **con eccezione**: l'eccezione consente esplicitamente di
distribuire eseguibili prodotti con esso sotto qualunque licenza.

**madmom** — motore di beat-tracking "preciso", opzionale. **Non è incluso**
nel repository né nell'eseguibile: vive in un binario separato che va
ricompilato dai sorgenti seguendo `madmom_worker/BUILD.md`. Chi lo ricompila è
soggetto alle condizioni di madmom, che includono restrizioni sull'uso
commerciale: se prevedi un uso commerciale, verificale prima di redistribuire
quel binario.

**Microsoft Edge WebView2 Runtime** — componente di sistema fornito da
Microsoft, richiesto per l'interfaccia. Non viene ridistribuito: se manca,
l'app rimanda all'installatore ufficiale.

---

## Font

**Poppins** (Regular, Medium, SemiBold, Bold) — Indian Type Foundry, distribuito
tramite Google Fonts sotto **SIL Open Font License 1.1**.

La OFL consente la ridistribuzione, anche incorporata in un software, a
condizione che il testo integrale della licenza accompagni i file del font e
che questi non vengano venduti da soli. Il testo completo è in
[`fonts/OFL.txt`](../../fonts/OFL.txt).

---

## Suoni

**`assets/sfx/hit_punch.wav`** — effetto "Short boxing punch" da
[Mixkit](https://mixkit.co/free-sound-effects/punch/), sotto *Mixkit Sound
Effects Free License*: uso libero, anche commerciale, senza attribuzione
richiesta; consentito incorporarlo in un software più ampio; **non** consentito
rivenderlo o ridistribuirlo come campione audio a sé stante.

Non è il suono originale di BoxVR. Estrarre quello dai file del gioco sarebbe
stata una violazione: è un'opera creativa protetta, cosa diversa dai dati di
pattern usati come riferimento algoritmico. È stato scelto un effetto libero il
più simile possibile.

---

## Grafica

Le icone e i componenti dell'interfaccia (SVG in
`web_migration_spike/mockups/assets/`, PNG in `data/icons/`) provengono dai
wireframe realizzati dall'autore del progetto in Figma, ed esportati da lì.

---

## Cosa NON è in questo repository

Nulla che appartenga a FitXR. In particolare, esclusi esplicitamente dal
versionamento:

| escluso | cos'è |
|---|---|
| `archivio libreria gioco/` | la libreria BoxVR reale (trackdata, wav, playlist) |
| `data/training_sequences.json` | il repertorio ufficiale dei pattern, estratto dagli asset Unity |
| `data/official_workouts/`, `data/reference_maps/` | materiale di ricerca derivato dai dati del gioco |
| `patch boxvr/*.dll` | gli assembly del gioco, originale e patchato |
| cartelle audio di test | musica commerciale, non di questo progetto |

Dove uno di questi dati serve al funzionamento, il tool lo ricava dalla **tua**
copia installata del gioco tramite l'estrattore incluso (`boxvr_extract.py`).
È il pattern standard del modding: si distribuisce lo strumento, non l'opera
altrui.

---

## Marchi

"BoxVR" e i marchi correlati appartengono a **FitXR**. Questo progetto non è
affiliato, sponsorizzato né approvato da FitXR, e il nome è usato unicamente
per identificare il software con cui il tool interopera.
