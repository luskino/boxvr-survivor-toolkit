# -*- coding: utf-8 -*-
"""Pulizia delle cartelle di servizio lasciate dagli avvii precedenti.

Ogni avvio del toolkit crea una cartella temporanea (`boxvr_<pagina>_*`) con
le pagine e una COPIA di ogni brano dell'elenco. Finora non veniva mai
cancellata: sono state trovate 596 cartelle per 117 GB. Con brani da 250 MB
bastano poche decine di avvii per riempire un disco.

Qui si cancellano quelle VECCHIE, all'avvio, prima di crearne una nuova.

Tre cautele, tutte necessarie:

  prefisso   si tocca solo cio' che porta il prefisso di questo programma.
             In %TEMP% c'e' roba di tutti: cancellare per data sarebbe un
             ottimo modo per rompere il lavoro di qualcun altro.

  eta'       si saltano le cartelle usate nelle ultime ORE_DI_GRAZIA ore.
             L'utente puo' avere una seconda finestra aperta adesso, e la
             sua cartella non va tolta da sotto i piedi.

  silenzio   una cartella bloccata si salta. Non poter cancellare un
             residuo non e' un motivo per impedire l'avvio del programma.
"""
import os
import shutil
import tempfile
import time

PREFISSO = 'boxvr_'
ORE_DI_GRAZIA = 6


NOME_PID = '.boxvr_pid'


def marca(cartella):
    """Scrive nella cartella il PID di chi la sta usando.

    Serve a rispondere alla domanda "questa cartella e' ancora in uso?"
    guardando il processo invece che l'orologio.
    """
    try:
        with open(os.path.join(cartella, NOME_PID), 'w', encoding='utf-8') as f:
            f.write(str(os.getpid()))
    except OSError:
        pass


def _processo_vivo(pid):
    """True se quel PID esiste ancora."""
    if pid <= 0:
        return False
    try:
        import ctypes
        # Aprire il processo NON basta: su Windows OpenProcess riesce anche
        # su un processo gia' terminato, finche' qualcuno ne tiene un
        # handle aperto - il PID resta valido come guscio vuoto. Provato: una
        # cartella intestata a un processo morto non veniva rimossa.
        # La risposta vera la da' il codice di uscita: finche' e'
        # STILL_ACTIVE il processo sta girando davvero.
        STILL_ACTIVE = 259
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False                    # non esiste piu' nemmeno il guscio
        try:
            codice = ctypes.c_ulong()
            if not k.GetExitCodeProcess(h, ctypes.byref(codice)):
                return True                 # non si sa: si presume vivo
            return codice.value == STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    except Exception:
        # se non lo si puo' sapere, si presume vivo: meglio tenere una
        # cartella di troppo che cancellarne una in uso
        return True


def _abbandonata(cartella):
    """La cartella appartiene a un processo che non c'e' piu'?

    None quando non si puo' dire (nessun PID scritto: viene da una versione
    precedente) - li' decide il criterio del tempo.
    """
    p = os.path.join(cartella, NOME_PID)
    try:
        with open(p, encoding='utf-8') as f:
            pid = int((f.read() or '0').strip())
    except (OSError, ValueError):
        return None
    return not _processo_vivo(pid)


# Cio' che produce il programma: trackdata, l'audio convertito, la
# definizione del brano, la playlist e la lista di azioni. Si cancella per
# estensione e non svuotando la cartella, perche' li' dentro finisce solo
# roba nostra - ma se qualcuno ci ha messo qualcosa di suo non tocca a noi
# decidere di buttarlo.
ESTENSIONI_PRODOTTE = ('.trackdata.txt', '.wav', '.wdef.txt',
                       '.workoutplaylist.txt', '.actionlist.json')


