# -*- coding: utf-8 -*-
"""Audit delle icone delle tre pagine.

Controlla, per ogni icona referenziata nell'HTML:
  - che il file esista;
  - che il viewBox sia coerente con la dimensione a cui viene usata
    (un'icona 100x100 messa in un riquadro 45x45 e' quasi sempre il segno di
     aver preso l'asset sbagliato: e' successo con l'icona "Correggi");
  - che non usi `currentColor` dentro un <img>, dove non eredita nulla e
    l'icona esce monocroma;
  - che il rapporto d'aspetto non venga deformato.

Si lancia da web_migration_spike/:  python audit_icone.py
"""
import io
import os
import re

QUI = os.path.dirname(os.path.abspath(__file__))
ICONE = os.path.join(QUI, 'mockups', 'assets', 'icons')
PAGINE = [('genera_real', 'index.html'), ('correggi_real', 'index.html'),
          ('dashboard_real', 'index.html'), ('playlist_real', 'index.html')]

esiti = []


def nota(ok, testo):
    esiti.append((ok, testo))


def leggi_icona(nome):
    p = os.path.join(ICONE, nome)
    if not os.path.isfile(p):
        return None
    s = io.open(p, encoding='utf-8', errors='replace').read()
    vb = re.search(r'viewBox="([^"]+)"', s)
    box = [float(x) for x in vb.group(1).split()] if vb else None
    return {
        'testo': s,
        'viewBox': box,
        'currentColor': 'currentColor' in s,
        'colori': sorted(set(re.findall(r'fill="(#[0-9A-Fa-f]{3,8})"', s))),
    }


for cartella, file_html in PAGINE:
    p = os.path.join(QUI, cartella, file_html)
    if not os.path.isfile(p):
        nota(False, '%s: pagina non trovata' % cartella)
        continue
    html = io.open(p, encoding='utf-8').read()

    # <img src="assets/icons/....svg" width=".." height="..">
    for m in re.finditer(r'<img[^>]+src="assets/icons/([^"]+)"[^>]*>', html):
        tag, nome = m.group(0), m.group(1)
        ic = leggi_icona(nome)
        if ic is None:
            nota(False, '%s: manca il file %s' % (cartella, nome))
            continue
        w = re.search(r'width="(\d+)"', tag)
        h = re.search(r'height="(\d+)"', tag)
        if ic['currentColor']:
            nota(False, '%s: %s usa currentColor dentro <img> (esce monocroma)'
                 % (cartella, nome))
        else:
            nota(True, '%s: %s ha colori propri' % (cartella, nome))
        if w and h and ic['viewBox']:
            vw, vh = ic['viewBox'][2], ic['viewBox'][3]
            usata_w, usata_h = int(w.group(1)), int(h.group(1))
            # rapporto d'aspetto
            r_file = vw / vh if vh else 0
            r_uso = usata_w / usata_h if usata_h else 0
            if abs(r_file - r_uso) > 0.12:
                nota(False, '%s: %s deformata (file %gx%g, usata %dx%d)'
                     % (cartella, nome, vw, vh, usata_w, usata_h))
            else:
                nota(True, '%s: %s proporzioni ok (%gx%g -> %dx%d)'
                     % (cartella, nome, vw, vh, usata_w, usata_h))

    # icone usate come mask-image (pattern di sfondo): li' currentColor va bene
    for nome in set(re.findall(r"assets/icons/(\w+\.svg)\)", html)):
        ic = leggi_icona(nome)
        if ic is None:
            nota(False, '%s: manca il file %s (usato come maschera)' % (cartella, nome))
        else:
            nota(True, '%s: %s presente (maschera)' % (cartella, nome))

# icone presenti ma non usate da nessuna pagina
usate = set()
for cartella, file_html in PAGINE:
    p = os.path.join(QUI, cartella, file_html)
    if os.path.isfile(p):
        html = io.open(p, encoding='utf-8').read()
        usate |= set(re.findall(r'assets/icons/([\w.]+\.svg)', html))
    # il pattern di sfondo costruisce il nome in JS: assets/icons/${icon}.svg
    for lista in re.findall(r"const ICONS = \[([^\]]+)\]", html):
        usate |= set(n.strip().strip("'\"") + '.svg' for n in lista.split(','))
    if "isBlock ? 'block'" in html:
        usate.add('block.svg')
    # e alcune icone sono INLINE nell'HTML, non via src: le riconosco dal
    # loro viewBox, che e' unico
    for nome in os.listdir(ICONE):
        if not nome.endswith('.svg'):
            continue
        ic = leggi_icona(nome)
        if ic and ic['viewBox']:
            vb = ' '.join(('%g' % v) for v in ic['viewBox'])
            if 'viewBox="%s"' % vb in html:
                usate.add(nome)

tutte = set(f for f in os.listdir(ICONE) if f.endswith('.svg'))
orfane = sorted(tutte - usate)

print('===== AUDIT ICONE =====')
visti = set()
for ok, testo in esiti:
    if testo in visti:
        continue
    visti.add(testo)
    print(('  ok    ' if ok else '  PROBLEMA ') + testo)
print('  %d/%d controlli superati' % (sum(1 for o, _ in esiti if o), len(esiti)))
if orfane:
    print('\n  icone presenti ma non referenziate da nessuna pagina:')
    for f in orfane:
        print('    %s' % f)
