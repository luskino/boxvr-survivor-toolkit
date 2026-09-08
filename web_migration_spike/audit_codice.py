# -*- coding: utf-8 -*-
"""Controlli statici sul codice delle tre pagine.

Cerca le classi di errore che in questo progetto hanno gia' fatto danni:

  1. getElementById('x') su un id che NON esiste nel markup -> l'elemento e'
     null e, se non protetto, interrompe tutto lo script. E' cosi' che la
     Dashboard e' rimasta bloccata su "Rilevamento cartella di gioco..." e
     che in Correggi mancava lo stato "Rimuovi".
  2. funzioni chiamate da un attributo onclick/onmouseenter/... che non sono
     definite da nessuna parte -> errore solo al clic dell'utente, invisibile
     ai test che non cliccano.
  3. funzioni definite e mai usate (codice morto).
  4. id duplicati.
  5. bilanciamento di graffe/parentesi nello script.

Si lancia da web_migration_spike/:  python audit_codice.py
"""
import io
import sys
import os
import re
import tempfile
import subprocess
import shutil

QUI = os.path.dirname(os.path.abspath(__file__))
PAGINE = ['genera_real', 'correggi_real', 'dashboard_real', 'playlist_real']

# funzioni del browser/note: non vanno cercate fra le definizioni della pagina
NOTE = {
    'alert', 'confirm', 'prompt', 'eval', 'parseInt', 'parseFloat', 'isNaN',
    'setTimeout', 'setInterval', 'clearTimeout', 'clearInterval', 'fetch',
    'requestAnimationFrame', 'encodeURIComponent', 'decodeURIComponent',
    'Number', 'String', 'Boolean', 'Array', 'Object', 'JSON', 'Math', 'Date',
    'console', 'window', 'document', 'event', 'this', 'return', 'if', 'for',
}


def scorpora(html):
    """(markup senza script, codice degli script)"""
    script = '\n'.join(re.findall(r'<script>(.*?)</script>', html, re.S))
    markup = re.sub(r'<script>.*?</script>', ' ', html, flags=re.S)
    markup = re.sub(r'<style>.*?</style>', ' ', markup, flags=re.S)
    return markup, script


def senza_stringhe(code):
    """toglie stringhe e commenti, per contare graffe/parentesi vere"""
    out, k, st = [], 0, None
    while k < len(code):
        c = code[k]
        if st is None:
            if c in ('"', "'", '`'):
                st = c
            elif c == '/' and k + 1 < len(code) and code[k + 1] == '/':
                while k < len(code) and code[k] != '\n':
                    k += 1
                continue
            elif c == '/' and k + 1 < len(code) and code[k + 1] == '*':
                k = code.find('*/', k) + 2
                continue
            else:
                out.append(c)
        else:
            if c == '\\':
                k += 2
                continue
            if c == st:
                st = None
        k += 1
    return ''.join(out)


problemi, note, ok_count = [], [], 0

