# """
# CLUCK CRICKET v2 - Bluetooth micro:bit bat  (Python + Pygame)

# Install:  pip install pygame numpy bleak pyserial
# Run:      python cluck_cricket_ble.py            (Bluetooth + USB are both tried automatically)
#           python cluck_cricket_ble.py --ble      (Bluetooth only)
#           python cluck_cricket_ble.py --usb --port COM5   (USB cable only)
#           python cluck_cricket_ble.py --name tizip        (connect to the bat named "BBC micro:bit [tizip]")

# Bat: flash microbit_bat_ble.ts (MakeCode) for Bluetooth, or microbit_bat.py (USB cable).

# Keys:  SPACE = shot (SHIFT = power shot, hold LEFT/RIGHT = tilt)   1/2/3 = level (menu)
#        , and . = timing offset -/+10 ms     H = timing assist on/off     F11 = fullscreen     ESC = quit
# """
# import sys, time, math, random, threading, queue, asyncio, argparse
# import numpy as np
# import pygame

# W, H, CX = 1280, 720, 640
# BALLS, WICKETS = 12, 3
# LEVELS = {1: ("EASY", 20, 2.0), 2: ("MEDIUM", 30, 1.6), 3: ("HARD", 40, 1.25)}  # name, target, ball time
# POWER_MIN, POWER_MAX = 1200, 3800      # peak swing acceleration (mg) -> power 0..1
# HIT_WINDOW = 0.30
# HS_FILE = "cricket_highscore.txt"
# NUS_TX = "6e400003-b5a0-f393-e0a9-e50e24dcca9e"     # Nordic UART (micro:bit -> PC)
# FIELDERS = [(200, 360, .30, (220, 60, 60)), (1080, 360, .30, (60, 120, 220)), (CX - 300, 335, .26, (240, 170, 40)),
#             (CX + 300, 335, .26, (160, 80, 200)), (130, 480, .38, (60, 180, 90)), (1150, 480, .38, (230, 90, 160))]
# RED, YEL, WHT, GRN = (255, 70, 70), (255, 220, 60), (255, 255, 255), (110, 240, 150)
# lerp = lambda a, b, t: a + (b - a) * t
# clamp = lambda v, lo, hi: max(lo, min(hi, v))


# # ----------------------------------------------------------------- bat input (Bluetooth + USB)
# class Bat:
#     def __init__(self, mode="auto", port=None, name=""):
#         self.q, self.s, self.name = queue.Queue(), {}, name.lower()
#         if mode in ("auto", "usb"): self._usb(port)
#         if mode in ("auto", "ble"): self._ble()

#     def set(self, src, kind, text): self.s[src] = (kind, text)

#     def info(self):                                  # -> (kind, text, source)
#         for k in ("ok", "search", "kb"):
#             for src, (kind, text) in self.s.items():
#                 if kind == k: return kind, text, src
#         return "kb", "Keyboard mode - SPACE / SHIFT+SPACE", "kb"

#     def feed(self, line):
#         if line.startswith("SWING"):
#             try:
#                 p = line.split(","); self.q.put((time.time(), int(p[1]), int(p[2]) if len(p) > 2 else 0))
#             except ValueError:
#                 pass

#     def _ble(self):
#         try:
#             import bleak
#         except ImportError:
#             self.set("ble", "kb", "Bluetooth needs:  pip install bleak"); return
#         self.set("ble", "search", "Bluetooth: searching for the bat...")
#         threading.Thread(target=lambda: asyncio.run(self._ble_loop()), daemon=True).start()

#     async def _ble_loop(self):
#         from bleak import BleakScanner, BleakClient
#         match = lambda d, ad: "micro:bit" in (d.name or ad.local_name or "").lower() and self.name in (d.name or ad.local_name or "").lower()
#         while True:
#             try:
#                 self.set("ble", "search", "Bluetooth: searching for the bat...")
#                 dev = await BleakScanner.find_device_by_filter(match, timeout=10)
#                 if not dev: continue
#                 self.set("ble", "search", f"Bluetooth: connecting to {dev.name}...")
#                 loop, gone, buf = asyncio.get_running_loop(), asyncio.Event(), [""]

#                 def on_data(_, data):
#                     buf[0] += data.decode(errors="ignore")
#                     while "\n" in buf[0]:
#                         line, buf[0] = buf[0].split("\n", 1); self.feed(line.strip())

#                 cb = lambda c: loop.call_soon_threadsafe(gone.set)
#                 try:       # Windows: ignore stale cached services from an older program on the micro:bit
#                     client = BleakClient(dev, disconnected_callback=cb, winrt=dict(use_cached_services=False))
#                 except TypeError:
#                     client = BleakClient(dev, disconnected_callback=cb)
#                 async with client as c:
#                     svc = next((sv for sv in c.services if sv.uuid.lower().startswith("6e400001")), None)
#                     if not svc: raise RuntimeError("UART missing: re-flash .ts")
#                     ch = next((x for x in svc.characteristics if "notify" in x.properties or "indicate" in x.properties), None)
#                     if not ch: raise RuntimeError("UART has no notify channel")
#                     await c.start_notify(ch, on_data)       # micro:bit sends via ...0002 (indicate)
#                     self.set("ble", "ok", f"Bluetooth connected: {dev.name}")
#                     await gone.wait()
#             except Exception as e:                      # show the real reason on screen + console
#                 import traceback; traceback.print_exc()
#                 self.set("ble", "search", f"BT error: {type(e).__name__} {str(e)[:30]}")
#                 await asyncio.sleep(2)

#     def _usb(self, port):
#         try:
#             import serial
#             from serial.tools import list_ports
#         except ImportError:
#             return
#         if not port:
#             for p in list_ports.comports():
#                 d = (p.description or "").lower()
#                 if p.vid == 0x0D28 or "micro:bit" in d or "mbed" in d: port = p.device; break
#         if port:
#             self.set("usb", "search", f"USB: opening {port}...")
#             threading.Thread(target=self._usb_loop, args=(serial, port), daemon=True).start()

#     def _usb_loop(self, serial, port):
#         while True:
#             try:
#                 with serial.Serial(port, 115200, timeout=1) as s:
#                     self.set("usb", "ok", f"USB cable connected ({port})")
#                     while True: self.feed(s.readline().decode(errors="ignore").strip())
#             except Exception:
#                 self.set("usb", "search", "USB: reconnecting..."); time.sleep(1)


# # ----------------------------------------------------------------- sounds + drawing helpers
# def mk(arr):
#     try:
#         a = (np.clip(arr, -1, 1) * 12000).astype(np.int16)
#         return pygame.sndarray.make_sound(np.column_stack([a, a]))
#     except Exception:
#         return None


# def make_sounds():
#     sr = 44100
#     t = np.arange(int(sr * .12)) / sr; t2 = np.arange(sr) / sr; t3 = np.arange(int(sr * .35)) / sr; t4 = np.arange(int(sr * .2)) / sr
#     roar = np.convolve(np.random.uniform(-1, 1, t2.size), np.ones(40) / 40, "same") * np.minimum(t2 * 6, 1) * np.exp(-t2 * 2.2) * 2.5
#     return dict(crack=mk(np.random.uniform(-1, 1, t.size) * np.exp(-t * 45)), roar=mk(roar),
#                 thud=mk(np.sin(2 * np.pi * 90 * t3) * np.exp(-t3 * 9)), beep=mk(np.sin(2 * np.pi * 660 * t4) * np.exp(-t4 * 8)))


# def rr(s, rect, col, rad=14, alpha=255, border=None, bw=2):
#     r = pygame.Rect(rect); t = pygame.Surface(r.size, pygame.SRCALPHA)
#     pygame.draw.rect(t, (*col, alpha), t.get_rect(), border_radius=rad)
#     if border: pygame.draw.rect(t, (*border, 255), t.get_rect(), bw, border_radius=rad)
#     s.blit(t, r.topleft)


# def bt_icon(s, x, y, col, sc=1.0):
#     pts = [(-5, -5), (5, 5), (0, 10), (0, -10), (5, -5), (-5, 5)]
#     pygame.draw.lines(s, col, False, [(x + px * sc, y + py * sc) for px, py in pts], max(2, int(2 * sc)))


# def star(s, cx, cy, r, col, fill=True):
#     pts = [(cx + (r if i % 2 == 0 else r * .45) * math.sin(i * math.pi / 5), cy - (r if i % 2 == 0 else r * .45) * math.cos(i * math.pi / 5)) for i in range(10)]
#     if fill: pygame.draw.polygon(s, col, pts)
#     else: pygame.draw.polygon(s, col, pts, 3)


# def make_bg(font):
#     s = pygame.Surface((W, H))
#     for y in range(300):
#         k = y / 300; pygame.draw.line(s, (int(80 + 120 * k), int(160 + 70 * k), 255 - int(10 * k)), (0, y), (W, y))
#     pygame.draw.circle(s, (255, 250, 190), (1100, 105), 62); pygame.draw.circle(s, (255, 240, 150), (1100, 105), 40)
#     pygame.draw.rect(s, (60, 62, 86), (0, 150, W, 150))
#     for i, y in enumerate((150, 190, 230, 270)):                  # stand tiers
#         pygame.draw.rect(s, (42, 44, 62), (0, y, W, 6)); pygame.draw.rect(s, (74, 76, 100), (0, y + 6, W, 3))
#     pygame.draw.rect(s, (30, 32, 46), (0, 138, W, 14))            # roof edge
#     rr(s, (CX - 150, 160, 300, 66), (15, 15, 30), 8, border=(255, 200, 60))   # big LED screen
#     t = font.render("CLUCK CUP  LIVE", True, (255, 220, 70)); s.blit(t, t.get_rect(center=(CX, 193)))
#     for x in (70, W - 70):                                        # floodlights
#         pygame.draw.rect(s, (110, 110, 124), (x - 6, 60, 12, 240))
#         pygame.draw.rect(s, (235, 235, 245), (x - 42, 28, 84, 44), border_radius=6)
#         for i in range(4):
#             for j in range(2): pygame.draw.circle(s, (255, 255, 200), (x - 31 + i * 21, 41 + j * 20), 7)
#     for i, y in enumerate(range(300, H, 40)):
#         pygame.draw.rect(s, (46, 140, 60) if i % 2 else (58, 165, 72), (0, y, W, 40))
#     ads = ["PYTHON", "micro:bit", "CODE!", "PLAY!", "AI ROCKS", "BUILD IT"]
#     for i in range(10):
#         r = pygame.Rect(i * 128, 296, 128, 28)
#         pygame.draw.rect(s, [(200, 50, 50), (40, 110, 200), (230, 170, 30), (60, 160, 80)][i % 4], r)
#         img = font.render(ads[i % len(ads)], True, WHT); s.blit(img, img.get_rect(center=r.center))
#     pygame.draw.polygon(s, (205, 175, 110), [(CX - 45, 252), (CX + 45, 252), (CX + 190, H), (CX - 190, H)])
#     for cx_, cy_, rx, ry in ((CX, 585, 120, 50), (CX, 275, 26, 10)):          # worn patches
#         w = pygame.Surface((rx * 2, ry * 2), pygame.SRCALPHA); pygame.draw.ellipse(w, (170, 140, 85, 110), w.get_rect()); s.blit(w, (cx_ - rx, cy_ - ry))
#     pygame.draw.line(s, WHT, (CX - 160, 625), (CX + 160, 625), 4); pygame.draw.line(s, WHT, (CX - 55, 262), (CX + 55, 262), 2)
#     for i in (-1, 0, 1): pygame.draw.line(s, (250, 240, 200), (CX + i * 5, 262), (CX + i * 5, 246), 2)
#     vig = pygame.Surface((W, H), pygame.SRCALPHA)                  # vignette
#     for i in range(70): pygame.draw.rect(vig, (0, 0, 0, int(110 * (1 - i / 70) ** 2)), (i, i, W - 2 * i, H - 2 * i), 1)
#     s.blit(vig, (0, 0))
#     return s


# def person(s, x, y, k, shirt, face=True, chicken=False, bat=None, arm=0.0, helmet=False, pads=False, hat=False):
#     h = lambda v: int(v * k)
#     skin = (240, 190, 150); dark = tuple(int(c * .6) for c in shirt)
#     pygame.draw.ellipse(s, (25, 85, 35), (x - h(42), y - h(7), h(84), h(16)))
#     for dx in (-24, 4):
#         pygame.draw.rect(s, (245, 245, 245), (x + h(dx), y - h(85), h(20), h(85)), border_radius=h(6))
#         if pads:
#             pygame.draw.rect(s, (250, 240, 205), (x + h(dx) - h(3), y - h(62), h(26), h(54)), border_radius=h(8))
#             pygame.draw.rect(s, (150, 140, 110), (x + h(dx) - h(3), y - h(62), h(26), h(54)), max(1, h(2)), border_radius=h(8))
#         pygame.draw.rect(s, (40, 40, 50), (x + h(dx) - h(2), y - h(8), h(24), h(9)), border_radius=h(4))
#     if chicken: pygame.draw.ellipse(s, (255, 250, 235), (x - h(48), y - h(150), h(28), h(54)))
#     pygame.draw.rect(s, shirt, (x - h(32), y - h(165), h(64), h(85)), border_radius=h(16))
#     sh = (x + h(28), y - h(148))
#     hand = (x + h(42), y - h(108)) if bat is not None else (lerp(x + h(34), x + h(14), arm), lerp(y - h(88), y - h(240), arm))
#     pygame.draw.line(s, skin, sh, hand, max(2, h(13)))
#     pygame.draw.circle(s, (255, 230, 90) if bat is not None else skin, hand, max(2, h(10)))
#     if bat is not None:
#         a = math.radians(bat); d = (math.cos(a), -math.sin(a)); L = h(125)
#         p1 = (hand[0] + d[0] * L * .35, hand[1] + d[1] * L * .35); p2 = (hand[0] + d[0] * L, hand[1] + d[1] * L)
#         pygame.draw.line(s, (60, 40, 30), hand, p1, max(2, h(9)))
#         pygame.draw.line(s, (225, 190, 120), p1, p2, max(3, h(22)))
#         pygame.draw.circle(s, (225, 190, 120), (int(p2[0]), int(p2[1])), max(2, h(11)))
#         pygame.draw.circle(s, (255, 230, 90), (int(hand[0]), int(hand[1])), max(2, h(10)))
#     hc = (x, y - h(192)); r = h(30)
#     if chicken:
#         pygame.draw.circle(s, (250, 250, 250), hc, r)
#         for dx in (-10, 0, 10): pygame.draw.circle(s, (230, 40, 40), (hc[0] + h(dx), hc[1] - r), max(2, h(9)))
#         pygame.draw.polygon(s, (255, 170, 30), [(hc[0] - h(8), hc[1] + h(2)), (hc[0] + h(8), hc[1] + h(2)), (hc[0], hc[1] + h(16))])
#         pygame.draw.circle(s, (240, 60, 60), (hc[0], hc[1] + h(20)), max(1, h(5)))
#         for dx in (-11, 11):
#             pygame.draw.circle(s, WHT, (hc[0] + h(dx), hc[1] - h(6)), max(2, h(6))); pygame.draw.circle(s, (0, 0, 0), (hc[0] + h(dx), hc[1] - h(6)), max(1, h(3)))
#         return
#     pygame.draw.circle(s, skin if face else (70, 45, 30), hc, r)
#     if face:
#         for dx in (-11, 11): pygame.draw.circle(s, (0, 0, 0), (hc[0] + h(dx), hc[1] - h(2)), max(1, h(4)))
#         pygame.draw.arc(s, (150, 40, 40), (hc[0] - h(12), hc[1] + h(2), h(24), h(16)), math.pi, 2 * math.pi, max(1, h(3)))
#     if helmet:
#         pygame.draw.ellipse(s, dark, (hc[0] - r - h(3), hc[1] - r - h(5), 2 * r + h(6), h(52)))
#         pygame.draw.line(s, WHT, (hc[0], hc[1] - r - h(3)), (hc[0], hc[1] - h(2)), max(1, h(4)))
#     elif hat:
#         pygame.draw.ellipse(s, WHT, (hc[0] - r - h(8), hc[1] - r + h(2), 2 * r + h(16), h(14)))
#         pygame.draw.ellipse(s, (235, 235, 235), (hc[0] - r + h(4), hc[1] - r - h(10), 2 * r - h(8), h(22)))
#     else:
#         pygame.draw.ellipse(s, dark, (hc[0] - r, hc[1] - r - h(2), 2 * r, h(38)))


# # ----------------------------------------------------------------- ball + rules
# def ball_pos(b, t):
#     gy = lerp(270, 610, t ** 1.1); tb = .62
#     if t < tb: hg = 55 * (1 - (t / tb) ** 2)
#     else:
#         u = (t - tb) / (1 - tb); hg = 95 * 4 * u * (1 - u)
#     x = lerp(CX + b["line"] * 40, CX + b["line"] * 120, t) + b["sway"] * 70 * math.sin(math.pi * t)
#     return x, gy - hg - 70 * t, gy, 5 + 17 * t ** 1.6


# def new_ball(T0):
#     on = random.random() < .78
#     kind = random.choice(["fast", "normal", "normal", "slow", "swing"])
#     return dict(on=on, kind=kind, T=T0 * dict(fast=.78, normal=1, slow=1.3, swing=1)[kind], t0=0, sw=None,
#                 line=random.uniform(-.3, .3) if on else random.choice([-1, 1]) * random.uniform(.9, 1.3),
#                 sway=random.choice([-1, 1]) * random.uniform(.6, 1) if kind == "swing" else 0)


# def R(**k):
#     d = dict(runs=0, out=False, wide=False, wait=1.3, fl=None); d.update(k); return d


# def judge(b, sw):
#     bx, by = ball_pos(b, 1)[:2]
#     if sw is None:
#         if b["on"]: return R(txt="BOWLED!", col=RED, out=True, kind="bowled", wait=1.9)
#         return R(txt="WIDE! +1", col=YEL, runs=1, wide=True, kind="dot")
#     dt, pw, tilt = sw
#     if abs(dt) > HIT_WINDOW:
#         if b["on"]: return R(txt="MISSED... BOWLED!", col=RED, out=True, kind="bowled", wait=1.9)
#         return R(txt="SWING & MISS!", col=(255, 160, 60), kind="dot")
#     q = 1 - abs(dt) / HIT_WINDOW
#     dirn = clamp(clamp(dt / .2, -1, 1) * .8 + clamp(tilt / 3000, -1, 1) * .3, -1, 1)
#     tx = CX + dirn * 620

