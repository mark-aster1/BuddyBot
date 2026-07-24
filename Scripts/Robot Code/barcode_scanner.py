import cv2, time, json, threading, io
from pyzbar import pyzbar
from flask import Flask, Response

SCANNER_STATUS = "/tmp/barcode_status.json"
STREAM_PORT    = 8080

PRODUCTS = {
    "8000500390306": {"name": "Nutella B-Ready",     "price": 16.29},
    "5942321000114": {"name": "Coca Cola Zero Zahar 2L",     "price": 11.49},
    "5942325003753": {"name": "Bucovina Apa Plata 2L",     "price": 3.90},
    "barcode_number": {"name": "Product Name", "price": 0.00},
}

CAMERA_DEVICES = ["/dev/video1", "/dev/video2", "/dev/video0"]
DEBOUNCE_SECS  = 5.0

_latest_frame      = None
_latest_frame_lock = threading.Lock()
_running           = True

def write_status(status, code, name, price, cart, total):
    try:
        with open(SCANNER_STATUS, "w") as f:
            json.dump({
                "status":     status,
                "last_code":  code,
                "last_name":  name,
                "last_price": price,
                "cart":       cart[-8:],
                "total":      round(total, 2),
            }, f)
    except Exception:
        pass

def open_camera():
    for dev in CAMERA_DEVICES:
        cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        cap.set(cv2.CAP_PROP_FPS, 15)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
        if not cap.isOpened():
            cap.release(); continue
        for _ in range(5):
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"Camera: {dev}")
                return cap
            time.sleep(0.05)
        cap.release()
    raise RuntimeError("No camera found")

app = Flask(__name__)

@app.route("/")
def index():
    return (
        '<html><head><title>Barcode Scanner</title></head>'
        '<body style="margin:0;background:#000;display:flex;'
        'align-items:center;justify-content:center;height:100vh">'
        '<img src="/video" style="max-width:100%;max-height:100vh">'
        '</body></html>'
    )

@app.route("/video")
def video():
    def generate():
        while _running:
            with _latest_frame_lock:
                frame = _latest_frame.copy() if _latest_frame is not None else None
            if frame is None:
                time.sleep(0.1)
                continue
            ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not ok:
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                   + jpeg.tobytes() + b"\r\n")
            time.sleep(0.1)
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

def stream_thread_func():
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=STREAM_PORT, debug=False,
            threaded=True, use_reloader=False)

def main():
    global _latest_frame, _running

    cap = open_camera()

    cart           = []
    total          = 0.0
    last_code      = ""
    last_scan_time = 0.0
    last_name      = ""
    last_price     = 0.0

    write_status("READY", "", "", 0.0, [], 0.0)
    print(f"Barcode scanner ready — stream at http://YOUR_PI_IP:{STREAM_PORT}/")
    print("Ctrl+C to stop.\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            barcodes = pyzbar.decode(frame)
            now      = time.time()

            for bc in barcodes:
                code = bc.data.decode("utf-8").strip()

                pts = bc.polygon
                if len(pts) == 4:
                    poly = [(p.x, p.y) for p in pts]
                    for i in range(4):
                        cv2.line(frame, poly[i], poly[(i+1) % 4], (0, 255, 0), 2)

                if code == last_code and now - last_scan_time < DEBOUNCE_SECS:
                    continue

                last_code      = code
                last_scan_time = now

                if code in PRODUCTS:
                    p          = PRODUCTS[code]
                    last_name  = p["name"]
                    last_price = p["price"]
                    cart.append({"name": last_name, "price": last_price})
                    total     += last_price
                    status     = "FOUND"
                    print(f"  ✓  {last_name:<32}  RON{last_price:>6.2f}   total: €{total:.2f}")
                else:
                    last_name  = f"Unknown ({code})"
                    last_price = 0.0
                    status     = "NOT FOUND"
                    print(f"  ✗  Unknown barcode: {code}")

                write_status(status, code, last_name, last_price, cart, total)

            cv2.putText(frame, f"Items: {len(cart)}  Total: RON{total:.2f}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            if last_name:
                col = (0, 255, 0) if last_price > 0 else (0, 100, 255)
                cv2.putText(frame, f"{last_name}  RON{last_price:.2f}",
                            (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)

            with _latest_frame_lock:
                _latest_frame = frame

            time.sleep(0.1)

    except KeyboardInterrupt:
        pass
    finally:
        _running = False
        write_status("OFFLINE", "", "", 0.0, [], 0.0)
        cap.release()
        print(f"\nSession ended — total: RON{total:.2f}  ({len(cart)} items)")


if __name__ == "__main__":
    threading.Thread(target=stream_thread_func, daemon=True).start()
    main()
