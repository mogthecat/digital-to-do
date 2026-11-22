# digital-to-do

A to-do list display that fetches tasks from the Todoist API and shows them on a Sharp Memory Display, with three buttons to refresh, scroll and tick tasks off. Programmed in MicroPython on a Raspberry Pi Pico 2 W.

## How to run

1. Flash MicroPython onto the Pico 2 W (the `RPI_PICO2_W` build already includes the `requests` and `network` modules this uses).
2. Copy `config_example.py` to `config.py` and fill in your Wi-Fi name, Wi-Fi password and Todoist API token (Todoist > Settings > Integrations > Developer).
3. Set the circuit up physically, making sure the right pins are correctly placed (see the pin layout below).
4. Copy the three files the Pico needs onto it and restart it, e.g. with `mpremote`:
   ```
   mpremote cp main.py fonts.py config.py : + reset
   ```
5. `main.py` runs automatically on boot, connects to Wi-Fi and shows your Todoist Inbox. It re-fetches the list every minute.

### Files

| File | What it is |
| --- | --- |
| `main.py` | Everything that runs on the Pico: display driver, font drawing, Wi-Fi, Todoist and buttons |
| `fonts.py` | Bitmap font data (generated, don't edit by hand) |
| `config_example.py` | Template for `config.py`, which holds your Wi-Fi details and Todoist token and is never uploaded to GitHub |
| `tools/make_fonts.py` | Runs on your computer to regenerate `fonts.py` |

### Buttons

| Button | Action |
| --- | --- |
| GP13 | Refresh the list from Todoist |
| GP14 | Move the highlight down to the next task (wraps back to the top) |
| GP15 | Mark the highlighted task as complete in Todoist |

Each button press is also printed in the terminal, which helps when debugging.

## Equipment
- Raspberry Pi Pico 2 W
> [!NOTE]
> Any microcontroller with network access and MicroPython support should be acceptable, but the pin numbers will need changing.
- Adafruit Sharp Memory Display 2.7" 400x240 Monochrome
> [!NOTE]
> The screen only needs power when it changes, and the picture stays on it without refreshing. The driver for it is the `Display` class in `main.py`.
- 3 push buttons
- Breadboard and pin-to-pin wires
> [!WARNING]
> Many full-size breadboards have power rails that are split in the middle. If the screen stays blank or the buttons do nothing, check that both halves of the rails are joined. This is a problem I encountered and spent way too long troubleshooting. 
- A Todoist account and API token.

## Pin Layout

| Display breakout | Pico 2 W |
| --- | --- |
| VIN | 3V3(OUT), physical pin 36 |
| GND | GND, physical pin 38 |
| CLK | GP18 (SPI0 SCK), physical pin 24 |
| DI | GP19 (SPI0 TX/MOSI), physical pin 25 |
| CS | GP17, physical pin 22 |

The three buttons connect GP13, GP14 and GP15 to GND. The Pico's internal pull-up resistors are used, so no extra resistors are needed.

> [!NOTE]
> GP numbers are different to the physical pin numbers. The display's CS pin is active HIGH, which is the opposite of most SPI devices, and the driver handles this.

## Fonts

The text uses CMU Serif, converted into bitmap fonts in `fonts.py` by `tools/make_fonts.py`. To change the font or size, edit `FONTS` in that script, run it on your computer with `python3 tools/make_fonts.py` (needs Pillow), and copy the new `fonts.py` onto the Pico.

## Photographs

![Full project](images/full-project.jpg)
Picture 1: Full project with the Pico 2 W, Sharp Memory Display and three buttons.

![Task list](images/task-list.jpg)
Picture 2: The Todoist Inbox on the display with the third task highlighted.

![Buttons](images/buttons.jpg)
Picture 3: Left side view.

![Pico connections](images/pico-connections.jpg)
Picture 4: Right side view.

## Footnote

> [!WARNING]
> This repository is not planned on being maintained. It is just a place to upload my code. If there are any questions regarding code, setup, etc, I am happy to answer them. Otherwise, there will be few changes to this repository.
