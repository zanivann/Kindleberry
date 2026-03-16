import psutil
import requests
import time
import glob

# --- CONFIGURAÇÃO ---
# Coloque o IP do seu servidor PRINCIPAL (o que gera a imagem)
MASTER_URL = "http://192.168.0.10:5000/report"

def get_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read()) / 1000.0
    except: return 0.0

def get_fan():
    try:
        for p in glob.glob("/sys/class/hwmon/hwmon*/fan*_input"):
            with open(p, "r") as f: return int(f.read().strip())
    except: pass
    return None

last_io = psutil.net_io_counters()
last_t = time.time()

print("Agente iniciado. Enviando telemetria para o Master...")

while True:
    time.sleep(5)
    now = time.time()
    curr_io = psutil.net_io_counters()
    dt = now - last_t
    
    down = (curr_io.bytes_recv - last_io.bytes_recv) / dt / 1024
    up = (curr_io.bytes_sent - last_io.bytes_sent) / dt / 1024
    last_io, last_t = curr_io, now

    payload = {
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent,
        "temp": get_temp(),
        "fan": get_fan(),
        "net_down": down,
        "net_up": up
    }
    
    try:
        requests.post(MASTER_URL, json=payload, timeout=2)
    except: pass # Falha silenciosa se o Master cair.