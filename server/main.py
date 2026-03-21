import psutil
import socket
import requests
import io
import datetime
import time
import json
import os
import glob
import threading
import traceback
from flask import Flask, send_file, request, render_template, redirect
from PIL import Image, ImageDraw, ImageFont, ImageOps
from w1thermsensor import W1ThermSensor

# --- ESTADO GLOBAL ---
latest_sensor_data = {"temp": "--", "hum": "--", "ext_temp": "--"}
DASH_ACTIVE = True
CURRENT_LANG = {} 
last_net_io, last_net_time, net_history = None, 0, []
MAX_HISTORY = 120 

# ESTADO DO SLAVE
slave_data = {
    "last_seen": 0, "cpu": 0, "ram": 0, "temp": 0.0, "fan": None, "net_history": []
}

try:
    from dht_reader import DHTReader
    # Corrigido para pino 4 para evitar conflito com o DS18B20 no 17
    sensor_client = DHTReader("DHT22", "/dev/gpiochip4", 4)
except Exception:
    sensor_client = None

try:
    ds_sensor = W1ThermSensor()
except Exception:
    ds_sensor = None

def update_sensor_background():
    global latest_sensor_data
    while True:
        if sensor_client:
            try:
                h, t_val, _ = sensor_client.read_data()
                if t_val is not None:
                    latest_sensor_data["temp"] = f"{t_val:.1f}"
                    latest_sensor_data["hum"] = f"{h:.1f}"
            except Exception: pass
            
        if ds_sensor:
            try:
                latest_sensor_data["ext_temp"] = f"{ds_sensor.get_temperature():.1f}"
            except Exception: pass
            
        time.sleep(15)

app = Flask(__name__)
CONFIG_FILE = 'config.json'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ICONS_DIR = os.path.join(BASE_DIR, "icons")
if not os.path.exists(ICONS_DIR): os.makedirs(ICONS_DIR)

def load_config():
    default = {
        "rotation": 1, "font_size": 120, "city_name": "Sao Paulo", 
        "timezone": "America/Sao_Paulo", "lat": "-23.5505", "lon": "-46.6333", 
        "dark_mode": False, "brightness": 10,
        "sensor_main": "online", "sensor_ext": "none"
    }
    if not os.path.exists(CONFIG_FILE): return default
    try:
        with open(CONFIG_FILE, 'r') as f:
            c = json.load(f)
            for k, v in default.items():
                if k not in c: c[k] = v
            return c
    except: return default

def save_config(data):
    with open(CONFIG_FILE, 'w') as f: json.dump(data, f, indent=4)

def load_translation_file():
    global CURRENT_LANG
    conf = load_config()
    lang = conf.get('language', 'pt_BR')
    path = os.path.join(BASE_DIR, 'locale', f'{lang}.json')
    if not os.path.exists(path): path = os.path.join(BASE_DIR, 'locale', 'pt_BR.json')
    try:
        with open(path, 'r', encoding='utf-8') as f: CURRENT_LANG = json.load(f)
    except: CURRENT_LANG = {}
    return CURRENT_LANG

def t(key): return CURRENT_LANG.get(key, key)

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except: return "Offline"

def get_rpi_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f: return float(f.read()) / 1000.0
    except: return 0.0

def get_fan_speed():
    try:
        for path in glob.glob("/sys/class/hwmon/hwmon*/fan*_input"):
            with open(path, "r") as f: return int(f.read().strip())
    except: pass
    return None

def get_moon_phase():
    try:
        diff = datetime.datetime.now() - datetime.datetime(2000, 1, 6, 18, 14, 0)
        index = int((diff.total_seconds() / 86400 % 29.530588) / 29.530588 * 8) % 8
        icons = ["moon_new", "moon_waxing_crescent", "moon_first_quarter", "moon_waxing_gibbous", "moon_full", "moon_waning_gibbous", "moon_last_quarter", "moon_waning_crescent"]
        phases = ["m_new", "m_wax_cresc", "m_first_q", "m_wax_gib", "m_full", "m_wan_gib", "m_last_q", "m_wan_cresc"]
        return icons[index], phases[index]
    except: return "moon_full", "m_full"

def update_net_stats():
    global last_net_io, last_net_time, net_history
    now, io_now = time.time(), psutil.net_io_counters()
    down, up = 0, 0
    if last_net_io:
        dt = now - last_net_time
        if dt > 0:
            down = (io_now.bytes_recv - last_net_io.bytes_recv) / dt / 1024
            up = (io_now.bytes_sent - last_net_io.bytes_sent) / dt / 1024
    last_net_io, last_net_time = io_now, now
    net_history.append((down, up))
    if len(net_history) > MAX_HISTORY: net_history.pop(0)
    return down, up

