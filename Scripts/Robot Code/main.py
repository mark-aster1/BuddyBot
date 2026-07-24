import time, subprocess, spidev, select, json, threading, queue, signal, os, math, io, sys
from flask import Flask, Response
import usb_module
import ble_scanner
import voice_module
import RPi.GPIO as GPIO
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from evdev import InputDevice, list_devices, ecodes


# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════

DC, RST  = 24, 25
W, H     = 480, 320

BASE_DIR        = "/home/mark-aster/documents/buddy_bot"
BUDDYBOT_STATUS = "/tmp/buddybot_status.json"
SCANNER_STATUS  = "/tmp/barcode_status.json"
CAM_FRAME_PATH  = "/tmp/cam_frame.jpg"

SCRIPTS = {
    "buddy_bot":       f"{BASE_DIR}/buddy_bot.py",
    "test_motors":     f"{BASE_DIR}/motor_test.py",
    "barcode_scanner": f"{BASE_DIR}/barcode_scanner.py",
}

MENU_ITEMS = [
    ("System Overview", "overview",   None),
    ("Following Mode",  "robot",      "buddy_bot"),
    ("BLE Radar",       "radar",      None),
    ("Barcode Scanner", "barcode",    "barcode_scanner"),
    ("Test Motors",     "robot",      "test_motors"),
    ("USB Module",      "usb_module", None),
    ("Reboot",        "shutdown",   None),
]

STICK_COOLDOWN = 0.20
STREAM_PORT    = 8081

RADAR_MIN_PERIOD   = 1.0 / 8  
BARCODE_MIN_PERIOD = 1.0 / 6
OVERVIEW_PERIOD    = 1.0


# ═══════════════════════════════════════════════════════════════
# COLORS
# ═══════════════════════════════════════════════════════════════

BG      = (10,  10,  20)
PANEL   = (20,  20,  38)
HILIGHT = (38,  38,  70)
ACCENT  = (0,   180, 255)
WHITE   = (255, 255, 255)
GRAY    = (90,  90,  110)
GREEN   = (50,  220, 100)
YELLOW  = (255, 200,  50)
RED     = (220,  60,  60)
CYAN    = (0,   200, 255)
ORANGE  = (255, 140,   0)
DIVIDER = (40,  40,  65)


# ═══════════════════════════════════════════════════════════════
# FRAMEBUFFER
# ═══════════════════════════════════════════════════════════════

fb      = Image.new("RGB", (W, H))
_d      = ImageDraw.Draw(fb)
_spi    = None
fb_lock = threading.Lock()


def fill_rect(x, y, w, h, color):
    if w <= 0 or h <= 0:
        return
    _d.rectangle([x, y, x+w-1, y+h-1], fill=color)

def draw_hline(x, y, length, color):
    _d.line([(x, y), (x+length-1, y)], fill=color)

def draw_vline(x, y, length, color):
    _d.line([(x, y), (x, y+length-1)], fill=color)

def draw_text(x, y, text, color, font):
    _d.text((x, y), text, fill=color, font=font)

def draw_bar(x, y, w, h, pct, color):
    fill_rect(x, y, w, h, (35, 35, 55))
    fw = int(w * max(0.0, min(pct, 100.0)) / 100)
    if fw > 0:
        fill_rect(x, y, fw, h, color)

def draw_gamepad(x, y, connected):
    c  = GREEN if connected else GRAY
    bg = (15, 15, 28)
    fill_rect(x+2,  y+4,  28, 14, c)
    fill_rect(x+2,  y+16,  9,  7, c)
    fill_rect(x+21, y+16,  9,  7, c)
    fill_rect(x+7,  y+9,   7,  2, bg)
    fill_rect(x+9,  y+7,   3,  6, bg)
    fill_rect(x+20, y+7,   3,  3, bg)
    fill_rect(x+24, y+7,   3,  3, bg)

def flush():
    with fb_lock:
        buf = fb.tobytes()

    GPIO.output(DC, GPIO.LOW);  _spi.xfer2([0x2A])
    GPIO.output(DC, GPIO.HIGH); _spi.xfer2([0, 0, (W-1)>>8, (W-1)&0xFF])
    GPIO.output(DC, GPIO.LOW);  _spi.xfer2([0x2B])
    GPIO.output(DC, GPIO.HIGH); _spi.xfer2([0, 0, (H-1)>>8, (H-1)&0xFF])
    GPIO.output(DC, GPIO.LOW);  _spi.xfer2([0x2C])
    GPIO.output(DC, GPIO.HIGH)

    _CHUNK = 4096
    for i in range(0, len(buf), _CHUNK):
        _spi.writebytes2(buf[i:i+_CHUNK])

# ═══════════════════════════════════════════════════════════════
# DISPLAY INIT
# ═══════════════════════════════════════════════════════════════

def _cmd(c): GPIO.output(DC, GPIO.LOW);  _spi.xfer2([c])
def _dat(d): GPIO.output(DC, GPIO.HIGH); _spi.xfer2(d if isinstance(d, list) else [d])

