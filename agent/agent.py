import psutil, requests, time, glob, os
from gpiozero import PWMOutputDevice

MASTER_URL = "http://192.168.0.10:5000/report"
FAN_PIN = 18

try:
    fan = PWMOutputDevice(FAN_PIN, frequency=100)
    print(f"✓ Hardware OK. Aguardando Master...")
except Exception as e:
    print(f"✗ Erro GPIO: {e}")
    fan = None

fan_temp_min, fan_temp_max = 35.0, 50.0
node_permission = "none"

def get_rack_temp():
    try:
        base_dir = '/sys/bus/w1/devices/'
        folders = glob.glob(base_dir + '28*')
        if not folders: return None
        with open(folders[0] + '/w1_slave', 'r') as f:
            lines = f.readlines()
            if 'YES' not in lines[0]: return None
            return float(lines[1][lines[1].find('t=')+2:]) / 1000.0
    except: return None

def update_fan_speed(current_temp):
    global fan_temp_min, fan_temp_max
    if not fan: return
    if current_temp is None: 
        fan.value = 1.0; return
    
    # LÓGICA DE CORTE: Se temp <= (mínimo - 10), desliga (0.0)
    limit_off = fan_temp_min - 10.0
    
    if current_temp >= fan_temp_max:
        fan.value = 1.0
    elif current_temp <= limit_off:
        fan.value = 0.0
    elif current_temp <= fan_temp_min:
        fan.value = 0.2
    else:
        fan.value = 0.2 + (0.8 * ((current_temp - fan_temp_min) / (fan_temp_max - fan_temp_min)))

print("Agente iniciado. Iniciando loop de telemetria...")

# Variáveis para cálculo de rede
last_net_io = psutil.net_io_counters()
last_net_time = time.time()

try:
    while True:
        temp = get_rack_temp()
        report_temp = temp if temp is not None else 0.0

        # Cálculo de rede do Slave
        now = time.time()
        io_now = psutil.net_io_counters()
        dt = now - last_net_time
        
        if dt > 0:
            net_down = (io_now.bytes_recv - last_net_io.bytes_recv) / dt / 1024
            net_up = (io_now.bytes_sent - last_net_io.bytes_sent) / dt / 1024
        else:
            net_down, net_up = 0.0, 0.0
            
        last_net_io, last_net_time = io_now, now

        # Payload com o status atual atualizado
        payload = {
            "cpu": psutil.cpu_percent(), 
            "ram": psutil.virtual_memory().percent, 
            "temp": report_temp, 
            "fan": int(fan.value * 100) if fan else 0,
            "net_down": net_down,
            "net_up": net_up
        }
        
        try:
            r = requests.post(MASTER_URL, json=payload, timeout=2)
            if r.status_code == 200:
                conf = r.json()
                fan_temp_min = float(conf.get('fan_temp_min', 35.0))
                fan_temp_max = float(conf.get('fan_temp_max', 50.0))
                node_permission = conf.get('fan_node', 'none')
                
                print(f"📡 Master -> Min: {fan_temp_min} | Max: {fan_temp_max} | Nó: {node_permission} | Rede: {net_down:.1f}↓ {net_up:.1f}↑ KB/s")
        except Exception as e:
            print(f"✗ Falha na conexão: {e}")
            node_permission = "none"

        if node_permission == "slave":
            update_fan_speed(temp)
            print(f"⚙️ Atuador -> Temp: {report_temp}°C | Fan: {int(fan.value*100)}%")
        else:
            if fan: fan.value = 0.0
        
        time.sleep(5)
except KeyboardInterrupt:
    if fan: fan.value = 1.0