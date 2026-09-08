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

"""La documentazione dice il vero?

Un documento si controlla come si controlla il codice: mettendo alla prova
le sue affermazioni, non rileggendolo. Qui si verificano quelle
VERIFICABILI - i file che nomina, i comandi che suggerisce, i numeri che
cita, la licenza che dichiara - contro il progetto com'e' adesso.

Il resto (se una spiegazione sia chiara, se il tono sia giusto) non lo puo'
dire un programma, e non finge di poterlo dire.

    python audit_documentazione.py
"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

R = os.path.dirname(os.path.abspath(__file__))
rilievi = []


def rileva(dove, cosa):
    rilievi.append((dove, cosa))


def leggi(rel):
    p = os.path.join(R, rel)
    if not os.path.isfile(p):
        return None
    return io.open(p, encoding='utf-8', errors='replace').read()


DOCS = ['README.md', 'README.it.md', 'THIRD_PARTY_NOTICES.md',
        'docs/boxvr-and-fix.md', 'docs/generate.md', 'docs/sidecar.md',
        'docs/patch.md', 'docs/playlist-manager.md', 'docs/history.md',
        'docs/ai.md', 'docs/contributing.md',
        'docs/it/boxvr-e-correggi.md', 'docs/it/genera.md',
        'docs/it/sidecar.md', 'docs/it/patch.md',
        'docs/it/playlist-manager.md', 'docs/it/storia.md',
        'docs/it/ia.md', 'docs/it/contribuire.md',
        'docs/it/licenze-terze-parti.md']


def controlla_esistenza():
    for d in DOCS:
        if leggi(d) is None:
            rileva(d, 'documento dichiarato ma assente')


def controlla_collegamenti():
    for d in DOCS:
        testo = leggi(d)
        if testo is None:
            continue
        base = os.path.dirname(os.path.join(R, d))
        for m in re.finditer(r'\]\(([^)#\s]+?)(#[^)]*)?\)', testo):
            dest = m.group(1)
            if dest.startswith(('http', 'mailto')) or dest == '../../releases':
                continue
            if not os.path.exists(os.path.normpath(os.path.join(base, dest))):
                rileva(d, 'collegamento rotto: %s' % dest)


def controlla_file_nominati():
    """I file citati fra backtick devono esistere."""
    IGNORA = ('...', 'settings.json', '<hash>.trackdata.txt', '<hash>.wav',
              '<hash>.wdef.txt', 'Assembly-CSharp.dll', 'musicActionList',
              'resources.assets', 'trackdata', 'madmom_worker.exe',
              # `tuning.json` NON esiste apposta: lo crea chi vuole regolare
              # qualcosa, copiandolo da tuning.esempio.json. Se esistesse
              # gia' nel repository, chiunque cloni si porterebbe dietro le
              # regolazioni di un altro senza saperlo.
              'tuning.json')
    for d in DOCS:
        testo = leggi(d)
        if testo is None:
            continue
        for m in re.finditer(r'`([\w /\\.-]+\.(?:py|md|spec|json|txt|css|html))`',
                             testo):
            nome = m.group(1).strip()
            # un nome che comincia col punto e' un'ESTENSIONE citata
            # (`.trackdata.txt`), non un file che deve esistere
            if nome in IGNORA or nome.startswith(('<', '.')):
                continue
            cand = [nome,
                    os.path.join('web_migration_spike', nome),
                    os.path.join('sidecar sandbox', nome),
                    os.path.join('web_migration_spike', '_build_correggi', nome)]
            if not any(os.path.exists(os.path.join(R, c)) for c in cand):
                rileva(d, 'file citato e inesistente: %s' % nome)


def controlla_licenza():
    lic = leggi('LICENSE') or ''
    if 'Version 3, 29 June 2007' not in lic:
        rileva('LICENSE', 'non e\' il testo della GPL-3.0')
    for d in ('README.md', 'README.it.md', 'THIRD_PARTY_NOTICES.md',
              'docs/ai.md', 'docs/it/ia.md'):
        t = leggi(d) or ''
        if re.search(r'\bMIT\b', t) and 'GPL' not in t:
            rileva(d, 'parla di MIT senza citare la GPL')
        if 'sotto licenza **MIT**' in t or 'under the **MIT** licence' in t:
            rileva(d, 'dichiara ancora la licenza MIT del progetto')


def controlla_comandi():
    """I comandi suggeriti devono puntare a file che esistono."""
    for d in DOCS:
        testo = leggi(d)
        if testo is None:
            continue
        for m in re.finditer(r'python\s+"?([\w /\\.-]+\.py)"?', testo):
            rel = m.group(1).replace('/', os.sep)
            if not os.path.exists(os.path.join(R, rel)):
                rileva(d, 'comando su file inesistente: python %s' % m.group(1))


def controlla_numeri():
    """I numeri citati nella documentazione contro il codice."""
    coppie = [
        ('docs/sidecar.md', '45 seconds', 'sidecar sandbox/engine.py',
         'EXTEND_MIN_COVERAGE_S = 45.0'),
        ('docs/it/sidecar.md', '45 secondi', 'sidecar sandbox/engine.py',
         'EXTEND_MIN_COVERAGE_S = 45.0'),
        ('docs/sidecar.md', '4 or more punches', 'sidecar sandbox/engine.py',
         'BLOCCO_MIN_COLPI = 4'),
        ('docs/patch.md', '42 bytes', 'patch boxvr/patch_boxvr.py',
         'LENGTH = 42'),
        ('docs/it/patch.md', '42 byte', 'patch boxvr/patch_boxvr.py',
         'LENGTH = 42'),
        ('docs/patch.md', '0xFE47', 'patch boxvr/patch_boxvr.py',
         'OFFSET = 0xFE47'),
    ]
    # I valori di fabbrica della tabella di tuning contano come sorgente:
    # da quando le costanti li leggono da li', nel codice non c'e' piu' il
    # numero scritto a mano (EXTEND_MIN_COVERAGE_S = 45.0 e' diventato
    # _reg('estendi_secondi_minimi', 45.0)), e cercare la stringa esatta
    # dava un falso allarme su una documentazione corretta.
    da_tuning = ''
    try:
        import tuning
        da_tuning = chr(10).join('%s = %s' % (k, v[0]) for k, v in tuning.VALORI.items())
    except Exception:                      # noqa: BLE001
        pass

    for doc, frase, sorgente, atteso in coppie:
        t = leggi(doc) or ''
        s = (leggi(sorgente) or '') + chr(10) + da_tuning
        if frase.lower() not in t.lower():
            continue                      # il documento non lo afferma piu'
        # il numero puo' stare nella costante o fra i valori di fabbrica
        numero = atteso.split('=')[-1].strip()
        if atteso not in s and ('= %s' % numero) not in s:
            rileva(doc, 'afferma "%s" ma ne %s ne la tabella di tuning '
                        'contengono "%s"' % (frase, sorgente, atteso))


def controlla_presets():
    """I bersagli di densita' citati devono essere quelli del codice."""
    choreo = leggi('boxvr_choreo.py') or ''
    veri = re.findall(r"'target_epm':\s*(\d+)", choreo)
    for doc in ('docs/generate.md', 'docs/it/genera.md'):
        t = leggi(doc) or ''
        for n in veri:
            if n not in t:
                rileva(doc, 'preset: target_epm %s non compare nel documento' % n)


