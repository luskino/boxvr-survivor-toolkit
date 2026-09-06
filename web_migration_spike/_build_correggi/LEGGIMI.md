# Come sono generate le pagine Correggi e Dashboard

Queste due pagine NON sono scritte a mano: sono **composte** da pezzi presi
da `genera_real/index.html`, così la logica condivisa (forma d'onda a
livelli, zoom, cursore, click a tempo, tooltip, tema, lingua, pattern di
sfondo, riga brano) resta una sola implementazione invece di copie
destinate a divergere.

Per rigenerarle dopo una modifica a `genera_real/index.html`:

```
python estrai_pezzi_genera.py      # CSS + HTML condivisi
python estrai_js_condiviso.py      # blocchi JS condivisi (whitelist per nome)
python fix_init_correggi.py        # attesa di pywebviewready + proxy API senza prefisso
python aggiungi_raccogli_errori.py # window.__errs (idempotente)
python componi_correggi.py         # -> correggi_real/index.html
python componi_dashboard.py        # -> dashboard_real/index.html
```

Gli script usano percorsi assoluti allo scratchpad della sessione in cui
sono stati scritti: se li si riesegue altrove vanno aggiornati i percorsi in
testa a ciascun file.

**Dimenticare di rieseguire l'estrazione dopo aver corretto `genera_real` è
già successo**: Correggi era stato composto prima delle correzioni su X di
rimozione, pillola "Rimuovi" e misure della riga brano, e l'audit
(`../audit_figma.py`) le ha trovate tutte e tre.
