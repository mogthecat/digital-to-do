"""
Todoist Inbox on a Sharp Memory Display - Raspberry Pi Pico 2 W / MicroPython.

Display (Adafruit 2.7" 400x240): CLK -> GP18, DI -> GP19, CS -> GP17.
Buttons (GPIO -> button -> GND): see BUTTONS below.
Secrets live in config.py (see config_example.py); fonts in fonts.py.
"""

import gc
import sys
import time
from collections import namedtuple

import framebuf
import machine
import network
import requests
from machine import Pin

import config
import fonts

WIDTH, HEIGHT = 400, 240
LINE_BYTES = WIDTH // 8 + 2  # per display line: address + 50 pixel bytes + trailer
BLACK, WHITE = 0, 1
BUTTONS = ((13, "Refresh"), (14, "Next"), (15, "Done"))  # (GPIO, label)
API = "https://api.todoist.com/api/v1"


def api(method, path):
    gc.collect()
    r = requests.request(method, API + path, timeout=15,
                         headers={"Authorization": "Bearer " + config.TODOIST_TOKEN})
    body = r.content  # reads the whole reply and closes the connection
    if r.status_code >= 300:
        raise OSError("Todoist HTTP %d" % r.status_code)
    return r.json() if body else None


class Display(framebuf.FrameBuffer):
    """Sharp Memory Display driver. The panel wants each line sent as
    [address][50 pixel bytes][0x00], so the framebuffer draws straight into
    a buffer laid out that way (via the stride) and show() just sends it.
    Data is LSB-first but RP2 SPI is MSB-first, so only the command and
    address bytes are bit-reversed; pixels use MONO_HLSB, 1 = white."""

    def __init__(self):
        self.spi = machine.SPI(0, baudrate=2_000_000, sck=Pin(18), mosi=Pin(19))
        self.cs = Pin(17, Pin.OUT, value=0)  # chip select is active HIGH
        self.tx = bytearray(1 + HEIGHT * LINE_BYTES + 1)
        for line in range(HEIGHT):
            n = line + 1  # line address, bit-reversed
            self.tx[1 + line * LINE_BYTES] = sum(((n >> b) & 1) << (7 - b) for b in range(8))
        super().__init__(memoryview(self.tx)[2:], WIDTH, HEIGHT, framebuf.MONO_HLSB, LINE_BYTES * 8)
        self.hold = bytearray(2)
        self.vcom = 0
        self.busy = False
        # VCOM must flip at least once a second or the LCD is damaged over
        # time; a timer keeps doing it even while a network request blocks.
        self.timer = machine.Timer(period=500, callback=lambda t: self.busy or self._send(self.hold, 0))

    def _send(self, buf, cmd):
        self.busy = True
        self.vcom ^= 0x40
        buf[0] = cmd | self.vcom
        try:
            self.cs(1)
            time.sleep_us(6)
            self.spi.write(buf)
            time.sleep_us(2)
        finally:  # even if the write fails, so the VCOM timer keeps running
            self.cs(0)
            self.busy = False

    def show(self):
        self._send(self.tx, 0x80)


