from datetime import datetime
import display as D

# ── Toggle these when your ESP32 is ready ─────────────────────
arm_connected = False

# Placeholder data — replace with real serial reads later
arm_data = {
    "status": "IDLE",      # IDLE | MOVING | ERROR
    "speed":  50,          # %
    "load":   18,          # % of rated load
    "temp":   38.5,        # motor temp °C
    "joints": [45, -30, 90, 0, 15, -45],   # J1–J6 degrees
    "x": 120.5,  "y": 45.2,  "z": 89.3,   # TCP position mm
}

STATUS_COLORS = {"IDLE": D.GREEN, "MOVING": D.YELLOW, "ERROR": D.RED}

def render(fonts):
    now = datetime.now()
    a   = arm_data
    D.clear()
    D.draw_header("MECHANICAL ARM", now.strftime("%H:%M:%S"), fonts)

    if not arm_connected:
        D.draw_text(100, 110, "ESP32 not connected",  D.GRAY, fonts['med'])
        D.draw_text(140, 140, "Check USB cable",      D.GRAY, fonts['sm'])
        # Simple arm sketch using lines of pixels
        # Base
        for x in range(180, 300): D.draw_pixel(x, 240, D.GRAY)
        # Vertical segment
        for y in range(200, 240): D.draw_pixel(240, y, D.GRAY)
        # Horizontal segment
        for x in range(240, 310): D.draw_pixel(x, 200, D.GRAY)
        # Wrist
        for y in range(180, 200): D.draw_pixel(310, y, D.GRAY)
        # Tool
        for x in range(295, 325): D.draw_pixel(x, 180, D.GRAY)
        D.draw_footer("Waiting for ESP32 on USB...", fonts)
        return

    sc = STATUS_COLORS.get(a["status"], D.GRAY)
    lc = D.RED if a["load"] > 80 else D.YELLOW if a["load"] > 50 else D.GREEN

    # ── Status bar ────────────────────────────────────────────
    y = D.HEADER_H + 6
    D.draw_text(10,  y, "STATUS",        D.GRAY,   fonts['sm'])
    D.draw_text(10,  y+15, a["status"],  sc,       fonts['med'])

    D.draw_text(130, y, "SPEED",         D.GRAY,   fonts['sm'])
    D.draw_text(130, y+15, f"{a['speed']} %", D.ORANGE, fonts['med'])
    D.draw_bar( 130, y+40, 100, 8, a["speed"], D.ORANGE)

    D.draw_text(265, y, "LOAD",          D.GRAY,   fonts['sm'])
    D.draw_text(265, y+15, f"{a['load']} %", lc,  fonts['med'])
    D.draw_bar( 265, y+40, 100, 8, a["load"],  lc)

    D.draw_text(390, y, "MOTOR TEMP",    D.GRAY,   fonts['sm'])
    tc = D.RED if a["temp"] > 70 else D.YELLOW if a["temp"] > 55 else D.GREEN
    D.draw_text(390, y+15, f"{a['temp']:.1f}°C", tc, fonts['med'])

    D.draw_hline(0, y + 56, D.W, D.LINE)

    # ── Joints ────────────────────────────────────────────────
    y += 64
    D.draw_text(10, y, "JOINT ANGLES", D.GRAY, fonts['sm'])
    y += 16

    for i, angle in enumerate(a["joints"]):
        col = i % 3
        row = i // 3
        px  = 10  + col * 158
        py  = y   + row * 50
        jc  = D.YELLOW if abs(angle) > 60 else D.WHITE
        D.draw_text(px,    py,    f"J{i+1}",        D.GRAY, fonts['sm'])
        D.draw_text(px+26, py,    f"{angle:+.0f}°", jc,     fonts['med'])
        # ±180° shown as 0–100%
        D.draw_bar(px, py + 24, 148, 7, (angle + 180) / 360 * 100, jc)

    D.draw_hline(0, y + 106, D.W, D.LINE)

    # ── TCP position ──────────────────────────────────────────
    y += 112
    D.draw_text(10,  y, f"X  {a['x']:+7.1f} mm", D.CYAN, fonts['med'])
    D.draw_text(170, y, f"Y  {a['y']:+7.1f} mm", D.CYAN, fonts['med'])
    D.draw_text(330, y, f"Z  {a['z']:+7.1f} mm", D.CYAN, fonts['med'])

    D.draw_footer(f"ESP32 connected  |  motor {a['temp']:.1f}°C", fonts)