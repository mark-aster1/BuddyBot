import spidev, RPi.GPIO as GPIO, time
from PIL import Image, ImageDraw

DC_PIN, RST_PIN = 24, 25
W, H = 480, 320

_spi = spidev.SpiDev()
def _cmd(c): GPIO.output(DC_PIN,0); _spi.xfer([c])
def _dat(d):  GPIO.output(DC_PIN,1); _spi.xfer(list(d))
def _wr(c,*d): _cmd(c); (_dat(d) if d else None)

GPIO.setmode(GPIO.BCM)
GPIO.setup(DC_PIN, GPIO.OUT)
GPIO.setup(RST_PIN, GPIO.OUT)
_spi.open(0,0); _spi.max_speed_hz=32_000_000; _spi.mode=0
GPIO.output(RST_PIN,0); time.sleep(0.05)
GPIO.output(RST_PIN,1); time.sleep(0.15)
_wr(0x01); time.sleep(0.12)
_wr(0x36,0xE8); _wr(0x3A,0x55)
_wr(0x11); time.sleep(0.12); _wr(0x29)

img = Image.new("RGB",(W,H),(255,0,0))  # solid red
_cmd(0x2A); _dat([0x00,0x00,(W-1)>>8,(W-1)&0xFF])
_cmd(0x2B); _dat([0x00,0x00,(H-1)>>8,(H-1)&0xFF])
_cmd(0x2C)
GPIO.output(DC_PIN,1)
data = img.tobytes()
buf = bytearray(W*H*2); j=0
for i in range(0,len(data),3):
    r,g,b = data[i],data[i+1],data[i+2]
    v = ((r&0xF8)<<8)|((g&0xFC)<<3)|(b>>3)
    buf[j]=v>>8; buf[j+1]=v&0xFF; j+=2
for off in range(0,len(buf),4096):
    _spi.xfer(list(buf[off:off+4096]))

print("done")
GPIO.cleanup()
