# -*- coding: utf-8 -*-
"""Come si comporta la finestra a SCHERMO INTERO su questo monitor.

Il canvas e' 16:9 fisso. Su un monitor 21:9 la scala e' sempre limitata
dall'ALTEZZA, quindi ingrandire la finestra non ingrandisce quasi nulla e
lascia due bande vuote ai lati. Questo script lo misura invece di dedurlo.
"""
import os, sys, time
QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, QUI); sys.path.insert(0, os.path.dirname(QUI))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import webview

sys.path.insert(0, os.path.join(QUI, 'correggi_real'))
import app as a
a._work_dir = a.build_serving_dir(); a._init_songs()

JS = """(function(){
  var p = document.querySelector('.page.genera-fixed, .page.dash-fixed');
  var r = p ? p.getBoundingClientRect() : {width:0,height:0};
  return {w: window.innerWidth, h: window.innerHeight,
          cw: r.width, ch: r.height, s: window.__scalaCanvas || 0,
          dpr: window.devicePixelRatio,
          extra: window.__extraCanvas,
          varExtra: p ? getComputedStyle(p).getPropertyValue('--extra') : '?',
          larghezzaCalcolata: p ? getComputedStyle(p).width : '?',
          inline: p ? p.style.getPropertyValue('--extra') : '?'};
})()"""


def run(window):
    time.sleep(2.0)
    d = window.evaluate_js(JS)
    print('--- finestra come si apre ---')
    print('  viewport %sx%s | canvas %.0fx%.0f | scala %.3f'
          % (d['w'], d['h'], d['cw'], d['ch'], d['s']))
    print('  --extra inline=%r calcolato=%r | width CSS=%r | __extraCanvas=%r'
          % (d['inline'], d['varExtra'], d['larghezzaCalcolata'], d['extra']))
    print('  bande vuote ai lati: %.0f px CSS per lato' % ((d['w'] - d['cw']) / 2))
    window.maximize()
    time.sleep(1.5)
    d = window.evaluate_js(JS)
    print('--- finestra MASSIMIZZATA ---')
    print('  viewport %sx%s | canvas %.0fx%.0f | scala %.3f'
          % (d['w'], d['h'], d['cw'], d['ch'], d['s']))
    print('  --extra inline=%r calcolato=%r | width CSS=%r | __extraCanvas=%r'
          % (d['inline'], d['varExtra'], d['larghezzaCalcolata'], d['extra']))
    print('  bande vuote ai lati: %.0f px CSS per lato = %.0f px fisici'
          % ((d['w'] - d['cw']) / 2, (d['w'] - d['cw']) / 2 * d['dpr']))
    print('  spreco orizzontale: %.0f%% della finestra'
          % ((d['w'] - d['cw']) / d['w'] * 100))
    window.destroy()


w = webview.create_window("max", os.path.join(a._work_dir, 'index.html'),
                          js_api=a.Api(), width=1920, height=1080)
webview.start(run, w)
