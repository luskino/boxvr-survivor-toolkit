# The role of AI in this project

*[Versione italiana](it/ia.md)*

## In short

**Almost all of the code and the interface was written by a large language
model** (Claude, by Anthropic), across weeks of work sessions, under the
direction of the project's author.

This is not a footnote. If you are deciding whether to trust this software —
or thinking about contributing to it — it is one of the most important things
to know, and it deserves to be stated in full rather than hinted at.

## Who did what

**The author** decided what to build and why: the goals, the scope of each
tool, the product decisions, the interface design in Figma. And above all did
the one thing no model can do in his place: **test the workouts in the
headset** and report what did not work. Almost every significant correction in
this project came from there.

**The model** wrote the code, the tests, the verification tooling and this
documentation; reverse-engineered the file format and the game's behaviour;
proposed solutions and, on several occasions, proposed wrong ones before right
ones.

## What was done to avoid trusting it blindly

A language model produces plausible code as easily as it produces correct
code. The difference is not visible by reading. The countermeasures, in order
of usefulness:

**Measure instead of deduce.** Wherever a claim could be checked, it was
checked: interface measurements read from the live DOM at runtime rather than
estimated from the code; colour contrast computed rather than eyeballed; the
generation engine's behaviour simulated on concrete cases rather than inferred
from its comments.

**Extensive automated tests**, both on the logic (the sidecar engine has over
100 checks) and on the interface (audits for code, icons, measurements against
the wireframe, legibility in both themes, accessibility).

**Verify the binary, not just the sources.** Every executable is rebuilt and
then inspected byte by byte, to confirm the fixes actually made it in. At
least once they were in the sources and not in the executable.

**Test the checks by injecting the defect.** A check that has never seen
anything fail is not a check: it is reassurance. At least once an audit came
back green because it was broken, not because the code was sound.

## Typical failure modes that showed up

Stated openly, because this is the instructive part:

- **Diverging copies of the same rule.** More than once the same logic ended
  up written in two places, and the two copies drifted apart: once the
  interface announced a behaviour the engine did not have. The remedy is
  always the same — one function, used by both.
- **Badly posed checks.** Verifications that looked for something in the wrong
  place and reported "missing" when nothing was missing.
- **Plausible but unmeasured fixes**, contradicted by the first real
  measurement.
- **Misplaced confidence in its own comments.** A comment saying "identical to
  X" does not make the code identical to X.

## What this means for you

- **The code is readable and unusually heavily commented**: the comments
  explain *why* a choice was made and what had been tried before. That is
  useful material if you want to understand or modify it.
- **Do not take any claim on trust without checking it**, including the claims
  in this documentation. Where a number is measured, it says so; where it is a
  choice, it says that too.
- **This software touches the data of a game you paid for.** Make a backup.
  The safeguards described in the documentation are real and implemented, but
  they are not a substitute for your own backup.

## On ownership of the result

The code is published under the GNU General Public License v3.0 by the
project's author. Who holds copyright in model-generated code is, as of
publication, not fully settled in many jurisdictions — several copyright
offices have taken the position that a work generated without sufficient human
authorship is not protectable.

That uncertainty is worth stating rather than glossing over, because a
copyleft licence rests on copyright: where no right is held, no condition can
be imposed. It applies to any licence choice, not only this one.

What is not uncertain is the human contribution: the goals, the scope of each
tool, the interface design, the product decisions, and the headset testing
from which nearly every significant correction came. Selection, arrangement
and direction are authorship. The licence states the intent clearly — this
stays open, and nobody closes it up — and that intent is the point.
