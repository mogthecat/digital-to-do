"""Hardware check for the Sharp Memory Display. Run with: mpremote run test_display.py"""

import time
import font_body
import font_header
from bitmap_font import BitmapFont
from sharp_memory_display import SharpMemoryDisplay, BLACK, WHITE

d = SharpMemoryDisplay()
d.start_auto_vcom()

d.fill(WHITE)
d.rect(0, 0, d.width, d.height, BLACK)
BitmapFont(font_header).draw(d, "Display OK", 12, 8)
BitmapFont(font_body).draw(d, "Body font: The quick brown fox", 12, 44)
d.text("Built-in 8x8 font", 12, 72)

for row in range(8):  # checkerboard
    for col in range(16):
        if (row + col) % 2 == 0:
            d.fill_rect(12 + col * 12, 96 + row * 12, 12, 12, BLACK)

t0 = time.ticks_ms()
d.show()
print("show() took", time.ticks_diff(time.ticks_ms(), t0), "ms")
time.sleep(10)
d.stop_auto_vcom()
print("done")
