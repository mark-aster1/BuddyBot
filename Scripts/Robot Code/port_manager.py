import threading

_claimed = set()
_lock    = threading.Lock()


def claim(port):
    with _lock:
        if port in _claimed:
            return False
        _claimed.add(port)
        return True


def release(port):
    with _lock:
        _claimed.discard(port)
