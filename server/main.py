import psutil
import socket
import requests
import io
import datetime
import time
import json
import os
import glob
import math
from flask import Flask, send_file, request, render_template, redirect
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
SERVER_VERSION = "1.3.1"
CONFIG_FILE = 'config.json'
DASH_ACTIVE = True
CURRENT_LANG = {} # Dicionário que guarda as traduções carregadas

# --- GLOBAIS ---
last_net_io = None
last_net_time = 0
net_history = [] 
MAX_HISTORY = 120 

DEFAULT_CONFIG = {
    "language": "pt_BR",
    "rotation": 1,
    "font_size": 120,
    "city_name": "Sao Paulo",
    "timezone": "America/Sao_Paulo",
    "lat": "-23.5505",
    "lon": "-46.6333",
    "dark_mode": False
}

def load_config():
    if not os.path.exists(CONFIG_FILE): return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r') as f:
            c = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in c: c[k] = v
            return c
    except: return DEFAULT_CONFIG

def save_config(data):
    with open(CONFIG_FILE, 'w') as f: json.dump(data, f, indent=4)

# --- SISTEMA DE TRADUÇÃO ---
def load_translation_file():
    global CURRENT_LANG
    conf = load_config()
    lang_code = conf.get('language', 'pt_BR')
    
    path = f"locale/{lang_code}.json"
    if not os.path.exists(path):
        path = "locale/pt_BR.json" # Fallback
        
    try:
        with open(path, 'r', encoding='utf-8') as f:
            CURRENT_LANG = json.load(f)
    except:
        CURRENT_LANG = {}

def t(key):
    """Retorna o texto traduzido ou a própria chave se não encontrar"""
    return CURRENT_LANG.get(key, key)

def setup_timezone():
    conf = load_config()
    tz = conf.get('timezone', 'UTC')
    os.environ['TZ'] = tz
    try:
        time.tzset()
    except: pass

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except: return "Offline"

# --- ASTRONOMIA ---
def get_moon_phase():
    try:
        now = datetime.datetime.now()
        ref_date = datetime.datetime(2000, 1, 6, 18, 14, 0)
        diff = now - ref_date
        days = diff.total_seconds() / 86400
        lunation = 29.53058867
        moon_age = days % lunation
        index = int((moon_age / lunation) * 8) % 8
        
        phases = [
            ("moon_new", "m_new"),
            ("moon_waxing_crescent", "m_wax_cresc"),
            ("moon_first_quarter", "m_first_q"),
            ("moon_waxing_gibbous", "m_wax_gib"),
            ("moon_full", "m_full"),
            ("moon_waning_gibbous", "m_wan_gib"),
            ("moon_last_quarter", "m_last_q"),
            ("moon_waning_crescent", "m_wan_cresc")
        ]
        return phases[index]
    except:
        return ("moon_full", "m_full")

# --- HARDWARE ---
def get_rpi_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read()) / 1000.0
    except:
        return 0.0

def get_fan_speed():
    try:
        fan_files = glob.glob("/sys/class/hwmon/hwmon*/fan1_input")
        if fan_files:
            with open(fan_files[0], "r") as f:
                return int(f.read())
    except:
        pass
    return None

# --- REDE ---
def update_net_stats():
    global last_net_io, last_net_time, net_history
    now = time.time()
    io_now = psutil.net_io_counters()
    down = 0
    up = 0
    if last_net_io:
        dt = now - last_net_time
        if dt > 0:
            down = (io_now.bytes_recv - last_net_io.bytes_recv) / dt / 1024
            up = (io_now.bytes_sent - last_net_io.bytes_sent) / dt / 1024
    last_net_io = io_now
    last_net_time = now
    net_history.append((down, up))
    if len(net_history) > MAX_HISTORY:
        net_history.pop(0)
    return down, up

# --- DESENHO ---
def draw_sparkline(draw, x, y, w, h, data, label, font_val, font_axis, color):
    draw.line((x, y+h, x+w, y+h), fill=color, width=2)
    step_x = w / (MAX_HISTORY - 1) if MAX_HISTORY > 1 else w
    for i in range(0, 5):
        pos_idx = i * (MAX_HISTORY / 4)
        px = x + (pos_idx * step_x)
        draw.line((px, y+h, px, y+h+8), fill=color, width=2)
    
    draw.text((x, y+h+10), "-10m", font=font_axis, fill=color)
    draw.text((x + (w/2), y+h+10), "-5m", font=font_axis, fill=color, anchor="mt")
    draw.text((x+w, y+h+10), t('lbl_now'), font=font_axis, fill=color, anchor="rt")

    if not data: return
    max_val = max(data) if max(data) > 10 else 10
    
    points = []
    for i, val in enumerate(data):
        px = x + (i * step_x)
        py = (y + h) - ((val / max_val) * h)
        points.append((px, py))
    
    if len(points) > 1:
        draw.line(points, fill=color, width=3)
        
    curr = data[-1] if data else 0
    if curr > 1024: val_str = f"{curr/1024:.1f} MB/s"
    else: val_str = f"{int(curr)} KB/s"
    draw.text((x, y-35), f"{label}: {val_str}", font=font_val, fill=color)

