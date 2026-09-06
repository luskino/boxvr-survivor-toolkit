# Ricompone dashboard_real/index.html sul canvas 1920x1080, tenendo INTATTA
# la logica gia' collegata (patch, cartella di gioco, navigazione, tema) e
# cambiando solo struttura e stile. Il pattern di sfondo e' lo stesso
# deterministico di Genera/Correggi, non piu' icone sparse a caso.
import io, re
import os as _os
# I pezzi (.part) stanno accanto a questo script, non in una cartella
# temporanea: cosi' la catena funziona anche in sessioni diverse.
_QUI = _os.path.dirname(_os.path.abspath(__file__))


ORIG = _QUI + r"\dashboard_index_ORIGINALE.html"
SP = _QUI
GEN = r"F:\BoxVR Songs Tool\web_migration_spike\genera_real\index.html"
OUT = r"F:\BoxVR Songs Tool\web_migration_spike\dashboard_real\index.html"

orig = io.open(ORIG, encoding='utf-8').read()
css = io.open(SP + r"\dashboard_nuovo.css.part", encoding='utf-8').read()
corpo = io.open(SP + r"\dashboard_corpo.html.part", encoding='utf-8').read()
gen = io.open(GEN, encoding='utf-8').read()


def _blocco(sorgente, inizio, fine):
    """Il pezzo di sorgente fra due marcatori, estremo finale escluso."""
    a = sorgente.index(inizio)
    b = sorgente.index(fine, a)
    return sorgente[a:b]


# Funzioni del tema, estratte da Genera come la geometria: qui il tema
# SEGUE IL SISTEMA e il cambio vale per la sola sessione. La copia
# congelata della Dashboard leggeva e scriveva ancora l'impostazione
# salvata - due copie della stessa logica divergono sempre.
_tema = _blocco(gen, '  function applyTheme(theme) {',
                '  window.toggleTheme = toggleTheme;')

# --- JS: prendo dal file originale tutto quello che sta dopo la creazione
#     delle icone sparse (che sostituisco col pattern vero) ---
i = orig.index("  const PATCH_CHECK_ICON")
j = orig.rindex("</script>")
js_logica = orig[i:j]

# la barra di stato ora e' .dash-devbar e ci aggiungo versione, tema e
# playlist manager, che nel wireframe non esistono
js_logica = js_logica.replace(
    "    bar.appendChild(label);\n    bar.appendChild(btn);",
    """    bar.appendChild(label);
    bar.appendChild(btn);
    const pill = document.createElement('span');
    pill.id = 'patch-pill-wrap';
    bar.appendChild(pill);
    // Il tema ora ha il suo interruttore in alto a destra (come nel
    // wireframe): il pulsante testuale qui sotto era un doppione, e stava
    // in una barra che nel wireframe non esiste.
    const pl = document.createElement('a');
    pl.href = '#';
    pl.textContent = 'Gestione playlist installate →';
    pl.onclick = (e) => { e.preventDefault(); location.href = 'playlist.html'; };
    bar.appendChild(pl);
    renderPatchPill(_ultimoStato || {state: 'unknown'});""")

# applyStatus ricorda l'ultimo stato (serve alla pillola ricreata sopra) e
# usa la classe .bloccato del tile invece delle vecchie classi
js_logica = js_logica.replace(
    "  function applyStatus(s) {",
    "  let _ultimoStato = null;\n  function applyStatus(s) {\n    _ultimoStato = s;")
