#!/usr/bin/env python3
r"""
Controllo preventivo di WebView2 Runtime (31/08/2026 notte)
=============================================================
Rischio reale trovato leggendo il sorgente di pywebview (non assunto):
`webview/platforms/edgechromium.py`, `on_webview_ready` - se
`EnsureCoreWebView2Async` fallisce (runtime WebView2 assente), pywebview
si limita a un `logger.error(...)` e un `return` - NESSUN messaggio arriva
all'utente. La finestra si apre comunque, ma resta vuota/silenziosa per
sempre - il tipo di guasto peggiore per un utente non tecnico (sembra che
il programma sia "rotto", nessun indizio del perche').

Questo modulo aggiunge un controllo PRIMA di `webview.create_window()`,
cosi' l'app puo' mostrare un messaggio chiaro (via Tkinter - sempre
disponibile, non dipende da WebView2) invece di aprire una finestra vuota.

Rilevamento basato sulla stessa chiave di registro che Microsoft
documenta per verificare la presenza del runtime (il GUID del prodotto
"WebView2 Runtime", non inventato - verificato su questa macchina:
HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{GUID} ->
pv=151.0.4129.107, corrisponde al valore gia' noto da sessioni precedenti).
Tre percorsi controllati (macchina 64-bit/32-bit, utente) perche' il
runtime puo' essere installato per-macchina O per-utente a seconda di come
e' arrivato (Evergreen Bootstrapper standalone vs incluso in Windows/Edge).
"""
import os
import winreg

