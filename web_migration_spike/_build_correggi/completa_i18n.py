# -*- coding: utf-8 -*-
"""Completa l'i18n: observer di ritraduzione + avvio della lingua salvata."""
import io
import os as _os
# I pezzi (.part) stanno accanto a questo script, non in una cartella
# temporanea: cosi' la catena funziona anche in sessioni diverse.
_QUI = _os.path.dirname(_os.path.abspath(__file__))


SP = _QUI

OBSERVER = """
  // Molti testi nascono da render JS (righe brano, pillole, stati, log):
  // invece di ricordarsi di ritradurre in ognuno di quei punti - dove prima o
  // poi se ne dimentica uno - la pagina si ritraduce da sola quando il DOM
  // cambia. Il lavoro e' nullo finche' la lingua e' italiano.
  let _pendente = false;
  new MutationObserver(() => {
    if (_lingua === 'it' || _pendente) return;
    _pendente = true;
    requestAnimationFrame(() => { _pendente = false; traduciPagina(); });
  }).observe(document.documentElement, {childList: true, subtree: true, characterData: true});
"""

ANCORA = "  window.stringheNonTradotte = stringheNonTradotte;\n"

FILE = [
    (r"F:\BoxVR Songs Tool\web_migration_spike\genera_real\index.html", 'genera'),
    (SP + r"\pezzi\js_condiviso.part", 'correggi (pezzo)'),
]

# La guardia "se c'e' gia', non aggiungerlo" NON basta: se per qualunque
# motivo le copie sono gia' piu' di una, la guardia le vede e non tocca
# niente, cioe' congela il guasto. E' successo davvero - la pagina Genera e'
# arrivata a QUATTRO copie e il test su macchina pulita l'ha trovata
# completamente inerte: quattro `let _pendente` nello stesso scope sono un
# SyntaxError di parsing, e un SyntaxError non uccide una riga, uccide
# l'intero blocco <script>. Nessun messaggio a schermo, la pagina si disegna
# e basta non funziona.
# Quindi qui non ci si limita a saltare: si NORMALIZZA a esattamente una
# copia, che e' l'unico stato corretto.
import re as _re
_BLOCCO = _re.compile(
    r"\n  // Molti testi nascono da render JS.*?"
    r"\}\)\.observe\(document\.documentElement, \{childList: true, subtree: true, characterData: true\}\);\n",
    _re.S)

for p, nome in FILE:
    s = io.open(p, encoding='utf-8').read()
    copie = len(_BLOCCO.findall(s))
    if copie > 1:
        s = _BLOCCO.sub('', s)
        assert s.count(ANCORA) == 1, (nome, s.count(ANCORA))
        s = s.replace(ANCORA, ANCORA + OBSERVER, 1)
        print('observer: %d copie in %s -> ridotte a 1' % (copie, nome))
    elif copie == 1:
        print('observer gia presente:', nome)
    else:
        assert s.count(ANCORA) == 1, (nome, s.count(ANCORA))
        s = s.replace(ANCORA, ANCORA + OBSERVER)
        print('observer aggiunto a', nome)
    # avvio della lingua salvata, accanto a initTheme
    if 'initLang()' not in s.replace('async function initLang', ''):
        s = s.replace("function avvio() { loadList(); loadAppInfo(); initTheme(); }",
                      "function avvio() { loadList(); loadAppInfo(); initTheme(); initLang(); }")
        s = s.replace("    loadList();\n    loadAppInfo();\n    initTheme();\n  } else {",
                      "    loadList();\n    loadAppInfo();\n    initTheme();\n    initLang();\n  } else {")
        s = s.replace("window.addEventListener('pywebviewready', () => { loadList(); loadAppInfo(); initTheme(); });",
                      "window.addEventListener('pywebviewready', () => { loadList(); loadAppInfo(); initTheme(); initLang(); });")
        print('  initLang collegato')
    io.open(p, 'w', encoding='utf-8', newline='').write(s)
