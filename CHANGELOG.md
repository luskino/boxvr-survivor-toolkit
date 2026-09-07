# Changelog

*[Versione italiana](CHANGELOG.it.md)*

Every entry says **what was wrong** and **how it was measured**, not just what
changed: a defect found in VR and one suspected on paper do not carry the same
weight, and the reader should be able to tell them apart.

The GitHub release notes are written from here.

Versions are `MAJOR.MINOR.PATCH`. During the beta the PATCH grows; the MINOR
marks a boundary (1.1.0 was the first public release).

---

## How a release happens

Four steps, in this order, none of them skipped.

1. **Bug fixing.** The corrections, each with the measurement that says what
   was wrong and by how much.
2. **Changelog and executable.** This file is updated — the release notes are
   written from it — and the executable is built, checking that the fixes are
   *inside the binary*, not only in the sources.
3. **Testing.** A person plays it, in VR.
4. **Confirmation and publishing.** Only after an explicit yes.

The third step is not a formality, and it is the one there is most temptation
to skip because the automated tests are green. But tests can only say whether
the program does what it was asked; never whether what it was asked makes
sense:

- the **dodge + simultaneous punch** combo passed eight well-written checks
  and was physically impossible to execute — your body is already moved to one
  side and half the space is taken by the obstacle;
- **Extend flattened the proportions of your rhythm** onto a single
  subdivision, and the test meant to catch it looked at one subdivision at a
  time: it could not see the defect.

Both were found in the headset, by someone in the middle of a workout.

---

## 1.2.0 — 7 September 2026

Four defects found during a real workout, and the tuning table that grew out
of how they were fixed.

### Fixed

- **Low punches did not exist.** Not rare: **zero**, on every preset and in
  every mode, against 4.3% in the game itself. No hooks to the body, no low
  blocks. They now follow the proportions measured on the official repertoire
  — Block 21% low, Hook 9%, Jab and Uppercut never — verified across twelve
  generations: low hooks at 8.8%.
- **Punches came too soon after a hook or an uppercut.** 44–50% of the moves
  that followed one landed under a beat away, with minimums of **0.00** — an
  uppercut and a jab at the very same instant. The 1.5-beat rule only applied
  to the same arm; on alternating sides half a beat was enough. It is now 0.75
  beats, i.e. +125 ms at 120 bpm, and moves under a full beat dropped to 6%.
  *Deliberately less than the full beat the game uses: copying that would make
  our choreographies as sparse as its own.*
- **"No obstacles" only worked halfway.** It reached the user's own markers
  but not the automatic layer, so its squats all survived: 11 measured in
  Harmonize and 5 in "Markers only", with a chain of eight. They now go, and
  the block+squat combo goes with them — a block paired with a squat counts as
  a squat.
- **Squat chains had no limit.** Measured up to eight in a row; the official
  repertoire reaches sixteen but with a median of one. Past the limit a squat
  becomes a punch: the instant stays, the move changes.
- **Extend learned where you punch, not how much.** Marking two hits per beat
  is 241 punches/min while the most intense preset targets 88 — a **2.7×** gap,
  pulled back to the ceiling every time. That is why it "could not learn
  punches in quick succession". It now follows your cadence when you set a
  faster pace than the preset.

### Added

- **Tuning table** (`tuning.json`): 24 values adjustable without touching the
  code, each with a range that rejects the absurd and with **where it came
  from** written next to it — measured on the game, confirmed in VR, or chosen
  and never verified. You write only what you change; the rest stays at
  factory values.
- **`confronta_tuning.py`**: regenerates the same track with and without your
  tuning and puts the measurements side by side. This is the half that counts:
  a table with no way to see the effect does not remove the guesswork, it
  moves it onto the user.

### Fixed in the tests

- Two checks verified **the wrong thing, and verified it well**: one compared
  exact lanes instead of sides (so it failed on correct choreography as soon as
  a hook could be low), the other counted as a violation a gap the program
  allows on purpose through the slider.

### Still open

- Gaps of 0.00 beats still occur between two of the user's own markers. The
  suspect is the magnetic grid snapping pulling two nearby hits onto the same
  point — **not verified, so not fixed**.
- `tests/test_onset_anchoring.py` section 7 was already red before this round.
- Three tests that open a Tkinter window time out intermittently, also from
  before this round.

---

## 1.1.2 — 6 September 2026

### Fixed

- **Generated tracks stayed on disk forever.** Measured **715 MB across 76
  files** in the results folder. The existing cleanup dealt with the temporary
  serving folders, which are a different thing. They are now cleared on close
  and on startup, deleted by extension: anything we did not produce stays
  where it is.

### Added

- Screenshots in both READMEs, with the two opening screens side by side —
  with and without the patch — so the two-doors rule reads at a glance.

---

## 1.1.1 — 6 September 2026

### Fixed

- **Dodge with a simultaneous punch: impossible to execute.** Reported from
  VR. The obvious fix — put the punch on the free side — is not possible: the
  dodge's direction **does not exist in the format**, the game picks it. The
  combo is withdrawn; the same share of squats becomes a dodge on its own,
  with the clear beat around it that the game gives them.
- **Harmonize and Extend "slid back into the BoxVR standard".** Extend learned
  the rhythm and then flattened it: it moved every punch onto the *nearest*
  allowed subdivision, so a 32%/68% marking came out 100%/0%. Harmonize did
  not learn at all. Both now place *from* the rhythm instead of moving towards
  it, at unchanged density.

---

## 1.1.0 — 6 September 2026 — first public release

### Fixed

- **Extend could be pressed before it could work**, and the explanation of why
  was unreachable to exactly the person looking for it. It now stays off until
  it has something to learn from, and states the threshold and your current
  count.
- **The energy curve did not reach the edges**: measured 12.7% empty on the
  left and 13.6% on the right, a quarter of the preview.
- **Generate could be entered without the patch**, letting you generate
  everything and discover in VR that nothing had changed. Half of this gate
  existed in the Tkinter GUI and had been lost in the port.
- **"Install into BoxVR" did not install the playlists.** Verified on the
  files: TrackData written, WorkoutPlaylists a week old. It also returned only
  the first one, and with 30-minute blocks there is more than one.
- Thirteen strings stayed in Italian while the interface was in English.

### Added

- **"BoxVR folder" always reachable** in the header, not only after a
  successful operation.