for cartella in PAGINE:
    p = os.path.join(QUI, cartella, 'index.html')
    if not os.path.isfile(p):
        continue
    html = io.open(p, encoding='utf-8').read()
    markup, script = scorpora(html)
    nome = cartella.replace('_real', '').upper()

    # --- id presenti nel markup ---
    ids = re.findall(r'\bid="([^"]+)"', markup)
    # anche quelli creati da JS (el.id = 'x')
    ids += re.findall(r"\.id\s*=\s*'([^']+)'", script)
    # e quelli scritti dentro template literal
    ids += re.findall(r"id=\\?[\"']([\w-]+)\\?[\"']", script)
    insieme_id = set(ids)

    dupli = sorted(set(i for i in ids if ids.count(i) > 1 and i in re.findall(r'\bid="([^"]+)"', markup)))
    dupli = [d for d in dupli if re.findall(r'\bid="%s"' % re.escape(d), markup).__len__() > 1]
    if dupli:
        problemi.append('%s: id duplicati nel markup: %s' % (nome, ', '.join(dupli)))
    else:
        ok_count += 1

    # --- Niente dati interpolati dentro un attributo on* ---------------
    #
    # Il 06/09 i brani con un apostrofo nel nome non si potevano
    # selezionare: l'identificativo (che in Genera E' il nome del file)
    # finiva dentro `onclick="selectSong('${s.id}')"`, e l'apostrofo
    # chiudeva la stringa prima del tempo. Il gestore non veniva mai
    # eseguito e quella riga sembrava morta, mentre le altre funzionavano -
    # ed e' il motivo per cui il difetto si leggeva come "alcuni si e altri
    # no" invece che come un errore di sintassi.
    #
    # La forma sicura e' leggere il dato dal DOM dentro il gestore
    # (`this.dataset.id`), dove non viene mai interpretato come codice.
    interpolati = []
    for m in re.finditer(r'\bon[a-z]+="([^"]*)"', html):
        corpo = m.group(1)
        if "\'${" in corpo or '"${' in corpo:
            interpolati.append(corpo.strip()[:60])
    if interpolati:
        problemi.append('%s: dato interpolato dentro un gestore evento '
                        '(un apostrofo nel valore rompe il gestore): %s'
                        % (nome, ' | '.join(interpolati[:3])))
    else:
        ok_count += 1

    # --- getElementById su id inesistenti ---
    # solo gli id LETTERALI: getElementById('pc-' + k) e' costruito a runtime
    cercati = set(re.findall(r"getElementById\(\s*'([^']+)'\s*\)", script))
    assenti = [i for i in cercati if i not in insieme_id]
    # Un id assente NON e' automaticamente un bug: nel codice condiviso fra le
    # tre pagine e' normale che un elemento esista solo in una. Lo diventa se
    # il risultato viene usato SENZA controllare che non sia null - ed e'
    # esattamente cosi' che la Dashboard si e' bloccata (playlist-cta).
    non_protetti, protetti = [], []
    for i in assenti:
        # la riga della chiamata e le 4 successive (fra la chiamata e il
        # controllo puo' esserci un commento)
        m = re.search(r"[^\n]*getElementById\(\s*'%s'\s*\)[^\n]*(?:\n[^\n]*){0,4}"
                      % re.escape(i), script)
        blocco = m.group(0) if m else ''
        sicuro = ('?.' in blocco or re.search(r'if\s*\(\s*!?\s*\w+\s*\)', blocco)
                  or '|| {}' in blocco or '|| []' in blocco
                  or re.search(r'(\w+)\s*&&', blocco)
                  or re.search(r'!\s*\w+\s*\|\|', blocco)   # "!x || ...": guardia valida
                  or re.search(r'\?\?', blocco))
        (protetti if sicuro else non_protetti).append(i)
    if non_protetti:
        problemi.append('%s: getElementById su id assenti E non protetti: %s'
                        % (nome, ', '.join(sorted(non_protetti))))
    else:
        ok_count += 1
    for i in sorted(protetti):
        note.append('%s: %s non esiste in questa pagina, ma il codice lo gestisce'
                    % (nome, i))

    # --- funzioni chiamate dagli attributi ma non definite ---
    definite = set(re.findall(r'function\s+(\w+)', script))
    definite |= set(re.findall(r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(', script))
    definite |= set(re.findall(r'window\.(\w+)\s*=', script))
    da_attributi = set()
    for attr in re.findall(r'on\w+="([^"]+)"', markup):
        # (?<![.\w]) esclude i METODI: event.stopPropagation(),
        # this.classList.toggle(), document.getElementById() non sono
        # funzioni definite dalla pagina
        da_attributi |= set(re.findall(r'(?<![.\w])([A-Za-z_]\w*)\s*\(', attr))
    for attr in re.findall(r"on\w+=\\?\"([^\"]+)\\?\"", script):
        # (?<![.\w]) esclude i METODI: event.stopPropagation(),
        # this.classList.toggle(), document.getElementById() non sono
        # funzioni definite dalla pagina
        da_attributi |= set(re.findall(r'(?<![.\w])([A-Za-z_]\w*)\s*\(', attr))
    orfane = sorted(f for f in da_attributi if f not in definite and f not in NOTE)
    if orfane:
        problemi.append('%s: funzioni chiamate da attributi ma non definite: %s'
                        % (nome, ', '.join(orfane)))
    else:
        ok_count += 1

    # --- funzioni definite e mai chiamate ---
    usate = set(re.findall(r'\b(\w+)\s*\(', script)) | da_attributi
    usate |= set(re.findall(r'window\.(\w+)', script))
    morte = sorted(f for f in definite
                   if script.count(f) <= 1 and f not in usate and not f.startswith('_'))
    if morte:
        problemi.append('%s: definite ma mai usate: %s' % (nome, ', '.join(morte)))
    else:
        ok_count += 1

    # --- la sintassi la giudica un parser, non un conteggio ---
    #
    # Prima si contavano parentesi e graffe fuori dalle stringhe. Un'euristica,
    # e come tale sbaglia: dopo le correzioni del 06/09 dava CORREGGI come
    # sbilanciata mentre il codice era valido. Se sul sistema c'e' node glielo
    # si chiede, perche' e' l'unico che lo sa davvero; se non c'e', il
    # controllo si salta DICENDOLO invece di dare un verdetto che non puo'
    # emettere.
    if shutil.which('node'):
        f = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                        encoding='utf-8')
        f.write(script)
        f.close()
        r = subprocess.run(['node', '--check', f.name], capture_output=True,
                           text=True, encoding='utf-8', errors='replace')
        os.unlink(f.name)
        if r.returncode != 0:
            dett = [x for x in (r.stderr or '').split('\n')
                    if 'Error' in x or 'error' in x]
            problemi.append("%s: lo script non e' JavaScript valido: %s"
                            % (nome, (dett[0] if dett else '').strip()[:90]))
        else:
            ok_count += 1
    else:
        saltati.append('%s: sintassi non verificata (node non installato)' % nome)

# --- prefisso del proxy dell'API, per pagina ---
# Dentro la Dashboard i metodi sono delegati con prefissi diversi:
#   Genera   -> genera_*      Playlist -> playlist_*    Correggi -> senza
# Sbagliare il prefisso rompe la pagina SOLO quando ci si arriva dalla
# Dashboard, non lanciandola da sola: un bug che i test non vedono.
ATTESO = {'genera_real': "genera_", 'correggi_real': None,
          'playlist_real': "playlist_", 'dashboard_real': None}
for cartella, atteso in ATTESO.items():
    f = os.path.join(QUI, cartella, 'index.html')
    if not os.path.isfile(f):
        continue
    html = io.open(f, encoding='utf-8').read()
    if 'const api = () => new Proxy' not in html:
        continue          # la Dashboard usa l'API diretta, senza proxy
    trovato = re.search(r"real\['(\w+_)' \+ prop\]", html)
    trovato = trovato.group(1) if trovato else None
    if trovato == atteso:
        ok_count += 1
    else:
        problemi.append('%s: proxy col prefisso %r, atteso %r'
                        % (cartella.replace('_real', '').upper(), trovato, atteso))

# ---- dichiarazioni duplicate nello stesso scope --------------------------
# IL CONTROLLO CHE MANCAVA. La pagina Genera e' arrivata ad avere QUATTRO
# copie dello stesso `let _pendente`, e nessuno dei controlli precedenti se
# n'era accorto: le graffe erano bilanciate, gli id unici, le funzioni tutte
# definite. Ma due `let` con lo stesso nome nello stesso scope sono un
# SyntaxError di PARSING, e un errore di parsing non fa fallire una riga:
# butta via l'INTERO blocco <script>. Risultato, scoperto solo dal test su
# macchina pulita: la pagina si disegnava perfetta e nessun pulsante
# rispondeva, senza un messaggio d'errore da nessuna parte - nemmeno il
# raccoglitore window.__errs, che sta dentro lo stesso blocco morto.
# Qui si guardano le dichiarazioni al primo livello del blocco (rientro di
# due spazi, lo stile di queste pagine): e' lo scope in cui la collisione e'
# fatale.
DICH = re.compile(r"^  (?:let|const|var|class)\s+([A-Za-z_$][\w$]*)", re.M)
for cartella in PAGINE:
    f = os.path.join(QUI, cartella, 'index.html')
    if not os.path.isfile(f):
        continue
    _, script = scorpora(io.open(f, encoding='utf-8').read())
    nomi = {}
    for nome in DICH.findall(senza_stringhe(script)):
        nomi[nome] = nomi.get(nome, 0) + 1
    doppi = sorted(n for n, c in nomi.items() if c > 1)
    if doppi:
        problemi.append(
            "%s: dichiarato piu' volte nello stesso scope -> SyntaxError, "
            "script morto: %s"
            % (cartella.replace('_real', '').upper(), ', '.join(doppi)))
    else:
        ok_count += 1

# ---- ogni metodo chiamato deve esistere sulla Dashboard -----------------
# Le pagine girano in due modi: da sole (con il proprio app.py) e DENTRO la
# Dashboard, che le serve tutte nella stessa finestra e rigira le chiamate
# ai moduli veri. Nel secondo caso il proxy della pagina cerca prima
# "<prefisso>_<metodo>" e poi "<metodo>" senza prefisso; se non trova ne'
# l'uno ne' l'altro la promessa viene rifiutata e - siccome quasi tutte le
# chiamate sono async - non si vede nessun errore: il comando semplicemente
# non fa niente.
#
# E' successo: mancavano genera_list_generated_tracks, genera_get_action_list,
# genera_install_preview, genera_install_run e genera_open_game_folder.
# Risultato, trovato dall'utente il 03/09: "Anteprima workout" non apriva
# niente, e "Installa in BoxVR" era rotta allo stesso modo senza che nessuno
# se ne fosse accorto.
PREFISSI = {'genera_real': 'genera_', 'playlist_real': 'playlist_',
            'correggi_real': ''}
_dash = os.path.join(QUI, 'dashboard_real', 'app.py')
if os.path.isfile(_dash):
    _testo_dash = io.open(_dash, encoding='utf-8').read()
    _esposti = set(re.findall(r'def ([a-z_]\w*)\(self', _testo_dash))
    for _cartella, _pref in PREFISSI.items():
        _f = os.path.join(QUI, _cartella, 'index.html')
        if not os.path.isfile(_f):
            continue
        _pag = io.open(_f, encoding='utf-8').read()
        # senza_stringhe toglie commenti e stringhe: senza, un api().x()
        # citato in un commento risultava una chiamata vera (successo
        # subito, con list_songs nella pagina Playlist).
        _, _sc = scorpora(_pag)
        _usati = sorted(set(re.findall(r'api\(\)\.(\w+)\(', senza_stringhe(_sc))))
        _mancanti, _ripiego = [], []
        for _m in _usati:
            if (_pref + _m) in _esposti:
                continue
            if _m in _esposti:
                _ripiego.append(_m)      # esiste, ma senza prefisso
            else:
                _mancanti.append(_m)
        if _mancanti:
            problemi.append('%s: metodi chiamati dalla pagina che la Dashboard '
                            'NON espone (comando morto, senza errore visibile): %s'
                            % (_cartella.replace('_real', '').upper(),
                               ', '.join(_mancanti)))
        else:
            ok_count += 1
        if _ripiego and _pref:
            # non e' un difetto: lingua e tema sono globali per progetto, un
            # solo settings.json per tutta l'app. Ma va detto, perche' un
            # ripiego involontario significherebbe chiamare il metodo di
            # un'ALTRA pagina senza accorgersene.
            note.append('%s: ripiegano sul metodo senza prefisso della '
                        'Dashboard (voluto per cio\' che e\' globale): %s'
                        % (_cartella.replace('_real', '').upper(),
                           ', '.join(_ripiego)))

# ---- le firme degli inoltri della Dashboard -----------------------------
# La Dashboard riespone i metodi delle altre pagine col prefisso
# (`genera_get_action_list` -> `genera_app.Api().get_action_list`). Se
# l'inoltro ha MENO parametri dell'originale, gli argomenti in piu' cadono
# per strada: il metodo esiste, viene chiamato, e fa la cosa sbagliata senza
# dare errore.
#
# Successo il 07/09: `genera_get_action_list(self, track_id)` contro
# `get_action_list(self, track_id, rigenera=False)`. Il pannello di tuning
# muoveva gli slider e l'anteprima restava congelata su disco.
import ast as _ast


def _firme(percorso):
    """{nome del metodo: numero di parametri} per ogni classe del file."""
    try:
        albero = _ast.parse(io.open(percorso, encoding='utf-8').read())
    except Exception:                      # noqa: BLE001
        return {}
    fuori = {}
    for nodo in _ast.walk(albero):
        if isinstance(nodo, _ast.ClassDef):
            for f in nodo.body:
                if isinstance(f, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    fuori[f.name] = len(f.args.args)
    return fuori


_dash = _firme(os.path.join(QUI, 'dashboard_real', 'app.py'))
_disallineati = []
for _cartella, _pref in (('genera_real', 'genera_'), ('correggi_real', 'correggi_'),
                         ('playlist_real', 'playlist_')):
    _vere = _firme(os.path.join(QUI, _cartella, 'app.py'))
    for _nome, _n in _dash.items():
        if not _nome.startswith(_pref):
            continue
        _originale = _nome[len(_pref):]
        if _originale not in _vere:
            continue
        if _n < _vere[_originale]:
            _disallineati.append(
                "%s: %s(%d parametri) inoltra %s.%s(%d) - gli argomenti "
                "in piu' cadono in silenzio"
                % (_cartella.replace('_real', '').upper(), _nome, _n - 1,
                   _cartella, _originale, _vere[_originale] - 1))
if _disallineati:
    problemi.append("DASHBOARD: inoltri con meno parametri dell'originale: "
                    + ' | '.join(_disallineati))
else:
    ok_count += 1

# ---- i due blocchi del tema scuro devono restare identici ---------------
# Il tema scuro e' scritto DUE volte: una per "il sistema e' scuro e l'utente
# non ha scelto" (media query) e una per "l'utente ha scelto scuro"
# (data-theme). Se divergono si ottengono due temi scuri diversi a seconda di
# come ci si arriva - il tipo di differenza che nessuno nota guardando una
# schermata per volta.
_css = os.path.join(QUI, 'mockups', 'styles.css')
if os.path.isfile(_css):
    _t = io.open(_css, encoding='utf-8').read()
    _a = re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)\n  \}', _t, re.S)
    _b = re.search(r':root\[data-theme="dark"\] \{(.*?)\n\}', _t, re.S)
    if _a and _b:
        _na = [l.strip() for l in _a.group(1).splitlines() if l.strip().startswith('--')]
        _nb = [l.strip() for l in _b.group(1).splitlines() if l.strip().startswith('--')]
        if _na == _nb:
            ok_count += 1
        else:
            _solo_a = [x for x in _na if x not in _nb]
            _solo_b = [x for x in _nb if x not in _na]
            problemi.append('TEMA SCURO: i due blocchi divergono - solo nella '
                            'media query: %s | solo in data-theme: %s'
                            % (_solo_a or 'niente', _solo_b or 'niente'))

# ---- ogni metodo chiamato esiste sulla Api della pagina stessa ----------
# Complementare al controllo sulle deleghe della Dashboard: quello verifica
# il caso "pagina dentro la Dashboard", questo il caso "pagina da sola".
# Nato da un difetto vero: due funzioni inserite a livello di modulo in
# mezzo alla classe `Api` l'avevano troncata, facendo sparire in silenzio
# add_files, run_generation, install_run, get_action_list e
# list_generated_tracks da genera_real.
import importlib.util as _ilu
for _cartella in PAGINE:
    _app = os.path.join(QUI, _cartella, 'app.py')
    _pag = os.path.join(QUI, _cartella, 'index.html')
    if not (os.path.isfile(_app) and os.path.isfile(_pag)):
        continue
    try:
        _spec = _ilu.spec_from_file_location('_audit_' + _cartella, _app)
        _mod = _ilu.module_from_spec(_spec)
        sys.modules['_audit_' + _cartella] = _mod
        _spec.loader.exec_module(_mod)
        _propri = {m for m in dir(_mod.Api) if not m.startswith('_')}
    except Exception as _e:
        note.append('%s: modulo non importabile per il controllo dei metodi (%s)'
                    % (_cartella.replace('_real', '').upper(), _e))
        continue
    _, _sc = scorpora(io.open(_pag, encoding='utf-8').read())
    _usati = sorted(set(re.findall(r'api\(\)\.(\w+)\(', senza_stringhe(_sc))))
    _assenti = [m for m in _usati if m not in _propri]
    if _assenti:
        problemi.append('%s: metodi chiamati dalla pagina che NON esistono '
                        'sulla sua Api: %s'
                        % (_cartella.replace('_real', '').upper(),
                           ', '.join(_assenti)))
    else:
        ok_count += 1

# Unita' CSS malformate: "13pxpx", "1remrem" e simili. Il browser scarta
# in silenzio la dichiarazione e l'elemento eredita la misura del genitore,
# quindi il difetto NON si vede come errore - si vede come un testo della
# dimensione sbagliata, che e' molto piu' difficile da ricondurre alla causa.
# Ne sono nate 172 in un colpo solo da uno script che alzava i corpi del
# testo e riscriveva l'unita' due volte.
import glob as _glob
_UNITA = re.compile(r':\s*[0-9.]+(px|rem|em|vh|vw|pt)(?=\1)', re.I)
for _p in (['genera_real/index.html', 'mockups/styles.css', 'index_template.html']
           + _glob.glob('_build_correggi/*.part')
           + _glob.glob('_build_correggi/pezzi/*.part')):
    _pp = os.path.join(QUI, _p) if not os.path.isabs(_p) else _p
    if not os.path.isfile(_pp):
        continue
    _t = io.open(_pp, encoding='utf-8').read()
    _bad = _UNITA.findall(_t)
    if _bad:
        problemi.append('unita CSS raddoppiata in %s: %d dichiarazioni '
                        '(es. "13pxpx") - il browser le scarta in silenzio'
                        % (_p, len(_bad)))
    else:
        ok_count += 1

print('===== AUDIT CODICE =====')
for n in note:
    print('  nota      %s' % n)
if not problemi:
    print('  nessun problema trovato (%d controlli superati)' % ok_count)
else:
    for x in problemi:
        print('  PROBLEMA  %s' % x)
    print('  %d controlli superati, %d problemi' % (ok_count, len(problemi)))
