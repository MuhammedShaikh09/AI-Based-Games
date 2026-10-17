"""
AR FIGHT ARENA - Motion Challenge   (Boxer / Sumo / Karate / Ninja)
Python + OpenCV + MediaPipe Pose + Pygame

Install:  pip install opencv-python mediapipe pygame numpy
Run:      python ar_fight_arena.py

HOW IT WORKS
  * Two students stand side by side. Player 1 = LEFT half of camera, Player 2 = RIGHT half.
  * Each student's REAL FACE is cut out of the camera and pasted on the chosen fighter's body
    (boxer, sumo, karate master, ninja). The body follows the student's pose live.
  * Both fight at the same time for a 2 or 3 minute round, inside a virtual arena.
  * Throw a real punch / push / kick / throw toward your opponent -> an attack flies across.
        Boxer : glove punches          Sumo  : heavy palm slams (slow, strong)
        Karate: kick / chop energy     Ninja : fast shuriken (weak, quick)
  * DEFEND:  DODGE = jump, duck or side-step     BLOCK = keep both hands up near your face
  * Hits fill the SUPER meter. When full, your next attack is a double-damage SUPER.
  * Win by KO (health 0) or by higher score when time ends.

CONTROLS
  SELECT  : P1 = A / D to change fighter, P2 = LEFT / RIGHT
            T = round time (2 / 3 min)   B = change arena   M = music on/off
            V = camera preview on/off    ENTER = start
  FIGHT   : fallback keys ->   P1: A attack, S dodge, D block (hold)
                                P2: L attack, K dodge, J block (hold)
            P = pause, ESC = quit, R = play again after the result screen

OPTIONAL: put a file named music.mp3 / music.ogg / music.wav next to this script and it
          will be used as the fight music instead of the built-in beat.

ADD YOUR OWN FIGHTER: copy one dictionary inside CHARS, change colours / stats, done.
"""
import sys, os, time, math, random, urllib.request
import cv2, numpy as np, pygame
import mediapipe as mp

W, H = 1280, 720
ROUND_OPTIONS = [120, 180]     # seconds (2 min / 3 min) - press T on the select screen
MAX_HP = 100
ATTACK_SPEED = 3.5             # wrist speed (shoulder-widths / sec) that counts as a strike
KICK_SPEED = 3.0               # ankle speed that counts as a kick
JUMP_T, SIDE_T, CROUCH_T = 0.30, 0.60, 0.45     # dodge thresholds (in shoulder-widths)
DODGE_PTS = 3
P_COL = [(255, 95, 80), (80, 160, 255)]
BG_NAMES = ["Boxing Ring", "Karate Dojo", "Sumo Dohyo", "Neon Rooftop"]

SKIN = (224, 172, 130)
CHARS = [
    dict(name="Boxer", skin=SKIN, top=None, thigh=(210, 40, 40), shin=SKIN, arm=SKIN,
         belt=(255, 255, 255), glove=(220, 30, 30), shoe=(30, 30, 30), fist=0.27,
         kind="punch", dmg=9, cd=0.55, flight=0.50, limbs=(15, 16), girth=1.0, gear="headguard",
         desc="Fast gloves - throw real punches!"),
    dict(name="Sumo", skin=(236, 190, 150), top=None, thigh=(236, 190, 150), shin=(236, 190, 150),
         arm=(236, 190, 150), belt=(40, 90, 200), glove=(236, 190, 150), shoe=(70, 45, 30), fist=0.17,
         kind="slam", dmg=14, cd=1.10, flight=0.85, limbs=(15, 16), girth=1.6, gear="topknot",
         desc="Slow but HEAVY palm slams - push forward!"),
    dict(name="Karate", skin=SKIN, top=(246, 246, 246), thigh=(246, 246, 246), shin=(246, 246, 246),
         arm=(246, 246, 246), belt=(25, 25, 25), glove=SKIN, shoe=SKIN, fist=0.15,
         kind="kick", dmg=11, cd=0.70, flight=0.55, limbs=(15, 16, 27, 28), girth=1.0, gear="headband",
         desc="Chops and KICKS send energy waves"),
    dict(name="Ninja", skin=SKIN, top=(32, 32, 44), thigh=(32, 32, 44), shin=(32, 32, 44),
         arm=(32, 32, 44), belt=(205, 30, 30), glove=(32, 32, 44), shoe=(20, 20, 28), fist=0.15,
         kind="star", dmg=7, cd=0.40, flight=0.45, limbs=(15, 16), girth=0.95, gear="mask",
         desc="Super quick shuriken throws"),
]
HITWORD = dict(punch="POW!", slam="SLAM!", kick="HIYAH!", star="THWIP!")
TRAIL = dict(punch=(255, 90, 90), slam=(255, 210, 150), kick=(255, 245, 150), star=(200, 210, 230))

MODEL = "pose_landmarker_lite.task"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task")


def ensure_model():
    if not os.path.exists(MODEL):
        print("Downloading pose model (one time, ~6 MB)...")
        urllib.request.urlretrieve(MODEL_URL, MODEL)


