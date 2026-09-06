#!/usr/bin/env python3
# BoxVR Survivor Toolkit - Copyright (C) 2026 Luca Giuseppe Buttacavoli
#
# Questo programma e' software libero: puoi ridistribuirlo e/o modificarlo
# secondo i termini della GNU General Public License come pubblicata dalla
# Free Software Foundation, versione 3 o (a tua scelta) successiva.
#
# E' distribuito nella speranza che sia utile, ma SENZA ALCUNA GARANZIA;
# senza neppure la garanzia implicita di COMMERCIABILITA' o IDONEITA' PER UNO
# SCOPO PARTICOLARE. Vedi la GNU General Public License per i dettagli.
#
# Dovresti aver ricevuto una copia della licenza insieme a questo programma
# (file LICENSE). Altrimenti: <https://www.gnu.org/licenses/>.

r"""
Gestione Playlist BoxVR - interfaccia
======================================
Tool separato dalla GUI principale (boxvr_fixer_gui.py), per vedere/
rinominare/riordinare/rimuovere brani e cancellare le playlist gia'
installate nella libreria live. Tutta la logica vive in
boxvr_playlist_manager.py (testata senza aprire alcuna finestra) - questo
file e' solo l'orchestrazione dei widget e delle conferme.

Volutamente non importa boxvr_fixer_gui.py: quel modulo e' enorme e ha
effetti collaterali a livello di modulo (tema, font) pensati per l'app
principale - un tool separato non ha bisogno di trascinarseli dietro.
Legge comunque le stesse preferenze salvate (lingua/tema) per restare
coerente con l'app principale senza dipenderne.
"""
import json
import os
import sys
from tkinter import messagebox, simpledialog

import customtkinter as ctk

import boxvr_playlist_manager as pm

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def _settings_path():
    base = os.environ.get('APPDATA') or os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, 'BoxVR Level Fixer')
    return os.path.join(d, 'settings.json')


def _load_lang_theme():
    """Stessa preferenza lingua/tema salvata dall'app principale
    (%APPDATA%/BoxVR Level Fixer/settings.json) - letta qui in isolamento,
    senza importare boxvr_fixer_gui.py, cosi' i due tool restano coerenti
    nell'aspetto senza essere accoppiati nel codice."""
    lang, theme = 'it', 'dark'
    try:
        with open(_settings_path(), encoding='utf-8') as f:
            data = json.load(f)
        lang = data.get('lang', lang)
        theme = data.get('theme', theme)
    except Exception:
        pass
    return lang, theme


STRINGS = {
    'title': {'it': 'Gestione Playlist BoxVR', 'en': 'BoxVR Playlist Manager'},
    'playlists_header': {'it': 'Playlist installate', 'en': 'Installed playlists'},
    'refresh': {'it': 'Aggiorna elenco', 'en': 'Refresh list'},
    'rename': {'it': 'Rinomina', 'en': 'Rename'},
    'delete': {'it': 'Elimina', 'en': 'Delete'},
    'no_playlists': {'it': 'Nessuna playlist trovata nella libreria.',
                     'en': 'No playlists found in the library.'},
    'songs_header': {'it': 'Brani', 'en': 'Songs'},
    'select_playlist_hint': {'it': 'Seleziona una playlist a sinistra per vederne i brani.',
                             'en': 'Select a playlist on the left to see its songs.'},
    'move_up': {'it': '▲', 'en': '▲'},
    'move_down': {'it': '▼', 'en': '▼'},
    'remove': {'it': 'Rimuovi', 'en': 'Remove'},
    'save': {'it': 'Salva modifiche', 'en': 'Save changes'},
    'discard': {'it': 'Annulla modifiche', 'en': 'Discard changes'},
    'unsaved_indicator': {'it': ' (modifiche non salvate)', 'en': ' (unsaved changes)'},
    'confirm_switch_title': {'it': 'Modifiche non salvate', 'en': 'Unsaved changes'},
    'confirm_switch_body': {'it': 'Ci sono modifiche non salvate su questa playlist. '
                                  'Vuoi scartarle e cambiare playlist?',
                            'en': 'This playlist has unsaved changes. '
                                  'Discard them and switch playlist?'},
    'confirm_delete_title': {'it': 'Elimina playlist', 'en': 'Delete playlist'},
    'confirm_delete_body': {'it': 'Eliminare la playlist "{name}"? Verra\' spostata in una '
                                  'sottocartella di backup, non cancellata per sempre - i '
                                  'brani installati non vengono toccati.',
                            'en': 'Delete playlist "{name}"? It will be moved to a backup '
                                  'subfolder, not permanently deleted - installed songs are '
                                  'left untouched.'},
    'rename_prompt_title': {'it': 'Rinomina playlist', 'en': 'Rename playlist'},
    'rename_prompt_body': {'it': 'Nuovo nome per "{name}":', 'en': 'New name for "{name}":'},
    'rename_error_title': {'it': 'Impossibile rinominare', 'en': 'Could not rename'},
    'rename_error_exists': {'it': 'Esiste gia\' una playlist chiamata "{name}".',
                            'en': 'A playlist named "{name}" already exists.'},
    'rename_error_empty': {'it': 'Il nome non puo\' essere vuoto.',
                           'en': 'The name cannot be empty.'},
    'lang_toggle': {'it': 'EN', 'en': 'IT'},
}