def draw_gauge(draw, x, y, radius, percent, label, font_val, font_label, color):
    start = 135
    end = 405
    curr = start + ((end - start) * (percent / 100))
    box = [x-radius, y-radius, x+radius, y+radius]
    draw.arc(box, start=start, end=end, fill=color, width=3)
    draw.arc(box, start=start, end=curr, fill=color, width=14)
    draw.text((x, y), f"{int(percent)}%", font=font_val, fill=color, anchor="mm")
    draw.text((x, y+radius+35), label, font=font_label, fill=color, anchor="mm")

def draw_kindle_battery(draw, x, y, level, font, color):
    w, h = 60, 30
    draw.rectangle([x, y, x+w, y+h], outline=color, width=3)
    draw.rectangle([x+w, y+8, x+w+4, y+h-8], fill=color)
    fill_w = (w-6) * (level / 100)
    draw.rectangle([x+3, y+3, x+3+fill_w, y+h-3], fill=color)
    draw.text((x-10, y+h/2), f"K: {level}%", font=font, fill=color, anchor="rm")

def ensure_icon(icon_name):
    icon_map = {
        "sun": "https://openweathermap.org/img/wn/01d@4x.png",
        "cloudy": "https://openweathermap.org/img/wn/03d@4x.png",
        "fog": "https://openweathermap.org/img/wn/50d@4x.png",
        "rain": "https://openweathermap.org/img/wn/10d@4x.png",
        "storm": "https://openweathermap.org/img/wn/11d@4x.png",
        "snow": "https://openweathermap.org/img/wn/13d@4x.png"
    }
    path = f"icons/{icon_name}.png"
    if not os.path.exists("icons"): os.makedirs("icons")
    if not os.path.exists(path):
        try:
            r = requests.get(icon_map.get(icon_name, icon_map["cloudy"]))
            with open(path, 'wb') as f: f.write(r.content)
        except: return None
    return path