#     def hit(runs, txt, col=WHT):
#         ty, arc, dur = {6: (190, 260, 1.5), 4: (305, 25, .9), 2: (400, 60, 1.1), 1: (470, 50, 1.0), 0: (560, 30, .8)}[runs]
#         return R(txt=txt, col=col, runs=runs, kind="hit", wait=dur + .9, fl=dict(x0=bx, y0=by, x1=tx, y1=ty, arc=arc, dur=dur))

#     def caught(txt):
#         f = min(FIELDERS, key=lambda f: abs(f[0] - tx))
#         return R(txt=txt, col=RED, out=True, kind="hit", wait=2.3, fl=dict(x0=bx, y0=by, x1=f[0], y1=f[1] - int(185 * f[2]), arc=170, dur=1.3))

#     if not b["on"]:
#         if random.random() < .3: return caught("EDGED! CAUGHT BEHIND!")
#         return hit(1, "EDGED! 1 RUN", YEL) if q > .5 else hit(0, "NO RUN")
#     if q > .7:
#         if pw > .65: return hit(6, "SIXXXER!!", (255, 120, 255))
#         return hit(4, "FOUR!", GRN) if pw > .35 else hit(2, "GENTLE TAP - 2 RUNS", YEL)
#     if q > .45:
#         if pw > .7: return hit(4, "FOUR!", GRN)
#         return hit(2, "2 RUNS", YEL) if pw > .35 else hit(1, "1 RUN", YEL)
#     if q > .2:
#         if pw > .5 and random.random() < .5: return caught("CAUGHT!")
#         return hit(1, "EDGE! 1 RUN", YEL)
#     return caught("TOP EDGE! CAUGHT!") if random.random() < .4 else hit(0, "MISTIMED!")


# # ----------------------------------------------------------------- main
# def main():
#     ap = argparse.ArgumentParser()
#     ap.add_argument("--ble", action="store_true"); ap.add_argument("--usb", action="store_true")
#     ap.add_argument("--port"); ap.add_argument("--name", default="")
#     a = ap.parse_args()
#     bat = Bat("ble" if a.ble else "usb" if a.usb else "auto", a.port, a.name)

#     pygame.mixer.pre_init(44100, -16, 2, 512); pygame.init()
#     scr = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
#     pygame.display.set_caption("Cluck Cricket - micro:bit bat")
#     clock = pygame.time.Clock()
#     F = [pygame.font.SysFont("arial", s, bold=True) for s in (22, 34, 64)]
#     FT = pygame.font.SysFont("impact,arialblack,arial", 104)
#     FS = pygame.font.SysFont("arial", 16, bold=True)
#     S = make_sounds(); play = lambda k: S[k] and S[k].play()
#     bg, cv = make_bg(F[0]), pygame.Surface((W, H))
#     rnd = random.Random(3)
#     crowd = [(x + rnd.randint(-4, 4), y, rnd.choice([(230, 80, 80), (80, 140, 230), (240, 200, 60), (240, 240, 240), (120, 200, 120)]))
#              for y in range(236, 296, 14) for x in range(8, W, 14)]
#     crowd += [(x + rnd.randint(-4, 4), y, rnd.choice([(230, 80, 80), (80, 140, 230), (240, 200, 60), (240, 240, 240), (120, 200, 120)]))
#               for y in range(172, 232, 14) for x in range(8, W, 14) if abs(x - CX) > 170]
#     clouds = [[rnd.randint(0, W), rnd.randint(30, 90), rnd.randint(50, 90)] for _ in range(4)]

#     def txt(f, s, pos, col=WHT, an="center", surf=None, font=None):
#         fo = font or F[f]; img = fo.render(s, True, col); r = img.get_rect(); setattr(r, an, pos)
#         (surf or scr).blit(fo.render(s, True, (0, 0, 0)), r.move(3, 3)); (surf or scr).blit(img, r)

#     def popup(f, s, pos, col, age):
#         sc = 1 + .6 * max(0, 1 - age * 4)
#         for c, o in (((0, 0, 0), 4), (col, 0)):
#             z = pygame.transform.rotozoom(F[f].render(s, True, c), 0, sc); scr.blit(z, z.get_rect(center=(pos[0] + o, pos[1] + o)))

#     def best_read():
#         try: return int(open(HS_FILE).read())
#         except Exception: return 0

#     G = dict(st="MENU", lvl=2, score=0, wk=0, played=0, hist=[], t_st=time.time(), ph="intro", t_ph=time.time(), b=None,
#              res=None, fl=None, t_fl=0, anim=-9, excite=0., off=0., best=best_read(), won=False, shake=0., trail=[],
#              fours=0, sixes=0, assist=True, newbest=False)
#     parts = []

#     def burst(x, y, n, cols, spd=7, grav=.25):
#         for _ in range(n):
#             parts.append([x, y, random.uniform(-spd, spd), random.uniform(-spd * 1.3, spd * .3), 1., random.choice(cols), grav])

#     def start():
#         G.update(st="PLAY", score=0, wk=0, played=0, hist=[], ph="intro", t_ph=time.time(), res=None, fl=None, won=False,
#                  fours=0, sixes=0, newbest=False, trail=[])
#         G["b"] = new_ball(LEVELS[G["lvl"]][2]); play("beep")

#     while True:
#         now = time.time(); swings = []
#         for e in pygame.event.get():
#             if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE): pygame.quit(); sys.exit()
#             if e.type == pygame.KEYDOWN:
#                 if e.key == pygame.K_SPACE:
#                     kp = pygame.key.get_pressed()
#                     swings.append((now, 3800 if e.mod & pygame.KMOD_SHIFT else 2600, (int(kp[pygame.K_RIGHT]) - int(kp[pygame.K_LEFT])) * 2500))
#                 elif e.key in (pygame.K_1, pygame.K_2, pygame.K_3) and G["st"] == "MENU": G["lvl"] = e.key - pygame.K_0
#                 elif e.key == pygame.K_COMMA: G["off"] = round(G["off"] - .01, 2)
#                 elif e.key == pygame.K_PERIOD: G["off"] = round(G["off"] + .01, 2)
#                 elif e.key == pygame.K_h: G["assist"] = not G["assist"]
#                 elif e.key == pygame.K_F11: pygame.display.toggle_fullscreen()
#         while not bat.q.empty():
#             t, mag, tilt = bat.q.get(); swings.append((t + G["off"], mag, tilt))

#         name, target, T0 = LEVELS[G["lvl"]]; b = G["b"]
#         for ts, mag, tilt in swings:
#             G["anim"] = now
#             if G["st"] == "MENU" or (G["st"] == "END" and now - G["t_st"] > 1.5): start(); continue
#             if G["st"] == "PLAY" and G["ph"] == "bowl" and b["sw"] is None:
#                 dt = ts - (b["t0"] + b["T"])
#                 if -.45 <= dt <= .35: b["sw"] = (dt, clamp((mag - POWER_MIN) / (POWER_MAX - POWER_MIN), 0, 1), tilt)

#         # ---------------- game logic ----------------
#         if G["st"] == "PLAY":
#             el = now - G["t_ph"]
#             if G["ph"] == "intro" and el > 1.1: G["ph"], b["t0"] = "bowl", now
#             elif G["ph"] == "bowl":
#                 arr = b["t0"] + b["T"]
#                 if (b["sw"] and now >= arr) or (not b["sw"] and now >= arr + .35):
#                     res = judge(b, b["sw"]); G.update(res=res, ph="after", t_ph=now)
#                     if res["fl"]: G.update(fl=res["fl"], t_fl=now)
#                     if res["kind"] == "hit": play("crack")
#                     if res["kind"] == "bowled": play("thud"); G["shake"] = 12
#                     if res["runs"] >= 4:
#                         G["excite"] = 1.0; play("roar"); G["shake"] = 14 if res["runs"] == 6 else 6
#                         G["sixes" if res["runs"] == 6 else "fours"] += 1
#                         if res["runs"] == 6: burst(CX, 200, 70, [(255, 200, 40), (255, 120, 255), (120, 255, 200), WHT], 9)
#                     if not res["wide"]: G["played"] += 1
#                     G["score"] += res["runs"]; G["wk"] += int(res["out"])
#                     G["hist"].append("Wd" if res["wide"] else "W" if res["out"] else str(res["runs"]) if res["runs"] else ".")
#             elif G["ph"] == "after" and el > G["res"]["wait"]:
#                 G["fl"] = None
#                 if G["score"] >= target or G["wk"] >= WICKETS or G["played"] >= BALLS:
#                     G.update(st="END", t_st=now, won=G["score"] >= target)
#                     if G["score"] > G["best"]:
#                         G["best"], G["newbest"] = G["score"], True
#                         try: open(HS_FILE, "w").write(str(G["best"]))
#                         except Exception: pass
#                     play("roar" if G["won"] else "thud")
#                     if G["won"]: burst(CX, 160, 160, [(255, 200, 40), (255, 90, 160), (90, 220, 255), (140, 255, 140)], 11, .18)
#                 else:
#                     G.update(ph="intro", t_ph=now, trail=[]); G["b"] = new_ball(T0)
#         G["excite"] = max(0, G["excite"] - .012)

#         # ---------------- scene (shakes) ----------------
#         cv.blit(bg, (0, 0))
#         for c in clouds:
#             c[0] = (c[0] + .3) % (W + 200); pygame.draw.ellipse(cv, (255, 255, 255), (c[0] - 100, c[1], c[2] * 2, c[2] // 2))
#         for i, (x, y, col) in enumerate(crowd):
#             pygame.draw.circle(cv, col, (x, int(y + 1.5 * math.sin(now * 2 + x * .05) - G["excite"] * 9 * abs(math.sin(now * 9 + i)))), 6)
#         for fx, fy, fk, fc in sorted(FIELDERS, key=lambda f: f[1]): person(cv, fx, fy, fk, fc)
#         person(cv, CX - 75, 266, .3, (245, 245, 245), hat=True)                       # umpire
#         ph, el, res = G["ph"], now - G["t_ph"], G["res"]
#         arm = (min(el, 1) if ph == "intro" else max(0, 1 - el / .3) if ph == "bowl" else 0) if G["st"] == "PLAY" else 0
#         person(cv, CX, 262, .32, (255, 200, 40), chicken=True, arm=arm)

#         broke = min(el / .5, 1) if (G["st"] == "PLAY" and ph == "after" and res and res["kind"] == "bowled") else 0
#         pygame.draw.ellipse(cv, (25, 85, 35), (CX - 34, 606, 68, 12))
#         for i, lean in enumerate((-.6, .2, .9)):
#             bx0 = CX - 14 + i * 14; ang = lean * broke
#             pygame.draw.line(cv, (250, 240, 200), (bx0, 612), (bx0 + math.sin(ang) * 85, 612 - math.cos(ang) * 85), 6)
#         for dx in (-7, 7):
#             by_ = 526 - 180 * broke * (1 - broke) - 60 * broke
#             pygame.draw.line(cv, (200, 60, 60), (CX + dx - 6 + 30 * broke * dx / 7, by_), (CX + dx + 6 + 30 * broke * dx / 7, by_), 4)

#         def draw_ball(x, y, r, gy=None):
#             tr = G["trail"]; tr.append((x, y, r)); del tr[:-10]
#             for i, (tx_, ty_, tr_) in enumerate(tr[:-1]):
#                 pygame.draw.circle(cv, (190, 50, 60), (int(tx_), int(ty_)), max(1, int(tr_ * (.25 + .6 * i / 10))))
#             if gy is not None: pygame.draw.ellipse(cv, (30, 90, 40), (x - r, gy - r // 3, 2 * r, max(2, int(r * .7))))
#             pygame.draw.circle(cv, (215, 30, 40), (int(x), int(y)), int(r)); pygame.draw.circle(cv, WHT, (int(x), int(y)), int(r), 2)
#             pygame.draw.arc(cv, WHT, (int(x - r * .6), int(y - r * .6), int(r * 1.2), int(r * 1.2)), 0.5, 2.2, 1)

#         if G["st"] == "PLAY" and ph == "bowl":
#             t = (now - b["t0"]) / b["T"]
#             if G["assist"]:
#                 ax, ay = ball_pos(b, 1)[:2]; inwin = abs(now - (b["t0"] + b["T"])) <= HIT_WINDOW
#                 pygame.draw.circle(cv, GRN if inwin else (255, 255, 255), (int(ax), int(ay)), int(32 + 4 * math.sin(now * 10)), 3)
#                 if inwin: txt(1, "SWING!", (int(ax), int(ay) - 52), GRN, surf=cv)
#             if t <= 1.12: x, y, gy, r = ball_pos(b, t); draw_ball(x, y, r, gy)
#         elif G["st"] == "PLAY" and ph == "after" and res and res["kind"] == "bowled" and el < .35:
#             x, y, gy, r = ball_pos(b, 1); draw_ball(x, y, r)

#         u = (now - G["anim"]) / .28
#         ang = 115 - 200 * u if 0 <= u <= 1 else -85 if 1 < u < 1.8 else 115
#         person(cv, CX - 110, 655, 1.0, (40, 90, 220), face=False, bat=ang, helmet=True, pads=True)

#         if G["fl"]:
#             f = G["fl"]; uu = clamp((now - G["t_fl"]) / f["dur"], 0, 1)
#             x = lerp(f["x0"], f["x1"], uu); gy = lerp(f["y0"], f["y1"], uu)
#             y = gy - f["arc"] * math.sin(math.pi * uu); r = int(5 + 13 * clamp((gy - 180) / 400, 0, 1))
#             if not (res["runs"] == 6 and uu >= 1): draw_ball(x, y, r, gy)

#         sh = int(G["shake"]); G["shake"] = max(0, G["shake"] - .8)
#         scr.blit(cv, (random.randint(-sh, sh), random.randint(-sh, sh)) if sh else (0, 0))

#         for p in parts[:]:                                           # particles / confetti
#             p[0] += p[2]; p[1] += p[3]; p[3] += p[6]; p[4] -= .012
#             if p[4] <= 0 or p[1] > H + 20: parts.remove(p)
#             else: pygame.draw.rect(scr, p[5], (int(p[0]), int(p[1]), 9, 6))

#         # ---------------- popups + timing meter ----------------
#         if G["st"] == "PLAY" and ph == "after" and res:
#             popup(2, res["txt"], (CX, 128), res["col"], el)
#             if b["sw"]:
#                 dt, pw, _ = b["sw"]; mx = CX + 250
#                 rr(scr, (mx - 235, H - 150, 470, 104), (10, 15, 40), 16, 200)
#                 for lo, hi, col in ((-.30, -.18, (230, 90, 60)), (-.18, -.09, (240, 200, 60)), (-.09, .09, (90, 220, 120)), (.09, .18, (240, 200, 60)), (.18, .30, (230, 90, 60))):
#                     pygame.draw.rect(scr, col, (mx + lo / .35 * 215, H - 120, (hi - lo) / .35 * 215 + 1, 18))
#                 pm = mx + clamp(dt, -.34, .34) / .35 * 215
#                 pygame.draw.polygon(scr, WHT, [(pm, H - 123), (pm - 9, H - 139), (pm + 9, H - 139)])
#                 txt(0, "EARLY", (mx - 225, H - 92), (200, 200, 220), "midleft", font=FS); txt(0, "LATE", (mx + 225, H - 92), (200, 200, 220), "midright", font=FS)
#                 txt(0, "PERFECT!" if abs(dt) < .09 else "TOO EARLY" if dt < 0 else "TOO LATE", (mx, H - 92), YEL, font=FS)
#                 txt(0, "POWER", (mx - 225, H - 66), WHT, "midleft", font=FS)
#                 pygame.draw.rect(scr, (60, 60, 80), (mx - 150, H - 74, 370, 16), border_radius=8)
#                 pygame.draw.rect(scr, (255, 120, 60), (mx - 150, H - 74, int(370 * pw), 16), border_radius=8)
#         elif G["st"] == "PLAY" and ph == "intro":
#             txt(1, f"Ball {G['played'] + 1} of {BALLS} - get ready!", (CX, 128))

#         # ---------------- HUD ----------------
#         if G["st"] != "MENU":
#             rr(scr, (12, 10, 300, 66), (10, 15, 40), 16, 200, (255, 200, 60))
#             txt(0, "SCORE", (28, 28), (255, 200, 60), "midleft", font=FS); txt(2, f"{G['score']}/{G['wk']}", (28, 54), WHT, "midleft", font=F[1])
#             rr(scr, (CX - 190, 10, 380, 66), (10, 15, 40), 16, 200, (90, 160, 255))
#             txt(1, f"TARGET {target}  -  {name}", (CX, 30))
#             need = target - G["score"]
#             txt(0, f"Need {need} from {BALLS - G['played']} balls" if need > 0 else "TARGET REACHED!", (CX, 58), GRN, font=FS)
#             rr(scr, (W - 312, 10, 300, 66), (10, 15, 40), 16, 200, (255, 120, 120))
#             for i in range(BALLS): pygame.draw.circle(scr, (110, 110, 130) if i < G["played"] else (230, 60, 70), (W - 296 + i * 24, 30), 8)
#             txt(0, "WKTS", (W - 300, 58), (255, 150, 150), "midleft", font=FS)
#             for i in range(WICKETS):
#                 alive = i >= G["wk"]
#                 for j in range(3): pygame.draw.line(scr, WHT if alive else (120, 70, 70), (W - 232 + i * 40 + j * 7, 48), (W - 232 + i * 40 + j * 7, 68), 3)
#                 if not alive: pygame.draw.line(scr, RED, (W - 236 + i * 40, 46), (W - 214 + i * 40, 70), 4)
#             for i, hs in enumerate(G["hist"][-7:]):
#                 c = RED if hs == "W" else GRN if hs in ("4", "6") else (230, 230, 230)
#                 pygame.draw.circle(scr, c, (32 + i * 38, 106), 16); pygame.draw.circle(scr, (0, 0, 0), (32 + i * 38, 106), 16, 2)
#                 txt(0, hs, (32 + i * 38, 106), (0, 0, 0), font=FS)
#         kind, text, src = bat.info()
#         pc = {"ok": (90, 230, 130), "search": (255, 200, 70), "kb": (170, 170, 190)}[kind]
#         wpx = FS.size(text)[0] + 70
#         rr(scr, (12, H - 40, wpx, 30), (10, 15, 40), 15, 210, pc)
#         pygame.draw.circle(scr, pc, (30, H - 25), 6 if kind == "search" and int(now * 3) % 2 else 8)
#         bt_icon(scr, 52, H - 25, pc, .8) if src == "ble" else None
#         txt(0, text, (68, H - 25), WHT, "midleft", font=FS)
#         txt(0, f"offset {G['off']:+.2f}s (, .)   assist {'ON' if G['assist'] else 'OFF'} (H)   fullscreen F11", (W - 12, H - 25), (225, 225, 240), "midright", font=FS)

