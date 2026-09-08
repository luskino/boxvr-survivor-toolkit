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

### Two numbers, not one

`VERSION_WEB` is what someone downloading sees, and it moves **only when a
release actually goes out**. `BUILD` is the internal counter: it moves on every
rebuild and resets to zero when a release is published. The file is named
`BoxVR SrvToolkit 1.2.0 build 6.exe` while work is in progress, and
`BoxVR SrvToolkit 1.2.0 Public Beta.exe` when it is the one being published.

This exists because for two days the public number moved on every rebuild:
1.2.0, 1.3.0, 1.3.1, 1.3.2, 1.3.3 — five versions nobody ever saw. A reader
would have found five entries for what is, from their side, one change, and
the numbers missing between two releases would have looked like withdrawn
versions. The public number never needed to distinguish builds; it only needed
not to overwrite a file, and that is what `BUILD` is for.

The same applies to this file: work between releases accumulates under the one
entry that is *not yet released*, and it is that single entry the release notes
are written from.

---

## 1.2.0 — 8 September 2026

The tuning table, and a panel to use it: the numbers that decide how a
workout *feels* are now visible, adjustable, and you can watch the effect
while you change them. Plus four defects found during a real VR workout.

### Added

- **Tuning is a feature, not a debug hatch.** It sits behind the **Advanced**
  button in the workout preview, follows the app language like everything else
  — all 25 value names, descriptions, block titles and provenance tags — and
  has its own guide: [docs/tuning.md](docs/tuning.md).
- **Scroll the track with the mouse wheel** over the preview. The step is
  musical, not a fixed time: one beat per notch, a quarter of a beat with
  Shift — because what you are looking at is the distance between two hits,
  and that distance is measured in beats everywhere else in the program.
- **Space pauses the preview**, as in any player — but never while you are
  typing in the panel, where a space is a space.
- **Two numbering schemes.** `VERSION_WEB` is what someone downloading sees and
  moves only when a release goes out; `BUILD` is the internal counter. In two
  days the public number had burned through five versions nobody ever saw.
  `rilascia.py` promotes an internal build to a public release.

- **Tuning panel.** Open a track's workout preview and press **Advanced** (or
  `Ctrl+Shift+T`): 25 adjustable values appear as sliders beside the preview.
  Move one and the choreography is rebuilt — 33 ms measured — so you see the
  effect instead of imagining it. Nothing is written to disk until you press
  Save. Full guide: [docs/tuning.md](docs/tuning.md).
- **Every value carries where it came from** — *measured* on the game,
  *confirmed* in VR, or *chosen* and never verified — and a range that refuses
  the absurd with a message saying why, rather than ignoring it in silence.
  This is what makes the panel safe to hand to anyone: the guardrails are in
  the values, not in hiding the panel.
- **Values grouped by what they affect**, in three collapsible blocks: on every
  kind of workout, only on what the tool generates, only on the hits you throw.
  The grouping was *measured*, not deduced from reading the code — each value
  was pushed to an extreme and the result compared across all three modes.
- **A reset next to each slider**, not only one for everything: while looking
  for one value you move five, and when one has gone too far you want that one
  back without losing the other four.
- **Methods**: a named setting, in a `tuning/` folder next to the executable,
  picked from a dropdown. Import and export go through the system file dialog,
  and each method carries who made it, what for, when, and with which version —
  a bag of numbers from a stranger does not tell you whether it still applies
  to the build you are holding. On import you are told what your version does
  not recognise, rather than having it applied half-way in silence. **A method
  that holds up in VR can ship with a release.**
- **`confronta_tuning.py`**: regenerates the same track with and without your
  tuning and puts the measurements side by side, averaged over several
  generations. A table with no way to see the effect does not remove the
  guesswork — it moves it from whoever writes the code onto whoever uses it.

### Fixed — what using the panel turned up

Every one of these was found by driving the sliders and watching the preview,
which is the whole reason the panel exists.

- **The rule now starts from the positioning.** Until now the only answer to
  "these two do not fit" was to shift the move or drop it. Now:

      is there room for two SWINGS?    yes → keep them    no ↓
      they become two STRAIGHTS
      is there room for two STRAIGHTS? yes → keep them    no → the second one goes

  Same principle already used for squat chains — the instant stays, the move
  changes — brought to where it mattered most. Measured with dense markers:
  **0 violations** across four combinations of breathing room and exemption,
  against 19 before.
- **Raising the breathing room removed the wrong punches.** With the full
  exemption on your markers, the breathing rules did not touch your own hits:
  raising the value deleted 12 automatic punches — which are not the problem —
  and left 13 close pairs, all of them yours. The exemption now defaults to
  applying to straight punches but not to hooks and uppercuts, which are wide
  movements you cannot throw back to back. Measured cost with realistic
  markers: **none**, 115 of 115 markers kept.
- **The exemption only looked at the first of the two hits.** A hook right
  after a straight got through, and no slider could push it away. Verified in
  runtime. It now looks at both: a wide movement counts whether it comes first
  or second.
- **There was no breathing room *before* a swing.** We only looked at the hit
  that came first, so `hook → jab` asked for the swing rule while
  `jab → hook` asked for the ordinary one. The official repertoire makes no
  such distinction: a full beat minimum in all four cases (before a swing, 8
  cases on the same arm and 141 on the other; after, 4 and 154). New value,
  `breathing room before a swing`.
