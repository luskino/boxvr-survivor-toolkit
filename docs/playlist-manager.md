# Playlist manager

*[Versione italiana](it/playlist-manager.md)*

A tool separate from the rest, for tidying up playlists **already installed**
in the BoxVR library — the alternative to opening the
`.workoutplaylist.txt` files in a text editor and hoping not to misplace a
comma.

## What it does

- **Lists** installed playlists, with the tracks they contain, each track's
  real title, and its duration.
- **Renames** a playlist.
- **Reorders** tracks, or **removes** one.
- **Deletes** an entire playlist.

## What it deliberately does not do

The scope was decided explicitly and is called *"basic management"*: only
operations on the playlist's structure. **No** merging of playlists, **no**
duplicate detection across different playlists. Those are sensible things, but
they belong to a possible future "advanced management", and mixing them in
here would have made the tool harder to understand and to verify.

## How it is built

It reuses the installation modules (library paths, a track's display name, its
duration) rather than duplicating the paths and the file schema for the third
time in the project. Like the installer, the logic knows nothing about the
interface: it **decides, it does not ask**. Confirmations stay with the caller.

The same caution applies as everywhere that touches the real library: back up
before writing, and no operation left half-done.
