import psutil, socket, requests, io, datetime, time, json, os, glob, threading, traceback, sqlite3
from flask import Flask, send_file, request, render_template, redirect, jsonify, make_response
from PIL import Image, ImageDraw, ImageFont, ImageOps
from w1thermsensor import W1ThermSensor

try:
    from gpiozero import PWMOutputDevice
except ImportError:
    PWMOutputDevice = None

# --- ESTADO GLOBAL ---
latest_sensor_data = {"temp": "--", "hum": "--", "ext_temp": "--"}
temp_online, cond_online = "--", "Buscando..."
current_fan_speed = 0.0
DASH_ACTIVE = True
CURRENT_LANG = {}
last_net_io, last_net_time, net_history = None, 0, []
MAX_HISTORY = 120
slave_data = {"last_seen": 0, "cpu": 0, "ram": 0, "temp": 0.0, "fan": 0, "net_history": []}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Caminho solicitado: /app/data (Mapear no Docker para /DATA/AppData/data)
DATA_DIR = "/app/data"
DB_PATH = os.path.join(DATA_DIR, "telemetry.db")

# --- BANCO DE DADOS (BLACKBOX) ---
def init_db():
    """Inicializa a estrutura do banco e garante que a pasta existe."""
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR, exist_ok=True)
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts DATETIME DEFAULT (datetime('now','localtime')),
                int_t REAL, int_h REAL, ext_t REAL,
                s_t REAL, s_f INTEGER, s_c REAL, s_r REAL,
                m_c REAL, m_r REAL,
                n_d REAL, n_u REAL
            )''')
            conn.commit()
    except Exception:
        print("Erro ao inicializar DB"); traceback.print_exc()

def log_telemetry():
    """Captura telemetria Master/Slave e persiste no SQLite."""
    try:
        def f(v):
            try: return float(v)
            except: return None
            
        m_c = psutil.cpu_percent()
        m_r = psutil.virtual_memory().percent
        n_d = net_history[-1][0] if net_history else 0
        n_u = net_history[-1][1] if net_history else 0

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('''INSERT INTO telemetry (
                int_t, int_h, ext_t, s_t, s_f, s_c, s_r, m_c, m_r, n_d, n_u
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                f(latest_sensor_data["temp"]), f(latest_sensor_data["hum"]), f(latest_sensor_data["ext_temp"]),
                slave_data["temp"], slave_data["fan"], slave_data["cpu"], slave_data["ram"],
                m_c, m_r, n_d, n_u
            ))
            conn.commit()
    except:
        pass

# --- HARDWARE INIT ---
try:
    from dht_reader import DHTReader
    sensor_client = DHTReader("DHT22", "/dev/gpiochip4", 17)
    print("✓ [HARDWARE] DHT22 OK")
except Exception: sensor_client = None

try: ds_sensor = W1ThermSensor()
except Exception: ds_sensor = None

try: fan = PWMOutputDevice(18, frequency=100) if PWMOutputDevice else None
except Exception: fan = None

# --- GESTÃO DE CONFIGURAÇÃO ---
def load_config():
    path = os.path.join(BASE_DIR, 'config.json')
    default = {
        "rotation": 1, "font_size": 120, "city_name": "Sao Paulo", "timezone": "America/Sao_Paulo", 
        "lat": "-23.5505", "lon": "-46.6333", "theme_mode": "auto", "language": "pt_BR", 
        "brightness": 10, "sensor_main": "online", "sensor_ext": "none", "label_main": "Int", 
        "label_ext": "Ext", "fan_node": "none", "fan_temp_min": 35.0, "fan_temp_max": 50.0,
        "hist_int_min_log": [], "hist_int_max_log": [],
        "hist_ext_min_log": [], "hist_ext_max_log": [],
        "hist_rack_min_log": [], "hist_rack_max_log": [],
        "hist_fan_min_log": [], "hist_fan_max_log": []
    }
    try:
        if not os.path.exists(path): return default
        with open(path, 'r') as f:
            c = json.load(f); [c.setdefault(k, v) for k, v in default.items()]
            return c
    except: return default

def save_config(data):
    path = os.path.join(BASE_DIR, 'config.json')
    with open(path, 'w') as f: json.dump(data, f, indent=4)

