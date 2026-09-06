# -*- coding: utf-8 -*-
"""Esercita il percorso "WebView2 non installato" su una macchina che ce l'ha.

PERCHE' NON SI DISINSTALLA E BASTA
-----------------------------------
Sembra la prova piu' onesta, e invece e' quella che dice meno:

1. Su questo PC WebView2 e' un componente di SISTEMA. Non ha una voce in
   "App installate" (nessuna chiave sotto ...\\CurrentVersion\\Uninstall):
   c'e' solo il setup.exe interno del runtime, che va forzato a mano.
2. Lo usano altre applicazioni. Su questa macchina almeno tre hanno una
   cartella EBWebView, fra cui Illustrator: toglierlo rompe loro, non solo
   la nostra prova.
3. **E lo rimetterebbe Microsoft.** L'attivita' pianificata di Edge Update
   ri-approvvigiona il runtime evergreen da sola. Anche riuscendo a
   toglierlo, un esito positivo non direbbe se l'ha reinstallato il nostro
   tool o Edge Update mentre guardavamo: la prova sarebbe ambigua proprio
   sul punto che vuole dimostrare.

Quello che serve davvero sapere e' se il NOSTRO codice si comporta bene
quando il runtime manca. Quella e' una domanda sul codice, e si risponde
facendo mentire il rilevamento invece di mutilare il sistema.

    python test_webview2_assente.py
"""
import io
import os
import sys
import winreg

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI)
sys.path.insert(0, os.path.dirname(QUI))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import webview2_check as wc

esiti = []


def prova(nome, condizione, dettaglio=''):
    esiti.append((bool(condizione), nome, dettaglio))


class RegistroSenzaWebView2:
    """Fa sparire SOLO le chiavi di WebView2, lasciando intatto il resto del
    registro: cosi' si prova il ramo "assente" senza toccare niente sul
    disco, e la macchina resta esattamente com'era."""

    def __enter__(self):
        self.originale = winreg.OpenKey
        guid = wc._WEBVIEW2_GUID

        def finta(hive, path, *a, **k):
            if guid in path:
                raise OSError(2, 'chiave assente (simulata)')
            return self.originale(hive, path, *a, **k)

        winreg.OpenKey = finta
        return self

    def __exit__(self, *e):
        winreg.OpenKey = self.originale
        return False


# ---- 1. il rilevamento vero funziona -------------------------------------
vera = wc.webview2_version()
prova('il runtime viene rilevato su questa macchina', bool(vera), 'versione %s' % vera)

# ---- 2. il rilevamento riconosce l'assenza --------------------------------
with RegistroSenzaWebView2():
    assente = wc.webview2_version()
    disponibile = wc.is_webview2_available()
prova('con le chiavi assenti webview2_version() torna None', assente is None,
      'ottenuto %r' % (assente,))
prova('con le chiavi assenti is_webview2_available() e\' False', disponibile is False)

# ---- 3. non solleva mai su un registro illeggibile ------------------------
originale = winreg.OpenKey
try:
    def esplode(*a, **k):
        raise PermissionError('accesso negato (simulato)')
    winreg.OpenKey = esplode
    try:
        v = wc.webview2_version()
        prova('un registro illeggibile conta come "assente", non come errore',
              v is None)
    except Exception as e:
        prova('un registro illeggibile conta come "assente", non come errore',
              False, 'ha sollevato %s: %s' % (type(e).__name__, e))
finally:
    winreg.OpenKey = originale

# ---- 4. il ramo di installazione parte davvero ----------------------------
# Non si installa niente: si sostituisce il download con una funzione che
# registra di essere stata chiamata. Serve a verificare che
# install_webview2_automatically() NON esca subito per il corto circuito
# "e' gia' presente" quando il runtime risulta assente.
chiamate = {'download': 0, 'esecuzione': 0, 'url': None, 'argomenti': None}
import subprocess
import urllib.request

vero_urlretrieve, vero_run = urllib.request.urlretrieve, subprocess.run
try:
    def finto_download(url, path):
        chiamate['download'] += 1
        chiamate['url'] = url
        io.open(path, 'wb').write(b'installer finto - non viene mai eseguito')
        return path, None

    def finta_run(cmd, *a, **k):
        chiamate['esecuzione'] += 1
        chiamate['argomenti'] = cmd[1:]        # senza il percorso del file
        class R:
            returncode = 0
        return R()

    urllib.request.urlretrieve = finto_download
    subprocess.run = finta_run
    messaggi = []
    with RegistroSenzaWebView2():
        ok = wc.install_webview2_automatically(progress_callback=messaggi.append)
finally:
    urllib.request.urlretrieve, subprocess.run = vero_urlretrieve, vero_run

prova('con il runtime assente tenta il download', chiamate['download'] == 1)
prova('scarica dal link ufficiale Microsoft',
      chiamate['url'] == wc.BOOTSTRAPPER_URL, chiamate['url'])
prova('esegue il bootstrapper una volta sola', chiamate['esecuzione'] == 1)
prova('lo esegue in modo SILENZIOSO (/silent /install)',
      chiamate['argomenti'] == ['/silent', '/install'], repr(chiamate['argomenti']))
prova('riferisce l\'esito senza dare per scontato il successo', ok is False,
      'con un installer finto il runtime non compare: deve tornare False')
prova('parla all\'utente durante l\'attesa', len(messaggi) >= 2,
      ' | '.join(messaggi))

# ---- 5. il file temporaneo viene ripulito --------------------------------
import tempfile
residuo = os.path.join(tempfile.gettempdir(), 'MicrosoftEdgeWebview2Setup.exe')
prova('non lascia l\'installer nella cartella temporanea',
      not os.path.exists(residuo), residuo)

# ---- 6. il messaggio di ripiego non dipende da WebView2 ------------------
import inspect
sorgente = inspect.getsource(wc.show_missing_webview2_message)
prova('il messaggio di errore usa Tkinter, non pywebview',
      'tkinter' in sorgente and 'webview.' not in sorgente,
      'deve poter comparire proprio quando WebView2 manca')

# ---- 7. tutti i main() controllano PRIMA di aprire la finestra -----------
for pagina in ('genera_real', 'correggi_real', 'dashboard_real', 'playlist_real'):
    p = os.path.join(QUI, pagina, 'app.py')
    if not os.path.isfile(p):
        continue
    testo = io.open(p, encoding='utf-8').read()
    i_check = testo.find('ensure_webview2_or_exit')
    i_win = testo.find('webview.create_window')
    prova('%s controlla WebView2 prima di create_window' % pagina.replace('_real', ''),
          i_check != -1 and i_check < i_win,
          'check a %d, create_window a %d' % (i_check, i_win))


if __name__ == '__main__':
    print('===== PERCORSO "WEBVIEW2 ASSENTE" =====')
    for ok, nome, dettaglio in esiti:
        print(('  ok      ' if ok else '  FALLITO ') + nome)
        if dettaglio and not ok:
            print('            %s' % dettaglio)
        elif dettaglio and ok:
            print('            (%s)' % dettaglio)
    n = sum(1 for e in esiti if e[0])
    print('  %d/%d superati' % (n, len(esiti)))
    print('\nNON coperto da qui: che il bootstrapper vero installi per davvero.')
    print('Quello si vede solo su una macchina senza WebView2 - e la macchina')
    print('del primo collaudo ce l\'aveva gia\'.')
    sys.exit(0 if n == len(esiti) else 1)
