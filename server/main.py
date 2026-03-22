import psutil, socket, requests, io, datetime, time, json, os, glob, threading, traceback
from flask import Flask, send_file, request, render_template, redirect, jsonify
from PIL import Image, ImageDraw, ImageFont, ImageOps
from w1thermsensor import W1ThermSensor

try:
    from gpiozero import PWMOutputDevice
except ImportError:
    PWMOutputDevice = None

# --- ESTADO GLOBAL ---
latest_sensor_data = {"temp": "--", "hum": "--", "ext_temp": "--"}
current_fan_speed = 0.0
DASH_ACTIVE = True
CURRENT_LANG = {}
last_net_io, last_net_time, net_history = None, 0, []
MAX_HISTORY = 120
slave_data = {"last_seen": 0, "cpu": 0, "ram": 0, "temp": 0.0, "fan": 0, "net_history": []}

try:
    from dht_reader import DHTReader
    sensor_client = DHTReader("DHT22", "/dev/gpiochip4", 17)
    print("✓ [HARDWARE] DHT22 OK no GPIO 17")
except Exception as e:
    print(f"✗ [HARDWARE] Erro DHT22: {e}")
    sensor_client = None

try: ds_sensor = W1ThermSensor()
except Exception: ds_sensor = None

try: 
    fan = PWMOutputDevice(18, frequency=100) if PWMOutputDevice else None
except Exception as e: 
    print(f"✗ [HARDWARE] Erro Fan PWM: {e}")
    fan = None

def update_sensor_background():
    global latest_sensor_data, current_fan_speed
    while True:
        # Leitura dos sensores para telemetria (sempre ocorre para o Dashboard)
        if sensor_client:
            try:
                h, t_val, _ = sensor_client.read_data()
                if t_val is not None: 
                    latest_sensor_data["temp"] = f"{t_val:.1f}"
                    latest_sensor_data["hum"] = f"{h:.1f}"
            except Exception: pass
        
        if ds_sensor:
            try: 
                t_ext = ds_sensor.get_temperature()
                latest_sensor_data["ext_temp"] = f"{t_ext:.1f}"
                c = load_config()
                
                if fan and c.get("fan_node") == "main":
                    t_min, t_max = float(c["fan_temp_min"]), float(c["fan_temp_max"])
                    
                    # NOVA LÓGICA DE CORTE LOCAL
                    if t_ext <= (t_min - 10):
                        speed = 0.0
                    elif t_ext <= t_min:
                        speed = 0.2
                    else:
                        speed = max(0.2, min(1.0, 0.2 + (0.8 * ((t_ext - t_min) / (t_max - t_min)))))
                    
                    fan.value = speed
                    current_fan_speed = speed
                elif fan:
                    fan.value = 0.0 
                    current_fan_speed = 0.0
            except Exception: 
                if fan and load_config().get("fan_node") == "main":
                    fan.value = 1.0
        time.sleep(5)

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
ICONS_DIR = os.path.join(BASE_DIR, "icons")

if not os.path.exists(ICONS_DIR): os.makedirs(ICONS_DIR)

def load_config():
    default = {"rotation": 1, "font_size": 120, "city_name": "Sao Paulo", "timezone": "America/Sao_Paulo", "lat": "-23.5505", "lon": "-46.6333", "theme_mode": "auto", "language": "pt_BR", "brightness": 10, "sensor_main": "online", "sensor_ext": "none", "label_main": "Ext", "label_ext": "Int", "fan_node": "none", "fan_temp_min": 35.0, "fan_temp_max": 50.0}
    try:
        if not os.path.exists(CONFIG_FILE): return default
        with open(CONFIG_FILE, 'r') as f:
            c = json.load(f); [c.setdefault(k, v) for k, v in default.items()]
            return c
    except: return default

def save_config(data):
    with open(CONFIG_FILE, 'w') as f: json.dump(data, f, indent=4)

def load_translation_file():
    global CURRENT_LANG
    conf = load_config()
    path = os.path.join(BASE_DIR, 'locale', f"{conf.get('language', 'pt_BR')}.json")
    try:
        with open(path, 'r', encoding='utf-8') as f: CURRENT_LANG = json.load(f)
    except: CURRENT_LANG = {}
    return CURRENT_LANG

