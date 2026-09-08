# Tuning the algorithm

*[Versione italiana](it/tuning.md)*

The toolkit builds choreographies from rules with numbers in them: how much
breathing room after a hook, how many hooks go to the body, how many squats in
a row. Those numbers are visible and adjustable, and you can watch the effect
while you change them.

You do not need this to use the tool. It is there for when a workout feels
almost right and you can name what is off.

---

## Opening it

Open a track's **workout preview**, then press **Advanced** (or `Ctrl+Shift+T`).
A panel opens beside the preview.

Move a slider: the choreography is rebuilt — 33 ms measured — and you see the
new one right there, at the position you were already looking at. Nothing is
written to disk until you press **Save to file**.

## What the three blocks mean

The values are grouped by **what they affect**, because that is the first
question when something looks wrong and you do not know which slider to reach
for. The grouping was measured, not guessed: each value was pushed to an
extreme and the result compared across all three ways of generating.

| Block | Applies to |
|---|---|
| **On every kind of workout** | automatic, mixed and markers-only alike |
| **Only on what the tool generates** | the automatic layer: Automatic, Harmonize, Extend — *not* "Markers only" |
| **Only on the hits you throw** | how your markers are filtered, snapped, and how far they may ignore the rules |

Each block opens and closes on its own. One that holds a changed value says so
even while closed, and opens itself when you load a set that touches it.

## The tag next to each value

This is the most important thing in the panel, and the reason it can be handed
to anyone:

| Tag | What it means |
|---|---|
| **measured** | taken from the game's own files, or from the 465 official workouts. Changing it moves you away from how BoxVR behaves. |
| **confirmed** | chosen by us and then tried in a VR session. |
| **chosen** | chosen by us and never verified in the headset. This is where there is most room to play. |

A value outside its allowed range is refused with a message saying why, not
silently ignored. The ranges are what stops an unusable setting: the panel is
open to everyone precisely because the guardrails are in the values.

## The honest warning

A setting can be wrong in a way you will not see on screen. `minimum breathing
room` at 0.25 raises no error and produces a choreography that is physically
impossible to keep up with — and you find out twenty minutes into a workout.

The preview tells you whether a number moved things the way you meant. Only the
headset tells you whether the result is *good*.

If you want to go back, **Reset** returns everything to factory values, and the
small ↺ next to each slider returns only that one — useful, because while
looking for one value you tend to move five.

---

## Methods: a setting with a name

One set of values is enough while you are looking for *one* setting. Looking,
you find several good for different things — a sparser one for slow tracks, a
denser one for fast ones — and with a single file the second erases the first.

A **method** is a named set, stored in a `tuning/` folder next to the
executable. The dropdown at the top of the panel picks one; **Default** is
simply the absence of a choice, i.e. factory values.

- **Save as…** stores what you are currently trying, with your name and a note
  about what it is good for.
- **⬆** exports it to a file you choose.
- **⬇** imports one you were given, and applies it immediately.
- **🗑** deletes the selected method.

Each method carries who made it, what for, when, and with which version of the
tool. That is not bureaucracy: a bag of numbers from a stranger does not tell
you whether it still applies to the build you are holding. On import you are
told what your version does not recognise, rather than having it applied
half-way in silence.

**Methods are meant to travel.** If you find a setting that holds up in VR,
send it — a good method can ship with a release.

---

## Without the panel

The same values can be set in a `tuning.json` file next to the executable, and
that is what a method file is. `tuning.esempio.json`, written at every startup,
lists all of them with their range, description and tag. Write **only what you
change**: everything else stays at factory values, so the file does not go
stale when new values are added. Changes made this way apply at the next start.

For measuring the effect from a terminal, without the headset, see
[contributing.md](contributing.md).