#         # ---------------- menu / end ----------------
#         if G["st"] == "MENU":
#             ov = pygame.Surface((W, H), pygame.SRCALPHA); ov.fill((5, 10, 35, 175)); scr.blit(ov, (0, 0))
#             txt(0, "CLUCK CRICKET", (CX, 86 + int(4 * math.sin(now * 3))), YEL, surf=scr, font=FT)
#             txt(1, "micro:bit Bluetooth Bat Challenge", (CX, 160), (190, 220, 255))
#             rr(scr, (CX - 340, 205, 680, 84), (15, 25, 60), 18, 235, pc, 3)
#             pygame.draw.circle(scr, pc, (CX - 304, 247), 10 if kind != "search" or int(now * 3) % 2 else 6)
#             if src == "ble": bt_icon(scr, CX - 270, 247, pc, 1.3)
#             txt(1, text, (CX - 245, 232), WHT, "midleft")
#             txt(0, "Switch the bat on - or press SPACE to play with the keyboard" if kind != "ok" else "Bat ready! Swing it to start", (CX - 245, 268), (200, 210, 230), "midleft", font=FS)
#             for i in (1, 2, 3):
#                 sel = G["lvl"] == i; x0 = CX - 345 + (i - 1) * 235
#                 rr(scr, (x0, 312 - 6 * sel, 220, 92 + 12 * sel), (30, 60, 130) if sel else (20, 30, 70), 16, 240, YEL if sel else (80, 100, 160), 4 if sel else 2)
#                 txt(1, LEVELS[i][0], (x0 + 110, 340 - 6 * sel), YEL if sel else WHT); txt(0, f"Target {LEVELS[i][1]}  [{i}]", (x0 + 110, 378 - 6 * sel), (200, 215, 240), font=FS)
#             for i, (a1, a2) in enumerate((("TIMING", "early = leg,  late = off side"), ("POWER", "harder swing = more runs"), ("WIDE BALL?", "leave it alone! (+1 run)"))):
#                 x0 = CX - 345 + i * 235
#                 rr(scr, (x0, 432, 220, 74), (20, 30, 70), 14, 220, (80, 100, 160)); txt(0, a1, (x0 + 110, 457), YEL, font=FS); txt(0, a2, (x0 + 110, 484), WHT, font=FS)
#             txt(0, f"Best score: {G['best']}", (CX, 540), (200, 220, 255), font=F[0])
#             pill = pygame.Rect(CX - 210, 585, 420, 64); rr(scr, pill, (255, 150, 40) if int(now * 2) % 2 else (240, 110, 30), 32, 255, WHT, 3)
#             txt(1, "SWING TO START", pill.center)
#         elif G["st"] == "END":
#             ov = pygame.Surface((W, H), pygame.SRCALPHA); ov.fill((5, 10, 35, 185)); scr.blit(ov, (0, 0))
#             rr(scr, (CX - 340, 110, 680, 450), (18, 28, 70), 26, 240, YEL if G["won"] else (200, 90, 90), 4)
#             txt(2, "YOU WIN!" if G["won"] else "INNINGS OVER", (CX, 175), GRN if G["won"] else RED)
#             stars = (3 if G["wk"] <= 1 else 2) if G["won"] else (1 if G["score"] >= target * .6 else 0)
#             for i in range(3):
#                 cy_ = 270 - (14 if i == 1 else 0)
#                 star(scr, CX - 110 + i * 110, cy_, 44, (255, 210, 50) if i < stars else (90, 100, 130), i < stars)
#             txt(2, f"{G['score']}/{G['wk']}", (CX, 360), WHT); txt(0, f"target {target}  -  {name}", (CX, 405), (190, 210, 240))
#             txt(0, f"Fours: {G['fours']}     Sixes: {G['sixes']}     Best: {G['best']}", (CX, 445), YEL)
#             if G["newbest"]: txt(1, "NEW BEST!", (CX, 485), (255, 120, 255))
#             txt(1, "Swing to play again", (CX, 530), WHT if int(now * 2) % 2 else YEL)

#         pygame.display.flip(); clock.tick(60)


# if __name__ == "__main__":
#     main()


# """
# CLUCK CRICKET v3 - Bluetooth micro:bit bat  (Python + Pygame)

# Install:  pip install pygame numpy bleak pyserial
# Run:      python cluck_cricket_ble.py            (Bluetooth + USB are both tried automatically)
#           python cluck_cricket_ble.py --ble      (Bluetooth only)
#           python cluck_cricket_ble.py --usb --port COM5   (USB cable only)
#           python cluck_cricket_ble.py --name tizip        (connect to the bat named "BBC micro:bit [tizip]")

# Bat: flash microbit_bat_ble.ts (MakeCode) for Bluetooth, or microbit_bat.py (USB cable).
#      Bat line format:  SWING,<peak_mg>,<tilt>[,<micro:bit millis>]
#      The 4th field is OPTIONAL. If the bat sends control.millis(), the game removes Bluetooth jitter
#      (clock-sync) and timing becomes much more accurate.

# Keys:  SPACE = shot (SHIFT = power shot, hold LEFT/RIGHT = tilt)   1/2/3 = level (menu)
#        C = calibrate bat timing (menu)    P = pause    , and . = offset -/+10 ms
#        H = timing assist on/off           F11 = fullscreen     ESC = quit

# What's new in v3
#   * Accuracy: monotonic clock, Bluetooth clock-sync, swing de-bounce, one-tap bat CALIBRATION,
#     per-level timing windows, offset/assist/level saved between runs.
#   * UI: live timing bar (watch the ball slide into the green zone), exact early/late in ms,
#     ball-type warnings, screen flashes, pause, required run-rate, accuracy stats on the end screen.
# """
# import sys, os, time, math, random, threading, queue, asyncio, argparse, json, statistics
# import numpy as np
# import pygame

# clk = time.perf_counter                    # monotonic, high-resolution clock (time.time() can jump)
# W, H, CX = 1280, 720, 640
# BALLS, WICKETS = 12, 3
# LEVELS = {1: ("EASY", 20, 2.0, .32), 2: ("MEDIUM", 30, 1.6, .28), 3: ("HARD", 40, 1.25, .22)}  # name, target, ball time, hit window (s)
# POWER_MIN, POWER_MAX = 1200, 3800      # peak swing acceleration (mg) -> power 0..1
# MR = .60                               # timing-bar range (+/- seconds)
# DEBOUNCE = .25                         # ignore a 2nd swing trigger within this time (back-swing)
# BASE = os.path.dirname(os.path.abspath(__file__))
# HS_FILE, CFG_FILE = os.path.join(BASE, "cricket_highscore.txt"), os.path.join(BASE, "cricket_settings.json")
# NUS_TX = "6e400003-b5a0-f393-e0a9-e50e24dcca9e"     # Nordic UART (micro:bit -> PC)
# FIELDERS = [(200, 360, .30, (220, 60, 60)), (1080, 360, .30, (60, 120, 220)), (CX - 300, 335, .26, (240, 170, 40)),
#             (CX + 300, 335, .26, (160, 80, 200)), (130, 480, .38, (60, 180, 90)), (1150, 480, .38, (230, 90, 160))]
# RED, YEL, WHT, GRN = (255, 70, 70), (255, 220, 60), (255, 255, 255), (110, 240, 150)
# ZONES = ((1.0, (230, 90, 60)), (.8, (240, 160, 60)), (.55, (240, 215, 70)), (.3, (90, 220, 120)))   # fraction of window, colour
# lerp = lambda a, b, t: a + (b - a) * t
# clamp = lambda v, lo, hi: max(lo, min(hi, v))


# # ----------------------------------------------------------------- bat input (Bluetooth + USB)
# class Bat:
#     def __init__(self, mode="auto", port=None, name=""):
#         self.q, self.s, self.name, self.sync = queue.Queue(), {}, name.lower(), []
#         if mode in ("auto", "usb"): self._usb(port)
#         if mode in ("auto", "ble"): self._ble()

#     def set(self, src, kind, text): self.s[src] = (kind, text)

#     def info(self):                                  # -> (kind, text, source)
#         for k in ("ok", "search", "kb"):
#             for src, (kind, text) in self.s.items():
#                 if kind == k: return kind, text, src
#         return "kb", "Keyboard mode - SPACE / SHIFT+SPACE", "kb"

#     def feed(self, line):
#         if not line.startswith("SWING"): return
#         rx = clk()
#         try:
#             p = line.split(",")
#             mag = int(p[1]); tilt = int(p[2]) if len(p) > 2 else 0
#             ms = int(p[3]) / 1000 if len(p) > 3 else None
#         except (ValueError, IndexError):
#             return
#         t = rx
#         if ms is not None:                     # clock-sync: the fastest packet ~ true latency, remove the jitter above it
#             off = rx - ms
#             if self.sync and abs(off - min(self.sync)) > 2: self.sync.clear()      # bat was reset
#             self.sync.append(off); del self.sync[:-60]
#             t = ms + min(self.sync)
#         self.q.put((t, mag, tilt))

#     def _ble(self):
#         try:
#             import bleak
#         except ImportError:
#             self.set("ble", "kb", "Bluetooth needs:  pip install bleak"); return
#         self.set("ble", "search", "Bluetooth: searching for the bat...")
#         threading.Thread(target=lambda: asyncio.run(self._ble_loop()), daemon=True).start()

#     async def _ble_loop(self):
#         from bleak import BleakScanner, BleakClient
#         match = lambda d, ad: "micro:bit" in (d.name or ad.local_name or "").lower() and self.name in (d.name or ad.local_name or "").lower()
#         while True:
#             try:
#                 self.set("ble", "search", "Bluetooth: searching for the bat...")
#                 dev = await BleakScanner.find_device_by_filter(match, timeout=10)
#                 if not dev: continue
#                 self.set("ble", "search", f"Bluetooth: connecting to {dev.name}...")
#                 loop, gone, buf = asyncio.get_running_loop(), asyncio.Event(), [""]

#                 def on_data(_, data):
#                     buf[0] += data.decode(errors="ignore")
#                     while "\n" in buf[0]:
#                         line, buf[0] = buf[0].split("\n", 1); self.feed(line.strip())

#                 cb = lambda c: loop.call_soon_threadsafe(gone.set)
#                 try:       # Windows: ignore stale cached services from an older program on the micro:bit
#                     client = BleakClient(dev, disconnected_callback=cb, winrt=dict(use_cached_services=False))
#                 except TypeError:
#                     client = BleakClient(dev, disconnected_callback=cb)
#                 async with client as c:
#                     svc = next((sv for sv in c.services if sv.uuid.lower().startswith("6e400001")), None)
#                     if not svc: raise RuntimeError("UART missing: re-flash .ts")
#                     ch = next((x for x in svc.characteristics if "notify" in x.properties or "indicate" in x.properties), None)
#                     if not ch: raise RuntimeError("UART has no notify channel")
#                     self.sync.clear()
#                     await c.start_notify(ch, on_data)       # micro:bit sends via ...0002 (indicate)
#                     self.set("ble", "ok", f"Bluetooth connected: {dev.name}")
#                     await gone.wait()
#                 self.set("ble", "search", "Bluetooth: bat disconnected, searching...")
#             except Exception as e:                      # show the real reason on screen + console
#                 import traceback; traceback.print_exc()
#                 self.set("ble", "search", f"BT error: {type(e).__name__} {str(e)[:30]}")
#                 await asyncio.sleep(2)

#     def _usb(self, port):
#         try:
#             import serial
#             from serial.tools import list_ports
#         except ImportError:
#             return
#         if not port:
#             for p in list_ports.comports():
#                 d = (p.description or "").lower()
#                 if p.vid == 0x0D28 or "micro:bit" in d or "mbed" in d: port = p.device; break
#         if port:
#             self.set("usb", "search", f"USB: opening {port}...")
#             threading.Thread(target=self._usb_loop, args=(serial, port), daemon=True).start()

#     def _usb_loop(self, serial, port):
#         while True:
#             try:
#                 with serial.Serial(port, 115200, timeout=1) as s:
#                     self.sync.clear()
#                     self.set("usb", "ok", f"USB cable connected ({port})")
#                     while True: self.feed(s.readline().decode(errors="ignore").strip())
#             except Exception:
#                 self.set("usb", "search", "USB: reconnecting..."); time.sleep(1)


# # ----------------------------------------------------------------- settings
# def load_cfg():
#     try:
#         with open(CFG_FILE) as f: return json.load(f)
#     except Exception:
#         return {}


# def save_cfg(G):
#     try:
#         with open(CFG_FILE, "w") as f: json.dump(dict(off=G["off"], assist=G["assist"], lvl=G["lvl"]), f)
#     except Exception:
#         pass


# # ----------------------------------------------------------------- sounds + drawing helpers
# def mk(arr):
#     try:
#         a = (np.clip(arr, -1, 1) * 12000).astype(np.int16)
#         return pygame.sndarray.make_sound(np.column_stack([a, a]))
#     except Exception:
#         return None


# def make_sounds():
#     sr = 44100
#     t = np.arange(int(sr * .12)) / sr; t2 = np.arange(sr) / sr; t3 = np.arange(int(sr * .35)) / sr; t4 = np.arange(int(sr * .2)) / sr
#     roar = np.convolve(np.random.uniform(-1, 1, t2.size), np.ones(40) / 40, "same") * np.minimum(t2 * 6, 1) * np.exp(-t2 * 2.2) * 2.5
#     return dict(crack=mk(np.random.uniform(-1, 1, t.size) * np.exp(-t * 45)), roar=mk(roar),
#                 thud=mk(np.sin(2 * np.pi * 90 * t3) * np.exp(-t3 * 9)), beep=mk(np.sin(2 * np.pi * 660 * t4) * np.exp(-t4 * 8)))


# def rr(s, rect, col, rad=14, alpha=255, border=None, bw=2):
#     r = pygame.Rect(rect); t = pygame.Surface(r.size, pygame.SRCALPHA)
#     pygame.draw.rect(t, (*col, alpha), t.get_rect(), border_radius=rad)
#     if border: pygame.draw.rect(t, (*border, 255), t.get_rect(), bw, border_radius=rad)
#     s.blit(t, r.topleft)


# def bt_icon(s, x, y, col, sc=1.0):
#     pts = [(-5, -5), (5, 5), (0, 10), (0, -10), (5, -5), (-5, 5)]
#     pygame.draw.lines(s, col, False, [(x + px * sc, y + py * sc) for px, py in pts], max(2, int(2 * sc)))


# def star(s, cx, cy, r, col, fill=True):
#     pts = [(cx + (r if i % 2 == 0 else r * .45) * math.sin(i * math.pi / 5), cy - (r if i % 2 == 0 else r * .45) * math.cos(i * math.pi / 5)) for i in range(10)]
#     if fill: pygame.draw.polygon(s, col, pts)
#     else: pygame.draw.polygon(s, col, pts, 3)


# def make_bg(font):
#     s = pygame.Surface((W, H))
#     for y in range(300):
#         k = y / 300; pygame.draw.line(s, (int(80 + 120 * k), int(160 + 70 * k), 255 - int(10 * k)), (0, y), (W, y))
#     pygame.draw.circle(s, (255, 250, 190), (1100, 105), 62); pygame.draw.circle(s, (255, 240, 150), (1100, 105), 40)
#     pygame.draw.rect(s, (60, 62, 86), (0, 150, W, 150))
#     for i, y in enumerate((150, 190, 230, 270)):                  # stand tiers
#         pygame.draw.rect(s, (42, 44, 62), (0, y, W, 6)); pygame.draw.rect(s, (74, 76, 100), (0, y + 6, W, 3))
#     pygame.draw.rect(s, (30, 32, 46), (0, 138, W, 14))            # roof edge
#     rr(s, (CX - 150, 160, 300, 66), (15, 15, 30), 8, border=(255, 200, 60))   # big LED screen
#     t = font.render("CLUCK CUP  LIVE", True, (255, 220, 70)); s.blit(t, t.get_rect(center=(CX, 193)))
#     for x in (70, W - 70):                                        # floodlights
#         pygame.draw.rect(s, (110, 110, 124), (x - 6, 60, 12, 240))
#         pygame.draw.rect(s, (235, 235, 245), (x - 42, 28, 84, 44), border_radius=6)
#         for i in range(4):
#             for j in range(2): pygame.draw.circle(s, (255, 255, 200), (x - 31 + i * 21, 41 + j * 20), 7)
#     for i, y in enumerate(range(300, H, 40)):
#         pygame.draw.rect(s, (46, 140, 60) if i % 2 else (58, 165, 72), (0, y, W, 40))
#     ads = ["PYTHON", "micro:bit", "CODE!", "PLAY!", "AI ROCKS", "BUILD IT"]
#     for i in range(10):
#         r = pygame.Rect(i * 128, 296, 128, 28)
#         pygame.draw.rect(s, [(200, 50, 50), (40, 110, 200), (230, 170, 30), (60, 160, 80)][i % 4], r)
#         img = font.render(ads[i % len(ads)], True, WHT); s.blit(img, img.get_rect(center=r.center))
#     pygame.draw.polygon(s, (205, 175, 110), [(CX - 45, 252), (CX + 45, 252), (CX + 190, H), (CX - 190, H)])
#     for cx_, cy_, rx, ry in ((CX, 585, 120, 50), (CX, 275, 26, 10)):          # worn patches
#         w = pygame.Surface((rx * 2, ry * 2), pygame.SRCALPHA); pygame.draw.ellipse(w, (170, 140, 85, 110), w.get_rect()); s.blit(w, (cx_ - rx, cy_ - ry))
#     pygame.draw.line(s, WHT, (CX - 160, 625), (CX + 160, 625), 4); pygame.draw.line(s, WHT, (CX - 55, 262), (CX + 55, 262), 2)
#     for i in (-1, 0, 1): pygame.draw.line(s, (250, 240, 200), (CX + i * 5, 262), (CX + i * 5, 246), 2)
#     vig = pygame.Surface((W, H), pygame.SRCALPHA)                  # vignette
#     for i in range(70): pygame.draw.rect(vig, (0, 0, 0, int(110 * (1 - i / 70) ** 2)), (i, i, W - 2 * i, H - 2 * i), 1)
#     s.blit(vig, (0, 0))
#     return s


