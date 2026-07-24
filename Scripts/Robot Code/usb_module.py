import serial, glob, threading, time, queue
import subprocess
import port_manager

USB_BAUD      = 115200
USB_LOST_SECS = 3.0

_state     = {"type": None, "label": None, "value": None, "port": None, "ts": 0.0}
_lock      = threading.Lock()
_running   = False
_thread    = None
_cmd_queue = queue.Queue()

def _speak_background(text):
    """Fires espeak in the background to prevent blocking the serial threads."""
    cmd = ['espeak', '-v', 'ro', '-s', '150', '-g', '1', '-a', '1000', text]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_state():
    with _lock:
        return dict(_state)


def get_menu_label():
    with _lock:
        mod_type = _state["type"]
        label    = _state["label"]
        ts       = _state["ts"]
    if mod_type and ts > 0 and (time.time() - ts) < USB_LOST_SECS:
        return f"USB Module ({label})"
    return "USB Module"


def start(skip_ports=()):
    """Start the USB module background thread."""
    global _running, _thread
    _running = True
    _thread  = threading.Thread(
        target=_thread_func,
        args=(frozenset(skip_ports),),
        daemon=True,
        name="usb-module",
    )
    _thread.start()
    return _thread


def stop():
    global _running
    _running = False
    if _thread:
        _thread.join(timeout=3)


def send_arm_command(cmd):
    _cmd_queue.put(cmd.strip())

    if "Weight:" in line:
        try:
            raw = float(line.split("Weight:")[-1].strip())
            val = max(0.0, min(abs(raw), 20000.0))
        except (ValueError, IndexError):
            val = None
        return "weight", "Scale Module", val

    if "Mech. Arm:" in line:
        try:
            part  = line.split("Mech. Arm:")[-1].strip()        # "clawAngle -> 92 deg"
            name  = part.split("->")[0].strip()                  # "clawAngle"
            angle = int(part.split("->")[1].strip().split()[0])  # 92
        except (ValueError, IndexError):
            return None, None, None
        return "arm", "Mech. Arm", {"servo": name, "angle": angle}

    return None, None, None

def _thread_func(skip_ports):
    _ble_ports    = set()
    _prev_portset = set()

    while _running:
        candidates     = sorted(
            glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
        )
        candidates_set = set(candidates)

        if candidates_set != _prev_portset:
            _ble_ports.clear()
            _prev_portset = candidates_set

        port = None
        for p in candidates:
            if p in skip_ports or p in _ble_ports:
                continue
            if port_manager.claim(p):
                port = p
                break

        if port is None:
            with _lock:
                _state.update(type=None, label=None, value=None, port=None, ts=0.0)
            time.sleep(2.0)
            continue

        is_ble        = False
        is_arm        = False   
        _arm_servos   = {}      
        announced_mod = None 
        
        try:
            with serial.Serial(port, USB_BAUD, timeout=2) as s:
                print(f"[USB-MOD] probing {port}")
                with _lock:
                    _state["port"] = port

                while _running:
                    if is_arm:
                        while not _cmd_queue.empty():
                            try:
                                cmd = _cmd_queue.get_nowait()
                                s.write((cmd + "\n").encode())
                                print(f"[USB-MOD] → arm: {cmd}")
                            except Exception:
                                pass

                    line = s.readline().decode(errors="ignore").strip()
                    if not line:
                        continue

                    if line.lower().startswith("rssi"):
                        print(f"[USB-MOD] {port} is BLE scanner — skipping")
                        is_ble = True
                        break

                    mod_type, mod_label, mod_value = _parse_line(line)
                    if mod_type:
                        if announced_mod != mod_type:
                            if mod_type == "weight":
                                _speak_background("Cântar conectat")
                            elif mod_type == "arm":
                                _speak_background("Braț mecanic conectat")
                            announced_mod = mod_type

                        if mod_type == "arm" and isinstance(mod_value, dict):
                            is_arm = True   
                            _arm_servos[mod_value["servo"]] = mod_value["angle"]
                            with _lock:
                                _state.update(
                                    type="arm",
                                    label="Mech. Arm",
                                    value=dict(_arm_servos),
                                    port=port,
                                    ts=time.time(),
                                )
                        else:
                            with _lock:
                                _state.update(
                                    type=mod_type,
                                    label=mod_label,
                                    value=mod_value,
                                    port=port,
                                    ts=time.time(),
                                )

        except Exception as e:
            if _running:
                print(f"[USB-MOD] {e} — retry in 2 s")
            time.sleep(2.0)

        finally:
            port_manager.release(port)
            if announced_mod:
                label_ro = "Cântar" if announced_mod == "weight" else "Braț mecanic"
                _speak_background(f"{label_ro} deconectat")
                announced_mod = None
                
            with _lock:
                _state.update(type=None, label=None, value=None, port=None, ts=0.0)

        if is_ble:
            _ble_ports.add(port)
            time.sleep(0.3)