def svuota_risultati():
    """Toglie i brani gia' generati/corretti dalle cartelle dei risultati.

    Sono file di PASSAGGIO: si generano, si installano in BoxVR, e da quel
    momento la copia che conta e' quella nella libreria del gioco. Quella
    qui e' un doppione che non serve piu' a nessuno, e pesa quanto i wav -
    cioe' tutto. Misurati 715 MB in 76 file prima che questa funzione
    esistesse.

    Da non confondere con `pulisci_vecchie_cartelle`, che si occupa delle
    cartelle TEMPORANEE di servizio in %TEMP%: quelle sono le copie di
    lavoro, queste sono i risultati. Erano due problemi diversi, e per un
    pezzo si e' risolto solo il primo.

    Ritorna (quanti file, quanti byte). Non solleva mai: la pulizia non deve
    poter impedire ne' l'avvio ne' la chiusura del programma.
    """
    quanti, byte = 0, 0
    try:
        import percorsi
    except Exception:                      # noqa: BLE001
        return (0, 0)
    cartelle = []
    for quale in ('genera', 'correggi'):
        try:
            # la STESSA funzione con cui il programma decide dove scrivere:
            # cablare i percorsi qui li legherebbe a una macchina sola
            cartelle.append(percorsi.cartella_output(quale))
        except Exception:                  # noqa: BLE001
            pass
        # E la cartella di RIPIEGO sotto il profilo utente, dove il
        # programma scrive finche' l'utente non ne sceglie una sua. Sono due
        # momenti diversi della vita del programma, e tutti e due possono
        # avere dentro dei risultati vecchi. Guardando solo la prima si
        # lascia indietro esattamente il caso misurato il 06/09: 715 MB nel
        # ripiego, mentre la cartella configurata era un'altra.
        try:
            base = os.environ.get('APPDATA') or percorsi.RADICE
            nome = 'generati' if quale == 'genera' else 'corretti'
            cartelle.append(os.path.join(base, 'BoxVR Level Fixer',
                                         'brani_' + quale, nome))
        except Exception:                  # noqa: BLE001
            pass
    viste = set()
    for cartella in cartelle:
        if not cartella or not os.path.isdir(cartella):
            continue
        chiave = os.path.normcase(os.path.abspath(cartella))
        if chiave in viste:                # le due possono coincidere
            continue
        viste.add(chiave)
        for nome in os.listdir(cartella):
            if not nome.lower().endswith(ESTENSIONI_PRODOTTE):
                continue
            p = os.path.join(cartella, nome)
            try:
                peso = os.path.getsize(p)
                os.remove(p)
            except OSError:
                continue
            quanti += 1
            byte += peso
    return (quanti, byte)


def pulisci_vecchie_cartelle(ore=ORE_DI_GRAZIA):
    """Cancella le cartelle di servizio piu' vecchie di `ore`.

    Ritorna (quante, byte_liberati) - utile per scriverlo nel log, non per
    decidere qualcosa: il chiamante non deve mai fermarsi su questo esito.
    """
    radice = tempfile.gettempdir()
    limite = time.time() - ore * 3600
    quante = byte = 0
    try:
        nomi = os.listdir(radice)
    except OSError:
        return (0, 0)
    for nome in nomi:
        if not nome.startswith(PREFISSO):
            continue
        p = os.path.join(radice, nome)
        try:
            if not os.path.isdir(p):
                continue
            # Prima decideva solo l'eta'. Ma il tempo e' una misura indiretta
            # della domanda vera, che e' "questa cartella e' ancora in uso?".
            # Adesso la si fa direttamente: dentro c'e' il PID di chi l'ha
            # creata. Se quel processo non esiste piu' la cartella e'
            # abbandonata e si toglie SUBITO, a qualunque eta' - e' il caso
            # del crash, che prima lasciava mezzo giga in giro per sei ore, o
            # per sempre se il tool non veniva riaperto.
            stato = _abbandonata(p)
            if stato is False:
                continue                  # processo vivo: non si tocca
            if stato is None and os.path.getmtime(p) > limite:
                continue                  # senza PID decide l'eta', come rete
            peso = 0
            for cartella, _, file in os.walk(p):
                for f in file:
                    try:
                        peso += os.path.getsize(os.path.join(cartella, f))
                    except OSError:
                        pass
            shutil.rmtree(p, ignore_errors=True)
            if not os.path.isdir(p):
                quante += 1
                byte += peso
        except OSError:
            continue          # bloccata o sparita: si tira dritto
    return (quante, byte)
