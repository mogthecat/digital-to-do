"""Draw proportional bitmap fonts (made by tools/make_fonts.py) on a framebuf."""

import framebuf


class BitmapFont:
    def __init__(self, module):
        self.height = module.HEIGHT
        self._widths = module.WIDTHS
        self._unknown = ord("?") - 32
        self._palette = framebuf.FrameBuffer(bytearray(1), 2, 1, framebuf.MONO_HLSB)
        # One small FrameBuffer per glyph, built once so drawing allocates nothing.
        data = memoryview(module.DATA)
        self._glyphs = []
        for w, off in zip(module.WIDTHS, module.OFFSETS):
            size = ((w + 7) // 8) * self.height
            self._glyphs.append(framebuf.FrameBuffer(
                data[off:off + size], w, self.height, framebuf.MONO_HLSB))

    def _index(self, ch):
        i = ord(ch) - 32  # the font starts at the space character
        return i if 0 <= i < len(self._widths) else self._unknown

    def width(self, s):
        return sum(self._widths[self._index(ch)] for ch in s)

    def _fitting_chars(self, s, max_w):
        """How many leading characters of s fit in max_w pixels."""
        w = 0
        for n, ch in enumerate(s):
            w += self._widths[self._index(ch)]
            if w > max_w:
                return n
        return len(s)

    def fit(self, s, max_w):
        """Shorten s with '...' so it fits in max_w pixels."""
        if self.width(s) <= max_w:
            return s
        return s[:self._fitting_chars(s, max_w - self.width("..."))] + "..."

    def wrap(self, s, max_w, max_lines=None):
        """Word-wrap s into lines no wider than max_w pixels. With max_lines,
        extra lines are dropped and the last line ends in '...'."""
        lines, line = [], ""
        for word in s.split():
            candidate = line + " " + word if line else word
            if self.width(candidate) <= max_w:
                line = candidate
                continue
            if line:
                lines.append(line)
            while self.width(word) > max_w:  # a single word too long: break it
                n = max(1, self._fitting_chars(word, max_w))
                lines.append(word[:n])
                word = word[n:]
            line = word
        if line:
            lines.append(line)
        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = self.fit(lines[-1] + "...", max_w)
        return lines or [""]

    def draw(self, fb, s, x, y, c=0):
        """Draw string s on framebuffer fb with colour c (transparent background)."""
        pal = self._palette
        pal.pixel(0, 0, 1 - c)  # glyph background -> made transparent by key
        pal.pixel(1, 0, c)      # glyph ink -> colour c
        for ch in s:
            i = self._index(ch)
            fb.blit(self._glyphs[i], x, y, 1 - c, pal)
            x += self._widths[i]