def t(key): return CURRENT_LANG.get(key, key)

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); return s.getsockname()[0]
    except: return "Offline"

def get_moon_phase():
    diff = datetime.datetime.now() - datetime.datetime(2000, 1, 6, 18, 14, 0)
    index = int((diff.total_seconds() / 86400 % 29.530588) / 29.530588 * 8) % 8
    icons = ["moon_new", "moon_waxing_crescent", "moon_first_quarter", "moon_waxing_gibbous", "moon_full", "moon_waning_gibbous", "moon_last_quarter", "moon_waning_crescent"]
    phases = ["m_new", "m_wax_cresc", "m_first_q", "m_wax_gib", "m_full", "m_wan_gib", "m_last_q", "m_wan_cresc"]
    return icons[index], phases[index]

def get_weather(lat, lon):
    try:
        r = requests.get(f"http://api.weatherapi.com/v1/current.json?key=4df7b3293f31480b96c115457261002&q={lat},{lon}&lang=pt", timeout=3).json()
        curr = r['current']; return curr['temp_c'], curr['condition']['text'], "https:" + curr['condition']['icon']
    except: return "--", "Erro API", None

def draw_gauge(draw, x, y, radius, percent, label, font_val, font_label, color):
    start, end = 135, 405; curr = start + ((end - start) * (percent / 100))
    draw.arc([x-radius, y-radius, x+radius, y+radius], start=start, end=end, fill=color, width=3)
    draw.arc([x-radius, y-radius, x+radius, y+radius], start=start, end=curr, fill=color, width=12)
    draw.text((x, y), f"{int(percent)}%", font=font_val, fill=color, anchor="mm")
    draw.text((x, y + radius + 15), label, font=font_label, fill=color, anchor="mm")

def draw_sparkline(draw, x, y, w, h, data, label, font_val, font_axis, color):
    draw.line((x, y, x, y+h), fill=color, width=3); draw.line((x, y+h, x+w, y+h), fill=color, width=3)
    if data:
        max_v = max(data) if max(data) > 10 else 10
        y_lbl = f"{max_v/1024:.1f}M" if max_v > 1024 else f"{int(max_v)}K"
        draw.text((x - 10, y), y_lbl, font=font_axis, fill=color, anchor="rm")
        step_x = w / (MAX_HISTORY - 1); pts = [(x + (i * step_x), (y + h) - ((v / max_v) * h)) for i, v in enumerate(data)]
        if len(pts) > 1: draw.line(pts, fill=color, width=3)
        draw.text((x, y-35), f"{label}: {data[-1]/1024:.1f}MB/s" if data[-1]>1024 else f"{label}: {int(data[-1])}KB/s", font=font_val, fill=color)

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
    net_history.append((down, up)); [net_history.pop(0) for _ in range(len(net_history) - MAX_HISTORY)]
    return down, up

@app.route('/report', methods=['POST'])
def report():
    global slave_data
    if request.is_json:
        data = request.get_json()
        # Recebe a informação do slave
        slave_data.update({
            "cpu": data.get("cpu", 0), 
            "ram": data.get("ram", 0), 
            "temp": data.get("temp", 0.0), 
            "fan": data.get("fan", 0), 
            "last_seen": time.time()
        })
        slave_data["net_history"].append((data.get("net_down", 0), data.get("net_up", 0)))
        if len(slave_data["net_history"]) > MAX_HISTORY: slave_data["net_history"].pop(0)
    
    # Verifica parâmetros e informa ao slave (Resposta do POST é o "próximo ciclo" do slave)
    c = load_config()
    return jsonify({
        "fan_node": c.get("fan_node", "none"),
        "fan_temp_min": c.get("fan_temp_min", 35.0),
        "fan_temp_max": c.get("fan_temp_max", 50.0)
    })

@app.route('/check_status')
def check_status(): return "RUN" if DASH_ACTIVE else "STOP"