# def person(s, x, y, k, shirt, face=True, chicken=False, bat=None, arm=0.0, helmet=False, pads=False, hat=False):
#     h = lambda v: int(v * k)
#     skin = (240, 190, 150); dark = tuple(int(c * .6) for c in shirt)
#     pygame.draw.ellipse(s, (25, 85, 35), (x - h(42), y - h(7), h(84), h(16)))
#     for dx in (-24, 4):
#         pygame.draw.rect(s, (245, 245, 245), (x + h(dx), y - h(85), h(20), h(85)), border_radius=h(6))
#         if pads:
#             pygame.draw.rect(s, (250, 240, 205), (x + h(dx) - h(3), y - h(62), h(26), h(54)), border_radius=h(8))
#             pygame.draw.rect(s, (150, 140, 110), (x + h(dx) - h(3), y - h(62), h(26), h(54)), max(1, h(2)), border_radius=h(8))
#         pygame.draw.rect(s, (40, 40, 50), (x + h(dx) - h(2), y - h(8), h(24), h(9)), border_radius=h(4))
#     if chicken: pygame.draw.ellipse(s, (255, 250, 235), (x - h(48), y - h(150), h(28), h(54)))
#     pygame.draw.rect(s, shirt, (x - h(32), y - h(165), h(64), h(85)), border_radius=h(16))
#     sh = (x + h(28), y - h(148))
#     hand = (x + h(42), y - h(108)) if bat is not None else (lerp(x + h(34), x + h(14), arm), lerp(y - h(88), y - h(240), arm))
#     pygame.draw.line(s, skin, sh, hand, max(2, h(13)))
#     pygame.draw.circle(s, (255, 230, 90) if bat is not None else skin, hand, max(2, h(10)))
#     if bat is not None:
#         a = math.radians(bat); d = (math.cos(a), -math.sin(a)); L = h(125)
#         p1 = (hand[0] + d[0] * L * .35, hand[1] + d[1] * L * .35); p2 = (hand[0] + d[0] * L, hand[1] + d[1] * L)
#         pygame.draw.line(s, (60, 40, 30), hand, p1, max(2, h(9)))
#         pygame.draw.line(s, (225, 190, 120), p1, p2, max(3, h(22)))
#         pygame.draw.circle(s, (225, 190, 120), (int(p2[0]), int(p2[1])), max(2, h(11)))
#         pygame.draw.circle(s, (255, 230, 90), (int(hand[0]), int(hand[1])), max(2, h(10)))
#     hc = (x, y - h(192)); r = h(30)
#     if chicken:
#         pygame.draw.circle(s, (250, 250, 250), hc, r)
#         for dx in (-10, 0, 10): pygame.draw.circle(s, (230, 40, 40), (hc[0] + h(dx), hc[1] - r), max(2, h(9)))
#         pygame.draw.polygon(s, (255, 170, 30), [(hc[0] - h(8), hc[1] + h(2)), (hc[0] + h(8), hc[1] + h(2)), (hc[0], hc[1] + h(16))])
#         pygame.draw.circle(s, (240, 60, 60), (hc[0], hc[1] + h(20)), max(1, h(5)))
#         for dx in (-11, 11):
#             pygame.draw.circle(s, WHT, (hc[0] + h(dx), hc[1] - h(6)), max(2, h(6))); pygame.draw.circle(s, (0, 0, 0), (hc[0] + h(dx), hc[1] - h(6)), max(1, h(3)))
#         return
#     pygame.draw.circle(s, skin if face else (70, 45, 30), hc, r)
#     if face:
#         for dx in (-11, 11): pygame.draw.circle(s, (0, 0, 0), (hc[0] + h(dx), hc[1] - h(2)), max(1, h(4)))
#         pygame.draw.arc(s, (150, 40, 40), (hc[0] - h(12), hc[1] + h(2), h(24), h(16)), math.pi, 2 * math.pi, max(1, h(3)))
#     if helmet:
#         pygame.draw.ellipse(s, dark, (hc[0] - r - h(3), hc[1] - r - h(5), 2 * r + h(6), h(52)))
#         pygame.draw.line(s, WHT, (hc[0], hc[1] - r - h(3)), (hc[0], hc[1] - h(2)), max(1, h(4)))
#     elif hat:
#         pygame.draw.ellipse(s, WHT, (hc[0] - r - h(8), hc[1] - r + h(2), 2 * r + h(16), h(14)))
#         pygame.draw.ellipse(s, (235, 235, 235), (hc[0] - r + h(4), hc[1] - r - h(10), 2 * r - h(8), h(22)))
#     else:
#         pygame.draw.ellipse(s, dark, (hc[0] - r, hc[1] - r - h(2), 2 * r, h(38)))


# # ----------------------------------------------------------------- ball + rules
# def ball_pos(b, t):
#     gy = lerp(270, 610, t ** 1.1); tb = .62
#     if t < tb: hg = 55 * (1 - (t / tb) ** 2)
#     else:
#         u = (t - tb) / (1 - tb); hg = 95 * 4 * u * (1 - u)
#     x = lerp(CX + b["line"] * 40, CX + b["line"] * 120, t) + b["sway"] * 70 * math.sin(math.pi * t)
#     return x, gy - hg - 70 * t, gy, 5 + 17 * t ** 1.6


# def new_ball(T0):
#     on = random.random() < .78
#     kind = random.choice(["fast", "normal", "normal", "slow", "swing"])
#     return dict(on=on, kind=kind, T=T0 * dict(fast=.78, normal=1, slow=1.3, swing=1)[kind], t0=0, sw=None,
#                 line=random.uniform(-.3, .3) if on else random.choice([-1, 1]) * random.uniform(.9, 1.3),
#                 sway=random.choice([-1, 1]) * random.uniform(.6, 1) if kind == "swing" else 0)


# def R(**k):
#     d = dict(runs=0, out=False, wide=False, wait=1.3, fl=None); d.update(k); return d


# def judge(b, sw, win):
#     bx, by = ball_pos(b, 1)[:2]
#     if sw is None:
#         if b["on"]: return R(txt="BOWLED!", col=RED, out=True, kind="bowled", wait=1.9)
#         return R(txt="WIDE! +1", col=YEL, runs=1, wide=True, kind="dot")
#     dt, pw, tilt = sw
#     if abs(dt) > win:
#         if b["on"]: return R(txt="MISSED... BOWLED!", col=RED, out=True, kind="bowled", wait=1.9)
#         return R(txt="SWING & MISS!", col=(255, 160, 60), kind="dot")
#     q = 1 - abs(dt) / win
#     dirn = clamp(clamp(dt / .2, -1, 1) * .8 + clamp(tilt / 3000, -1, 1) * .3, -1, 1)
#     tx = CX + dirn * 620

#     def hit(runs, txt, col=WHT):
#         ty, arc, dur = {6: (190, 260, 1.5), 4: (305, 25, .9), 2: (400, 60, 1.1), 1: (470, 50, 1.0), 0: (560, 30, .8)}[runs]
#         return R(txt=txt, col=col, runs=runs, kind="hit", wait=dur + .9, fl=dict(x0=bx, y0=by, x1=tx, y1=ty, arc=arc, dur=dur))

#     def caught(txt):
#         f = min(FIELDERS, key=lambda f: abs(f[0] - tx))
#         return R(txt=txt, col=RED, out=True, kind="hit", wait=2.3, fl=dict(x0=bx, y0=by, x1=f[0], y1=f[1] - int(185 * f[2]), arc=170, dur=1.3))

#     if not b["on"]:
#         if random.random() < .3: return caught("EDGED! CAUGHT BEHIND!")
#         return hit(1, "EDGED! 1 RUN", YEL) if q > .5 else hit(0, "NO RUN")
#     if q > .7:
#         if pw > .65: return hit(6, "SIXXXER!!", (255, 120, 255))
#         return hit(4, "FOUR!", GRN) if pw > .35 else hit(2, "GENTLE TAP - 2 RUNS", YEL)
#     if q > .45:
#         if pw > .7: return hit(4, "FOUR!", GRN)
#         return hit(2, "2 RUNS", YEL) if pw > .35 else hit(1, "1 RUN", YEL)
#     if q > .2:
#         if pw > .5 and random.random() < .5: return caught("CAUGHT!")
#         return hit(1, "EDGE! 1 RUN", YEL)
#     return caught("TOP EDGE! CAUGHT!") if random.random() < .4 else hit(0, "MISTIMED!")


# # ----------------------------------------------------------------- main
# def main():
#     ap = argparse.ArgumentParser()
#     ap.add_argument("--ble", action="store_true"); ap.add_argument("--usb", action="store_true")
#     ap.add_argument("--port"); ap.add_argument("--name", default="")
#     a = ap.parse_args()
#     bat = Bat("ble" if a.ble else "usb" if a.usb else "auto", a.port, a.name)

#     pygame.mixer.pre_init(44100, -16, 2, 512); pygame.init()
#     scr = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
#     pygame.display.set_caption("Cluck Cricket - micro:bit bat")
#     clock = pygame.time.Clock()
#     F = [pygame.font.SysFont("arial", s, bold=True) for s in (22, 34, 64)]
#     FT = pygame.font.SysFont("impact,arialblack,arial", 104)
#     FS = pygame.font.SysFont("arial", 16, bold=True)
#     S = make_sounds(); play = lambda k: S[k] and S[k].play()
#     bg, cv = make_bg(F[0]), pygame.Surface((W, H))
#     fsurf = pygame.Surface((W, H), pygame.SRCALPHA)
#     rnd = random.Random(3)
#     crowd = [(x + rnd.randint(-4, 4), y, rnd.choice([(230, 80, 80), (80, 140, 230), (240, 200, 60), (240, 240, 240), (120, 200, 120)]))
#              for y in range(236, 296, 14) for x in range(8, W, 14)]
#     crowd += [(x + rnd.randint(-4, 4), y, rnd.choice([(230, 80, 80), (80, 140, 230), (240, 200, 60), (240, 240, 240), (120, 200, 120)]))
#               for y in range(172, 232, 14) for x in range(8, W, 14) if abs(x - CX) > 170]
#     clouds = [[rnd.randint(0, W), rnd.randint(30, 90), rnd.randint(50, 90)] for _ in range(4)]

#     def txt(f, s, pos, col=WHT, an="center", surf=None, font=None):
#         fo = font or F[f]; img = fo.render(s, True, col); r = img.get_rect(); setattr(r, an, pos)
#         (surf or scr).blit(fo.render(s, True, (0, 0, 0)), r.move(3, 3)); (surf or scr).blit(img, r)

#     def popup(f, s, pos, col, age):
#         sc = 1 + .6 * max(0, 1 - age * 4)
#         for c, o in (((0, 0, 0), 4), (col, 0)):
#             z = pygame.transform.rotozoom(F[f].render(s, True, c), 0, sc); scr.blit(z, z.get_rect(center=(pos[0] + o, pos[1] + o)))

#     def best_read():
#         try:
#             with open(HS_FILE) as f: return int(f.read())
#         except Exception: return 0

#     cfg = load_cfg()
#     t_init = clk()
#     G = dict(st="MENU", lvl=cfg.get("lvl", 2) if cfg.get("lvl") in LEVELS else 2, score=0, wk=0, played=0, hist=[], t_st=t_init,
#              ph="intro", t_ph=t_init, b=None, res=None, fl=None, t_fl=0, anim=-9, excite=0.,
#              off=clamp(float(cfg.get("off", 0.0)), -.5, .5), best=best_read(), won=False, shake=0., trail=[],
#              fours=0, sixes=0, assist=bool(cfg.get("assist", True)), newbest=False,
#              pause=False, pt=0.0, last_real=t_init, last_sw=-9., errs=[], perfect=0, flash=[(255, 255, 255), 0], cal=None)
#     parts = []
#     gt = lambda: clk() - G["pt"]                    # game clock (frozen while paused)

#     def burst(x, y, n, cols, spd=7, grav=.25):
#         for _ in range(n):
#             parts.append([x, y, random.uniform(-spd, spd), random.uniform(-spd * 1.3, spd * .3), 1., random.choice(cols), grav])

#     def start():
#         T0 = LEVELS[G["lvl"]][2]; n = gt()
#         G.update(st="PLAY", score=0, wk=0, played=0, hist=[], ph="intro", t_ph=n, res=None, fl=None, won=False,
#                  fours=0, sixes=0, newbest=False, trail=[], errs=[], perfect=0, pause=False)
#         G["b"] = new_ball(T0); play("beep")

#     def cal_start():
#         G.update(st="CAL", cal=dict(t0=gt() + 2.0, errs={}, done=None, msg=""))

#     def cal_swing(ts):
#         c = G["cal"]
#         if c["done"] is not None: return
#         k = round(ts - c["t0"])
#         if 0 <= k < 8 and abs(ts - c["t0"] - k) < .45 and k not in c["errs"]:
#             c["errs"][k] = ts - c["t0"] - k            # + = late, - = early

#     while True:
#         real = clk()
#         if G["pause"]: G["pt"] += real - G["last_real"]
#         G["last_real"] = real
#         now = real - G["pt"]; swings = []
#         name, target, T0, WIN = LEVELS[G["lvl"]]; b = G["b"]
#         for e in pygame.event.get():
#             if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE): pygame.quit(); sys.exit()
#             if e.type == pygame.KEYDOWN:
#                 if e.key == pygame.K_SPACE:
#                     kp = pygame.key.get_pressed()
#                     swings.append((now, 3800 if e.mod & pygame.KMOD_SHIFT else 2600, (int(kp[pygame.K_RIGHT]) - int(kp[pygame.K_LEFT])) * 2500, "kb"))
#                 elif e.key in (pygame.K_1, pygame.K_2, pygame.K_3) and G["st"] == "MENU": G["lvl"] = e.key - pygame.K_0; save_cfg(G)
#                 elif e.key == pygame.K_COMMA: G["off"] = round(G["off"] - .01, 3); save_cfg(G)
#                 elif e.key == pygame.K_PERIOD: G["off"] = round(G["off"] + .01, 3); save_cfg(G)
#                 elif e.key == pygame.K_h: G["assist"] = not G["assist"]; save_cfg(G)
#                 elif e.key == pygame.K_p and G["st"] == "PLAY": G["pause"] = not G["pause"]
#                 elif e.key == pygame.K_c:
#                     if G["st"] == "MENU": cal_start()
#                     elif G["st"] == "CAL": G["st"] = "MENU"
#                 elif e.key == pygame.K_F11: pygame.display.toggle_fullscreen()
#         while not bat.q.empty():
#             t, mag, tilt = bat.q.get(); swings.append((t + G["off"] - G["pt"], mag, tilt, "bat"))
#         if G["pause"]: swings = []

#         for ts, mag, tilt, src in swings:
#             if ts - G["last_sw"] < DEBOUNCE: continue
#             G["last_sw"] = ts; G["anim"] = now
#             if G["st"] == "CAL":
#                 if src == "bat": cal_swing(ts)
#                 continue
#             if G["st"] == "MENU" or (G["st"] == "END" and now - G["t_st"] > 1.5): start(); b = G["b"]; continue
#             if G["st"] == "PLAY" and G["ph"] == "bowl" and b["sw"] is None:
#                 dt = ts - (b["t0"] + b["T"])
#                 if -(WIN + .15) <= dt <= WIN + .05: b["sw"] = (dt, clamp((mag - POWER_MIN) / (POWER_MAX - POWER_MIN), 0, 1), tilt)