# --------------------------------------------------------------------------- tracking
class Tracker:
    """One MediaPipe PoseLandmarker per half of the frame (one player each)."""
    LIMBS = (15, 16, 27, 28)

    def __init__(self):
        opts = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=MODEL),
            running_mode=mp.tasks.vision.RunningMode.IMAGE, num_poses=1,
            min_pose_detection_confidence=0.5, min_tracking_confidence=0.5)
        self.pose = mp.tasks.vision.PoseLandmarker.create_from_options(opts)
        self.ok = False; self.prev = None; self.prev_t = 0
        self.hist = []; self.base = None; self.pts = None; self.limb = {}

    def update(self, rgb, t):
        res = self.pose.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        if not res.pose_landmarks:
            self.ok = False; self.prev = None; return
        lm = res.pose_landmarks[0]
        hw, hh = rgb.shape[1], rgb.shape[0]
        raw = np.array([[p.x * hw, p.y * hh] for p in lm])
        self.pts = raw if (self.pts is None or not self.ok) else 0.6 * raw + 0.4 * self.pts
        P = self.pts
        self.sw = max(float(np.linalg.norm(P[11] - P[12])), 40.0)
        self.hist.append(((P[11] + P[12]) / 2, (P[23] + P[24]) / 2))
        self.hist = self.hist[-4:]
        self.sh = np.mean([h[0] for h in self.hist], axis=0)
        self.hip = np.mean([h[1] for h in self.hist], axis=0)
        self.nose = P[0]
        self.limb = {}
        if self.prev is not None and t > self.prev_t:
            dt = t - self.prev_t
            for i in self.LIMBS:
                v = (raw[i] - self.prev[i]) / dt / self.sw
                s = float(np.linalg.norm(v))
                self.limb[i] = (s, float(v[0]) / (s + 1e-6))
        self.prev, self.prev_t, self.ok = raw, t, True

    def dodging(self):
        if not (self.ok and self.base):
            return False
        bsh, bhip, bsw = self.base
        jump = (bhip[1] - self.hip[1]) / bsw > JUMP_T
        side = abs(self.sh[0] - bsh[0]) / bsw > SIDE_T
        duck = (self.sh[1] - bsh[1]) / bsw > CROUCH_T
        return jump or side or duck

    def blocking(self):
        """Both hands raised close to the face = guard."""
        if not self.ok:
            return False
        for i in (15, 16):
            p = self.pts[i]
            if abs(p[0] - self.nose[0]) > 0.9 * self.sw: return False
            if not (self.nose[1] - 0.5 * self.sw < p[1] < self.sh[1] + 0.5 * self.sw): return False
        return True


# --------------------------------------------------------------------------- drawing helpers
_mask_cache = {}


def face_surface(rgb, cx, cy, rc, r):
    """Cut a round face out of the camera frame (radius rc) and scale it to radius r."""
    rc = max(int(rc), 8); r = max(int(r), 8); d = 2 * r
    x0, y0 = int(cx - rc), int(cy - rc); x1, y1 = x0 + 2 * rc, y0 + 2 * rc
    crop = rgb[max(y0, 0):min(y1, H), max(x0, 0):min(x1, W)]
    if crop.size == 0:
        return None
    crop = cv2.copyMakeBorder(crop, max(-y0, 0), max(y1 - H, 0), max(-x0, 0), max(x1 - W, 0),
                              cv2.BORDER_REPLICATE)
    crop = cv2.resize(crop, (d, d))
    m = _mask_cache.get(r)
    if m is None:
        yy, xx = np.ogrid[:d, :d]
        dist = np.sqrt((xx - r + .5) ** 2 + (yy - r + .5) ** 2)
        m = np.clip((r - dist) / (r * .12) * 255, 0, 255).astype(np.uint8)
        _mask_cache[r] = m
    rgba = np.dstack([crop, m])
    return pygame.image.frombuffer(rgba.tobytes(), (d, d), "RGBA")


