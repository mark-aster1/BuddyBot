import cv2
import time
import select
import threading
import math
import subprocess

import board
import RPi.GPIO as GPIO
import busio
import json

BUDDYBOT_STATUS = "/tmp/buddybot_status.json"
BUDDYBOT_CMD    = "/tmp/buddybot_cmd.json"

from flask import Flask, Response
from adafruit_pca9685 import PCA9685
from evdev import InputDevice, list_devices, ecodes

cv2.setNumThreads(4)

# ============================================================
# SETTINGS
# ============================================================

CAMERA_WIDTH  = 640
CAMERA_HEIGHT = 480

FRAME_WIDTH  = 160
FRAME_HEIGHT = 120
CENTER_X     = FRAME_WIDTH // 2

STREAM_WIDTH  = 640
STREAM_HEIGHT = 480

STREAM_PORT  = 8080
JPEG_QUALITY = 80

CROP_TOP    = 0
CROP_BOTTOM = 0

CAMERA_DEVICES = [
    "/dev/video1",
    "/dev/video2",
    "/dev/video0",
]

DEAD_ZONE        = 18
FOLLOW_SPEED_MIN = 18
FOLLOW_SPEED_MAX = 25
TURN_KP          = 0.35

CONFIDENCE_THRESHOLD = 0.35

LOST_TIMEOUT          = 0.3   
MAX_TARGET_JUMP_PIXELS = 90
IOU_KEEP_THRESHOLD     = 0.15  

DETECTION_MAX_AGE = 0.5

MAX_MANUAL_SPEED         = 100
JOYSTICK_DEADZONE        = 0.12
MANUAL_TIMEOUT           = 1.0
CONTROLLER_SEARCH_INTERVAL = 3.0

STOP_BOX_RATIO    = 0.35
FORWARD_SPEED_MIN = 20
FORWARD_SPEED_MAX = 55

PROTOTXT_PATH = "/home/mark-aster/models/deploy.prototxt"
MODEL_PATH    = "/home/mark-aster/models/mobilenet_iter_73000.caffemodel"


# ============================================================
# PCA9685 SETUP
# ============================================================

LEFT_RPWM  = 0
LEFT_LPWM  = 1
RIGHT_RPWM = 5
RIGHT_LPWM = 4

latest_detection_boxes = []
latest_detection_ts    = 0.0   
detection_lock         = threading.Lock()

i2c = busio.I2C(board.SCL, board.SDA)
pca = PCA9685(i2c)
pca.frequency = 1500

GPIO.setmode(GPIO.BCM)
EN_PINS = [26, 19, 16, 6]
for pin in EN_PINS:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.HIGH)


# ============================================================
# GLOBAL STATE & SPEECH ENGINE
# ============================================================

latest_raw_frame     = None
latest_frame_id      = 0
latest_display_frame = None

raw_frame_lock     = threading.Lock()
display_frame_lock = threading.Lock()

running = True

def speak(text):
    """Executes non-blocking espeak calls so the main process loop never stutters."""
    cmd = ['espeak', '-v', 'ro', '-s', '150', '-g', '1', '-a', '1000', text]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ============================================================
# MOTOR FUNCTIONS
# ============================================================

def set_pwm(channel, percent):
    percent = max(0, min(100, percent))
    value   = int(percent / 100 * 0xFFFF)
    pca.channels[channel].duty_cycle = value


def motor_left(speed):
    speed = int(max(-100, min(100, speed)))
    if speed > 0:
        set_pwm(LEFT_RPWM, speed); set_pwm(LEFT_LPWM, 0)
    elif speed < 0:
        set_pwm(LEFT_RPWM, 0);    set_pwm(LEFT_LPWM, -speed)
    else:
        set_pwm(LEFT_RPWM, 0);    set_pwm(LEFT_LPWM, 0)


def motor_right(speed):
    speed = int(max(-100, min(100, speed)))
    if speed > 0:
        set_pwm(RIGHT_RPWM, speed); set_pwm(RIGHT_LPWM, 0)
    elif speed < 0:
        set_pwm(RIGHT_RPWM, 0);    set_pwm(RIGHT_LPWM, -speed)
    else:
        set_pwm(RIGHT_RPWM, 0);    set_pwm(RIGHT_LPWM, 0)


