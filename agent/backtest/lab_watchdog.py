"""
Watchdog simple del laboratorio: pedido explicito del usuario (2026-09-13)
tras encontrar que el lab quedo caido 2 dias sin que nadie lo notara --
"necesito que siempre este activo". Corre cada 5 min via Tarea Programada
de Windows, le pregunta a lab_control_server (:8011) si esta vivo y si no,
lo arranca. No reemplaza a lab_control_server (sigue siendo el que sabe
arrancar/parar el proceso real) -- esto solo lo mantiene vivo sin
intervencion manual.
"""
import requests

try:
    r = requests.get("http://localhost:8011/control/status", timeout=10)
    running = r.json().get("running", False)
except Exception:
    running = False

if not running:
    try:
        requests.post("http://localhost:8011/control/start", timeout=10)
        print("[WATCHDOG] Laboratorio caido -- relanzado.")
    except Exception as e:
        print(f"[WATCHDOG] Laboratorio caido, no se pudo relanzar: {e}")
else:
    print("[WATCHDOG] Laboratorio OK.")
