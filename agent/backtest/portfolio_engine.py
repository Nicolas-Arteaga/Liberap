"""
ROUND 23 — motor central de asignación de capital (Parte 3 del brief).

Un solo punto de verdad para "10 candidatos, 3 slots -> quien entra". Todo
backtest futuro que compita por capital limitado debe usar esta funcion, en
vez de reimplementar su propia logica de slot-filling (como hacia cada
script r18-r22 por separado).

Entrada: candidatos con timestamp + score + info suficiente para ejecutar.
Salida: quien entra, quien se rechaza, cuanto capital se asigna.

Regla de asignacion (Parte 2): DETERMINISTICA, basada solo en informacion
causal disponible en ese timestamp (score = funcion de features pre-señal,
nunca del resultado). Si el score empata, el tie-break es el symbol en
orden alfabetico ascendente -- NUNCA el orden de iteracion del
diccionario/lista de entrada. Se prueba explicitamente (test_order_
invariance) que alimentar la MISMA lista de candidatos en cualquier orden
de entrada produce EXACTAMENTE el mismo resultado.
"""
import collections


class Position:
    __slots__ = ("symbol", "open_ts", "close_ts", "score")

    def __init__(self, symbol, open_ts, close_ts, score):
        self.symbol = symbol; self.open_ts = open_ts; self.close_ts = close_ts; self.score = score


def allocate_timestamp(candidates, free_at, slots, tie_break_key=None):
    """candidates: list of dicts con al menos {symbol, score}. free_at: list
    de longitud `slots` con el timestamp en que cada slot queda libre. Se
    MODIFICA in-place. Devuelve (accepted, rejected) -- listas de dicts,
    en el MISMO orden determinístico sin importar el orden de `candidates`
    de entrada.

    Regla: orden fijo score DESC, symbol ASC como tie-break (o el
    tie_break_key dado). Esto es una funcion pura de `candidates` y
    `free_at` -- no del orden en que `candidates` llego a esta funcion.
    """
    key = tie_break_key or (lambda c: c["symbol"])
    ordered = sorted(candidates, key=lambda c: (-c["score"], key(c)))
    accepted, rejected = [], []
    for c in ordered:
        fslot = next((k for k in range(slots) if free_at[k] <= c["ts"]), None)
        if fslot is None:
            rejected.append(c)
            continue
        accepted.append(c)
        free_at[fslot] = c["exit_ts"]
    return accepted, rejected


def run_portfolio(all_candidates, slots, capital, hold_ms):
    """all_candidates: list of dicts {ts, symbol, score, ...payload}.
    Agrupa por timestamp y corre allocate_timestamp en orden cronologico de
    timestamps (el UNICO orden con significado economico real: no podemos
    asignar capital a un evento antes de que ocurra). Dentro de cada
    timestamp, el orden de los candidatos que llegan en la lista de entrada
    NO debe afectar el resultado -- eso es lo que testeamos.

    Devuelve dict con 'accepted' (list) y 'rejected' (list), y 'notional'.
    """
    notional = capital / slots
    free_at = [0] * slots
    by_ts = collections.defaultdict(list)
    for c in all_candidates:
        by_ts[c["ts"]].append(c)
    accepted_all = []; rejected_all = []
    for ts in sorted(by_ts):
        cands_here = list(by_ts[ts])   # el orden de entrada de ESTA lista es lo que se testea
        for c in cands_here:
            c["exit_ts"] = ts + hold_ms
        acc, rej = allocate_timestamp(cands_here, free_at, slots)
        accepted_all.extend(acc); rejected_all.extend(rej)
    return dict(accepted=accepted_all, rejected=rejected_all, notional=notional)