def fmt_duration(seconds):
    seconds = int(round(seconds or 0))
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


class PlaylistManagerApp:
    def __init__(self):
        self.lang, self.theme = _load_lang_theme()
        ctk.set_appearance_mode(self.theme)

        self.root = ctk.CTk()
        self.root.geometry("980x560")
        self.root.title(self.t('title'))

        self.current_path = None
        self.current_data = None
        self.dirty = False

        self._build_ui()
        self.refresh_playlists()
        self._render_songs()

    def t(self, key, **kwargs):
        text = STRINGS.get(key, {}).get(self.lang, key)
        return text.format(**kwargs) if kwargs else text

    # -- costruzione interfaccia ------------------------------------------
    def _build_ui(self):
        top = ctk.CTkFrame(self.root, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(12, 4))
        self.title_label = ctk.CTkLabel(top, text=self.t('title'),
                                        font=ctk.CTkFont(size=18, weight="bold"))
        self.title_label.pack(side="left")
        self.lang_btn = ctk.CTkButton(top, text=self.t('lang_toggle'), width=44,
                                      command=self._toggle_lang)
        self.lang_btn.pack(side="right")

        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # -- colonna sinistra: elenco playlist --
        left = ctk.CTkFrame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.playlists_header = ctk.CTkLabel(left, text=self.t('playlists_header'),
                                             font=ctk.CTkFont(weight="bold"))
        self.playlists_header.pack(anchor="w", padx=10, pady=(10, 4))
        self.playlists_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.playlists_scroll.pack(fill="both", expand=True, padx=6, pady=4)
        self.refresh_btn = ctk.CTkButton(left, text=self.t('refresh'),
                                         command=self.refresh_playlists)
        self.refresh_btn.pack(fill="x", padx=10, pady=(4, 10))

        # -- colonna destra: brani della playlist selezionata --
        right = ctk.CTkFrame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.songs_header = ctk.CTkLabel(right, text=self.t('songs_header'),
                                         font=ctk.CTkFont(weight="bold"))
        self.songs_header.pack(anchor="w", padx=10, pady=(10, 4))
        self.songs_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.songs_scroll.pack(fill="both", expand=True, padx=6, pady=4)
        save_row = ctk.CTkFrame(right, fg_color="transparent")
        save_row.pack(fill="x", padx=10, pady=(4, 10))
        self.save_btn = ctk.CTkButton(save_row, text=self.t('save'), command=self._save_changes,
                                      state="disabled")
        self.save_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))
        self.discard_btn = ctk.CTkButton(save_row, text=self.t('discard'),
                                         command=self._discard_changes, state="disabled",
                                         fg_color="transparent", border_width=1)
        self.discard_btn.pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _toggle_lang(self):
        self.lang = 'en' if self.lang == 'it' else 'it'
        self.root.title(self.t('title'))
        self.title_label.configure(text=self.t('title'))
        self.lang_btn.configure(text=self.t('lang_toggle'))
        self.playlists_header.configure(text=self.t('playlists_header'))
        self.refresh_btn.configure(text=self.t('refresh'))
        self.songs_header.configure(text=self.t('songs_header'))
        self.save_btn.configure(text=self.t('save'))
        self.discard_btn.configure(text=self.t('discard'))
        self.refresh_playlists()
        self._render_songs()

    # -- elenco playlist ----------------------------------------------------
    def refresh_playlists(self):
        for w in self.playlists_scroll.winfo_children():
            w.destroy()
        self.playlists = pm.list_playlists()
        if not self.playlists:
            ctk.CTkLabel(self.playlists_scroll, text=self.t('no_playlists'),
                        wraplength=220, justify="left").pack(padx=6, pady=10)
            return
        for entry in self.playlists:
            self._build_playlist_row(entry)

    def _build_playlist_row(self, entry):
        is_current = self.current_path == entry['path']
        row = ctk.CTkFrame(self.playlists_scroll,
                           fg_color=("gray75", "gray28") if is_current else "transparent")
        row.pack(fill="x", pady=2)
        label_text = f"{entry['workout_name']}  •  {entry['num_songs']}  •  {fmt_duration(entry['duration'])}"
        if is_current and self.dirty:
            label_text += self.t('unsaved_indicator')
        label = ctk.CTkLabel(row, text=label_text, anchor="w", justify="left")
        label.pack(side="top", fill="x", padx=8, pady=(6, 2))
        for widget in (row, label):
            widget.bind("<Button-1>", lambda e, p=entry['path']: self._select_playlist(p))
        btn_row = ctk.CTkFrame(row, fg_color="transparent")
        btn_row.pack(side="top", fill="x", padx=6, pady=(0, 6))
        ctk.CTkButton(btn_row, text=self.t('rename'), width=80,
                     command=lambda p=entry: self._rename_playlist(p)).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text=self.t('delete'), width=80, fg_color="#8b2b2b",
                     hover_color="#6e2222",
                     command=lambda p=entry: self._delete_playlist(p)).pack(side="left")

    # -- selezione e visualizzazione brani -----------------------------------
    def _select_playlist(self, path):
        if path == self.current_path:
            return
        if self.dirty and not messagebox.askyesno(self.t('confirm_switch_title'),
                                                   self.t('confirm_switch_body')):
            return
        self.current_path = path
        self.current_data = pm.load_playlist(path)
        self.dirty = False
        self.refresh_playlists()
        self._render_songs()

    def _render_songs(self):
        for w in self.songs_scroll.winfo_children():
            w.destroy()
        if self.current_data is None:
            ctk.CTkLabel(self.songs_scroll, text=self.t('select_playlist_hint'),
                        wraplength=380, justify="left").pack(padx=6, pady=10)
            self.save_btn.configure(state="disabled")
            self.discard_btn.configure(state="disabled")
            return
        trackdata_dir = pm.install.boxvr_dirs()[0]
        songs = pm.songs_with_names(self.current_data, trackdata_dir=trackdata_dir)
        for s in songs:
            self._build_song_row(s, len(songs))
        self.save_btn.configure(state="normal" if self.dirty else "disabled")
        self.discard_btn.configure(state="normal" if self.dirty else "disabled")

    def _build_song_row(self, song, total):
        row = ctk.CTkFrame(self.songs_scroll)
        row.pack(fill="x", pady=2)
        text = f"{song['index'] + 1}. {song['display_name']}  ({fmt_duration(song['duration'])})"
        ctk.CTkLabel(row, text=text, anchor="w", justify="left").pack(
            side="left", fill="x", expand=True, padx=8, pady=6)
        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.pack(side="right", padx=6, pady=4)
        up_btn = ctk.CTkButton(btns, text=self.t('move_up'), width=32,
                               command=lambda i=song['index']: self._move_song(i, i - 1))
        up_btn.pack(side="left", padx=2)
        if song['index'] == 0:
            up_btn.configure(state="disabled")
        down_btn = ctk.CTkButton(btns, text=self.t('move_down'), width=32,
                                 command=lambda i=song['index']: self._move_song(i, i + 1))
        down_btn.pack(side="left", padx=2)
        if song['index'] == total - 1:
            down_btn.configure(state="disabled")
        ctk.CTkButton(btns, text=self.t('remove'), width=70, fg_color="#8b2b2b",
                     hover_color="#6e2222",
                     command=lambda i=song['index']: self._remove_song(i)).pack(side="left", padx=(2, 0))

    def _move_song(self, from_i, to_i):
        pm.move_song(self.current_data, from_i, to_i)
        self.dirty = True
        self._render_songs()
        self.refresh_playlists()

    def _remove_song(self, index):
        pm.remove_song(self.current_data, index)
        self.dirty = True
        self._render_songs()
        self.refresh_playlists()

    def _save_changes(self):
        pm.recompute_duration(self.current_data, trackdata_dir=pm.install.boxvr_dirs()[0])
        pm.save_playlist(self.current_path, self.current_data)
        self.dirty = False
        self._render_songs()
        self.refresh_playlists()

    def _discard_changes(self):
        self.current_data = pm.load_playlist(self.current_path)
        self.dirty = False
        self._render_songs()
        self.refresh_playlists()

    # -- rinomina / elimina ---------------------------------------------------
    def _rename_playlist(self, entry):
        new_name = simpledialog.askstring(
            self.t('rename_prompt_title'),
            self.t('rename_prompt_body', name=entry['workout_name']),
            initialvalue=entry['workout_name'], parent=self.root)
        if new_name is None:
            return
        try:
            new_path = pm.rename_playlist(entry['path'], new_name)
        except FileExistsError:
            messagebox.showerror(self.t('rename_error_title'),
                                 self.t('rename_error_exists', name=new_name.strip()))
            return
        except ValueError:
            messagebox.showerror(self.t('rename_error_title'), self.t('rename_error_empty'))
            return
        if self.current_path == entry['path']:
            self.current_path = new_path
            self.current_data = pm.load_playlist(new_path)
        self.refresh_playlists()

    def _delete_playlist(self, entry):
        if not messagebox.askyesno(self.t('confirm_delete_title'),
                                   self.t('confirm_delete_body', name=entry['workout_name'])):
            return
        pm.delete_playlist(entry['path'])
        if self.current_path == entry['path']:
            self.current_path = None
            self.current_data = None
            self.dirty = False
        self.refresh_playlists()
        self._render_songs()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    PlaylistManagerApp().run()
