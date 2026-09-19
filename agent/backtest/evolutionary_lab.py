"""
LABORATORIO EVOLUTIVO -- 2026-08-18, reemplaza la busqueda random pura de
strategy_lab.py. Pedido explicito del usuario: "quiero algo cuantico...
que avance a lo loco, que sepa como ir evolucionando" -- no tirar dados a
ciegas para siempre, sino aprender de lo que ya encontro y converger hacia
las zonas buenas del espacio de parametros.

Algoritmo genetico simple sobre el MISMO espacio de piezas ya validadas
(ma_cross, level_sweep, band_touch, rsi_extreme, ma_pullback) y el MISMO
motor honesto (backtest_strategy con vetos reales + limite real de 3 cupos
x $150, arreglado 2026-08-17/18 -- ver strategy_lab.py):

  1. Poblacion inicial: POPULATION_SIZE individuos random.
  2. Cada generacion: evaluar TODOS (backtest completo, split-half real).
  3. Elitismo: los mejores POP*ELITE_FRAC sobreviven tal cual.
  4. Resto de la poblacion se rellena con:
     - Mutacion (cambia 1-2 parametros de un elite a un vecino del espacio)
     - Cruce (mezcla parametros de 2 elites distintos)
     - Random fresco (mantiene diversidad, evita optimo local prematuro)
  5. Se repite para siempre. Fitness = $/mes si pasa el minimo de trades,
     con bonus fuerte si ademas pasa passes_bar (estable en ambas mitades)
     -- no basta con ganar mucho, tiene que sostenerse en el tiempo (mismo
     criterio anti-MA-Slope-Caso-3 de siempre).

Escribe TODO en los mismos archivos que strategy_lab.py (found_strategies.
jsonl, lab_tested_all.jsonl, lab_current.json) -- el frontend/API no
necesitan cambios, solo mejora el generador por dentro.
"""
import sys
import os
import sqlite3
import json
import random
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backtest.strategy_lab import (  # noqa: E402
    DB_PATH, FOUND_PATH, PROGRESS_PATH, TESTED_LOG, CURRENT_PATH,
    load_basket, backtest_strategy, evaluate, strat_label,
    ENTRY_TYPES, TIMEFRAMES_MIN, MA_PAIRS, SIDES, ATR_SL_MULTS, RR_MULTS,
    LOOKBACKS, RSI_THRESH, MA_PULLBACK_SLOPE_MIN_PCT, VOLUME_MULTS,
    random_strategy, BAR_MONTHLY_USD, MIN_TRADES_PER_HALF,
)

POPULATION_SIZE = 24
ELITE_FRAC = 0.30          # top 30% sobreviven intactos a la siguiente generacion
MUTATION_FRAC = 0.40       # 40% de la poblacion nueva = mutaciones de elites
CROSSOVER_FRAC = 0.30      # 30% = cruces entre 2 elites
# el resto (30%) se completa con random fresco, para no converger prematuro

GEN_LOG_PATH = os.path.join(os.path.dirname(__file__), "evolutionary_generations.jsonl")


def fitness(result: dict) -> float:
    """$/mes como base, con bonus fuerte si pasa passes_bar (estable en
    ambas mitades) -- evita que el genetico converja hacia estrategias que
    ganan mucho en agregado pero se estan apagando (mismo problema real
    que vimos con MA Slope Caso 3)."""
    if result.get("insufficient_data"):
        return -9999.0
    monthly = result.get("monthly", -9999.0)
    if result.get("passes_bar"):
        return monthly + 500.0  # empuja fuerte a las estables al frente del ranking
    return monthly


def clamp_choice(options, current, direction):
    """Mueve `current` un paso hacia arriba/abajo dentro de `options`
    (lista ordenada) -- mutacion de "vecino cercano", no un salto random
    a cualquier punto del espacio."""
    if current not in options:
        return random.choice(options)
    idx = options.index(current)
    new_idx = idx + direction
    new_idx = max(0, min(len(options) - 1, new_idx))
    return options[new_idx]


