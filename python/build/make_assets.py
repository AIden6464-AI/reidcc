"""Build Reidcc's UI assets from the branding art: banner.png (image 1 crop) and reidcc.ico (the logo)."""
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter
BRAND = r"E:\reidcc\vision\branding"
OUT = r"E:\reidcc\assets"

# banner: the folder -> persona -> signal band, 720px wide so the whole launcher fits one screen
art = Image.open(BRAND + r"\Classical Blueprint Flow with Emerald Signal-1.png").convert("RGB")
band = art.crop((40, 250, 1632, 640))
w = 720
band.resize((w, round(band.height * w / band.width)), Image.LANCZOS).save(OUT + r"\banner.png", optimize=True)

# --- the gate (SPEC-gate.md), rebuilt 2026-11-19 (Reid: "they're not sized right [...] it's kind of just looks
# like a picture and like unwell done animation"). Everything is drawn on image 2 at its full 1672 px and
# filmed by a camera into frames the size of the launcher (1000 x 880), so the gate fills the window:
#   ghost + rise  the gate's blueprint lines, then the stone fills in under them
#   ignite        the keystone flares and light runs from it down the gate's mouldings
#   open          the doors swing open on real light (falloff, halo, spill on the steps, bloom) while the
#                 camera pushes in, accelerating, through the passage; the light then goes dark, which is
#                 where the session window appears
import os, json, math, shutil
import numpy as np


def ease(t):                             # fast start, soft stop, no overshoot (design doc curve)
    return 1 - (1 - t) ** 3


def smooth(t):                           # ease in and out
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def to_img(a):
    return Image.fromarray(np.clip(np.asarray(a, np.float32) + 0.5, 0, 255).astype(np.uint8))


def feather(size, ex, ey):
    """0 at the edges rising to 1 over ex / ey pixels (h x w)."""
    w, h = size
    fx = np.minimum(np.arange(w), np.arange(w)[::-1]) / ex
    fy = np.minimum(np.arange(h), np.arange(h)[::-1]) / ey
    return np.clip(np.minimum(fx[None, :], fy[:, None]), 0, 1)


GATE_BG = (3, 2, 2)                      # median of the art's background; the gate window's colour


def over_bg(im, a, bg=GATE_BG):
    arr = np.asarray(im, np.float32)
    return to_img(arr * a[..., None] + np.array(bg, np.float32) * (1 - a[..., None]))


def glow(size, centre, radius, strength):
    """Emerald halo to add onto the art: emerald-glow #00B15C, hot core #07E86A."""
    g = Image.new("RGB", size, (0, 0, 0))
    d = ImageDraw.Draw(g)
    x, y = centre
    d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=tuple(round(c * strength) for c in (0, 177, 92)))
    core = radius * 0.28
    d.ellipse((x - core, y - core, x + core, y + core), fill=tuple(round(c * strength) for c in (7, 232, 106)))
    return g.filter(ImageFilter.GaussianBlur(radius * 0.55))


def save_frame(im, path):
    """256 colours, dithered: looks the same on this art and halves the files."""
    im.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(path, optimize=True)


# --- the doors (Reid, 2026-11-17: "for both the gui and tui"): a pair of lion doors in the passage that
# swing open. Leaves from "Engraved Lion Door Collection.png" (the two single leaves on the right).
DOOR_ART = Image.open(BRAND + r"\Engraved Lion Door Collection.png").convert("RGB")
DOOR_MAX = math.radians(82)             # fully open: two thin slivers at the sides


def cut_leaf(box):
    im = DOOR_ART.crop(box)
    b = im.convert("L").point(lambda v: 255 if v > 12 else 0)
    for c in ((0, 0), (b.width - 1, 0), (0, b.height - 1), (b.width - 1, b.height - 1)):
        ImageDraw.floodfill(b, c, 128)  # background reachable from a corner
    alpha = b.point(lambda v: 0 if v == 128 else 255)
    im.putalpha(alpha)
    return im.crop(alpha.getbbox())


