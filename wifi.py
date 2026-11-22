"""Wi-Fi helper for the Pico 2 W."""

import time
import network

_wlan = network.WLAN(network.STA_IF)


def is_connected():
    return _wlan.isconnected()


def connect(ssid, password, timeout=20):
    """Connect (or reuse an existing connection). Returns the IP address."""
    _wlan.active(True)
    if _wlan.isconnected():
        return _wlan.ifconfig()[0]
    _wlan.connect(ssid, password)
    start = time.ticks_ms()
    while not _wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > timeout * 1000:
            _wlan.disconnect()
            raise OSError("Wi-Fi timeout (status %d)" % _wlan.status())
        time.sleep_ms(250)
    return _wlan.ifconfig()[0]
