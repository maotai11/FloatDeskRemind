"""
Generate icon.png and icon.ico for FloatDesk Remind.
Design: indigo rounded square, white floating-window silhouette with three task lines.
Run: python scripts/gen_icon.py
"""
import math
import struct
import zlib
from pathlib import Path

# Output paths
ASSETS = Path(__file__).parent.parent / 'assets'
ASSETS.mkdir(exist_ok=True)

# -- Pure-stdlib PNG writer (no PIL dependency) --

def _write_chunk(chunk_type: bytes, data: bytes) -> bytes:
    c = chunk_type + data
    return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)


def _png_bytes(pixels: list[list[tuple]], size: int) -> bytes:
    """pixels[y][x] = (R,G,B,A)"""
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)
    ihdr = _write_chunk(b'IHDR', ihdr_data)

    raw_rows = []
    for row in pixels:
        row_bytes = bytearray([0])  # filter type None
        for r, g, b, a in row:
            row_bytes += bytearray([r, g, b, a])
        raw_rows.append(bytes(row_bytes))
    compressed = zlib.compress(b''.join(raw_rows), 9)
    idat = _write_chunk(b'IDAT', compressed)
    iend = _write_chunk(b'IEND', b'')
    return sig + ihdr + idat + iend


def _lerp(a, b, t):
    return a + (b - a) * t


def _in_rounded_rect(x, y, x0, y0, x1, y1, r) -> float:
    """Anti-aliased coverage: 1.0 inside, 0.0 outside, partial at edges."""
    # clamp to nearest corner circle
    cx = max(x0 + r, min(x1 - r, x))
    cy = max(y0 + r, min(y1 - r, y))
    dist = math.hypot(x - cx, y - cy)
    # distance from corner arc edge
    edge_dist = dist - r if (x < x0 + r or x > x1 - r) and (y < y0 + r or y > y1 - r) else 0
    # smooth AA within 1px
    if edge_dist > 1.0:
        return 0.0
    if edge_dist < 0.0:
        # check rect bounds
        if x0 <= x <= x1 and y0 <= y <= y1:
            return 1.0
        return 0.0
    return 1.0 - edge_dist


def render(size: int) -> list[list[tuple]]:
    s = size
    BG = (79, 70, 229)        # #4F46E5 indigo
    WIN_BG = (255, 255, 255)   # window body white
    HDR = (199, 196, 246)      # light indigo header #C7C4F6
    LINE = (179, 176, 230)     # task line color

    margin = s * 0.12
    radius = s * 0.18

    # floating window bounds (inside the icon square)
    wx0 = s * 0.16
    wx1 = s * 0.84
    wy0 = s * 0.18
    wy1 = s * 0.82
    wr = s * 0.08

    # header bar inside window
    hdr_h = (wy1 - wy0) * 0.22
    hdr_y1 = wy0 + hdr_h

    # task lines: 3 lines below header
    line_x0 = wx0 + s * 0.06
    line_x1 = wx1 - s * 0.06
    line_h = s * 0.04
    line_r = line_h / 2
    lines_y_start = hdr_y1 + s * 0.06

    line_ys = [lines_y_start + i * (line_h + s * 0.055) for i in range(3)]
    line_widths = [0.75, 0.55, 0.45]  # fraction of full width

    pixels = []
    for y in range(s):
        row = []
        for x in range(s):
            # -- Background rounded square --
            cov_bg = _in_rounded_rect(x + 0.5, y + 0.5, margin, margin,
                                       s - margin, s - margin, radius)

            if cov_bg <= 0:
                row.append((0, 0, 0, 0))
                continue

            # Start with indigo bg
            r, g, b = BG
            a = int(cov_bg * 255)

            # -- Window body --
            cov_win = _in_rounded_rect(x + 0.5, y + 0.5, wx0, wy0, wx1, wy1, wr)
            if cov_win > 0:
                # Blend window bg
                wr_c, wg_c, wb_c = WIN_BG
                r = int(_lerp(r, wr_c, cov_win))
                g = int(_lerp(g, wg_c, cov_win))
                b = int(_lerp(b, wb_c, cov_win))

                # -- Header bar (clipped to window top) --
                cov_hdr = _in_rounded_rect(x + 0.5, y + 0.5, wx0, wy0, wx1, hdr_y1, wr)
                # only top corners rounded; bottom of header is flat
                flat_hdr = 1.0 if (wx0 <= x + 0.5 <= wx1 and wy0 + wr <= y + 0.5 <= hdr_y1) else 0.0
                cov_hdr = max(cov_hdr, flat_hdr * cov_win)
                if cov_hdr > 0:
                    hr_c, hg_c, hb_c = HDR
                    r = int(_lerp(r, hr_c, cov_hdr * cov_win))
                    g = int(_lerp(g, hg_c, cov_hdr * cov_win))
                    b = int(_lerp(b, hb_c, cov_hdr * cov_win))

                # -- Task lines --
                for i, ly in enumerate(line_ys):
                    lx1 = line_x0 + (line_x1 - line_x0) * line_widths[i]
                    cov_line = _in_rounded_rect(x + 0.5, y + 0.5,
                                                line_x0, ly, lx1, ly + line_h, line_r)
                    if cov_line > 0:
                        lr_c, lg_c, lb_c = LINE
                        blend = cov_line * cov_win
                        r = int(_lerp(r, lr_c, blend))
                        g = int(_lerp(g, lg_c, blend))
                        b = int(_lerp(b, lb_c, blend))

            row.append((
                max(0, min(255, r)),
                max(0, min(255, g)),
                max(0, min(255, b)),
                a
            ))
        pixels.append(row)
    return pixels


def write_ico(png_256: bytes, png_48: bytes, png_32: bytes, png_16: bytes, path: Path):
    """Write a multi-size .ico from PNG blobs (ICO with PNG compression, Vista+)."""
    images = [
        (256, png_256),
        (48,  png_48),
        (32,  png_32),
        (16,  png_16),
    ]
    # ICO header: ICONDIR
    count = len(images)
    header = struct.pack('<HHH', 0, 1, count)  # reserved, type=1(icon), count

    dir_entry_size = 16
    data_offset = 6 + count * dir_entry_size

    entries = b''
    data_blobs = b''
    current_offset = data_offset

    for w, png in images:
        size_val = 0 if w == 256 else w  # 0 means 256 in ICO format
        entry = struct.pack('<BBBBHHII',
            size_val, size_val,  # width, height
            0,                   # color count (0 = no palette)
            0,                   # reserved
            1,                   # color planes
            32,                  # bits per pixel
            len(png),            # size of image data
            current_offset       # offset of image data
        )
        entries += entry
        data_blobs += png
        current_offset += len(png)

    with open(path, 'wb') as f:
        f.write(header + entries + data_blobs)


if __name__ == '__main__':
    print('Rendering icon sizes...')
    sizes = [256, 48, 32, 16]
    pngs = {}
    for sz in sizes:
        print(f'  {sz}x{sz}...')
        px = render(sz)
        pngs[sz] = _png_bytes(px, sz)

    png_path = ASSETS / 'icon.png'
    png_path.write_bytes(pngs[256])
    print(f'Wrote {png_path}')

    ico_path = ASSETS / 'icon.ico'
    write_ico(pngs[256], pngs[48], pngs[32], pngs[16], ico_path)
    print(f'Wrote {ico_path}')
    print('Done.')