def get_weather(lat, lon):
    API_KEY = "4df7b3293f31480b96c115457261002"
    try:
        url = f"http://api.weatherapi.com/v1/current.json?key={API_KEY}&q={lat},{lon}&lang=pt"
        r = requests.get(url, timeout=3).json()
        curr = r['current']
        temp = curr['temp_c']
        cond_text = curr['condition']['text']
        code = curr['condition']['code']
        is_day = curr['is_day']
        icon_url = "https:" + curr['condition']['icon']
        icon_map = {
            1000: "sun", 1003: "cloudy_sun", 1006: "cloudy", 1009: "cloudy",
            1030: "mist", 1063: "rain_light", 1183: "rain_light", 1189: "rain",
            1195: "rain_heavy", 1240: "rain_light", 1273: "storm",
        }
        icon_name = icon_map.get(code, "cloudy")
        if is_day == 0:
            if icon_name == "sun": icon_name = "moon"
            if icon_name == "cloudy_sun": icon_name = "cloudy_moon"
        return temp, cond_text, icon_name, is_day, icon_url
    except:
        return "--", "Erro API", "cloudy", 1, None

# --- FUNÇÕES DE DESENHO CORRIGIDAS ---
def draw_sparkline(draw, x, y, w, h, data, label, font_val, font_axis, color):
    draw.line((x, y, x, y+h), fill=color, width=3)
    draw.line((x, y+h, x+w, y+h), fill=color, width=3)
    step_x = w / (MAX_HISTORY - 1)
    if data:
        max_v = max(data) if max(data) > 10 else 10
        y_lbl = f"{max_v/1024:.1f}M" if max_v > 1024 else f"{int(max_v)}K"
        # Ajustado: font= explicitamente
        draw.text((x - 10, y), y_lbl, font=font_axis, fill=color, anchor="rm")
        points = [(x + (i * step_x), (y + h) - ((val / max_v) * h)) for i, val in enumerate(data)]
        if len(points) > 1: draw.line(points, fill=color, width=3)
        curr = data[-1]
        val_str = f"{curr/1024:.1f} MB/s" if curr > 1024 else f"{int(curr)} KB/s"
        # Ajustado: font= explicitamente
        draw.text((x, y-35), f"{label}: {val_str}", font=font_val, fill=color)

def draw_gauge(draw, x, y, radius, percent, label, font_val, font_label, color):
    start, end = 135, 405
    curr = start + ((end - start) * (percent / 100))
    draw.arc([x-radius, y-radius, x+radius, y+radius], start=start, end=end, fill=color, width=3)
    draw.arc([x-radius, y-radius, x+radius, y+radius], start=start, end=curr, fill=color, width=16 if radius > 80 else 10)
    # Ajustado: font= explicitamente
    draw.text((x, y), f"{int(percent)}%", font=font_val, fill=color, anchor="mm")
    draw.text((x, y+radius+40), label, font=font_label, fill=color, anchor="mm")

# --- ROTAS ---
@app.route('/report', methods=['POST'])
def report():
    global slave_data
    if request.is_json:
        data = request.get_json()
        slave_data["cpu"] = data.get("cpu", 0)
        slave_data["ram"] = data.get("ram", 0)
        slave_data["temp"] = data.get("temp", 0.0)
        slave_data["fan"] = data.get("fan")
        slave_data["net_history"].append((data.get("net_down", 0), data.get("net_up", 0)))
        if len(slave_data["net_history"]) > MAX_HISTORY: slave_data["net_history"].pop(0)
        slave_data["last_seen"] = time.time()
    return "OK"

