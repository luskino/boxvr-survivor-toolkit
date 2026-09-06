# The game patch

*[Versione italiana](it/patch.md)*

> **Only needed for written choreography.** Fix, Generate (trackdata) and the
> playlist manager all work without touching the game at all. If you do not
> care about punch-by-punch choreography, you can ignore this page.

## Why it is needed

BoxVR stores a `musicActionList` field inside a user playlist: the punch-by-
punch action list. The tool knows how to write it (see
[Generate §5](generate.md#5-the-extra-layer-written-choreography)).

The problem is that the game **regenerates it on every start and throws ours
away**. In `GameStateTraining.OnEnableGameState` the sequence is, in essence:

```csharp
List<MusicAction> list = null;
if (list != null) goto PLAY;                             // dead condition
MusicActionFactory.instance.GenerateActionSequence(...); // ← writes into musicActionList
list = playlist.songs[i].musicActionList;                // ← and the next line reads it back
PLAY:
sequencer.PlaySequence(list);
```

`GenerateActionSequence` writes into `songs[i].musicActionList`, and the next
line reads from there. Neutralising just that call makes the line read the
list the playlist loader already deserialised from our file instead.

## Exactly what changes

**42 bytes replaced with NOPs**, at offset `0xFE47` of `Assembly-CSharp.dll`.
Nothing else.

Why this is a contained change:

- **Same length**: 42 bytes in, 42 bytes out. No offset shifts, no table needs
  recomputing.
- **Net stack effect: zero.** The block contains only the argument loads and
  the call to a `void` method. Before and after, the stack is identical.
- **The tool verifies the bytes before writing.** If it does not find exactly
  the expected sequence it stops: that means the game version differs from the
  one the patch was built against.

## How to undo it

Two independent routes, both working:

1. **The tool's backup.** A timestamped copy is saved before writing. Command:
   `python "patch boxvr/patch_boxvr.py" --revert` (restores from the most recent backup), or
   the corresponding button in the interface.
2. **Steam.** "Verify integrity of game files" restores the original at any
   time, even if you lost the backups.

To just see the current state: `python "patch boxvr/patch_boxvr.py" --check`.

## The pattern repertoire

Written choreography uses BoxVR's **original** movement vocabulary: 47
sequences of 16 beats (4 bars) each, organised by intensity 0-5. They are not
invented: they are the same patterns the game itself would use.

That repertoire is **FitXR's creative content and is not distributed with this
tool**. What the tool contains instead is the **extractor**, which pulls it
from your installed copy of the game: it sits in `BoxVR_Data/resources.assets`
as a plain-text Unity TextAsset, preceded by its own length as 4 little-endian
bytes — so it can be read exactly, without balancing braces and without any
Unity asset library.

This is the standard modding pattern: distribute the tool, not someone else's
work. It also has a practical benefit — if a game update changed the
repertoire, you just re-extract it.

## Risks, stated plainly

- **Modifying a game's files may violate its terms of service.** That is your
  decision and your responsibility.
- A **game update** overwrites the DLL: the patch must be reapplied, and if
  the code changed it may no longer apply.
- The patch touches nothing related to anti-cheat, networking or purchases. It
  neutralises one local procedural-generation call.
- **Back up your BoxVR library** before you start.