def motor(speed):
    motor_left(speed)
    motor_right(-speed)


def drive(speed):
    motor_left(speed)
    motor_right(speed)


def stop_motors():
    motor_left(0)
    motor_right(0)


# ============================================================
# VOICE COMMAND IPC
# ============================================================

def read_voice_cmd():
    try:
        with open(BUDDYBOT_CMD) as f:
            data = json.load(f)
        cmd = data.get("cmd", "").strip()
        ts  = data.get("ts",  0.0)
        if cmd and (time.time() - ts) < 3.0:
            with open(BUDDYBOT_CMD, "w") as f:
                json.dump({"cmd": "", "ts": 0.0}, f)
            return cmd
    except Exception:
        pass
    return ""


# ============================================================
# CAMERA FUNCTIONS
# ============================================================

def open_camera():
    for cam in CAMERA_DEVICES:
        print(f"Trying camera: {cam}")
        cap = cv2.VideoCapture(cam, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS,          30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
        cap.set(cv2.CAP_PROP_AUTOFOCUS,    0)
        cap.set(cv2.CAP_PROP_FOCUS,        30)
        if not cap.isOpened():
            print(f"Could not open {cam}")
            cap.release()
            continue
        for _ in range(10):
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"Camera opened successfully: {cam}")
                return cap
            time.sleep(0.05)
        print(f"{cam} opened, but gave no frame")
        cap.release()
    raise RuntimeError("No working camera found.")


def camera_thread_func():
    global latest_raw_frame, latest_frame_id, running
    cap = open_camera()
    while running:
        ret, frame = cap.read()
        if ret and frame is not None:
            with raw_frame_lock:
                latest_raw_frame  = frame
                latest_frame_id  += 1
        time.sleep(0.001)
    cap.release()


def detection_thread_func():
    global latest_detection_boxes, latest_detection_ts, running
    detector          = PersonDetector()
    last_processed_id = -1
    print("Detection thread started.")

    while running:
        with raw_frame_lock:
            fid = latest_frame_id
            if latest_raw_frame is None or fid == last_processed_id:
                frame = None
            else:
                frame             = latest_raw_frame.copy()
                last_processed_id = fid

        if frame is None:
            time.sleep(0.005)
            continue

        small, _ = prepare_frame(frame)
        boxes    = detector.detect(small)

        with detection_lock:
            latest_detection_boxes = boxes
            latest_detection_ts    = time.time()   


def prepare_frame(frame):
    h, w = frame.shape[:2]
    y1   = CROP_TOP
    y2   = h - CROP_BOTTOM if CROP_BOTTOM > 0 else h
    if y2 <= y1:
        y1, y2 = 0, h
    cropped = frame[y1:y2, :]
    small   = cv2.resize(cropped, (FRAME_WIDTH,  FRAME_HEIGHT))
    display = cv2.resize(cropped, (STREAM_WIDTH, STREAM_HEIGHT))
    return small, display


# ============================================================
# CONTROLLER FUNCTIONS
# ============================================================

def find_dualsense_gamepad():
    for path in list_devices():
        try:
            dev  = InputDevice(path)
            name = dev.name.lower()
            caps = dev.capabilities()
            if not ("dualsense" in name or "wireless controller" in name or "ps5" in name):
                continue
            if "touchpad" in name or "motion" in name or "sensor" in name:
                continue
            abs_axes   = caps.get(ecodes.EV_ABS, [])
            axis_codes = [a[0] if isinstance(a, tuple) else a for a in abs_axes]
            if ecodes.ABS_RX in axis_codes:
                print(f"\nController connected: {dev.path} - {dev.name}")
                return dev
        except Exception:
            pass
    return None


def normalize_axis(value):
    x = (value - 128) / 128.0
    if abs(x) < JOYSTICK_DEADZONE:
        return 0.0
    return max(-1.0, min(1.0, x))


# ============================================================
# PERSON DETECTOR
# ============================================================

