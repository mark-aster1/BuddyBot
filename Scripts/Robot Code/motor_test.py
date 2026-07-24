import RPi.GPIO as GPIO
from adafruit_pca9685 import PCA9685
import board, busio, time

i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 1500
print("PCA9685 OK")

GPIO.setmode(GPIO.BCM)
EN_PINS = [26, 19, 16, 6]
for pin in EN_PINS:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.HIGH)
print("EN pins HIGH")

def set_motor(rpwm_ch, lpwm_ch, speed):
    full = 0xFFFF
    if speed > 0:
        pca.channels[rpwm_ch].duty_cycle = int(full * speed / 100)
        pca.channels[lpwm_ch].duty_cycle = 0
    elif speed < 0:
        pca.channels[rpwm_ch].duty_cycle = 0
        pca.channels[lpwm_ch].duty_cycle = int(full * -speed / 100)
    else:
        pca.channels[rpwm_ch].duty_cycle = 0
        pca.channels[lpwm_ch].duty_cycle = 0

def stop_all():
    set_motor(4, 5, 0)
    set_motor(0, 1, 0)
    print("Motors stopped.")

try:
    print("Setting motor to 100%...")
    set_motor(4, 5, 100)
    set_motor(0, 1, 100)
    time.sleep(1)
    print("Stopping")
finally:
    stop_all()
    pca.deinit()
    GPIO.cleanup()