js_logica = js_logica.replace("""    if (s.state === 'patched') {
      cta.classList.add('disabled');
      cta.textContent = 'Vai al tool 🔒';
      note.classList.add('visible');
    } else {
      cta.classList.remove('disabled');
      cta.textContent = 'Vai al tool →';
      note.classList.remove('visible');
    }""", """    // variante "Rilevata Patch" del componente Tile mode: CTA grigia col
    // lucchetto e l'avviso rosso sotto - e' il tile intero a cambiare stato,
    // non solo il bottone.
    const tile = document.getElementById('tile-correggi');
    tile.classList.toggle('bloccato', s.state === 'patched');
    cta.textContent = s.state === 'patched' ? 'Vai al tool 🔒' : 'Vai al tool ›';

    // E lo stesso all'incontrario per Genera. Le coreografie che scrive, il
    // gioco le legge SOLO da patchato: senza patch si puo' fare tutto il
    // giro - analisi, anteprima, generazione, file scritti - e scoprire che
    // in VR non e' cambiato niente, con l'auricolare gia' in testa. Meglio
    // dirlo qui, dove la cosa che manca si puo' ancora installare.
    const tileG = document.getElementById('tile-genera');
    const ctaG = document.getElementById('genera-cta');
    const notaG = document.getElementById('genera-patch-note');
    const senzaPatch = (s.state !== 'patched');
    tileG.classList.toggle('bloccato', senzaPatch);
    ctaG.textContent = senzaPatch ? 'Vai al tool 🔒' : 'Vai al tool ›';
    if (notaG) {
      // due impedimenti diversi, due richieste diverse: installare la patch
      // e' un'altra cosa dal dire dov'e' il gioco
      notaG.innerHTML = !senzaPatch ? ''
        : (s.state === 'original')
        ? '⚠ <span>Patch non installata.</span> <a href="#" id="install-patch-link">Installa</a>'
        : '⚠ <span>Serve la cartella di BoxVR.</span> <a href="#" id="pick-dir-link">Scegli</a>';
      const li = document.getElementById('install-patch-link');
      if (li) li.onclick = (e) => { e.preventDefault(); chiediLaPatch(); };
      const lp = document.getElementById('pick-dir-link');
      if (lp) lp.onclick = (e) => { e.preventDefault(); chooseGameDir(); };
    }""")

# renderPatchPill scriveva in un contenitore che ora vive dentro la devbar
js_logica = js_logica.replace(
    "    const wrap = document.getElementById('patch-pill-wrap');\n    if (s.state",
    "    const wrap = document.getElementById('patch-pill-wrap');\n    if (!wrap) return;\n    if (s.state")

# la versione va nella devbar, non piu' accanto al titolo della modale
js_logica = js_logica.replace(
    "    if (s.version) document.getElementById('app-version').textContent = 'Ver ' + s.version;",
    "    if (s.version) _versione = 'Ver ' + s.version;")
js_logica = js_logica.replace(
    "  let _ultimoStato = null;", "  let _ultimoStato = null, _versione = '';")
js_logica = js_logica.replace(
    "    label.innerHTML = s.game_dir",
    "    label.innerHTML = (_versione ? _versione + ' — ' : '') + (s.game_dir ? '' : '') + (s.game_dir")
js_logica = js_logica.replace(
    "      : 'Nessuna cartella di gioco impostata';",
    "      : 'Nessuna cartella di gioco impostata');")

# La Dashboard non passa dall'estrattore per nome: si porta via un blocco
# solo del sorgente di Genera. attivaConTastiera sta fuori da quel blocco,
# quindi le pillole IT/EN qui restavano con un onkeydown che chiamava una
# funzione inesistente - lo ha visto audit_codice, non un occhio umano.
# via la versione congelata del tema, dentro quella di Genera
_i_tema = js_logica.find('  function applyTheme(theme) {')
if _i_tema >= 0:
    _j_tema = js_logica.index('  window.toggleTheme = toggleTheme;', _i_tema)
    js_logica = (js_logica[:_i_tema] + _tema
                 + js_logica[_j_tema:])

js_logica += """
  // Invio e Spazio su cio' che e' interattivo per role+tabindex e non per
  // tag: un <button> lo fa da solo, uno <span role="button"> no.
  function attivaConTastiera(e) {
    if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
    e.preventDefault();
    e.currentTarget.click();
  }
  window.attivaConTastiera = attivaConTastiera;
"""

