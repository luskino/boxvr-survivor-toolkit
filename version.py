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

"""Versione dell'app - incrementata ad ogni nuova build dell'exe cosi' i vecchi
eseguibili non vengono mai sovrascritti (build_exe.bat la usa nel nome del file)."""

VERSION = "1.29.2"

# Il toolkit sul framework web ha una numerazione SUA, ripartita da 1.0 con
# il nome nuovo ("BoxVR SrvToolkit <versione> Public Beta.exe"). Non riusa VERSION
# perche' quella e' condivisa con i due eseguibili Tkinter storici
# (BoxVR_Level_Fixer e BoxVR_Playlist_Manager, oggi a 1.27.18): azzerarla li
# farebbe tornare indietro di ventisette versioni.
#
# Come per VERSION, va incrementata PRIMA di ricostruire: il numero finisce
# nel nome del file, quindi due build diverse non possono piu' sovrascriversi
# a vicenda. E' esattamente cosi' che si e' persa la 1.29.1, quando lo spec
# produceva sempre "BoxVR_Toolkit_web.exe".
# Schema: MAJOR.MINOR.PATCH, e durante la beta si incrementa il PATCH.
#
# La 1.1.0 fa eccezione, e vale la pena dire perche': le 1.0.1-1.0.27
# sono state ventisette giri di collaudo fra due persone, la 1.1.0 e' la
# prima che chiunque puo' scaricare. Salire di MINOR segna quel confine
# nell'elenco delle release, che altrimenti sarebbe una fila piatta di
# patch dove non si capisce dove comincia la storia pubblica.
# Le prime build sono state numerate 1.0, 1.1, 1.2, 1.3 - cioe' bruciando
# una minor per ogni giro di correzioni, che e' troppo: la minor si alza
# quando cambia qualcosa di sostanziale, non a ogni ricompilazione.
# Rinumerate di conseguenza: 1.0 -> 1.0.0, 1.1 -> 1.0.1, 1.2 -> 1.0.2,
# 1.3 -> 1.0.3, sia nel nome del file sia dentro l'archivio delle vecchie
# versioni.
# La prossima release PUBBLICA. Avanza solo quando si pubblica davvero -
# l'ultima uscita e' la 1.1.2, quindi questa e' cio' che uscira' la prossima
# volta. Tutto il lavoro fra una release e l'altra sta in BUILD qui sotto.
#
# Cambiato l'08/09. Prima questo numero avanzava a ogni ricompilazione, e in
# due giorni era passato per 1.2.0, 1.3.0, 1.3.1, 1.3.2, 1.3.3: cinque
# versioni mai uscite. Chi legge il changelog trovava cinque voci per quello
# che dal suo lato e' un cambiamento solo, e i numeri mancanti fra due
# release sembravano versioni ritirate.
VERSION_WEB = "1.2.0"

# Il contatore interno: avanza a OGNI ricostruzione, si azzera quando si
# pubblica. Serve alla ragione pratica per cui il numero finiva nel nome del
# file - due build diverse non devono potersi sovrascrivere - senza per
# questo consumare numeri pubblici.
#
# 0 = questa e' la build che si pubblica, e il file si chiama
# "... Public Beta.exe". Sopra lo zero il file si chiama "... build N.exe".
BUILD = 0
