# -*- coding: utf-8 -*-
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

"""Il pannello di tuning disegna davvero cio' che promette?

Il pannello e' l'unico posto in cui la tabella di tuning si tocca a mano, e
il suo disegno e' gia' stato rotto una volta senza che nulla lo dicesse: il
giorno in cui i gruppi sono passati da uno per argomento a tre per ambito,
`tuningDisegna` continuava a leggere una chiave che non c'era piu'. Nessun
errore, nessuna riga rossa: semplicemente il pannello mostrava una lista
piatta, e per accorgersene bisognava aprirlo e guardarlo.

Qui si prende la funzione VERA dal sorgente della pagina - non una copia,
che avrebbe smesso di somigliarle al primo ritocco - le si danno i dati VERI
di `tuning.per_il_pannello()`, e si guarda il markup che produce.

Serve `node` (c'e' gia' per gli altri controlli). Senza, il test lo dice e
si ferma, invece di dichiararsi superato.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RADICE)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import tuning                                                   # noqa: E402

PAGINA = os.path.join(RADICE, 'web_migration_spike', 'genera_real', 'index.html')

esiti = []


def prova(ok, nome, dettaglio=''):
    esiti.append((bool(ok), nome, dettaglio))


def pesca(sorgente, nome):
    """Il corpo di una funzione, dal sorgente della pagina.

    Si va da `function nome(` fino alla prima riga che chiude a due spazi
    di rientro: e' lo stile di tutto il file, ed e' cio' che rende il taglio
    affidabile senza tirarsi dietro un parser.
    """
    m = re.search(r'^  (?:async )?function %s\(' % re.escape(nome),
                  sorgente, re.M)
    if not m:
        return None
    fine = re.compile(r'^  \}$', re.M).search(sorgente, m.start())
    if not fine:
        return None
    return sorgente[m.start():fine.end()]


def main():
    sorgente = io.open(PAGINA, encoding='utf-8').read()
    m = re.search(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', sorgente, re.S)
    js = m.group(1) if m else ''

    pezzi = {}
    for nome in ('perAttributo', 'tuningDisegna', 'tuningMetodi'):
        pezzi[nome] = pesca(js, nome)
    mancanti = [k for k, v in pezzi.items() if not v]
    prova(not mancanti,
          'le funzioni del pannello si trovano ancora nel sorgente',
          'mancano: %s' % mancanti if mancanti else ', '.join(pezzi))
    if mancanti:
        return

    if not shutil.which('node'):
        prova(False, 'serve node per far girare il disegno del pannello')
        return

    dati = tuning.per_il_pannello()
    dati['ok'] = True
    # un valore spostato, per vedere il contrassegno del blocco
    chiave = dati['voci'][0]['chiave']
    for v in dati['voci']:
        if v['chiave'] == chiave:
            v['modificato'] = True

    banco = r'''
// Un DOM finto ridotto all'osso: il pannello tocca solo l'innerHTML del
// corpo, il select dei metodi e due bottoni.
const _el = {};
function nodo(id) {
  if (!_el[id]) _el[id] = {id: id, innerHTML: '', textContent: '',
                           disabled: false, dataset: {}, value: ''};
  return _el[id];
}
const document = {
  getElementById: nodo,
  addEventListener: () => {},
};
const window = {};
const _tuningAperti = new Set();
let _tuningPrimoDisegno = true;
__PEZZI__
const DATI = __DATI__;
(async () => {
  await tuningDisegna(DATI);
  const uno = nodo('tuning-corpo').innerHTML;
  // secondo giro: un blocco chiuso a mano deve restare chiuso
  _tuningAperti.clear();
  await tuningDisegna(DATI);
  const due = nodo('tuning-corpo').innerHTML;
  console.log(JSON.stringify({
    html: uno,
    tuttiChiusi: due,
    metodi: nodo('tuning-metodo').innerHTML,
    esporta: nodo('tuning-esporta').disabled,
    elimina: nodo('tuning-elimina').disabled,
    nota: nodo('tuning-metodo-nota').textContent,
  }));
})();
'''
    banco = banco.replace('__PEZZI__', '\n'.join(pezzi.values()))
    banco = banco.replace('__DATI__', json.dumps(dati, ensure_ascii=False))
    d = tempfile.mkdtemp(prefix='pannello_')
    f = os.path.join(d, 'banco.mjs')
    io.open(f, 'w', encoding='utf-8').write(banco)
    r = subprocess.run(['node', f], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if r.returncode != 0:
        prova(False, 'il disegno del pannello gira senza errori',
              (r.stderr or '').strip()[:400])
        shutil.rmtree(d, ignore_errors=True)
        return
    prova(True, 'il disegno del pannello gira senza errori')
    fuori = json.loads(r.stdout.strip().splitlines()[-1])
    shutil.rmtree(d, ignore_errors=True)
    html = fuori['html']

    # ---- i tre blocchi ci sono, e sono chiusi
    aperti = html.count('<details')
    chiusi = html.count('</details>')
    prova(aperti == len(dati['gruppi']) and aperti == chiusi,
          'un blocco richiudibile per ogni ambito, e tutti chiusi bene',
          '%d aperture, %d chiusure, %d ambiti'
          % (aperti, chiusi, len(dati['gruppi'])))

    # ---- ogni valore compare una volta sola, dentro un blocco
    doppi = [v['chiave'] for v in dati['voci']
             if html.count('data-k="%s"' % v['chiave']) != 1]
    prova(not doppi,
          'ogni valore regolabile compare una volta sola',
          'in doppio o assenti: %s' % doppi if doppi
          else '%d valori' % len(dati['voci']))

    # ---- la spiegazione dell'ambito e' li'
    senza = [g['titolo'] for g in dati['gruppi']
             if g['spiega'] and g['spiega'][:24] not in html]
    prova(not senza,
          'ogni blocco dice a cosa serve', 'senza spiegazione: %s' % senza)

    # ---- il contrassegno: chiuso, e' l'unico modo per sapere che dentro
    #      c'e' qualcosa di modificato
    prova('tp-gmod' in html,
          'un blocco con dentro dei valori spostati lo dice anche da chiuso')

    # ---- e il blocco che li contiene si apre da solo
    gruppo_mod = next(v['gruppo'] for v in dati['voci'] if v['modificato'])
    m = re.search(r'<details class="tp-blocco" data-g="%s"([^>]*)>'
                  % re.escape(gruppo_mod), fuori['tuttiChiusi'])
    prova(bool(m) and 'open' in m.group(1),
          'e si apre da solo anche partendo da tutto chiuso',
          m.group(1) if m else 'blocco non trovato')

    # ---- i metodi
    prova('Predefinito' in fuori['metodi'],
          'la tendina dei metodi parte da «Predefinito»')
    prova(fuori['esporta'] and fuori['elimina'],
          'e su «Predefinito» esporta ed elimina sono spenti: non e\' un '
          'metodo, e\' l\'assenza di metodo')


if __name__ == '__main__':
    main()
    print('===== IL PANNELLO DI TUNING =====')
    if not esiti:
        print('  FALLITO  nessun controllo eseguito')
        sys.exit(1)
    rossi = 0
    for ok, nome, dett in esiti:
        print(('  ok       ' if ok else '  FALLITO  ') + nome)
        if dett:
            print('             %s' % dett)
        rossi += 0 if ok else 1
    print('  %d problemi' % rossi)
    sys.exit(1 if rossi else 0)