def mutate(strat: dict) -> dict:
    """Copia mutada de `strat` -- cambia 1-2 parametros a un vecino
    cercano en el espacio discreto (no un random total, para explorar
    ALREDEDOR de lo que ya funciono, no lejos de eso)."""
    child = dict(strat)
    et = child["entry_type"]
    n_mutations = random.choice([1, 1, 2])  # mayoria mutaciones chicas, a veces 2
    mutable_fields = ["tf_min", "side", "atr_sl_mult", "rr_mult"]
    if et == "ma_cross":
        mutable_fields.append("ma_pair")
    if et == "level_sweep":
        mutable_fields.append("lookback")
    if et == "rsi_extreme":
        mutable_fields.append("rsi_thresh")
    if et == "ma_pullback":
        mutable_fields += ["lookback", "slope_min_pct", "volume_mult"]

    for field in random.sample(mutable_fields, min(n_mutations, len(mutable_fields))):
        direction = random.choice([-1, 1])
        if field == "tf_min":
            child["tf_min"] = clamp_choice(TIMEFRAMES_MIN, child["tf_min"], direction)
        elif field == "side":
            child["side"] = random.choice(SIDES)
        elif field == "atr_sl_mult":
            child["atr_sl_mult"] = clamp_choice(ATR_SL_MULTS, child["atr_sl_mult"], direction)
        elif field == "rr_mult":
            child["rr_mult"] = clamp_choice(RR_MULTS, child["rr_mult"], direction)
        elif field == "ma_pair":
            child["ma_pair"] = random.choice(MA_PAIRS)
        elif field == "lookback":
            child["lookback"] = clamp_choice(LOOKBACKS, child["lookback"], direction)
        elif field == "rsi_thresh":
            child["rsi_thresh"] = random.choice(RSI_THRESH)
        elif field == "slope_min_pct":
            child["slope_min_pct"] = clamp_choice(MA_PULLBACK_SLOPE_MIN_PCT, child["slope_min_pct"], direction)
        elif field == "volume_mult":
            child["volume_mult"] = clamp_choice(VOLUME_MULTS, child["volume_mult"], direction)
    return child


def crossover(parent_a: dict, parent_b: dict) -> dict:
    """Hijo que mezcla parametros de 2 padres -- si son de distinto
    entry_type, el hijo hereda el entry_type de uno de los dos (elegido al
    azar) y solo los campos compatibles con ese tipo del otro padre que
    apliquen; el resto sale de random_strategy() base para no dejar
    campos huerfanos."""
    base_et = random.choice([parent_a["entry_type"], parent_b["entry_type"]])
    child = random_strategy()
    child["entry_type"] = base_et
    for field in ("tf_min", "side", "atr_sl_mult", "rr_mult"):
        child[field] = random.choice([parent_a.get(field, child[field]), parent_b.get(field, child[field])])
    if base_et == "ma_cross":
        child["ma_pair"] = random.choice([parent_a.get("ma_pair"), parent_b.get("ma_pair"), child["ma_pair"]])
    if base_et == "level_sweep":
        child["lookback"] = random.choice([parent_a.get("lookback"), parent_b.get("lookback"), child["lookback"]])
    if base_et == "rsi_extreme":
        child["rsi_thresh"] = random.choice([parent_a.get("rsi_thresh"), parent_b.get("rsi_thresh"), child["rsi_thresh"]])
    if base_et == "ma_pullback":
        child["lookback"] = random.choice([parent_a.get("lookback"), parent_b.get("lookback"), child["lookback"]])
        child["slope_min_pct"] = random.choice([parent_a.get("slope_min_pct"), parent_b.get("slope_min_pct"), child["slope_min_pct"]])
        child["volume_mult"] = random.choice([parent_a.get("volume_mult"), parent_b.get("volume_mult"), child["volume_mult"]])
    return child


def next_generation(evaluated: list) -> list:
    """evaluated: lista de (strat, result) de la generacion actual, YA
    ordenada por fitness descendente. Devuelve la poblacion de la
    siguiente generacion (solo los strats, sin evaluar todavia)."""
    n_elite = max(2, int(POPULATION_SIZE * ELITE_FRAC))
    elites = [s for s, r in evaluated[:n_elite]]

    new_pop = list(elites)  # elitismo: pasan intactos

    n_mutation = int(POPULATION_SIZE * MUTATION_FRAC)
    n_crossover = int(POPULATION_SIZE * CROSSOVER_FRAC)
    n_random = POPULATION_SIZE - len(new_pop) - n_mutation - n_crossover

    for _ in range(n_mutation):
        new_pop.append(mutate(random.choice(elites)))
    for _ in range(n_crossover):
        a, b = random.sample(elites, 2) if len(elites) >= 2 else (elites[0], elites[0])
        new_pop.append(crossover(a, b))
    for _ in range(max(0, n_random)):
        new_pop.append(random_strategy())

    return new_pop[:max(POPULATION_SIZE, len(elites))]  # nunca se pierde un elite por redondeo


