import sounddevice, vosk, json, queue, sys, os

MODEL_PATH  = "vosk-model" 
SAMPLE_RATE = 16000
BLOCK_SIZE  = 4000

DEVICE = 2

if "--list" in sys.argv:
    print(sounddevice.query_devices())
    sys.exit(0)

if not os.path.isdir(MODEL_PATH):
    print(f"Model not found at '{MODEL_PATH}'")
    print("Run the setup commands in the script header, then try again.")
    sys.exit(1)

print(f"Loading model from '{MODEL_PATH}' ...")
model = vosk.Model(MODEL_PATH)
rec   = vosk.KaldiRecognizer(model, SAMPLE_RATE)
rec.SetWords(False)

print("Listening — speak now.  Ctrl+C to stop.\n")

audio_q = queue.Queue()

def callback(indata, frames, time_info, status):
    audio_q.put(bytes(indata))

with sounddevice.RawInputStream(
    samplerate = SAMPLE_RATE,
    blocksize  = BLOCK_SIZE,
    dtype      = "int16",
    channels   = 1,
    device     = DEVICE,
    callback   = callback,
):
    try:
        while True:
            data = audio_q.get()

            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "").strip()
                if text:
                    print(f"> {text}")
            else:
                partial = json.loads(rec.PartialResult()).get("partial", "").strip()
                if partial:
                    print(f"  {partial}", end="\r")

    except KeyboardInterrupt:
        print("\nStopped.")