def get_sensor_value(sensor_key):
    if sensor_key == "online": return temp_online
    if sensor_key == "dht": return latest_sensor_data["temp"]
    if sensor_key == "ds18": return latest_sensor_data["ext_temp"]
    if sensor_key == "slave": 
        return f"{slave_data['temp']:.1f}" if (time.time() - slave_data['last_seen'] < 60) else "--"
    return "--"

def update_thermal_log(config, log_key, val, is_min):
    if val == "--" or val is None: return False
    log = config.get(log_key, [])
    try: val_f = float(val)
    except: return False
    current_record = log[0]['val'] if log else (999.0 if is_min else -999.0)
    if (is_min and val_f < current_record) or (not is_min and val_f > current_record):
        now_str = datetime.datetime.now().strftime("%d/%m %H:%M")
        log.insert(0, {"val": round(val_f, 1), "dt": now_str}); config[log_key] = log[:3]
        return True
    return False

def get_weather_data(lat, lon):
    global temp_online, cond_online
    try:
        r = requests.get(f"http://api.weatherapi.com/v1/current.json?key=4df7b3293f31480b96c115457261002&q={lat},{lon}&lang=pt", timeout=5).json()
        temp_online, cond_online = r['current']['temp_c'], r['current']['condition']['text']
        return temp_online, cond_online, "https:" + r['current']['condition']['icon']
    except: return "--", "Erro API", None

def update_sensor_background():
    global latest_sensor_data, current_fan_speed
    init_db()
    last_weather_check = 0
    while True:
        c = load_config(); updated = False
        if time.time() - last_weather_check > 900:
            get_weather_data(c['lat'], c['lon']); last_weather_check = time.time()

        if sensor_client:
            try:
                h, t_val, _ = sensor_client.read_data()
                if t_val is not None: latest_sensor_data["temp"], latest_sensor_data["hum"] = f"{t_val:.1f}", f"{h:.1f}"
            except Exception: pass
        if ds_sensor:
            try: latest_sensor_data["ext_temp"] = f"{ds_sensor.get_temperature():.1f}"
            except Exception: pass

        v_main, v_ext = get_sensor_value(c['sensor_main']), get_sensor_value(c['sensor_ext'])
        val_for_int = v_main if c['label_main'] == "Int" else (v_ext if c['label_ext'] == "Int" else "--")
        if update_thermal_log(c, "hist_int_min_log", val_for_int, True): updated = True
        if update_thermal_log(c, "hist_int_max_log", val_for_int, False): updated = True

        val_for_ext = v_main if c['label_main'] == "Ext" else (v_ext if c['label_ext'] == "Ext" else "--")
        if update_thermal_log(c, "hist_ext_min_log", val_for_ext, True): updated = True
        if update_thermal_log(c, "hist_ext_max_log", val_for_ext, False): updated = True

        target_temp = "--"
        if c.get("fan_node") == "main": target_temp = latest_sensor_data["ext_temp"]
        elif c.get("fan_node") == "slave": target_temp = f"{slave_data['temp']:.1f}" if (time.time()-slave_data['last_seen'] < 60) else "--"

        if target_temp != "--":
            if update_thermal_log(c, "hist_rack_min_log", target_temp, True): updated = True
            if update_thermal_log(c, "hist_rack_max_log", target_temp, False): updated = True

            if fan and c.get("fan_node") == "main":
                try:
                    t_val = float(target_temp); t_min, t_max = float(c["fan_temp_min"]), float(c["fan_temp_max"])
                    speed = max(0.2, min(1.0, 0.2 + (0.8 * ((t_val - t_min) / (t_max - t_min))))) if t_val > t_min else (0.0 if t_val <= t_min-10 else 0.2)
                    fan.value = speed; current_fan_speed = speed
                    if update_thermal_log(c, "hist_fan_min_log", speed*100, True): updated = True
                    if update_thermal_log(c, "hist_fan_max_log", speed*100, False): updated = True
                except: pass
        
        if updated: save_config(c)
        log_telemetry()
        time.sleep(10)

