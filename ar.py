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
  * The round ALWAYS runs the full 2 or 3 minutes (press T on the menu to choose).
    Health reaching 0 is only a KNOCKDOWN (+25 points for the attacker, health refills to 60%).
    When the clock hits 0:00 the higher score wins (tie -> more health, else draw).

CONTROLS
  SELECT  : P1 = A / D to change fighter, P2 = LEFT / RIGHT
            T = round time (2 / 3 min)   B = change arena   M = music on/off
            V = camera preview on/off    ENTER = start
  ANY     : [ / ] = punch sensitivity (lower if punches trigger by themselves)
            G = show what the tracker sees (green = good, red = poorly seen)
  HOW TO ATTACK: throw a real, fast punch (or kick for Karate) SIDEWAYS toward your opponent.
  Standing still or small movements do nothing.
  ANY     : F11 (or F) = fullscreen on/off.  The window can also be resized/maximised freely;
            the game keeps its 16:9 shape.  Start fullscreen:  python ar_fight_arena.py --fullscreen
  FIGHT   : fallback keys ->   P1: A attack, S dodge, D block (hold)
                                P2: L attack, K dodge, J block (hold)
            P = pause, ESC = quit, R = play again after the result screen

SPRITE IMAGES (optional, used instead of the drawn body when present)
  Put PNGs (transparent background, face area left as a plain WHITE oval) in a folder
  called  assets/  next to this script, 3 per fighter:
        assets/boxer_ready.png   assets/boxer_right.png   assets/boxer_left.png
        (same for sumo_, karate_, ninja_)
  ready = default stance, right = punch with your RIGHT hand, left = punch with your LEFT hand
  (if they come out swapped, set SWAP_PUNCH = True near the top of this file).
  Only head-to-hips of each player has to be visible to the camera. If images are missing, the
  built-in drawn fighter is used automatically.

OPTIONAL: put a file named music.mp3 / music.ogg / music.wav next to this script and it
          will be used as the fight music instead of the built-in beat.

