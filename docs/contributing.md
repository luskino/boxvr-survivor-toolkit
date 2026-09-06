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
