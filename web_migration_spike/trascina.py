# -*- coding: utf-8 -*-
"""Trascinamento di file e cartelle dentro la finestra.

Il riquadro vuoto dice da sempre "Trascina qui le cartelle o i file", ma il
trascinamento non esisteva: l'interfaccia prometteva una cosa che non
faceva. Segnalato nella revisione del 03/09.

COME FUNZIONA, e perche' non basta il drop HTML
------------------------------------------------
In una pagina web un file trascinato arriva come oggetto `File`, che per
ragioni di sicurezza NON espone il percorso su disco. A noi serve proprio
quello: il tool lavora su file veri, non su contenuti caricati.

pywebview 6 risolve esattamente questo: quando un gestore di `drop` e'
registrato **dal lato Python** (`window.dom.get_element(...).on('drop', ...)`,
vedi `webview/util.py`, ramo `event['type'] == 'drop'`), la libreria
arricchisce ogni file con `pywebviewFullPath`. Registrarlo dal JavaScript
della pagina NON basta: quel ramo non viene percorso e i percorsi non
compaiono.

Le cartelle vanno percorse a mano: un drop di cartella arriva come un unico
elemento, e i file dentro li deve trovare chi riceve.
"""
import os


def percorsi_dal_drop(evento):
    """I percorsi reali dei file trascinati. Lista vuota se non ce ne sono
    (per esempio se si trascina del testo invece che dei file)."""
    dati = (evento or {}).get('dataTransfer') or {}
    fuori = []
    for f in dati.get('files') or []:
        p = f.get('pywebviewFullPath')
        if p:
            fuori.append(p)
    return fuori


def espandi(percorsi, estensioni):
    """Da percorsi misti (file e cartelle) alla lista dei soli file utili.

    Le cartelle vengono percorse in profondita': chi trascina una cartella
    di brani si aspetta che vengano presi quelli dentro, non che non succeda
    niente. L'ordine e' alfabetico per stabilita' - due trascinamenti uguali
    devono dare lo stesso risultato.
    """
    estensioni = tuple(e.lower() for e in estensioni)
    fuori = []
    for p in percorsi or []:
        if os.path.isdir(p):
            for radice, _cartelle, nomi in os.walk(p):
                for n in sorted(nomi):
                    if n.lower().endswith(estensioni):
                        fuori.append(os.path.join(radice, n))
        elif p.lower().endswith(estensioni):
            fuori.append(p)
    # senza duplicati, mantenendo l'ordine
    visti, unici = set(), []
    for p in fuori:
        k = os.path.normcase(os.path.abspath(p))
        if k not in visti:
            visti.add(k)
            unici.append(p)
    return unici


def collega(window, selettore, quando_arrivano):
    """Registra il gestore di drop su `selettore`, e lo ri-registra a ogni
    caricamento di pagina.

    Il secondo pezzo non e' un dettaglio: dentro la Dashboard le pagine si
    aprono nella STESSA finestra con `location.href`, quindi il DOM viene
    sostituito e un gestore registrato una volta sola sparirebbe al primo
    cambio di pagina - cioe' quasi subito, visto che si parte sempre dalla
    Dashboard.

    `quando_arrivano(percorsi)` riceve i percorsi veri gia' estratti.
    """
    def _registra(*_):
        try:
            elemento = window.dom.get_element(selettore)
        except Exception:
            return
        if not elemento:
            return
        try:
            elemento.on('drop', lambda e: quando_arrivano(percorsi_dal_drop(e)))
        except Exception:
            pass          # senza trascinamento si usa comunque "Aggiungi brani +"

    _registra()
    try:
        window.events.loaded += _registra
    except Exception:
        pass