#         # ---------------- game logic ----------------
#         if G["st"] == "PLAY" and not G["pause"]:
#             el = now - G["t_ph"]
#             if G["ph"] == "intro" and el > 1.1: G["ph"], b["t0"] = "bowl", now
#             elif G["ph"] == "bowl":
#                 arr = b["t0"] + b["T"]
#                 if (b["sw"] and now >= arr) or (not b["sw"] and now >= arr + WIN + .08):
#                     res = judge(b, b["sw"], WIN); G.update(res=res, ph="after", t_ph=now)
#                     if b["sw"]:
#                         G["errs"].append(abs(b["sw"][0])); G["perfect"] += int(abs(b["sw"][0]) < WIN * .3)
#                     if res["fl"]: G.update(fl=res["fl"], t_fl=now)
#                     if res["kind"] == "hit": play("crack")
#                     if res["kind"] == "bowled": play("thud"); G["shake"] = 12
#                     if res["out"]: G["flash"] = [RED, 120]
#                     if res["runs"] >= 4:
#                         G["excite"] = 1.0; play("roar"); G["shake"] = 14 if res["runs"] == 6 else 6
#                         G["flash"] = [(255, 210, 60), 110] if res["runs"] == 6 else [(90, 230, 130), 70]
#                         G["sixes" if res["runs"] == 6 else "fours"] += 1
#                         if res["runs"] == 6: burst(CX, 200, 70, [(255, 200, 40), (255, 120, 255), (120, 255, 200), WHT], 9)
#                     if not res["wide"]: G["played"] += 1
#                     G["score"] += res["runs"]; G["wk"] += int(res["out"])
#                     G["hist"].append("Wd" if res["wide"] else "W" if res["out"] else str(res["runs"]) if res["runs"] else ".")
#             elif G["ph"] == "after" and el > G["res"]["wait"]:
#                 G["fl"] = None
#                 if G["score"] >= target or G["wk"] >= WICKETS or G["played"] >= BALLS:
#                     G.update(st="END", t_st=now, won=G["score"] >= target)
#                     if G["score"] > G["best"]:
#                         G["best"], G["newbest"] = G["score"], True
#                         try:
#                             with open(HS_FILE, "w") as f: f.write(str(G["best"]))
#                         except Exception: pass
#                     play("roar" if G["won"] else "thud")
#                     if G["won"]: burst(CX, 160, 160, [(255, 200, 40), (255, 90, 160), (90, 220, 255), (140, 255, 140)], 11, .18)
#                 else:
#                     G.update(ph="intro", t_ph=now, trail=[]); G["b"] = new_ball(T0); b = G["b"]
#             G["excite"] = max(0, G["excite"] - .012)
#         elif G["st"] == "CAL":
#             c = G["cal"]
#             if c["done"] is None and now > c["t0"] + 8.3:
#                 vals = [v for k, v in sorted(c["errs"].items()) if k >= 2]          # first 2 beats = practice
#                 if len(vals) >= 3:
#                     G["off"] = round(clamp(G["off"] - statistics.median(vals), -.5, .5), 3)
#                     c["msg"] = f"Done!  Timing offset is now {G['off'] * 1000:+.0f} ms"; save_cfg(G)
#                 else:
#                     c["msg"] = "Not enough bat swings detected - try again (press C)"
#                 c["done"] = now
#             elif c["done"] is not None and now - c["done"] > 2.6: G["st"] = "MENU"

#         # ---------------- scene (shakes) ----------------
#         cv.blit(bg, (0, 0))
#         for c in clouds:
#             c[0] = (c[0] + .3) % (W + 200); pygame.draw.ellipse(cv, (255, 255, 255), (c[0] - 100, c[1], c[2] * 2, c[2] // 2))
#         for i, (x, y, col) in enumerate(crowd):
#             pygame.draw.circle(cv, col, (x, int(y + 1.5 * math.sin(now * 2 + x * .05) - G["excite"] * 9 * abs(math.sin(now * 9 + i)))), 6)
#         for fx, fy, fk, fc in sorted(FIELDERS, key=lambda f: f[1]): person(cv, fx, fy, fk, fc)
#         person(cv, CX - 75, 266, .3, (245, 245, 245), hat=True)                       # umpire
#         ph, el, res = G["ph"], now - G["t_ph"], G["res"]
#         arm = (min(el, 1) if ph == "intro" else max(0, 1 - el / .3) if ph == "bowl" else 0) if G["st"] == "PLAY" else 0
#         person(cv, CX, 262, .32, (255, 200, 40), chicken=True, arm=arm)

#         broke = min(el / .5, 1) if (G["st"] == "PLAY" and ph == "after" and res and res["kind"] == "bowled") else 0
#         pygame.draw.ellipse(cv, (25, 85, 35), (CX - 34, 606, 68, 12))
#         for i, lean in enumerate((-.6, .2, .9)):
#             bx0 = CX - 14 + i * 14; ang = lean * broke
#             pygame.draw.line(cv, (250, 240, 200), (bx0, 612), (bx0 + math.sin(ang) * 85, 612 - math.cos(ang) * 85), 6)
#         for dx in (-7, 7):
#             by_ = 526 - 180 * broke * (1 - broke) - 60 * broke
#             pygame.draw.line(cv, (200, 60, 60), (CX + dx - 6 + 30 * broke * dx / 7, by_), (CX + dx + 6 + 30 * broke * dx / 7, by_), 4)

#         def draw_ball(x, y, r, gy=None):
#             tr = G["trail"]
#             if not G["pause"]: tr.append((x, y, r)); del tr[:-10]
#             for i, (tx_, ty_, tr_) in enumerate(tr[:-1]):
#                 pygame.draw.circle(cv, (190, 50, 60), (int(tx_), int(ty_)), max(1, int(tr_ * (.25 + .6 * i / 10))))
#             if gy is not None: pygame.draw.ellipse(cv, (30, 90, 40), (x - r, gy - r // 3, 2 * r, max(2, int(r * .7))))
#             pygame.draw.circle(cv, (215, 30, 40), (int(x), int(y)), int(r)); pygame.draw.circle(cv, WHT, (int(x), int(y)), int(r), 2)
#             pygame.draw.arc(cv, WHT, (int(x - r * .6), int(y - r * .6), int(r * 1.2), int(r * 1.2)), 0.5, 2.2, 1)

#         if G["st"] == "PLAY" and ph == "bowl":
#             t = (now - b["t0"]) / b["T"]
#             if G["assist"]:
#                 ax, ay = ball_pos(b, 1)[:2]; inwin = abs(now - (b["t0"] + b["T"])) <= WIN
#                 leave = G["lvl"] == 1 and not b["on"]                     # EASY level: warn about wide balls
#                 pygame.draw.circle(cv, RED if leave else GRN if inwin else (255, 255, 255), (int(ax), int(ay)), int(32 + 4 * math.sin(now * 10)), 3)
#                 if leave: txt(1, "LEAVE IT!", (int(ax), int(ay) - 52), RED, surf=cv)
#                 elif inwin: txt(1, "SWING!", (int(ax), int(ay) - 52), GRN, surf=cv)
#             if t <= 1.12: x, y, gy, r = ball_pos(b, t); draw_ball(x, y, r, gy)
#         elif G["st"] == "PLAY" and ph == "after" and res and res["kind"] == "bowled" and el < .35:
#             x, y, gy, r = ball_pos(b, 1); draw_ball(x, y, r)

#         u = (now - G["anim"]) / .28
#         ang = 115 - 200 * u if 0 <= u <= 1 else -85 if 1 < u < 1.8 else 115
#         person(cv, CX - 110, 655, 1.0, (40, 90, 220), face=False, bat=ang, helmet=True, pads=True)

#         if G["fl"]:
#             f = G["fl"]; uu = clamp((now - G["t_fl"]) / f["dur"], 0, 1)
#             x = lerp(f["x0"], f["x1"], uu); gy = lerp(f["y0"], f["y1"], uu)
#             y = gy - f["arc"] * math.sin(math.pi * uu); r = int(5 + 13 * clamp((gy - 180) / 400, 0, 1))
#             if not (res["runs"] == 6 and uu >= 1): draw_ball(x, y, r, gy)

#         sh = int(G["shake"]); G["shake"] = max(0, G["shake"] - .8) if not G["pause"] else G["shake"]
#         scr.blit(cv, (random.randint(-sh, sh), random.randint(-sh, sh)) if sh else (0, 0))

#         if G["flash"][1] > 0:                                           # screen flash on wicket / four / six
#             fsurf.fill((*G["flash"][0], int(G["flash"][1]))); scr.blit(fsurf, (0, 0))
#             if not G["pause"]: G["flash"][1] = max(0, G["flash"][1] - 5)

#         for p in parts[:]:                                           # particles / confetti
#             if not G["pause"]: p[0] += p[2]; p[1] += p[3]; p[3] += p[6]; p[4] -= .012
#             if p[4] <= 0 or p[1] > H + 20: parts.remove(p)
#             else: pygame.draw.rect(scr, p[5], (int(p[0]), int(p[1]), 9, 6))

#         # ---------------- timing bar + popups ----------------
#         def draw_meter(ball_dt, sw_dt, pw):
#             mx, sc = CX + 250, 215 / MR
#             rr(scr, (mx - 235, H - 150, 470, 104), (10, 15, 40), 16, 200)
#             pygame.draw.rect(scr, (50, 55, 80), (mx - 215, H - 120, 430, 18), border_radius=4)
#             for fr, col in ZONES:
#                 w = 2 * fr * WIN * sc; pygame.draw.rect(scr, col, (mx - w / 2, H - 120, w, 18))
#             pygame.draw.line(scr, WHT, (mx, H - 124), (mx, H - 98), 2)
#             if ball_dt is not None:
#                 bx = int(mx + clamp(ball_dt, -MR, MR) * sc)
#                 pygame.draw.circle(scr, (215, 30, 40), (bx, H - 111), 10); pygame.draw.circle(scr, WHT, (bx, H - 111), 10, 2)
#             if sw_dt is not None:
#                 pm = mx + clamp(sw_dt, -MR, MR) * sc
#                 pygame.draw.polygon(scr, WHT, [(pm, H - 123), (pm - 9, H - 139), (pm + 9, H - 139)])
#             txt(0, "EARLY", (mx - 225, H - 92), (200, 200, 220), "midleft", font=FS); txt(0, "LATE", (mx + 225, H - 92), (200, 200, 220), "midright", font=FS)
#             if sw_dt is None: txt(0, "swing when the ball hits the green", (mx, H - 92), (200, 210, 230), font=FS)
#             else:
#                 lbl = "PERFECT" if abs(sw_dt) < WIN * .3 else "EARLY" if sw_dt < 0 else "LATE"
#                 txt(0, f"{lbl}  {sw_dt * 1000:+.0f} ms", (mx, H - 92), YEL if abs(sw_dt) < WIN * .55 else (255, 150, 90), font=FS)
#             if pw is not None:
#                 txt(0, "POWER", (mx - 225, H - 66), WHT, "midleft", font=FS)
#                 pygame.draw.rect(scr, (60, 60, 80), (mx - 150, H - 74, 370, 16), border_radius=8)
#                 pygame.draw.rect(scr, (255, 120, 60), (mx - 150, H - 74, int(370 * pw), 16), border_radius=8)

#         if G["st"] == "PLAY" and ph == "bowl":
#             draw_meter(now - (b["t0"] + b["T"]), b["sw"][0] if b["sw"] else None, None)
#         elif G["st"] == "PLAY" and ph == "after" and res:
#             popup(2, res["txt"], (CX, 128), res["col"], el)
#             if b["sw"]: draw_meter(None, b["sw"][0], b["sw"][1])
#         elif G["st"] == "PLAY" and ph == "intro":
#             tag = {"fast": "FAST ball incoming!", "slow": "SLOW ball - wait for it!", "swing": "SWINGER - watch the curve!"}.get(b["kind"], "get ready!")
#             txt(1, f"Ball {G['played'] + 1} of {BALLS} - {tag}", (CX, 128))

#         # ---------------- HUD ----------------
#         if G["st"] in ("PLAY", "END"):
#             rr(scr, (12, 10, 300, 66), (10, 15, 40), 16, 200, (255, 200, 60))
#             txt(0, "SCORE", (28, 28), (255, 200, 60), "midleft", font=FS); txt(2, f"{G['score']}/{G['wk']}", (28, 54), WHT, "midleft", font=F[1])
#             rr(scr, (CX - 190, 10, 380, 66), (10, 15, 40), 16, 200, (90, 160, 255))
#             txt(1, f"TARGET {target}  -  {name}", (CX, 30))
#             need, left = target - G["score"], BALLS - G["played"]
#             txt(0, (f"Need {need} from {left} balls  (RRR {need / left:.1f})" if left > 0 else f"Need {need}") if need > 0 else "TARGET REACHED!", (CX, 58), GRN, font=FS)
#             rr(scr, (W - 312, 10, 300, 66), (10, 15, 40), 16, 200, (255, 120, 120))
#             for i in range(BALLS): pygame.draw.circle(scr, (110, 110, 130) if i < G["played"] else (230, 60, 70), (W - 296 + i * 24, 30), 8)
#             txt(0, "WKTS", (W - 300, 58), (255, 150, 150), "midleft", font=FS)
#             for i in range(WICKETS):
#                 alive = i >= G["wk"]
#                 for j in range(3): pygame.draw.line(scr, WHT if alive else (120, 70, 70), (W - 232 + i * 40 + j * 7, 48), (W - 232 + i * 40 + j * 7, 68), 3)
#                 if not alive: pygame.draw.line(scr, RED, (W - 236 + i * 40, 46), (W - 214 + i * 40, 70), 4)
#             for i, hs in enumerate(G["hist"][-7:]):
#                 c = RED if hs == "W" else GRN if hs in ("4", "6") else (230, 230, 230)
#                 pygame.draw.circle(scr, c, (32 + i * 38, 106), 16); pygame.draw.circle(scr, (0, 0, 0), (32 + i * 38, 106), 16, 2)
#                 txt(0, hs, (32 + i * 38, 106), (0, 0, 0), font=FS)
#         kind, text, src = bat.info()
#         pc = {"ok": (90, 230, 130), "search": (255, 200, 70), "kb": (170, 170, 190)}[kind]
#         wpx = FS.size(text)[0] + 70
#         rr(scr, (12, H - 40, wpx, 30), (10, 15, 40), 15, 210, pc)
#         pygame.draw.circle(scr, pc, (30, H - 25), 6 if kind == "search" and int(now * 3) % 2 else 8)
#         bt_icon(scr, 52, H - 25, pc, .8) if src == "ble" else None
#         txt(0, text, (68, H - 25), WHT, "midleft", font=FS)
#         txt(0, f"offset {G['off'] * 1000:+.0f} ms (, .)   assist {'ON' if G['assist'] else 'OFF'} (H)   pause P   fullscreen F11", (W - 12, H - 25), (225, 225, 240), "midright", font=FS)

#         # ---------------- menu / calibration / end / pause ----------------
#         if G["st"] == "MENU":
#             ov = pygame.Surface((W, H), pygame.SRCALPHA); ov.fill((5, 10, 35, 175)); scr.blit(ov, (0, 0))
#             txt(0, "CLUCK CRICKET", (CX, 86 + int(4 * math.sin(now * 3))), YEL, surf=scr, font=FT)
#             txt(1, "micro:bit Bluetooth Bat Challenge", (CX, 160), (190, 220, 255))
#             rr(scr, (CX - 340, 205, 680, 84), (15, 25, 60), 18, 235, pc, 3)
#             pygame.draw.circle(scr, pc, (CX - 304, 247), 10 if kind != "search" or int(now * 3) % 2 else 6)
#             if src == "ble": bt_icon(scr, CX - 270, 247, pc, 1.3)
#             txt(1, text, (CX - 245, 232), WHT, "midleft")
#             txt(0, "Switch the bat on - or press SPACE to play with the keyboard" if kind != "ok" else "Bat ready! Swing it to start", (CX - 245, 268), (200, 210, 230), "midleft", font=FS)
#             for i in (1, 2, 3):
#                 sel = G["lvl"] == i; x0 = CX - 345 + (i - 1) * 235
#                 rr(scr, (x0, 312 - 6 * sel, 220, 92 + 12 * sel), (30, 60, 130) if sel else (20, 30, 70), 16, 240, YEL if sel else (80, 100, 160), 4 if sel else 2)
#                 txt(1, LEVELS[i][0], (x0 + 110, 336 - 6 * sel), YEL if sel else WHT)
#                 txt(0, f"Target {LEVELS[i][1]}  [{i}]", (x0 + 110, 368 - 6 * sel), (200, 215, 240), font=FS)
#                 txt(0, f"timing window +/-{int(LEVELS[i][3] * 1000)} ms", (x0 + 110, 388 - 6 * sel), (160, 180, 220), font=FS)
#             for i, (a1, a2) in enumerate((("TIMING", "early = leg,  late = off side"), ("POWER", "harder swing = more runs"), ("WIDE BALL?", "leave it alone! (+1 run)"))):
#                 x0 = CX - 345 + i * 235
#                 rr(scr, (x0, 432, 220, 74), (20, 30, 70), 14, 220, (80, 100, 160)); txt(0, a1, (x0 + 110, 457), YEL, font=FS); txt(0, a2, (x0 + 110, 484), WHT, font=FS)
#             txt(0, f"Best score: {G['best']}", (CX, 540), (200, 220, 255), font=F[0])
#             pill = pygame.Rect(CX - 210, 575, 420, 64); rr(scr, pill, (255, 150, 40) if int(now * 2) % 2 else (240, 110, 30), 32, 255, WHT, 3)
#             txt(1, "SWING TO START", pill.center)
#             txt(0, "Bat feels late or early?  Press C to calibrate", (CX, 662), (170, 230, 255), font=FS)
#         elif G["st"] == "CAL":
#             c = G["cal"]
#             ov = pygame.Surface((W, H), pygame.SRCALPHA); ov.fill((5, 10, 35, 215)); scr.blit(ov, (0, 0))
#             txt(2, "CALIBRATION", (CX, 110), YEL)
#             if c["done"] is None:
#                 txt(1, "Swing the bat the moment the ball crosses the ring", (CX, 190))
#                 txt(0, "8 beats - the first 2 are practice.  Use the BAT (not the keyboard).  Press C to cancel.", (CX, 225), (200, 210, 230), font=FS)
#                 w = ((now - c["t0"] + .5) % 1.0) - .5
#                 pygame.draw.line(scr, (80, 100, 160), (CX - 320, 360), (CX + 320, 360), 4)
#                 flash = abs(w) < .06 and now > c["t0"] - .1
#                 pygame.draw.circle(scr, GRN if flash else WHT, (CX, 360), 44, 0 if flash else 4)
#                 bxp = int(CX + w * 640)
#                 pygame.draw.circle(scr, (215, 30, 40), (bxp, 360), 20); pygame.draw.circle(scr, WHT, (bxp, 360), 20, 3)
#                 if now < c["t0"]: txt(1, "Get ready...", (CX, 450), YEL)
#                 else:
#                     for k in range(8):
#                         x0, e = CX - 210 + k * 60, c["errs"].get(k)
#                         pygame.draw.circle(scr, GRN if e is not None else (110, 110, 130), (x0, 450), 14 if k >= 2 else 9)
#                         if e is not None: txt(0, f"{e * 1000:+.0f}", (x0, 485), (200, 220, 255), font=FS)
#             else:
#                 txt(1, c["msg"], (CX, 330), GRN if "Done" in c["msg"] else RED)
#         elif G["st"] == "END":
#             ov = pygame.Surface((W, H), pygame.SRCALPHA); ov.fill((5, 10, 35, 185)); scr.blit(ov, (0, 0))
#             rr(scr, (CX - 340, 100, 680, 480), (18, 28, 70), 26, 240, YEL if G["won"] else (200, 90, 90), 4)
#             txt(2, "YOU WIN!" if G["won"] else "INNINGS OVER", (CX, 165), GRN if G["won"] else RED)
#             stars = (3 if G["wk"] <= 1 else 2) if G["won"] else (1 if G["score"] >= target * .6 else 0)
#             for i in range(3):
#                 cy_ = 255 - (14 if i == 1 else 0)
#                 star(scr, CX - 110 + i * 110, cy_, 44, (255, 210, 50) if i < stars else (90, 100, 130), i < stars)
#             txt(2, f"{G['score']}/{G['wk']}", (CX, 345), WHT); txt(0, f"target {target}  -  {name}", (CX, 390), (190, 210, 240))
#             txt(0, f"Fours: {G['fours']}     Sixes: {G['sixes']}     Best: {G['best']}", (CX, 430), YEL)
#             avg = f"{sum(G['errs']) / len(G['errs']) * 1000:.0f} ms" if G["errs"] else "-"
#             txt(0, f"Avg timing error: {avg}     Perfect hits: {G['perfect']}", (CX, 465), (190, 230, 255))
#             if G["newbest"]: txt(1, "NEW BEST!", (CX, 505), (255, 120, 255))
#             txt(1, "Swing to play again", (CX, 545), WHT if int(now * 2) % 2 else YEL)
#         if G["pause"]:
#             ov = pygame.Surface((W, H), pygame.SRCALPHA); ov.fill((5, 10, 35, 170)); scr.blit(ov, (0, 0))
#             txt(2, "PAUSED", (CX, 330), YEL); txt(1, "press P to resume", (CX, 400), WHT)