LEAF_L, LEAF_R = cut_leaf((806, 14, 1064, 908)), cut_leaf((1243, 14, 1502, 908))


def persp(dst, src):
    """Coefficients for Image.PERSPECTIVE mapping output points dst onto source points src."""
    A, B = [], []
    for (x, y), (X, Y) in zip(dst, src):
        A += [[x, y, 1, 0, 0, 0, -X * x, -X * y], [0, 0, 0, x, y, 1, -Y * x, -Y * y]]
        B += [X, Y]
    return np.linalg.solve(np.array(A, float), np.array(B, float)).tolist()


def swing(leaf, w, h, theta, hinge_left):
    """A leaf turned theta away from the viewer on its hinge: narrower, its free edge shorter, darker."""
    W, H = round(w), round(h)
    lf = leaf.resize((W, H), Image.LANCZOS)
    c, sn = math.cos(theta), math.sin(theta)
    if sn > 0:
        rgb = ImageEnhance.Brightness(lf.convert("RGB")).enhance(1 - 0.55 * sn)
        lf = Image.merge("RGBA", (*rgb.split(), lf.getchannel("A")))
    fw, k = max(1.0, W * c), H * 0.16 * sn
    src = [(0, 0), (W, 0), (W, H), (0, H)]
    if hinge_left:
        dst = [(0, 0), (fw, k * 0.55), (fw, H - k * 0.45), (0, H)]
    else:
        dst = [(W - fw, k * 0.55), (W, 0), (W, H), (W - fw, H - k * 0.45)]
    return lf.transform((W, H), Image.PERSPECTIVE, persp(dst, src), Image.BICUBIC)


def put_doors(img, x0, x1, top, bottom, theta=0.0):
    out, w, h = img.copy(), (x1 - x0) / 2, bottom - top
    for leaf, x, left in ((LEAF_L, x0, True), (LEAF_R, x0 + w, False)):
        d = swing(leaf, w, h, theta, left)
        out.paste(d, (round(x), round(top)), d)
    return out


BONE = np.array((214, 208, 200), np.float32)   # bone #D6D0C8
HOT = np.array((236, 232, 224), np.float32)


def make_light(size, x0, x1, floor, centre, r, unit):
    """lit(img, e): the passage (x0-x1, a half circle of radius r on centre, down to floor) fills with
    light to strength e: brightest low in the passage, a halo on the jambs, spill on the steps, bloom.
    unit: image pixels per gate.png pixel, so the light looks the same at any scale."""
    def mask(blur):
        m = Image.new("L", size, 0)
        d = ImageDraw.Draw(m)
        d.rectangle((x0, centre[1], x1, floor), fill=255)
        d.ellipse((centre[0] - r, centre[1] - r, centre[0] + r, centre[1] + r), fill=255)
        return np.asarray(m.filter(ImageFilter.GaussianBlur(blur)), np.float32) / 255
    inside, halo, bloom = mask(2 * unit), mask(16 * unit), mask(48 * unit)
    sp = Image.new("L", size, 0)
    ImageDraw.Draw(sp).polygon([(x0, floor - 4 * unit), (x1, floor - 4 * unit),
                                (x1 + 52 * unit, floor + 31 * unit), (x0 - 52 * unit, floor + 31 * unit)], fill=255)
    spill = np.asarray(sp.filter(ImageFilter.GaussianBlur(9 * unit)), np.float32) / 255
    gy, gx = np.mgrid[0:size[1], 0:size[0]]
    core = np.clip(1 - np.sqrt(((gx - centre[0]) / (r * 1.1)) ** 2 + ((gy - (floor - 47 * unit)) / (r * 2.2)) ** 2), 0, 1) ** 1.5
    light = BONE * (0.86 + 0.14 * core[..., None]) + (HOT - BONE) * core[..., None]
    glow_add = (halo * 0.42 + spill * 0.40 + bloom * 0.22)[..., None] * BONE / 255

    def lit(img, e):
        a = np.asarray(img, np.float32)
        k = (inside * 0.96 * e)[..., None]
        a = a * (1 - k) + light * k
        return to_img(255 - (255 - a) * (1 - glow_add * e))   # screen: the stone stays visible under it
    return lit


