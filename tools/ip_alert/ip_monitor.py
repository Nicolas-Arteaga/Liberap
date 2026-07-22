"""
Monitor de IP publica para la whitelist de la API key de Binance.

Binance no permite actualizar la whitelist de IP via API (es la unica
barrera real si roban la key), asi que esto NO automatiza el update -
avisa lo mas fuerte posible apenas la IP cambia para que se actualice
a mano en Binance antes de perder trades.

Uso:
    python ip_monitor.py            # corre en loop, chequea cada INTERVAL_SECONDS
    python ip_monitor.py --once     # chequea una sola vez y sale (para Task Scheduler)

Config: copiar config.example.json a config.json y completar credenciales.
"""
import json
import time
import sys
import subprocess
import threading
from pathlib import Path
from datetime import datetime

import requests

# La consola de Windows por default usa cp1252, que no soporta el emoji de
# la alerta (⚠️) y tira UnicodeEncodeError ANTES de mandar Telegram/WhatsApp.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "last_ip.txt"
INTERVAL_SECONDS = 300  # 5 min

# Servicios publicos neutrales para consultar IP - NUNCA pegarle a Binance para esto
IP_CHECK_URLS = [
    "https://api.ipify.org?format=json",
    "https://ifconfig.me/ip",
]


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"[ERROR] Falta {CONFIG_PATH}. Copia config.example.json y completa tus datos.")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def get_public_ip() -> str | None:
    for url in IP_CHECK_URLS:
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            if "ipify" in url:
                return resp.json()["ip"]
            return resp.text.strip()
        except Exception:
            continue
    return None


def get_last_known_ip() -> str | None:
    if STATE_PATH.exists():
        return STATE_PATH.read_text(encoding="utf-8").strip()
    return None


def save_ip(ip: str):
    STATE_PATH.write_text(ip, encoding="utf-8")


def send_telegram(config: dict, message: str):
    token = config.get("telegram_bot_token")
    chat_id = config.get("telegram_chat_id")
    if not token or not chat_id:
        print("[telegram] no configurado, salteo")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[telegram] ERROR {resp.status_code}: {resp.text}")
        else:
            print("[telegram] enviado")
    except Exception as e:
        print(f"[telegram] EXCEPCION: {e}")


def send_whatsapp(config: dict, message: str):
    # CallMeBot (gratis, sin cuenta business): mandas UNA vez "I allow
    # callmebot to send me messages" al numero de CallMeBot desde tu WhatsApp,
    # te devuelve un apikey, y con eso ya podes mandarte mensajes vos mismo.
    phone = config.get("whatsapp_phone")   # ej "5493511234567" (con codigo pais, sin +)
    apikey = config.get("whatsapp_apikey")
    if not phone or not apikey:
        print("[whatsapp] no configurado, salteo")
        return
    try:
        resp = requests.get(
            "https://api.callmebot.com/whatsapp.php",
            params={"phone": phone, "text": message, "apikey": apikey},
            timeout=10,
        )
        print(f"[whatsapp] status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[whatsapp] EXCEPCION: {e}")


def trigger_local_alarm(config: dict):
    # Lanza la alarma en un PROCESO separado (no thread) para que quede
    # sonando aunque este script termine (--once / tarea programada corta).
    alarm_script = BASE_DIR / "alarm.py"
    try:
        subprocess.Popen(
            [sys.executable, str(alarm_script)],
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
        )
        print("[alarma] disparada en proceso separado")
    except Exception as e:
        print(f"[alarma] EXCEPCION: {e}")


def check_once(config: dict) -> bool:
    """Retorna True si detecto un cambio de IP y disparo alertas."""
    current_ip = get_public_ip()
    if not current_ip:
        print(f"[{datetime.now()}] no pude obtener la IP publica (sin internet?)")
        return False

    last_ip = get_last_known_ip()

    if last_ip is None:
        # Primera corrida: solo guarda el baseline, no alerta
        save_ip(current_ip)
        print(f"[{datetime.now()}] baseline inicial: {current_ip}")
        return False

    if current_ip != last_ip:
        msg = (
            f"⚠️ IP PUBLICA CAMBIO — Verge / Binance\n"
            f"Anterior: {last_ip}\n"
            f"Nueva:    {current_ip}\n"
            f"Actualiza la whitelist de la API key en Binance YA, "
            f"o el agente va a dejar de poder ejecutar trades."
        )
        print(f"[{datetime.now()}] {msg}")
        save_ip(current_ip)
        send_telegram(config, msg)
        send_whatsapp(config, msg)
        trigger_local_alarm(config)
        return True

    print(f"[{datetime.now()}] IP sin cambios ({current_ip})")
    return False


def main():
    config = load_config()
    once = "--once" in sys.argv

    if once:
        check_once(config)
        return

    print(f"Monitor de IP arrancado. Chequeando cada {INTERVAL_SECONDS}s. Ctrl+C para salir.")
    while True:
        try:
            check_once(config)
        except Exception as e:
            print(f"[ERROR inesperado] {e}")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