#         pygame.display.flip(); clock.tick(60)


# if __name__ == "__main__":
#     main()
"""
CLUCK CRICKET v3 - Bluetooth micro:bit bat  (Python + Pygame)

Install:  pip install pygame numpy bleak pyserial
Run:      python cluck_cricket_ble.py            (Bluetooth + USB are both tried automatically)
          python cluck_cricket_ble.py --ble      (Bluetooth only)
          python cluck_cricket_ble.py --usb --port COM5   (USB cable only)
          python cluck_cricket_ble.py --name tizip        (connect to the bat named "BBC micro:bit [tizip]")

Bat: flash microbit_bat_ble.ts (MakeCode) for Bluetooth, or microbit_bat.py (USB cable).
     Bat line format:  SWING,<peak_mg>,<tilt>[,<micro:bit millis>]
     The 4th field is OPTIONAL. If the bat sends control.millis(), the game removes Bluetooth jitter
     (clock-sync) and timing becomes much more accurate.

Keys:  SPACE = shot (SHIFT = power shot, hold LEFT/RIGHT = tilt)   1/2/3 = level (menu)
       C = calibrate bat timing (menu)    P = pause    , and . = offset -/+10 ms
       H = timing assist on/off           F11 = fullscreen     ESC = quit

What's new in v3
  * Accuracy: monotonic clock, Bluetooth clock-sync, swing de-bounce, one-tap bat CALIBRATION,
    per-level timing windows, offset/assist/level saved between runs.
  * UI: live timing bar (watch the ball slide into the green zone), exact early/late in ms,
    ball-type warnings, screen flashes, pause, required run-rate, accuracy stats on the end screen.
"""
import sys, os, time, math, random, threading, queue, asyncio, argparse, json, statistics
import numpy as np
import pygame

clk = time.perf_counter                    # monotonic, high-resolution clock (time.time() can jump)
W, H, CX = 1280, 720, 640
BALLS, WICKETS = 12, 3
LEVELS = {1: ("EASY", 20, 2.0, .32), 2: ("MEDIUM", 30, 1.6, .28), 3: ("HARD", 40, 1.25, .22)}  # name, target, ball time, hit window (s)
POWER_MIN, POWER_MAX = 1200, 3800      # peak swing acceleration (mg) -> power 0..1
MR = .60                               # timing-bar range (+/- seconds)
DEBOUNCE = .25                         # ignore a 2nd swing trigger within this time (back-swing)
BASE = os.path.dirname(os.path.abspath(__file__))
HS_FILE, CFG_FILE = os.path.join(BASE, "cricket_highscore.txt"), os.path.join(BASE, "cricket_settings.json")
NUS_TX = "6e400003-b5a0-f393-e0a9-e50e24dcca9e"     # Nordic UART (micro:bit -> PC)
FIELDERS = [(200, 360, .30, (220, 60, 60)), (1080, 360, .30, (60, 120, 220)), (CX - 300, 335, .26, (240, 170, 40)),
            (CX + 300, 335, .26, (160, 80, 200)), (130, 480, .38, (60, 180, 90)), (1150, 480, .38, (230, 90, 160))]
RED, YEL, WHT, GRN = (255, 70, 70), (255, 220, 60), (255, 255, 255), (110, 240, 150)
ZONES = ((1.0, (230, 90, 60)), (.8, (240, 160, 60)), (.55, (240, 215, 70)), (.3, (90, 220, 120)))   # fraction of window, colour
lerp = lambda a, b, t: a + (b - a) * t
clamp = lambda v, lo, hi: max(lo, min(hi, v))


# ----------------------------------------------------------------- bat input (Bluetooth + USB)
class Bat:
    def __init__(self, mode="auto", port=None, name=""):
        self.q, self.s, self.name, self.sync = queue.Queue(), {}, name.lower(), []
        if mode in ("auto", "usb"): self._usb(port)
        if mode in ("auto", "ble"): self._ble()

    def set(self, src, kind, text): self.s[src] = (kind, text)

    def info(self):                                  # -> (kind, text, source)
        for k in ("ok", "search", "kb"):
            for src, (kind, text) in self.s.items():
                if kind == k: return kind, text, src
        return "kb", "Keyboard mode - SPACE / SHIFT+SPACE", "kb"

    def feed(self, line):
        if not line.startswith("SWING"): return
        rx = clk()
        try:
            p = line.split(",")
            mag = int(p[1]); tilt = int(p[2]) if len(p) > 2 else 0
            ms = int(p[3]) / 1000 if len(p) > 3 else None
        except (ValueError, IndexError):
            return
        t = rx
        if ms is not None:                     # clock-sync: the fastest packet ~ true latency, remove the jitter above it
            off = rx - ms
            if self.sync and abs(off - min(self.sync)) > 2: self.sync.clear()      # bat was reset
            self.sync.append(off); del self.sync[:-60]
            t = ms + min(self.sync)
        self.q.put((t, mag, tilt))

    def _ble(self):
        try:
            import bleak
        except ImportError:
            self.set("ble", "kb", "Bluetooth needs:  pip install bleak"); return
        self.set("ble", "search", "Bluetooth: searching for the bat...")
        threading.Thread(target=lambda: asyncio.run(self._ble_loop()), daemon=True).start()

    async def _ble_loop(self):
        from bleak import BleakScanner, BleakClient
        match = lambda d, ad: "micro:bit" in (d.name or ad.local_name or "").lower() and self.name in (d.name or ad.local_name or "").lower()
        while True:
            try:
                self.set("ble", "search", "Bluetooth: searching for the bat...")
                dev = await BleakScanner.find_device_by_filter(match, timeout=10)
                if not dev: continue
                self.set("ble", "search", f"Bluetooth: connecting to {dev.name}...")
                loop, gone, buf = asyncio.get_running_loop(), asyncio.Event(), [""]

                def on_data(_, data):
                    buf[0] += data.decode(errors="ignore")
                    while "\n" in buf[0]:
                        line, buf[0] = buf[0].split("\n", 1); self.feed(line.strip())

                cb = lambda c: loop.call_soon_threadsafe(gone.set)
                try:       # Windows: ignore stale cached services from an older program on the micro:bit
                    client = BleakClient(dev, disconnected_callback=cb, winrt=dict(use_cached_services=False))
                except TypeError:
                    client = BleakClient(dev, disconnected_callback=cb)
                async with client as c:
                    svc = next((sv for sv in c.services if sv.uuid.lower().startswith("6e400001")), None)
                    if not svc: raise RuntimeError("UART missing: re-flash .ts")
                    ch = next((x for x in svc.characteristics if "notify" in x.properties or "indicate" in x.properties), None)
                    if not ch: raise RuntimeError("UART has no notify channel")
                    self.sync.clear()
                    await c.start_notify(ch, on_data)       # micro:bit sends via ...0002 (indicate)
                    self.set("ble", "ok", f"Bluetooth connected: {dev.name}")
                    await gone.wait()
                self.set("ble", "search", "Bluetooth: bat disconnected, searching...")
            except Exception as e:                      # show the real reason on screen + console
                import traceback; traceback.print_exc()
                self.set("ble", "search", f"BT error: {type(e).__name__} {str(e)[:30]}")
                await asyncio.sleep(2)

    def _usb(self, port):
        try:
            import serial
            from serial.tools import list_ports
        except ImportError:
            return
        if not port:
            for p in list_ports.comports():
                d = (p.description or "").lower()
                if p.vid == 0x0D28 or "micro:bit" in d or "mbed" in d: port = p.device; break
        if port:
            self.set("usb", "search", f"USB: opening {port}...")
            threading.Thread(target=self._usb_loop, args=(serial, port), daemon=True).start()

    def _usb_loop(self, serial, port):
        while True:
            try:
                with serial.Serial(port, 115200, timeout=1) as s:
                    self.sync.clear()
                    self.set("usb", "ok", f"USB cable connected ({port})")
                    while True: self.feed(s.readline().decode(errors="ignore").strip())
            except Exception:
                self.set("usb", "search", "USB: reconnecting..."); time.sleep(1)


# ----------------------------------------------------------------- settings
def load_cfg():
    try:
        with open(CFG_FILE) as f: return json.load(f)
    except Exception:
        return {}


def save_cfg(G):
    try:
        with open(CFG_FILE, "w") as f: json.dump(dict(off=G["off"], assist=G["assist"], lvl=G["lvl"]), f)
    except Exception:
        pass


# ----------------------------------------------------------------- sounds + drawing helpers
def mk(arr):
    try:
        a = (np.clip(arr, -1, 1) * 12000).astype(np.int16)
        return pygame.sndarray.make_sound(np.column_stack([a, a]))
    except Exception:
        return None


def make_sounds():
    sr = 44100
    t = np.arange(int(sr * .12)) / sr; t2 = np.arange(sr) / sr; t3 = np.arange(int(sr * .35)) / sr; t4 = np.arange(int(sr * .2)) / sr
    roar = np.convolve(np.random.uniform(-1, 1, t2.size), np.ones(40) / 40, "same") * np.minimum(t2 * 6, 1) * np.exp(-t2 * 2.2) * 2.5
    return dict(crack=mk(np.random.uniform(-1, 1, t.size) * np.exp(-t * 45)), roar=mk(roar),
                thud=mk(np.sin(2 * np.pi * 90 * t3) * np.exp(-t3 * 9)), beep=mk(np.sin(2 * np.pi * 660 * t4) * np.exp(-t4 * 8)))


def rr(s, rect, col, rad=14, alpha=255, border=None, bw=2):
    r = pygame.Rect(rect); t = pygame.Surface(r.size, pygame.SRCALPHA)
    pygame.draw.rect(t, (*col, alpha), t.get_rect(), border_radius=rad)
    if border: pygame.draw.rect(t, (*border, 255), t.get_rect(), bw, border_radius=rad)
    s.blit(t, r.topleft)


_pc = {}


def panel(s, rect, accent, alpha=222, rad=16, hi=0):
    """Glossy rounded card: soft shadow, vertical gradient, accent border, top highlight (cached)."""
    r = pygame.Rect(rect); key = (r.w, r.h, accent, alpha, rad, hi)
    t = _pc.get(key)
    if t is None:
        t = pygame.Surface((r.w + 10, r.h + 12), pygame.SRCALPHA)
        pygame.draw.rect(t, (0, 0, 0, 80), (6, 8, r.w, r.h), border_radius=rad)
        body = pygame.Surface(r.size, pygame.SRCALPHA)
        for y in range(r.h):
            k = 1 - y / r.h
            pygame.draw.line(body, (min(255, int(16 + 14 * k) + hi), min(255, int(24 + 20 * k) + hi), min(255, int(54 + 34 * k) + hi * 2), alpha), (0, y), (r.w, y))
        m = pygame.Surface(r.size, pygame.SRCALPHA); pygame.draw.rect(m, (255, 255, 255, 255), m.get_rect(), border_radius=rad)
        body.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        pygame.draw.rect(body, (*accent, 255), body.get_rect(), 2, border_radius=rad)
        pygame.draw.line(body, (255, 255, 255, 45), (rad, 3), (r.w - rad, 3))
        t.blit(body, (4, 4)); _pc[key] = t
    s.blit(t, (r.x - 4, r.y - 4))


def bt_icon(s, x, y, col, sc=1.0):
    pts = [(-5, -5), (5, 5), (0, 10), (0, -10), (5, -5), (-5, 5)]
    pygame.draw.lines(s, col, False, [(x + px * sc, y + py * sc) for px, py in pts], max(2, int(2 * sc)))


def star(s, cx, cy, r, col, fill=True):
    pts = [(cx + (r if i % 2 == 0 else r * .45) * math.sin(i * math.pi / 5), cy - (r if i % 2 == 0 else r * .45) * math.cos(i * math.pi / 5)) for i in range(10)]
    if fill: pygame.draw.polygon(s, col, pts)
    else: pygame.draw.polygon(s, col, pts, 3)


def make_bg(font):
    s = pygame.Surface((W, H))
    for y in range(300):
        k = y / 300; pygame.draw.line(s, (int(80 + 120 * k), int(160 + 70 * k), 255 - int(10 * k)), (0, y), (W, y))
    pygame.draw.circle(s, (255, 250, 190), (1100, 105), 62); pygame.draw.circle(s, (255, 240, 150), (1100, 105), 40)
    pygame.draw.rect(s, (60, 62, 86), (0, 150, W, 150))
    for i, y in enumerate((150, 190, 230, 270)):                  # stand tiers
        pygame.draw.rect(s, (42, 44, 62), (0, y, W, 6)); pygame.draw.rect(s, (74, 76, 100), (0, y + 6, W, 3))
    pygame.draw.rect(s, (30, 32, 46), (0, 138, W, 14))            # roof edge
    rr(s, (CX - 150, 160, 300, 66), (15, 15, 30), 8, border=(255, 200, 60))   # big LED screen
    t = font.render("CLUCK CUP  LIVE", True, (255, 220, 70)); s.blit(t, t.get_rect(center=(CX, 193)))
    for x in (70, W - 70):                                        # floodlights
        pygame.draw.rect(s, (110, 110, 124), (x - 6, 60, 12, 240))
        pygame.draw.rect(s, (235, 235, 245), (x - 42, 28, 84, 44), border_radius=6)
        for i in range(4):
            for j in range(2): pygame.draw.circle(s, (255, 255, 200), (x - 31 + i * 21, 41 + j * 20), 7)
    for i, y in enumerate(range(300, H, 40)):
        pygame.draw.rect(s, (46, 140, 60) if i % 2 else (58, 165, 72), (0, y, W, 40))
    ads = ["PYTHON", "micro:bit", "CODE!", "PLAY!", "AI ROCKS", "BUILD IT"]
    for i in range(10):
        r = pygame.Rect(i * 128, 296, 128, 28)
        pygame.draw.rect(s, [(200, 50, 50), (40, 110, 200), (230, 170, 30), (60, 160, 80)][i % 4], r)
        img = font.render(ads[i % len(ads)], True, WHT); s.blit(img, img.get_rect(center=r.center))
    pygame.draw.polygon(s, (205, 175, 110), [(CX - 45, 252), (CX + 45, 252), (CX + 190, H), (CX - 190, H)])
    for cx_, cy_, rx, ry in ((CX, 585, 120, 50), (CX, 275, 26, 10)):          # worn patches
        w = pygame.Surface((rx * 2, ry * 2), pygame.SRCALPHA); pygame.draw.ellipse(w, (170, 140, 85, 110), w.get_rect()); s.blit(w, (cx_ - rx, cy_ - ry))
    pygame.draw.line(s, WHT, (CX - 160, 625), (CX + 160, 625), 4); pygame.draw.line(s, WHT, (CX - 55, 262), (CX + 55, 262), 2)
    for i in (-1, 0, 1): pygame.draw.line(s, (250, 240, 200), (CX + i * 5, 262), (CX + i * 5, 246), 2)
    vig = pygame.Surface((W, H), pygame.SRCALPHA)                  # vignette
    for i in range(70): pygame.draw.rect(vig, (0, 0, 0, int(110 * (1 - i / 70) ** 2)), (i, i, W - 2 * i, H - 2 * i), 1)
    s.blit(vig, (0, 0))
    return s


