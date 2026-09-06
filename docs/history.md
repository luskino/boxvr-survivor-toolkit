# Project history

*[Versione italiana](it/storia.md)*

This is not a series of course changes: it is the same question widening, as
each answer uncovers the next limit.

---

## The starting point: one wrong level

It began with something noticed in the headset. A track imported into BoxVR, a
full chorus, and nothing happening on screen. The game had labelled that
stretch as low intensity.

So the first question was only: **can that number be fixed?**

Opening a `.trackdata.txt` answered it. It is readable JSON, and inside there
is exactly one thing that matters: `beat._segment._energyLevel`, an integer
from 0 to 3. That is where **Fix** comes from: re-read the real audio,
calculate its energy bar by bar, and repair the clearly wrong labels without
touching the structure the game had recognised.

## The first limit: there is not always something to fix

Measuring the coverage of real files revealed that the segments **do not cover
the whole song**. Gaps of 6 seconds and more, and in one case the final ~15
seconds left entirely uncovered.

No correction can fill those: there is no segment to act on. The `trackdata`
had to be built from scratch. Hence **Generate**, and with it the beat-tracking
problem — which led to librosa, then to madmom when librosa was not enough,
and finally to the two engines side by side with automatic escalation.

## Understanding how the game thinks

To generate something credible, it was necessary to know what BoxVR actually
does rather than imagine it. The build turned out to be readable, and a
two-level picture emerged:

- the **trackdata** only says *"this section is loaded like this"*;
- the choreography itself is decided **at runtime**, drawing patterns from an
  internal repertoire according to intensity.

That discovery raised the ambition. If the patterns already exist and the game
merely picks them at random, we can write them ourselves — and that produced
**explicit choreography**, unlocking squats, dodges and blocks that were
inexpressible through `_energyLevel` alone. At the cost of [a patch](patch.md),
because the game regenerates and discards our list.

## Verifying instead of believing

Some convenient beliefs turned out to be false, and that is worth saying:

- **Beat-grid stability does not predict perceived quality.** It is a useful,
  cheap signal for choosing the engine, but a track with a stable grid can
  still be unpleasant to dance to. The only judge is testing in the headset.
- **A correlation study across 20 tracks** (comparing punch placement against
  an external generator) produced a modest average correlation and
  **falsified** the hypothesis it started from. The negative result was worth
  as much as a positive one: it closed off a direction.
- **"There are no real gaps"** had been taken as settled, and had a genuine
  exception. Corrected.

## The sidecar

An automatic generator, however good, decides everything itself. The next
question was: **what if I place the punches?**

The [sidecar](sidecar.md) came from that, and it is the part that took the
most iterations: first making human punches coexist with generated ones, then
correcting imprecision, then snapping them to the grid, then teaching the tool
to *learn* the user's cadence and rhythm — and finally realising that the
model behind "Extend" was wrong in a common case, and redoing it.

## From a utility interface to a real one

For a long time the interface was Tkinter: functional, but with a low ceiling.
Wireframes were designed in Figma, and from there came the migration to a web
interface inside a native window (pywebview + WebView2), with four screens.

It was not a rewrite: the logic — analysis, generation, installation — stayed
the same, verified by the same tests. What changed is what sits on top.

---

## Where things stand

| component | state |
|---|---|
| Fix | mature, in use |
| Generate (trackdata) | mature, in use |
| Explicit choreography + patch | working, needs headset testing |
| Sidecar | working; three thresholds still to tune |
| Web interface | beta |
| Playlist manager | "basic management" complete |

Two version numbers coexist: the historical Tkinter executables (`1.29.x`) and
the toolkit on the new interface, restarted from `1.0`
(`BoxVR SrvToolkit`).

## What is still open

- The sidecar thresholds need tuning against real sessions, not statistics: a
  "human marker" does not exist in the official workouts.
- Generated choreography currently **moves** automatic punches onto the user's
  rhythmic signature; generating them directly on that grid would be better.
- The tool has mostly been tested on high-BPM tracks.