def get_weather(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&timezone=auto"
        r = requests.get(url, timeout=2).json()
        w = r['current_weather']
        code = w['weathercode']
        icon = "cloudy"
        if code == 0: icon = "sun"
        elif code <= 3: icon = "cloudy"
        elif code <= 48: icon = "fog"
        elif code <= 67: icon = "rain"
        elif code > 80: icon = "storm"
        
        status_key = "w_cloudy"
        if code == 0: status_key = "w_sun"
        elif code < 3: status_key = "w_cloudy"
        elif code < 50: status_key = "w_fog"
        elif code < 80: status_key = "w_rain"
        elif code > 80: status_key = "w_snow"
        if code > 95: status_key = "w_storm"

        return w['temperature'], status_key, ensure_icon(icon)
    except: return "--", "w_cloudy", None

@app.route('/dashboard.png')
def serve_dashboard():
    setup_timezone()
    load_translation_file()
    conf = load_config()
    
    W, H = 1448, 1072
    BG = 0 if conf.get('dark_mode') else 255
    FG = 255 if conf.get('dark_mode') else 0
    img = Image.new('L', (W, H), BG)
    draw = ImageDraw.Draw(img)

    try:
        f_huge = ImageFont.truetype("fonts/Roboto-Bold.ttf", conf['font_size'])
        f_city = ImageFont.truetype("fonts/Roboto-Bold.ttf", 90)
        f_big  = ImageFont.truetype("fonts/Roboto-Bold.ttf", 60)
        f_med  = ImageFont.truetype("fonts/Roboto-Bold.ttf", 40)
        f_graph= ImageFont.truetype("fonts/Roboto-Bold.ttf", 28)
        f_small= ImageFont.truetype("fonts/Roboto-Bold.ttf", 24)
        f_tiny = ImageFont.truetype("fonts/Roboto-Bold.ttf", 20)
    except:
        f_huge = ImageFont.load_default()
        f_city = f_big = f_med = f_graph = f_small = f_tiny = f_huge

    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    
    rpi_temp = get_rpi_temp()
    fan_rpm = get_fan_speed()
    moon_icon_name, moon_key = get_moon_phase() 

    update_net_stats()
    temp, status_key, icon_path = get_weather(conf['lat'], conf['lon'])
    now = datetime.datetime.now()
    kbat = request.args.get('kbat', type=int)

    # --- Lógica de Data Traduzida ---
    day_key = f"day_{now.weekday()}"
    day_name = t(day_key)
    date_str = f"{day_name}, {now.strftime('%d/%m')}"

    # ESQUERDA
    draw.text((60, 60), now.strftime("%H:%M"), font=f_huge, fill=FG)
    draw.text((60, 220), date_str, font=f_med, fill=FG) # Dia da semana traduzido
    draw.text((60, 320), conf['city_name'], font=f_city, fill=FG)
    draw.text((60, 520), f"{temp}°C", font=f_huge, fill=FG)
    draw.text((60, 680), t(status_key), font=f_med, fill=FG)

    # --- LUA ---
    moon_path = f"icons/{moon_icon_name}.png"
    if os.path.exists(moon_path):
        try:
            m_icon = Image.open(moon_path).convert("RGBA").resize((80, 80))
            bg_m = Image.new("RGBA", m_icon.size, (BG, BG, BG, 255))
            bg_m.alpha_composite(m_icon)
            final_moon = bg_m.convert("L")
            if conf.get('dark_mode'):
                from PIL import ImageOps
                final_moon = ImageOps.invert(final_moon)
            
            draw_x, draw_y = 610, 60
            img.paste(final_moon, (draw_x, draw_y))
            draw.text((draw_x + 40, draw_y + 85), t(moon_key), font=f_tiny, fill=FG, anchor="mt")
        except: pass

    if icon_path:
        try:
            icon = Image.open(icon_path).convert("RGBA").resize((300, 300))
            bg_icon = Image.new("RGBA", icon.size, (BG, BG, BG, 255))
            bg_icon.alpha_composite(icon)
            final_icon = bg_icon.convert("L")
            if conf.get('dark_mode'):
                from PIL import ImageOps
                final_icon = ImageOps.invert(final_icon)
            img.paste(final_icon, (60, 740))
        except: pass

    draw.line((724, 50, 724, 1022), fill=FG, width=4)

    # DIREITA
    cx = 724 + (724 // 2)
    draw_gauge(draw, cx - 180, 250, 130, cpu, t("lbl_cpu"), f_big, f_med, FG)
    draw_gauge(draw, cx + 180, 250, 130, mem, t("lbl_ram"), f_big, f_med, FG)

    hist_down = [x[0] for x in net_history]
    hist_up = [x[1] for x in net_history]
    
    draw.text((cx, 480), t("lbl_net_title"), font=f_med, fill=FG, anchor="mm")
    gx, gw, gh = 780, 600, 100
    draw_sparkline(draw, gx, 530, gw, gh, hist_down, t("lbl_down"), f_graph, f_tiny, FG)
    draw_sparkline(draw, gx, 730, gw, gh, hist_up, t("lbl_up"), f_graph, f_tiny, FG)

    hw_info = f"{t('lbl_temp_rpi')}: {rpi_temp:.1f}°C"
    if fan_rpm is not None:
        hw_info += f"  |  {t('lbl_fan')}: {fan_rpm} RPM"
    elif rpi_temp > 60:
        hw_info += f"  |  {t('lbl_fan')}: (N/A)"
        
    draw.text((cx, 920), hw_info, font=f_med, fill=FG, anchor="mm")

    ip = get_ip()
    footer = f"Server: {ip} | Up: {now.strftime('%H:%M:%S')}"
    draw.text((1400, 1040), footer, font=f_small, fill=FG, anchor="rb")

    if kbat is not None:
        draw_kindle_battery(draw, 1350, 60, kbat, f_small, FG)

    if conf['rotation'] in [1, 3]: img = img.rotate(90, expand=True)
    if conf['rotation'] == 2: img = img.rotate(180)

    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/update', methods=['POST'])
def update():
    c = load_config()
    c['language'] = request.form.get('language')
    c['rotation'] = int(request.form.get('rotation'))
    c['font_size'] = int(request.form.get('font_size'))
    c['city_name'] = request.form.get('city_name')
    c['timezone'] = request.form.get('timezone')
    c['lat'] = request.form.get('lat')
    c['lon'] = request.form.get('lon')
    c['dark_mode'] = 'dark_mode' in request.form
    save_config(c)
    setup_timezone()
    return redirect('/')

@app.route('/check_status')
def check_status():
    return "RUN" if DASH_ACTIVE else "STOP"

@app.route('/toggle_status', methods=['POST'])
def toggle_status():
    global DASH_ACTIVE
    DASH_ACTIVE = not DASH_ACTIVE
    return redirect('/')

@app.route('/')
def index(): 
    load_translation_file()
    return render_template('index.html', config=load_config(), dash_active=DASH_ACTIVE, tr=CURRENT_LANG)

if __name__ == '__main__':
    setup_timezone()
    load_translation_file()
    app.run(host='0.0.0.0', port=5000)