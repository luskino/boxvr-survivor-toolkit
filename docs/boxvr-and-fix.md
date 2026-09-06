# How BoxVR works, and why "Fix" exists

*[Versione italiana](it/boxvr-e-correggi.md)*

## What happens when you import a song

BoxVR lets you add your own music. When you do, the game analyses the track
and writes two files into its library:

```
%AppData%/LocalLow/FITXR/BoxVR/Playlists/
├── TrackData/<hash>.trackdata.txt   ← the analysis
├── TrackData/<hash>.wav             ← the decoded audio
└── TrackDefinitions/<hash>.wdef.txt ← the index: artist, title, duration, BPM
```

`.trackdata.txt` is JSON. Inside it are the detected **beats**, grouped into
**bars**, and — the part that actually matters — a structure of **segments**:
the musical sections the game recognised. Intro, verse, chorus, break.

Every beat carries a reference to the segment it belongs to, and every segment
carries exactly one number:

```
beat._segment._energyLevel   →   0, 1, 2 or 3
```

**That number decides the workout.** There is nothing else: BoxVR does not
store which punches appear where. At runtime it draws movement patterns from
an internal repertoire, picking them according to the intensity of the segment
it is currently in.

| value | what happens on screen |
|---|---|
| 0 | silence: no events |
| 1 | few punches, slow |
| 2 | medium intensity |
| 3 | maximum density |

## The first problem: wrong levels

The game's automatic analysis sometimes gets it badly wrong. You find a full
chorus labelled `1`, or a quiet bridge labelled `3`. In the headset the result
is a workout that does not follow the song: you stand still while the music
explodes, and punch through the quiet part.

**Fix** addresses exactly this, and only this.

### What Fix does

1. Finds each song's `<hash>.trackdata.txt` + `<hash>.wav` pair.
2. Re-analyses the actual audio: **bass** energy (below 250 Hz) and **RMS**
   loudness, bar by bar.
3. Splits the track's energy into four bands using the distribution of that
   track — every song is judged on its own scale, not against one absolute
   threshold for all music.
4. Changes `_energyLevel` **only** when the score is clearly past the boundary
   between two bands (confidence margin, 12% by default). When in doubt it
   leaves the value the game computed.
5. **Never touches segment boundaries or structure.** It only changes the
   intensity label.

That caution is deliberate: the game did analyse the musical structure with
its own tools, and rewriting it from the outside based on energy alone would
produce a worse result, not a better one.

### The intensity preset

Beyond fixing, you can shift the **ratio** between "punches only" sections and
mixed ones (squats, dodges, blocks), choosing between three presets. Nothing
is invented: it redistributes levels along the same energy curve that was
already measured.

## The second problem: the gaps

Fix has one hard limit: **it operates on segments that exist.** Where the game
defined no segment at all, there is nothing to correct.

And the gaps are real. Verified on actual library tracks: holes of 6 seconds
and more between one segment and the next, and in one case the final ~15
seconds of the song left entirely uncovered. In the headset those stretches
are silence, however loud the music is.

No correction can fill them, because there is no segment to act on. That is
where the other tool comes from: **[Generate](generate.md)**, which builds the
`trackdata` from scratch, covering the whole song by construction.
