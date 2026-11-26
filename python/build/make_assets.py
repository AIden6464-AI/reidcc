"""Build Reidcc's UI assets from the branding art: banner.png (image 1 crop) and reidcc.ico (the logo).

    python python\\build\\make_assets.py          the app's assets (banner, icon, gate frames)
    python python\\build\\make_assets.py --site   only the website's WebP cuts (SPEC-github-pages.md Part 4)
    python python\\build\\make_assets.py --emblem only medium's opening (SPEC-hand.md)
"""
import sys
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter
BRAND = r"E:\reidcc\vision\branding"
OUT = r"E:\reidcc\assets"


def site():
    """The site never links the 1-2.5 MB branding PNGs: WebP cuts at the sizes it shows, from the app's own
    gate frames (assets\\gate_*) and the art. Writes site\\public\\{frames,art,shots}."""
    import os
    root = os.path.dirname(OUT)
    pub = os.path.join(root, "site", "public")
    for d in ("frames", "art", "shots"):
        os.makedirs(os.path.join(pub, d), exist_ok=True)

    def cut(src, dst, width, q=80):
        im = Image.open(src).convert("RGB")
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        im.save(os.path.join(pub, dst), "WEBP", quality=q, method=6)

    # the gate: rise 6 + ignite 8 + open 30, 1000x880 -> 800x704 (r00, i00, o00 ...)
    for step, pre in (("rise", "r"), ("ignite", "i"), ("open", "o")):
        d = os.path.join(OUT, "gate_" + step)
        for f in sorted(os.listdir(d)):
            cut(os.path.join(d, f), os.path.join("frames", pre + f.replace(".png", ".webp")), 800, 74)
    cut(os.path.join(OUT, "gate_ghost.png"), r"art\ghost-800.webp", 800, 74)  # the 404's ghost lines
    cut(BRAND + r"\Classical Blueprint Flow with Emerald Signal-1.png", r"art\flow-1120.webp", 1120)
    cut(BRAND + r"\Engraved Compass and Marble Hand Emblem.png", r"art\emblem-144.webp", 144, 85)
    cut(BRAND + r"\Reidcc Logo - Engraved RC.png", r"art\logo-52.webp", 52, 90)
    # the favicon: 32px PNG (reidcc.ico carries every size up to 256 and weighs 150 KB)
    Image.open(BRAND + r"\Reidcc Logo - Engraved RC.png").convert("RGBA").resize((32, 32), Image.LANCZOS).save(
        os.path.join(pub, "favicon.png"), optimize=True)
    for shot in ("session-window", "launcher"):
        cut(os.path.join(root, "docs", shot + ".png"), os.path.join("shots", shot + ".webp"), 1000, 82)
    cut(os.path.join(root, "rs", "tests", "gui_shots", "settings.png"), r"shots\settings.webp", 1000, 82)
    # og image 1200x630: the flow band on canvas
    band = Image.open(BRAND + r"\Classical Blueprint Flow with Emerald Signal-1.png").convert("RGB").crop((40, 250, 1632, 640))
    band = band.resize((1200, round(band.height * 1200 / band.width)), Image.LANCZOS)
    og = Image.new("RGB", (1200, 630), (4, 4, 4))
    og.paste(band, (0, (630 - band.height) // 2))
    og.save(os.path.join(pub, "og.png"), optimize=True)


if "--site" in sys.argv:
    site()
    sys.exit()

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


# --- the emblem (SPEC-hand.md): medium's opening, made from the emblem itself, no generated layers.
# Reid, 2026-11-22: "it's coming around and it's growing out. And we should have the leaves come out. And then
# it zooms into the green, into the emerald. Like it's the image, not making it touch the tip."
#   rest    the blueprint lines, then the stone base fills in under them (no hand, compass or leaves yet)
#   grow    the hand and its drapery grow out from the top right, bringing the compass
#   leaves  the laurels grow out from their stems
#   ignite  the emerald flares and settles
#   open    the view zooms into the emerald, then goes dark (where the session window appears)
def emblem():
    import cv2
    from scipy import ndimage
    src = Image.open(BRAND + r"\Engraved Compass and Marble Hand Emblem.png").convert("RGB")
    S, PAD = src.width, 700                      # 1254 px; padded so the camera never leaves the canvas
    WS = S + 2 * PAD
    SRC = np.asarray(src)
    yy, xx = np.mgrid[0:S, 0:S]

    def region(*shapes):
        """emblem px (measured 2026-11-22): polygons and (x, y, r) circles -> a hard S x S mask"""
        m = Image.new("L", (S, S), 0)
        d = ImageDraw.Draw(m)
        for s in shapes:
            if len(s) == 3:
                d.ellipse((s[0] - s[2], s[1] - s[2], s[0] + s[2], s[1] + s[2]), fill=255)
            else:
                d.polygon(s, fill=255)
        return np.asarray(m) > 0

    ell = lambda k: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    solid = cv2.GaussianBlur(np.asarray(src.convert("L"), np.float32), (0, 0), 4) > 30   # the drawn parts, not the thin lines

    def silhouette(reg, k):
        """the drawn part inside reg, its dark folds filled: what hides the plate"""
        m = cv2.morphologyEx((solid & reg).astype(np.uint8), cv2.MORPH_CLOSE, ell(k))
        return cv2.dilate(ndimage.binary_fill_holes(m).astype(np.uint8), ell(7)) > 0

    CLOTH = region([(250, 700), (300, 640), (380, 610), (480, 600), (565, 620), (570, 725), (470, 768), (325, 790), (255, 770)])   # on the left column
    # the hand and its drapery: the whole area (only background and construction lines live there besides)
    BODY = cv2.dilate((region([(355, 330), (470, 225), (610, 190), (730, 140), (790, 60), (1080, 45), (1125, 210),
                               (1110, 420), (1070, 600), (1010, 700), (960, 750), (860, 762), (780, 720), (700, 640),
                               (560, 605), (360, 545)]) | CLOTH).astype(np.uint8), ell(9)) > 0
    # the compass stands from the start, with the house; the hand grows around it
    COMPASS = region((626, 527, 54), [(615, 408), (639, 408), (639, 482), (615, 482)],
                     [(583, 543), (634, 561), (394, 1022), (360, 1022)], [(618, 561), (670, 543), (894, 1024), (858, 1024)])
    LEAF_L = silhouette(region([(150, 600), (320, 600), (320, 925), (150, 925)]), 9)
    LEAF_R = silhouette(region([(930, 600), (1105, 600), (1105, 925), (930, 925)]), 9)

    # the plate: the emblem without the hand and the leaves, so nothing shows as a black hole before they grow.
    # Under the hand: the background with the construction lines redrawn (fitted 2026-11-22); under the cloth's
    # foot: the right column's capital, mirrored. Where a leaf covers its column: that column's other side,
    # mirrored about its own axis (x 342 / 901); elsewhere a leaf is on background: filled from around it.
    plate = SRC.copy()
    plate[BODY] = GATE_BG
    low = BODY & CLOTH & (yy >= 745)
    plate[low] = SRC[yy[low], 1243 - xx[low]]                # the columns mirror about x 621.5
    for leaf, axis, x0, x1 in ((LEAF_L, 342, 262, 424), (LEAF_R, 901, 818, 990)):
        on = leaf & (xx >= x0) & (xx <= x1) & (yy >= 760)
        plate[on] = SRC[yy[on], 2 * axis - xx[on]]
    leaves = ((LEAF_L | LEAF_R) & ~(((xx >= 262) & (xx <= 424) | (xx >= 818) & (xx <= 990)) & (yy >= 760)))
    plate = cv2.inpaint(plate, leaves.astype(np.uint8) * 255, 9, cv2.INPAINT_TELEA)
    plate[COMPASS] = SRC[COMPASS]
    # the stone that stands from the start (emblem px, 2026-11-22): columns, steps, house, plinth, the compass.
    # Everything else is background, cleaned whole so no patch edge or leftover smoke shows ("i can see the
    # patching job of it")
    mirror = lambda p: [(1243 - x, y) for x, y in p]                 # the right side mirrors the left
    COL = [(276, 765), (430, 765), (430, 1045), (276, 1045)]         # capital and shaft: their shape, from the art
    STEPS = [(272, 1043), (433, 1043), (433, 1072), (451, 1072), (451, 1114), (250, 1114), (250, 1072), (272, 1072)]
    sol = cv2.GaussianBlur(np.asarray(to_img(plate).convert("L"), np.float32), (0, 0), 4) > 30
    STONE = cv2.dilate(ndimage.binary_fill_holes(cv2.morphologyEx((sol & region(COL, mirror(COL))).astype(np.uint8),
                                                                   cv2.MORPH_CLOSE, ell(15))).astype(np.uint8), ell(5)) > 0
    STONE |= COMPASS | region(STEPS, mirror(STEPS), [(466, 850), (628, 786), (788, 850), (788, 1114), (466, 1114)],
                              [(202, 1112), (1051, 1112), (1051, 1134), (202, 1134)])   # house, steps, plinth: whole
    BG = cv2.GaussianBlur((~STONE).astype(np.float32), (0, 0), 1.5)
    plate = plate * (1 - BG[..., None]) + np.array(GATE_BG, np.float32) * BG[..., None]
    SS = 4                                      # drawn 4x and scaled down: smooth 1.5 px lines
    ln = Image.new("L", (S * SS, S * SS), 0)
    d = ImageDraw.Draw(ln)
    for cx, cy, r in ((621.1, 501.7, 401.6), (626.9, 691.9, 334.8)):
        d.ellipse([v * SS for v in (cx - r, cy - r, cx + r, cy + r)], outline=255, width=6)
    for y, x0, x1 in ((464.5, 146, 1108), (704.5, 167, 1086)):
        d.line([(x0 * SS, y * SS), (x1 * SS, y * SS)], fill=255, width=6)
    d.line([(625.5 * SS, 13 * SS), (625.5 * SS, 1211 * SS)], fill=255, width=6)
    d.line([(145 * SS, 1136.3 * SS), (1108 * SS, 1136.3 * SS)], fill=255, width=6)   # the ground line
    ln = np.asarray(ln.resize((S, S), Image.LANCZOS), np.float32) / 255
    ln *= BG                                    # on the background, not over the stone
    LINE = np.median(SRC[464:466, 150:340].reshape(-1, 3)[SRC[464:466, 150:340].reshape(-1, 3).max(1) > 90], axis=0)
    plate = plate * (1 - ln[..., None]) + LINE * ln[..., None]

    def canvas(a):
        w = Image.new("RGB", (WS, WS), GATE_BG)
        im = to_img(a)
        w.paste(over_bg(im, feather(im.size, 40, 40)), (PAD, PAD))
        return np.asarray(w, np.float32)

    W, PLATE = canvas(SRC), canvas(plate)
    pad = lambda m: np.pad(cv2.GaussianBlur(m.astype(np.float32), (0, 0), 2), PAD)   # soft edges, canvas size
    # the hand's own shape, not its whole area: the smoke around it would show a cut edge on the clean background
    HAND, LEAF_L, LEAF_R = pad(silhouette(BODY & ~COMPASS, 15)), pad(LEAF_L), pad(LEAF_R)
    P = lambda x, y: (x + PAD, y + PAD)          # emblem px -> canvas px
    layer = lambda m: W * m[..., None]           # a part on black, to composite
    gy, gx = np.mgrid[0:WS, 0:WS].astype(np.float32)
    dist = lambda o: np.hypot(gx - P(*o)[0], gy - P(*o)[1])
    O_HAND, O_L, O_R = (1100, 50), (300, 885), (955, 885)   # where each part grows from
    D_HAND, D_L, D_R = dist(O_HAND), dist(O_L), dist(O_R)

    def grown(a, s, o):
        """a (h x w or h x w x 3) scaled by s about emblem point o: the part grows out of o."""
        ox, oy = P(*o)
        im = to_img(a) if a.ndim == 3 else Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8))
        im = im.transform(im.size, Image.AFFINE, (1 / s, 0, ox - ox / s, 0, 1 / s, oy - oy / s), Image.BICUBIC)
        r = np.asarray(im, np.float32)
        return r if a.ndim == 3 else r / 255

    def part(m, d, o, t, reach, s0):
        """part with mask m revealed to t (0..1): a soft front running reach px out of o, growing from s0 to 1."""
        front = t * (reach + 90)
        rev = m * np.clip((front - d) / 90, 0, 1)
        s = s0 + (1 - s0) * t
        return grown(layer(rev), s, o), grown(rev, s, o)

    def compose(t_hand, t_leaf):
        out = PLATE
        for m, d, o, t, reach, s0 in ((HAND, D_HAND, O_HAND, t_hand, 1250, 0.82),
                                      (LEAF_L, D_L, O_L, t_leaf, 330, 0.55), (LEAF_R, D_R, O_R, t_leaf, 330, 0.55)):
            if t <= 0:
                continue
            rgb, a = part(m, d, o, t, reach, s0)
            out = out * (1 - a[..., None]) + rgb
        return to_img(out)

    if "--plate" in sys.argv:                    # look at the plate alone
        to_img(plate).save(os.path.join(os.environ.get("TEMP", "."), "emblem_plate.png"))

    FW, FH = 640, 900                            # medium's window is 480-959 wide: the edges fade into it
    EM = P(626, 527)                             # the emerald
    W0, ZF = S * FW / 520, 14.0                  # the emblem 520 px wide; at ZF the hinge ring fills the view
    cam = camera(P(627, 610), W0, EM, ZF, (FW, FH))
    VIG = feather((FW, FH), 40, 40) ** 0.8
    finish = lambda im: over_bg(im, VIG)

    for sub in ("rest", "grow", "leaves", "ignite", "open"):
        shutil.rmtree(os.path.join(OUT, "emblem_" + sub), ignore_errors=True)
        os.makedirs(os.path.join(OUT, "emblem_" + sub))
    frame = lambda step, i: OUT + r"\emblem_%s\%02d.png" % (step, i)

    full = compose(1, 1)
    em_pt = (FW / 2 + (EM[0] - P(627, 610)[0]) * FW / W0, FH / 2 + (EM[1] - P(627, 610)[1]) * FW / W0)

    def lines(im):
        a = np.asarray(cam(im, 1.0).convert("L").filter(ImageFilter.GaussianBlur(1.1)), np.float32)
        ly, lx = np.gradient(a)
        return (np.clip(np.hypot(lx, ly) / 14.0, 0, 1) ** 1.2 * VIG)[..., None] * BONE

    # ghost: the whole emblem's lines and its emerald point on the see-through key colour
    KEY = (1, 1, 1)
    ghost = np.clip(lines(full) + np.asarray(glow((FW, FH), em_pt, 16, 0.9), np.float32), 0, 255)
    ghost[ghost.max(axis=2) < 40] = KEY
    to_img(ghost).save(OUT + r"\emblem_ghost.png", optimize=True)

    # rest: the base's lines give way to its stone
    base_im = compose(0, 0)
    closed = finish(cam(base_im, 1.0))
    save_frame(closed, OUT + r"\emblem.png")
    L, c_arr, N_REST = lines(base_im), np.asarray(closed, np.float32), 8
    for i in range(N_REST):
        a = ease((i + 1) / N_REST)
        save_frame(to_img(255 - (255 - c_arr * a) * (1 - L * (1 - a) ** 0.7 / 255)), frame("rest", i))

    N_GROW, N_LEAVES = 20, 13
    for i in range(N_GROW):
        save_frame(finish(cam(compose(ease((i + 1) / N_GROW), 0), 1.0)), frame("grow", i))
    for i in range(N_LEAVES):
        save_frame(finish(cam(compose(1, ease((i + 1) / N_LEAVES)), 1.0)), frame("leaves", i))

    flare = [(8, .4), (11, .55), (14, .7), (18, .83), (22, .95), (25, 1.0), (26, .96), (26, .91), (25, .86), (24, .82)]
    for i, (r, s) in enumerate(flare):
        save_frame(finish(cam(ImageChops.add(full, glow(full.size, EM, r, s)), 1.0)), frame("ignite", i))
    lit = ImageChops.add(full, glow(full.size, EM, flare[-1][0], flare[-1][1]))

    N_OPEN = 20
    for i in range(N_OPEN):
        u = i / (N_OPEN - 1)
        f = cam(lit, push(u, ZF))
        d = smooth((u - 0.75) / 0.25)
        if d > 0:
            f = Image.blend(f, Image.new("RGB", f.size, GATE_BG), d)
        save_frame(finish(f), frame("open", i))

    meta = {"size": [FW, FH], "bg": "#%02x%02x%02x" % GATE_BG, "key": "#%02x%02x%02x" % KEY, "tag": [FW - 28, FH - 22],
            "steps": [["rest", N_REST, 0, 250], ["grow", N_GROW, 250, 500], ["leaves", N_LEAVES, 750, 330],
                      ["ignite", len(flare), 1080, 250], ["open", N_OPEN, 1330, 490]]}  # 1820 ms: 2.5 s at PACE 1.375
    with open(OUT + r"\emblem.json", "w") as f:
        json.dump(meta, f, indent=1)
    total = sum(os.path.getsize(os.path.join(dp, n)) for dp, _, ns in os.walk(OUT) for n in ns if "emblem" in dp + n)
    assert sum(s[1] for s in meta["steps"]) == 71, meta
    print("emblem", meta, "%.1f MB" % (total / 1e6))


if "--emblem" in sys.argv:
    emblem()
    sys.exit()


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
emblem()

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
# The TUI header (SPEC-one-look Part 6.3): the launcher's banner, resting in grey like the launcher's
# (one emerald per screen: the footer's ● ready). Dark pixels are left out, so it sits on the terminal.
BANNER_SIZES = (60, 70, 80, 90, 100, 110, 120, 130, 140)   # art columns; the TUI shows it from 100 terminal columns
save_tui("banner", [Image.open(os.path.join(OUT, "banner.png")).convert("L").convert("RGB")], BANNER_SIZES, clear_below=14)
with open(os.path.join(TUI, "tui.json"), "w") as f:
    json.dump({"gate": list(TUI_SIZES), "banner": list(BANNER_SIZES), "bg": list(TUI_BG),
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