ADD YOUR OWN FIGHTER: copy one dictionary inside CHARS, change colours / stats, done.
"""
import sys, os, time, math, random, urllib.request
import threading
from collections import deque
import cv2, numpy as np, pygame
import mediapipe as mp

W, H = 1280, 720
ROUND_OPTIONS = [120, 180]     # seconds (2 min / 3 min) - press T on the select screen
MAX_HP = 100
ATTACK_SPEED = 3.5             # wrist speed (shoulder-widths / sec) that counts as a strike
KICK_SPEED = 3.0               # ankle speed that counts as a kick
JUMP_T, SIDE_T, CROUCH_T = 0.30, 0.60, 0.45     # dodge thresholds (in shoulder-widths)
DODGE_PTS = 3
ASSET_DIR = "assets"
SPRITE_BODY_K = 3.2            # sprite height = this x player shoulder width ...
SPRITE_MAX_H = 0.62            # ... but never taller than this fraction of the screen height
PUNCH_HOLD = 0.35              # seconds a punch pose stays on screen
SWAP_PUNCH = False             # True = swap the left/right punch images
POSE_MODEL = "lite"            # "lite" = fast (default). "full" = more accurate but slower
STRIKE_DISP = 0.8              # a real strike moves the hand/foot this far (x shoulder-width) toward the opponent ...
STRIKE_SPEED = 2.6             # ... at least this fast (shoulder-widths per second) ...
REACH_HAND = 1.0               # ... and ends with the hand this far from your body centre
REACH_FOOT = 0.6               # kicks: foot this far from hips AND lifted off the ground
FOOT_LIFT = 0.35
DETECT_W = 640                 # width of the picture given to the pose detector (smaller = faster)
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

MODEL = "pose_landmarker_%s.task" % POSE_MODEL
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_%s/float16/latest/pose_landmarker_%s.task" % (POSE_MODEL, POSE_MODEL))


def ensure_model():
    if not os.path.exists(MODEL):
        print("Downloading pose model (one time)...")
        urllib.request.urlretrieve(MODEL_URL, MODEL)


# --------------------------------------------------------------------------- tracking
class Tracker:
    """One MediaPipe PoseLandmarker per half of the frame (one player each).
    Stability features: VIDEO tracking mode, adaptive smoothing of every landmark,
    a dead-band on body size (sprite never 'breathes'), and a short grace period so a
    missed frame does not make the character vanish."""
    LIMBS = (15, 16, 27, 28)
    GRACE = 0.4          # seconds to keep the last pose when detection drops out
    SIZE_BAND = 0.10     # body size only changes when it differs by more than 10 %

    def __init__(self):
        opts = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=MODEL),
            running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=1,
            min_pose_detection_confidence=0.5, min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5)
        self.pose = mp.tasks.vision.PoseLandmarker.create_from_options(opts)
        self.ok = False; self.prev = None; self.prev_t = 0
        self.hist = []; self.base = None; self.pts = None; self.limb = {}
        self.size = None; self.sw = 100.0; self.last_good = 0.0; self.ts = 0
        self.wh = {i: deque(maxlen=14) for i in self.LIMBS}
        self.vis = np.ones(33); self.ok_since = 0.0

    def update(self, rgb, t):
        self.ts = max(self.ts + 1, int(t * 1000))
        res = self.pose.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), self.ts)
        if not res.pose_landmarks:
            if self.ok and t - self.last_good < self.GRACE:
                self.limb = {}; return                 # keep last pose for a moment
            self.ok = False; self.prev = None; return
        lm = res.pose_landmarks[0]
        raw = np.array([[p.x * (W // 2), p.y * H] for p in lm])   # normalised -> full-res pixels
        self.vis = np.array([p.visibility if getattr(p, "visibility", None) is not None else 1.0 for p in lm])
        if not self.ok:                                            # (re)acquired: forget old motion
            self.ok_since = t
            for q in self.wh.values(): q.clear()
        if self.pts is None or not self.ok:
            self.pts = raw
        else:                                          # slow when still, fast when moving
            d = np.linalg.norm(raw - self.pts, axis=1) / max(self.size or 100.0, 40.0)
            a = (0.2 + 0.7 * np.clip(d / 0.3, 0, 1))[:, None]
            self.pts = a * raw + (1 - a) * self.pts
        P = self.pts
        sw = max(float(np.linalg.norm(P[11] - P[12])), 40.0)
        if self.size is None or not self.ok:
            self.size = sw if self.size is None else self.size * 0.5 + sw * 0.5
        elif abs(sw - self.size) / self.size > self.SIZE_BAND:
            self.size += (sw - self.size) * 0.12
        self.sw = self.size
        for i in self.LIMBS:
            self.wh[i].append((t, float(P[i][0]), float(P[i][1])))
        self.hist.append(((P[11] + P[12]) / 2, (P[23] + P[24]) / 2))
        self.hist = self.hist[-6:]
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
        self.prev, self.prev_t, self.ok, self.last_good = raw, t, True, t

    def strike(self, i, dirn, now, sens=1.0):
        """True only for a REAL strike: hand/foot i moved quickly, far, and mostly sideways
        toward the opponent (dirn = +1 / -1), ending extended. Idle jitter never passes."""
        h = self.wh[i]
        if not self.ok or len(h) < 3 or self.vis[i] < 0.5 or now - h[-1][0] > 0.15:
            return False
        if h[-1][0] - self.ok_since < 0.6:
            return False
        t1, x1, y1 = h[-1]
        old = next(((t0, x0, y0) for (t0, x0, y0) in h if t1 - t0 <= 0.30), None)
        if old is None or t1 - old[0] < 0.08:
            return False
        t0, x0, y0 = old
        disp = dirn * (x1 - x0) / self.sw
        if disp < STRIKE_DISP / sens or disp / (t1 - t0) < STRIKE_SPEED / sens:
            return False
        if abs(y1 - y0) > 1.3 * abs(x1 - x0):
            return False
        if i < 20:                                           # punch: hand must end up extended
            return dirn * (x1 - self.sh[0]) / self.sw >= REACH_HAND / sens
        other = self.pts[28 if i == 27 else 27]              # kick: foot extended AND lifted
        return (dirn * (x1 - self.hip[0]) / self.sw >= REACH_FOOT / sens
                and (other[1] - y1) / self.sw >= FOOT_LIFT)

    def dodge_dir(self):
        if not (self.ok and self.base):
            return (0.0, -1.0)
        bsh, bhip, bsw = self.base
        mx, my = (self.sh[0] - bsh[0]) / bsw, (self.sh[1] - bsh[1]) / bsw
        if abs(mx) < .2 and abs(my) < .2:
            my = (self.hip[1] - bhip[1]) / bsw
        n = math.hypot(mx, my) or 1.0
        return (mx / n, my / n)

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


class Detector(threading.Thread):
    """Runs pose detection in the background so drawing never waits for it (no more lag)."""

    def __init__(self, trk):
        super().__init__(daemon=True)
        self.trk, self.frame, self.t = trk, None, 0.0
        self.lock, self.ev, self.alive = threading.Lock(), threading.Event(), True

    def post(self, small_rgb, t):
        with self.lock:
            self.frame, self.t = small_rgb, t
        self.ev.set()

    def run(self):
        while self.alive:
            self.ev.wait(); self.ev.clear()
            with self.lock:
                f, t = self.frame, self.t
            if f is None:
                continue
            half = f.shape[1] // 2
            for i in (0, 1):
                try:
                    self.trk[i].update(np.ascontiguousarray(f[:, i * half:(i + 1) * half]), t)
                except Exception as ex:
                    print("detect error:", ex)


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


# --------------------------------------------------------------------------- sprites (image fighters)
class SpriteSet:
    """3 PNG poses of one fighter. The white face oval is detected automatically and cut out,
    so the student's live face shows through it."""

    def __init__(self, name, recolor=False):
        self.img, self.cache = {}, {}
        for pose in ("ready", "right", "left"):
            f = os.path.join(ASSET_DIR, "%s_%s.png" % (name.lower(), pose))
            if os.path.exists(f):
                try:
                    d = self._prep(pygame.image.load(f).convert_alpha(), recolor)
                    if d: self.img[pose] = d
                except Exception as ex:
                    print("Could not load", f, ex)
        self.ok = "ready" in self.img

    @staticmethod
    def _prep(surf, recolor):
        a = pygame.surfarray.array_alpha(surf).T.copy()
        rgb = pygame.surfarray.array3d(surf).transpose(1, 0, 2).copy()
        h, w = a.shape
        if recolor:                                   # red -> blue team colour
            hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
            m = (hsv[..., 1] > 170) & (hsv[..., 2] > 120) & ((hsv[..., 0] <= 3) | (hsv[..., 0] >= 172))
            hsv[..., 0][m] = 110
            rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
        white = ((rgb.min(axis=2) >= 238) & (a > 200)).astype(np.uint8)
        white[int(h * .5):] = 0
        n, lab, st, _ = cv2.connectedComponentsWithStats(white, connectivity=4)
        hc, hw, hh = (w / 2, h * .2, w * .22), None, None
        if n >= 2 and st[1 + int(np.argmax(st[1:, 4])), 4] > 300:
            i = 1 + int(np.argmax(st[1:, 4]))
            mask = cv2.dilate((lab == i).astype(np.uint8), np.ones((5, 5), np.uint8))
            a[mask > 0] = 0
            x, y, bw, bh = st[i, :4]
            hc, hw, hh = (x + bw / 2, y + bh / 2), float(bw), float(bh)
        else:
            hc, hw, hh = (w / 2, h * .2), w * .22, w * .26
        s = pygame.image.frombuffer(np.dstack([rgb, a]).astype(np.uint8).tobytes(), (w, h), "RGBA").convert_alpha()
        return dict(s=s, hc=hc, hw=hw, hh=hh)

    def get(self, pose, sc):
        pose = pose if pose in self.img else "ready"
        k = max(int(sc * 100), 1)
        if (pose, k) not in self.cache:
            if len(self.cache) > 300: self.cache.clear()
            s = self.img[pose]["s"]
            self.cache[(pose, k)] = pygame.transform.smoothscale(
                s, (max(1, int(s.get_width() * k / 100)), max(1, int(s.get_height() * k / 100))))
        return self.cache[(pose, k)], self.img[pose], k / 100


