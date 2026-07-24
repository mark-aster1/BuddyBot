import serial, glob, threading, math, time
import port_manager

BLE_BAUD       = 115200
BLE_TX_POWER   = -59
BLE_N          = 2.5
BLE_SEPARATION = 0.40
BLE_ALPHA      = 0.25
BLE_LOST_SECS  = 3.0

_state = {"rssi_l": None, "rssi_r": None, "ts_l": 0.0, "ts_r": 0.0}
_lock  = threading.Lock()

_non_rssi      = set()
_non_rssi_lock = threading.Lock()

_running = False
_threads = []

def get_state():
    with _lock:
        return dict(_state)


def dist(rssi):
    return 10.0 ** ((BLE_TX_POWER - rssi) / (10.0 * BLE_N))


def position(rssi_l, rssi_r):
    dl, dr = dist(rssi_l), dist(rssi_r)
    half   = BLE_SEPARATION / 2.0
    x = max(-6.0, min(6.0, (dl**2 - dr**2) / (2.0 * BLE_SEPARATION)))
    y = math.sqrt(max(0.0, dl**2 - (x + half)**2))
    return x, y


def start():
    global _running, _threads
    _running = True
    _threads = [
        threading.Thread(target=_reader_thread, args=("L",),
                         daemon=True, name="ble-L"),
        threading.Thread(target=_reader_thread, args=("R",),
                         daemon=True, name="ble-R"),
    ]
    for t in _threads:
        t.start()
    return _threads


def stop():
    global _running
    _running = False
    for t in _threads:
        t.join(timeout=3)

def _reader_thread(side):
    k_rssi        = "rssi_l" if side == "L" else "rssi_r"
    k_ts          = "ts_l"   if side == "L" else "ts_r"
    _prev_portset = set()

    while _running:
        candidates     = sorted(
            glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        )
        candidates_set = set(candidates)

        if candidates_set != _prev_portset:
            with _non_rssi_lock:
                _non_rssi.clear()
            _prev_portset = candidates_set

        with _non_rssi_lock:
            excluded = set(_non_rssi)

        port = None
        for p in candidates:
            if p in excluded:
                continue
            if port_manager.claim(p):
                port = p
                break

        if port is None:
            with _lock:
                _state[k_rssi] = None
                _state[k_ts]   = 0.0
            time.sleep(1.0)
            continue

        is_ble = False
        try:
            with serial.Serial(port, BLE_BAUD, timeout=2) as s:
                for _ in range(5):
                    if not _running:
                        break
                    line = s.readline().decode(errors="ignore").strip()
                    if not line:
                        continue
                    if line.lower().startswith("rssi"):
                        is_ble = True
                        break
                    else:
                        break

                if not is_ble:
                    with _non_rssi_lock:
                        _non_rssi.add(port)
                    port_manager.release(port)
                    time.sleep(0.3)
                    continue

                print(f"[BLE-{side}] connected on {port}")

                while _running:
                    line = s.readline().decode(errors="ignore").strip()
                    if not line or ":" not in line:
                        continue
                    try:
                        val = float(line.split(":")[-1])
                    except ValueError:
                        continue
                    with _lock:
                        prev           = _state[k_rssi]
                        _state[k_rssi] = val if prev is None else (
                            (1 - BLE_ALPHA) * prev + BLE_ALPHA * val)
                        _state[k_ts]   = time.time()

        except Exception as e:
            if _running:
                print(f"[BLE-{side}] {e} — retry in 2 s")
            time.sleep(2.0)

        finally:
            port_manager.release(port)
            with _lock:
                _state[k_rssi] = None
                _state[k_ts]   = 0.0