@app.route('/dashboard.png')
def serve_dashboard():
    try:
        kindle_bat = request.args.get('kbat')

        conf, tr_data = load_config(), load_translation_file()
        W, H = 1448, 1072
        BG, FG = (0, 255) if conf.get('dark_mode') else (255, 0)
        img = Image.new('L', (W, H), BG)
        draw = ImageDraw.Draw(img)

        f_p = os.path.join(BASE_DIR, "fonts", "Roboto-Bold.ttf")
        f_huge = ImageFont.truetype(f_p, conf.get('font_size', 120))
        f_city = ImageFont.truetype(f_p, 90)
        f_med = ImageFont.truetype(f_p, 40)
        f_graph = ImageFont.truetype(f_p, 32)
        f_tiny = ImageFont.truetype(f_p, 24)

        sensor_main = conf.get('sensor_main', 'online')
        sensor_ext = conf.get('sensor_ext', 'none')

        temp_on, cond_txt, w_icon, is_day, w_url = "--", "", "cloudy", 1, None
        
        if "online" in [sensor_main, sensor_ext] or (sensor_main == "none" and sensor_ext == "none"):
            temp_on, cond_txt, w_icon, is_day, w_url = get_weather(conf['lat'], conf['lon'])

        def get_sensor_data(s_type):
            if s_type == "online": 
                return temp_on, None, cond_txt
            if s_type == "dht": 
                return latest_sensor_data["temp"], latest_sensor_data["hum"], t("lbl_sensor_local")
            if s_type == "ds18": 
                return latest_sensor_data.get("ext_temp", "--"), None, t("lbl_sensor_ext")
            return None, None, None

        temp_main, hum_main, status_main = get_sensor_data(sensor_main)
        temp_sec, _, status_sec = get_sensor_data(sensor_ext)

        if not temp_main: 
            temp_main = "--"
            status_main = t("lbl_no_data")

        update_net_stats()
        now = datetime.datetime.now()
        moon_icon, moon_key = get_moon_phase()

        # Desenho Esquerda
        draw.text((60, 60), now.strftime("%H:%M"), font=f_huge, fill=FG)
        draw.text((60, 220), f"{t(f'day_{now.weekday()}')}, {now.strftime('%d/%m')}", font=f_med, fill=FG)
        draw.text((60, 320), conf.get('city_name', 'Dashboard'), font=f_city, fill=FG)
        
        # Temperatura Principal (Interno/Main)
        draw.text((60, 520), f"{temp_main}°C", font=f_huge, fill=FG)
        
        y_cursor = 620
        # Temperatura Secundária (Externo/Ext)
        if sensor_ext != "none" and temp_sec:
            draw.text((60, y_cursor), f"Ext: {temp_sec}°C", font=f_med, fill=FG)
            y_cursor += 60
            
        # Umidade
        if hum_main and hum_main != "--":
            draw.text((60, y_cursor), f"{t('lbl_humidity')}: {hum_main}%", font=f_med, fill=FG)
            y_cursor += 60
            
        draw.text((60, y_cursor), status_main, font=f_med if not hum_main else f_tiny, fill=FG)

        # Ícones
        if "online" in [sensor_main, sensor_ext]:
            moon_path = os.path.join(BASE_DIR, "icons", f"{moon_icon}.png")
            if os.path.exists(moon_path):
                m_img = Image.open(moon_path).convert("RGBA").resize((100, 100))
                m_bg = Image.new("RGBA", m_img.size, (BG, BG, BG, 255))
                m_bg.alpha_composite(m_img)
                m_final = m_bg.convert("L")
                if conf.get('dark_mode'): m_final = ImageOps.invert(m_final)
                img.paste(m_final, (610, 50))
                draw.text((660, 160), t(moon_key), font=f_tiny, fill=FG, anchor="mt")
    
            i_path = os.path.join(BASE_DIR, "icons", f"{w_icon}.png")
            if not os.path.exists(i_path) and w_url:
                try:
                    r_icon = requests.get(w_url, timeout=5)
                    if r_icon.status_code == 200:
                        with open(i_path, 'wb') as f: f.write(r_icon.content)
                except: pass
    
            if not os.path.exists(i_path):
                if "_" in w_icon: i_path = os.path.join(BASE_DIR, "icons", f"{w_icon.split('_')[-1]}.png")
                if not os.path.exists(i_path): i_path = os.path.join(BASE_DIR, "icons", "cloudy.png")
    
            if os.path.exists(i_path):
                i_img = Image.open(i_path).convert("RGBA").resize((320, 320))
                i_bg = Image.new("RGBA", i_img.size, (BG, BG, BG, 255))
                i_bg.alpha_composite(i_img)
                i_final = i_bg.convert("L")
                if conf.get('dark_mode'): i_final = ImageOps.invert(i_final)
                img.paste(i_final, (60, 740))

        # Desenho Direita - Adaptativo e Redimensionado
        draw.line((724, 50, 724, 1022), fill=FG, width=4)
        cx = 1086
        fan_rpm = get_fan_speed()

        if time.time() - slave_data["last_seen"] < 60:
            draw_gauge(draw, cx - 160, 165, 85, psutil.cpu_percent(), "MASTER CPU", f_graph, f_tiny, FG)
            draw_gauge(draw, cx + 160, 165, 85, psutil.virtual_memory().percent, "MASTER RAM", f_graph, f_tiny, FG)
            draw_sparkline(draw, 780, 330, 600, 70, [x[0] for x in net_history], "M-Down", f_tiny, f_tiny, FG)
            draw_sparkline(draw, 780, 460, 600, 70, [x[1] for x in net_history], "M-Up", f_tiny, f_tiny, FG)
            
            draw.line((740, 560, 1428, 560), fill=FG, width=2)

            draw_gauge(draw, cx - 160, 680, 85, slave_data['cpu'], "SLAVE CPU", f_graph, f_tiny, FG)
            draw_gauge(draw, cx + 160, 680, 85, slave_data['ram'], "SLAVE RAM", f_graph, f_tiny, FG)
            draw_sparkline(draw, 780, 830, 600, 70, [x[0] for x in slave_data['net_history']], "S-Down", f_tiny, f_tiny, FG)
            draw_sparkline(draw, 780, 960, 600, 70, [x[1] for x in slave_data['net_history']], "S-Up", f_tiny, f_tiny, FG)
            
            m_hw = f"M: {get_rpi_temp():.1f}°C"
            if fan_rpm: m_hw += f" | {fan_rpm}RPM"
            draw.text((740, 525), m_hw, font=f_tiny, fill=FG)
            
            s_hw = f"S: {slave_data['temp']:.1f}°C"
            if slave_data['fan']: s_hw += f" | {slave_data['fan']}RPM"
            draw.text((740, 1025), s_hw, font=f_tiny, fill=FG)
        else:
            draw_gauge(draw, cx - 180, 250, 130, psutil.cpu_percent(), t("lbl_cpu"), f_med, f_med, FG)
            draw_gauge(draw, cx + 180, 250, 130, psutil.virtual_memory().percent, t("lbl_ram"), f_med, f_med, FG)
            draw_sparkline(draw, 780, 530, 600, 100, [x[0] for x in net_history], t("lbl_down"), f_graph, f_tiny, FG)
            draw_sparkline(draw, 780, 730, 600, 100, [x[1] for x in net_history], t("lbl_up"), f_graph, f_tiny, FG)
            hw_info = f"CPU: {get_rpi_temp():.1f}°C"
            if fan_rpm is not None: hw_info += f" | FAN: {fan_rpm} RPM"
            draw.text((cx, 920), hw_info, font=f_med, fill=FG, anchor="mm")

        footer_text = f"IP: {get_ip()}"
        if kindle_bat: footer_text += f" | Kindle: {kindle_bat}%"
        footer_text += f" | {now.strftime('%H:%M:%S')}"
        draw.text((1400, 1040), footer_text, font=f_tiny, fill=FG, anchor="rb")

        if conf.get('rotation') in [1, 3]: img = img.rotate(90, expand=True)
        elif conf['rotation'] == 2: img = img.rotate(180)
        
        buf = io.BytesIO()
        img.save(buf, 'PNG'); buf.seek(0)
        response = send_file(buf, mimetype='image/png')
        response.headers['X-Brightness'] = str(conf.get('brightness', 10))
        return response
    except:
        traceback.print_exc()
        return "Erro", 500

@app.route('/update', methods=['POST'])
def update():
    c = load_config()
    for k in ['city_name', 'timezone', 'lat', 'lon']:
        if k in request.form: c[k] = request.form[k]
    
    if 'brightness' in request.form: c['brightness'] = int(request.form['brightness'])
    
    c['rotation'] = int(request.form.get('rotation', 1))
    c['font_size'] = int(request.form.get('font_size', 120))
    c['dark_mode'] = 'dark_mode' in request.form
    
    if 'sensor_main' in request.form: c['sensor_main'] = request.form['sensor_main']
    if 'sensor_ext' in request.form: c['sensor_ext'] = request.form['sensor_ext']

    save_config(c)
    return redirect('/')

@app.route('/toggle_status', methods=['POST'])
def toggle_status():
    global DASH_ACTIVE
    DASH_ACTIVE = not DASH_ACTIVE
    return redirect('/')

@app.route('/check_status')
def check_status():
    return "RUN" if DASH_ACTIVE else "STOP"

@app.route('/')
def index():
    return render_template('index.html', config=load_config(), tr=load_translation_file(), dash_active=DASH_ACTIVE)

if __name__ == '__main__':
    threading.Thread(target=update_sensor_background, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, threaded=True)