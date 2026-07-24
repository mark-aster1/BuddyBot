import time
import numpy as np
from collections import deque
from scipy.spatial.transform import Rotation
from ahrs.filters import Madgwick
import qwiic_icm20948

imu = qwiic_icm20948.QwiicIcm20948()
if not imu.begin():
    print("Failed to initialize ICM-20948")
    exit()

mag_bias = {'x': 0.0, 'y': 0.0, 'z': 0.0}

print("1. Calibrating Gyroscope... Keep sensor completely still!")
gx_samples, gy_samples, gz_samples = [], [], []

for _ in range(400):
    if imu.dataReady():
        imu.getAgmt()
        gx_samples.append(imu.gxRaw)
        gy_samples.append(imu.gyRaw)
        gz_samples.append(imu.gzRaw)
    time.sleep(0.005)

gyro_bias = {
    'x': np.mean(gx_samples),
    'y': np.mean(gy_samples),
    'z': np.mean(gz_samples)
}
print(f"   Gyro Bias Calibrated: {gyro_bias}")

madgwick = Madgwick(gain=0.3)
q = np.array([1.0, 0.0, 0.0, 0.0])
last_time = time.time()

CARDINALS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

roll_buffer = deque(maxlen=15)
pitch_buffer = deque(maxlen=15)

is_imu_ready = False

print("2. Settling IMU orientation...")
while True:
    if imu.dataReady():
        now = time.time()
        dt = max(now - last_time, 1e-4)
        last_time = now

        imu.getAgmt()

        acc = np.array([imu.axRaw, imu.ayRaw, imu.azRaw], dtype=float)

        gx = (imu.gxRaw - gyro_bias['x']) / 131.0
        gy = (imu.gyRaw - gyro_bias['y']) / 131.0
        gz = (imu.gzRaw - gyro_bias['z']) / 131.0
        gyro_rad = np.radians([gx, gy, gz])

        if np.linalg.norm(gyro_rad) < 0.01:
            gyro_rad = np.array([0.0, 0.0, 0.0])

        q = madgwick.updateIMU(q, gyr=gyro_rad, acc=acc, dt=dt)

        r = Rotation.from_quat([q[1], q[2], q[3], q[0]])
        roll, pitch, _ = r.as_euler('xyz', degrees=True)

        if not is_imu_ready:
            roll_buffer.append(roll)
            pitch_buffer.append(pitch)

            if len(roll_buffer) == roll_buffer.maxlen:
                unwrapped_roll = np.degrees(np.unwrap(np.radians(roll_buffer)))
                
                roll_std = np.std(unwrapped_roll)
                pitch_std = np.std(pitch_buffer)

                if roll_std < 0.5 and pitch_std < 0.5:
                    is_imu_ready = True
                    madgwick.gain = 0.08 
                    print("\n>>> IMU READY! Orientation locked & stabilized. <<<\n")

        mx = imu.myRaw - mag_bias['x']
        my = imu.mxRaw - mag_bias['y']
        mz = -imu.mzRaw - mag_bias['z']
        mag_body = np.array([mx, my, mz], dtype=float)

        mag_world = r.apply(mag_body)
        heading_rad = np.arctan2(-mag_world[1], mag_world[0])
        heading_deg = (np.degrees(heading_rad) + 360.0) % 360.0

        cardinal_idx = int((heading_deg + 22.5) // 45) % 8
        cardinal_dir = CARDINALS[cardinal_idx]

        status = "READY" if is_imu_ready else "INITIALIZING..."

        print(
            f"[{status:<15}] "
            f"Roll: {roll:6.2f}° | "
            f"Pitch: {pitch:6.2f}° | "
            f"Heading: {heading_deg:6.1f}° ({cardinal_dir:<2})"
        )

    time.sleep(0.01)
