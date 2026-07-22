# Monitor de IP publica (alerta Telegram + WhatsApp + alarma sonora)

Binance no deja actualizar la whitelist de IP de una API key via API
(es intencional, es la unica barrera si te roban la key). Esto no
automatiza el update — te avisa lo mas fuerte posible apenas la IP
publica cambia, para que lo actualices vos a mano en Binance antes de
perder trades.

## 1. Setup Telegram (gratis, ~2 min)

1. Hablale a **@BotFather** en Telegram, mandale `/newbot`, seguile los pasos.
   Te da un `bot_token` (algo como `123456:ABC-DEF...`).
2. Buscá tu bot recien creado y mandale cualquier mensaje (ej "hola").
3. Abri en el navegador: `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
   y ahi vas a ver tu `chat_id` (numero) en la respuesta JSON.

## 2. Setup WhatsApp via CallMeBot (gratis, sin cuenta business)

1. Agenda este numero en tu WhatsApp: **+34 644 59 71 65**
2. Mandale por WhatsApp exactamente: `I allow callmebot to send me messages`
3. Te responde con tu `apikey` (un numero).
4. Tu `whatsapp_phone` es tu propio numero con codigo de pais, sin `+`
   (ej `5493511234567`).

## 3. Configurar

```
cp config.example.json config.json
```

Completa `config.json` con los 4 valores de arriba.

```
pip install requests
```

(tkinter y winsound ya vienen con Python en Windows, no hace falta instalar nada mas.)

## 4. Probar que funciona

```
python ip_monitor.py --once
```

La primera corrida solo guarda la IP actual como baseline (no alerta,
no tiene con que comparar). Para forzar una alerta de prueba, editá a
mano `last_ip.txt` y poné cualquier IP distinta a la tuya, despues
corré `--once` de nuevo — te tiene que llegar Telegram, WhatsApp, y
abrir la ventana con alarma sonora.

## 5. Dejarlo corriendo solo (Windows Task Scheduler)

Mejor que dejar una consola abierta: crear una tarea programada que
corra `python ip_monitor.py --once` cada 5 minutos.

1. Abrí "Programador de tareas" (Task Scheduler) de Windows.
2. Crear tarea basica → Desencadenador: "Diariamente", repetir cada
   5 minutos durante 1 dia (indefinidamente).
3. Accion: iniciar programa
   - Programa: ruta completa a tu `python.exe`
     (ej `C:\Users\Nicolas\AppData\Local\Programs\Python\Python311\python.exe`)
   - Argumentos: `ip_monitor.py --once`
   - Iniciar en: la carpeta `tools\ip_alert` de este repo.
4. Marcar "Ejecutar tanto si el usuario inicio sesion como si no" si
   queres que corra aunque no estes logueado.

Con esto, apenas la IP cambie (router, corte de luz, ISP renovando
DHCP, etc.) vas a tener Telegram + WhatsApp + una ventana roja con
alarma sonando en loop hasta que apretes "APAGAR ALARMA".