def write_current(tried, found, generation, strat=None, t_start=None, days_covered=None, gen_best_fitness=None):
    payload = {
        "heartbeat": datetime.now(timezone.utc).isoformat(),
        "tried": tried,
        "found": found,
        "generation": generation,
        "gen_best_fitness": gen_best_fitness,
        "current_label": (strat_label(strat) + f" [gen {generation}]") if strat else None,
        "current_strat": strat,
        "elapsed_sec": round(time.time() - t_start, 1) if t_start else None,
        "days_covered": round(days_covered, 1) if days_covered else None,
        "engine": "evolutionary",
    }
    tmp_path = CURRENT_PATH + f".tmp{os.getpid()}"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp_path, CURRENT_PATH)
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def main():
    conn = sqlite3.connect(DB_PATH)
    basket = load_basket(conn)

    cur = conn.cursor()
    cur.execute("SELECT MIN(open_time), MAX(open_time) FROM klines_clean WHERE interval='15m'")
    t0, t1 = cur.fetchone()
    days_covered = (t1 - t0) / (1000 * 60 * 60 * 24) if t0 and t1 else 240

    tried = 0
    found = 0
    generation = 0
    t_start = time.time()

    population = [random_strategy() for _ in range(POPULATION_SIZE)]

    while True:
        try:
            generation += 1
            evaluated = []
            for strat in population:
                write_current(tried, found, generation, strat, t_start, days_covered)
                trades = backtest_strategy(conn, basket, strat)
                result = evaluate(trades, days_covered)
                tried += 1

                row = {"strat": strat, "result": result, "ts": datetime.now(timezone.utc).isoformat(),
                       "generation": generation}
                with open(TESTED_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")

                if result.get("passes_bar"):
                    found += 1
                    with open(FOUND_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps(row) + "\n")
                    print(
                        f"[EVO-LAB] *** ENCONTRADA #{found} (gen {generation}) *** {strat_label(strat)} -> "
                        f"${result['monthly']}/mes | WR={result['wr_pct']}% | n={result['n']} | "
                        f"mitades: ${result['pnl_h1']}/${result['pnl_h2']}",
                        flush=True,
                    )

                evaluated.append((strat, result))

                if tried % 10 == 0:
                    elapsed = time.time() - t_start
                    with open(PROGRESS_PATH, "a", encoding="utf-8") as f:
                        f.write(f"{datetime.now(timezone.utc).isoformat()} | probadas={tried} | encontradas={found} | "
                                f"gen={generation} | basket={len(basket)} simbolos | {elapsed/tried:.1f}s/estrategia\n")

            evaluated.sort(key=lambda sr: fitness(sr[1]), reverse=True)
            best_strat, best_result = evaluated[0]
            best_fit = fitness(best_result)

            gen_summary = {
                "generation": generation,
                "ts": datetime.now(timezone.utc).isoformat(),
                "best_label": strat_label(best_strat),
                "best_monthly": best_result.get("monthly"),
                "best_passes_bar": best_result.get("passes_bar"),
                "best_fitness": round(best_fit, 2),
                "population_size": len(evaluated),
                "cumulative_tried": tried,
                "cumulative_found": found,
            }
            with open(GEN_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(gen_summary) + "\n")
            print(f"[EVO-LAB] === Generacion {generation} completa === mejor: {strat_label(best_strat)} "
                  f"-> ${best_result.get('monthly')}/mes (passes_bar={best_result.get('passes_bar')}) "
                  f"| fitness={best_fit:.2f} | acumulado: {tried} probadas, {found} encontradas", flush=True)

            population = next_generation(evaluated)

        except Exception as e:
            print(f"[EVO-LAB] *** ERROR en generacion {generation} (tried={tried}), continuando *** {type(e).__name__}: {e}", flush=True)
            time.sleep(1)
            population = [random_strategy() for _ in range(POPULATION_SIZE)]  # reset defensivo si algo se corrompio


if __name__ == "__main__":
    main()
