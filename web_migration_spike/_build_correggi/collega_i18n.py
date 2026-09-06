# -*- coding: utf-8 -*-
"""Collega il dizionario i18n alle tre pagine e rende reale setLang."""
import io
import os as _os
# I pezzi (.part) stanno accanto a questo script, non in una cartella
# temporanea: cosi' la catena funziona anche in sessioni diverse.
_QUI = _os.path.dirname(_os.path.abspath(__file__))


SP = _QUI
def _blocco_trad(testo):
    """Il letterale `const TRAD = { ... };` dentro `testo`, contando le
    graffe: una regex non basta, il dizionario contiene graffe nelle
    stringhe."""
    i = testo.find('const TRAD = {')
    if i < 0:
        return None
    j = testo.index('{', i)
    livello = 0
    for k in range(j, len(testo)):
        if testo[k] == '{':
            livello += 1
        elif testo[k] == '}':
            livello -= 1
            if livello == 0:
                fine = testo.find(';', k)
                return testo[i:fine + 1]
    return None


def sincronizza_dal_sorgente():
    """Riporta nel pezzo condiviso il dizionario di genera_real.

    genera_real e' la fonte: e' li' che si scrivono le voci nuove, ed e' da
    li' che vengono estratti tutti gli altri blocchi condivisi. Prima questo
    passo non esisteva e le due copie si allontanavano a ogni aggiunta.
    """
    sorgente = _os.path.join(_os.path.dirname(_QUI), 'genera_real', 'index.html')
    if not _os.path.isfile(sorgente):
        return
    nuovo = _blocco_trad(io.open(sorgente, encoding='utf-8').read())
    if not nuovo:
        return
    pezzo = _os.path.join(_QUI, 'i18n.js.part')
    testo = io.open(pezzo, encoding='utf-8').read()
    vecchio = _blocco_trad(testo)
    if not vecchio:
        return
    if vecchio.strip() == nuovo.strip():
        print('  dizionario gia allineato (%d voci)' % nuovo.count(':'))
        return
    io.open(pezzo, 'w', encoding='utf-8', newline='').write(
        testo.replace(vecchio, nuovo, 1))
    print('  dizionario sincronizzato da genera_real: %d voci (erano %d)'
          % (nuovo.count(':'), vecchio.count(':')))


sincronizza_dal_sorgente()
DIZ = io.open(SP + r"\i18n.js.part", encoding='utf-8').read()

SETLANG_NUOVO = """  // Cambio lingua VERO (prima cambiava solo la pillola attiva). La scelta e'
  // ricordata in settings.json come tema e cartella di gioco.
  async function setLang(code) {
    document.querySelectorAll('.lang-pill').forEach(p =>
      p.classList.toggle('active', p.textContent.trim().toLowerCase() === code));
    _lingua = code;
    if (code === 'it') ripristinaItaliano(); else traduciPagina();
    try { await api().set_lang(code); } catch (e) { /* pagina aperta fuori da pywebview */ }
  }
  window.setLang = setLang;
  window.traduciPagina = traduciPagina;

  async function initLang() {
    let code = 'it';
    try { code = await api().get_lang(); } catch (e) { /* default italiano */ }
    setLang(code);
  }
"""

SETLANG_VECCHIO = """  function setLang(code) {
    document.querySelectorAll('.lang-pill').forEach(p =>
      p.classList.toggle('active', p.textContent.trim().toLowerCase() === code));
  }
  window.setLang = setLang;
"""


def applica(percorso, e_un_pezzo=False):
    s = io.open(percorso, encoding='utf-8').read()
    if 'const TRAD = {' in s:
        print('  dizionario gia presente:', percorso)
        return
    if SETLANG_VECCHIO in s:
        s = s.replace(SETLANG_VECCHIO, SETLANG_NUOVO)
        print('  setLang sostituito')
    if e_un_pezzo:
        s = DIZ + s
    else:
        i = s.index('<script>') + len('<script>')
        s = s[:i] + '\n' + DIZ + s[i:]
    io.open(percorso, 'w', encoding='utf-8', newline='').write(s)
    print('  dizionario inserito in', percorso)


print('genera_real:')
applica(r"F:\BoxVR Songs Tool\web_migration_spike\genera_real\index.html")
print('pezzo condiviso (per correggi_real):')
applica(SP + r"\pezzi\js_condiviso.part", e_un_pezzo=True)