_emask = {}


def face_patch(rgb, cx, cy, cw, chh, fw, fh):
    fw, fh, cw, chh = max(int(fw), 8), max(int(fh), 8), max(int(cw), 8), max(int(chh), 8)
    x0, y0 = int(cx - cw / 2), int(cy - chh / 2); x1, y1 = x0 + cw, y0 + chh
    crop = rgb[max(y0, 0):min(y1, H), max(x0, 0):min(x1, W)]
    if crop.size == 0:
        return None
    crop = cv2.copyMakeBorder(crop, max(-y0, 0), max(y1 - H, 0), max(-x0, 0), max(x1 - W, 0), cv2.BORDER_REPLICATE)
    crop = cv2.resize(crop, (fw, fh))
    m = _emask.get((fw, fh))
    if m is None:
        if len(_emask) > 300: _emask.clear()
        yy, xx = np.ogrid[:fh, :fw]
        d = np.sqrt(((xx - fw / 2 + .5) / (fw / 2)) ** 2 + ((yy - fh / 2 + .5) / (fh / 2)) ** 2)
        m = np.clip((1 - d) / .1 * 255, 0, 255).astype(np.uint8); _emask[(fw, fh)] = m
    return pygame.image.frombuffer(np.dstack([crop, m]).tobytes(), (fw, fh), "RGBA")


def head_info(P, sw):
    """Centre of the real face (camera coords) and its width, from nose / ears / eyes."""
    ear = float(np.linalg.norm(P[7] - P[8]))
    fw = float(np.clip(ear * 1.45, .42 * sw, .8 * sw))
    cx = (P[0][0] + (P[7][0] + P[8][0]) / 2) / 2
    cy = (P[2][1] + P[5][1]) / 2 + .1 * fw * 1.25
    return cx, cy, fw


def draw_sprite(surf, P, sw, ss, pose, rgb, ghosts=()):
    hx, hy, fwc = head_info(P, sw)
    d0 = ss.img["ready"]; w0, h0 = d0["s"].get_size()
    # stable size: scales with the player but is capped so the whole character always fits the screen
    tgt = float(np.clip(sw * SPRITE_BODY_K, H * .28, H * SPRITE_MAX_H))
    tgt = min(tgt, (W / 2 * .92) / w0 * h0)
    spr, d, sc = ss.get(pose, tgt / h0)
    w_, h_ = spr.get_size()
    ox = min(max(hx - d["hc"][0] * sc, 0), W - w_)
    oy = min(max(hy - d["hc"][1] * sc, 6), H - h_ - 6)
    fcx, fcy = ox + d["hc"][0] * sc, oy + d["hc"][1] * sc          # where the face hole really is
    shd = pygame.Surface((int(w_ * .8), 30), pygame.SRCALPHA)
    pygame.draw.ellipse(shd, (0, 0, 0, 100), shd.get_rect())
    surf.blit(shd, shd.get_rect(center=(int(ox + w_ / 2), int(oy + h_ - 8))))
    fw, fh = d["hw"] * sc * 1.14, d["hh"] * sc * 1.14
    chh = fwc * 1.25
    fp = face_patch(rgb, hx, hy, chh * fw / fh, chh, fw, fh) if rgb is not None else None
    if fp is not None:
        surf.blit(fp, fp.get_rect(center=(int(fcx), int(fcy))))
    else:                                              # placeholder face (menu preview)
        rc = pygame.Rect(0, 0, int(fw), int(fh)); rc.center = (int(fcx), int(fcy))
        pygame.draw.ellipse(surf, (240, 200, 160), rc)
        for dx in (-.22, .22):
            pygame.draw.circle(surf, (40, 30, 30), (int(fcx + dx * fw), int(fcy - fh * .08)), max(3, int(fw * .05)))
        pygame.draw.arc(surf, (140, 60, 60), (int(fcx - fw * .2), int(fcy), int(fw * .4), int(fh * .25)),
                        math.radians(200), math.radians(340), 3)
    for gx, gy, ga in ghosts:                          # dodge after-images
        spr.set_alpha(ga); surf.blit(spr, (int(ox + gx), int(oy + gy)))
    spr.set_alpha(255)
    surf.blit(spr, (int(ox), int(oy)))
    return int(ox + w_ / 2), max(int(oy) - 30, 160), pygame.Rect(int(ox), int(oy), w_, h_)