- **A separate breathing room for your own hits.** 1.225 works well between
  two hits you marked, but imposing it on everything made two figures in the
  euclidean catalogue unplayable — tresillo and wide cinquillo sit at exactly
  1 beat, as the official repertoire does. The automatic layer builds on the
  game's own figures; your markers do not.
- **The preview refused to rebuild on already-generated tracks.** Those are
  exactly the ones the dropdown lists, and at startup none of them has an
  analysis in memory, so every slider did nothing. The analysis is now computed
  on demand when you move a slider.
- **In the visualizer, every block was drawn with a squat under it.** A block
  drew a bar — the same shape used for a squat — plus the shield icon just
  below it, so it read as *squat + shield* always, and the two separated as
  they approached. There were **zero** blocks simultaneous with a squat in the
  data: it was not a squat, it was its shape. A block on its own now draws only
  the shield; the bar stays for the squat+block combo, where it is real.
- **The track name is gone from the playback bar.** It repeated what the
  dropdown above already said and cost up to 260px — exactly what the position
  slider needs, since its precision is the one thing there that depends on
  length.

### Fixed — found during a real VR workout

- **Low punches did not exist.** Not rare: **zero**, on every preset and in
  every mode, against 4.3% in the game itself. No hooks to the body, no low
  blocks. They now follow the proportions measured on the official repertoire,
  verified across twelve generations: low hooks at 8.8%.
- **Punches came too soon after a hook or an uppercut.** 44–50% of the moves
  that followed one landed under a beat away, with minimums of **0.00** — an
  uppercut and a jab at the very same instant. The 1.5-beat rule only applied
  to the same arm; on alternating sides half a beat was enough. It is now 0.75
  beats, i.e. +125 ms at 120 bpm, and moves under a full beat dropped to 6%.
  *Deliberately less than the full beat the game uses: copying that would make
  our choreographies as sparse as its own.*
- **A high block arriving next to a squat.** Reported twice, six weeks apart.
  The rule turns out to be **deterministic**, measured without a single
  exception: a block paired with a squat is low 12 times out of 12, a block on
  its own is high 44 out of 44. You crouch and block low, or you stand and
  block high — a high block while crouched is a position that does not exist.
  A first attempt used a random 21% quota: the right number with the wrong
  mechanism, since drawing at random produces exactly the two things the game
  never does.
- **"No obstacles" only worked halfway.** It reached your own markers but not
  the automatic layer, so its squats all survived: 11 measured in Harmonize and
  5 in "Markers only", with a chain of eight. They now go, and the block+squat
  combo goes with them.
- **Squat chains had no limit.** Measured up to eight in a row; the official
  repertoire reaches sixteen but with a median of one. Past the limit a squat
  becomes a punch: the instant stays, the move changes.
- **Extend learned where you punch, not how much.** Marking two hits per beat
  is 241 punches/min while the most intense preset targets 88 — a **2.7×** gap,
  pulled back to the ceiling every time. That is why it "could not learn
  punches in quick succession". It now follows your cadence when you set a
  faster pace than the preset.
- **An uppercut and a hook on the same arm, almost touching.** Your own markers
  are exempt from the spacing rules — that is what makes "your marker always
  wins" true — but the exemption was all-or-nothing, so nothing could separate
  them. How wide it goes is now yours to choose, because the two requests in
  play are both legitimate and in conflict: *let me pack my own hits closer*
  against *these two are too close together*.

### Fixed — the same track now gives the same choreography

Generating a track twice, with the same markers, produced two different
workouts: the seed came from the clock. The purely automatic layer never had
this problem — it derives its seed from title|artist on purpose — but the path
that uses your markers did not honour it. Nobody had noticed, because there is
no reason to generate the same track twice, until a panel arrives that does it
twenty times in a row. Moving a slider now changes only what that slider
governs: **236 of 278 instants stay untouched** instead of everything
reshuffling.

### Fixed — in the tools themselves

- **The panel never regenerated anything.** A cache one level below the request
  keyed itself on the *track* settings, with nothing about the tuning in it:
  move a slider, the key does not change, back comes the previous
  choreography. Measured: 279 hits before and 279 after, at the same instants
  to the millisecond. It was not one value — it was every value.
- **The panel failed silently.** When a rebuild could not be done, the handler
  simply returned, leaving no trace anywhere. That is the reason the defect
  above survived two days of use.
- **Twelve values were frozen at import**, taken as a parameter's *default*,
  which in Python is evaluated once at definition. Adjusting through the file
  worked; adjusting from the panel did nothing.
- **The workout preview was squeezed** when the panel opened, and the track
  name in the playback bar repeated what the dropdown already said while
  costing the position slider the width it needs.

### On the tests

Several checks verified **the wrong thing, and verified it well**: one compared
exact lanes instead of sides, another counted as a violation a gap the program
allows on purpose. The guard against dead knobs checked that a value was
*read*, not that it was read *every time*. And the guard between the engines'
constants and what actually appears on screen did not exist at all — which is
how a panel that regenerated nothing stayed green for two days.

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
