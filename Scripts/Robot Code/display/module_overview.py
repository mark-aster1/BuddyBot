import time, subprocess
from datetime import datetime, timedelta
import display as D

def _read(path, default=0.0):
    try:    return open(path).read().strip()
    except: return str(default)

def get_temp():
    return float(_read("/sys/class/thermal/thermal_zone0/temp", 0)) / 1000

def get_voltage():
    try:
        raw = subprocess.check_output(["vcgencmd", "measure_volts", "core"], text=True)
        return float(raw.split("=")[1].rstrip("V\n"))
    except: return 0.0

def get_cpu_pct():
    def stat():
        f = open("/proc/stat").readline().split()
        t = sum(int(x) for x in f[1:])
        return t, int(f[4])
    t1, i1 = stat(); time.sleep(0.15); t2, i2 = stat()
    dt = t2 - t1
    return 100 * (1 - (i2 - i1) / dt) if dt else 0

def get_ram():
    m = {l.split()[0].rstrip(":"): int(l.split()[1]) for l in open("/proc/meminfo")}
    used = m["MemTotal"] - m["MemAvailable"]
    return 100 * used // m["MemTotal"], used // 1024, m["MemTotal"] // 1024

def get_freq():
    try:    return int(_read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", 0)) // 1000
    except: return 0

def get_uptime():
    secs = float(open("/proc/uptime").read().split()[0])
    return str(timedelta(seconds=int(secs)))

def render(fonts):
    now                      = datetime.now()
    temp                     = get_temp()
    voltage                  = get_voltage()
    cpu                      = get_cpu_pct()
    ram_pct, ram_used, ram_t = get_ram()
    freq                     = get_freq()
    uptime                   = get_uptime()

    tc = D.RED if temp    > 75 else D.YELLOW if temp    > 60 else D.GREEN
    cc = D.RED if cpu     > 80 else D.YELLOW if cpu     > 50 else D.GREEN
    rc = D.RED if ram_pct > 80 else D.YELLOW if ram_pct > 60 else D.GREEN

    D.clear()
    D.draw_header("SYSTEM OVERVIEW", now.strftime("%H:%M:%S"), fonts)

    # Big clock
    D.draw_text(10, 42, now.strftime("%H:%M:%S"),        D.WHITE,  fonts['big'])
    D.draw_text(10, 92, now.strftime("%A  %d %B %Y"),    D.GRAY,   fonts['sm'])
    D.draw_hline(0, 110, D.W, D.LINE)

    # Two-column stats grid
    x1, x2 = 10, 252
    D.draw_vline(243, 110, D.FOOTER_Y - 110, D.LINE)

    rows = [
        (x1, "CPU TEMP",     f"{temp:.1f} °C",      tc,       temp / 85 * 100, tc),
        (x1, "CPU USAGE",    f"{cpu:.1f} %",         cc,       cpu,             cc),
        (x1, "RAM",          f"{ram_used}/{ram_t}MB", rc,      ram_pct,         rc),
    ]
    right = [
        (x2, "CORE VOLTAGE", f"{voltage:.4f} V",    D.CYAN),
        (x2, "CPU FREQ",     f"{freq} MHz",          D.ORANGE),
        (x2, "UPTIME",       uptime,                 D.WHITE),
    ]

    for i, (x, label, val, vc, bar_pct, bc) in enumerate(rows):
        y = 118 + i * 60
        D.draw_text(x, y,      label,   D.GRAY, fonts['sm'])
        D.draw_text(x, y + 15, val,     vc,     fonts['med'])
        D.draw_bar( x, y + 42, 220, 10, bar_pct, bc)

    for i, (x, label, val, vc) in enumerate(right):
        y = 118 + i * 60
        D.draw_text(x, y,      label, D.GRAY, fonts['sm'])
        D.draw_text(x, y + 15, val,   vc,     fonts['med'])

    D.draw_footer("Raspberry Pi 3B+", fonts)