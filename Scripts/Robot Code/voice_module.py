import sounddevice, vosk, json, queue, threading, time, os
import usb_module

MODEL_PATH  = "/home/mark-aster/documents/buddy_bot/vosk-model"
MIC_NAME    = "Webcam"       
SAMPLE_RATE = 16000
BLOCK_SIZE  = 4000

ARM_COMMANDS = [
    "straight", "zero",
    "open",     "close",
    "wave",     "yes",   "no",
    "rise",     "lower",
    "dance",    "grab",  "throw",
]

_last_cmd = ""
_last_ts  = 0.0
_cmd_lock = threading.Lock()
_running  = False
_thread   = None

def get_last_command():
    with _cmd_lock:
        return _last_cmd, _last_ts


def start():
    global _running, _thread
    _running = True
    _thread  = threading.Thread(target=_voice_thread, daemon=True, name="voice-mod")
    _thread.start()
    return _thread


def stop():
    global _running
    _running = False
    if _thread:
        _thread.join(timeout=3)

def _find_mic():
    devices = sounddevice.query_devices()
    candidates = []

    for i, d in enumerate(devices):
        if d["max_input_channels"] < 1:
            continue
        priority = 0 if MIC_NAME.lower() in d["name"].lower() else 1
        candidates.append((priority, i, d))

    candidates.sort(key=lambda x: x[0])

    for _, idx, d in candidates:
        for ch in (1, 2):
            if d["max_input_channels"] < ch:
                continue
            try:
                sounddevice.check_input_settings(
                    device=idx, channels=ch, dtype="int16", samplerate=SAMPLE_RATE
                )
                print(f"[VOICE] using device {idx} '{d['name']}' channels={ch}")
                return idx, ch
            except Exception:
                continue

    return None, 1


def _listen_once(model):
    global _last_cmd, _last_ts

    device, channels = _find_mic()
    if device is None:
        print("[VOICE] No suitable input device found.")
        return True

    grammar = json.dumps(ARM_COMMANDS + ["[unk]"])
    rec     = vosk.KaldiRecognizer(model, SAMPLE_RATE, grammar)
    rec.SetWords(False)

    audio_q = queue.Queue()

    def _callback(indata, frames, time_info, status):
        if channels == 2:
            import numpy as np
            arr  = np.frombuffer(bytes(indata), dtype=np.int16).reshape(-1, 2)
            mono = arr.mean(axis=1).astype(np.int16).tobytes()
            audio_q.put(mono)
        else:
            audio_q.put(bytes(indata))

    try:
        with sounddevice.RawInputStream(
            samplerate = SAMPLE_RATE,
            blocksize  = BLOCK_SIZE,
            dtype      = "int16",
            channels   = channels,
            device     = device,
            callback   = _callback,
        ):
            print("[VOICE] Listening — " + " ".join(ARM_COMMANDS))

            while _running:
                try:
                    data = audio_q.get(timeout=0.5)
                except queue.Empty:
                    continue

                if rec.AcceptWaveform(data):
                    text = json.loads(rec.Result()).get("text", "").strip()

                    if not text or text == "[unk]" or text not in ARM_COMMANDS:
                        continue

                    print(f"[VOICE] '{text}'")
                    if text == "wave":
                        text = "hi"
                    usb_module.send_arm_command(text)

                    with _cmd_lock:
                        _last_cmd = text
                        _last_ts  = time.time()

    except Exception as e:
        if _running:
            print(f"[VOICE] stream error: {e}")

    return True


def _voice_thread():
    if not os.path.isdir(MODEL_PATH):
        print(f"[VOICE] Model not found at '{MODEL_PATH}'. See module docstring for setup.")
        return

    try:
        model = vosk.Model(MODEL_PATH)
    except Exception as e:
        print(f"[VOICE] Cannot load model: {e}")
        return

    while _running:
        _listen_once(model)
        if _running:
            print("[VOICE] Retrying in 3 s…")
            time.sleep(3)