class Font:
    """Proportional bitmap font from fonts.py (characters 32-126)."""

    def __init__(self, font):
        self.height, self.widths, data = font
        data = memoryview(data)
        self.glyphs, offset = [], 0
        for w in self.widths:
            size = (w + 7) // 8 * self.height
            self.glyphs.append(framebuf.FrameBuffer(data[offset:offset + size], w, self.height, framebuf.MONO_HLSB))
            offset += size
        self.palette = framebuf.FrameBuffer(bytearray(1), 2, 1, framebuf.MONO_HLSB)

    def _index(self, ch):
        i = ord(ch) - 32
        return i if 0 <= i < len(self.widths) else ord("?") - 32

    def width(self, s):
        return sum(self.widths[self._index(ch)] for ch in s)

    def chars_that_fit(self, s, max_w):
        w = 0
        for n, ch in enumerate(s):
            w += self.widths[self._index(ch)]
            if w > max_w:
                return n
        return len(s)

    def fit(self, s, max_w):
        """Shorten s with '...' so it fits in max_w pixels."""
        if self.width(s) <= max_w:
            return s
        return s[:self.chars_that_fit(s, max_w - self.width("..."))].rstrip() + "..."

    def wrap(self, s, max_w, max_lines):
        """Word-wrap s into at most max_lines lines no wider than max_w."""
        lines, line = [], ""
        for word in s.split():
            test = (line + " " + word).strip()
            if self.width(test) <= max_w:
                line = test
                continue
            if line:
                lines.append(line)
            while self.width(word) > max_w:  # one word too long: break it
                n = max(1, self.chars_that_fit(word, max_w))
                lines.append(word[:n])
                word = word[n:]
            line = word
        lines.append(line)
        if len(lines) > max_lines:  # cut off, ending the last line with "..."
            lines[max_lines - 1] = self.fit(lines[max_lines - 1] + " " + lines[max_lines], max_w)
            del lines[max_lines:]
        return lines

    def draw(self, fb, s, x, y, c=BLACK):
        self.palette.pixel(0, 0, 1 - c)  # glyph background -> transparent
        self.palette.pixel(1, 0, c)      # glyph ink -> colour c
        for ch in s:
            i = self._index(ch)
            fb.blit(self.glyphs[i], x, y, 1 - c, self.palette)
            x += self.widths[i]


HEADER, BODY, SMALL = Font(fonts.HEADER), Font(fonts.BODY), Font(fonts.SMALL)

# Layout (pixels), worked out from the font sizes
LIST_TOP = HEADER.height + 7
FOOTER_Y = HEIGHT - SMALL.height - 4
LINE_H = BODY.height + 1
PAD = 3                     # space above and below each task
TEXT_X = 20                 # task text starts here, bullet to its left
MAX_LINES = 4               # longer tasks are cut off with "..."
HINTS = "   ".join("%d %s" % b for b in BUTTONS)
HINTS_X = WIDTH - 4 - SMALL.width(HINTS)

Task = namedtuple("Task", ("id", "content", "lines", "height"))


def make_task(task_id, content):
    lines = BODY.wrap(content, WIDTH - TEXT_X - 6, MAX_LINES)
    return Task(task_id, content, lines, len(lines) * LINE_H + 2 * PAD)


