import time, spidev, RPi.GPIO as GPIO
import numpy as np
from PIL import Image, ImageDraw, ImageFont

DC, RST = 24, 25
W, H    = 480, 320

# ── Framebuffer ───────────────────────────────────────────────
fb  = Image.new("RGB", (W, H))
_d  = ImageDraw.Draw(fb)
spi = None   # set by main.py

# ── Colors ────────────────────────────────────────────────────
BG     = (10,  10,  20)
WHITE  = (255, 255, 255)
GRAY   = (90,  90, 110)
GREEN  = (50,  220, 100)
YELLOW = (255, 200,  50)
RED    = (220,  60,  60)
CYAN   = (0,   200, 255)
ORANGE = (255, 140,   0)
BLUE   = (80,  140, 255)
PURPLE = (160,  80, 255)
DARK   = (20,  20,  40)
LINE   = (40,  40,  65)

# ── Primitives ────────────────────────────────────────────────
def draw_pixel(x, y, color):
    fb.putpixel((x, y), color)

def fill_rect(x, y, w, h, color):
    _d.rectangle([x, y, x + w - 1, y + h - 1], fill=color)

def draw_hline(x, y, length, color):
    _d.line([(x, y), (x + length - 1, y)], fill=color)

def draw_vline(x, y, length, color):
    _d.line([(x, y), (x, y + length - 1)], fill=color)

def draw_text(x, y, text, color, font):
    _d.text((x, y), text, fill=color, font=font)

def draw_bar(x, y, w, h, pct, color, bg=(35, 35, 55)):
    fill_rect(x, y, w, h, bg)
    fw = int(w * max(0, min(pct, 100)) / 100)
    if fw > 0:
        fill_rect(x, y, fw, h, color)

def clear():
    fill_rect(0, 0, W, H, BG)

# ── Common UI chrome ──────────────────────────────────────────
HEADER_H = 36
FOOTER_Y = H - 22

def draw_header(title, right_text, fonts):
    fill_rect(0, 0, W, HEADER_H, DARK)
    draw_text(10, 9, title, WHITE, fonts['med'])
    if right_text:
        tw = int(fonts['sm'].getlength(right_text))
        draw_text(W - tw - 10, 11, right_text, GRAY, fonts['sm'])
    draw_hline(0, HEADER_H, W, LINE)

def draw_footer(text, fonts):
    draw_hline(0, FOOTER_Y, W, LINE)
    fill_rect(0, FOOTER_Y + 1, W, H - FOOTER_Y - 1, DARK)
    draw_text(10, FOOTER_Y + 4, text, GRAY, fonts['sm'])

# ── SPI / display ─────────────────────────────────────────────
def _cmd(c): GPIO.output(DC, GPIO.LOW);  spi.xfer2([c])
def _dat(d): GPIO.output(DC, GPIO.HIGH); spi.xfer2(d if isinstance(d, list) else [d])

def flush():
    _cmd(0x2A); _dat([0, 0, (W-1)>>8, (W-1)&0xFF])
    _cmd(0x2B); _dat([0, 0, (H-1)>>8, (H-1)&0xFF])
    _cmd(0x2C)
    GPIO.output(DC, GPIO.HIGH)
    arr = (np.array(fb, dtype=np.uint8) & 0xFC).flatten().tolist()
    for i in range(0, len(arr), 4096):
        spi.xfer2(arr[i:i + 4096])

def init():
    for v in (GPIO.HIGH, GPIO.LOW, GPIO.HIGH):
        GPIO.output(RST, v); time.sleep(0.1)
    _cmd(0xE0); _dat([0x00,0x07,0x0F,0x0D,0x1B,0x0A,0x3C,0x78,0x4A,0x07,0x0E,0x09,0x1B,0x1E,0x0F])
    _cmd(0xE1); _dat([0x00,0x22,0x24,0x06,0x12,0x07,0x36,0x47,0x47,0x06,0x0A,0x07,0x30,0x37,0x0F])
    _cmd(0xC0); _dat([0x10, 0x10])
    _cmd(0xC1); _dat([0x41])
    _cmd(0xC5); _dat([0x00, 0x22, 0x80])
    _cmd(0x36); _dat([0x28])    # landscape
    _cmd(0x3A); _dat([0x66])    # 18-bit color
    _cmd(0xB0); _dat([0x00])
    _cmd(0xB1); _dat([0xA0])
    _cmd(0xB4); _dat([0x02])
    _cmd(0xB6); _dat([0x02, 0x02, 0x3B])
    _cmd(0xB7); _dat([0xC6])
    _cmd(0xF7); _dat([0xA9, 0x51, 0x2C, 0x82])
    _cmd(0x11); time.sleep(0.12)
    _cmd(0x29); time.sleep(0.02)

def load_fonts():
    base = "/usr/share/fonts/truetype/dejavu/"
    try:
        return {
            'big': ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 44),
            'med': ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 22),
            'sm':  ImageFont.truetype(base + "DejaVuSans.ttf",      13),
        }
    except IOError:
        d = ImageFont.load_default()
        return {'big': d, 'med': d, 'sm': d}