def controlla_versione():
    ver = leggi('version.py') or ''
    m = re.search(r'VERSION_WEB = "([\d.]+)"', ver)
    if not m:
        rileva('version.py', 'VERSION_WEB non trovata')
        return
    # Due numerazioni dall'08/09: VERSION_WEB e' quella pubblica e si muove
    # solo quando si pubblica davvero; BUILD e' il contatore interno, e
    # finisce nel nome del file finche' non e' zero. Il nome atteso dipende
    # da quale delle due situazioni siamo - vedi rilascia.py.
    b = re.search(r'^BUILD = (\d+)', ver, re.M)
    build = int(b.group(1)) if b else 0
    if build:
        atteso = 'BoxVR SrvToolkit %s build %d.exe' % (m.group(1), build)
        come = 'build interna %d' % build
    else:
        atteso = 'BoxVR SrvToolkit %s Public Beta.exe' % m.group(1)
        come = 'pubblica'
    d = os.path.join(R, 'dist_web')
    if os.path.isdir(d):
        presenti = [f for f in os.listdir(d) if f.endswith('.exe')]
        if presenti and atteso not in presenti:
            rileva('dist_web', 'atteso "%s" (%s) ma in dist_web c\'e\' %s'
                              % (atteso, come, ', '.join(presenti)))


def controlla_gitignore_vivo():
    """Il .gitignore fa davvero il suo mestiere? Lo si chiede a git."""
    import shutil
    git = os.path.join(R, '.git')
    temp = not os.path.isdir(git)
    if temp:
        subprocess.run(['git', 'init', '-q'], cwd=R, check=True)
    try:
        out = subprocess.run(['git', 'add', '-A', '--dry-run'], cwd=R,
                             capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
        righe = [r.strip()[5:-1] for r in out.stdout.split('\n')
                 if r.strip().startswith("add '")]
    finally:
        if temp:
            shutil.rmtree(git, ignore_errors=True)
    for d in DOCS:
        testo = leggi(d)
        if testo is None or 'NOT in this repository' not in testo and \
                'NON è in questo repository' not in testo:
            continue
        for escluso in ('archivio libreria gioco', 'training_sequences.json'):
            if any(escluso in r for r in righe):
                rileva(d, 'dichiara escluso "%s" ma git lo includerebbe' % escluso)


def main():
    controlla_esistenza()
    controlla_collegamenti()
    controlla_file_nominati()
    controlla_licenza()
    controlla_comandi()
    controlla_numeri()
    controlla_presets()
    controlla_versione()
    controlla_gitignore_vivo()

    print('documenti controllati:', len(DOCS))
    if rilievi:
        print('rilievi (%d):' % len(rilievi))
        for dove, cosa in rilievi:
            print('   %-34s %s' % (dove, cosa))
    else:
        print('nessun rilievo: file, collegamenti, comandi, numeri, preset,')
        print('licenza e versione combaciano con il progetto.')
    print()
    print('ESITO:', 'documentazione coerente' if not rilievi
          else 'DA CORREGGERE')
    return 1 if rilievi else 0


if __name__ == '__main__':
    sys.exit(main())
