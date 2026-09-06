# Third-party notices

*[Versione italiana](docs/it/licenze-terze-parti.md)*

The code in this project is distributed under the **GNU General Public
License v3.0** ([LICENSE](LICENSE)). This file lists everything that belongs
to someone else: libraries, fonts, sounds — and the data that is **not**
distributed at all.

---

## A note on mutagen, now resolved

`mutagen` is GPL-2.0-or-later, and for a while it was the one dependency that
did not fit: an MIT-licensed executable bundling it would have become a
GPL-derived work, which MIT alone did not account for.

Since this project moved to **GPL-3.0**, the conflict is gone: GPL-2.0-**or
later** is compatible with GPL-3.0, so nothing needs replacing and no extra
declaration is required. Every dependency below is GPL-compatible.

## Python libraries

| library | licence | role |
|---|---|---|
| numpy | BSD-3-Clause | numerical computing |
| scipy | BSD-3-Clause | filters and signal analysis |
| librosa | ISC | "fast" beat tracking, audio analysis |
| soundfile (libsndfile) | BSD-3-Clause | audio read/write, including MP3 |
| mutagen | GPL-2.0-or-later | ID3 tags — compatible, see the note above |
| sounddevice (PortAudio) | MIT | audio playback |
| tkinterdnd2 | MIT | file drag-and-drop (historical interface) |
| customtkinter | MIT | widgets (historical interface) |
| pywebview | BSD-3-Clause | native window for the web interface |
| bottle | MIT | local server used by pywebview |
| proxy_tools | MIT | pywebview dependency |
| numba / llvmlite | BSD-2-Clause | acceleration used by librosa |
| scikit-learn, joblib, threadpoolctl | BSD-3-Clause | librosa dependencies |
| pooch, soxr, msgpack, decorator, lazy_loader | BSD / Apache-2.0 | librosa dependencies |
| cffi / pycparser | MIT | soundfile dependencies |
| pythonnet / clr_loader | MIT | pywebview Windows dependencies |

**PyInstaller** (used to build the executable, not contained in it) is
GPL-2.0-or-later **with an exception**: the exception explicitly permits
distributing executables produced with it under any licence.

**madmom** — the optional "precise" beat-tracking engine. It is **not
included** in the repository or in the executable: it lives in a separate
binary that must be rebuilt from source following `madmom_worker/BUILD.md`.
Whoever rebuilds it is bound by madmom's own terms, which include restrictions
on commercial use: if you intend commercial use, check them before
redistributing that binary.

**Microsoft Edge WebView2 Runtime** — a system component provided by
Microsoft, required by the interface. It is not redistributed: if it is
missing, the app points you to the official installer.

---

## Fonts

**Poppins** (Regular, Medium, SemiBold, Bold) — Indian Type Foundry,
distributed through Google Fonts under the **SIL Open Font License 1.1**.

The OFL permits redistribution, including embedded in software, provided the
full licence text accompanies the font files and they are not sold on their
own. The complete text is in [`fonts/OFL.txt`](fonts/OFL.txt).

---

## Sounds

**`assets/sfx/hit_punch.wav`** — the "Short boxing punch" effect from
[Mixkit](https://mixkit.co/free-sound-effects/punch/), under the *Mixkit Sound
Effects Free License*: free use, including commercial, with no attribution
required; embedding it in a larger piece of software is permitted; reselling
or redistributing it as a standalone audio sample is **not**.

It is not BoxVR's original sound. Extracting that from the game's files would
have been an infringement: it is protected creative work, unlike the pattern
data used as an algorithmic reference. A free effect as close as possible was
chosen instead.

---

## Graphics

The interface icons and components (SVG in
`web_migration_spike/mockups/assets/`, PNG in `data/icons/`) come from
wireframes created by the project's author in Figma, and exported from there.

---

## What is NOT in this repository

Nothing belonging to FitXR. Explicitly excluded from version control:

| excluded | what it is |
|---|---|
| `archivio libreria gioco/` | the real BoxVR library (trackdata, wav, playlists) |
| `data/training_sequences.json` | the official pattern repertoire, extracted from Unity assets |
| `data/official_workouts/`, `data/reference_maps/` | research material derived from game data |
| `patch boxvr/*.dll` | the game assemblies, original and patched |
| test audio folders | commercial music, not part of this project |

Where any of that data is needed at runtime, the tool obtains it from **your**
installed copy of the game via the included extractor (`boxvr_extract.py`).
This is the standard modding pattern: distribute the tool, not someone else's
work.

The executable does not bundle it either — verified, and the reason is
recorded in `BoxVR_Toolkit_web.spec`. Without the repertoire, the tool raises a
dedicated error explaining how to obtain it, rather than failing obscurely.

---

## Trademarks

"BoxVR" and related marks belong to **FitXR**. This project is not affiliated
with, sponsored by, or endorsed by FitXR, and the name is used solely to
identify the software the tool interoperates with.