def draw_avatar(surf, P, sw, ch, ss, pose, rgb, ghosts=()):
    """Image fighter if sprites exist, otherwise the drawn fighter. Returns (x, tag_y, rect)."""
    if ss.ok:
        return draw_sprite(surf, P, sw, ss, pose, rgb, ghosts)
    hx, hy, r = draw_fighter(surf, P, sw, ch, rgb)
    return hx, hy - int(r * 1.8) - 14, pygame.Rect(int(hx - sw * 1.1), int(hy - r), int(sw * 2.2), int(sw * 4))


def draw_shield(surf, rc, now):
    """Blue guard bubble around a blocking fighter."""
    pulse = .5 + .5 * math.sin(now * 10)
    r = pygame.Rect(rc.x - 18, rc.y + int(rc.h * .04), rc.w + 36, int(rc.h * .72))
    s = pygame.Surface(r.size, pygame.SRCALPHA)
    pygame.draw.ellipse(s, (80, 160, 255, int(50 + 40 * pulse)), s.get_rect())
    pygame.draw.ellipse(s, (170, 220, 255, 230), s.get_rect(), 6)
    pygame.draw.ellipse(s, (255, 255, 255, int(120 + 100 * pulse)), s.get_rect().inflate(-26, -26), 2)
    surf.blit(s, r.topleft)


def fake_pose(cx, top, k=1.0):
    P = np.zeros((33, 2))
    pts = {0: (0, 35), 2: (-10, 28), 5: (10, 28), 7: (-24, 30), 8: (24, 30), 9: (-8, 45), 10: (8, 45), 11: (-55, 80), 12: (55, 80), 13: (-85, 150), 14: (85, 150), 15: (-45, 112),
           16: (45, 112), 23: (-35, 230), 24: (35, 230), 25: (-45, 312), 26: (45, 312),
           27: (-52, 392), 28: (52, 392)}
    for i, (dx, dy) in pts.items():
        P[i] = (cx + dx * k, top + dy * k)
    return P


# --------------------------------------------------------------------------- UI helpers
_pc = {}


def panel(surf, rect, col=(10, 12, 30), alpha=170, rad=14, border=None, bw=2):
    k = (rect[2], rect[3], col, alpha, rad, border, bw)
    s = _pc.get(k)
    if s is None:
        if len(_pc) > 200: _pc.clear()
        s = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
        pygame.draw.rect(s, (*col, alpha), s.get_rect(), border_radius=rad)
        if border: pygame.draw.rect(s, (*border, 255), s.get_rect(), bw, border_radius=rad)
        _pc[k] = s
    surf.blit(s, (rect[0], rect[1]))


def make_vignette():
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    a = np.clip((d - .65) * 230, 0, 170).astype(np.uint8)
    rgba = np.dstack([np.zeros((H, W, 3), np.uint8), a])
    return pygame.image.frombuffer(rgba.tobytes(), (W, H), "RGBA").convert_alpha()


