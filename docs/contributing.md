# Contributing

*[Versione italiana](it/contribuire.md)*

## Running from source

You need **Python 3.14** (the optional madmom engine is the only part that
needs an older one, and it lives outside — see below).

```bash
pip install -r requirements.txt
```

New interface (web, inside a native window):

```bash
python web_migration_spike/main.py
```

Historical interface (Tkinter):

```bash
python boxvr_fixer_gui.py
```

On Windows the new interface needs the **WebView2 Runtime**; it is normally
already present on Windows 10/11.

## Before opening a pull request

This project has an above-average amount of automated verification, and that
is deliberate: most of the code was written by a language model (see
[ai.md](ai.md)), and the checks are the countermeasure.

```bash
python "sidecar sandbox/test_engine.py"     # the sidecar engine
python web_migration_spike/verifica.py      # every interface check
python tests/test_playability.py            # one of the core logic tests
```

`verifica.py` covers: static code analysis, icons, measurements and colours
against the wireframes, legibility in **both** light and dark themes,
accessibility, parity between pages, and a live check with a window open that
the page script is not broken.

The core logic tests are the `test_*.py` files in [`tests/`](../tests).

### Tests bring their own audio

No test needs music you have to supply. `web_migration_spike/fixture_brano.py`
synthesises a short track — audio plus a matching `trackdata` — on the fly.
Earlier the tests read the author's own working folder, which meant commercial
music that cannot be in a public repository: anyone cloning found a red test
with no way to make it pass.

Three tests of the choreography preview report **skipped** rather than failed
when the pattern repertoire is absent. That repertoire is FitXR content and by
design is not in the repository — it is extracted from your own copy of the
game when you apply the patch. A red result there would send you hunting for a
defect that does not exist.

## How the interface pages are composed

Careful, this is the project's most common source of mistakes: **Fix,
Dashboard and Playlist are generated** from `genera_real/index.html` by the
scripts in `web_migration_spike/_build_correggi/`.

If you modify the Generate page, recompose the others:

```bash
python web_migration_spike/rigenera.py
```

And **look at the output**: `rigenera.py` checks its exit code, but if you
discard it you will not notice. It has happened.

Extraction works **by name**: anonymous blocks and bare `const`/`let` do not
travel. If you add a function that also needs to exist on the other pages, add
it to the extraction lists.

## Building the executable

Bump `VERSION_WEB` in `version.py` **before** compiling — the number goes into
the filename, and that is how you avoid overwriting a previous build.

```bash
python -m PyInstaller --noconfirm --distpath dist_web --workpath build_web BoxVR_Toolkit_web.spec
```

The madmom engine (`madmom_worker.exe`) is optional, not versioned, and is
rebuilt separately: see `madmom_worker/BUILD.md`.

## Style

- **Comments are in Italian**, like the rest of the project.
- Comments explain the **why**, not the what: what had been tried before,
  which measurement led to a choice, which real defect caused a line to exist.
  It is the project's strongest convention and what makes it readable weeks
  later.
- Where a number is **measured**, say so and say against what. Where it is a
  **choice**, say that too.

## What never to submit

No BoxVR data: tracks, official maps, the pattern repertoire, the game
assemblies. They belong to FitXR, and `.gitignore` excludes them on purpose.
No commercial music in the test folders.

---

## The tuning table

The values that decide how the choreography *feels* — how much breathing room
after a hook, how many hooks go to the body, how many squats in a row — live
in `tuning.py` and are adjusted from a `tuning.json` file next to the
executable, without touching the code.

```bash
python tuning.py                       # writes a complete tuning.esempio.json
cp tuning.esempio.json tuning.json     # then change what you need
```

Write **only what you change**: everything else stays at factory values, so
the file does not go stale when new ones are added. A value outside its
allowed range is rejected with a message saying why, not silently ignored.
It applies on restart.

Every value carries **where it came from**, and that is the most important
part of the table:

| provenance | means |
|---|---|
| `misurato` | taken from the game's own files or the 465 official workouts. Changing it moves you away from how BoxVR behaves. |
| `provato` | chosen by us and then confirmed in a VR session. |
| `scelto` | chosen by us and never verified in the headset. This is where there is most room to play. |

### Seeing the effect without the headset

```bash
python confronta_tuning.py "a track.mp3"
```

Regenerates the same track with and without your tuning and puts the
measurements side by side — density, low lanes, squat chains, gaps after a
swing.

This half is not an accessory. A table of adjustable values, on its own, does
not remove the guesswork: it moves it from whoever writes the code to whoever
uses it. On 7 September that is exactly what happened to the author: chasing
the missing low punches, he made three rounds of changes measuring on a
single track each time, and on the third discovered the fix had worked from
the first — he had been chasing the noise of one sample. That is why
`confronta_tuning` averages several generations rather than one.

The headset is still needed to say whether the choreography is *good*. Not to
know whether a number moved the way you wanted.

### Adjusting while you watch

`tuning.json` works on the "change it, restart" contract. That is fine for an
occasional adjustment and unusable for twenty attempts in a row — which is
what looking for a value actually takes.

Open a track's **workout preview** and press **Advanced** (or `Ctrl+Shift+T`).
A panel opens beside the preview with the same 24 values as sliders. Move one:
the choreography regenerates — 33 ms measured — and you see the new one right
there. Nothing is written to disk until you press Save.

The values are grouped by **what they affect**, because that is the first
question when something looks wrong and you do not know which slider to reach
for:

| block | applies to |
|---|---|
| on every kind of workout | automatic, mixed and markers-only alike |
| only on what the tool generates | the automatic layer: Automatic, Harmonize, Extend — not "Markers only" |
| only on the hits you mark | how your markers are filtered, snapped, and how far they may ignore the rules |

Each block opens and closes on its own; one that holds a changed value says so
even while closed, and opens itself when you load a set that touches it.

### Methods: an adjustment set with a name

One `tuning.json` is enough while you are looking for *one* setting. But
looking, you find several good for different things — a sparser one for slow
tracks, a denser one for fast ones — and with a single file the second erases
the first.

A **method** is the same format, with a name, in a `tuning/` folder next to
the executable. The dropdown at the top of the panel chooses one;
"Predefinito" is simply the absence of a choice, i.e. factory values.

Methods are meant to **travel**. Import and export go through the system file
dialog, not a hidden folder, because a file you can point at is a file you can
attach to a message. Each one carries who made it, what for, when, and with
which version of the tool — a bag of numbers from a stranger does not even
tell you whether it still applies to the build you are holding. On import you
are told what your version does not recognise, rather than having it applied
half-way in silence.

If you find a setting that holds up in VR, send it: a good method can ship
with a release.
