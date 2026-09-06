# -*- coding: utf-8 -*-
"""Esegue TUTTI i controlli del port in un colpo solo.

    python verifica.py           controlli statici (veloci, ~2 secondi)
    python verifica.py --app     anche quelli che aprono le finestre (lenti)

Cosa controlla, e perche' ognuno esiste:

  audit_codice.py   riferimenti a elementi inesistenti, funzioni chiamate ma
                    non definite, codice morto, id duplicati, parentesi.
                    Esiste perche' due volte una pagina e' rimasta a meta'
                    per un getElementById su un id sparito, senza che nulla
                    lo segnalasse.
  audit_icone.py    icone mancanti, prese dall'asset sbagliato, deformate o
                    che usano currentColor dentro un <img> (dove non eredita
                    nulla e l'icona esce monocroma).
  audit_bundle.py   che lo .spec di PyInstaller dichiari tutti i moduli
                    importati dinamicamente: se ne manca uno l'exe si
                    compila senza avvisi e poi muore all'avvio. Successo
                    due volte (boxvr_patch, installa).
  test_port.py      test FUNZIONALI: esercita le API come farebbe la
                    pagina, casi limite compresi, e verifica cio' che NON
                    deve succedere (scritture nella libreria del gioco,
                    file cancellati, elenchi che schiantano).
  audit_runtime.py  che lo script di ogni pagina SIA DAVVERO PARTITO. Tutti
                    gli altri controlli leggono il file; questo apre la
                    pagina e chiede se le funzioni esistono. Esiste perche'
                    la pagina Genera e' rimasta a lungo completamente
                    inerte - quattro copie di uno stesso `let`, cioe' un
                    SyntaxError che butta via l'INTERO blocco <script> - e
                    nessun controllo statico se n'era accorto: l'ha trovato
                    il test su macchina pulita. Solo con --app.
  test_webview2_assente.py  il percorso "WebView2 non installato", provato
                    facendo mentire il rilevamento invece di disinstallare
                    il runtime dalla macchina (che e' un componente di
                    sistema, lo usano altre app, e Edge Update lo
                    rimetterebbe da solo rendendo la prova ambigua).
  test_pulizia.py       che la pulizia delle cartelle temporanee cancelli le
                        VECCHIE nostre e lasci stare le recenti e quelle di
                        altri programmi - provata con cartelle finte
  audit_ux.py           bersagli 24x24 (WCAG 2.2 SC 2.5.8), indicatore di
                        fuoco (SC 2.4.7), contrasto non testuale (SC 1.4.11)
                        ed etichette dei campi - misurati sugli elementi veri
  audit_leggibilita.py  contrasto WCAG e dimensione REALE dei testi (px CSS
                    per la scala di fitPage per la densita' dello schermo).
                    Nato dalla segnalazione "i testi piccoli non si leggono":
                    la misura ha mostrato 23 testi su 64 sotto la soglia,
                    il log a 2.49:1 contro i 4.5:1 richiesti. Solo con --app.
  test_installazione.py  l'installazione in BoxVR percorsa TUTTA, ma su una
                    libreria finta in una cartella temporanea. Passa dalla
                    Api della Dashboard, cioe' la strada che percorre
                    l'interfaccia - i test precedenti chiamavano le Api
                    dirette dei moduli, e infatti non si erano accorti che
                    "Installa in BoxVR" era morta.
  audit_parita.py   parita' con la GUI Tkinter: per ogni comando della
                    vecchia finestra cerca il corrispondente nel port. Serve
                    a rispondere alla domanda "abbiamo perso pezzi per
                    strada?" con un elenco invece che a memoria.
  audit_coerenza.py  coerenza INTERNA: token dichiarati e mai usati (o il
                    contrario), whitelist che chiedono blocchi spariti,
                    pagine composte piu' vecchie dei loro pezzi, commenti
                    che affermano cose non piu' vere.
  audit_consegna.py  (a parte, serve l'exe) verifica sull'ESEGUIBILE che
                    quanto chiesto sia arrivato fin li': fra sorgente e exe
                    ci sono tre passaggi che hanno gia' perso qualcosa.
  audit_figma.py    misure e colori contro i valori reali del wireframe.
                    Solo con --app: apre ogni pagina e misura sul vero.

Non copre: testi, tipografia, spaziature interne, tema scuro.
"""
import os
import subprocess
import sys