app = Flask(__name__)
ICONS_DIR = os.path.join(BASE_DIR, "icons")

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
        f_s = data.get("fan", 0); t_s = data.get("temp", 0.0)
        slave_data.update({"cpu": data.get("cpu", 0), "ram": data.get("ram", 0), "temp": t_s, "fan": f_s, "last_seen": time.time()})
        slave_data["net_history"].append((data.get("net_down", 0), data.get("net_up", 0)))
        if len(slave_data["net_history"]) > MAX_HISTORY: slave_data["net_history"].pop(0)
        
        c = load_config(); upd = False
        if c.get("fan_node") == "slave":
            if update_thermal_log(c, "hist_fan_min_log", f_s, True): upd = True
            if update_thermal_log(c, "hist_fan_max_log", f_s, False): upd = True
            if upd: save_config(c)
    c = load_config()
    return jsonify({"fan_node": c.get("fan_node", "none"), "fan_temp_min": c.get("fan_temp_min", 35.0), "fan_temp_max": c.get("fan_temp_max", 50.0)})

@app.route('/check_status')
def check_status(): return "RUN" if DASH_ACTIVE else "STOP"

@app.route('/toggle_status', methods=['POST'])
def toggle_status():
    global DASH_ACTIVE; DASH_ACTIVE = not DASH_ACTIVE; return redirect('/')

@app.route('/reset_history', methods=['POST'])
def reset_history():
    c = load_config()
    for k in ["hist_int_min_log", "hist_int_max_log", "hist_ext_min_log", "hist_ext_max_log", "hist_fan_min_log", "hist_fan_max_log", "hist_rack_min_log", "hist_rack_max_log"]: c[k] = []
    save_config(c); return redirect('/')

@app.route('/history')
def history_page():
    # Parâmetros de filtro
    start_d = request.args.get('start_date', datetime.datetime.now().strftime('%Y-%m-%d'))
    end_d = request.args.get('end_date', datetime.datetime.now().strftime('%Y-%m-%d'))
    start_t = request.args.get('start_time', '00:00')
    end_t = request.args.get('end_time', '23:59')
    
    # Parâmetros de ordenação
    sort_col = request.args.get('sort', 'ts')
    sort_dir = request.args.get('dir', 'DESC').upper()
    
    # Whitelist para evitar SQL Injection na ordenação
    allowed_cols = ['ts', 'int_t', 'ext_t', 's_t', 's_f', 'm_c', 's_c', 'n_d']
    if sort_col not in allowed_cols: sort_col = 'ts'
    if sort_dir not in ['ASC', 'DESC']: sort_dir = 'DESC'

    start_full = f"{start_d} {start_t}:00"
    end_full = f"{end_d} {end_t}:59"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        query = f"SELECT * FROM telemetry WHERE ts BETWEEN ? AND ? ORDER BY {sort_col} {sort_dir}"
        logs = conn.execute(query, (start_full, end_full)).fetchall()
    
    return render_template('history.html', logs=logs, start_date=start_d, end_date=end_d, 
                           start_time=start_t, end_time=end_t, sort=sort_col, dir=sort_dir)
    
@app.route('/api/stats')
def api_stats():
    conf = load_config()
    is_s_act = (time.time() - slave_data["last_seen"] < 60)
    now = datetime.datetime.now()
    net_down, net_up = update_net_stats()

    stats = {
        "system_master": {
            "hostname": socket.gethostname(),
            "ip": get_ip(),
            "cpu_usage": f"{psutil.cpu_percent()}%",
            "ram_usage": f"{psutil.virtual_memory().percent}%",
            "net_down": f"{net_down:.1f} KB/s",
            "net_up": f"{net_up:.1f} KB/s",
            "uptime_reference": now.strftime("%Y-%m-%d %H:%M:%S")
        },
        "system_slave": {
            "status": "Online" if is_s_act else "Offline",
            "last_seen": datetime.datetime.fromtimestamp(slave_data["last_seen"]).strftime("%H:%M:%S") if slave_data["last_seen"] > 0 else "N/A",
            "cpu_usage": f"{slave_data['cpu']}%",
            "ram_usage": f"{slave_data['ram']}%",
            "temp": f"{slave_data['temp']:.1f}°C",
            "fan_speed": f"{slave_data['fan']}%"
        },
        "weather": {
            "city": conf.get("city_name"),
            "temp_online": f"{temp_online}°C",
            "condition": cond_online,
            "moon_phase": t(get_moon_phase()[1])
        },
        "environment": {
            "internal_temp": f"{latest_sensor_data['temp']}°C",
            "internal_hum": f"{latest_sensor_data['hum']}%",
            "external_temp": f"{latest_sensor_data['ext_temp']}°C"
        },
        "rack_control": {
            "active_node": conf.get("fan_node"),
            "current_fan_speed": f"{int(current_fan_speed * 100)}%"
        },
        "history_top_records": {
            "internal_max": conf.get("hist_int_max_log", [])[:1],
            "external_max": conf.get("hist_ext_max_log", [])[:1],
            "rack_max": conf.get("hist_rack_max_log", [])[:1]
        }
    }
    return jsonify(stats)