def limb_line(surf, col, a, b, w):
    a = (int(a[0]), int(a[1])); b = (int(b[0]), int(b[1]))
    pygame.draw.line(surf, col, a, b, w)
    pygame.draw.circle(surf, col, a, w // 2); pygame.draw.circle(surf, col, b, w // 2)


def fake_pose(cx, top):
    P = np.zeros((33, 2))
    pts = {0: (0, 35), 11: (-55, 80), 12: (55, 80), 13: (-85, 150), 14: (85, 150), 15: (-45, 112),
           16: (45, 112), 23: (-35, 230), 24: (35, 230), 25: (-45, 312), 26: (45, 312),
           27: (-52, 392), 28: (52, 392)}
    for i, (dx, dy) in pts.items():
        P[i] = (cx + dx, top + dy)
    return P


def draw_fighter(surf, P, sw, ch, rgb):
    """Draw a costume body following pose P, with the student's face as the head."""
    g = ch["girth"]; sumo = g > 1.3
    aw = int(sw * (.30 if sumo else .2)); lw = int(sw * .27 * g ** .7)
    # shadow
    fx = int((P[27][0] + P[28][0]) / 2); fy = int(max(P[27][1], P[28][1]) + sw * .12)
    shd = pygame.Surface((int(sw * 2.4 * g), int(sw * .4)), pygame.SRCALPHA)
    pygame.draw.ellipse(shd, (0, 0, 0, 90), shd.get_rect()); surf.blit(shd, shd.get_rect(center=(fx, fy)))
    # legs + shoes
    for hp, kn, an in ((23, 25, 27), (24, 26, 28)):
        limb_line(surf, ch["shin"], P[kn], P[an], lw)
        limb_line(surf, ch["thigh"], P[hp], P[kn], lw + 4)
        pygame.draw.ellipse(surf, ch["shoe"], (int(P[an][0] - sw * .22), int(P[an][1] - sw * .02),
                                               int(sw * .44), int(sw * .2)))
    # torso
    cx = (P[11][0] + P[12][0]) / 2; sy = (P[11][1] + P[12][1]) / 2; hy = (P[23][1] + P[24][1]) / 2
    if sumo:
        tw = abs(P[11][0] - P[12][0]) * g + sw * .35
        rect = (int(cx - tw / 2), int(sy - sw * .05), int(tw), int((hy - sy) * 1.15 + sw * .1))
        pygame.draw.ellipse(surf, ch["skin"], rect)
        pygame.draw.ellipse(surf, (190, 140, 105), rect, 4)
        pygame.draw.circle(surf, (150, 100, 80), (int(cx), int(sy + (hy - sy) * .6)), max(3, int(sw * .04)))
    else:
        quad = [(cx + (p[0] - cx) * g, p[1]) for p in (P[11], P[12], P[24], P[23])]
        pygame.draw.polygon(surf, ch["top"] or ch["skin"], quad)
        if ch["gear"] == "headband":         # karate gi collar
            pygame.draw.line(surf, (170, 170, 170), (int(P[11][0]), int(P[11][1])), (int(cx), int(sy + sw * .45)), 4)
            pygame.draw.line(surf, (170, 170, 170), (int(P[12][0]), int(P[12][1])), (int(cx), int(sy + sw * .45)), 4)
    # belt
    half = (tw * .42) if sumo else abs(P[23][0] - P[24][0]) / 2 * g + aw * .5
    bw = int(sw * (.30 if sumo else .16))
    pygame.draw.line(surf, ch["belt"], (int(cx - half), int(hy)), (int(cx + half), int(hy)), bw)
    if sumo:
        pygame.draw.polygon(surf, ch["belt"], [(cx - sw * .18, hy), (cx + sw * .18, hy), (cx, hy + sw * .6)])
        pygame.draw.line(surf, (255, 215, 60), (int(cx - half), int(hy + bw // 2)), (int(cx + half), int(hy + bw // 2)), 3)
    elif ch["gear"] == "headband":
        for dx in (-.12, .12):
            pygame.draw.line(surf, ch["belt"], (int(cx), int(hy)), (int(cx + dx * sw), int(hy + sw * .4)), 6)
    # arms + fists / gloves
    for s_, e_, w_ in ((11, 13, 15), (12, 14, 16)):
        limb_line(surf, ch["arm"], P[s_], P[e_], aw); limb_line(surf, ch["arm"], P[e_], P[w_], aw)
        fr = int(sw * ch["fist"]); pos = (int(P[w_][0]), int(P[w_][1]))
        pygame.draw.circle(surf, ch["glove"], pos, fr)
        if ch["gear"] == "headguard":
            pygame.draw.circle(surf, (255, 255, 255), pos, fr, 3)
            pygame.draw.circle(surf, (255, 150, 150), (pos[0] - fr // 3, pos[1] - fr // 3), fr // 4)
    # head = student's face
    hx = int(P[0][0]); hy2 = int(P[0][1] - .1 * sw); r = int(sw * .52)
    face = face_surface(rgb, hx, hy2, sw * .42, r) if rgb is not None else None
    if face is not None:
        surf.blit(face, (hx - r, hy2 - r))
    else:
        pygame.draw.circle(surf, (240, 200, 160), (hx, hy2), r)
        for dx in (-.35, .35):
            pygame.draw.circle(surf, (40, 30, 30), (int(hx + dx * r), int(hy2 - r * .15)), max(3, r // 8))
        pygame.draw.arc(surf, (120, 50, 50), (hx - r // 2, hy2 - r // 4, r, r // 2 + 6),
                        math.radians(200), math.radians(340), 4)
    gear = ch["gear"]; rr = max(4, r // 4)
    if gear == "headguard":
        pygame.draw.circle(surf, (210, 30, 30), (hx, hy2), r + 2, rr)
        for dx in (-1, 1):
            pygame.draw.circle(surf, (210, 30, 30), (hx + dx * r, hy2 + int(r * .1)), int(r * .3))
    elif gear == "topknot":
        pygame.draw.arc(surf, (25, 20, 20), (hx - r - 3, hy2 - r - 3, 2 * r + 6, 2 * r + 6),
                        math.radians(15), math.radians(165), max(6, r // 3))
        pygame.draw.ellipse(surf, (25, 20, 20), (hx - int(r * .28), hy2 - int(r * 1.5), int(r * .56), int(r * .55)))
    elif gear == "headband":
        pygame.draw.rect(surf, (210, 30, 30), (hx - r, hy2 - int(r * .66), 2 * r, int(r * .3)))
        for dy in (-.45, -.2):
            pygame.draw.line(surf, (210, 30, 30), (hx + int(r * .9), hy2 + int(r * dy)),
                             (hx + int(r * 1.6), hy2 + int(r * (dy + .35))), 6)
    elif gear == "mask":
        pygame.draw.arc(surf, (25, 25, 35), (hx - r - 3, hy2 - r - 3, 2 * r + 6, 2 * r + 6),
                        math.radians(10), math.radians(170), max(6, r // 3))
        pygame.draw.rect(surf, (205, 30, 30), (hx - r, hy2 - int(r * .62), 2 * r, int(r * .26)))
        pygame.draw.polygon(surf, (25, 25, 35), [(hx - r * .95, hy2 + r * .12), (hx + r * .95, hy2 + r * .12),
                                                 (hx + r * .7, hy2 + r * .92), (hx - r * .7, hy2 + r * .92)])
        pygame.draw.line(surf, (205, 30, 30), (hx + int(r * .9), hy2 - int(r * .5)),
                         (hx + int(r * 1.7), hy2 - int(r * .1)), 6)
    return hx, hy2, r


_ps = {}


def proj_surface(kind, size):
    key = (kind, size)
    if key in _ps:
        return _ps[key]
    s = pygame.Surface((size, size), pygame.SRCALPHA); c = size // 2
    if kind == "punch":
        pygame.draw.rect(s, (245, 245, 245), (int(c * .1), c - c // 4, c // 2, c // 2), border_radius=4)
        pygame.draw.circle(s, (220, 30, 30), (c + c // 6, c), int(c * .7))
        pygame.draw.circle(s, (255, 130, 130), (c, c - c // 4), c // 5)
    elif kind == "slam":
        pygame.draw.circle(s, (255, 230, 170), (c, c), c - 2, 6)
        pygame.draw.circle(s, (255, 200, 120), (c, c), int(c * .66), 5)
        pygame.draw.circle(s, (236, 190, 150), (c, c), int(c * .4))
        for k in range(4):
            pygame.draw.circle(s, (236, 190, 150), (c + int(c * .42), c - int(c * .27) + k * int(c * .18)), int(c * .1))
    elif kind == "kick":
        pygame.draw.circle(s, (255, 240, 120), (c, c), c - 2)
        pygame.draw.circle(s, (0, 0, 0, 0), (c - c // 3, c), c - 2)
        pygame.draw.circle(s, (255, 255, 255), (c, c), c - 2, 3)
    else:  # star
        pts = []
        for i in range(8):
            a = i * math.pi / 4; rad = c - 2 if i % 2 == 0 else c * .3
            pts.append((c + math.cos(a) * rad, c + math.sin(a) * rad))
        pygame.draw.polygon(s, (210, 215, 228), pts); pygame.draw.polygon(s, (90, 95, 110), pts, 3)
        pygame.draw.circle(s, (40, 40, 55), (c, c), c // 6)
    _ps[key] = s
    return s


# --------------------------------------------------------------------------- arenas
def vgrad(s, rect, c1, c2):
    x, y, w, h = rect
    for i in range(h):
        k = i / max(h - 1, 1)
        pygame.draw.line(s, [int(c1[j] + (c2[j] - c1[j]) * k) for j in range(3)], (x, y + i), (x + w, y + i))


def make_bg(kind):
    s = pygame.Surface((W, H)); rnd = random.Random(kind * 11 + 5); hz = int(H * .58)

    def persp(col, n, step, bstep):
        for k in range(-n, n + 1):
            pygame.draw.line(s, col, (W // 2 + k * step, hz), (W // 2 + k * bstep, H), 2)
    if kind == 0:      # boxing ring
        vgrad(s, (0, 0, W, hz), (10, 10, 28), (48, 30, 70))
        for _ in range(300):
            c = rnd.randrange(30, 80)
            pygame.draw.circle(s, (c, c // 2, c + 15), (rnd.randrange(W), rnd.randrange(50, hz - 30)), rnd.randrange(9, 17))
        glow = pygame.Surface((W, H), pygame.SRCALPHA)
        for x in (220, 640, 1060):
            pygame.draw.polygon(glow, (255, 255, 210, 30), [(x - 14, 0), (x + 14, 0), (x + 190, hz), (x - 190, hz)])
        s.blit(glow, (0, 0))
        vgrad(s, (0, hz, W, H - hz), (36, 70, 170), (14, 30, 100)); persp((70, 110, 210), 14, 50, 240)
        for i, c in enumerate(((220, 40, 40), (245, 245, 245), (220, 40, 40))):
            pygame.draw.line(s, c, (0, hz - 140 + i * 45), (W, hz - 140 + i * 45), 9)
        for x in (0, W - 46):
            pygame.draw.rect(s, (70, 70, 80), (x, hz - 170, 46, 230))
    elif kind == 1:    # karate dojo
        vgrad(s, (0, 0, W, hz), (160, 110, 70), (115, 75, 45))
        for i in range(5):
            x = 60 + i * 245
            pygame.draw.rect(s, (244, 236, 212), (x, 80, 205, 300)); pygame.draw.rect(s, (90, 55, 30), (x, 80, 205, 300), 8)
            for k in (1, 2):
                pygame.draw.line(s, (90, 55, 30), (x + k * 68, 80), (x + k * 68, 380), 4)
            pygame.draw.line(s, (90, 55, 30), (x, 230), (x + 205, 230), 4)
        pygame.draw.rect(s, (245, 245, 240), (W // 2 - 65, 40, 130, 230)); pygame.draw.rect(s, (60, 40, 30), (W // 2 - 65, 40, 130, 230), 6)
        pygame.draw.circle(s, (200, 30, 30), (W // 2, 155), 42)
        pygame.draw.rect(s, (90, 55, 30), (0, hz - 20, W, 20))
        vgrad(s, (0, hz, W, H - hz), (176, 196, 110), (118, 148, 78)); persp((90, 115, 60), 16, 60, 260)
        for k in range(1, 7):
            y = hz + int((H - hz) * (k / 7) ** 1.6); pygame.draw.line(s, (90, 115, 60), (0, y), (W, y), 2)
    elif kind == 2:    # sumo stadium
        vgrad(s, (0, 0, W, hz), (28, 16, 18), (60, 30, 30))
        for _ in range(220):
            c = rnd.randrange(35, 80)
            pygame.draw.circle(s, (c, c // 2, c // 2), (rnd.randrange(W), rnd.randrange(130, hz - 20)), rnd.randrange(8, 15))
        pygame.draw.polygon(s, (165, 30, 30), [(0, 0), (W, 0), (W - 110, 120), (110, 120)])
        for x in range(130, W - 100, 70):
            pygame.draw.circle(s, (250, 240, 220), (x, 124), 9)
        for x in range(120, W, 220):
            pygame.draw.line(s, (120, 100, 60), (x, 120), (x, 190), 3)
            pygame.draw.circle(s, (215, 40, 40), (x, 215), 30); pygame.draw.circle(s, (255, 200, 80), (x, 215), 10)
        vgrad(s, (0, hz, W, H - hz), (125, 90, 58), (80, 55, 35))
        pygame.draw.ellipse(s, (176, 130, 84), (W // 2 - 520, hz + 40, 1040, 230))
        pygame.draw.ellipse(s, (236, 206, 130), (W // 2 - 520, hz + 40, 1040, 230), 10)
    else:              # neon rooftop
        vgrad(s, (0, 0, W, hz), (18, 8, 48), (130, 50, 115))
        for _ in range(90):
            pygame.draw.circle(s, (255, 255, 255), (rnd.randrange(W), rnd.randrange(hz // 2)), rnd.choice((1, 1, 2)))
        pygame.draw.circle(s, (250, 245, 220), (1020, 120), 58)
        x = 0
        while x < W:
            w = rnd.randrange(60, 130); h = rnd.randrange(120, 300)
            pygame.draw.rect(s, (16, 10, 36), (x, hz - h, w, h))
            for wy in range(hz - h + 14, hz - 14, 26):
                for wx in range(x + 10, x + w - 14, 22):
                    if rnd.random() < .45:
                        pygame.draw.rect(s, (255, 220, 110), (wx, wy, 10, 14))
            x += w + rnd.randrange(0, 14)
        vgrad(s, (0, hz, W, H - hz), (52, 52, 72), (20, 20, 36)); persp((120, 70, 170), 12, 50, 240)
        pygame.draw.line(s, (255, 80, 200), (0, hz), (W, hz), 4)
    return s


# --------------------------------------------------------------------------- sound
SR = 44100


def _t(d):
    return np.arange(int(SR * d)) / SR


def _snd(sig, vol=.6):
    w = (np.clip(sig, -1, 1) * vol * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack([w, w]))


def make_sfx():
    rng = np.random.RandomState(1)
    d = {}
    t = _t(.18); d["punch"] = _snd(np.sin(2 * np.pi * (120 * np.exp(-t * 20) + 50) * t) * np.exp(-t * 18)
                                   + .6 * rng.uniform(-1, 1, t.size) * np.exp(-t * 40), .9)
    t = _t(.25); d["whoosh"] = _snd(rng.uniform(-1, 1, t.size) * np.sin(np.pi * t / .25) ** 2 * .5, .6)
    t = _t(.2); d["block"] = _snd((np.sin(2 * np.pi * 700 * t) + np.sin(2 * np.pi * 1130 * t)) * np.exp(-t * 25) * .5, .6)
    t = _t(.25); d["dodge"] = _snd(np.sin(2 * np.pi * (500 + 1500 * t) * t) * np.exp(-t * 8), .5)
    t = _t(.9); d["bell"] = _snd(sum(a * np.sin(2 * np.pi * f * t) for f, a in ((660, 1), (1320, .5), (1980, .3))) * np.exp(-t * 4) * .4, .7)
    t = _t(.8); d["ko"] = _snd(np.sin(2 * np.pi * (420 - 400 * t) * t) * np.exp(-t * 3), .8)
    t = _t(.5); d["power"] = _snd(np.sin(2 * np.pi * (300 + 1200 * t) * t) * (1 - t / .5) * .8, .7)
    t = _t(.15); d["beep"] = _snd(np.sin(2 * np.pi * 520 * t) * np.exp(-t * 10), .6)
    t = _t(.3); d["go"] = _snd(np.sin(2 * np.pi * 920 * t) * np.exp(-t * 6), .6)
    return d


def synth_music(bpm, bars, full):
    st = 60 / bpm / 4; n = int(bars * 16 * st * SR); out = np.zeros(n + SR)
    rng = np.random.RandomState(3)

    def add(sig, step):
        i = int(step * st * SR); seg = sig[:max(0, len(out) - i)]; out[i:i + len(seg)] += seg
    t = _t(.2); kick = np.sin(2 * np.pi * np.cumsum(55 + 150 * np.exp(-t * 30)) / SR) * np.exp(-t * 14)
    t = _t(.15); snare = (rng.uniform(-1, 1, t.size) * .7 + np.sin(2 * np.pi * 190 * t) * .4) * np.exp(-t * 24)
    t = _t(.05); hat = rng.uniform(-1, 1, t.size) * np.exp(-t * 90) * .25
    roots = [110, 110, 87.3, 98]; scale = [220, 261.6, 293.7, 329.6, 392, 440, 523.3]
    tb = _t(st * 2)
    for s in range(bars * 16):
        b, k = s // 16, s % 16
        if full:
            if k % 4 == 0: add(kick, s)
            if k % 8 == 4: add(snare, s)
            if k % 2 == 0: add(hat, s)
            if k in (0, 3, 6, 8, 11, 14):
                f = roots[b % 4] * (2 if k in (6, 14) else 1)
                add(np.sign(np.sin(2 * np.pi * f * tb)) * .22 * np.exp(-tb * 5), s)
            if rng.rand() < .55:
                f = scale[rng.randint(len(scale))]
                add((np.sin(2 * np.pi * f * tb) + .3 * np.sin(4 * np.pi * f * tb)) * .18 * np.exp(-tb * 4), s)
        else:
            if k == 0: add(kick * .6, s)
            if k % 4 == 0:
                add(np.sin(2 * np.pi * roots[b % 4] * tb) * .3 * np.exp(-tb * 3), s)
            if k % 2 == 0:
                f = scale[(s // 2 + b) % len(scale)]
                add(np.sin(2 * np.pi * f * tb) * .14 * np.exp(-tb * 5), s)
    tail = out[n:]; out = out[:n]; out[:len(tail)] += tail
    return _snd(out / (np.abs(out).max() + 1e-6), .55)


# --------------------------------------------------------------------------- main
def main():
    ensure_model()
    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("AR Fight Arena")
    world = pygame.Surface((W, H))
    clock = pygame.time.Clock()
    F = [pygame.font.SysFont("arial", s, bold=True) for s in (22, 34, 56, 100)]
    print("Building arenas, sounds and music (a few seconds)...")
    bgs = [make_bg(k) for k in range(4)]
    sfx = make_sfx()
    tracks = {"menu": synth_music(92, 4, False), "fight": synth_music(128, 8, True)}
    custom = next((f for f in ("music.mp3", "music.ogg", "music.wav") if os.path.exists(f)), None)
    cfg = dict(mute=False, cur=None)

    def setvol():
        for s_ in tracks.values(): s_.set_volume(0 if cfg["mute"] else .55)
        pygame.mixer.music.set_volume(0 if cfg["mute"] else .6)

    def music(name):
        if cfg["cur"] == name: return
        pygame.mixer.music.stop()
        for s_ in tracks.values(): s_.stop()
        if name == "fight" and custom:
            pygame.mixer.music.load(custom); pygame.mixer.music.play(-1)
        else:
            tracks[name].play(-1)
        cfg["cur"] = name; setvol()

    def play(k):
        if not cfg["mute"]: sfx[k].play()

    def txt(f, s, pos, col=(255, 255, 255), surf=None):
        surf = surf if surf is not None else screen
        img = F[f].render(s, True, col); shd = F[f].render(s, True, (0, 0, 0))
        r = img.get_rect(center=(int(pos[0]), int(pos[1])))
        surf.blit(shd, r.move(2, 2)); surf.blit(img, r)

    def bar(x, y, w, h, frac, col, right=False):
        pygame.draw.rect(screen, (20, 20, 30), (x, y, w, h))
        fw = int(w * max(min(frac, 1), 0))
        pygame.draw.rect(screen, col, (x + w - fw if right else x, y, fw, h))
        pygame.draw.rect(screen, (255, 255, 255), (x, y, w, h), 2)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Camera not found!"); sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    trk = [Tracker(), Tracker()]
    zone = lambda i: (i * W // 2 + W // 4, H // 2)
    dim = pygame.Surface((W, H), pygame.SRCALPHA); dim.fill((0, 0, 0, 150))

    state, hero, bg, round_idx, show_cam, paused = "SELECT", [0, 3], 0, 0, True, False
    hp, scores, meter, combo = [MAX_HP] * 2, [0, 0], [0.0, 0.0], [0, 0]
    ready, dod_prev, dod_start, kdo_until = [0.5, 0.5], [False] * 2, [-9.0, -9.0], [0.0, 0.0]
    projs, parts, pops = [], [], []
    samples, cal_start, cal_pr, cd_last = [[], []], None, 0, 4
    t_state = time.time(); last = t_state; gt = 0.0; t_left = ROUND_OPTIONS[0]
    shake = 0.0; result = ("", ""); end_reason = None
    pop = lambda s_, x, y, c=(255, 230, 80): pops.append([s_, x, y, 1.0, c])

    def burst(x, y, n, cols):
        for _ in range(n):
            parts.append([x, y, random.uniform(-8, 8), random.uniform(-8, 8), 1.0, random.choice(cols)])

    while True:
        now = time.time(); dt = min(now - last, 0.1); last = now
        kat, kdo = [False, False], [False, False]
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                cap.release(); pygame.quit(); sys.exit()
            if e.type != pygame.KEYDOWN:
                continue
            k = e.key
            if k == pygame.K_m: cfg["mute"] = not cfg["mute"]; setvol()
            elif k == pygame.K_v: show_cam = not show_cam
            if state == "SELECT":
                n = len(CHARS)
                if k == pygame.K_a: hero[0] = (hero[0] - 1) % n
                if k == pygame.K_d: hero[0] = (hero[0] + 1) % n
                if k == pygame.K_LEFT: hero[1] = (hero[1] - 1) % n
                if k == pygame.K_RIGHT: hero[1] = (hero[1] + 1) % n
                if k == pygame.K_t: round_idx = (round_idx + 1) % len(ROUND_OPTIONS)
                if k == pygame.K_b: bg = (bg + 1) % len(bgs)
                if k == pygame.K_RETURN:
                    state, cal_start = "CALIBRATE", None
                    hp, scores, meter, combo = [MAX_HP] * 2, [0, 0], [0.0, 0.0], [0, 0]
                    projs.clear(); parts.clear(); pops.clear()
            elif state == "FIGHT":
                if k == pygame.K_p: paused = not paused
                if k == pygame.K_a: kat[0] = True
                if k == pygame.K_l: kat[1] = True
                if k == pygame.K_s: kdo[0] = True
                if k == pygame.K_k: kdo[1] = True
            elif state == "FINAL" and k == pygame.K_r:
                state = "SELECT"

        # ---- camera + tracking ----------------------------------------------------
        ok, frame = cap.read()
        if not ok:
            clock.tick(30); continue
        frame = cv2.resize(cv2.flip(frame, 1), (W, H))
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        for i in (0, 1):
            trk[i].update(np.ascontiguousarray(rgb[:, i * W // 2:(i + 1) * W // 2]), now)

        # ---- game logic -----------------------------------------------------------
        end_reason = None
        if state == "SELECT":
            music("menu")
        elif state == "CALIBRATE":
            if all(t.ok for t in trk):
                if cal_start is None:
                    cal_start, samples = now, [[], []]
                for i in (0, 1):
                    samples[i].append((trk[i].sh.copy(), trk[i].hip.copy(), trk[i].sw))
                cal_pr = min((now - cal_start) / 3, 1)
                if cal_pr >= 1:
                    for i in (0, 1):
                        sm = samples[i]
                        trk[i].base = (np.mean([x[0] for x in sm], axis=0), np.mean([x[1] for x in sm], axis=0),
                                       float(np.mean([x[2] for x in sm])))
                    state, t_state, cd_last = "COUNTDOWN", now, 4
            else:
                cal_start, cal_pr = None, 0
        elif state == "COUNTDOWN":
            el = now - t_state; n = 3 - int(el)
            if el < 3 and n != cd_last: cd_last = n; play("beep")
            if el >= 3 and cd_last != 0: cd_last = 0; play("go")
            if el >= 3.6:
                state, gt, t_left, paused = "FIGHT", 0.0, ROUND_OPTIONS[round_idx], False
                projs.clear(); ready, kdo_until, dod_start, dod_prev = [.5, .5], [0, 0], [-9.0, -9.0], [False] * 2
                music("fight"); play("bell")
        elif state == "FIGHT" and not paused:
            gt += dt; t_left -= dt
            keys = pygame.key.get_pressed()
            kblock = [keys[pygame.K_d], keys[pygame.K_j]]
            for i in (0, 1):
                t = trk[i]; ch = CHARS[hero[i]]
                if kdo[i]: kdo_until[i] = gt + 0.6; dod_start[i] = gt
                nd = t.dodging() or gt < kdo_until[i]
                if nd and not dod_prev[i]: dod_start[i] = gt
                dod_prev[i] = nd
                if gt < ready[i]:
                    continue
                fire = None
                if t.ok:
                    for L in ch["limbs"]:
                        sp, vx = t.limb.get(L, (0, 0))
                        if sp > (KICK_SPEED if L > 20 else ATTACK_SPEED) and vx * (1 if i == 0 else -1) > 0.45:
                            fire = L; break
                if fire is None and kat[i]:
                    fire = 16 if i == 0 else 15
                if fire is not None:
                    o = trk[1 - i]; sup = meter[i] >= 1
                    src = (t.pts[fire] + [i * W // 2, 0]) if t.ok else zone(i)
                    dst = ((o.sh + o.hip) / 2 + [(1 - i) * W // 2, 0]) if o.ok else zone(1 - i)
                    projs.append(dict(own=i, s=np.array(src, float), e=np.array(dst, float), t0=gt,
                                      fl=ch["flight"] * (1.2 if sup else 1), kind=ch["kind"],
                                      dmg=ch["dmg"] * (2 if sup else 1), sup=sup, dodged=False))
                    if sup:
                        meter[i] = 0; pop("SUPER ATTACK!", zone(i)[0], 200, (255, 120, 255))
                    ready[i] = gt + ch["cd"]; play("power" if sup else "whoosh")
            for p in projs[:]:
                u = min((gt - p["t0"]) / p["fl"], 1); a = p["own"]; d = 1 - a
                if u > 0.2 and dod_prev[d] and dod_start[d] >= p["t0"] - 0.15:
                    p["dodged"] = True
                if u < 1:
                    continue
                projs.remove(p); ex, ey = p["e"]
                if p["dodged"]:
                    scores[d] += DODGE_PTS; combo[a] = 0
                    pop("DODGED! +%d" % DODGE_PTS, ex, ey - 60, (120, 255, 160)); play("dodge")
                elif trk[d].blocking() or kblock[d]:
                    hp[d] = max(0, hp[d] - p["dmg"] * 0.2); scores[a] += 2; combo[a] = 0
                    pop("BLOCKED", ex, ey - 60, (180, 200, 255)); play("block")
                    burst(ex, ey, 12, [(200, 220, 255), (255, 255, 255)])
                else:
                    combo[a] += 1; combo[d] = 0
                    gain = 10 + min(combo[a] - 1, 5) * 2
                    if p["sup"]: gain *= 2
                    scores[a] += gain; hp[d] = max(0, hp[d] - p["dmg"])
                    meter[a] = min(1.0, meter[a] + .34)
                    pop("%s +%d" % (HITWORD[p["kind"]], gain), ex, ey - 60, P_COL[a])
                    if combo[a] >= 2: pop("%dx COMBO!" % combo[a], ex, ey - 110, (255, 200, 60))
                    burst(ex, ey, 45, [(255, 200, 40), (255, 90, 30), (255, 255, 255)])
                    shake = now + 0.25; play("punch")
            if hp[0] <= 0 or hp[1] <= 0: end_reason = "KO"
            elif t_left <= 0: end_reason = "TIME"

        if end_reason:
            if end_reason == "KO" and (hp[0] <= 0) != (hp[1] <= 0):
                w = 1 if hp[0] <= 0 else 0
            else:
                w = 0 if scores[0] > scores[1] else 1 if scores[1] > scores[0] else \
                    0 if hp[0] > hp[1] else 1 if hp[1] > hp[0] else -1
            head = "IT'S A DRAW!" if w < 0 else "P%d  %s  WINS!" % (w + 1, CHARS[hero[w]]["name"].upper())
            result = (head, "K.O.!" if end_reason == "KO" else "TIME UP!")
            state = "FINAL"; projs.clear(); music("menu"); play("ko" if end_reason == "KO" else "bell")

        # ---- draw world (arena, fighters, attacks) --------------------------------
        world.blit(bgs[bg], (0, 0))
        for i in (0, 1):
            ch = CHARS[hero[i]]; t = trk[i]
            if t.ok:
                hx, hy, r = draw_fighter(world, t.pts + [i * W // 2, 0], t.sw, ch, rgb)
            elif state == "SELECT":
                hx, hy, r = draw_fighter(world, fake_pose(zone(i)[0], 210), 110, ch, None)
            else:
                txt(1, "Step into your zone", zone(i), (255, 255, 255), world); continue
            ty = hy - int(r * 1.8) - 14
            pygame.draw.polygon(world, P_COL[i], [(hx - 12, ty + 12), (hx + 12, ty + 12), (hx, ty + 28)])
            txt(0, "P%d" % (i + 1), (hx, ty), P_COL[i], world)
        for p in projs:
            u = min((gt - p["t0"]) / p["fl"], 1)
            x = p["s"][0] + (p["e"][0] - p["s"][0]) * u
            y = p["s"][1] + (p["e"][1] - p["s"][1]) * u - 60 * math.sin(math.pi * u)
            sz = int((150 if p["kind"] == "slam" else 110) * (1.5 if p["sup"] else 1))
            for k in range(1, 5):
                uu = max(u - k * .04, 0)
                tx = p["s"][0] + (p["e"][0] - p["s"][0]) * uu
                ty = p["s"][1] + (p["e"][1] - p["s"][1]) * uu - 60 * math.sin(math.pi * uu)
                pygame.draw.circle(world, TRAIL[p["kind"]], (int(tx), int(ty)), max(3, sz // 5 - k * 4))
            sf = proj_surface(p["kind"], sz)
            if p["kind"] == "star": sf = pygame.transform.rotate(sf, u * 1080)
            elif p["own"] == 1: sf = pygame.transform.flip(sf, True, False)
            if p["sup"]: pygame.draw.circle(world, (255, 230, 80), (int(x), int(y)), sz // 2 + 8, 5)
            world.blit(sf, sf.get_rect(center=(int(x), int(y))))
        if not paused:
            for p in parts[:]:
                p[0] += p[2]; p[1] += p[3]; p[4] -= 0.03
                if p[4] <= 0: parts.remove(p)
            for p in pops[:]:
                p[2] -= 1.2; p[3] -= 0.022
                if p[3] <= 0: pops.remove(p)
        for p in parts:
            pygame.draw.circle(world, p[5], (int(p[0]), int(p[1])), max(2, int(8 * p[4])))
        for p in pops:
            txt(1, p[0], (p[1], p[2]), p[4], world)

        ox, oy = (random.randint(-9, 9), random.randint(-9, 9)) if now < shake else (0, 0)
        screen.blit(world, (ox, oy))

        # ---- overlays / HUD -------------------------------------------------------
        if state == "SELECT":
            txt(3, "AR FIGHT ARENA", (W // 2, 55))
            for i in (0, 1):
                ch = CHARS[hero[i]]; cx = zone(i)[0]
                txt(2, ch["name"].upper(), (cx, 140), P_COL[i])
                txt(0, ch["desc"], (cx, 640))
                txt(0, "Player %d:  %s" % (i + 1, "A / D" if i == 0 else "<  /  >"), (cx, 668), P_COL[i])
            txt(0, "ENTER start   |   T: round %d:00   |   B: arena - %s   |   M: music %s   |   V: camera"
                % (ROUND_OPTIONS[round_idx] // 60, BG_NAMES[bg], "OFF" if cfg["mute"] else "ON"), (W // 2, 700))
        elif state == "CALIBRATE":
            txt(1, "Stand still, facing the camera, in your zone", (W // 2, 90))
            pygame.draw.rect(screen, (80, 220, 120), (W // 4, H - 80, int(W / 2 * cal_pr), 24))
            if cal_start is None:
                txt(0, "Both players must be fully visible", (W // 2, H - 110), (255, 120, 120))
        elif state == "COUNTDOWN":
            el = now - t_state
            txt(3, str(3 - int(el)) if el < 3 else "FIGHT!", (W // 2, H // 2), (255, 230, 80))
        if state in ("COUNTDOWN", "FIGHT", "FINAL"):
            for i in (0, 1):
                ch = CHARS[hero[i]]; h = hp[i] / MAX_HP; x = 40 if i == 0 else W - 540
                bar(x, 22, 500, 26, h, (80, 220, 100) if h > .5 else (240, 210, 60) if h > .25 else (240, 70, 60), i == 1)
                bar(x, 52, 500, 9, meter[i], (255, 120, 255), i == 1)
                txt(0, "P%d  %s" % (i + 1, ch["name"]), (x + (60 if i == 0 else 440), 86), P_COL[i])
                txt(1, "SCORE %d" % scores[i], (x + (250 if i == 0 else 250), 86), (255, 255, 255))
                if meter[i] >= 1 and int(now * 4) % 2 == 0:
                    txt(0, "SUPER READY!", (x + 250, 112), (255, 120, 255))
            tl = max(int(math.ceil(t_left)), 0) if state != "COUNTDOWN" else ROUND_OPTIONS[round_idx]
            txt(2, "%d:%02d" % divmod(tl, 60), (W // 2, 40),
                (255, 90, 80) if (state == "FIGHT" and t_left < 10) else (255, 255, 255))
        if state == "FIGHT" and gt < 5:
            txt(0, "STRIKE toward your opponent!   DODGE: jump / duck / side-step   BLOCK: hands up at your face",
                (W // 2, H - 40), (255, 240, 150))
        if paused and state == "FIGHT":
            screen.blit(dim, (0, 0)); txt(3, "PAUSED", (W // 2, H // 2)); txt(1, "Press P to resume", (W // 2, H // 2 + 80))
        if state == "FINAL":
            screen.blit(dim, (0, 0))
            txt(3, result[1], (W // 2, H // 2 - 150), (255, 90, 80))
            txt(2, result[0], (W // 2, H // 2 - 50), (255, 230, 80))
            txt(2, "%d  -  %d" % (scores[0], scores[1]), (W // 2, H // 2 + 40))
            txt(1, "Health  %d%%  -  %d%%" % (hp[0], hp[1]), (W // 2, H // 2 + 110))
            txt(1, "Press R to play again", (W // 2, H // 2 + 175), (200, 220, 255))
        if show_cam:
            pip = cv2.resize(rgb, (160, 90))
            screen.blit(pygame.image.frombuffer(pip.tobytes(), (160, 90), "RGB"), (W // 2 - 80, 100))
            pygame.draw.rect(screen, (255, 255, 255), (W // 2 - 80, 100, 160, 90), 2)

        pygame.display.flip()
        clock.tick(30)


if __name__ == "__main__":
    main()














##############################################################################################################################################################################
