QUI = os.path.dirname(os.path.abspath(__file__))
CON_APP = '--app' in sys.argv


def esegui(script, cwd=None, args=()):
    r = subprocess.run([sys.executable, script] + list(args),
                       cwd=cwd or QUI, capture_output=True, text=True)
    print(r.stdout.rstrip())
    if r.returncode != 0 and r.stderr:
        print(r.stderr.rstrip())
    return r.returncode


uscita = 0
uscita |= esegui(os.path.join(QUI, 'audit_codice.py'))
print()
uscita |= esegui(os.path.join(QUI, 'audit_icone.py'))
print()
uscita |= esegui(os.path.join(QUI, 'audit_bundle.py'))
print()
uscita |= esegui(os.path.join(QUI, 'test_port.py'))
print()
uscita |= esegui(os.path.join(QUI, 'test_webview2_assente.py'))
print()
uscita |= esegui(os.path.join(QUI, 'test_installazione.py'))
print()
uscita |= esegui(os.path.join(QUI, 'audit_coerenza.py'))
print()
uscita |= esegui(os.path.join(QUI, 'audit_parita.py'))
print()
uscita |= esegui(os.path.join(QUI, 'test_pulizia.py'))

# audit_runtime NON sta piu' dietro --app.
#
# Motivo, imparato a spese proprie: un errore di sintassi in una riga ha
# ucciso l'INTERO script di due pagine - niente scala del canvas, niente
# elenco brani, niente traduzioni - e la suite completa era passata verde,
# perche' tutti gli altri controlli leggono i sorgenti e non aprono la
# pagina. Il controllo piu' importante di tutti e' il piu' banale: la
# pagina, aperta davvero, funziona? Costa una ventina di secondi ed e' il
# solo che distingue "il file c'e'" da "il programma va".
print()
uscita |= esegui(os.path.join(QUI, 'audit_runtime.py'))

if CON_APP:

    for pagina in ('correggi', 'genera', 'dashboard'):
        print()
        uscita |= esegui(os.path.join(QUI, 'audit_leggibilita.py'), args=(pagina,))
    # bersagli, fuoco da tastiera, contrasto non testuale, etichette:
    # tutte e quattro le pagine, perche' i difetti trovati stavano sparsi
    # (i bersagli in Genera, gli span non raggiungibili in Playlist)
    for pagina in ('correggi', 'genera', 'dashboard', 'playlist'):
        print()
        uscita |= esegui(os.path.join(QUI, 'audit_ux.py'), args=(pagina,))
    for pagina in ('correggi', 'genera', 'dashboard', 'playlist'):
        print()
        uscita |= esegui(os.path.join(QUI, 'audit_traduzione.py'), args=(pagina,))
    for pagina in ('correggi', 'dashboard'):
        print()
        uscita |= esegui(os.path.join(QUI, 'audit_tema_scuro.py'), args=(pagina,))
    for pagina in ('correggi', 'genera'):
        print()
        uscita |= esegui(os.path.join(QUI, 'test_interazioni.py'), args=(pagina,))

if CON_APP:
    for pagina in ('genera', 'correggi', 'dashboard'):
        print()
        uscita |= esegui(os.path.join(QUI, 'audit_figma.py'),
                         cwd=os.path.join(QUI, pagina + '_real'), args=(pagina,))
else:
    print('\n(audit_figma non eseguito: serve --app, apre le finestre ed e\' lento)')

sys.exit(uscita)
