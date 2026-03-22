import psutil
import requests
import time
import glob
from gpiozero import PWMOutputDevice

# --- CONFIGURAÇÃO DA REDE ---
MASTER_URL = "http://192.168.0.10:5000/report"

# --- CONFIGURAÇÃO FÍSICA ---
FAN_PIN = 18
try:
    fan = PWMOutputDevice(FAN_PIN, frequency=100)
    print(f"Controle PWM iniciado no GPIO {FAN_PIN}.")
except Exception as e:
    print(f"Erro GPIO: {e}. O controle físico está inoperante. 🙄")
    fan = None

# Limites dinâmicos (sobrescritos pelo Master)
fan_temp_min = 35.0
fan_temp_max = 50.0

def get_rack_temp():
    try:
        base_dir = '/sys/bus/w1/devices/'
        device_folder = glob.glob(base_dir + '28*')[0]
        device_file = device_folder + '/w1_slave'
        
        with open(device_file, 'r') as f:
            lines = f.readlines()
            if lines[0].strip()[-3:] != 'YES':
                return None
            temp_string = lines[1].find('t=')
            if temp_string != -1:
                return float(lines[1][temp_string+2:]) / 1000.0
    except:
        return None

def update_fan_speed(current_temp):
    global fan_temp_min, fan_temp_max
    if not fan: return
    
    if current_temp is None:
        fan.value = 1.0 # Segurança ativada
        return

    if current_temp >= fan_temp_max:
        fan.value = 1.0
    elif current_temp <= fan_temp_min:
        fan.value = 0.2 # Piso silencioso da Noctua
    else:
        fan.value = 0.2 + (0.8 * ((current_temp - fan_temp_min) / (fan_temp_max - fan_temp_min)))

last_io = psutil.net_io_counters()
last_t = time.time()

print("Agente (Slave) operando. Aguardando diretrizes do Master...")

try:
    while True:
        time.sleep(5)
        now = time.time()
        curr_io = psutil.net_io_counters()
        dt = now - last_t
        
        down = (curr_io.bytes_recv - last_io.bytes_recv) / dt / 1024
        up = (curr_io.bytes_sent - last_io.bytes_sent) / dt / 1024
        last_io, last_t = curr_io, now

        # 1. Lê os dados físicos locais
        current_temp = get_rack_temp()
        
        # 2. Executa a ação mecânica
        update_fan_speed(current_temp)

        # Fallback de telemetria caso o DS18B20 morra
        report_temp = current_temp
        if report_temp is None:
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    report_temp = float(f.read()) / 1000.0
            except: report_temp = 0.0

        payload = {
            "cpu": psutil.cpu_percent(),
            "ram": psutil.virtual_memory().percent,
            "temp": report_temp,
            "fan": None, # Sem fio tacômetro na leitura atual
            "net_down": down,
            "net_up": up
        }
        
        # 3. Comunica-se com a base e atualiza o protocolo
        try:
            response = requests.post(MASTER_URL, json=payload, timeout=2)
            if response.status_code == 200:
                config = response.json()
                if 'fan_temp_min' in config: fan_temp_min = float(config['fan_temp_min'])
                if 'fan_temp_max' in config: fan_temp_max = float(config['fan_temp_max'])
        except: 
            pass # Falha na rede. O hardware continuará usando os últimos limites válidos.
            
except KeyboardInterrupt:
    if fan: fan.value = 1.0
    print("\nScript abortado. Ventoinha fixada em 100% por segurança.")