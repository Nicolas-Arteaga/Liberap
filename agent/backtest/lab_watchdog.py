"""Retirado: nunca relanza servicios ni expone control del Laboratorio.

El servidor de control anterior fue eliminado: el Laboratorio no tiene endpoint
de arranque/parada ni ruta hacia StrategyProfiles. Este archivo se conserva sólo
para que una tarea histórica, si todavía existiera en otra máquina, termine de
forma explícita y segura en vez de intentar reconstruir esa puerta.
"""

print("[WATCHDOG] Retirado: no se arranca ni controla ningún servicio del Laboratorio.")
