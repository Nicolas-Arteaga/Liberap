"""
Alarma que suena en loop hasta que alguien la apaga a mano.
Se lanza como proceso separado desde ip_monitor.py cuando detecta
un cambio de IP publica.
"""
import sys
import threading
import tkinter as tk
import winsound

stop_flag = threading.Event()


def beep_loop():
    while not stop_flag.is_set():
        # Beep de sistema, no depende de ningun archivo .wav externo
        winsound.Beep(1200, 400)
        winsound.Beep(900, 400)
        if stop_flag.wait(timeout=0.3):
            break


def main():
    root = tk.Tk()
    root.title("VERGE - IP CAMBIO")
    root.attributes("-topmost", True)
    root.configure(bg="#b30000")
    root.geometry("480x220+400+300")
    root.resizable(False, False)

    label = tk.Label(
        root,
        text="⚠️  LA IP PUBLICA CAMBIO  ⚠️\n\nActualiza la whitelist de la\nAPI key en Binance AHORA",
        fg="white",
        bg="#b30000",
        font=("Segoe UI", 14, "bold"),
        justify="center",
    )
    label.pack(expand=True, fill="both", padx=20, pady=20)

    def on_stop():
        stop_flag.set()
        root.destroy()

    stop_btn = tk.Button(
        root,
        text="APAGAR ALARMA",
        command=on_stop,
        font=("Segoe UI", 12, "bold"),
        bg="white",
        fg="#b30000",
        height=2,
    )
    stop_btn.pack(pady=10, padx=20, fill="x")

    root.protocol("WM_DELETE_WINDOW", on_stop)

    t = threading.Thread(target=beep_loop, daemon=True)
    t.start()

    root.mainloop()
    sys.exit(0)


if __name__ == "__main__":
    main()
