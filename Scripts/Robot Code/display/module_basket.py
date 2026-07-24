from datetime import datetime
import display as D

# ── Toggle this when your detection is ready ──────────────────
basket_detected = False

# Placeholder data — replace with real scan data later
ITEMS = [
    ("Apple",       3,  0.150),
    ("Milk 1L",     1,  1.020),
    ("Bread",       1,  0.380),
    ("Cheese",      1,  0.250),
    ("Yogurt",      2,  0.400),
]

def render(fonts):
    now = datetime.now()
    D.clear()
    D.draw_header("SHOPPING BASKET", now.strftime("%H:%M:%S"), fonts)

    if not basket_detected:
        D.draw_text(130, 110, "No basket detected",  D.GRAY, fonts['med'])
        D.draw_text(160, 140, "Waiting...",          D.GRAY, fonts['sm'])
        # Simple basket shape using draw_pixel
        bx, by = D.W // 2 - 45, 190
        for x in range(bx, bx + 90):
            D.draw_pixel(x, by,      D.GRAY)   # top edge
            D.draw_pixel(x, by + 50, D.GRAY)   # bottom
        for y in range(by, by + 51):
            D.draw_pixel(bx,      y, D.GRAY)   # left
            D.draw_pixel(bx + 90, y, D.GRAY)   # right
        # Handle
        for x in range(bx + 25, bx + 65):
            D.draw_pixel(x, by - 15, D.GRAY)
        D.draw_footer("Place basket under camera", fonts)
        return

    # Table header
    y = D.HEADER_H + 4
    D.draw_text(10,  y, "ITEM",    D.GRAY, fonts['sm'])
    D.draw_text(300, y, "QTY",     D.GRAY, fonts['sm'])
    D.draw_text(360, y, "WEIGHT",  D.GRAY, fonts['sm'])
    y += 16
    D.draw_hline(0, y, D.W, D.LINE)
    y += 4

    total_weight = 0.0
    total_items  = 0
    for name, qty, weight_each in ITEMS:
        total_w = qty * weight_each
        D.draw_text(10,  y, name,                D.WHITE,  fonts['sm'])
        D.draw_text(300, y, f"x{qty}",           D.CYAN,   fonts['sm'])
        D.draw_text(360, y, f"{total_w:.3f} kg", D.GREEN,  fonts['sm'])
        total_weight += total_w
        total_items  += qty
        y += 18
        if y > D.FOOTER_Y - 80:
            D.draw_text(10, y, "...", D.GRAY, fonts['sm'])
            break

    D.draw_hline(0, y + 4, D.W, D.LINE)
    y += 10

    D.draw_text(10,  y, f"{total_items} items",    D.WHITE,  fonts['med'])
    D.draw_text(280, y, f"{total_weight:.3f} kg",  D.GREEN,  fonts['med'])

    # Weight bar  (0–5 kg scale)
    D.draw_text(10, y + 32, "TOTAL WEIGHT  (5 kg max)", D.GRAY, fonts['sm'])
    D.draw_bar(10, y + 48, D.W - 20, 14, total_weight / 5 * 100, D.GREEN)

    D.draw_footer("Basket detected — scanning active", fonts)