def mkfont(size):
    p = pygame.font.match_font("impact,arialblack,arial")
    f = pygame.font.Font(p, size) if p else pygame.font.SysFont("arial", size, bold=True)
    return f


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
    flags = pygame.SCALED | pygame.RESIZABLE | (pygame.FULLSCREEN if "--fullscreen" in sys.argv else 0)
    screen = pygame.display.set_mode((W, H), flags)      # SCALED = keeps 16:9, letterboxes any window size
    pygame.display.set_caption("AR Fight Arena")
    world = pygame.Surface((W, H)).convert()
    clock = pygame.time.Clock()
    F = [mkfont(s) for s in (22, 34, 56, 100, 16)]
    print("Building arenas, sounds and music (a few seconds)...")
    vig = make_vignette()
    bgs = [make_bg(k).convert() for k in range(4)]
    for b_ in bgs: b_.blit(vig, (0, 0))              # vignette baked in once (no per-frame cost)
    sprites = {c["name"]: SpriteSet(c["name"]) for c in CHARS}
    sprites_alt = {c["name"]: SpriteSet(c["name"], True) for c in CHARS}
    print("Image fighters found:", [n for n, s_ in sprites.items() if s_.ok] or "none (using drawn fighters)")
    sfx = make_sfx()
    tracks = {"menu": synth_music(92, 4, False), "fight": synth_music(128, 8, True)}
    custom = next((f for f in ("music.mp3", "music.ogg", "music.wav") if os.path.exists(f)), None)
    cfg = dict(mute=False, cur=None)
    tcache = {}

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

    def txt(f, s, pos, col=(255, 255, 255), surf=None, al="c"):
        surf = surf if surf is not None else screen
        key = (f, s, col)
        if key not in tcache:
            if len(tcache) > 700: tcache.clear()
            tcache[key] = (F[f].render(s, True, col), F[f].render(s, True, (0, 0, 0)))
        img, shd = tcache[key]
        r = img.get_rect(); p = (int(pos[0]), int(pos[1]))
        if al == "c": r.center = p
        elif al == "l": r.midleft = p
        else: r.midright = p
        surf.blit(shd, r.move(2, 2)); surf.blit(img, r)

    def big_txt(s, pos, col, scale):
        img = F[3].render(s, True, col); shd = F[3].render(s, True, (0, 0, 0))
        sz = (int(img.get_width() * scale), int(img.get_height() * scale))
        img = pygame.transform.smoothscale(img, sz); shd = pygame.transform.smoothscale(shd, sz)
        r = img.get_rect(center=pos); screen.blit(shd, r.move(4, 4)); screen.blit(img, r)

    def bar(x, y, w, h, frac, col, right=False, ghost=None, rad=8):
        pygame.draw.rect(screen, (15, 15, 28), (x, y, w, h), border_radius=rad)
        if ghost is not None:
            gw = int(w * max(min(ghost, 1), 0))
            pygame.draw.rect(screen, (255, 255, 255), (x + w - gw if right else x, y, gw, h), border_radius=rad)
        fw = int(w * max(min(frac, 1), 0))
        if fw > 0:
            pygame.draw.rect(screen, col, (x + w - fw if right else x, y, fw, h), border_radius=rad)
        pygame.draw.rect(screen, (255, 255, 255), (x, y, w, h), 2, border_radius=rad)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Camera not found!"); sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    trk = [Tracker(), Tracker()]
    det = Detector(trk); det.start()
    zone = lambda i: (i * W // 2 + W // 4, H // 2)
    dim = pygame.Surface((W, H), pygame.SRCALPHA); dim.fill((0, 0, 0, 150))

    state, hero, bg, round_idx, show_cam, paused = "SELECT", [0, 3], 0, 0, True, False
    hp, scores, meter, combo = [MAX_HP] * 2, [0, 0], [0.0, 0.0], [0, 0]
    ghost = [100.0, 100.0]
    hits, dodges, blocks, maxc = [0, 0], [0, 0], [0, 0], [0, 0]
    ready, dod_prev, dod_start, kdo_until = [0.5, 0.5], [False] * 2, [-9.0, -9.0], [0.0, 0.0]
    pose_until, pose_side, hand_flip = [0.0, 0.0], ["right", "left"], [0, 0]
    blk, kblock, sens, sens_until, debug = [False, False], [False, False], 1.0, 0.0, False
    projs, parts, pops = [], [], []
    samples, cal_start, cal_pr, cd_last = [[], []], None, 0, 4
    t_state = time.time(); last = t_state; gt = 0.0; t_left = ROUND_OPTIONS[0]
    shake = 0.0; result = ("", ""); end_reason = None
    pop = lambda s_, x, y, c=(255, 230, 80): pops.append([s_, x, y, 1.0, c])

    def burst(x, y, n, cols):
        for _ in range(n):
            parts.append([x, y, random.uniform(-8, 8), random.uniform(-8, 8), 1.0, random.choice(cols)])

    while True:
        now = time.time(); raw_dt = now - last; dt = min(raw_dt, 0.1); last = now
        kat, kdo = [False, False], [False, False]
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                det.alive = False; det.ev.set(); cap.release(); pygame.quit(); sys.exit()
            if e.type != pygame.KEYDOWN:
                continue
            k = e.key
            if k == pygame.K_m: cfg["mute"] = not cfg["mute"]; setvol()
            elif k == pygame.K_v: show_cam = not show_cam
            elif k in (pygame.K_F11, pygame.K_f): pygame.display.toggle_fullscreen()
            elif k == pygame.K_g: debug = not debug
            elif k in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET):
                sens = round(min(1.8, max(0.6, sens + (0.1 if k == pygame.K_RIGHTBRACKET else -0.1))), 1)
                sens_until = now + 2.0
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
                    ghost = [100.0, 100.0]; hits, dodges, blocks, maxc = [0, 0], [0, 0], [0, 0], [0, 0]
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
        det.post(cv2.resize(rgb, (DETECT_W, DETECT_W * H // W), interpolation=cv2.INTER_AREA), now)

        # ---- game logic -----------------------------------------------------------
        end_reason = None
        if state != "FIGHT": blk = [False, False]
        for i in (0, 1):
            ghost[i] = max(hp[i], ghost[i] - 35 * dt)
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
                pose_until = [0.0, 0.0]
                music("fight"); play("bell")
        elif state == "FIGHT" and not paused:
            gt += dt; t_left -= raw_dt          # round length follows the real clock
            keys = pygame.key.get_pressed()
            kblock = [keys[pygame.K_d], keys[pygame.K_j]]
            blk = [trk[0].blocking() or kblock[0], trk[1].blocking() or kblock[1]]
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
                        if t.strike(L, 1 if i == 0 else -1, now, sens):
                            fire = L; break
                if fire is None and kat[i]:                       # keyboard fallback alternates hands
                    hand_flip[i] ^= 1; fire = 15 if hand_flip[i] else 16
                if fire is not None:
                    o = trk[1 - i]; sup = meter[i] >= 1
                    src = (t.pts[fire] + [i * W // 2, 0]) if t.ok else zone(i)
                    dst = ((o.sh + o.hip) / 2 + [(1 - i) * W // 2, 0]) if o.ok else zone(1 - i)
                    # camera is mirrored: landmark 15 / 27 = YOUR right hand / foot -> "right" image
                    pose_side[i] = "right" if fire in (15, 27) else "left"; pose_until[i] = gt + PUNCH_HOLD
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
                    scores[d] += DODGE_PTS; combo[a] = 0; dodges[d] += 1
                    pop("DODGED! +%d" % DODGE_PTS, ex, ey - 60, (120, 255, 160)); play("dodge")
                elif blk[d]:
                    hp[d] = max(0, hp[d] - p["dmg"] * 0.2); scores[a] += 2; combo[a] = 0; blocks[d] += 1
                    pop("BLOCKED", ex, ey - 60, (180, 200, 255)); play("block")
                    burst(ex, ey, 12, [(200, 220, 255), (255, 255, 255)])
                else:
                    combo[a] += 1; combo[d] = 0; hits[a] += 1; maxc[a] = max(maxc[a], combo[a])
                    gain = 10 + min(combo[a] - 1, 5) * 2
                    if p["sup"]: gain *= 2
                    scores[a] += gain; hp[d] = max(0, hp[d] - p["dmg"])
                    meter[a] = min(1.0, meter[a] + .34)
                    pop("%s +%d" % (HITWORD[p["kind"]], gain), ex, ey - 60, P_COL[a])
                    if combo[a] >= 2: pop("%dx COMBO!" % combo[a], ex, ey - 110, (255, 200, 60))
                    burst(ex, ey, 45, [(255, 200, 40), (255, 90, 30), (255, 255, 255)])
                    shake = now + 0.25; play("punch")
                if hp[d] <= 0:                                  # knockdown: fight goes on, no early end
                    hp[d] = MAX_HP * 0.6; ghost[d] = hp[d]; scores[a] += 25
                    pop("KNOCKDOWN! +25", ex, ey - 150, (255, 90, 80)); play("ko"); shake = now + 0.5
            if t_left <= 0: end_reason = "TIME"

        if end_reason:
            w = 0 if scores[0] > scores[1] else 1 if scores[1] > scores[0] else \
                0 if hp[0] > hp[1] else 1 if hp[1] > hp[0] else -1
            head = "IT'S A DRAW!" if w < 0 else "P%d  %s  WINS!" % (w + 1, CHARS[hero[w]]["name"].upper())
            result = (head, "TIME UP!")
            state = "FINAL"; projs.clear(); music("menu"); play("bell")

        # ---- draw world (arena, fighters, attacks) --------------------------------
        world.blit(bgs[bg], (0, 0))
        for i in (0, 1):
            ch = CHARS[hero[i]]; t = trk[i]
            ss = (sprites_alt if (i == 1 and hero[0] == hero[1]) else sprites)[ch["name"]]
            if t.ok:
                P, sw, rg = t.pts + [i * W // 2, 0], t.sw, rgb
            elif state == "SELECT":
                sw, top_ = (100, 341) if ss.ok else (80, 332)
                P, rg = fake_pose(zone(i)[0], top_, sw / 110), None
            else:
                txt(1, "Step into your zone", zone(i), (255, 255, 255), world); continue
            pose = "ready"
            if state == "FIGHT" and gt < pose_until[i]:
                pose = pose_side[i]
                if SWAP_PUNCH: pose = "left" if pose == "right" else "right"
            ghosts = ()
            if state == "FIGHT" and dod_prev[i]:
                mx, my = trk[i].dodge_dir()
                ghosts = tuple((-mx * 38 * k, -my * 38 * k, 120 - 30 * k) for k in (1, 2, 3))
            hx, ty, rc = draw_avatar(world, P, sw, ch, ss, pose, rg, ghosts)
            pygame.draw.polygon(world, P_COL[i], [(hx - 12, ty + 12), (hx + 12, ty + 12), (hx, ty + 28)])
            txt(0, "P%d" % (i + 1), (hx, ty), P_COL[i], world)
            if state == "FIGHT":
                if blk[i]:
                    draw_shield(world, rc, now); txt(1, "BLOCK", (hx, min(rc.bottom + 18, H - 16)), (150, 210, 255), world)
                elif dod_prev[i]:
                    txt(1, "DODGE", (hx, min(rc.bottom + 18, H - 16)), (120, 255, 160), world)
        for p in projs:
            u = min((gt - p["t0"]) / p["fl"], 1)
            x = p["s"][0] + (p["e"][0] - p["s"][0]) * u
            y = p["s"][1] + (p["e"][1] - p["s"][1]) * u - 60 * math.sin(math.pi * u)
            sz = int((150 if p["kind"] == "slam" else 110) * (1.5 if p["sup"] else 1))
            for k in range(1, 5):
                uu = max(u - k * .04, 0)
                tx = p["s"][0] + (p["e"][0] - p["s"][0]) * uu
                ty2 = p["s"][1] + (p["e"][1] - p["s"][1]) * uu - 60 * math.sin(math.pi * uu)
                pygame.draw.circle(world, TRAIL[p["kind"]], (int(tx), int(ty2)), max(3, sz // 5 - k * 4))
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
            for g_, c_ in ((6, (255, 120, 60)), (3, (255, 200, 80))):      # title glow
                txt(3, "AR FIGHT ARENA", (W // 2 + g_ // 2, 46 + g_ // 2), c_)
            txt(3, "AR FIGHT ARENA", (W // 2, 46), (255, 255, 255))
            txt(0, "MOTION FIGHT CHALLENGE", (W // 2, 98), (255, 220, 120))
            for i in (0, 1):
                ch = CHARS[hero[i]]; cx = zone(i)[0]; col = P_COL[i]
                panel(screen, (cx - 170, 118, 340, 34), col, 230, 17)
                txt(0, "PLAYER %d    %s" % (i + 1, "A / D" if i == 0 else "<  /  >"), (cx, 135), (255, 255, 255))
                txt(2, ch["name"].upper(), (cx, 190), col)
                bob = int(4 * math.sin(now * 5))
                for sgn in (-1, 1):                                          # selector arrows
                    ax = cx + sgn * 190 + sgn * bob
                    pygame.draw.polygon(screen, (255, 255, 255), [(ax + sgn * 14, 190 - 16), (ax + sgn * 14, 190 + 16), (ax - sgn * 14, 190)])
                txt(0, ch["desc"], (cx, 233), (230, 230, 230))
                panel(screen, (cx - 200, 252, 400, 48), (10, 12, 30), 190, 12, col, 2)
                stats = (("POWER", ch["dmg"] / 14), ("SPEED", .4 / ch["cd"]), ("FLIGHT", .45 / ch["flight"]))
                for k, (lb, v) in enumerate(stats):
                    bx = cx - 188 + k * 129
                    txt(4, lb, (bx + 58, 262), (200, 200, 220))
                    pygame.draw.rect(screen, (40, 42, 70), (bx, 276, 116, 10), border_radius=5)
                    pygame.draw.rect(screen, col, (bx, 276, int(116 * min(v, 1)), 10), border_radius=5)
                live = trk[i].ok
                txt(4, "IN ZONE - LIVE!" if live else "STEP INTO YOUR ZONE", (cx, 648),
                    (120, 255, 160) if live else (255, 140, 120))
            panel(screen, (40, 662, W - 80, 46), (10, 12, 30), 200, 14, (255, 220, 120), 2)
            txt(0, "ENTER Start   |   T Round %d:00   |   B Arena: %s   |   M Music %s   |   V Cam   |   F11 Full"
                % (ROUND_OPTIONS[round_idx] // 60, BG_NAMES[bg], "OFF" if cfg["mute"] else "ON"), (W // 2, 685))
        elif state in ("CALIBRATE", "COUNTDOWN"):
            for i in (0, 1):
                rc = (i * W // 2 + 40, 130, W // 2 - 80, H - 190)
                pygame.draw.rect(screen, P_COL[i], rc, 3, border_radius=18)
                txt(0, "PLAYER %d ZONE" % (i + 1), (zone(i)[0], 150), P_COL[i])
        if state == "CALIBRATE":
            panel(screen, (W // 2 - 380, 40, 760, 60), (10, 12, 30), 200, 16, (255, 220, 120), 2)
            txt(1, "Stand still, facing the camera, in your zone", (W // 2, 70))
            pygame.draw.rect(screen, (30, 30, 50), (W // 4, H - 56, W // 2, 22), border_radius=11)
            if cal_pr > 0:
                pygame.draw.rect(screen, (80, 220, 120), (W // 4, H - 56, max(int(W / 2 * cal_pr), 22), 22), border_radius=11)
            if cal_start is None:
                txt(0, "Both players must be fully visible", (W // 2, H - 80), (255, 120, 120))
        elif state == "COUNTDOWN":
            el = now - t_state
            if el < 3:
                big_txt(str(3 - int(el)), (W // 2, H // 2), (255, 230, 80), 1 + .7 * (1 - (el % 1)) ** 2)
            else:
                big_txt("FIGHT!", (W // 2, H // 2), (255, 90, 70), 1.0 + .3 * math.sin((el - 3) * 8))
        if state in ("COUNTDOWN", "FIGHT", "FINAL"):
            for i in (0, 1):
                ch = CHARS[hero[i]]; h = hp[i] / MAX_HP; x = 30 if i == 0 else W - 520
                al = "l" if i == 0 else "r"; ex_ = x if i == 0 else x + 490
                txt(0, "P%d  %s" % (i + 1, ch["name"].upper()), (ex_, 24), P_COL[i], None, al)
                bar(x, 40, 490, 24, h, (80, 220, 100) if h > .5 else (240, 210, 60) if h > .25 else (240, 70, 60),
                    i == 1, ghost[i] / MAX_HP)
                bar(x, 68, 490, 8, meter[i], (255, 120, 255) if meter[i] < 1 else (255, 230, 80), i == 1, None, 4)
                txt(1, "SCORE %d" % scores[i], (ex_, 100), (255, 255, 255), None, al)
                if meter[i] >= 1 and int(now * 4) % 2 == 0:
                    txt(0, "SUPER READY!", (x + (330 if i == 0 else 160), 100), (255, 120, 255))
            for i in (0, 1):                                  # live action indicators
                act = (("STRIKE", state == "FIGHT" and gt < pose_until[i], (255, 200, 80)),
                       ("GUARD", state == "FIGHT" and blk[i], (120, 190, 255)),
                       ("DODGE", state == "FIGHT" and dod_prev[i], (120, 255, 160)))
                for k, (lb, on, c_) in enumerate(act):
                    x0 = (30 if i == 0 else W - 30 - 296) + k * 102
                    panel(screen, (x0, 128, 94, 24), c_ if on else (30, 32, 50), 235 if on else 150, 10)
                    txt(4, lb, (x0 + 47, 140), (0, 0, 0) if on else (140, 145, 170))
            panel(screen, (W // 2 - 80, 10, 160, 68), (10, 12, 30), 210, 16, (255, 255, 255), 2)
            tl = max(int(math.ceil(t_left)), 0) if state != "COUNTDOWN" else ROUND_OPTIONS[round_idx]
            txt(2, "%d:%02d" % divmod(tl, 60), (W // 2, 44),
                (255, 90, 80) if (state == "FIGHT" and t_left < 10) else (255, 255, 255))
        if state == "FIGHT" and gt < 5:
            panel(screen, (W // 2 - 470, H - 66, 940, 44), (10, 12, 30), 200, 14, (255, 240, 150), 2)
            txt(0, "STRIKE toward your opponent  |  DODGE: jump / duck / side-step  |  BLOCK: hands up at your face",
                (W // 2, H - 44), (255, 240, 150))
        if paused and state == "FIGHT":
            screen.blit(dim, (0, 0)); txt(3, "PAUSED", (W // 2, H // 2)); txt(1, "Press P to resume", (W // 2, H // 2 + 80))
        if state == "FINAL":
            screen.blit(dim, (0, 0))
            panel(screen, (W // 2 - 360, 110, 720, 490), (8, 10, 30), 235, 24, (255, 230, 80), 3)
            txt(2, result[1], (W // 2, 165), (255, 90, 80))
            txt(2, result[0], (W // 2, 232), (255, 230, 80))
            txt(3, str(scores[0]), (W // 2 - 170, 315), P_COL[0]); txt(2, "-", (W // 2, 315))
            txt(3, str(scores[1]), (W // 2 + 170, 315), P_COL[1])
            rows = (("HEALTH", int(hp[0]), int(hp[1])), ("HITS LANDED", hits[0], hits[1]),
                    ("DODGES", dodges[0], dodges[1]), ("BLOCKS", blocks[0], blocks[1]),
                    ("BEST COMBO", maxc[0], maxc[1]))
            for k, (lb, a_, b_) in enumerate(rows):
                yy = 390 + k * 31
                pygame.draw.line(screen, (60, 64, 100), (W // 2 - 300, yy + 15), (W // 2 + 300, yy + 15), 1)
                txt(0, str(a_), (W // 2 - 240, yy), P_COL[0]); txt(0, lb, (W // 2, yy), (200, 205, 230))
                txt(0, str(b_), (W // 2 + 240, yy), P_COL[1])
            txt(1, "Press R to play again", (W // 2, 565), (200, 220, 255))
        if debug and state != "FINAL":                         # G = show what the tracker sees
            for i in (0, 1):
                t = trk[i]
                if not t.ok: continue
                for L in (0, 11, 12, 15, 16, 23, 24, 27, 28):
                    c_ = (80, 255, 120) if t.vis[L] >= .5 else (255, 80, 80)
                    pygame.draw.circle(screen, c_, (int(t.pts[L][0] + i * W // 2), int(t.pts[L][1])), 7, 3)
        if state == "SELECT":
            txt(4, "Sensitivity %.1f  ( [ / ] )" % sens, (W // 2, 135), (200, 210, 235))
        elif now < sens_until:
            txt(1, "Sensitivity %.1f" % sens, (W // 2, H - 100), (255, 240, 150))
        if show_cam and state != "FINAL":
            pip = cv2.resize(rgb, (160, 90))
            screen.blit(pygame.image.frombuffer(pip.tobytes(), (160, 90), "RGB"), (W // 2 - 80, 100))
            pygame.draw.rect(screen, (255, 255, 255), (W // 2 - 80, 100, 160, 90), 2, border_radius=6)

        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()