# la X della modale: nel wireframe c'e', e chiude l'applicazione
js_logica += """
  // ogni modale ha la sua X (wireframe): chiude la finestra dell'applicazione
  document.querySelectorAll('.dash-close').forEach((b) => b.addEventListener('click', () => {
    if (window.pywebview && window.pywebview.api.close_app) window.pywebview.api.close_app();
    else window.close();
  }));

  // Sequenza di apertura: Disclaimer 1 -> Disclaimer 2 -> scelta del tool.
  // Il consenso e' registrato in settings.json, quindi le due schermate
  // compaiono solo finche' non sono state accettate.
  function mostraSchermata(id) {
    ['disclaimer-1', 'disclaimer-2', 'dash-scelta'].forEach((k) => {
      document.getElementById(k).style.display = (k === id) ? '' : 'none';
    });
    // Sui disclaimer il blocco della patch non ci va: parla di un'operazione
    // sul gioco mentre l'utente sta ancora leggendo che cosa sia questo
    // programma, e offrirebbe "Disabilita" prima che l'avviso che lo spiega
    // sia stato accettato. Ricompare con la schermata di scelta.
    const suDisclaimer = (id === 'disclaimer-1' || id === 'disclaimer-2');
    document.body.classList.toggle('su-disclaimer', suDisclaimer);
  }
  document.getElementById('disc1-avanti').addEventListener(
    'click', () => mostraSchermata('disclaimer-2'));
  document.getElementById('disc2-avanti').addEventListener('click', async () => {
    await api().set_disclaimer_seen();
    mostraSchermata('dash-scelta');
  });

  async function avvioSchermate() {
    const visto = await api().get_disclaimer_seen();
    mostraSchermata(visto ? 'dash-scelta' : 'disclaimer-1');
  }
  if (window.pywebview) avvioSchermate();
  else window.addEventListener('pywebviewready', avvioSchermate);
"""

# Il vecchio link "Gestione playlist installate" era un elemento fisso
# dell'HTML; ora lo crea la devbar col suo onclick, quindi il listener che lo
# cercava per id trovava null e interrompeva tutto lo script (era questo a
# lasciare la barra di stato ferma su "Rilevamento cartella di gioco...").
i_pl = js_logica.find("  document.getElementById('playlist-cta')")
if i_pl != -1:
    j_pl = js_logica.index('});', i_pl) + 4
    js_logica = js_logica[:i_pl] + js_logica[j_pl:]

# --- pattern di sfondo: la stessa funzione deterministica di Genera ---
a = gen.index('  function renderBgPattern() {')
b = gen.index('  renderBgPattern();', a)
pattern = gen[a:b] + "  renderBgPattern();\n"

# --- Geometria del canvas: PRESA DA GENERA, non riscritta qui -----------
#
# Prima questo blocco era una copia scritta a mano, con il commento
# "identico a Genera". Non lo era piu': mentre Genera passava a un
# pavimento indipendente dalla densita' dello schermo, alla scala guidata
# dalla sola larghezza e alle tre fasce di adattamento, questa copia era
# rimasta ferma. Risultato misurato: la Dashboard sbordava di 142px a
# destra e 109px sotto a 1280x720, mentre le altre tre pagine reggevano.
#
# Ora le funzioni si ESTRAGGONO dal sorgente di Genera e si adatta solo
# cio' che e' davvero diverso: il selettore della pagina. Due copie della
# stessa logica in due file prima o poi divergono - e questa lo aveva gia'
# fatto.

_geometria = _blocco(gen, '  // ---- Le tre fasce di adattamento', '  function extraCorrente()')
_extra_corr = _blocco(gen, '  function extraCorrente()', chr(10) + chr(10))

# Funzioni del tema: estratte da Genera come la geometria, non
# ricopiate. Qui il tema SEGUE IL SISTEMA e il cambio vale per la sola
# sessione: la copia congelata invece leggeva e scriveva ancora
# l'impostazione salvata.

_fitpage = _blocco(gen, '  function fitPage() {', "  window.addEventListener('resize', fitPage);")

