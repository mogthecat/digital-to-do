"""
MicroPython driver for the Adafruit Sharp Memory Display (LS027B7DH01, 400x240).

Wiring (Pico 2 W):
    VIN -> 3V3(OUT)   GND -> GND
    CLK -> GP18 (SPI0 SCK)   DI -> GP19 (SPI0 MOSI)   CS -> GP17

Notes on the Sharp protocol:
  * Chip select is ACTIVE HIGH (opposite of most SPI devices).
  * The panel expects data LSB-first, but the RP2 hardware SPI only sends
    MSB-first. Pixel rows are stored as framebuf.MONO_HLSB (leftmost pixel in
    the MSB), which comes out in the right order when sent MSB-first. Only the
    command byte and line-address bytes need bit-reversing.
  * Pixel value 1 = white (reflective), 0 = black.
  * The VCOM bit must flip at least once per second to stop a DC bias
    building up in the LCD. start_auto_vcom() does this from a timer.
"""

import framebuf
from machine import Pin, SPI, Timer
from time import sleep_us

WIDTH = 400
HEIGHT = 240
_LINE_BYTES = WIDTH // 8       # 50 bytes of pixels per line
_TX_LINE = _LINE_BYTES + 2     # + line-address byte + trailing 0x00

# Commands, already bit-reversed for MSB-first sending.
_CMD_WRITE = 0x80  # M0 (0x01 LSB-first)
_CMD_VCOM = 0x40   # M1 (0x02 LSB-first)
_CMD_CLEAR = 0x20  # M2 (0x04 LSB-first)

WHITE = 1
BLACK = 0


def _reverse_bits(b):
    r = 0
    for _ in range(8):
        r = (r << 1) | (b & 1)
        b >>= 1
    return r


class SharpMemoryDisplay(framebuf.FrameBuffer):
    def __init__(self, cs=17, sck=18, mosi=19, baudrate=2_000_000):
        self.spi = SPI(0, baudrate=baudrate, polarity=0, phase=0,
                       sck=Pin(sck), mosi=Pin(mosi))
        self.cs = Pin(cs, Pin.OUT, value=0)
        self.width = WIDTH
        self.height = HEIGHT
        self._vcom = 0
        self._busy = False
        self._timer = None
        self._cmd2 = bytearray(2)

        # The transmit buffer is laid out exactly as the panel wants it:
        #   [cmd] + 240 x ([addr][50 pixel bytes][0x00]) + [0x00]
        # The framebuffer draws straight into it: it starts at the first pixel
        # byte and steps _TX_LINE bytes per row, so drawing never touches the
        # address/padding bytes and show() needs no copying.
        self._tx = bytearray(1 + HEIGHT * _TX_LINE + 1)
        for line in range(HEIGHT):
            self._tx[1 + line * _TX_LINE] = _reverse_bits(line + 1)
        super().__init__(memoryview(self._tx)[2:], WIDTH, HEIGHT,
                         framebuf.MONO_HLSB, _TX_LINE * 8)

        self.fill(WHITE)
        self.clear()

    # --- low level -------------------------------------------------------
    def _send(self, data):
        self._busy = True
        self.cs.value(1)
        sleep_us(6)   # CS setup time (datasheet: >= 3 us)
        self.spi.write(data)
        sleep_us(2)   # CS hold time (datasheet: >= 1 us)
        self.cs.value(0)
        self._busy = False

    def _command(self, cmd):
        """Send a 2-byte command, flipping VCOM as it goes."""
        self._vcom ^= _CMD_VCOM
        self._cmd2[0] = cmd | self._vcom
        self._send(self._cmd2)

    def toggle_vcom(self):
        """Flip VCOM without changing the picture."""
        if not self._busy:  # a frame is being sent; show() flips VCOM anyway
            self._command(0)

    def start_auto_vcom(self, period_ms=500):
        """Toggle VCOM from a hardware timer so it keeps running even while
        the main loop is blocked (e.g. waiting on a network request)."""
        self._timer = Timer(period=period_ms, mode=Timer.PERIODIC,
                            callback=lambda t: self.toggle_vcom())

    def stop_auto_vcom(self):
        if self._timer:
            self._timer.deinit()
            self._timer = None

    def clear(self):
        """Hardware clear: blanks the panel to white (framebuffer not touched)."""
        self._command(_CMD_CLEAR)

    def show(self):
        """Send the whole framebuffer to the panel."""
        self._vcom ^= _CMD_VCOM
        self._tx[0] = _CMD_WRITE | self._vcom
        self._send(self._tx)
