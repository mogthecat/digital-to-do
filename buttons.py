"""Debounced push buttons wired from a GPIO pin to GND (internal pull-up)."""

import time
from machine import Pin

DEBOUNCE_MS = 30


class Button:
    def __init__(self, pin_no):
        self._pin = Pin(pin_no, Pin.IN, Pin.PULL_UP)
        self._stable = self._pin.value()
        self._last_raw = self._stable
        self._changed_at = time.ticks_ms()

    def pressed(self):
        """Return True once for each press. Call this often (e.g. every 20 ms)."""
        raw = self._pin.value()
        now = time.ticks_ms()
        if raw != self._last_raw:
            self._last_raw = raw
            self._changed_at = now
            return False
        if raw != self._stable and time.ticks_diff(now, self._changed_at) >= DEBOUNCE_MS:
            self._stable = raw
            return raw == 0  # pressed = pulled to GND
        return False
