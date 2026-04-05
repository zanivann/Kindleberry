import psutil, requests, time, glob, os
from gpiozero import PWMOutputDevice

MASTER_URL = "http://192.168.0.10:5000/report"

def get_fan_device():
    """Inicialização resiliente para RPi 5."""
    test_pins = [18, 13, 12]
    for pin in test_pins:
        try:
            print(f"Tentando inicializar ventoinha no GPIO {pin}...")
            device = PWMOutputDevice(pin, frequency=100)
            print(f"Sucesso no GPIO {pin}!")
            return device, pin
        except Exception as e:
            print(f"Falha no GPIO {pin}: {e}")
            continue
    return None, None

# Inicialização Robusta do Hardware (Ventoinha)
fan, active_pin = get_fan_device()
if not fan:
    print("Sr., não foi possível controlar a ventoinha em nenhum pino.")

# --- VARREDURA DO SENSOR DE TEMPERATURA 1-WIRE ---
active_sensor_path = None

def get_temp_sensor():
    """Identifica e fixa o caminho do sensor DS18B20 no sysfs."""
    try:
        base_dir = '/sys/bus/w1/devices/'
        folders = glob.glob(base_dir + '28*')
        if folders:
            sensor_path = folders[0]
            sensor_id = sensor_path.split('/')[-1]
            print(f"Sucesso! Sensor térmico 1-Wire detectado ({sensor_id}).")
            return sensor_path
    except Exception as e:
        print(f"Erro na leitura do barramento 1-Wire: {e}")
    
    print("Atenção, Sr. Nenhum sensor 1-Wire encontrado.")
    return None

# Fixa o sensor na inicialização
active_sensor_path = get_temp_sensor()
# -------------------------------------------------

fan_temp_min, fan_temp_max = 35.0, 50.0
node_permission = "none"

def get_core_temp():
    """Extrai a temperatura interna do SoC do Slave."""
    try:
        temps = psutil.sensors_temperatures()
        if 'cpu_thermal' in temps: return temps['cpu_thermal'][0].current
        if 'bcm2835_thermal' in temps: return temps['bcm2835_thermal'][0].current
    except: pass
    return 0.0

def get_rack_temp():
    """Lê a temperatura a partir do sensor fixado."""
    if not active_sensor_path: 
        return None
    try:
        with open(active_sensor_path + '/w1_slave', 'r') as f:
            lines = f.readlines()
            if 'YES' not in lines[0]: return None
            return float(lines[1][lines[1].find('t=')+2:]) / 1000.0
    except: return None

def update_fan_speed(current_temp):
    global fan_temp_min, fan_temp_max
    if not fan: return
    
    # Se a leitura do sensor falhar (None ou 0.0), gira em 100% por segurança
    if current_temp is None or current_temp == 0.0: 
        fan.value = 1.0; return 
    
    limit_off = fan_temp_min - 10.0
    
    if current_temp <= limit_off:
        fan.value = 0.0  # Desliga totalmente
    elif current_temp <= fan_temp_min:
        fan.value = 0.2  # Rotação mínima de segurança (20%)
    elif current_temp >= fan_temp_max:
        fan.value = 1.0  # Rotação máxima
    else:
        # Rampa de aceleração proporcional
        ramp = (current_temp - fan_temp_min) / (fan_temp_max - fan_temp_min)
        fan.value = 0.2 + (0.8 * ramp)

print(f"Agente V4.7.1 iniciado. Pino Ativo: {active_pin}")

last_net_io = psutil.net_io_counters()
last_net_time = time.time()

try:
    while True:
        temp_rack = get_rack_temp()
        temp_core = get_core_temp()
        report_temp_rack = temp_rack if temp_rack is not None else 0.0

        now = time.time()
        io_now = psutil.net_io_counters()
        dt = now - last_net_time
        if dt > 0:
            net_down = (io_now.bytes_recv - last_net_io.bytes_recv) / dt / 1024
            net_up = (io_now.bytes_sent - last_net_io.bytes_sent) / dt / 1024
        else: net_down, net_up = 0.0, 0.0
        last_net_io, last_net_time = io_now, now

        payload = {
            "cpu": psutil.cpu_percent(), 
            "ram": psutil.virtual_memory().percent, 
            "temp": report_temp_rack, 
            "core_temp": temp_core,
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
        except Exception as e:
            print(f"✗ Falha na comunicação: {e}"); node_permission = "none"

        # Controle local baseado na permissão do Master
        if node_permission == "slave":
            update_fan_speed(temp_rack)
        else:
            if fan: fan.value = 0.0
        
        time.sleep(5)
except KeyboardInterrupt:
    if fan: fan.value = 1.0 # Garante ventilação ao encerrar o script