def init_display():
    for v in (GPIO.HIGH, GPIO.LOW, GPIO.HIGH):
        GPIO.output(RST, v); time.sleep(0.1)
    _cmd(0xE0); _dat([0x00,0x07,0x0F,0x0D,0x1B,0x0A,0x3C,0x78,0x4A,0x07,0x0E,0x09,0x1B,0x1E,0x0F])
    _cmd(0xE1); _dat([0x00,0x22,0x24,0x06,0x12,0x07,0x36,0x47,0x47,0x06,0x0A,0x07,0x30,0x37,0x0F])
    _cmd(0xC0); _dat([0x10, 0x10])
    _cmd(0xC1); _dat([0x41])
    _cmd(0xC5); _dat([0x00, 0x22, 0x80])
    _cmd(0x36); _dat([0xE8])
    _cmd(0x3A); _dat([0x66])
    _cmd(0xB0); _dat([0x00])
    _cmd(0xB1); _dat([0xA0])
    _cmd(0xB4); _dat([0x02])
    _cmd(0xB6); _dat([0x02, 0x02, 0x3B])
    _cmd(0xB7); _dat([0xC6])
    _cmd(0xF7); _dat([0xA9, 0x51, 0x2C, 0x82])
    _cmd(0x11); time.sleep(0.12)
    _cmd(0x29); time.sleep(0.02)


# ═══════════════════════════════════════════════════════════════
# PI STATS
# ═══════════════════════════════════════════════════════════════

_stats = {"cpu": 0.0, "temp": 0.0, "voltage": 0.0,
          "ram_pct": 0, "ram_used": 0, "ram_total": 1,
          "freq": 0, "uptime": "0:00:00"}
_stats_lock = threading.Lock()

_ble_trail = []


def _measure_cpu():
    def stat():
        f = open("/proc/stat").readline().split()
        return sum(int(x) for x in f[1:]), int(f[4])
    t1, i1 = stat()
    time.sleep(0.5)
    t2, i2 = stat()
    dt = t2 - t1
    return 100.0 * (1 - (i2 - i1) / dt) if dt else 0.0

