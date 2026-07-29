import time
import math
import subprocess
import threading

import qwiic_icm20948

AXIS_SIGN = {"x": 1, "y": -1, "z": -1}

ROLL_THRESHOLD  = 45.0 
PITCH_THRESHOLD = 45.0

CHECK_HZ         = 10       
ALERT_COOLDOWN   = 5.0    
RECOVER_HOLD_SEC = 1.0       

MAG_TOLERANCE_FRAC   = 0.35
BASELINE_CALIB_SEC   = 1.0 
BASELINE_ADAPT_ALPHA = 0.01

TIP_CONFIRM_HOLD_SEC = 0.30

DISTRESS_PHRASES = [
    "AUUUUUUU! Am picat! Te rog ridica-ma!",
]

def speak(text):
    """Executes non-blocking espeak calls so the caller's main loop never stutters."""
    cmd = ['espeak', '-v', 'ro', '-s', '150', '-g', '1', '-a', '1000', text]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def _roll_pitch_from_accel(ax, ay, az):
    roll  = math.degrees(math.atan2(ay, az))
    pitch = math.degrees(math.atan2(-ax, math.sqrt(ay * ay + az * az)))
    return roll, pitch


def _magnitude(ax, ay, az):
    return math.sqrt(ax * ax + ay * ay + az * az)

class TipoverMonitor:
    def __init__(self, imu=None, on_tipped=None, on_recovered=None):
        self._owns_imu = imu is None
        self.imu = imu
        self.on_tipped = on_tipped
        self.on_recovered = on_recovered

        self._thread = None
        self._running = False

        self.is_tipped = False
        self.last_roll = 0.0
        self.last_pitch = 0.0

    def start(self):
        if self._thread is not None:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self):
        if self.imu is None:
            self.imu = qwiic_icm20948.QwiicIcm20948()
            if not self.imu.begin():
                print("[tipover_monitor] Failed to initialize ICM-20948 — monitor not running.")
                return

        interval = 1.0 / CHECK_HZ
        last_alert_time = 0.0
        level_since = None
        tilt_since = None
        baseline_mag = None
        calib_end = time.time() + BASELINE_CALIB_SEC
        calib_samples = []

        print("[tipover_monitor] Started. Calibrating resting accel magnitude...")

        while self._running:
            if not self.imu.dataReady():
                time.sleep(0.005)
                continue

            self.imu.getAgmt()
            ax = self.imu.axRaw * AXIS_SIGN["x"]
            ay = self.imu.ayRaw * AXIS_SIGN["y"]
            az = self.imu.azRaw * AXIS_SIGN["z"]

            mag = _magnitude(ax, ay, az)

            if baseline_mag is None:
                calib_samples.append(mag)
                if time.time() >= calib_end:
                    baseline_mag = sum(calib_samples) / len(calib_samples)
                    print(f"[tipover_monitor] Baseline accel magnitude: {baseline_mag:.0f}")
                time.sleep(interval)
                continue

            roll, pitch = _roll_pitch_from_accel(ax, ay, az)
            self.last_roll, self.last_pitch = roll, pitch

            now = time.time()

            mag_deviation = abs(mag - baseline_mag) / baseline_mag if baseline_mag else 0.0
            reliable = mag_deviation <= MAG_TOLERANCE_FRAC

            if reliable:
                baseline_mag = ((1 - BASELINE_ADAPT_ALPHA) * baseline_mag
                                + BASELINE_ADAPT_ALPHA * mag)

                angle_tipped = abs(roll) > ROLL_THRESHOLD or abs(pitch) > PITCH_THRESHOLD

                if angle_tipped:
                    level_since = None
                    if tilt_since is None:
                        tilt_since = now
                    confirmed = (now - tilt_since) >= TIP_CONFIRM_HOLD_SEC

                    if confirmed and (not self.is_tipped or (now - last_alert_time) > ALERT_COOLDOWN):
                        speak(DISTRESS_PHRASES[0])
                        print(f"[tipover_monitor] TIPPED OVER — roll={roll:.1f} pitch={pitch:.1f}")
                        last_alert_time = now
                        if self.on_tipped is not None:
                            try:
                                self.on_tipped(roll, pitch)
                            except Exception as e:
                                print(f"[tipover_monitor] on_tipped callback error: {e}")
                    if confirmed:
                        self.is_tipped = True
                else:
                    tilt_since = None
                    if self.is_tipped:
                        if level_since is None:
                            level_since = now
                        elif now - level_since >= RECOVER_HOLD_SEC:
                            print(f"[tipover_monitor] Recovered — roll={roll:.1f} pitch={pitch:.1f}")
                            self.is_tipped = False
                            level_since = None
                            if self.on_recovered is not None:
                                try:
                                    self.on_recovered()
                                except Exception as e:
                                    print(f"[tipover_monitor] on_recovered callback error: {e}")
                    else:
                        level_since = None

            time.sleep(interval)

        print("[tipover_monitor] Stopped.")

_default_monitor = None


def start_tipover_monitor(imu=None, on_tipped=None, on_recovered=None):
    global _default_monitor
    monitor = TipoverMonitor(imu=imu, on_tipped=on_tipped, on_recovered=on_recovered)
    monitor.start()
    _default_monitor = monitor
    return monitor

if __name__ == "__main__":
    print("Running tipover_monitor standalone for testing. Ctrl+C to stop.")
    m = start_tipover_monitor()
    try:
        while True:
            time.sleep(1.0)
            print(f"roll={m.last_roll:.1f} pitch={m.last_pitch:.1f} tipped={m.is_tipped}")
    except KeyboardInterrupt:
        m.stop()
        print("\nStopped.")