@app.route('/dashboard.png')
def serve_dashboard():
    try:
        kindle_bat = request.args.get('kbat'); conf = load_config(); load_translation_file()
        W, H = 1448, 1072; BG, FG = (0, 255) if conf.get('theme_mode') == 'dark' else (255, 0)
        img = Image.new('L', (W, H), BG); draw = ImageDraw.Draw(img)

        # FONTES
        f_p = os.path.join(BASE_DIR, "fonts", "Roboto-Bold.ttf")
        f_huge = ImageFont.truetype(f_p, conf.get('font_size', 120))
        f_city = ImageFont.truetype(f_p, 90); f_med = ImageFont.truetype(f_p, 45)
        f_graph = ImageFont.truetype(f_p, 32); f_tiny = ImageFont.truetype(f_p, 24)
        f_label = ImageFont.truetype(f_p, 35) 

        temp_on, cond_txt, icon_url = get_weather(conf['lat'], conf['lon'])
        moon_icon, moon_key = get_moon_phase()

        def get_v(s):
            if s == "online": return temp_on, None, cond_txt
            if s == "dht": return latest_sensor_data["temp"], latest_sensor_data["hum"], "Interno"
            if s == "ds18": return latest_sensor_data["ext_temp"], None, "Externo"
            return None, None, None

        v1, h1, st1 = get_v(conf['sensor_main']); v2, h2, st2 = get_v(conf['sensor_ext'])
        now = datetime.datetime.now(); update_net_stats()

        # --- UI ESQUERDA ---
        draw.text((60, 40), now.strftime("%H:%M"), font=f_huge, fill=FG)
        draw.text((60, 190), f"{t(f'day_{now.weekday()}')}, {now.strftime('%d/%m')}", font=f_med, fill=FG)
        draw.text((60, 280), conf.get('city_name', 'Dashboard'), font=f_city, fill=FG)
        
        ptr = 410 
        
        # Sensor 1
        label1 = f"{conf.get('label_main','')}: "
        l_w1 = draw.textlength(label1, font=f_label)
        draw.text((60, ptr + 65), label1, font=f_label, fill=FG) 
        draw.text((60 + l_w1, ptr), f"{v1}°C", font=f_huge, fill=FG)
        ptr += 145 
        
        # Sensor 2
        if conf['sensor_ext'] != "none":
            label2 = f"{conf.get('label_ext','')}: "
            l_w2 = draw.textlength(label2, font=f_label)
            draw.text((60, ptr + 65), label2, font=f_label, fill=FG)
            draw.text((60 + l_w2, ptr), f"{v2}°C", font=f_huge, fill=FG)
            ptr += 145

        h_val = h1 if conf['sensor_main'] == "dht" else h2 if conf['sensor_ext'] == "dht" else None
        if h_val and h_val != "--":
            draw.text((60, ptr), f"Umidade: {h_val}%", font=f_med, fill=FG); ptr += 70
        
        draw.text((60, ptr), cond_txt, font=f_med, fill=FG); ptr += 80

        # --- ÍCONES ---
        def paste_icon(icon_file, pos, size, url=None):
            p = os.path.join(ICONS_DIR, f"{icon_file}.png")
            if not os.path.exists(p) and url:
                try:
                    r = requests.get(url, timeout=5)
                    if r.status_code == 200:
                        with open(p, 'wb') as f: f.write(r.content)
                except: pass
            if os.path.exists(p):
                with Image.open(p) as icon_rgba:
                    icon_rgba = icon_rgba.resize(size).convert("RGBA")
                    if conf.get('theme_mode') == 'dark':
                        r, g, b, a = icon_rgba.split()
                        icon_rgba = Image.merge("RGBA", (ImageOps.invert(r), ImageOps.invert(g), ImageOps.invert(b), a))
                    img.paste(icon_rgba.convert("L"), pos, mask=icon_rgba.split()[3])

        paste_icon(moon_icon, (610, 40), (100, 100))
        draw.text((660, 150), t(moon_key), font=f_tiny, fill=FG, anchor="mt")
        if icon_url:
            icon_name = icon_url.split('/')[-1].replace('.png', '')
            paste_icon(icon_name, (60, ptr), (180, 180), icon_url)

        # --- UI DIREITA ---
        draw.line((724, 50, 724, 1022), fill=FG, width=4); cx = 1086
        
        is_slave_active = (time.time() - slave_data["last_seen"] < 60)
        
        # Prioriza telemetria do Slave se ele for o nó designado
        if conf.get("fan_node") == "slave" and is_slave_active:
            rack_t = f"{slave_data['temp']:.1f}"
            fan_p = slave_data.get('fan', 0)
        else:
            rack_t = latest_sensor_data.get('ext_temp', '--')
            fan_p = int(current_fan_speed * 100)

        h_info = f"IP: {get_ip()} | Bat: {kindle_bat or '--'}% | Rack: {rack_t}°C | Fan: {fan_p}% | {now.strftime('%H:%M:%S')}"
        draw.text((740, 60), h_info, font=f_tiny, fill=FG)

        y_m = 205
        draw_gauge(draw, cx - 160, y_m, 85, psutil.cpu_percent(), "MASTER CPU", f_graph, f_tiny, FG)
        draw_gauge(draw, cx + 160, y_m, 85, psutil.virtual_memory().percent, "MASTER RAM", f_graph, f_tiny, FG)
        
        y_d_m = 350
        draw_sparkline(draw, 780, y_d_m, 600, 70 if is_slave_active else 150, [x[0] for x in net_history], "M-Down", f_med if not is_slave_active else f_tiny, f_tiny, FG)
        if not is_slave_active:
            draw_sparkline(draw, 780, y_d_m + 230, 600, 150, [x[1] for x in net_history], "M-Up", f_med, f_tiny, FG)
        else:
            draw_sparkline(draw, 780, 460, 600, 70, [x[1] for x in net_history], "M-Up", f_tiny, f_tiny, FG)
            draw.line((740, 595, 1428, 595), fill=FG, width=2)
            draw_gauge(draw, cx - 160, 725, 85, slave_data['cpu'], "SLAVE CPU", f_graph, f_tiny, FG)
            draw_gauge(draw, cx + 160, 725, 85, slave_data['ram'], "SLAVE RAM", f_graph, f_tiny, FG)
            draw_sparkline(draw, 780, 890, 600, 70, [x[0] for x in slave_data['net_history']], "S-Down", f_tiny, f_tiny, FG)
            draw_sparkline(draw, 780, 1000, 600, 70, [x[1] for x in slave_data['net_history']], "S-Up", f_tiny, f_tiny, FG)

        rot = int(conf.get('rotation', 1))
        angle = 90 if rot == 1 else 180 if rot == 2 else 270 if rot == 3 else 0
        final_img = img.rotate(angle, expand=True)

        buf = io.BytesIO()
        final_img.save(buf, 'PNG')
        buf.seek(0)

        # CRIA A RESPOSTA COM O CABEÇALHO DE BRILHO
        from flask import make_response
        response = make_response(send_file(buf, mimetype='image/png'))
        response.headers['X-Brightness'] = str(conf.get('brightness', 10))
        
        return response
    except Exception:
        traceback.print_exc()
        return "Erro", 500

@app.route('/update', methods=['POST'])
def update():
    c = load_config()
    fields = ['city_name', 'lat', 'lon', 'timezone', 'language', 'theme_mode', 'sensor_main', 'sensor_ext', 'label_main', 'label_ext', 'fan_node']
    for k in fields:
        if k in request.form: c[k] = request.form[k]
        
    c.update({
        "font_size": int(request.form.get('font_size', 120)), 
        "brightness": int(request.form.get('brightness', 10)), 
        "rotation": int(request.form.get('rotation', 1)),
        "fan_temp_min": float(request.form.get('fan_temp_min', 35.0)),
        "fan_temp_max": float(request.form.get('fan_temp_max', 50.0))
    })
    save_config(c); return redirect('/')

@app.route('/toggle_status', methods=['POST'])
def toggle_status():
    global DASH_ACTIVE; DASH_ACTIVE = not DASH_ACTIVE; return redirect('/')

@app.route('/')
def index(): return render_template('index.html', config=load_config(), tr=load_translation_file(), dash_active=DASH_ACTIVE)

if __name__ == '__main__':
    threading.Thread(target=update_sensor_background, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, threaded=True)