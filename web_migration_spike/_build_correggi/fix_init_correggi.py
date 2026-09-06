import io
import os as _os
# I pezzi (.part) stanno accanto a questo script, non in una cartella
# temporanea: cosi' la catena funziona anche in sessioni diverse.
_QUI = _os.path.dirname(_os.path.abspath(__file__))


p = _QUI + r"\correggi_specifico.js.part"
s = io.open(p, encoding='utf-8').read()

old = """  // --- avvio ---
  renderBgPattern();
  window.addEventListener('resize', fitPage);
  fitPage();
  initTheme();
  loadAppInfo();
  loadList();
"""
if s.count(old) != 1:
    print('init: gia applicato')
    old = None
new = """  // --- avvio ---
  // Le chiamate all'API vanno fatte solo quando il ponte pywebview esiste:
  // partendo subito fallivano tutte in silenzio (lista ferma su
  // "caricamento...", versione e pillola patch mai popolate).
  renderBgPattern();
  window.addEventListener('resize', fitPage);
  fitPage();

  function avvio() { loadList(); loadAppInfo(); initTheme(); }
  if (window.pywebview) avvio();
  else window.addEventListener('pywebviewready', avvio);
"""
s = s.replace(old, new) if old else s
io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('init corretto')

# Il proxy condiviso cerca prima i metodi col prefisso "genera_": serve a
# Genera quando gira dentro la dashboard, che delega i suoi metodi con quel
# prefisso. I metodi di Correggi la dashboard li espone SENZA prefisso
# (dashboard_real/app.py: list_songs -> self._correggi.list_songs), quindi
# qui il proxy va usato liscio.
q = _os.path.join(_QUI, "pezzi") + r"\js_condiviso.part"
t = io.open(q, encoding='utf-8').read()
# Tolgo SOLO le due righe del prefisso, qualunque sia il resto del proxy:
# legarsi al testo completo lo rendeva fragile - quando ho reso il proxy piu'
# esplicito sui metodi mancanti, questa sostituzione ha smesso di combaciare
# in silenzio e Correggi si e' ritrovato il prefisso sbagliato.
PREFISSO = ("      const prefixed = real['genera_' + prop];\n"
            "      const fn = typeof prefixed === 'function' ? prefixed : real[prop];\n")
if PREFISSO not in t:
    print('proxy: gia senza prefisso')
else:
    t = t.replace(PREFISSO, "      const fn = real[prop];\n")
    io.open(q, 'w', encoding='utf-8', newline='').write(t)
    print('proxy: prefisso "genera_" rimosso per Correggi')