class PersonDetector:
    def __init__(self):
        try:
            self.net = cv2.dnn.readNetFromCaffe(PROTOTXT_PATH, MODEL_PATH)
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            print("Using MobileNet SSD person detector.")
        except Exception as e:
            raise RuntimeError(f"MobileNet SSD model failed to load: {e}")

    def detect(self, frame):
        h, w       = frame.shape[:2]
        blob       = cv2.dnn.blobFromImage(frame, 0.007843, (w, h), 127.5)
        self.net.setInput(blob)
        detections = self.net.forward()
        boxes      = []
        for i in range(detections.shape[2]):
            confidence = float(detections[0, 0, i, 2])
            class_id   = int(detections[0, 0, i, 1])
            if class_id != 15 or confidence < CONFIDENCE_THRESHOLD:
                continue
            box          = detections[0, 0, i, 3:7] * [w, h, w, h]
            x1, y1, x2, y2 = box.astype("int")
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w - 1, x2))
            y2 = max(0, min(h - 1, y2))
            bw, bh = x2 - x1, y2 - y1
            if bw > 15 and bh > 30:
                boxes.append((x1, y1, bw, bh, confidence))
        return boxes


# ============================================================
# TARGET TRACKING
# ============================================================

def box_center(box):
    x, y, w, h, conf = box
    return x + w // 2, y + h // 2

def box_area(box):
    x, y, w, h, conf = box
    return w * h

def distance_between_boxes(a, b):
    ax, ay = box_center(a)
    bx, by = box_center(b)
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)

def iou(a, b):
    ax, ay, aw, ah, _ = a
    bx, by, bw, bh, _ = b
    ax2, ay2   = ax + aw, ay + ah
    bx2, by2   = bx + bw, by + bh
    inter_w    = max(0, min(ax2, bx2) - max(ax, bx))
    inter_h    = max(0, min(ay2, by2) - max(ay, by))
    inter_area = inter_w * inter_h
    union_area = aw * ah + bw * bh - inter_area
    return inter_area / union_area if union_area > 0 else 0.0

def choose_initial_target(boxes):
    if not boxes:
        return None
    return max(boxes, key=lambda b: box_area(b) - abs(box_center(b)[0] - CENTER_X) * 3)

def update_target(current_target, boxes):
    if not boxes:
        return current_target
    if current_target is None:
        return choose_initial_target(boxes)
    best_box, best_score = None, -999999
    for box in boxes:
        score = iou(current_target, box) * 1000 \
                - distance_between_boxes(current_target, box) * 5 \
                + box[4] * 100
        if score > best_score:
            best_score = score
            best_box   = box
    if best_box is None:
        return current_target
    if distance_between_boxes(current_target, best_box) < MAX_TARGET_JUMP_PIXELS \
            or iou(current_target, best_box) > IOU_KEEP_THRESHOLD:
        return best_box
    return current_target


# ============================================================
# FLASK VIDEO STREAM
# ============================================================

app = Flask(__name__)

@app.route("/")
def index():
    return """<!DOCTYPE html><html>
    <head><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Buddy Bot</title>
    <style>*{margin:0;padding:0;box-sizing:border-box}
    body{background:#000;display:flex;justify-content:center;align-items:center;height:100vh}
    img{width:100vw;height:auto;max-height:100vh;object-fit:contain;display:block}</style>
    </head><body><img src="/video"></body></html>"""

def generate_stream():
    while running:
        with display_frame_lock:
            frame = latest_display_frame.copy() if latest_display_frame is not None else None
        if frame is None:
            time.sleep(0.03)
            continue
        ok, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not ok:
            continue
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
        time.sleep(0.04)

