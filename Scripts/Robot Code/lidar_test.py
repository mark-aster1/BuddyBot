import serial

ser = serial.Serial('/dev/ttyAMA0', 115200, timeout=1)

print("Reading LiDAR data...\n")

while True:
    data = ser.read(64)
    if data:
        print(' '.join(f'{b:02X}' for b in data))