@app.route('/dashboard.png')
def serve_dashboard():
    try:
        kindle_bat = request.args.get('kbat'); conf = load_config(); load_translation_file()
        W, H = 1448, 1072; BG, FG = (0, 255) if conf.get('theme_mode') == 'dark' else (255, 0)
        img = Image.new('L', (W, H), BG); draw = ImageDraw.Draw(img)

        f_p = os.path.join(BASE_DIR, "fonts", "Roboto-Bold.ttf")
        f_huge = ImageFont.truetype(f_p, conf.get('font_size', 120))
        f_city = ImageFont.truetype(f_p, 90); f_med = ImageFont.truetype(f_p, 45); f_tiny = ImageFont.truetype(f_p, 24)
        f_label = ImageFont.truetype(f_p, 35); f_graph = ImageFont.truetype(f_p, 32)

        t_api, cond_api, icon_url = get_weather_data(conf['lat'], conf['lon'])
        moon_icon, moon_key = get_moon_phase()

        def get_display_val(s):
            if s == "online": return t_api, None, cond_api
            if s == "dht": return latest_sensor_data["temp"], latest_sensor_data["hum"], "Interno"
            if s == "ds18": return latest_sensor_data["ext_temp"], None, "Externo"
            if s == "slave": return (f"{slave_data['temp']:.1f}" if time.time()-slave_data['last_seen']<60 else "--"), None, "Slave"
            return "--", None, "--"

        v1, h1, st1 = get_display_val(conf['sensor_main']); v2, h2, st2 = get_display_val(conf['sensor_ext'])
        now = datetime.datetime.now(); update_net_stats()

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
                        r_ch, g_ch, b_ch, a_ch = icon_rgba.split()
                        icon_rgba = Image.merge("RGBA", (ImageOps.invert(r_ch), ImageOps.invert(g_ch), ImageOps.invert(b_ch), a_ch))
                    img.paste(icon_rgba.convert("L"), pos, mask=icon_rgba.split()[3])

        # --- UI ESQUERDA ---
        draw.text((60, 40), now.strftime("%H:%M"), font=f_huge, fill=FG)
        draw.text((60, 190), f"{t(f'day_{now.weekday()}')}, {now.strftime('%d/%m')}", font=f_med, fill=FG)
        draw.text((60, 280), conf.get('city_name', 'Dashboard'), font=f_city, fill=FG)
        ptr = 410
        l1 = f"{conf.get('label_main','')}: "; lw1 = draw.textlength(l1, font=f_label)
        draw.text((60, ptr + 65), l1, font=f_label, fill=FG); draw.text((60 + lw1, ptr), f"{v1}°C", font=f_huge, fill=FG); ptr += 145 
        if conf['sensor_ext'] != "none":
            l2 = f"{conf.get('label_ext','')}: "; lw2 = draw.textlength(l2, font=f_label)
            draw.text((60, ptr + 65), l2, font=f_label, fill=FG); draw.text((60 + lw2, ptr), f"{v2}°C", font=f_huge, fill=FG); ptr += 145

        h_val = h1 if conf['sensor_main'] == "dht" else h2 if conf['sensor_ext'] == "dht" else None
        if h_val and h_val != "--":
            try:
                hf = float(h_val); hst = "- Ideal" if 40 <= hf <= 60 else ("- Baixa" if hf < 40 else "- Alta")
            except: hst = ""
            htxt = f"Umidade: {h_val}% "; draw.text((60, ptr), htxt, font=f_med, fill=FG)
            draw.text((60 + draw.textlength(htxt, font=f_med), ptr + 8), hst, font=f_label, fill=FG); ptr += 70
        
        draw.text((60, ptr), cond_api, font=f_med, fill=FG); ptr += 55
        if icon_url:
            icon_name = icon_url.split('/')[-1].replace('.png', '')
            paste_icon(icon_name, (60, ptr), (180, 180), icon_url)

        # --- UI DIREITA ---
        draw.line((724, 50, 724, 1022), fill=FG, width=4); cx = 1086
        is_s_act = (time.time() - slave_data["last_seen"] < 60)
        rack_t, fan_p = (f"{slave_data['temp']:.1f}", str(slave_data['fan'])) if (conf.get("fan_node") == "slave" and is_s_act) else (latest_sensor_data.get('ext_temp', '--'), str(int(current_fan_speed * 100)))

        curr_x, y_p = 740, 60
        header_pts = [(f"IP: {get_ip()} | Bat: {kindle_bat or '--'}% | Rack: ", f_tiny), (f"{rack_t} C", f_med), (" | Fan: ", f_tiny), (f"{fan_p}%", f_med)]
        for txt, fnt in header_pts:
            draw.text((curr_x, y_p if fnt == f_tiny else y_p - 15), txt, font=fnt, fill=FG)
            curr_x += draw.textlength(txt, font=fnt)
        
        draw_gauge(draw, cx - 160, 205, 85, psutil.cpu_percent(), "MASTER CPU", f_graph, f_tiny, FG)
        draw_gauge(draw, cx + 160, 205, 85, psutil.virtual_memory().percent, "MASTER RAM", f_graph, f_tiny, FG)
        y_d_m = 350
        draw_sparkline(draw, 780, y_d_m, 600, 70 if is_s_act else 150, [x[0] for x in net_history], "M-Down", f_med if not is_s_act else f_tiny, f_tiny, FG)
        if is_s_act:
            draw_sparkline(draw, 780, 485, 600, 70, [x[1] for x in net_history], "M-Up", f_tiny, f_tiny, FG)
            draw.line((740, 570, 1428, 570), fill=FG, width=2)
            draw_gauge(draw, cx - 160, 700, 85, slave_data['cpu'], "SLAVE CPU", f_graph, f_tiny, FG)
            draw_gauge(draw, cx + 160, 700, 85, slave_data['ram'], "SLAVE RAM", f_graph, f_tiny, FG)
            draw_sparkline(draw, 780, 865, 600, 70, [x[0] for x in slave_data['net_history']], "S-Down", f_tiny, f_tiny, FG)
            draw_sparkline(draw, 780, 975, 600, 70, [x[1] for x in slave_data['net_history']], "S-Up", f_tiny, f_tiny, FG)
        else:
            draw_sparkline(draw, 780, y_d_m + 230, 600, 150, [x[1] for x in net_history], "M-Up", f_med, f_tiny, FG)

        paste_icon(moon_icon, (610, 40), (100, 100))
        draw.text((660, 150), t(moon_key), font=f_tiny, fill=FG, anchor="mt")

        rot = int(conf.get('rotation', 1)); angle = 90 if rot == 1 else 180 if rot == 2 else 270 if rot == 3 else 0
        final_img = img.rotate(angle, expand=True)
        buf = io.BytesIO(); final_img.save(buf, 'PNG'); buf.seek(0)
        res = make_response(send_file(buf, mimetype='image/png'))
        res.headers['X-Brightness'] = str(conf.get('brightness', 10))
        return res
    except Exception: traceback.print_exc(); return "Erro", 500

@app.route('/update', methods=['POST'])
def update():
    c = load_config()
    fields = ['city_name', 'lat', 'lon', 'timezone', 'language', 'theme_mode', 'sensor_main', 'sensor_ext', 'label_main', 'label_ext', 'fan_node']
    for k in fields:
        if k in request.form: c[k] = request.form[k]
    c.update({"font_size": int(request.form.get('font_size', 120)), "brightness": int(request.form.get('brightness', 10)), "rotation": int(request.form.get('rotation', 1)), "fan_temp_min": float(request.form.get('fan_temp_min', 35.0)), "fan_temp_max": float(request.form.get('fan_temp_max', 50.0))})
    save_config(c); return redirect('/')

@app.route('/')
def index(): 
    return render_template('index.html', config=load_config(), tr=load_translation_file(), dash_active=DASH_ACTIVE)

if __name__ == '__main__':
    threading.Thread(target=update_sensor_background, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, threaded=True)