def stats_thread_func():
    while _running:
        temp = 0.0
        try:    temp = float(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000
        except: pass

        voltage = 0.0
        try:
            raw     = subprocess.check_output(["vcgencmd", "measure_volts", "core"], text=True).strip()
            voltage = float(raw.split("=")[1].rstrip("V"))
        except: pass

        m = {}
        for line in open("/proc/meminfo"):
            p = line.split()
            m[p[0].rstrip(":")] = int(p[1])
        used     = m["MemTotal"] - m["MemAvailable"]
        ram_pct  = 100 * used // m["MemTotal"]
        ram_used = used // 1024
        ram_tot  = m["MemTotal"] // 1024

        freq = 0
        try:    freq = int(open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq").read()) // 1000
        except: pass

        secs   = float(open("/proc/uptime").read().split()[0])
        uptime = str(timedelta(seconds=int(secs)))
        cpu    = _measure_cpu()

        with _stats_lock:
            _stats.update(cpu=cpu, temp=temp, voltage=voltage,
                          ram_pct=ram_pct, ram_used=ram_used, ram_total=ram_tot,
                          freq=freq, uptime=uptime)
        time.sleep(1.5)

def get_stats():
    with _stats_lock:
        return dict(_stats)


# ═══════════════════════════════════════════════════════════════
# SCRIPT MANAGEMENT
# ═══════════════════════════════════════════════════════════════

_procs      = {}
_procs_lock = threading.Lock()

def launch(name):
    with _procs_lock:
        p = _procs.get(name)
        if p and p.poll() is None:
            return
        path = SCRIPTS.get(name)
        if not path:
            return
        _procs[name] = subprocess.Popen([sys.executable, "-u", path])
        print(f"Launched: {name}  pid={_procs[name].pid}")

def stop(name):
    with _procs_lock:
        p = _procs.pop(name, None)
    if p and p.poll() is None:
        p.send_signal(signal.SIGINT)
        try:   p.wait(timeout=5)
        except subprocess.TimeoutExpired: p.kill()
        print(f"Stopped: {name}")

def is_running(name):
    with _procs_lock:
        p = _procs.get(name)
    return p is not None and p.poll() is None

def stop_all():
    for name in list(_procs.keys()):
        stop(name)


# ═══════════════════════════════════════════════════════════════
# INPUT THREAD
# ═══════════════════════════════════════════════════════════════

_ctrl       = None
_action_q   = queue.Queue()
_stick_time = 0.0

def find_controller():
    for path in list_devices():
        try:
            dev  = InputDevice(path)
            name = dev.name.lower()
            if not ("dualsense" in name or "wireless controller" in name or "ps5" in name):
                continue
            if any(k in name for k in ("touchpad", "motion", "sensor")):
                continue
            axes = [a[0] if isinstance(a, tuple) else a
                    for a in dev.capabilities().get(ecodes.EV_ABS, [])]
            if ecodes.ABS_RX in axes:
                return dev
        except Exception:
            pass
    return None

def input_thread_func():
    global _ctrl, _stick_time
    last_search = 0.0
    while _running:
        now = time.time()
        if _ctrl is None:
            if now - last_search > 3.0:
                last_search = now
                _ctrl = find_controller()
                if _ctrl:
                    print(f"Controller: {_ctrl.name}")
                    _mark_dirty()
            time.sleep(0.1)
            continue
        try:
            r, _, _ = select.select([_ctrl.fd], [], [], 0.02)
            if not r:
                continue
            for ev in _ctrl.read():
                if ev.type == ecodes.EV_ABS and ev.code == ecodes.ABS_HAT0Y:
                    if ev.value == -1: _action_q.put("up")
                    if ev.value ==  1: _action_q.put("down")
                if ev.type == ecodes.EV_ABS and ev.code == ecodes.ABS_LY:
                    v = (ev.value - 128) / 128.0
                    if abs(v) > 0.6 and now - _stick_time > STICK_COOLDOWN:
                        _action_q.put("up" if v < 0 else "down")
                        _stick_time = now
                if ev.type == ecodes.EV_KEY and ev.value == 1:
                    if ev.code == ecodes.BTN_SOUTH: _action_q.put("select")
                    if ev.code == ecodes.BTN_EAST:  _action_q.put("back")
                    if ev.code == ecodes.BTN_NORTH: _action_q.put("launch_stop")
        except OSError:
            print("Controller disconnected.")
            _ctrl = None
            _mark_dirty()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# LAYOUT HELPERS
# ═══════════════════════════════════════════════════════════════

def draw_header(title, fonts):
    fill_rect(0, 0, W, 50, PANEL)
    draw_text(12, 14, title, WHITE, fonts[1])
    draw_gamepad(W - 114, 12, _ctrl is not None)
    label = "CTRL OK" if _ctrl is not None else "NO CTRL"
    color = GREEN     if _ctrl is not None else RED
    draw_text(W - 76, 18, label, color, fonts[2])
    draw_hline(0, 50, W, DIVIDER)

def draw_footer(hint, fonts):
    draw_hline(0, 300, W, DIVIDER)
    draw_text(10, 306, hint, GRAY, fonts[2])

def status_style(raw):
    if not raw or raw == "OFFLINE":             return "OFFLINE",          RED
    if raw == "STARTING":                       return "STARTING ...",     GRAY
    if raw.startswith("MANUAL"):                return "MANUAL OVERRIDE",  ORANGE
    if raw in ("TURN RIGHT", "TURN LEFT"):      return "FOLLOWING",        CYAN
    if raw.startswith("FORWARD"):               return "FOLLOWING",        GREEN
    if raw in ("AT TARGET", "TARGET CENTERED"): return "AT TARGET",        GREEN
    if raw == "TARGET LOST":                    return "SEARCHING ...",    YELLOW
    if raw == "VOICE STOPPED":                  return "VOICE STOPPED",    ORANGE
    return raw, WHITE


# ═══════════════════════════════════════════════════════════════
# SCREEN: MAIN MENU
# ═══════════════════════════════════════════════════════════════

_ITEM_H  = 35
_START_Y = 54

def render_main(fonts, sel):
    f_big, f_med, f_sm = fonts
    running_states = [s and is_running(s) for _, _, s in MENU_ITEMS]
    with fb_lock:
        fill_rect(0, 0, W, H, BG)
        draw_header("BUDDY BOT", fonts)
        for i, (label, screen_key, _) in enumerate(MENU_ITEMS):
            if screen_key == "usb_module":
                label = usb_module.get_menu_label()
            y       = _START_Y + i * _ITEM_H
            running = running_states[i]
            if i == sel:
                fill_rect(8, y, W-16, _ITEM_H-2, HILIGHT)
                fill_rect(8, y, 4,    _ITEM_H-2, ACCENT)
                if running:
                    draw_text(20,    y+8, "●",   GREEN, f_med)
                txt_x = 42 if running else 20
                draw_text(txt_x, y+8, label, WHITE, f_med)
                draw_text(W-28,  y+8, ">",   ACCENT, f_med)
            else:
                if running:
                    draw_text(20, y+8, "●",   GREEN, f_med)
                    draw_text(42, y+8, label, GRAY,  f_med)
                else:
                    draw_text(20, y+8, label, GRAY, f_med)
        draw_footer("up/down  Navigate      X  Select", fonts)


# ═══════════════════════════════════════════════════════════════
# SCREEN: SYSTEM OVERVIEW
# ═══════════════════════════════════════════════════════════════

def render_overview(fonts):
    f_big, f_med, f_sm = fonts
    s   = get_stats()
    now = datetime.now()
    tc = RED if s["temp"]    > 75 else YELLOW if s["temp"]    > 60 else GREEN
    cc = RED if s["cpu"]     > 80 else YELLOW if s["cpu"]     > 50 else GREEN
    rc = RED if s["ram_pct"] > 80 else YELLOW if s["ram_pct"] > 60 else GREEN
    with fb_lock:
        fill_rect(0, 0, W, H, BG)
        draw_header("SYSTEM OVERVIEW", fonts)
        draw_text(10, 55,  now.strftime("%H:%M:%S"),     WHITE, f_big)
        draw_text(10, 104, now.strftime("%A  %d %B %Y"), GRAY,  f_sm)
        draw_text(W-170, 60, "UPTIME",    GRAY,  f_sm)
        draw_text(W-170, 76, s["uptime"], WHITE, f_med)
        draw_hline(0, 118, W, DIVIDER)
        x1 = 10
        draw_text(x1, 124, "CPU TEMP",                          GRAY, f_sm)
        draw_text(x1, 140, f"{s['temp']:.1f} °C",               tc,   f_med)
        draw_bar( x1, 166, 210, 10, s["temp"] / 85 * 100,       tc)
        draw_text(x1, 180, "CPU USAGE",                         GRAY, f_sm)
        draw_text(x1, 196, f"{s['cpu']:.1f} %",                 cc,   f_med)
        draw_bar( x1, 222, 210, 10, s["cpu"],                   cc)
        draw_text(x1, 236, "RAM",                               GRAY, f_sm)
        draw_text(x1, 252, f"{s['ram_used']} / {s['ram_total']} MB", rc, f_med)
        draw_bar( x1, 278, 210, 10, s["ram_pct"],               rc)
        x2 = 255
        draw_text(x2, 124, "CORE VOLTAGE",          GRAY,   f_sm)
        draw_text(x2, 140, f"{s['voltage']:.4f} V", CYAN,   f_med)
        draw_text(x2, 192, "CPU FREQ",              GRAY,   f_sm)
        draw_text(x2, 208, f"{s['freq']} MHz",      ORANGE, f_med)
        draw_vline(245, 120, 178, DIVIDER)
        draw_footer("O  Back", fonts)


# ═══════════════════════════════════════════════════════════════
# SCREEN: ROBOT STATUS
# ═══════════════════════════════════════════════════════════════

def render_robot(fonts):
    f_big, f_med, f_sm = fonts
    data = {}
    try:
        with open(BUDDYBOT_STATUS) as f:
            data = json.load(f)
    except Exception:
        pass
    raw_status = data.get("status",     "OFFLINE")
    fps        = data.get("fps",        0.0)
    motor      = data.get("motor",      0)
    target     = data.get("target",     False)
    ctrl_ok    = data.get("controller", False)
    label, sc  = status_style(raw_status)
    running_bb = is_running(_cur_script or "buddy_bot")
    with fb_lock:
        fill_rect(0, 0, W, H, BG)
        draw_header("BUDDY BOT", fonts)
        fill_rect(8,  58, W-16, 36, PANEL)
        fill_rect(8,  58, 4,    36, sc)
        draw_text(18, 66, label, sc, f_med)
        fps_col = GREEN if fps > 10 else YELLOW if fps > 5 else RED
        draw_text(W-90, 60, "FPS",        GRAY,    f_sm)
        draw_text(W-90, 76, f"{fps:.1f}", fps_col, f_sm)
        draw_hline(0, 98, W, DIVIDER)
        x1 = 12
        draw_text(x1, 106, "TARGET",  GRAY, f_sm)
        draw_text(x1, 122, "● LOCKED" if target else "○ NONE",
                  GREEN if target else GRAY, f_med)
        draw_text(x1, 166, "CONTROLLER", GRAY, f_sm)
        draw_text(x1, 182, "● CONNECTED" if ctrl_ok else "○ OFFLINE",
                  GREEN if ctrl_ok else GRAY, f_med)
        draw_text(x1, 226, "MOTOR", GRAY, f_sm)
        mdir = "FWD" if motor > 0 else "REV" if motor < 0 else "STOP"
        mcol = GREEN if motor > 0 else RED   if motor < 0 else GRAY
        draw_text(x1, 242, f"{motor:+d}%  {mdir}", mcol, f_med)
        draw_bar( x1, 268, 200, 10, abs(motor), mcol)
        x2 = 255
        draw_text(x2, 106, "PROCESS", GRAY, f_sm)
        draw_text(x2, 122, "● RUNNING" if running_bb else "○ STOPPED",
                  GREEN if running_bb else RED, f_med)
        draw_text(x2, 166, "UPTIME", GRAY,  f_sm)
        draw_text(x2, 182, get_stats()["uptime"], WHITE, f_med)
        draw_vline(245, 100, 198, DIVIDER)
        tri = "▲"
        if running_bb:
            draw_footer(f"O  Back (keep running)      {tri}  Stop", fonts)
        else:
            draw_footer(f"O  Back                     {tri}  Launch", fonts)


# ═══════════════════════════════════════════════════════════════
# SCREEN: BARCODE SCANNER
# ═══════════════════════════════════════════════════════════════

_last_cam_mtime = 0.0

def render_barcode(fonts):
    global _last_cam_mtime
    f_big, f_med, f_sm = fonts
    data = {}
    try:
        with open(SCANNER_STATUS) as f:
            data = json.load(f)
    except Exception:
        pass

    status     = data.get("status",     "OFFLINE")
    last_name  = data.get("last_name",  "")
    last_price = data.get("last_price", 0.0)
    cart       = data.get("cart",       [])
    total      = data.get("total",      0.0)
    running_sc = is_running("barcode_scanner")
    sc = {"FOUND": GREEN, "NOT FOUND": RED, "READY": CYAN, "OFFLINE": GRAY}.get(status, GRAY)

    with fb_lock:
        fill_rect(0, 0, W, H, BG)
        draw_header("BARCODE SCANNER", fonts)

        fill_rect(8, 54, W-16, 28, PANEL)
        fill_rect(8, 54, 4,    28, sc)
        draw_text(16, 61, status, sc, f_sm)

        if last_name:
            draw_text(10,    90, last_name[:22],           WHITE, f_med)
            draw_text(W-105, 90, f"{last_price:.2f} RON", CYAN,  f_med)
        else:
            draw_text(10, 90, "Scan an item...", GRAY, f_med)

        draw_hline(0, 118, W, DIVIDER)

        draw_text(10, 123, "CART", GRAY, f_sm)
        shown = cart[-6:] 
        for i, item in enumerate(shown):
            y   = 142 + i * 22
            col = WHITE if i == len(shown)-1 else GRAY
            draw_text(10,   y, item["name"][:18],      col, f_sm)
            draw_text(160,  y, f"{item['price']:.1f}", col, f_sm)

        draw_vline(235, 118, 150, DIVIDER)

        if running_sc:
            try:
                mtime = os.path.getmtime(CAM_FRAME_PATH)
            except OSError:
                mtime = 0.0
            if mtime:
                if mtime != _last_cam_mtime:
                    try:
                        with Image.open(CAM_FRAME_PATH) as cam_img:
                            fb.paste(cam_img, (242, 124))
                        _last_cam_mtime = mtime
                    except Exception:
                        pass
            else:
                fill_rect(242, 124, 230, 140, PANEL)
                draw_text(285, 180, "STARTING CAM...", GRAY, f_sm)
        else:
            _last_cam_mtime = 0.0
            fill_rect(242, 124, 230, 140, PANEL)
            draw_text(300, 180, "CAM OFFLINE", GRAY, f_sm)

        draw_hline(0, 268, W, DIVIDER)
        draw_text(10,    272, f"{len(cart)} items",      GRAY,   f_sm)
        draw_text(W-200, 272, f"TOTAL {total:.2f} RON", YELLOW, f_med)

        tri = "▲"
        if running_sc:
            draw_footer(f"O  Back (keep running)      {tri}  Stop", fonts)
        else:
            draw_footer(f"O  Back                     {tri}  Launch", fonts)

def _barcode_snapshot():
    """Cheap fingerprint of barcode state used to decide whether a redraw
    is warranted, independent of the camera frame (handled separately)."""
    data = {}
    try:
        with open(SCANNER_STATUS) as f:
            data = json.load(f)
    except Exception:
        pass
    return (
        data.get("status", "OFFLINE"),
        data.get("last_name", ""),
        len(data.get("cart", [])),
        data.get("total", 0.0),
        is_running("barcode_scanner"),
    )


# ═══════════════════════════════════════════════════════════════
# SCREEN: BLE RADAR
# ═══════════════════════════════════════════════════════════════

def render_radar(fonts):
    f_big, f_med, f_sm = fonts
    SCALE        = 50
    RX, RY       = W // 2, 240
    BAR_Y, BAR_W = 276, 90
    GRID_C       = (22, 22, 38)
    RING_C       = (0,  60,  0)

    now    = time.time()
    state  = ble_scanner.get_state()
    rl     = state["rssi_l"]
    rr     = state["rssi_r"]
    lost_l = (now - state["ts_l"]) > ble_scanner.BLE_LOST_SECS
    lost_r = (now - state["ts_r"]) > ble_scanner.BLE_LOST_SECS
    lc = (0, 200, 110) if not lost_l else GRAY
    rc = (210, 195, 0) if not lost_r else GRAY

    hp = max(10, int(ble_scanner.BLE_SEPARATION / 2 * SCALE))

    with fb_lock:
        fill_rect(0, 0, W, H, BG)
        draw_header("BLE RADAR", fonts)

        for gx in range(0, W, 80):
            _d.line([(gx, 52), (gx, 297)], fill=GRID_C)
        for gy in range(52, 297, 80):
            _d.line([(0, gy), (W, gy)], fill=GRID_C)

        for r in (1.0, 2.0, 3.0):
            px = int(r * SCALE)
            _d.ellipse([RX-px, RY-px, RX+px, RY+px], outline=RING_C, width=1)
            if RY - px > 54:
                draw_text(RX+px+3, RY-px-7, f"{r:.0f}m", (0, 90, 0), f_sm)

        _d.line([(RX, RY), (RX, 54)], fill=(38, 38, 60))

        _d.polygon([(RX-hp, RY-6), (RX-hp-10, RY), (RX-hp, RY+6)], fill=lc)
        _d.polygon([(RX+hp, RY-6), (RX+hp+10, RY), (RX+hp, RY+6)], fill=rc)
        draw_text(RX-hp-16, RY-20, "L", lc, f_sm)
        draw_text(RX+hp+12, RY-20, "R", rc, f_sm)

        fill_rect(RX-12, RY-9, 24, 18, (0, 140, 240))
        _d.polygon([(RX-6, RY-9), (RX+6, RY-9), (RX, RY-20)], fill=(0, 140, 240))

        if rl is not None and rr is not None and not lost_l and not lost_r:
            x_m, y_m = ble_scanner.position(rl, rr)
            sx = max(10, min(W-10, RX + int(x_m * SCALE)))
            sy = max(56, min(294, RY - int(y_m * SCALE)))
            _ble_trail.append((sx, sy))
            if len(_ble_trail) > 14:
                _ble_trail.pop(0)
            for i, (tx, ty) in enumerate(_ble_trail[:-1]):
                frac = (i + 1) / 14
                r_px = max(2, int(5 * frac))
                col  = (int(110*frac), int(12*frac), int(12*frac))
                _d.ellipse([tx-r_px, ty-r_px, tx+r_px, ty+r_px], fill=col)
            _d.ellipse([sx-8, sy-8, sx+8, sy+8], fill=RED)
            _d.ellipse([sx-3, sy-3, sx+3, sy+3], fill=(255, 200, 200))
            dist    = math.hypot(x_m, y_m)
            bearing = math.degrees(math.atan2(x_m, max(0.01, y_m)))
            draw_text(sx+11, sy-7, f"{dist:.1f}m  {bearing:+.0f}°", GRAY, f_sm)
        else:
            _ble_trail.clear()
            draw_text(W//2-55, 155, "SEARCHING...", YELLOW, f_med)

        if rl is not None:
            fw = int(BAR_W * max(0.0, min(1.0, (rl + 85.0) / 55.0)))
            fill_rect(8, BAR_Y, BAR_W, 12, (30, 30, 50))
            if fw > 0: fill_rect(8, BAR_Y, fw, 12, lc)
            draw_text(8+BAR_W+4, BAR_Y, f"L: {rl:.0f} dBm", lc, f_sm)
        else:
            draw_text(8, BAR_Y, "L: --", GRAY, f_sm)
        if rr is not None:
            fw = int(BAR_W * max(0.0, min(1.0, (rr + 85.0) / 55.0)))
            fill_rect(W-8-BAR_W, BAR_Y, BAR_W, 12, (30, 30, 50))
            if fw > 0: fill_rect(W-8-BAR_W, BAR_Y, fw, 12, rc)
            draw_text(W-8-BAR_W-80, BAR_Y, f"R: {rr:.0f} dBm", rc, f_sm)
        else:
            draw_text(W-55, BAR_Y, "R: --", GRAY, f_sm)

        draw_footer("O  Back", fonts)

def _radar_snapshot():
    """Cheap fingerprint of radar state, rounded so tiny RSSI jitter doesn't
    force a redraw every tick."""
    state = ble_scanner.get_state()
    rl, rr = state["rssi_l"], state["rssi_r"]
    return (
        round(rl) if rl is not None else None,
        round(rr) if rr is not None else None,
        state["ts_l"], state["ts_r"],
    )


# ═══════════════════════════════════════════════════════════════
# SCREEN: USB MODULE
# ═══════════════════════════════════════════════════════════════

def render_usb_module(fonts):
    f_big, f_med, f_sm = fonts
    now = time.time()
    mod = usb_module.get_state()

    connected = (mod["type"] is not None
                 and mod["ts"] > 0
                 and (now - mod["ts"]) < usb_module.USB_LOST_SECS)

    with fb_lock:
        fill_rect(0, 0, W, H, BG)
        title = mod["label"].upper() if connected and mod["label"] else "USB MODULE"
        draw_header(title, fonts)

        if not connected:
            draw_text(20, 100, "NO MODULE DETECTED", GRAY, f_med)
            draw_text(20, 130, "Connect a module to the USB port", GRAY, f_sm)
            draw_text(20, 150, "on top of the robot.", GRAY, f_sm)

        elif mod["type"] == "weight":
            val = mod["value"] if isinstance(mod["value"], (int, float)) else None

            fill_rect(8, 54, W-16, 28, PANEL)
            fill_rect(8, 54, 4,    28, GREEN)
            draw_text(16, 61, f"LIVE  {mod['port'] or ''}", GREEN, f_sm)
            draw_hline(0, 86, W, DIVIDER)

            draw_text(20, 95, "WEIGHT", GRAY, f_sm)
            if val is not None:
                reading = f"{val / 1000:.2f} kg" if val >= 1000 else f"{val:.0f} g"
                col     = RED if val > 19000 else YELLOW if val > 15000 else CYAN
                draw_text(20, 112, reading, col, f_big)
            else:
                draw_text(20, 112, "---", GRAY, f_big)

            BX, BY, BW, BH = 20, 215, W-40, 18
            fill_rect(BX, BY, BW, BH, (30, 30, 50))
            if val is not None:
                fw      = int(BW * max(0.0, min(val / 20000.0, 1.0)))
                bar_col = RED if val > 19000 else YELLOW if val > 15000 else CYAN
                if fw > 0:
                    fill_rect(BX, BY, fw, BH, bar_col)
            draw_text(BX,       BY + BH + 5, "0 g",   GRAY, f_sm)
            draw_text(BX+BW-40, BY + BH + 5, "20 kg", GRAY, f_sm)

            draw_text(20, 258, "PORT", GRAY, f_sm)
            draw_text(80, 258, mod["port"] or "N/A", WHITE, f_sm)

        elif mod["type"] == "arm":
            val = mod["value"] if isinstance(mod["value"], dict) else {}
            if not isinstance(val, dict):
                val = {}

            fill_rect(8, 54, W-16, 28, PANEL)
            fill_rect(8, 54, 4,    28, ORANGE)
            draw_text(16, 61, f"LIVE  {mod['port'] or ''}", ORANGE, f_sm)
            draw_hline(0, 86, W, DIVIDER)
            draw_text(20, 92, "SERVO POSITIONS", GRAY, f_sm)

            servos = ["base", "firstLeg", "secondLeg", "thirdLeg", "claw", "clawAngle"]
            for i, sname in enumerate(servos):
                cx = 20 if i % 2 == 0 else W // 2 + 10
                cy = 110 + (i // 2) * 60
                angle = val.get(sname)
                draw_text(cx, cy, sname, GRAY, f_sm)
                if angle is not None:
                    pct = angle / 180.0
                    col = RED if pct > 0.9 else YELLOW if pct > 0.6 else CYAN
                    draw_text(cx, cy + 16, f"{angle}°", col, f_med)
                    fill_rect(cx, cy + 40, 90, 6, (30, 30, 50))
                    fill_rect(cx, cy + 40, max(1, int(90 * pct)), 6, col)
                else:
                    draw_text(cx, cy + 16, "--°", GRAY, f_med)

            vcmd, vts = voice_module.get_last_command()
            if vcmd and (time.time() - vts) < 4.0:
                draw_text(20, 293, f"mic: {vcmd}", ORANGE, f_sm)
            else:
                draw_text(20, 293, "mic: listening...", GRAY, f_sm)

        draw_footer("O  Back", fonts)

def _usb_snapshot():
    now = time.time()
    mod = usb_module.get_state()
    connected = (mod["type"] is not None
                 and mod["ts"] > 0
                 and (now - mod["ts"]) < usb_module.USB_LOST_SECS)
    vcmd, vts = voice_module.get_last_command()
    return (
        connected, mod["type"], mod["port"],
        json.dumps(mod["value"], sort_keys=True) if isinstance(mod["value"], dict) else mod["value"],
        vcmd, round(vts, 1),
    )


# ═══════════════════════════════════════════════════════════════
# DISPLAY MIRROR STREAM  (http://<pi-ip>:8081/)
# ═══════════════════════════════════════════════════════════════

_flask = Flask(__name__)

@_flask.route("/")
def _stream_index():
    return (
        '<html><head><title>Buddy Bot Display</title>'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '<style>'
        '  body { margin:0; background:#0b0b14; color:white; font-family:sans-serif; '
        '         display:flex; flex-direction:column; align-items:center; height:100vh; }'
        '  #stream { max-width:100%; max-height:55vh; border-bottom:2px solid #282841; }'
        '  .controls { display:flex; gap: 40px; margin-top: 20px; width: 100%; max-width: 480px; justify-content: center; }'
        '  .col { display:flex; flex-direction:column; gap: 15px; }'
        '  .btn { background:#1c1c2e; color:#00b4ff; border:2px solid #282841; padding:15px 25px; '
        '         font-size:18px; font-weight:bold; border-radius:8px; cursor:pointer; user-select:none; touch-action:manipulation; }'
        '  .btn:active { background:#00b4ff; color:#fff; }'
        '  .btn-action { color:#ffc832; }'
        '  .btn-danger { color:#dc3c3c; }'
        '</style>'
        '<script>'
        '  function sendCmd(act) { fetch("/action/" + act); }'
        '</script>'
        '</head><body>'
        '<img id="stream" src="/stream">'
        '<div class="controls">'
        '  <div class="col">'
        '    <button class="btn" onclick="sendCmd(\'up\')">▲ UP</button>'
        '    <button class="btn" onclick="sendCmd(\'down\')">▼ DOWN</button>'
        '  </div>'
        '  <div class="col">'
        '    <button class="btn btn-action" onclick="sendCmd(\'select\')">X SELECT</button>'
        '    <button class="btn btn-danger" onclick="sendCmd(\'back\')">O BACK</button>'
        '    <button class="btn" style="color:#32dc64;" onclick="sendCmd(\'launch_stop\')">△ LAUNCH/STOP</button>'
        '  </div>'
        '</div>'
        '</body></html>'
    )

@_flask.route("/action/<act>")
def _stream_action(act):
    # Valid actions match the controller events exactly
    if act in ("up", "down", "select", "back", "launch_stop"):
        _action_q.put(act)
    return "OK", 200

@_flask.route("/stream")
def _stream_feed():
    def _generate():
        while _running:
            with fb_lock:
                snap = fb.copy()
            buf = io.BytesIO()
            snap.save(buf, format="JPEG", quality=70)
            frame = buf.getvalue()
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
            time.sleep(1 / 15)
    return Response(_generate(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

def stream_thread_func():
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    _flask.run(host="0.0.0.0", port=STREAM_PORT, threaded=True,
               debug=False, use_reloader=False)

# ═══════════════════════════════════════════════════════════════
# DISPLAY THREAD
# ═══════════════════════════════════════════════════════════════

_running    = True
_screen     = "main"
_menu_sel   = 0
_cur_script = None

_force_redraw = True
_force_lock   = threading.Lock()

def _mark_dirty():
    global _force_redraw
    with _force_lock:
        _force_redraw = True


def _handle(action):
    global _screen, _menu_sel, _cur_script

    if _screen == "main":
        if   action == "up":     _menu_sel = (_menu_sel - 1) % len(MENU_ITEMS)
        elif action == "down":   _menu_sel = (_menu_sel + 1) % len(MENU_ITEMS)
        elif action == "select":
            _, screen_key, script = MENU_ITEMS[_menu_sel]
            _screen     = screen_key
            _cur_script = script

    elif _screen == "overview":
        if action == "back": _screen = "main"

    elif _screen == "robot":
        if action == "back": _screen = "main"
        elif action == "launch_stop":
            name = _cur_script or "buddy_bot"
            stop(name) if is_running(name) else launch(name)

    elif _screen == "radar":
        if action == "back": _screen = "main"

    elif _screen == "barcode":
        if action == "back": _screen = "main"
        elif action == "launch_stop":
            name = "barcode_scanner"
            stop(name) if is_running(name) else launch(name)

    elif _screen == "usb_module":
        if action == "back": _screen = "main"

    elif _screen == "shutdown":
        os.system("sudo reboot")


def display_thread_func(fonts):
    global _force_redraw

    _target_dt = 1.0 / 10
    prev_screen = None

    last_radar_snap   = None
    last_barcode_snap = None
    last_usb_snap     = None
    last_overview_min = None

    last_radar_paint   = 0.0
    last_barcode_paint = 0.0
    last_overview_paint = 0.0

    while _running:
        t0 = time.monotonic()

        has_input = False
        while True:
            try:
                _handle(_action_q.get_nowait())
                has_input = True
            except queue.Empty:
                break

        if has_input:
            _mark_dirty()

        screen_changed = (_screen != prev_screen)
        if screen_changed:
            _mark_dirty()
            prev_screen = _screen

        with _force_lock:
            forced = _force_redraw
            _force_redraw = False

        now = time.monotonic()
        do_render = forced

        if not do_render:
            if _screen == "radar":
                if now - last_radar_paint >= RADAR_MIN_PERIOD:
                    snap = _radar_snapshot()
                    if snap != last_radar_snap:
                        do_render = True
            elif _screen == "barcode":
                if now - last_barcode_paint >= BARCODE_MIN_PERIOD:
                    snap = _barcode_snapshot()
                    cam_changed = False
                    if is_running("barcode_scanner"):
                        try:
                            cam_changed = os.path.getmtime(CAM_FRAME_PATH) != _last_cam_mtime
                        except OSError:
                            pass
                    if snap != last_barcode_snap or cam_changed:
                        do_render = True
            elif _screen == "overview":
                if now - last_overview_paint >= OVERVIEW_PERIOD:
                    do_render = True
            elif _screen == "usb_module":
                snap = _usb_snapshot()
                if snap != last_usb_snap:
                    do_render = True
            elif _screen == "robot":
                do_render = True 

        if do_render:
            if   _screen == "main":       render_main(fonts, _menu_sel)
            elif _screen == "overview":
                render_overview(fonts)
                last_overview_paint = now
            elif _screen == "robot":      render_robot(fonts)
            elif _screen == "radar":
                render_radar(fonts)
                last_radar_snap  = _radar_snapshot()
                last_radar_paint = now
            elif _screen == "barcode":
                render_barcode(fonts)
                last_barcode_snap  = _barcode_snapshot()
                last_barcode_paint = now
            elif _screen == "usb_module":
                render_usb_module(fonts)
                last_usb_snap = _usb_snapshot()

            flush()

        dt = time.monotonic() - t0
        time.sleep(max(0.010, _target_dt - dt))

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    global _spi, _running

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(DC,  GPIO.OUT)
    GPIO.setup(RST, GPIO.OUT)
    _spi = spidev.SpiDev()
    _spi.open(0, 0)
    _spi.max_speed_hz = 32_000_000
    _spi.mode = 0
    init_display()

    base = "/usr/share/fonts/truetype/dejavu/"
    try:
        fonts = (
            ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 46),
            ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 24),
            ImageFont.truetype(base + "DejaVuSans.ttf",      14),
        )
    except IOError:
        d = ImageFont.load_default()
        fonts = (d, d, d)

    ble_scanner.start()
    usb_module.start()
    voice_module.start()

    threads = [
        threading.Thread(target=input_thread_func,   daemon=True),
        threading.Thread(target=stats_thread_func,   daemon=True),
        threading.Thread(target=display_thread_func, args=(fonts,), daemon=True),
        threading.Thread(target=stream_thread_func,  daemon=True),
    ]
    for t in threads:
        t.start()

    print(f"Display running — stream at http://0.0.0.0:{STREAM_PORT}/  — Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        _running = False
        voice_module.stop()
        ble_scanner.stop()
        usb_module.stop()
        for t in threads:
            t.join(timeout=2)
        stop_all()
        GPIO.cleanup()
        _spi.close()
        print("Stopped.")


if __name__ == "__main__":
    main()