@app.route("/video")
def video():
    return Response(generate_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")

def start_stream_server():
    app.run(host="0.0.0.0", port=STREAM_PORT, debug=False, threaded=True)


# ============================================================
# STATUS WRITE
# ============================================================

def write_status(status, fps, motor, target, ctrl_ok):
    try:
        with open(BUDDYBOT_STATUS, "w") as f:
            json.dump({
                "status":     status,
                "fps":        round(fps, 1),
                "motor":      motor,
                "target":     target is not None,
                "controller": ctrl_ok,
            }, f)
    except Exception:
        pass


# ============================================================
# MAIN PROGRAM
# ============================================================

def main():
    global latest_display_frame, running

    write_status("TESTING MOTORS", 0, 0, None, False)
    print("Testing motors...")
    speak("Testare motoare") # Voice notification on boot execution
    motor_left(50);  time.sleep(1); motor_left(0);  time.sleep(0.5)
    motor_right(50); time.sleep(1); motor_right(0); time.sleep(0.5)
    print("Motor test done.")
    speak("Sistem pregătit")

    controller             = None
    last_controller_search = 0
    right_x    = 0.0
    left_y     = 0.0
    last_manual_time = 0

    last_seen_time = 0
    target_box     = None
    last_boxes     = []

    prev_time = time.time()
    fps = 0.0

    following_enabled = True
    was_tracking = False  # Track state transitions to avoid voice spamming

    print("Buddy Bot started.")
    print(f"Stream: http://YOUR_PI_IP:{STREAM_PORT}")

    try:
        while True:
            now = time.time()

            # ── Voice command ────────────────────────────────────────────
            vcmd = read_voice_cmd()
            if vcmd == "follow":
                following_enabled = True
                speak("Mod urmărire activat")
                print("\n[VOICE] Following resumed.")
            elif vcmd == "stop":
                following_enabled = False
                stop_motors()
                target_box = None
                last_boxes = []
                speak("Robot oprit")
                print("\n[VOICE] Following stopped.")

            # ── Controller search ────────────────────────────────────────
            if controller is None and now - last_controller_search > CONTROLLER_SEARCH_INTERVAL:
                last_controller_search = now
                controller = find_dualsense_gamepad()
                if controller is not None:
                    speak("Controler conectat")

            # ── Controller read ──────────────────────────────────────────
            if controller is not None:
                try:
                    r, _, _ = select.select([controller.fd], [], [], 0)
                    if r:
                        for event in controller.read():
                            if event.type == ecodes.EV_ABS and event.code == ecodes.ABS_RX:
                                right_x = normalize_axis(event.value)
                            if event.type == ecodes.EV_ABS and event.code == ecodes.ABS_Y:
                                left_y = normalize_axis(event.value)
                except OSError:
                    print("\nController disconnected.")
                    speak("Controler deconectat")
                    controller = None
                    right_x = left_y = 0.0
                    stop_motors()
                except Exception as e:
                    print(f"\nController error: {e}")
                    speak("Eroare controler")
                    controller = None
                    right_x = left_y = 0.0
                    stop_motors()

            # ── Camera frame ─────────────────────────────────────────────
            with raw_frame_lock:
                frame = latest_raw_frame.copy() if latest_raw_frame is not None else None

            if frame is None:
                print("Waiting for camera...                    ", end="\r")
                time.sleep(0.02)
                continue

            small_frame, display_frame = prepare_frame(frame)

            dt        = now - prev_time
            prev_time = now
            fps       = 1.0 / dt if dt > 0 else fps

            status      = "STARTING"
            motor_speed = 0
            sx = STREAM_WIDTH  / FRAME_WIDTH
            sy = STREAM_HEIGHT / FRAME_HEIGHT

            # ── Motor logic ──────────────────────────────────────────────

            manual_moving = abs(right_x) > 0 or abs(left_y) > 0
            if manual_moving:
                last_manual_time = now
            manual_active = now - last_manual_time < MANUAL_TIMEOUT

            if manual_active:
                if was_tracking:
                    was_tracking = False # Reset state if manual mode takes over tracking
                forward = -left_y
                turn    =  right_x
                left_speed  = max(-100, min(100, int((forward + turn) * MAX_MANUAL_SPEED)))
                right_speed = max(-100, min(100, int((forward - turn) * MAX_MANUAL_SPEED)))
                motor_left(left_speed)
                motor_right(right_speed)
                motor_speed = int(forward * MAX_MANUAL_SPEED)
                status = f"MANUAL fwd={motor_speed}% trn={int(turn * MAX_MANUAL_SPEED)}%"

            elif not following_enabled:
                if was_tracking:
                    was_tracking = False
                stop_motors()
                motor_speed = 0
                status = "VOICE STOPPED"

            else:
                with detection_lock:
                    det_age = now - latest_detection_ts
                    boxes   = list(latest_detection_boxes) if det_age < DETECTION_MAX_AGE else []

                if boxes:
                    last_boxes = boxes
                    target_box = update_target(target_box, boxes)
                    if target_box is not None:
                        last_seen_time = now
                else:
                    if now - last_seen_time > LOST_TIMEOUT * 0.5:
                        last_boxes = []

                if target_box is not None and now - last_seen_time <= LOST_TIMEOUT:
                    # Target acquired and locked! Trigger single speech notification
                    if not was_tracking:
                        speak("Țintă blocată")
                        was_tracking = True

                    x, y, w, h, conf = target_box
                    person_center_x  = x + w // 2
                    error     = person_center_x - CENTER_X
                    box_ratio = (w * h) / (FRAME_WIDTH * FRAME_HEIGHT)

                    if abs(error) >= DEAD_ZONE:
                        raw_speed   = max(FOLLOW_SPEED_MIN,
                                          min(FOLLOW_SPEED_MAX, abs(error) * TURN_KP))
                        motor_speed = int(raw_speed) if error > 0 else -int(raw_speed)
                        motor(motor_speed)
                        status = "TURN RIGHT" if error > 0 else "TURN LEFT"

                    elif box_ratio >= STOP_BOX_RATIO:
                        stop_motors()
                        motor_speed = 0
                        status = "AT TARGET"

                    else:
                        t             = box_ratio / STOP_BOX_RATIO
                        forward_speed = max(FORWARD_SPEED_MIN,
                                            min(FORWARD_SPEED_MAX,
                                                int(FORWARD_SPEED_MAX * (1.0 - t))))
                        drive(forward_speed)
                        motor_speed = forward_speed
                        status = f"FORWARD {forward_speed}%"

                else:
                    # Target was dropped/lost. Trigger single notification
                    if was_tracking:
                        speak("Țintă pierdută")
                        was_tracking = False

                    target_box = None
                    last_boxes = []
                    stop_motors()
                    motor_speed = 0
                    status = "TARGET LOST"

            # ── Draw overlays ────────────────────────────────────────────

            for box in last_boxes:
                x, y, w, h, conf = box
                dx, dy, dw, dh   = int(x*sx), int(y*sy), int(w*sx), int(h*sy)
                cv2.rectangle(display_frame, (dx, dy), (dx+dw, dy+dh), (120, 120, 120), 1)
                cv2.putText(display_frame, f"person {conf:.2f}",
                            (dx, max(15, dy - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 120, 120), 1)

            if target_box is not None and now - last_seen_time <= LOST_TIMEOUT:
                x, y, w, h, conf = target_box
                dx, dy, dw, dh   = int(x*sx), int(y*sy), int(w*sx), int(h*sy)
                cx, cy = dx + dw // 2, dy + dh // 2
                cxs    = int(CENTER_X * sx)
                cv2.rectangle(display_frame, (dx, dy), (dx+dw, dy+dh), (0, 255, 0), 2)
                cv2.circle(display_frame, (cx, cy), 6, (0, 255, 0), -1)
                cv2.line(display_frame, (cxs, 0), (cxs, STREAM_HEIGHT), (255, 255, 255), 1)
                cv2.line(display_frame, (cx, cy), (cxs, cy), (0, 255, 255), 1)
                cv2.putText(display_frame, "LOCKED TARGET",
                            (dx, max(25, dy - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            ctrl_label = "CTRL OK" if controller is not None else "NO CTRL"
            cv2.putText(display_frame, f"FPS:{fps:.1f} | {ctrl_label}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.putText(display_frame, f"{status} | motor={motor_speed}",
                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

            with display_frame_lock:
                latest_display_frame = display_frame.copy()

            print(f"FPS:{fps:.1f} | {ctrl_label} | {status} | motor={motor_speed}      ",
                  end="\r")
            write_status(status, fps, motor_speed, target_box, controller is not None)
            time.sleep(0.003)

    finally:
        running = False
        stop_motors()
        print("\nMain loop stopped.")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    threading.Thread(target=camera_thread_func,    daemon=True).start()
    threading.Thread(target=detection_thread_func, daemon=True).start()
    threading.Thread(target=start_stream_server,   daemon=True).start()

    try:
        main()
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"\nMain error: {e}")
    finally:
        running = False
        stop_motors()
        write_status("OFFLINE", 0, 0, None, False)
        try:
            pca.deinit()
        except Exception:
            pass
        GPIO.cleanup()
        print("Stopped.")