def camera(c0, w0, cp, zf, out_size):
    """cam(img, z): the view at zoom z. z = 1 frames c0 at width w0; as z grows the centre moves to cp
    (reached at zf) so the passage stays put on screen while the view pushes into it."""
    ow, oh = out_size

    def cam(img, z):
        p = (1 - 1 / z) / (1 - 1 / zf)
        cx, cy = c0[0] + (cp[0] - c0[0]) * p, c0[1] + (cp[1] - c0[1]) * p
        w = w0 / z
        h = w * oh / ow
        return img.resize(out_size, Image.LANCZOS, box=(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
    return cam


def push(u, zf):
    """The camera's zoom at u (0..1): slow while the doors open, then faster into the light."""
    return math.exp(math.log(zf) * (0.18 * u + 0.82 * u ** 2.4))


# image 2 at full size. Its baked-in "REIDCC · READY" tag (1480-1625, 900-911) is painted out; the app
# draws a live tag instead. Positions below are in gate.png's old 1000 px units (measured 2026-11-17) x K.
portal = Image.open(BRAND + r"\Emerald Portal_ Engraved Blueprint Monument.png").convert("RGB")
around = [portal.getpixel((x, y)) for x in range(1470, 1640, 4) for y in (890, 922)]
bg = tuple(sorted(c[i] for c in around)[len(around) // 2] for i in range(3))
ImageDraw.Draw(portal).rectangle((1474, 895, 1632, 917), fill=bg)
K = portal.width / 1000
world_plain = over_bg(portal, feather(portal.size, 70 * K, 50 * K))   # no visible border against the window
KEYSTONE = (500 * K, 202 * K)            # the emerald point
ARCH = tuple(v * K for v in (439, 239, 561, 447))   # the passage: x 439-561, apex 239, steps 447
ARCH_C, ARCH_R = (500 * K, 300 * K), 61 * K
doors = lambda im, theta=0.0: put_doors(im, ARCH[0], ARCH[2], ARCH[1], ARCH[3], theta)
lit = make_light(portal.size, ARCH[0], ARCH[2], ARCH[3], ARCH_C, ARCH_R, K)

FW, FH = 1000, 880                       # the launcher's client area (reid_gui.py: 1000 x 880)
C0, W0 = (500 * K, 319 * K), 520 * K     # the closed view: the monument and its lions, x 240-760, y 90-548
ZF = 5.2                                 # here the passage fills the frame
cam = camera(C0, W0, (500 * K, 380 * K), ZF, (FW, FH))
yy, xx = np.mgrid[0:FH, 0:FW]
VIG = feather((FW, FH), 46, 46) ** 0.8 * (1 - 0.22 * np.clip(((xx - FW / 2) / (FW / 2)) ** 2 + ((yy - FH / 2) / (FH / 2)) ** 2 - 0.35, 0, 1))
finish = lambda im: over_bg(im, VIG)     # edges fade into the window colour, so any window size looks right

# the trace: the gate's edges near the keystone, lit by a wave running out from it
lum = np.asarray(world_plain.convert("L").filter(ImageFilter.GaussianBlur(1.3 * K)), np.float32)
ey, ex = np.gradient(lum)
box = np.zeros_like(lum)
box[int(172 * K):int(452 * K), int(370 * K):int(632 * K)] = 1           # the gate building
box = np.asarray(to_img(box * 255).filter(ImageFilter.GaussianBlur(6 * K)), np.float32) / 255
EDGE = np.clip(np.hypot(ex, ey) / 9.0, 0, 1) ** 1.4 * box
gy, gx = np.mgrid[0:portal.height, 0:portal.width]
DKEY = np.sqrt((gx - KEYSTONE[0]) ** 2 + (gy - KEYSTONE[1]) ** 2) / K
EMERALD = np.array((0, 177, 92), np.float32)


def trace(img, t, fade=1.0):
    """t 0..1: how far the wave has run; behind it the lines keep a low glow, scaled by fade."""
    if fade <= 0:
        return img
    front = t * 290
    level = (np.exp(-((DKEY - front) / 22) ** 2) * 0.8 + (DKEY < front) * 0.2) * EDGE * fade
    return to_img(np.asarray(img, np.float32) + level[..., None] * EMERALD * 1.15)


for sub in ("gate_rise", "gate_ignite", "gate_open"):
    shutil.rmtree(os.path.join(OUT, sub), ignore_errors=True)
    os.makedirs(os.path.join(OUT, sub))

closed_world = doors(world_plain)
closed = finish(cam(closed_world, 1.0))
save_frame(closed, OUT + r"\gate.png")

# ghost: the gate's blueprint lines (and its emerald point) on the see-through key colour
KEY = (1, 1, 1)                          # Tk -transparentcolor
cl = np.asarray(cam(closed_world, 1.0).convert("L").filter(ImageFilter.GaussianBlur(1.1)), np.float32)
ly, lx = np.gradient(cl)
LINES = (np.clip(np.hypot(lx, ly) / 14.0, 0, 1) ** 1.2 * VIG)[..., None] * BONE
key_pt = (FW / 2 + (KEYSTONE[0] - C0[0]) * FW / W0, FH / 2 + (KEYSTONE[1] - C0[1]) * FW / W0)
ghost = np.clip(LINES + np.asarray(glow((FW, FH), key_pt, 26, 0.9), np.float32), 0, 255)
ghost[ghost.max(axis=2) < 40] = KEY
to_img(ghost).save(OUT + r"\gate_ghost.png", optimize=True)

# rise: the lines give way to the stone
N_RISE = 6
c_arr = np.asarray(closed, np.float32)
for i in range(N_RISE):
    a = ease((i + 1) / N_RISE)
    save_frame(to_img(255 - (255 - c_arr * a) * (1 - LINES * (1 - a) ** 0.7 / 255)), OUT + r"\gate_rise\%02d.png" % i)

# ignite: the keystone flares and settles while the trace runs down the gate
flare = [(14, .5), (24, .75), (34, .95), (42, 1.0), (46, .9), (44, .8), (42, .72), (40, .66)]
N_IGNITE = len(flare)
for i, (r, s) in enumerate(flare):
    w = trace(ImageChops.add(world_plain, glow(portal.size, KEYSTONE, r * K, s)), (i + 1) / N_IGNITE)
    save_frame(finish(cam(doors(w), 1.0)), OUT + r"\gate_ignite\%02d.png" % i)
settled = ImageChops.add(world_plain, glow(portal.size, KEYSTONE, flare[-1][0] * K, flare[-1][1]))

# open: doors, light and the push through the passage, then the light goes dark
N_OPEN = 30
for i in range(N_OPEN):
    u = i / (N_OPEN - 1)
    w = doors(lit(trace(settled, 1.0, fade=1 - smooth(u / 0.4)), smooth(u / 0.45)), DOOR_MAX * smooth(u / 0.5))
    f = cam(w, push(u, ZF))
    d = smooth((u - 0.84) / 0.16)
    if d > 0:
        f = Image.blend(f, Image.new("RGB", f.size, GATE_BG), d)
    save_frame(finish(f), OUT + r"\gate_open\%02d.png" % i)

# for reid_gui.py (no duplicated constants): frame sets with their design times in ms (x Gate.PACE)
meta = {"size": [FW, FH], "bg": "#%02x%02x%02x" % GATE_BG, "key": "#%02x%02x%02x" % KEY, "tag": [FW - 28, FH - 22],
        "steps": [["rise", N_RISE, 0, 180], ["ignite", N_IGNITE, 180, 180], ["open", N_OPEN, 360, 480]]}
with open(OUT + r"\gate.json", "w") as f:
    json.dump(meta, f, indent=1)
print("gate", meta)

# --- the TUI's art: the same images as terminal text. One cell = two pixels stacked ("▀": top pixel
# in the text colour, bottom in the background colour, 24-bit). Pre-rendered at a few widths so the
# TUI only has to print: assets\tui\<name>_<cols>.json.gz = list of frames, each a list of lines.
import gzip
TUI = os.path.join(OUT, "tui")
shutil.rmtree(TUI, ignore_errors=True)
os.makedirs(TUI)
QUANT = 6   # colour steps per channel: neighbouring cells share colours, so far fewer escape codes per frame


def ansi(im, clear_below=None):
    """im: RGB, even height. clear_below: luminance under which a pixel is left out, so the art sits
    on the terminal's own background (None: every pixel painted)."""
    im = im.point(lambda v: min(255, round(v / QUANT) * QUANT))
    px, (w, h) = im.load(), im.size
    lum = im.convert("L").load()
    lines = []
    for y in range(0, h, 2):
        out, fg, bg = [], None, None
        for x in range(w):
            t, b = px[x, y], px[x, y + 1]
            if clear_below is not None:
                t = None if lum[x, y] < clear_below else t
                b = None if lum[x, y + 1] < clear_below else b
            if t is None and b is None:
                ch, want_fg, want_bg = " ", fg, "49"
            elif t is None:
                ch, want_fg, want_bg = "▄", "38;2;%d;%d;%d" % b, "49"
            elif b is None:
                ch, want_fg, want_bg = "▀", "38;2;%d;%d;%d" % t, "49"
            elif t == b:
                ch, want_fg, want_bg = " ", fg, "48;2;%d;%d;%d" % b
            else:
                ch, want_fg, want_bg = "▀", "38;2;%d;%d;%d" % t, "48;2;%d;%d;%d" % b
            codes = [c for c, cur in ((want_fg, fg), (want_bg, bg)) if c != cur]
            if codes:
                out.append("\x1b[" + ";".join(codes) + "m")
                fg, bg = want_fg, want_bg
            out.append(ch)
        lines.append("".join(out) + "\x1b[0m")
    return lines


def fit(im, cols):
    rows = max(1, round(im.height * cols / im.width / 2))
    return im.resize((cols, rows * 2), Image.LANCZOS)


def save_tui(name, frames, sizes, clear_below=None):
    for cols in sizes:
        data = [ansi(fit(f, cols), clear_below) for f in frames]
        with gzip.open(os.path.join(TUI, "%s_%d.json.gz" % (name, cols)), "wt", encoding="utf-8") as f:
            json.dump(data, f)


# The TUI gate is the arch from "Engraved Arches and Pedestals.png" (Reid, 2026-11-17): one clean
# silhouette that still reads at ~40 terminal rows, where the portal painting turns to blocks.
# The sheet has it twice, unlit and with the keystone lit, 384 px apart. Positions below are in
# the 384x320 crop, measured 2026-11-17. It plays the GUI's story: fade in, ignite, open and push
# through the passage into the dark, where the session starts.
kit = Image.open(BRAND + r"\Engraved Arches and Pedestals.png").convert("RGB")
k_closed, k_litkey = kit.crop((60, 110, 444, 430)), kit.crop((444, 110, 828, 430))
K_PASS = (130, 259, 308)        # passage left, right, floor
K_C, K_R = (194.5, 143), 64.5   # the arch's half circle (apex at y 78)
K_KEY = (195, 49)               # the emerald point
K_ZF = 3.3                      # here the passage fills the view
TUI_BG = (1, 1, 1)              # the sheet's black
ground = Image.new("RGB", k_closed.size, TUI_BG)
kdoors = lambda im, theta=0.0: put_doors(im, K_PASS[0], K_PASS[1], K_C[1] - K_R, K_PASS[2], theta)
klit = make_light(k_closed.size, K_PASS[0], K_PASS[1], K_PASS[2], K_C, K_R, (K_PASS[1] - K_PASS[0]) / 122)
kcam = camera((192, 160), 384, (194.5, 228), K_ZF, k_closed.size)
N_TUI_IGNITE, N_TUI_OPEN = 6, 16
ignite_plain = []               # the lit arch fades in while a halo swells on the point and settles
for i, (r, s) in enumerate([(8, .5), (14, .8), (20, 1.0), (24, .9), (22, .75), (20, .65)]):
    base = Image.blend(k_closed, k_litkey, ease((i + 1) / N_TUI_IGNITE))
    ignite_plain.append(ImageChops.add(base, glow(k_closed.size, K_KEY, r, s * 0.6)))
opened = []
for i in range(N_TUI_OPEN):
    u = i / (N_TUI_OPEN - 1)
    f = kcam(kdoors(klit(ignite_plain[-1], smooth(u / 0.45)), DOOR_MAX * smooth(u / 0.5)), push(u, K_ZF))
    opened.append(Image.blend(f, ground, smooth((u - 0.8) / 0.2)))
tui_frames = ([Image.blend(ground, kdoors(k_closed), a) for a in (.25, .5, .75, 1)]   # fade in
              + [kdoors(f) for f in ignite_plain] + opened)
TUI_SIZES = (40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 160, 180)   # columns; rows = cols x 0.42
save_tui("gate", tui_frames, TUI_SIZES)
with open(os.path.join(TUI, "tui.json"), "w") as f:
    json.dump({"gate": list(TUI_SIZES), "bg": list(TUI_BG),
               "steps": [["fade_in", 4, 0, 180], ["ignite", N_TUI_IGNITE, 180, 180], ["open", N_TUI_OPEN, 360, 480]]}, f)
sheet = Image.new("RGB", (k_closed.width * 4, k_closed.height * 2))
for n, idx in enumerate((0, 3, 6, 9, 13, 17, 21, 24)):
    sheet.paste(tui_frames[idx], ((n % 4) * k_closed.width, (n // 4) * k_closed.height))
sheet.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tui-preview.png"))  # not shipped
print("tui art", sorted(os.listdir(TUI)))

# icon: the engraved R logo. Tile measured at (63,48)-(1189,1184), corner radius ~248.
logo = Image.open(BRAND + r"\Reidcc Logo - Engraved RC.png").convert("RGB")
TILE, R = (60, 45, 1192, 1187), 250
mask = Image.new("L", logo.size, 0)
ImageDraw.Draw(mask).rounded_rectangle(TILE, R, fill=255)
full = logo.copy()
full.putalpha(mask)
full = full.crop((54, 44, 1198, 1188))           # square around the tile, transparent corners

# Small sizes: the tile border, column and construction lines turn to mush, so crop to the
# RC letters + emerald marble on a plain rounded tile and lift contrast a little.
core = ImageEnhance.Contrast(logo.crop((215, 190, 1055, 1030))).enhance(1.25)
small_mask = Image.new("L", core.size, 0)
ImageDraw.Draw(small_mask).rounded_rectangle((0, 0, core.width - 1, core.height - 1), core.width * 0.2, fill=255)
core.putalpha(small_mask)

sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
imgs = [(core if s <= 32 else full).resize((s, s), Image.LANCZOS) for s in sizes]
imgs[-1].save(r"E:\reidcc\reidcc.ico", format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[:-1])

sheet = Image.new("RGB", (sum(sizes) + 10 * len(sizes) + 10, 276), (40, 40, 40))
x = 10
for s, im in zip(sizes, imgs):
    sheet.paste(im, (x, 10), im); x += s + 10
sheet.save(OUT + r"\icon-preview.png")
check = Image.open(r"E:\reidcc\reidcc.ico")
print("banner", Image.open(OUT + r"\banner.png").size, "| ico sizes", sorted(check.info.get("sizes", [])))