def person(s, x, y, k, shirt, face=True, chicken=False, bat=None, arm=0.0, helmet=False, pads=False, hat=False):
    h = lambda v: int(v * k)
    skin = (240, 190, 150); dark = tuple(int(c * .6) for c in shirt)
    pygame.draw.ellipse(s, (25, 85, 35), (x - h(42), y - h(7), h(84), h(16)))
    for dx in (-24, 4):
        pygame.draw.rect(s, (245, 245, 245), (x + h(dx), y - h(85), h(20), h(85)), border_radius=h(6))
        if pads:
            pygame.draw.rect(s, (250, 240, 205), (x + h(dx) - h(3), y - h(62), h(26), h(54)), border_radius=h(8))
            pygame.draw.rect(s, (150, 140, 110), (x + h(dx) - h(3), y - h(62), h(26), h(54)), max(1, h(2)), border_radius=h(8))
        pygame.draw.rect(s, (40, 40, 50), (x + h(dx) - h(2), y - h(8), h(24), h(9)), border_radius=h(4))
    if chicken: pygame.draw.ellipse(s, (255, 250, 235), (x - h(48), y - h(150), h(28), h(54)))
    pygame.draw.rect(s, shirt, (x - h(32), y - h(165), h(64), h(85)), border_radius=h(16))
    sh = (x + h(28), y - h(148))
    hand = (x + h(42), y - h(108)) if bat is not None else (lerp(x + h(34), x + h(14), arm), lerp(y - h(88), y - h(240), arm))
    pygame.draw.line(s, skin, sh, hand, max(2, h(13)))
    pygame.draw.circle(s, (255, 230, 90) if bat is not None else skin, hand, max(2, h(10)))
    if bat is not None:
        a = math.radians(bat); d = (math.cos(a), -math.sin(a)); L = h(125)
        p1 = (hand[0] + d[0] * L * .35, hand[1] + d[1] * L * .35); p2 = (hand[0] + d[0] * L, hand[1] + d[1] * L)
        pygame.draw.line(s, (60, 40, 30), hand, p1, max(2, h(9)))
        pygame.draw.line(s, (225, 190, 120), p1, p2, max(3, h(22)))
        pygame.draw.circle(s, (225, 190, 120), (int(p2[0]), int(p2[1])), max(2, h(11)))
        pygame.draw.circle(s, (255, 230, 90), (int(hand[0]), int(hand[1])), max(2, h(10)))
    hc = (x, y - h(192)); r = h(30)
    if chicken:
        pygame.draw.circle(s, (250, 250, 250), hc, r)
        for dx in (-10, 0, 10): pygame.draw.circle(s, (230, 40, 40), (hc[0] + h(dx), hc[1] - r), max(2, h(9)))
        pygame.draw.polygon(s, (255, 170, 30), [(hc[0] - h(8), hc[1] + h(2)), (hc[0] + h(8), hc[1] + h(2)), (hc[0], hc[1] + h(16))])
        pygame.draw.circle(s, (240, 60, 60), (hc[0], hc[1] + h(20)), max(1, h(5)))
        for dx in (-11, 11):
            pygame.draw.circle(s, WHT, (hc[0] + h(dx), hc[1] - h(6)), max(2, h(6))); pygame.draw.circle(s, (0, 0, 0), (hc[0] + h(dx), hc[1] - h(6)), max(1, h(3)))
        return
    pygame.draw.circle(s, skin if face else (70, 45, 30), hc, r)
    if face:
        for dx in (-11, 11): pygame.draw.circle(s, (0, 0, 0), (hc[0] + h(dx), hc[1] - h(2)), max(1, h(4)))
        pygame.draw.arc(s, (150, 40, 40), (hc[0] - h(12), hc[1] + h(2), h(24), h(16)), math.pi, 2 * math.pi, max(1, h(3)))
    if helmet:
        pygame.draw.ellipse(s, dark, (hc[0] - r - h(3), hc[1] - r - h(5), 2 * r + h(6), h(52)))
        pygame.draw.line(s, WHT, (hc[0], hc[1] - r - h(3)), (hc[0], hc[1] - h(2)), max(1, h(4)))
    elif hat:
        pygame.draw.ellipse(s, WHT, (hc[0] - r - h(8), hc[1] - r + h(2), 2 * r + h(16), h(14)))
        pygame.draw.ellipse(s, (235, 235, 235), (hc[0] - r + h(4), hc[1] - r - h(10), 2 * r - h(8), h(22)))
    else:
        pygame.draw.ellipse(s, dark, (hc[0] - r, hc[1] - r - h(2), 2 * r, h(38)))


# ----------------------------------------------------------------- ball + rules
def ball_pos(b, t):
    gy = lerp(270, 610, t ** 1.1); tb = .62
    if t < tb: hg = 55 * (1 - (t / tb) ** 2)
    else:
        u = (t - tb) / (1 - tb); hg = 95 * 4 * u * (1 - u)
    x = lerp(CX + b["line"] * 40, CX + b["line"] * 120, t) + b["sway"] * 70 * math.sin(math.pi * t)
    return x, gy - hg - 70 * t, gy, 5 + 17 * t ** 1.6


def new_ball(T0):
    on = random.random() < .78
    kind = random.choice(["fast", "normal", "normal", "slow", "swing"])
    return dict(on=on, kind=kind, T=T0 * dict(fast=.78, normal=1, slow=1.3, swing=1)[kind], t0=0, sw=None,
                line=random.uniform(-.3, .3) if on else random.choice([-1, 1]) * random.uniform(.9, 1.3),
                sway=random.choice([-1, 1]) * random.uniform(.6, 1) if kind == "swing" else 0)


def R(**k):
    d = dict(runs=0, out=False, wide=False, wait=1.3, fl=None); d.update(k); return d


