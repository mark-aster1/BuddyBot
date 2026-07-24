import serial
import threading

PORT = "/dev/ttyACM2"
BAUD = 115200

try:
    ser = serial.Serial(PORT, BAUD, timeout=1)
    print(f"Connected to {PORT}")

except serial.SerialException as e:
    print(f"Connection error: {e}")
    exit()


def read_serial():
    while True:
        try:
            if ser.in_waiting:
                line = ser.readline().decode(
                    'utf-8',
                    errors='replace'
                ).strip()

                if line:
                    print(f"\n[RX] {line}")

        except Exception as e:
            print(f"Read error: {e}")
            break


reader_thread = threading.Thread(
    target=read_serial,
    daemon=True
)

reader_thread.start()

try:
    while True:
        msg = input("[TX] Enter message: ")

        ser.write((msg + "\n").encode())

except KeyboardInterrupt:
    print("\nStopped.")
    ser.close()