class App:
    def __init__(self):
        self.d = Display()
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.tasks = None    # None until the first successful fetch
        self.selected = 0
        self.top = 0         # first task shown (for scrolling)
        self.status = ""

    def position(self):
        return "%d of %d" % (self.selected + 1, len(self.tasks))

    def render(self):
        d = self.d
        d.fill(WHITE)
        HEADER.draw(d, "Inbox", 6, 2)
        d.fill_rect(0, LIST_TOP - 4, WIDTH, 2, BLACK)
        if self.tasks:
            pos = self.position()
            SMALL.draw(d, pos, WIDTH - 6 - SMALL.width(pos), 2 + HEADER.height - SMALL.height)
            # scroll so the selected task is fully on screen
            self.top = min(self.top, self.selected)
            while sum(t.height for t in self.tasks[self.top:self.selected + 1]) > FOOTER_Y - LIST_TOP:
                self.top += 1
            y = LIST_TOP
            for i, task in enumerate(self.tasks[self.top:], self.top):
                if y + task.height > FOOTER_Y:
                    break
                c = WHITE if i == self.selected else BLACK  # selected: white on black
                if c == WHITE:
                    d.fill_rect(0, y, WIDTH, task.height, BLACK)
                d.ellipse(10, y + PAD + LINE_H // 2, 2, 2, c, True)  # bullet
                for n, line in enumerate(task.lines):
                    BODY.draw(d, line, TEXT_X, y + PAD + n * LINE_H, c)
                y += task.height
        elif self.tasks is not None:
            HEADER.draw(d, "All done!", (WIDTH - HEADER.width("All done!")) // 2, 100)
        d.hline(0, FOOTER_Y, WIDTH, BLACK)
        SMALL.draw(d, self.status, 4, FOOTER_Y + 3)
        SMALL.draw(d, HINTS, HINTS_X, FOOTER_Y + 3)
        d.show()

    def set_status(self, msg):
        print(msg)
        self.status = SMALL.fit(msg, HINTS_X - 12)
        self.render()

    def online(self, busy_msg, action):
        """Connect Wi-Fi if needed, show progress, run action, then show
        the status it returns (or the error)."""
        try:
            if not self.wlan.isconnected():
                self.set_status("Connecting to Wi-Fi...")
                self.wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
                for _ in range(80):  # up to 20 s
                    if self.wlan.isconnected():
                        break
                    time.sleep_ms(250)
                else:
                    status = self.wlan.status()
                    self.wlan.disconnect()  # cancel the attempt before retrying later
                    raise OSError("Wi-Fi did not connect (status %d)" % status)
            self.set_status(busy_msg)
            self.set_status(action())
        except Exception as e:
            self.set_status("Error: %s" % e)

    def refresh(self):
        self.last_refresh = time.ticks_ms()
        self.online("Refreshing...", self.fetch)

    def fetch(self):
        found, cursor = [], ""
        while True:  # Todoist sends tasks in pages of up to 50
            page = api("GET", "/tasks/filter?query=%23Inbox&limit=50" + (cursor and "&cursor=" + cursor))
            found += [(t.get("child_order", 0), t["id"], t["content"]) for t in page["results"]]
            cursor = page.get("next_cursor")
            del page  # free this page before downloading the next
            if not cursor:
                break
        found.sort()
        old_id = self.tasks[self.selected].id if self.tasks else None
        self.tasks = [make_task(task_id, content) for _, task_id, content in found]
        ids = [t.id for t in self.tasks]
        self.selected = ids.index(old_id) if old_id in ids else 0  # keep selection
        return "Updated: %d task%s" % (len(self.tasks), "" if len(self.tasks) == 1 else "s")

    def next_task(self):
        if self.tasks:
            self.selected = (self.selected + 1) % len(self.tasks)
            print("Selected", self.position(), self.tasks[self.selected].content)
            self.render()

    def complete(self):
        if self.tasks:
            self.online("Completing...", self.close_selected)

    def close_selected(self):
        task = self.tasks[self.selected]
        api("POST", "/tasks/%s/close" % task.id)
        self.tasks.pop(self.selected)
        self.selected = min(self.selected, max(0, len(self.tasks) - 1))
        return "Done: " + task.content

    def run(self):
        self.refresh()
        pins = [Pin(n, Pin.IN, Pin.PULL_UP) for n, _ in BUTTONS]
        actions = (self.refresh, self.next_task, self.complete)  # same order as BUTTONS
        level = [p.value() for p in pins]  # settled level of each pin (0 = pressed)
        last = level[:]                    # previous raw reading
        while True:
            for i, pin in enumerate(pins):
                now = pin.value()
                # Debounce: only accept a new level once two readings 20 ms apart agree.
                if now == last[i] and now != level[i]:
                    level[i] = now
                    if now == 0:  # pressed = pin pulled to GND
                        print("[GP%d %s] pressed" % BUTTONS[i])
                        actions[i]()
                last[i] = now
            if time.ticks_diff(time.ticks_ms(), self.last_refresh) > config.AUTO_REFRESH_S * 1000:
                self.refresh()
            time.sleep_ms(20)


if __name__ == "__main__":
    try:
        App().run()
    except Exception as e:  # never stay dead when running on its own: restart
        # (Ctrl-C is a KeyboardInterrupt, not an Exception, so it still stops)
        sys.print_exception(e)
        time.sleep(10)
        machine.reset()