def judge(b, sw, win):
    bx, by = ball_pos(b, 1)[:2]
    if sw is None:
        if b["on"]: return R(txt="BOWLED!", col=RED, out=True, kind="bowled", wait=1.9)
        return R(txt="WIDE! +1", col=YEL, runs=1, wide=True, kind="dot")
    dt, pw, tilt = sw
    if abs(dt) > win:
        if b["on"]: return R(txt="MISSED... BOWLED!", col=RED, out=True, kind="bowled", wait=1.9)
        return R(txt="SWING & MISS!", col=(255, 160, 60), kind="dot")
    q = 1 - abs(dt) / win
    dirn = clamp(clamp(dt / .2, -1, 1) * .8 + clamp(tilt / 3000, -1, 1) * .3, -1, 1)
    tx = CX + dirn * 620

    def hit(runs, txt, col=WHT):
        ty, arc, dur = {6: (190, 260, 1.5), 4: (305, 25, .9), 2: (400, 60, 1.1), 1: (470, 50, 1.0), 0: (560, 30, .8)}[runs]
        return R(txt=txt, col=col, runs=runs, kind="hit", wait=dur + .9, fl=dict(x0=bx, y0=by, x1=tx, y1=ty, arc=arc, dur=dur))

    def caught(txt):
        f = min(FIELDERS, key=lambda f: abs(f[0] - tx))
        return R(txt=txt, col=RED, out=True, kind="hit", wait=2.3, fl=dict(x0=bx, y0=by, x1=f[0], y1=f[1] - int(185 * f[2]), arc=170, dur=1.3))

    if not b["on"]:
        if random.random() < .3: return caught("EDGED! CAUGHT BEHIND!")
        return hit(1, "EDGED! 1 RUN", YEL) if q > .5 else hit(0, "NO RUN")
    if q > .7:
        if pw > .65: return hit(6, "SIXXXER!!", (255, 120, 255))
        return hit(4, "FOUR!", GRN) if pw > .35 else hit(2, "GENTLE TAP - 2 RUNS", YEL)
    if q > .45:
        if pw > .7: return hit(4, "FOUR!", GRN)
        return hit(2, "2 RUNS", YEL) if pw > .35 else hit(1, "1 RUN", YEL)
    if q > .2:
        if pw > .5 and random.random() < .5: return caught("CAUGHT!")
        return hit(1, "EDGE! 1 RUN", YEL)
    return caught("TOP EDGE! CAUGHT!") if random.random() < .4 else hit(0, "MISTIMED!")


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ble", action="store_true"); ap.add_argument("--usb", action="store_true")
    ap.add_argument("--port"); ap.add_argument("--name", default="")
    a = ap.parse_args()
    bat = Bat("ble" if a.ble else "usb" if a.usb else "auto", a.port, a.name)

    pygame.mixer.pre_init(44100, -16, 2, 512); pygame.init()
    scr = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("Cluck Cricket - micro:bit bat")
    clock = pygame.time.Clock()
    F = [pygame.font.SysFont("arial", s, bold=True) for s in (22, 34, 64)]
    FT = pygame.font.SysFont("impact,arialblack,arial", 104)
    FS = pygame.font.SysFont("arial", 16, bold=True)
    FB = pygame.font.SysFont("arial", 50, bold=True)
    S = make_sounds(); play = lambda k: S[k] and S[k].play()
    bg, cv = make_bg(F[0]), pygame.Surface((W, H))
    fsurf = pygame.Surface((W, H), pygame.SRCALPHA)
    rnd = random.Random(3)
    crowd = [(x + rnd.randint(-4, 4), y, rnd.choice([(230, 80, 80), (80, 140, 230), (240, 200, 60), (240, 240, 240), (120, 200, 120)]))
             for y in range(236, 296, 14) for x in range(8, W, 14)]
    crowd += [(x + rnd.randint(-4, 4), y, rnd.choice([(230, 80, 80), (80, 140, 230), (240, 200, 60), (240, 240, 240), (120, 200, 120)]))
              for y in range(172, 232, 14) for x in range(8, W, 14) if abs(x - CX) > 170]
    clouds = [[rnd.randint(0, W), rnd.randint(30, 90), rnd.randint(50, 90)] for _ in range(4)]

    def txt(f, s, pos, col=WHT, an="center", surf=None, font=None):
        fo = font or F[f]; img = fo.render(s, True, col); r = img.get_rect(); setattr(r, an, pos)
        o = 2 if fo.get_height() < 26 else 3
        (surf or scr).blit(fo.render(s, True, (0, 0, 0)), r.move(o, o)); (surf or scr).blit(img, r)

    def popup(f, s, pos, col, age):
        sc = 1 + .6 * max(0, 1 - age * 4)
        for c, o in (((0, 0, 0), 4), (col, 0)):
            z = pygame.transform.rotozoom(F[f].render(s, True, c), 0, sc); scr.blit(z, z.get_rect(center=(pos[0] + o, pos[1] + o)))

    def best_read():
        try:
            with open(HS_FILE) as f: return int(f.read())
        except Exception: return 0

    cfg = load_cfg()
    t_init = clk()
    G = dict(st="MENU", lvl=cfg.get("lvl", 2) if cfg.get("lvl") in LEVELS else 2, score=0, wk=0, played=0, hist=[], t_st=t_init,
             ph="intro", t_ph=t_init, b=None, res=None, fl=None, t_fl=0, anim=-9, excite=0.,
             off=clamp(float(cfg.get("off", 0.0)), -.5, .5), best=best_read(), won=False, shake=0., trail=[],
             fours=0, sixes=0, assist=bool(cfg.get("assist", True)), newbest=False,
             pause=False, pt=0.0, last_real=t_init, last_sw=-9., errs=[], perfect=0, flash=[(255, 255, 255), 0], cal=None)
    parts = []
    gt = lambda: clk() - G["pt"]                    # game clock (frozen while paused)

    def burst(x, y, n, cols, spd=7, grav=.25):
        for _ in range(n):
            parts.append([x, y, random.uniform(-spd, spd), random.uniform(-spd * 1.3, spd * .3), 1., random.choice(cols), grav])

    def start():
        T0 = LEVELS[G["lvl"]][2]; n = gt()
        G.update(st="PLAY", score=0, wk=0, played=0, hist=[], ph="intro", t_ph=n, res=None, fl=None, won=False,
                 fours=0, sixes=0, newbest=False, trail=[], errs=[], perfect=0, pause=False)
        G["b"] = new_ball(T0); play("beep")

    def cal_start():
        G.update(st="CAL", cal=dict(t0=gt() + 2.0, errs={}, done=None, msg=""))

    def cal_swing(ts):
        c = G["cal"]
        if c["done"] is not None: return
        k = round(ts - c["t0"])
        if 0 <= k < 8 and abs(ts - c["t0"] - k) < .45 and k not in c["errs"]:
            c["errs"][k] = ts - c["t0"] - k            # + = late, - = early

    while True:
        real = clk()
        if G["pause"]: G["pt"] += real - G["last_real"]
        G["last_real"] = real
        now = real - G["pt"]; swings = []
        name, target, T0, WIN = LEVELS[G["lvl"]]; b = G["b"]
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE): pygame.quit(); sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_SPACE:
                    kp = pygame.key.get_pressed()
                    swings.append((now, 3800 if e.mod & pygame.KMOD_SHIFT else 2600, (int(kp[pygame.K_RIGHT]) - int(kp[pygame.K_LEFT])) * 2500, "kb"))
                elif e.key in (pygame.K_1, pygame.K_2, pygame.K_3) and G["st"] == "MENU": G["lvl"] = e.key - pygame.K_0; save_cfg(G)
                elif e.key == pygame.K_COMMA: G["off"] = round(G["off"] - .01, 3); save_cfg(G)
                elif e.key == pygame.K_PERIOD: G["off"] = round(G["off"] + .01, 3); save_cfg(G)
                elif e.key == pygame.K_h: G["assist"] = not G["assist"]; save_cfg(G)
                elif e.key == pygame.K_p and G["st"] == "PLAY": G["pause"] = not G["pause"]
                elif e.key == pygame.K_c:
                    if G["st"] == "MENU": cal_start()
                    elif G["st"] == "CAL": G["st"] = "MENU"
                elif e.key == pygame.K_F11: pygame.display.toggle_fullscreen()
        while not bat.q.empty():
            t, mag, tilt = bat.q.get(); swings.append((t + G["off"] - G["pt"], mag, tilt, "bat"))
        if G["pause"]: swings = []

        for ts, mag, tilt, src in swings:
            if ts - G["last_sw"] < DEBOUNCE: continue
            G["last_sw"] = ts; G["anim"] = now
            if G["st"] == "CAL":
                if src == "bat": cal_swing(ts)
                continue
            if G["st"] == "MENU" or (G["st"] == "END" and now - G["t_st"] > 1.5): start(); b = G["b"]; continue
            if G["st"] == "PLAY" and G["ph"] == "bowl" and b["sw"] is None:
                dt = ts - (b["t0"] + b["T"])
                if -(WIN + .15) <= dt <= WIN + .05: b["sw"] = (dt, clamp((mag - POWER_MIN) / (POWER_MAX - POWER_MIN), 0, 1), tilt)

        # ---------------- game logic ----------------
        if G["st"] == "PLAY" and not G["pause"]:
            el = now - G["t_ph"]
            if G["ph"] == "intro" and el > 1.1: G["ph"], b["t0"] = "bowl", now
            elif G["ph"] == "bowl":
                arr = b["t0"] + b["T"]
                if (b["sw"] and now >= arr) or (not b["sw"] and now >= arr + WIN + .08):
                    res = judge(b, b["sw"], WIN); G.update(res=res, ph="after", t_ph=now)
                    if b["sw"]:
                        G["errs"].append(abs(b["sw"][0])); G["perfect"] += int(abs(b["sw"][0]) < WIN * .3)
                    if res["fl"]: G.update(fl=res["fl"], t_fl=now)
                    if res["kind"] == "hit": play("crack")
                    if res["kind"] == "bowled": play("thud"); G["shake"] = 12
                    if res["out"]: G["flash"] = [RED, 120]
                    if res["runs"] >= 4:
                        G["excite"] = 1.0; play("roar"); G["shake"] = 14 if res["runs"] == 6 else 6
                        G["flash"] = [(255, 210, 60), 110] if res["runs"] == 6 else [(90, 230, 130), 70]
                        G["sixes" if res["runs"] == 6 else "fours"] += 1
                        if res["runs"] == 6: burst(CX, 200, 70, [(255, 200, 40), (255, 120, 255), (120, 255, 200), WHT], 9)
                    if not res["wide"]: G["played"] += 1
                    G["score"] += res["runs"]; G["wk"] += int(res["out"])
                    G["hist"].append("Wd" if res["wide"] else "W" if res["out"] else str(res["runs"]) if res["runs"] else ".")
            elif G["ph"] == "after" and el > G["res"]["wait"]:
                G["fl"] = None
                if G["score"] >= target or G["wk"] >= WICKETS or G["played"] >= BALLS:
                    G.update(st="END", t_st=now, won=G["score"] >= target)
                    if G["score"] > G["best"]:
                        G["best"], G["newbest"] = G["score"], True
                        try:
                            with open(HS_FILE, "w") as f: f.write(str(G["best"]))
                        except Exception: pass
                    play("roar" if G["won"] else "thud")
                    if G["won"]: burst(CX, 160, 160, [(255, 200, 40), (255, 90, 160), (90, 220, 255), (140, 255, 140)], 11, .18)
                else:
                    G.update(ph="intro", t_ph=now, trail=[]); G["b"] = new_ball(T0); b = G["b"]
            G["excite"] = max(0, G["excite"] - .012)
        elif G["st"] == "CAL":
            c = G["cal"]
            if c["done"] is None and now > c["t0"] + 8.3:
                vals = [v for k, v in sorted(c["errs"].items()) if k >= 2]          # first 2 beats = practice
                if len(vals) >= 3:
                    G["off"] = round(clamp(G["off"] - statistics.median(vals), -.5, .5), 3)
                    c["msg"] = f"Done!  Timing offset is now {G['off'] * 1000:+.0f} ms"; save_cfg(G)
                else:
                    c["msg"] = "Not enough bat swings detected - try again (press C)"
                c["done"] = now
            elif c["done"] is not None and now - c["done"] > 2.6: G["st"] = "MENU"

        # ---------------- scene (shakes) ----------------
        cv.blit(bg, (0, 0))
        for c in clouds:
            c[0] = (c[0] + .3) % (W + 200); pygame.draw.ellipse(cv, (255, 255, 255), (c[0] - 100, c[1], c[2] * 2, c[2] // 2))
        for i, (x, y, col) in enumerate(crowd):
            pygame.draw.circle(cv, col, (x, int(y + 1.5 * math.sin(now * 2 + x * .05) - G["excite"] * 9 * abs(math.sin(now * 9 + i)))), 6)
        for fx, fy, fk, fc in sorted(FIELDERS, key=lambda f: f[1]): person(cv, fx, fy, fk, fc)
        person(cv, CX - 75, 266, .3, (245, 245, 245), hat=True)                       # umpire
        ph, el, res = G["ph"], now - G["t_ph"], G["res"]
        arm = (min(el, 1) if ph == "intro" else max(0, 1 - el / .3) if ph == "bowl" else 0) if G["st"] == "PLAY" else 0
        person(cv, CX, 262, .32, (255, 200, 40), chicken=True, arm=arm)

        broke = min(el / .5, 1) if (G["st"] == "PLAY" and ph == "after" and res and res["kind"] == "bowled") else 0
        pygame.draw.ellipse(cv, (25, 85, 35), (CX - 34, 606, 68, 12))
        for i, lean in enumerate((-.6, .2, .9)):
            bx0 = CX - 14 + i * 14; ang = lean * broke
            pygame.draw.line(cv, (250, 240, 200), (bx0, 612), (bx0 + math.sin(ang) * 85, 612 - math.cos(ang) * 85), 6)
        for dx in (-7, 7):
            by_ = 526 - 180 * broke * (1 - broke) - 60 * broke
            pygame.draw.line(cv, (200, 60, 60), (CX + dx - 6 + 30 * broke * dx / 7, by_), (CX + dx + 6 + 30 * broke * dx / 7, by_), 4)

        def draw_ball(x, y, r, gy=None):
            tr = G["trail"]
            if not G["pause"]: tr.append((x, y, r)); del tr[:-10]
            for i, (tx_, ty_, tr_) in enumerate(tr[:-1]):
                pygame.draw.circle(cv, (190, 50, 60), (int(tx_), int(ty_)), max(1, int(tr_ * (.25 + .6 * i / 10))))
            if gy is not None: pygame.draw.ellipse(cv, (30, 90, 40), (x - r, gy - r // 3, 2 * r, max(2, int(r * .7))))
            pygame.draw.circle(cv, (215, 30, 40), (int(x), int(y)), int(r)); pygame.draw.circle(cv, WHT, (int(x), int(y)), int(r), 2)
            pygame.draw.arc(cv, WHT, (int(x - r * .6), int(y - r * .6), int(r * 1.2), int(r * 1.2)), 0.5, 2.2, 1)

        if G["st"] == "PLAY" and ph == "bowl":
            t = (now - b["t0"]) / b["T"]
            if G["assist"]:
                ax, ay = ball_pos(b, 1)[:2]; inwin = abs(now - (b["t0"] + b["T"])) <= WIN
                leave = G["lvl"] == 1 and not b["on"]                     # EASY level: warn about wide balls
                pygame.draw.circle(cv, RED if leave else GRN if inwin else (255, 255, 255), (int(ax), int(ay)), int(32 + 4 * math.sin(now * 10)), 3)
                if leave: txt(1, "LEAVE IT!", (int(ax), int(ay) - 52), RED, surf=cv)
                elif inwin: txt(1, "SWING!", (int(ax), int(ay) - 52), GRN, surf=cv)
            if t <= 1.12: x, y, gy, r = ball_pos(b, t); draw_ball(x, y, r, gy)
        elif G["st"] == "PLAY" and ph == "after" and res and res["kind"] == "bowled" and el < .35:
            x, y, gy, r = ball_pos(b, 1); draw_ball(x, y, r)

        u = (now - G["anim"]) / .28
        ang = 115 - 200 * u if 0 <= u <= 1 else -85 if 1 < u < 1.8 else 115
        person(cv, CX - 110, 655, 1.0, (40, 90, 220), face=False, bat=ang, helmet=True, pads=True)

        if G["fl"]:
            f = G["fl"]; uu = clamp((now - G["t_fl"]) / f["dur"], 0, 1)
            x = lerp(f["x0"], f["x1"], uu); gy = lerp(f["y0"], f["y1"], uu)
            y = gy - f["arc"] * math.sin(math.pi * uu); r = int(5 + 13 * clamp((gy - 180) / 400, 0, 1))
            if not (res["runs"] == 6 and uu >= 1): draw_ball(x, y, r, gy)

        sh = int(G["shake"]); G["shake"] = max(0, G["shake"] - .8) if not G["pause"] else G["shake"]
        scr.blit(cv, (random.randint(-sh, sh), random.randint(-sh, sh)) if sh else (0, 0))

        if G["flash"][1] > 0:                                           # screen flash on wicket / four / six
            fsurf.fill((*G["flash"][0], int(G["flash"][1]))); scr.blit(fsurf, (0, 0))
            if not G["pause"]: G["flash"][1] = max(0, G["flash"][1] - 5)

        for p in parts[:]:                                           # particles / confetti
            if not G["pause"]: p[0] += p[2]; p[1] += p[3]; p[3] += p[6]; p[4] -= .012
            if p[4] <= 0 or p[1] > H + 20: parts.remove(p)
            else: pygame.draw.rect(scr, p[5], (int(p[0]), int(p[1]), 9, 6))

        # ---------------- timing bar + popups ----------------
        def draw_meter(ball_dt, sw_dt, pw):
            px, py_, pwid, ph_ = W - 492, H - 164, 480, 118          # bottom-right: never covers the stumps
            mx, sc = px + pwid // 2, (pwid / 2 - 24) / MR
            panel(scr, (px, py_, pwid, ph_), (120, 200, 255))
            bar = pygame.Rect(px + 22, py_ + 40, pwid - 44, 22)
            rr(scr, bar, (46, 52, 84), 11, 255)
            for fr, col in ZONES:
                w = int(2 * fr * WIN * sc); pygame.draw.rect(scr, col, (mx - w // 2, bar.y + 3, w, bar.h - 6), border_radius=4)
            pygame.draw.line(scr, WHT, (mx, bar.y - 4), (mx, bar.bottom + 4), 2)
            txt(0, "EARLY", (bar.x, py_ + 14), (170, 185, 220), "midleft", font=FS); txt(0, "LATE", (bar.right, py_ + 14), (170, 185, 220), "midright", font=FS)
            if ball_dt is not None:
                bx = int(mx + clamp(ball_dt, -MR, MR) * sc)
                pygame.draw.circle(scr, (215, 30, 40), (bx, bar.centery), 10); pygame.draw.circle(scr, WHT, (bx, bar.centery), 10, 2)
            if sw_dt is not None:
                pm = mx + clamp(sw_dt, -MR, MR) * sc
                pygame.draw.polygon(scr, WHT, [(pm, bar.y - 2), (pm - 9, bar.y - 16), (pm + 9, bar.y - 16)])
                lbl = "PERFECT" if abs(sw_dt) < WIN * .3 else "EARLY" if sw_dt < 0 else "LATE"
                txt(0, f"{lbl}  {sw_dt * 1000:+.0f} ms", (mx, py_ + 14), YEL if abs(sw_dt) < WIN * .55 else (255, 150, 90), font=FS)
            else:
                txt(0, "swing when the ball hits the green", (mx, py_ + 14), (225, 230, 245), font=FS)
            if pw is not None:
                txt(0, "POWER", (px + 22, py_ + 92), WHT, "midleft", font=FS)
                pb = pygame.Rect(px + 92, py_ + 84, pwid - 114, 16); rr(scr, pb, (46, 52, 84), 8, 255)
                if pw > .04: rr(scr, (pb.x, pb.y, int(pb.w * pw), pb.h), (255, int(200 - 110 * pw), 60), 8, 255)
            else:
                txt(0, f"timing window +/-{int(WIN * 1000)} ms", (mx, py_ + 92), (140, 155, 195), font=FS)

        if G["st"] == "PLAY" and ph == "bowl":
            draw_meter(now - (b["t0"] + b["T"]), b["sw"][0] if b["sw"] else None, None)
        elif G["st"] == "PLAY" and ph == "after" and res:
            popup(2, res["txt"], (CX, 128), res["col"], el)
            if b["sw"]: draw_meter(None, b["sw"][0], b["sw"][1])
        elif G["st"] == "PLAY" and ph == "intro":
            tag = {"fast": "FAST ball incoming!", "slow": "SLOW ball - wait for it!", "swing": "SWINGER - watch the curve!"}.get(b["kind"], "get ready!")
            txt(1, f"Ball {G['played'] + 1} of {BALLS} - {tag}", (CX, 128))

        # ---------------- HUD ----------------
        if G["st"] in ("PLAY", "END"):
            need, left = target - G["score"], BALLS - G["played"]
            lc = {1: (110, 240, 150), 2: (255, 200, 60), 3: (255, 90, 90)}[G["lvl"]]
            panel(scr, (12, 10, 250, 82), (255, 200, 60))                                   # scoreboard
            txt(0, "SCORE", (28, 28), (255, 200, 60), "midleft", font=FS); txt(0, "RUNS / WKTS", (246, 28), (170, 185, 220), "midright", font=FS)
            sw_ = FB.size(str(G["score"]))[0]
            txt(0, str(G["score"]), (28, 62), WHT, "midleft", font=FB); txt(1, f"/ {G['wk']}", (28 + sw_ + 8, 66), (255, 120, 120), "midleft")
            panel(scr, (CX - 215, 10, 430, 82), (90, 160, 255))                             # target + progress
            txt(0, f"TARGET {target}", (CX - 195, 30), WHT, "midleft")
            chip = pygame.Rect(0, 0, FS.size(name)[0] + 24, 24); chip.midright = (CX + 195, 30); rr(scr, chip, lc, 12, 255)
            im = FS.render(name, True, (20, 20, 40)); scr.blit(im, im.get_rect(center=chip.center))
            bar = pygame.Rect(CX - 195, 47, 390, 12); rr(scr, bar, (46, 52, 84), 6, 255)
            fw = int(bar.w * clamp(G["score"] / target, 0, 1))
            if fw >= 12: rr(scr, (bar.x, bar.y, fw, bar.h), GRN, 6, 255)
            msg = "TARGET REACHED!" if need <= 0 else f"Need {need} from {left} balls  -  RRR {need / left:.1f}" if left > 0 else f"Need {need}"
            txt(0, msg, (CX, 74), GRN if need <= 0 or need / max(left, 1) < 3 else YEL, font=FS)
            panel(scr, (W - 312, 10, 300, 82), (255, 120, 120))                             # balls + wickets
            txt(0, "BALLS", (W - 296, 27), (255, 150, 150), "midleft", font=FS); txt(0, f"{left} left", (W - 28, 27), (200, 205, 225), "midright", font=FS)
            for i in range(BALLS): pygame.draw.circle(scr, (100, 105, 130) if i < G["played"] else (235, 70, 80), (W - 290 + i * 22, 47), 6)
            txt(0, "WKTS", (W - 296, 71), (255, 150, 150), "midleft", font=FS)
            for i in range(WICKETS):
                alive, x = i >= G["wk"], W - 225 + i * 44
                for j in range(3): pygame.draw.line(scr, WHT if alive else (120, 70, 70), (x + j * 7, 62), (x + j * 7, 80), 3)
                pygame.draw.line(scr, WHT if alive else (120, 70, 70), (x - 2, 61), (x + 16, 61), 2)
                if not alive: pygame.draw.line(scr, RED, (x - 3, 59), (x + 17, 82), 4)
            txt(0, f"4s {G['fours']}   6s {G['sixes']}", (W - 24, 71), (200, 205, 225), "midright", font=FS)
            for i, hs in enumerate(G["hist"][-8:]):                                         # ball-by-ball chips
                c = RED if hs == "W" else (255, 120, 255) if hs == "6" else GRN if hs == "4" else YEL if hs == "Wd" else (225, 228, 240)
                r_ = pygame.Rect(14 + i * 40, 104, 34, 34); rr(scr, r_, c, 9, 255, (10, 15, 40), 2)
                im = FS.render(hs, True, WHT if hs == "W" else (10, 15, 40)); scr.blit(im, im.get_rect(center=r_.center))
        kind, text, src = bat.info()
        pc = {"ok": (90, 230, 130), "search": (255, 200, 70), "kb": (170, 170, 190)}[kind]
        wpx = FS.size(text)[0] + 70
        rr(scr, (12, H - 40, wpx, 30), (10, 15, 40), 15, 210, pc)
        pygame.draw.circle(scr, pc, (30, H - 25), 6 if kind == "search" and int(now * 3) % 2 else 8)
        bt_icon(scr, 52, H - 25, pc, .8) if src == "ble" else None
        txt(0, text, (68, H - 25), WHT, "midleft", font=FS)
        txt(0, f"offset {G['off'] * 1000:+.0f} ms (, .)   assist {'ON' if G['assist'] else 'OFF'} (H)   pause P   fullscreen F11", (W - 12, H - 25), (225, 225, 240), "midright", font=FS)

        # ---------------- menu / calibration / end / pause ----------------
        if G["st"] == "MENU":
            ov = pygame.Surface((W, H), pygame.SRCALPHA); ov.fill((5, 10, 35, 175)); scr.blit(ov, (0, 0))
            txt(0, "CLUCK CRICKET", (CX, 86 + int(4 * math.sin(now * 3))), YEL, surf=scr, font=FT)
            txt(1, "micro:bit Bluetooth Bat Challenge", (CX, 160), (190, 220, 255))
            panel(scr, (CX - 340, 205, 680, 84), pc, 235, 18)
            pygame.draw.circle(scr, pc, (CX - 304, 247), 10 if kind != "search" or int(now * 3) % 2 else 6)
            if src == "ble": bt_icon(scr, CX - 270, 247, pc, 1.3)
            txt(0, text if len(text) < 48 else text[:46] + "..", (CX - 245, 233), WHT, "midleft")
            txt(0, "Switch the bat on - or press SPACE to play with the keyboard" if kind != "ok" else "Bat ready! Swing it to start", (CX - 245, 268), (200, 210, 230), "midleft", font=FS)
            for i in (1, 2, 3):
                sel = G["lvl"] == i; x0 = CX - 345 + (i - 1) * 235
                panel(scr, (x0, 312 - 6 * sel, 220, 92 + 12 * sel), YEL if sel else (80, 100, 160), 240, 16, 26 if sel else 0)
                txt(1, LEVELS[i][0], (x0 + 110, 336 - 6 * sel), YEL if sel else WHT)
                txt(0, f"Target {LEVELS[i][1]}  [{i}]", (x0 + 110, 368 - 6 * sel), (200, 215, 240), font=FS)
                txt(0, f"timing window +/-{int(LEVELS[i][3] * 1000)} ms", (x0 + 110, 388 - 6 * sel), (160, 180, 220), font=FS)
            for i, (a1, a2) in enumerate((("TIMING", "early = leg,  late = off side"), ("POWER", "harder swing = more runs"), ("WIDE BALL?", "leave it alone! (+1 run)"))):
                x0 = CX - 345 + i * 235
                panel(scr, (x0, 432, 220, 74), (80, 100, 160), 225, 14); txt(0, a1, (x0 + 110, 457), YEL, font=FS); txt(0, a2, (x0 + 110, 484), WHT, font=FS)
            txt(0, f"Best score: {G['best']}", (CX, 540), (200, 220, 255), font=F[0])
            pill = pygame.Rect(CX - 210, 575, 420, 64); rr(scr, pill, (255, 150, 40) if int(now * 2) % 2 else (240, 110, 30), 32, 255, WHT, 3)
            txt(1, "SWING TO START", pill.center)
            txt(0, "Bat feels late or early?  Press C to calibrate", (CX, 662), (170, 230, 255), font=FS)
        elif G["st"] == "CAL":
            c = G["cal"]
            ov = pygame.Surface((W, H), pygame.SRCALPHA); ov.fill((5, 10, 35, 215)); scr.blit(ov, (0, 0))
            txt(2, "CALIBRATION", (CX, 110), YEL)
            if c["done"] is None:
                txt(1, "Swing the bat the moment the ball crosses the ring", (CX, 190))
                txt(0, "8 beats - the first 2 are practice.  Use the BAT (not the keyboard).  Press C to cancel.", (CX, 225), (200, 210, 230), font=FS)
                w = ((now - c["t0"] + .5) % 1.0) - .5
                pygame.draw.line(scr, (80, 100, 160), (CX - 320, 360), (CX + 320, 360), 4)
                flash = abs(w) < .06 and now > c["t0"] - .1
                pygame.draw.circle(scr, GRN if flash else WHT, (CX, 360), 44, 0 if flash else 4)
                bxp = int(CX + w * 640)
                pygame.draw.circle(scr, (215, 30, 40), (bxp, 360), 20); pygame.draw.circle(scr, WHT, (bxp, 360), 20, 3)
                if now < c["t0"]: txt(1, "Get ready...", (CX, 450), YEL)
                else:
                    for k in range(8):
                        x0, e = CX - 210 + k * 60, c["errs"].get(k)
                        pygame.draw.circle(scr, GRN if e is not None else (110, 110, 130), (x0, 450), 14 if k >= 2 else 9)
                        if e is not None: txt(0, f"{e * 1000:+.0f}", (x0, 485), (200, 220, 255), font=FS)
            else:
                txt(1, c["msg"], (CX, 330), GRN if "Done" in c["msg"] else RED)
        elif G["st"] == "END":
            ov = pygame.Surface((W, H), pygame.SRCALPHA); ov.fill((5, 10, 35, 185)); scr.blit(ov, (0, 0))
            panel(scr, (CX - 340, 100, 680, 480), YEL if G["won"] else (200, 90, 90), 245, 26)
            txt(2, "YOU WIN!" if G["won"] else "INNINGS OVER", (CX, 165), GRN if G["won"] else RED)
            stars = (3 if G["wk"] <= 1 else 2) if G["won"] else (1 if G["score"] >= target * .6 else 0)
            for i in range(3):
                cy_ = 255 - (14 if i == 1 else 0)
                star(scr, CX - 110 + i * 110, cy_, 44, (255, 210, 50) if i < stars else (90, 100, 130), i < stars)
            txt(2, f"{G['score']}/{G['wk']}", (CX, 345), WHT); txt(0, f"target {target}  -  {name}", (CX, 390), (190, 210, 240))
            txt(0, f"Fours: {G['fours']}     Sixes: {G['sixes']}     Best: {G['best']}", (CX, 430), YEL)
            avg = f"{sum(G['errs']) / len(G['errs']) * 1000:.0f} ms" if G["errs"] else "-"
            txt(0, f"Avg timing error: {avg}     Perfect hits: {G['perfect']}", (CX, 465), (190, 230, 255))
            if G["newbest"]: txt(1, "NEW BEST!", (CX, 505), (255, 120, 255))
            txt(1, "Swing to play again", (CX, 545), WHT if int(now * 2) % 2 else YEL)
        if G["pause"]:
            ov = pygame.Surface((W, H), pygame.SRCALPHA); ov.fill((5, 10, 35, 170)); scr.blit(ov, (0, 0))
            txt(2, "PAUSED", (CX, 330), YEL); txt(1, "press P to resume", (CX, 400), WHT)

        pygame.display.flip(); clock.tick(60)


if __name__ == "__main__":
    main()