fit = ("""
  // Geometria IDENTICA a Genera perche' e' la stessa: estratta dal suo
  // sorgente da componi_dashboard.py, non ricopiata. L'unica differenza e'
  // il selettore della pagina (.dash-fixed invece di .genera-fixed) e il
  // fatto che qui --extra allarga SOLO il campo scuro col pattern: i
  // riquadri della dashboard sono centrati e allargarli non aggiungerebbe
  // informazione.
  // La disposizione impilata non si applica: la Dashboard non ha colonne
  // da impilare. Restano le soglie e il pavimento, che sono cio' che
  // serviva davvero.
"""
       # La Dashboard non ha colonne da impilare, ma ha un contenuto molto
       # piu' stretto delle altre pagine: una finestra di dialogo centrata e
       # una fascia in fondo. Quindi non riusa le misure di canvas di Genera
       # (1920 / 1448, dettate dai 1360 di contenuto della card anteprima):
       # sotto la fascia intera le bastano 1200x820, e con quelle a 1280x720
       # entra senza scorrimento orizzontale.
       # La Dashboard non ha colonne da impilare, ma ha un contenuto molto
       # piu' stretto delle altre pagine: una finestra di dialogo centrata
       # e una fascia in fondo. Non riusa quindi le misure di canvas di
       # Genera (1920 / 1448, dettate dai 1360 di contenuto della card
       # anteprima): sotto la fascia intera le bastano 1200x820, e con
       # quelle a 1280x720 entra senza scorrimento orizzontale.
       + _geometria.replace(
           "  function canvasW() { return impilata() ? 1448 : 1920; }",
           "  function canvasW() {" + chr(10) +
           "    return fasciaCanvas() === 'intera' ? 1920 : 1200;" + chr(10) +
           "  }"
         ).replace(
           "  function canvasH() {" + chr(10) +
           "    return impilata() ? (window.__altezzaImpilata || 1420) : 1080;" + chr(10) +
           "  }",
           "  function canvasH() {" + chr(10) +
           "    return fasciaCanvas() === 'intera' ? 1080 : 820;" + chr(10) +
           "  }"
         )
       + _extra_corr + chr(10)
       # La Dashboard non impila: non ha colonne da mandare a capo.
       # La riga che chiama impilaDalContenuto va tolta, altrimenti
       # cerca una funzione che qui non esiste e fitPage muore a meta -
       # con il risultato che il canvas non viene scalato affatto.
       + _fitpage.replace(".page.genera-fixed", ".page.dash-fixed")
                 .replace(
           "    if (page.classList.contains('stretta')) impilaDalContenuto(page);" + chr(10), "")
       + """  window.addEventListener('resize', fitPage);
  fitPage();
""")

RACCOGLI = """  // Raccoglitore di errori: senza questo un errore JS (o una promise
  // rifiutata, il caso piu' frequente qui perche' quasi tutte le chiamate
  // all'API sono async) sparisce in silenzio e la pagina resta a meta'.
  window.__errs = [];
  window.addEventListener('error', (e) => window.__errs.push(String(e.message)));
  window.addEventListener('unhandledrejection',
    (e) => window.__errs.push('promise: ' + (e.reason && e.reason.message || e.reason)));

"""

testa = orig[:orig.index('<style>') + len('<style>')]
# tolgo dallo <style> originale le regole che non servono piu' (icone sparse)
stile_vecchio = orig[orig.index('<style>') + 7: orig.index('</style>')]
stile_vecchio = re.sub(r'\s*\.scatter[^}]*}', '', stile_vecchio)
stile_vecchio = re.sub(r'\s*\.game-dir-bar[^}]*}', '', stile_vecchio)
stile_vecchio = re.sub(r'\s*\.status-warning[^}]*}', '', stile_vecchio)

# La Dashboard ORA ha lo switch IT/EN (il frame scuro 81:5252 lo mostra in
# alto a destra, e l'utente lo ha chiesto): oltre a rispettare la lingua
# scelta altrove, deve poterla cambiare. Serve quindi anche setLang, che
# prima qui non esisteva - e l'audit lo ha subito segnalato appena aggiunto
# il markup.
DIZ = io.open(_os.path.join(_QUI, 'i18n.js.part'), encoding='utf-8').read()
AVVIO_LINGUA = """
  function _segnaLingua(code) {
    document.querySelectorAll('.lang-pill').forEach(function (p) {
      p.classList.toggle('active', p.textContent.trim().toLowerCase() === code);
    });
  }

  async function setLang(code) {
    _lingua = code;
    if (code === 'it') ripristinaItaliano(); else traduciPagina();
    _segnaLingua(code);
    try { await api().set_lang(code); } catch (e) { /* fuori da pywebview */ }
  }
  window.setLang = setLang;

  async function initLang() {
    let code = 'it';
    try { code = await api().get_lang(); } catch (e) { /* default italiano */ }
    _lingua = code;
    if (code === 'it') ripristinaItaliano(); else traduciPagina();
    _segnaLingua(code);
  }
  if (window.pywebview) initLang();
  else window.addEventListener('pywebviewready', initLang);
"""

pagina = (testa + stile_vecchio + css + "</style>\n" + corpo +
          "<script>\n" + RACCOGLI + "  const api = () => window.pywebview.api;\n\n" +
          DIZ + pattern + fit + "\n" + js_logica + AVVIO_LINGUA +
          "</script>\n</body>\n</html>\n")

io.open(OUT, 'w', encoding='utf-8', newline='').write(pagina)
print('scritto', OUT, len(pagina), 'caratteri')
