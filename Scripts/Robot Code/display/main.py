import time, spidev, RPi.GPIO as GPIO
import display as D
import module_overview as overview
import module_basket   as basket
import module_arm      as arm

# ── Detection flags — flip these from your detection code later ─
basket_detected = False
arm_connected   = True

def active_module():
    if basket_detected: return basket
    if arm_connected:   return arm
    return overview

def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(D.DC,  GPIO.OUT)
    GPIO.setup(D.RST, GPIO.OUT)

    D.spi = spidev.SpiDev()
    D.spi.open(0, 0)
    D.spi.max_speed_hz = 32_000_000
    D.spi.mode = 0

    D.init()
    fonts = D.load_fonts()

    # Push flags into modules
    basket.basket_detected = basket_detected
    arm.arm_connected      = arm_connected

    print("Running — Ctrl+C to stop.")
    try:
        while True:
            active_module().render(fonts)
            D.flush()
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
        D.spi.close()

if __name__ == "__main__":
    main()