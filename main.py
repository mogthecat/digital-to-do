"""
Todoist Inbox on a Sharp Memory Display - Pico 2 W / MicroPython.

Buttons (wired GPIO -> button -> GND):
    GP13  Refresh (re-fetch tasks from Todoist)
    GP14  Move selection down (wraps to the top)
    GP15  Mark the selected task complete
"""

import time
from collections import namedtuple
import config
import wifi
import font_body
import font_header
import font_small
from bitmap_font import BitmapFont
from buttons import Button
from sharp_memory_display import SharpMemoryDisplay, WIDTH, HEIGHT, BLACK, WHITE
from todoist import Todoist

HEADER = BitmapFont(font_header)
BODY = BitmapFont(font_body)
SMALL = BitmapFont(font_small)

# Layout (pixels), worked out from the font sizes
HEADER_Y = 2
LIST_TOP = HEADER_Y + HEADER.height + 5
FOOTER_Y = HEIGHT - SMALL.height - 4
LINE_H = BODY.height + 1   # line spacing inside a task
PAD = 3                    # space above and below each task
TEXT_X = 20                # task text starts here (bullet sits to its left)
TEXT_W = WIDTH - TEXT_X - 6
MAX_LINES = 4              # longer tasks are cut off with "..."
HINTS = "13 Refresh   14 Next   15 Done"
HINTS_X = WIDTH - 4 - SMALL.width(HINTS)

Task = namedtuple("Task", ("id", "content", "lines", "height"))


def make_task(task_id, content):
    lines = BODY.wrap(content, TEXT_W, MAX_LINES)
    return Task(task_id, content, lines, len(lines) * LINE_H + 2 * PAD)


class App:
    def __init__(self):
        self.d = SharpMemoryDisplay()
        self.d.start_auto_vcom()
        self.api = Todoist(config.TODOIST_TOKEN)
        self.tasks = []
        self.selected = 0
        self.top = 0         # first task shown (for scrolling)
        self.status = "Starting..."
        self.loaded = False
        self.last_refresh = time.ticks_ms()

    # --- drawing ---------------------------------------------------------
    def _position(self):
        return "%d of %d" % (self.selected + 1, len(self.tasks))

    def _scroll(self):
        """Move the window so the selected task is fully on screen."""
        if self.selected < self.top:
            self.top = self.selected
        space = FOOTER_Y - LIST_TOP
        while sum(t.height for t in self.tasks[self.top:self.selected + 1]) > space:
            self.top += 1

    def render(self):
        d = self.d
        d.fill(WHITE)

        HEADER.draw(d, "Inbox", 6, HEADER_Y)
        if self.tasks:
            pos = self._position()
            SMALL.draw(d, pos, WIDTH - 6 - SMALL.width(pos),
                       HEADER_Y + HEADER.height - SMALL.height)
        d.fill_rect(0, LIST_TOP - 4, WIDTH, 2, BLACK)

        if not self.tasks:
            if self.loaded:
                msg = "All done!"
                HEADER.draw(d, msg, (WIDTH - HEADER.width(msg)) // 2, 100)
        else:
            self._scroll()
            y = LIST_TOP
            for i in range(self.top, len(self.tasks)):
                task = self.tasks[i]
                if y + task.height > FOOTER_Y:
                    break
                c = BLACK
                if i == self.selected:
                    d.fill_rect(0, y, WIDTH, task.height, BLACK)
                    c = WHITE
                d.ellipse(10, y + PAD + LINE_H // 2, 2, 2, c, True)  # bullet
                for n, line in enumerate(task.lines):
                    BODY.draw(d, line, TEXT_X, y + PAD + n * LINE_H, c)
                y += task.height

        d.hline(0, FOOTER_Y, WIDTH, BLACK)
        SMALL.draw(d, SMALL.fit(self.status, HINTS_X - 12), 4, FOOTER_Y + 3)
        SMALL.draw(d, HINTS, HINTS_X, FOOTER_Y + 3)
        d.show()

    def set_status(self, msg):
        print(msg)
        self.status = msg
        self.render()

    # --- actions ---------------------------------------------------------
    def _online(self, busy_msg, action):
        """Run a network action: connect Wi-Fi if needed, show progress,
        then show the status it returns (or the error)."""
        try:
            if not wifi.is_connected():
                self.set_status("Connecting to Wi-Fi...")
                print("Wi-Fi IP:", wifi.connect(config.WIFI_SSID, config.WIFI_PASSWORD))
            self.set_status(busy_msg)
            self.set_status(action())
        except Exception as e:
            self.set_status("Error: %s" % e)

    def refresh(self):
        self.last_refresh = time.ticks_ms()
        self._online("Refreshing...", self._fetch)

    def _fetch(self):
        sel_id = self.tasks[self.selected].id if self.tasks else None
        inbox = self.api.get_inbox_id()
        self.tasks = [make_task(tid, content) for tid, content in self.api.get_tasks(inbox)]
        self.loaded = True
        ids = [t.id for t in self.tasks]
        self.selected = ids.index(sel_id) if sel_id in ids else 0
        n = len(self.tasks)
        return "Updated: %d task%s" % (n, "" if n == 1 else "s")

    def move_down(self):
        if self.tasks:
            self.selected = (self.selected + 1) % len(self.tasks)
            self.render()

    def complete_selected(self):
        if self.tasks:
            self._online("Completing...", self._complete)

    def _complete(self):
        task = self.tasks[self.selected]
        self.api.close_task(task.id)
        self.tasks.pop(self.selected)
        self.selected = min(self.selected, max(0, len(self.tasks) - 1))
        return "Done: " + task.content

    # --- main loop -------------------------------------------------------
    def _selected_text(self):
        if not self.tasks:
            return "(no tasks)"
        return '%s "%s"' % (self._position(), self.tasks[self.selected].content)

    def run(self):
        self.render()
        self.refresh()
        b_refresh, b_next, b_done = Button(13), Button(14), Button(15)
        auto_ms = config.AUTO_REFRESH_S * 1000
        print("Ready. Buttons: GP13 refresh, GP14 next, GP15 done")
        while True:
            if b_refresh.pressed():
                print("[GP13] Refresh pressed")
                self.refresh()
            elif b_next.pressed():
                self.move_down()
                print("[GP14] Next pressed -> selected", self._selected_text())
            elif b_done.pressed():
                print("[GP15] Done pressed on", self._selected_text())
                self.complete_selected()
            elif time.ticks_diff(time.ticks_ms(), self.last_refresh) > auto_ms:
                print("[auto] refresh every %d s" % config.AUTO_REFRESH_S)
                self.refresh()
            time.sleep_ms(20)


def start():
    import machine
    import sys
    print("To-do display starting...")
    time.sleep_ms(500)  # let power settle when booting from USB
    app = None
    try:
        app = App()
        app.run()
    except KeyboardInterrupt:  # Ctrl-C from the computer: stop cleanly
        if app:
            app.d.stop_auto_vcom()
        raise
    except Exception as e:
        # Never leave the device dead when running on its own:
        # show the error, then restart after 10 s.
        sys.print_exception(e)
        if app:
            try:
                app.set_status("Crashed: %s - restarting" % e)
            except Exception:
                pass
        time.sleep(10)
        machine.reset()


if __name__ == "__main__":
    start()