_WEBVIEW2_GUID = r'{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
_REG_PATHS = (
    (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\%s' % _WEBVIEW2_GUID),
    (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\EdgeUpdate\Clients\%s' % _WEBVIEW2_GUID),
    (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\EdgeUpdate\Clients\%s' % _WEBVIEW2_GUID),
)

DOWNLOAD_URL = 'https://developer.microsoft.com/microsoft-edge/webview2/'
# Link "evergreen" ufficiale Microsoft per il bootstrapper WebView2 (redirect
# stabile, ~2MB - NON il runtime intero da 150+MB: il bootstrapper scarica lui
# stesso il resto). Stesso link che Visual Studio/altri installer Microsoft
# usano per lo stesso scopo - non improvvisato.
BOOTSTRAPPER_URL = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'


def webview2_version():
    """Stringa versione (es. '151.0.4129.107') se il runtime e' installato,
    None altrimenti. Mai solleva - un registro illeggibile conta come
    'assente', non come errore fatale."""
    for hive, path in _REG_PATHS:
        try:
            with winreg.OpenKey(hive, path) as key:
                return winreg.QueryValueEx(key, 'pv')[0]
        except OSError:
            continue
    return None


def is_webview2_available():
    return webview2_version() is not None


def install_webview2_automatically(progress_callback=None):
    """Scarica il bootstrapper evergreen ufficiale ed esegue un'installazione
    SILENZIOSA (`/silent /install`, flag documentati del bootstrapper) -
    l'utente non deve andare a cercare/scaricare/cliccare nulla a mano.
    Richiede una connessione internet (il bootstrapper scarica il runtime
    vero da li'). L'installazione per-utente non richiede privilegi di
    amministratore; se il bootstrapper prova l'installazione per-macchina e
    non ha i permessi, fallisce silenziosamente e questa funzione ritorna
    False - il chiamante ricontrolla con `is_webview2_available()` e mostra
    il messaggio manuale come ultima spiaggia, non assume il successo.

    `progress_callback(msg)`, se dato, riceve righe di stato leggibili (per
    mostrarle in una UI d'attesa) - mai richiesto, l'installazione prova
    comunque anche in silenzio totale."""
    import subprocess
    import tempfile
    import urllib.request

    def log(msg):
        if progress_callback:
            progress_callback(msg)

    if is_webview2_available():
        return True

    log('Download di Microsoft Edge WebView2 Runtime...')
    installer_path = os.path.join(tempfile.gettempdir(), 'MicrosoftEdgeWebview2Setup.exe')
    try:
        urllib.request.urlretrieve(BOOTSTRAPPER_URL, installer_path)
    except OSError as e:
        log(f'Download non riuscito ({e}) - serve una connessione internet.')
        return False

    log('Installazione in corso (silenziosa)...')
    try:
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        subprocess.run([installer_path, '/silent', '/install'],
                       timeout=180, creationflags=flags, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f'Installazione non riuscita ({e}).')
        return False
    finally:
        try:
            os.remove(installer_path)
        except OSError:
            pass

    ok = is_webview2_available()
    log('Installato con successo.' if ok else 'Installazione terminata ma il runtime non risulta ancora presente.')
    return ok


def show_missing_webview2_message(after_failed_auto_install=False):
    """Messaggio via Tkinter (mai WebView2/pywebview - deve funzionare
    ANCHE quando WebView2 manca) - ultima spiaggia, mostrato solo se
    l'installazione automatica non e' stata possibile (niente internet,
    permessi negati, ecc.) - non il primo tentativo."""
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    intro = ('L\'installazione automatica di "Microsoft Edge WebView2 Runtime" non è riuscita.'
             if after_failed_auto_install else
             'Questa parte del programma richiede "Microsoft Edge WebView2 Runtime", non trovato su questo computer.')
    messagebox.showerror(
        'BoxVR Survivor Toolkit',
        intro + '\n\nScaricalo manualmente da:\n' + DOWNLOAD_URL + '\n\n'
        '(Sui PC con Windows 10/11 aggiornati è già installato di default - '
        'questo messaggio compare solo se manca o è stato rimosso.)'
    )
    root.destroy()


def ensure_webview2_or_exit():
    """Da chiamare in cima a ogni main() dei moduli _real, PRIMA di
    webview.create_window(). Se il runtime manca, prova PRIMA a installarlo
    da solo (silenzioso, nessun click richiesto all'utente) mostrando una
    finestra d'attesa minima; solo se anche questo fallisce (niente
    internet, permessi negati...) mostra il messaggio manuale come ultima
    spiaggia. Ritorna True/False - il chiamante esce pulito su False invece
    di aprire una finestra pywebview vuota."""
    if is_webview2_available():
        return True

    import threading
    import tkinter as tk

    wait_win = tk.Tk()
    wait_win.title('BoxVR Survivor Toolkit')
    wait_win.geometry('420x110')
    wait_win.resizable(False, False)
    label = tk.Label(wait_win, text='Preparazione in corso...\nInstallazione di un componente necessario (WebView2).',
                     font=('Segoe UI', 10), justify='center')
    label.pack(expand=True, fill='both', padx=16, pady=16)

    result = {'ok': False, 'done': False}

    def worker():
        result['ok'] = install_webview2_automatically(progress_callback=lambda m: wait_win.after(0, lambda: label.config(text=m)))
        result['done'] = True

    threading.Thread(target=worker, daemon=True).start()

    def poll():
        if result['done']:
            wait_win.destroy()
        else:
            wait_win.after(200, poll)
    wait_win.after(200, poll)
    wait_win.mainloop()

    if result['ok']:
        return True
    show_missing_webview2_message(after_failed_auto_install=True)
    return False


if __name__ == '__main__':
    import sys
    print("Verifica WebView2 Runtime...")
    version = webview2_version()
    if version:
        print(f"TROVATO: WebView2 Runtime {version} già installato su questo PC.")
        print("(Questa macchina non è utile per testare il percorso 'runtime mancante' -")
        print(" serve una macchina dove questo controllo dica 'NON TROVATO'.)")
        sys.exit(0)

    print("NON TROVATO: WebView2 Runtime non risulta installato su questo PC.")
    if '--install' in sys.argv:
        print("Tento l'installazione automatica silenziosa (--install passato)...")
        ok = install_webview2_automatically(progress_callback=print)
        print("Risultato:", "installato con successo" if ok else "installazione NON riuscita")
        sys.exit(0 if ok else 1)
    else:
        print("Rilancia con '--install' per tentare l'installazione automatica silenziosa")
        print("(scarica ed esegue il bootstrapper ufficiale Microsoft, ~2MB, nessun click richiesto),")
        print("oppure con '--message' per vedere il messaggio di fallback mostrato all'utente finale.")
        if '--message' in sys.argv:
            show_missing_webview2_message()
