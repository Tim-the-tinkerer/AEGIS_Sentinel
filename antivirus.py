#!/usr/bin/env python3
"""Play AEGIS Sentinel, a resident antivirus, and purge viruses out of live code.

You move through a process map. The floor is memory. Packed pages are
walls. Worms replicate and corrupt that memory. Trojans disguise
themselves as ordinary files until a scan exposes them. Spyware calls
the other processes to you. Ransomware locks a room. On the kernel,
the system fails while POLY.SYS is alive. Clear every threat, then
step on CLEAN.EXIT.

Usage: antivirus.py [--seed N] [--level N] [--mute] [--check]

--seed N repeats the processes. N is an integer from 0 through
2^64 - 1. With no seed, the run picks one and shows it on the title.
--level N starts at that process, from 1 through 9.
--mute starts with the sound off. M switches it during play.
--check runs the tests and does not open a window.

WASD or the arrows move. The mouse aims. Click or space purges.
N toggles procedural music independently of sound.
Control+Enter (or Option+Enter) toggles fullscreen. The mouse is confined
to the game while playing and released when paused or unfocused.
Shift or F scans. A scan names a sleeping trojan without waking it,
quarantines infected memory in range, and slows whatever it touches.
Esc or P pauses. From a menu, Q quits. R retries the current process
from the pause menu or the halt screen. Retry rebuilds that process
at the integrity it had when you mounted it.

python3 antivirus.py --help prints this text and exits 0.
A finished game exits 0. Argument errors exit 2. A missing pygame
install exits 1. Ctrl-C exits 130.
"""

from __future__ import annotations

import math
from array import array
import os
import random
import struct
import sys
import unittest
from pathlib import Path

import sim

USAGE = "usage: antivirus.py [--seed N] [--level N] [--mute] [--fullscreen] [--check]"
VIEW_W = 1280
VIEW_H = 800
# Two rows at the bottom edge: combat stats, then the control hint.
# The playfield above this strip stays clear.
DOCK_H = 62

BG = (6, 10, 16)
FLOOR = (10, 16, 26)
GRID = (18, 30, 44)
WALL = (15, 26, 46)
WALL_HI = (58, 88, 124)
WALL_LO = (5, 8, 16)
CYAN = (136, 232, 255)
CYAN_DIM = (62, 118, 140)
WHITE = (236, 246, 250)
AMBER = (255, 188, 72)
RED = (255, 88, 100)
MAGENTA = (236, 78, 156)
GREEN = (116, 226, 156)
TEAL = (84, 220, 214)
INK = (6, 10, 16)
DIM = (150, 170, 176)

KIND_COLOR = {
    "worm": MAGENTA,
    "trojan": RED,
    "spyware": TEAL,
    "ransom": AMBER,
    "boss": RED,
}

pygame = None


class UsageError(Exception):
    pass


class Options:
    def __init__(self) -> None:
        self.help = False
        self.check = False
        self.seed: int | None = None
        self.level = 1
        self.mute = False
        self.fullscreen = False


def engine():
    """Import pygame the first time the window needs it."""
    global pygame
    if pygame is None:
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame as loaded

        pygame = loaded
    return pygame


def parse_args(argv: list[str]) -> Options:
    opts = Options()
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg in ("-h", "--help"):
            opts.help = True
        elif arg == "--check":
            opts.check = True
        elif arg == "--mute":
            opts.mute = True
        elif arg == "--fullscreen":
            opts.fullscreen = True
        elif arg == "--seed" or arg.startswith("--seed="):
            raw, index = _value(argv, index, arg, "--seed")
            opts.seed = _u64(raw, "seed")
        elif arg == "--level" or arg.startswith("--level="):
            raw, index = _value(argv, index, arg, "--level")
            opts.level = _level(raw)
        else:
            raise UsageError(f"unknown argument: {arg}")
        index += 1
    return opts


def _value(argv: list[str], index: int, arg: str, flag: str) -> tuple[str, int]:
    if arg.startswith(flag + "="):
        raw = arg.split("=", 1)[1]
        if raw == "":
            raise UsageError(f"{flag} needs a value")
        return raw, index
    if index + 1 >= len(argv):
        raise UsageError(f"{flag} needs a value")
    return argv[index + 1], index + 1


def _u64(text: str, name: str) -> int:
    try:
        value = int(text, 10)
    except ValueError:
        raise UsageError(f"{name} is not an integer: {text}") from None
    if value < 0 or value > sim.MASK64:
        raise UsageError(f"{name} is out of range: {text}")
    return value


def _level(text: str) -> int:
    try:
        value = int(text, 10)
    except ValueError:
        raise UsageError(f"level is not an integer: {text}") from None
    if value < 1 or value > len(sim.PROCESSES):
        raise UsageError(f"level is out of range: {text}")
    return value


def run_checks() -> int:
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import test_antivirus

    suite = unittest.defaultTestLoader.loadTestsFromModule(test_antivirus)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


def tone(freq: float, ms: int, volume: float = 0.12):
    pg = engine()
    rate = 22050
    count = max(1, int(rate * ms / 1000))
    frames = bytearray()
    for i in range(count):
        attack = min(1.0, i / max(1, int(rate * 0.008)))
        env = (1.0 - i / count) * attack
        sample = math.sin(2 * math.pi * freq * (i / rate))
        value = int(max(-1.0, min(1.0, sample * volume * env)) * 32767)
        frames += struct.pack("<h", value)
    return pg.mixer.Sound(buffer=bytes(frames))


class ProceduralScore:
    """A deterministic tracker-like score. All audio is synthesized in memory."""
    RATE = 22050
    ROOTS = (38, 40, 35, 33, 36, 31, 34, 29, 26)
    # Minor / suspended intervals, to avoid randomly dissonant melodies.
    SCALE = (0, 3, 5, 7, 10, 12, 15, 17)

    def __init__(self, pg):
        self.pg = pg
        self.ambient = pg.mixer.Channel(4)
        self.danger = pg.mixer.Channel(5)
        self.level_key = None
        self.enabled = True
        self.built = False

    @staticmethod
    def note_freq(midi: float) -> float:
        return 440.0 * (2 ** ((midi - 69) / 12))

    def make_layer(self, seed: int, level: int, tense: bool):
        rng = random.Random((seed ^ (level * 0x9E3779B97F4A7C15) ^
                             (0xB16B00B5 if tense else 0xA6815)) & sim.MASK64)
        bpm = 96 + level * 3
        beat = 60 / bpm
        duration = beat * 8     # 2 bars of 4/4, with a repeatable seed.
        count = round(duration * self.RATE)
        buf = array('f', [0.0]) * count
        root = self.ROOTS[level - 1]

        def voice(start, length, pitch, gain, style):
            begin = int(start * self.RATE)
            frames = min(int(length * self.RATE), count - begin)
            if frames <= 0:
                return
            frequency = self.note_freq(pitch)
            phase_step = math.tau * frequency / self.RATE
            for j in range(frames):
                t = j / self.RATE
                x = j / frames
                if style == 'pad':
                    env = min(1.0, t / .30) * min(1.0, (1 - x) * 5)
                    osc = (math.sin(phase_step * j) * .65 +
                           math.sin(phase_step * j * 1.003) * .25 +
                           math.sin(phase_step * j * 2) * .10)
                elif style == 'bass':
                    env = (1 - x) ** 1.8 * min(1, t / .008)
                    osc = math.sin(phase_step * j) + .17 * math.sin(phase_step * j * 2)
                elif style == 'ping':
                    env = math.exp(-7 * x) * min(1, t / .004)
                    osc = math.sin(phase_step * j) + .15 * math.sin(phase_step * j * 3)
                else:  # noise-like tick: deterministic inharmonic sines
                    env = math.exp(-12 * x)
                    osc = (.5 * math.sin(phase_step * j * 13) +
                           .5 * math.sin(phase_step * j * 19.7))
                buf[begin + j] += osc * gain * env

        if not tense:
            # Continuous drone, atmospheric chord, and non-obvious low pulse.
            for k, degree in enumerate((0, 3, 5)):
                voice(0, duration, root - 12 + degree, .075 if k == 0 else .036, 'pad')
            for step in range(8):
                degree = (0, 0, 4, 0, 3, 0, 4, 2)[step]
                voice(step * beat, beat * .64, root - 12 + degree, .095, 'bass')
                if step in (2, 6):
                    voice(step * beat + .03, beat * .65,
                          root + self.SCALE[rng.choice((1, 2, 4, 5))], .057, 'ping')
            for step in range(16):
                if rng.random() < .58:
                    voice(step * beat / 2, .065, 96 + rng.randrange(8), .022, 'tick')
        else:
            # Separate rhythmic layer, raised as actual threats grow nearby.
            for step in range(16):
                if step % 2 == 0:
                    voice(step * beat / 2, .20, root - 12, .15, 'bass')
                if step % 4 in (1, 3):
                    voice(step * beat / 2, .080, 93 + rng.randrange(10), .060, 'tick')
                if step in (3, 7, 11, 14):
                    voice(step * beat / 2, beat * .45,
                          root + self.SCALE[rng.randrange(2, 8)], .045, 'ping')

        # Smooth loop boundary; no clipped waveform or abrupt repeat click.
        fade = min(800, count // 8)
        out = array('h')
        for i, sample in enumerate(buf):
            edge = min(1.0, i / fade, (count - 1 - i) / fade)
            out.append(int(max(-1, min(1, sample * edge)) * 32767))
        return self.pg.mixer.Sound(buffer=out.tobytes())

    def sync(self, seed: int, level: int, active: bool, threat: float, on: bool):
        key = (seed, level)
        if key != self.level_key:
            self.level_key = key
            self.ambient.stop()
            self.danger.stop()
            self.ambient.play(self.make_layer(seed, level, False), loops=-1)
            self.danger.play(self.make_layer(seed, level, True), loops=-1)
        volume = 1.0 if (active and on and self.enabled) else 0.0
        self.ambient.set_volume(.70 * volume)
        self.danger.set_volume(.64 * volume * max(0.0, min(1.0, threat)))

    def stop(self):
        self.ambient.stop()
        self.danger.stop()


class Audio:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.ready = False
        self.sounds: dict = {}
        self.score = None
        pg = engine()
        try:
            pg.mixer.init(22050, -16, 1, 512)
        except pg.error:
            self.enabled = False
            return
        specs = {
            "fire": (780, 32, 0.08),
            "scan": (520, 70, 0.08),
            "reveal": (660, 80, 0.1),
            "kill": (880, 70, 0.1),
            "hurt": (110, 90, 0.12),
            "exit": (660, 120, 0.1),
            "clear": (784, 160, 0.1),
            "crash": (80, 220, 0.12),
            "lock": (160, 50, 0.08),
        }
        self.sounds = {name: tone(*spec) for name, spec in specs.items()}
        self.ready = True
        self.score = ProceduralScore(pg)

    def play(self, name: str) -> None:
        if self.enabled and self.ready and name in self.sounds:
            self.sounds[name].play()

    def toggle(self) -> None:
        if not self.ready:
            return
        self.enabled = not self.enabled
        if not self.enabled:
            engine().mixer.stop()


def load_fonts() -> dict:
    pg = engine()
    names = ["menlo", "consolas", "dejavusansmono", "monospace"]

    def font(size: int):
        return pg.font.SysFont(names, size)

    return {
        "logo": font(48),
        "head": font(30),
        "body": font(18),
        "small": font(16),
        "byte": font(15),
        "tiny": font(13),
    }


def blit(surf, font, msg: str, x: int, y: int, color: tuple[int, int, int]) -> tuple[int, int]:
    shadow = font.render(msg, True, (0, 0, 0))
    surf.blit(shadow, (x + 1, y + 1))
    image = font.render(msg, True, color)
    surf.blit(image, (x, y))
    return image.get_width(), image.get_height()


def blit_right(surf, font, msg: str, right: int, y: int, color: tuple[int, int, int]) -> None:
    width, _height = font.size(msg)
    blit(surf, font, msg, right - width, y, color)


def tracked(surf, font, msg: str, x: int, y: int, color: tuple[int, int, int], gap: int) -> None:
    cursor = x
    for char in msg:
        width, _height = blit(surf, font, char, cursor, y, color)
        cursor += width + gap


def wrap(font, msg: str, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in msg.split():
        trial = word if not current else f"{current} {word}"
        if font.size(trial)[0] <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def panel(surf, rect, border: tuple[int, int, int]) -> None:
    pg = engine()
    pg.draw.rect(surf, (7, 12, 18), rect)
    pg.draw.rect(surf, border, rect, 1)


def plate(surf, rect) -> None:
    pg = engine()
    pg.draw.rect(surf, (7, 12, 18), rect)
    pg.draw.rect(surf, (28, 48, 62), rect, 1)


def bar(surf, x: int, y: int, width: int, height: int, frac: float, fill: tuple[int, int, int]) -> None:
    pg = engine()
    frac = min(1.0, max(0.0, frac))
    pg.draw.rect(surf, (8, 14, 22), (x, y, width, height))
    inner = int((width - 4) * frac)
    if inner > 0:
        pg.draw.rect(surf, fill, (x + 2, y + 2, inner, height - 4))
    pg.draw.rect(surf, CYAN_DIM, (x, y, width, height), 1)


def cell_byte(c: int, r: int, seed: int) -> tuple[str, int]:
    mix = (c * 73856093 ^ r * 19349663 ^ (seed & 0xFFFFFFFF) * 83492791) & 0xFFFFFFFF
    return f"{mix & 0xFF:02x}", mix


def lift(color: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
    return (
        min(255, color[0] + amount),
        min(255, color[1] + amount),
        min(255, color[2] + amount),
    )


def format_time(seconds: float) -> str:
    whole = max(0, int(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


def camera_of(world: sim.World, shake: tuple[float, float]) -> tuple[float, float]:
    x = world.player.x - VIEW_W / 2
    y = world.player.y - VIEW_H / 2
    x = min(max(0.0, x), max(0, sim.WIDTH_PX - VIEW_W))
    y = min(max(0.0, y), max(0, sim.HEIGHT_PX - VIEW_H))
    return x + shake[0], y + shake[1]


def paint_player(surf, player: sim.Player, sx: int, sy: int, now: float) -> None:
    """AEGIS Sentinel: an articulated, non-humanoid security construct."""
    pg = engine()
    blink = player.hurt > 0 and int(now * 16) % 2 == 0
    primary = CYAN_DIM if blink else CYAN
    pulse = 0.5 + 0.5 * math.sin(now * 3.4)
    aim = player.aim

    def pt(angle: float, radius: float) -> tuple[int, int]:
        return (round(sx + math.cos(angle) * radius),
                round(sy + math.sin(angle) * radius))

    # The outline stays inside the same collision envelope as the old avatar.
    pg.draw.circle(surf, (8, 35, 47), (sx, sy), player.radius + 7)
    pg.draw.circle(surf, primary, (sx, sy), player.radius + 7, 1)
    for i in range(4):
        start = now * (0.42 if i % 2 else -0.38) + i * math.pi / 2
        pg.draw.arc(surf, TEAL if i % 2 else primary,
                    (sx - 20, sy - 20, 40, 40), start, start + 0.65, 2)
    # Four segmented armor vanes counter-rotate around the central processor.
    for i in range(4):
        ang = now * -0.7 + i * math.pi / 2
        blade = (pt(ang - 0.29, 11), pt(ang - 0.18, 16),
                 pt(ang + 0.18, 16), pt(ang + 0.29, 11))
        pg.draw.polygon(surf, (19, 67, 79), blade)
        pg.draw.lines(surf, primary, False, blade[:3], 1)
    # Distinctive hexagonal processor housing with pulsing diamond-eye.
    hexagon = [pt(aim + math.pi / 6 + i * math.tau / 6, 10) for i in range(6)]
    pg.draw.polygon(surf, (7, 20, 32), hexagon)
    pg.draw.polygon(surf, primary, hexagon, 2)
    pg.draw.polygon(surf, (25, int(115 + 75 * pulse), 176),
                    (pt(aim, 6), pt(aim + math.pi / 2, 4),
                     pt(aim + math.pi, 6), pt(aim - math.pi / 2, 4)))
    # A turret/emitter rather than a triangle: aiming remains unambiguous.
    muzzle = pt(aim, 20)
    pg.draw.line(surf, (12, 60, 75), pt(aim, 7), muzzle, 7)
    pg.draw.line(surf, WHITE if not blink else primary, pt(aim, 11), muzzle, 3)
    pg.draw.circle(surf, TEAL, muzzle, 3)
    if player.muzzle > 0:
        pg.draw.circle(surf, WHITE, muzzle, 5)
        pg.draw.circle(surf, CYAN, muzzle, 9, 1)


def _open_neighbor(world: sim.World, c: int, r: int, dc: int, dr: int) -> bool:
    nc, nr = c + dc, r + dr
    if not (0 <= nc < sim.COLS and 0 <= nr < sim.ROWS):
        return False
    return not world.solid[nr][nc]


def _corridor_axis(world: sim.World, c: int, r: int) -> str | None:
    if world._open_count(c, r) not in (2, 3):
        return None
    horiz = _open_neighbor(world, c, r, -1, 0) and _open_neighbor(world, c, r, 1, 0)
    vert = _open_neighbor(world, c, r, 0, -1) and _open_neighbor(world, c, r, 0, 1)
    if horiz and not vert:
        return "h"
    if vert and not horiz:
        return "v"
    return None


def _near_corrupt(world: sim.World, c: int, r: int) -> bool:
    for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nc, nr = c + dc, r + dr
        if 0 <= nc < sim.COLS and 0 <= nr < sim.ROWS and world.tile[nr][nc] == sim.CORRUPT:
            return True
    return False


def _paint_block(
    surf,
    sx: int,
    sy: int,
    fill: tuple[int, int, int],
    hi: tuple[int, int, int],
    lo: tuple[int, int, int],
) -> None:
    pg = engine()
    pg.draw.rect(surf, fill, (sx, sy, sim.CELL, sim.CELL))
    pg.draw.line(surf, hi, (sx, sy), (sx + sim.CELL - 1, sy))
    pg.draw.line(surf, hi, (sx, sy), (sx, sy + sim.CELL - 1))
    pg.draw.line(surf, lo, (sx, sy + sim.CELL - 1), (sx + sim.CELL, sy + sim.CELL - 1))
    pg.draw.line(surf, lo, (sx + sim.CELL - 1, sy), (sx + sim.CELL - 1, sy + sim.CELL))


def paint_enemy(surf, enemy: sim.Enemy, sx: int, sy: int, now: float, font) -> None:
    pg = engine()
    if enemy.kind == "trojan" and not enemy.awake:
        if enemy.marked:
            _paint_hidden(surf, sx, sy, font, True)
        else:
            _paint_cover(surf, enemy.cover, sx, sy, font)
        return
    if enemy.flash > 0:
        pg.draw.circle(surf, WHITE, (sx, sy), int(enemy.radius + 4), 2)
    if enemy.kind == "worm":
        _paint_worm(surf, enemy, sx, sy)
    elif enemy.kind == "trojan":
        _paint_trojan(surf, enemy, sx, sy, font)
    elif enemy.kind == "spyware":
        _paint_spy(surf, enemy, sx, sy, now)
    elif enemy.kind == "ransom":
        _paint_ransom(surf, enemy, sx, sy)
    else:
        _paint_boss(surf, enemy, sx, sy, now)
    if enemy.max_hp > 1:
        _pips(surf, enemy, sx, sy)


def _paint_cover(surf, name: str, sx: int, sy: int, font) -> None:
    """A sleeping trojan, drawn as just another filename."""
    pg = engine()
    label = name or "tmp.sh"
    width, height = font.size(label)
    left = sx - width // 2
    top = sy - height // 2
    pg.draw.rect(surf, (6, 14, 16), (left - 3, top - 2, width + 6, height + 4))
    blit(surf, font, label, left, top, (120, 186, 150))


def _paint_checked(surf, name: str, sx: int, sy: int, font) -> None:
    """A file a scan has read. It is only a file."""
    pg = engine()
    width, height = font.size(name)
    left = sx - width // 2
    top = sy - height // 2
    pg.draw.rect(surf, (6, 12, 16), (left - 3, top - 2, width + 6, height + 4))
    pg.draw.rect(surf, (40, 70, 70), (left - 3, top - 2, width + 6, height + 4), 1)
    blit(surf, font, name, left, top, (84, 118, 112))


def _paint_hidden(surf, sx: int, sy: int, font, marked: bool = False) -> None:
    pg = engine()
    rect = pg.Rect(sx - 28, sy - 14, 56, 28)
    border = CYAN if marked else (52, 120, 84)
    pg.draw.rect(surf, (8, 20, 16), rect, border_radius=3)
    pg.draw.rect(surf, border, rect, 2 if marked else 1, border_radius=3)
    for index, (text, color) in enumerate((("e7", (64, 140, 104)), ("@", (196, 255, 190)), ("1c", (64, 140, 104)))):
        image = font.render(text, True, color)
        surf.blit(image, image.get_rect(center=(sx - 18 + index * 18, sy)))


def _paint_worm(surf, enemy: sim.Enemy, sx: int, sy: int) -> None:
    pg = engine()
    fx, fy = math.cos(enemy.facing), math.sin(enemy.facing)
    px, py = -fy, fx
    shades = (MAGENTA, (186, 48, 112), (120, 24, 72))
    for index, radius in enumerate((8, 11, 13)):
        ox = int(-fx * (2 - index) * 11)
        oy = int(-fy * (2 - index) * 11)
        pg.draw.circle(surf, (28, 6, 18), (sx + ox, sy + oy), radius + 2)
        pg.draw.circle(surf, shades[index], (sx + ox, sy + oy), radius)
    pg.draw.circle(surf, WHITE, (sx + int(fx * 5 + px * 4), sy + int(fy * 5 + py * 4)), 2)
    pg.draw.circle(surf, WHITE, (sx + int(fx * 5 - px * 4), sy + int(fy * 5 - py * 4)), 2)


def _paint_trojan(surf, enemy: sim.Enemy, sx: int, sy: int, font) -> None:
    pg = engine()
    reach = 18 if enemy.dash > 0 else 14
    points = (
        (sx, sy - reach),
        (sx + reach, sy),
        (sx, sy + reach),
        (sx - reach, sy),
    )
    pg.draw.polygon(surf, (48, 8, 14), points)
    pg.draw.polygon(surf, RED, points, 2)
    image = font.render("!", True, WHITE)
    surf.blit(image, image.get_rect(center=(sx, sy)))


def _paint_spy(surf, enemy: sim.Enemy, sx: int, sy: int, now: float) -> None:
    pg = engine()
    points = []
    for index in range(6):
        ang = math.tau * index / 6 + now * 0.3
        points.append((sx + math.cos(ang) * 15, sy + math.sin(ang) * 15))
    pg.draw.polygon(surf, (10, 32, 36), points)
    pg.draw.polygon(surf, TEAL, points, 2)
    fx, fy = math.cos(enemy.facing), math.sin(enemy.facing)
    pg.draw.circle(surf, TEAL, (sx, sy), 6)
    pg.draw.circle(surf, INK, (sx + int(fx * 3), sy + int(fy * 3)), 3)


def _paint_ransom(surf, enemy: sim.Enemy, sx: int, sy: int) -> None:
    pg = engine()
    if enemy.pulse > 0:
        grown = 1 - enemy.pulse / sim.PULSE_TIME
        radius = int(14 + grown * (sim.RANSOM_RADIUS - 14))
        pg.draw.circle(surf, AMBER, (sx, sy), radius, 2)
    body = pg.Rect(sx - 11, sy - 6, 22, 20)
    pg.draw.rect(surf, AMBER, body, border_radius=3)
    pg.draw.arc(surf, AMBER, (sx - 8, sy - 18, 16, 16), 0, math.pi, 3)
    pg.draw.circle(surf, INK, (sx, sy + 2), 3)
    pg.draw.rect(surf, INK, (sx - 1, sy + 3, 3, 6))


def _paint_boss(surf, enemy: sim.Enemy, sx: int, sy: int, now: float) -> None:
    pg = engine()
    outer = []
    inner = []
    for index in range(8):
        ang = math.tau * index / 8 + now * 0.6
        outer.append((sx + math.cos(ang) * 28, sy + math.sin(ang) * 28))
    for index in range(3):
        ang = -now * 1.1 + index * math.tau / 3
        inner.append((sx + math.cos(ang) * 12, sy + math.sin(ang) * 12))
    pg.draw.polygon(surf, (42, 6, 16), outer)
    pg.draw.polygon(surf, RED, outer, 2)
    pg.draw.polygon(surf, WHITE, inner, 2)


def _pips(surf, enemy: sim.Enemy, sx: int, sy: int) -> None:
    pg = engine()
    total = enemy.max_hp * 8
    left = sx - total // 2
    for index in range(enemy.max_hp):
        color = KIND_COLOR.get(enemy.kind, WHITE) if index < enemy.hp else (40, 48, 58)
        pg.draw.rect(surf, color, (left + index * 8, sy - int(enemy.radius) - 12, 6, 4))


class MapLayer:
    """The tile floor and walls of one process, painted once.

    The floor only changes when a cell fills or clears, and each of those
    bumps world.map_rev. On a new rev, only the changed cells and their
    neighbors are repainted. The moving sweep and the flashes are drawn
    over this layer every frame.
    """

    def __init__(self, app: "App", world: sim.World) -> None:
        pg = engine()
        self.app = app
        self.world = world
        self.rev = None
        self.snap: list[list[tuple[int, bool]]] | None = None
        self.surface = pg.Surface((sim.WIDTH_PX, sim.HEIGHT_PX))
        self.surface.fill(BG)
        self.gates = {(cell[0], cell[1]) for cell in world.unstable}
        self.tint = world.spec.tint
        self.hot = lift(self.tint, 138)
        self.corrupt_wash = pg.Surface((sim.CELL, sim.CELL), pg.SRCALPHA)
        self.corrupt_wash.fill((120, 24, 52, 42))

    def _state(self, c: int, r: int) -> tuple[int, bool]:
        kind = self.world.tile[r][c]
        if kind == sim.LATENT:
            kind = sim.OPEN
        return kind, self.world.solid[r][c]

    def sync(self) -> None:
        world = self.world
        if self.rev == world.map_rev and self.snap is not None:
            return
        dirty: set[tuple[int, int]] = set()
        if self.snap is None:
            dirty = {(c, r) for r in range(sim.ROWS) for c in range(sim.COLS)}
        else:
            for r in range(sim.ROWS):
                row = self.snap[r]
                for c in range(sim.COLS):
                    if row[c] != self._state(c, r):
                        dirty.add((c, r))
                        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            nc, nr = c + dc, r + dr
                            if 0 <= nc < sim.COLS and 0 <= nr < sim.ROWS:
                                dirty.add((nc, nr))
        for c, r in dirty:
            self.paint(c, r)
        self.snap = [[self._state(c, r) for c in range(sim.COLS)] for r in range(sim.ROWS)]
        self.rev = world.map_rev

    def is_floor(self, c: int, r: int) -> bool:
        kind = self.world.tile[r][c]
        if kind == sim.LATENT:
            return True
        return kind == sim.OPEN and not self.world.solid[r][c]

    def paint(self, c: int, r: int) -> None:
        pg = engine()
        world = self.world
        surf = self.surface
        sx = c * sim.CELL
        sy = r * sim.CELL
        kind = world.tile[r][c]
        if world.solid[r][c] and kind == sim.OPEN:
            kind = sim.PACKED
        if kind == sim.CORRUPT:
            _paint_block(surf, sx, sy, (78, 18, 42), (186, 64, 112), (40, 8, 22))
            return
        if kind == sim.SEAL:
            _paint_block(surf, sx, sy, (92, 64, 18), (220, 164, 64), (48, 30, 8))
            return
        if kind == sim.GATE:
            _paint_block(surf, sx, sy, (16, 40, 52), (126, 196, 208), (6, 16, 22))
            return
        if kind == sim.PACKED or (world.solid[r][c] and kind != sim.LATENT):
            _paint_block(surf, sx, sy, WALL, WALL_HI, WALL_LO)
            return
        pg.draw.rect(surf, FLOOR, (sx, sy, sim.CELL, sim.CELL))
        if _near_corrupt(world, c, r):
            surf.blit(self.corrupt_wash, (sx, sy))
        axis = _corridor_axis(world, c, r)
        if axis == "h":
            pg.draw.line(surf, (52, 118, 146), (sx, sy + sim.CELL // 2), (sx + sim.CELL, sy + sim.CELL // 2), 2)
        elif axis == "v":
            pg.draw.line(surf, (52, 118, 146), (sx + sim.CELL // 2, sy), (sx + sim.CELL // 2, sy + sim.CELL), 2)
        text, mix = cell_byte(c, r, world.seed)
        image = self.app.glyph(text, self.hot if mix % 17 == 0 else self.tint)
        surf.blit(image, image.get_rect(center=(sx + sim.CELL // 2, sy + sim.CELL // 2)))
        if (c, r) in self.gates and kind == sim.OPEN:
            pg.draw.rect(surf, (64, 150, 168), (sx + 3, sy + 3, sim.CELL - 6, sim.CELL - 6), 1)
        pg.draw.line(surf, GRID, (sx + sim.CELL - 1, sy), (sx + sim.CELL - 1, sy + sim.CELL))
        pg.draw.line(surf, GRID, (sx, sy + sim.CELL - 1), (sx + sim.CELL, sy + sim.CELL - 1))


class App:
    def __init__(self, screen, seed: int, level: int, mute: bool, fullscreen: bool = False) -> None:
        self.screen = screen
        self.fullscreen = fullscreen
        self.focused = True
        self.mouse_captured = False
        self.seed = seed
        self.start_level = level
        self.session: sim.Session | None = None
        self.paused = False
        self.now = 0.0
        self.fonts = load_fonts()
        self.audio = Audio(not mute)
        self.cache: dict = {}
        self.map_surface = None
        self.map_key = None
        self.layer: MapLayer | None = None
        self.flash_wash = None
        self.rings: list[list[float]] = []
        self.alerts: list[list[float]] = []
        self.sparks: list[list] = []
        self.feed: list[list] = []
        self.trail: list[tuple[float, float]] = []
        self.shake = 0.0
        self.want_scan = False
        self.arm = 0.0
        self.keys = None
        self.prev_down: set[int] = set()
        self.prev_right = False
        self.clock = engine().time.Clock()

    def run(self) -> int:
        pg = engine()
        while True:
            dt = min(self.clock.tick(60) / 1000.0, sim.DT_MAX)
            if not self.handle():
                self.release_mouse()
                return 0
            self.update(dt)
            self.draw()
            pg.display.flip()

    def current(self) -> str:
        if self.session is None:
            return "title"
        if self.paused and self.session.mode == "play":
            return "pause"
        return self.session.mode

    def set_fullscreen(self, enabled: bool) -> None:
        """Switch display mode, retaining 1280x800 logical aiming coordinates."""
        pg = engine()
        if self.fullscreen == enabled:
            return
        # Release SDL capture before changing the video mode.
        self.release_mouse()
        flags = pg.SCALED | (pg.FULLSCREEN if enabled else 0)
        try:
            new_screen = pg.display.set_mode((VIEW_W, VIEW_H), flags)
        except pg.error:
            # Stay playable if this display cannot switch modes.
            flags = pg.SCALED | (pg.FULLSCREEN if self.fullscreen else 0)
            self.screen = pg.display.set_mode((VIEW_W, VIEW_H), flags)
            return
        self.screen = new_screen
        self.fullscreen = enabled

    def release_mouse(self) -> None:
        pg = engine()
        pg.event.set_grab(False)
        pg.mouse.set_visible(True)
        self.mouse_captured = False

    def sync_mouse_capture(self) -> None:
        """Capture only during active focused play; menus and desktop are free."""
        pg = engine()
        capture = self.focused and self.current() == "play"
        if capture != self.mouse_captured:
            pg.event.set_grab(capture)
            pg.mouse.set_visible(not capture)
            self.mouse_captured = capture

    @staticmethod
    def fullscreen_shortcut(key: int, mods: int, pg) -> bool:
        """Use Mac-friendly modifiers instead of the system-reserved F11 key."""
        return key == pg.K_RETURN and bool(mods & (pg.KMOD_CTRL | pg.KMOD_ALT))

    def handle(self) -> bool:
        pg = engine()
        for event in pg.event.get():
            if event.type == pg.QUIT:
                return False
            if event.type == pg.WINDOWFOCUSLOST:
                self.focused = False
                if self.current() == "play":
                    self.paused = True  # Don't die while switching to another app.
                self.release_mouse()
            elif event.type == pg.WINDOWFOCUSGAINED:
                self.focused = True
            elif event.type == pg.KEYDOWN and self.fullscreen_shortcut(event.key, event.mod, pg):
                self.set_fullscreen(not self.fullscreen)
        self.keys = pg.key.get_pressed()
        mode = self.current()
        buttons = pg.mouse.get_pressed(3)
        self.want_scan = mode == "play" and (
            self.edge(pg.K_f)
            or self.edge(pg.K_LSHIFT)
            or self.edge(pg.K_RSHIFT)
            or (buttons[2] and not self.prev_right)
        )
        if mode == "title":
            if (self.edge(pg.K_RETURN) and not (pg.key.get_mods() & (pg.KMOD_ALT | pg.KMOD_CTRL))) or self.edge(pg.K_SPACE):
                self.session = sim.Session(self.seed, self.start_level)
                self.reset_fx()
            elif self.edge(pg.K_q) or self.edge(pg.K_ESCAPE):
                return False
        elif mode == "brief":
            if (self.edge(pg.K_RETURN) and not (pg.key.get_mods() & (pg.KMOD_ALT | pg.KMOD_CTRL))) or self.edge(pg.K_SPACE):
                self.session.mount()
                self.reset_fx()
            elif self.edge(pg.K_ESCAPE):
                self.session = None
            elif self.edge(pg.K_q):
                return False
        elif mode == "play":
            if self.edge(pg.K_ESCAPE) or self.edge(pg.K_p):
                self.paused = True
            elif self.edge(pg.K_m):
                self.audio.toggle()
            elif self.edge(pg.K_n) and self.audio.score:
                self.audio.score.enabled = not self.audio.score.enabled
        elif mode == "pause":
            if self.edge(pg.K_ESCAPE) or self.edge(pg.K_p):
                self.paused = False
            elif self.edge(pg.K_r):
                self.session.retry()
                self.paused = False
                self.reset_fx()
            elif self.edge(pg.K_m):
                self.audio.toggle()
            elif self.edge(pg.K_n) and self.audio.score:
                self.audio.score.enabled = not self.audio.score.enabled
            elif self.edge(pg.K_q):
                return False
        elif mode == "crash":
            if self.edge(pg.K_r) or self.edge(pg.K_RETURN):
                self.session.retry()
                self.reset_fx()
            elif self.edge(pg.K_q) or self.edge(pg.K_ESCAPE):
                return False
        elif mode == "win":
            if self.edge(pg.K_RETURN):
                self.session.restart()
                self.seed = self.session.seed
                self.reset_fx()
            elif self.edge(pg.K_n):
                self.session.restart(random.SystemRandom().randrange(sim.MASK64 + 1))
                self.seed = self.session.seed
                self.reset_fx()
            elif self.edge(pg.K_q) or self.edge(pg.K_ESCAPE):
                return False
        self.prev_down = {code for code in self._watched(pg) if self.keys[code]}
        self.prev_right = pg.mouse.get_pressed(3)[2]
        self.sync_mouse_capture()
        return True

    def _watched(self, pg) -> tuple[int, ...]:
        return (
            pg.K_RETURN, pg.K_SPACE, pg.K_ESCAPE, pg.K_q, pg.K_p, pg.K_r,
            pg.K_n, pg.K_m, pg.K_f, pg.K_LSHIFT, pg.K_RSHIFT,
        )

    def edge(self, code: int) -> bool:
        return bool(self.keys[code]) and code not in self.prev_down

    def update(self, dt: float) -> None:
        mode = self.current()
        if mode == "play":
            self.now += dt
            self._step_play(dt)
        elif mode != "pause":
            self.now += dt
            self._fade_fx(dt)
        self.shake = max(0.0, self.shake - dt * 16)
        if self.audio.score:
            if self.session and mode in ("play", "pause", "brief", "crash", "win"):
                world = self.session.world
                player = world.player
                close = sum(1 for enemy in world.enemies
                            if enemy.alive and (enemy.x - player.x) ** 2 +
                            (enemy.y - player.y) ** 2 < 230 ** 2)
                if world.secured:
                    # After the threat is contained, the restless percussion
                    # fades as the residual corruption is restored.
                    threat = (0.38 * world.restoration_remaining() /
                              max(1, world.restoration_total))
                else:
                    threat = min(1.0, close / 3 + (1 - player.hp / 100) * .35)
                self.audio.score.sync(self.session.seed, self.session.level,
                                      mode == "play", threat, self.audio.enabled)
            else:
                self.audio.score.ambient.set_volume(0)
                self.audio.score.danger.set_volume(0)

    def _step_play(self, dt: float) -> None:
        pg = engine()
        assert self.session is not None
        keys = self.keys
        dx = float(keys[pg.K_d] or keys[pg.K_RIGHT]) - float(keys[pg.K_a] or keys[pg.K_LEFT])
        dy = float(keys[pg.K_s] or keys[pg.K_DOWN]) - float(keys[pg.K_w] or keys[pg.K_UP])
        mx, my = pg.mouse.get_pos()
        cam = self.cam()
        buttons = pg.mouse.get_pressed(3)
        if self.arm > 0:
            self.arm = max(0.0, self.arm - dt)
        fire = self.arm <= 0 and bool(buttons[0] or keys[pg.K_SPACE])
        self.session.step(dt, sim.Input(dx, dy, mx + cam[0], my + cam[1], fire, self.want_scan))
        self.want_scan = False
        self._take_events()
        self._fade_fx(dt)
        player = self.session.world.player
        self.trail.append((player.x, player.y))
        self.trail = self.trail[-6:]
        if self.session.mode != "play":
            self.paused = False

    def _take_events(self) -> None:
        assert self.session is not None
        world = self.session.world
        events = world.events
        world.events = []
        for event in events:
            kind = event[0]
            if kind == "fire":
                self.audio.play("fire")
            elif kind == "scan":
                self.audio.play("scan")
                self.rings.append([event[1], event[2], 0.0])
            elif kind == "alert":
                self.alerts.append([event[1], event[2], 0.0])
            elif kind == "reveal":
                self.audio.play("reveal")
            elif kind == "kill":
                self.audio.play("kill")
                self._burst(event[2], event[3], KIND_COLOR.get(event[1], WHITE))
                self.feed.append([sim.NAMES[event[1]], 2.6])
            elif kind == "hurt":
                self.audio.play("hurt")
                self.shake = 6
            elif kind == "exit":
                self.audio.play("exit")
            elif kind == "clear":
                self.audio.play("clear")
            elif kind == "crash":
                self.audio.play("crash")
                self.shake = 8
            elif kind == "lock":
                self.audio.play("lock")

    def _burst(self, x: float, y: float, color: tuple[int, int, int]) -> None:
        rng = random.Random((int(x) << 8) ^ int(y) ^ int(self.now * 1000))
        for _ in range(9):
            ang = rng.random() * math.tau
            speed = rng.uniform(30, 150)
            self.sparks.append([x, y, math.cos(ang) * speed, math.sin(ang) * speed, 0.38, color])

    def _fade_fx(self, dt: float) -> None:
        for ring in self.rings:
            ring[2] += dt
        self.rings = [ring for ring in self.rings if ring[2] < 0.48]
        for alert in self.alerts:
            alert[2] += dt
        self.alerts = [alert for alert in self.alerts if alert[2] < 0.9]
        for spark in self.sparks:
            spark[0] += spark[2] * dt
            spark[1] += spark[3] * dt
            spark[4] -= dt
        self.sparks = [spark for spark in self.sparks if spark[4] > 0]
        for item in self.feed:
            item[1] -= dt
        self.feed = [item for item in self.feed if item[1] > 0][-4:]

    def reset_fx(self) -> None:
        self.rings.clear()
        self.alerts.clear()
        self.sparks.clear()
        self.feed.clear()
        self.trail.clear()
        self.shake = 0.0
        self.arm = 0.15
        self.map_surface = None
        self.map_key = None
        self.layer = None

    def cam(self) -> tuple[float, float]:
        assert self.session is not None
        mag = self.shake
        shake = (0.0, 0.0)
        if mag:
            shake = (math.sin(self.now * 42) * mag, math.cos(self.now * 35) * mag)
        return camera_of(self.session.world, shake)

    def draw(self) -> None:
        mode = self.current()
        if mode == "title":
            self.draw_title()
        else:
            self.draw_world()
            if mode == "play":
                self.draw_hud()
                self.draw_crosshair()
            else:
                self.veil(160)
                if mode == "brief":
                    self.draw_brief()
                elif mode == "pause":
                    self.draw_pause()
                elif mode == "crash":
                    self.draw_crash()
                elif mode == "win":
                    self.draw_win()
        self.frame()

    def draw_title(self) -> None:
        pg = engine()
        self.paint_code_field()
        pg.draw.rect(self.screen, BG, (0, 0, 730, VIEW_H))
        pg.draw.line(self.screen, (28, 52, 64), (730, 36), (730, VIEW_H - 36), 1)
        fonts = self.fonts
        tracked(self.screen, fonts["logo"], "AEGIS SENTINEL", 56, 86, CYAN, 3)
        blit(self.screen, fonts["body"], "resident antivirus", 58, 156, CYAN_DIM)
        pg.draw.line(self.screen, CYAN_DIM, (58, 196), (430, 196), 1)
        lines = (
            "You are the scanner inside the machine.",
            "Processes keep running until an infection takes them.",
            "Purge it, and leave the system able to work.",
        )
        y = 220
        for line in lines:
            blit(self.screen, fonts["body"], line, 58, y, WHITE)
            y += 28
        y = 340
        controls = (
            ("WASD  arrows", "move"),
            ("mouse", "aim"),
            ("click  space", "purge"),
            ("shift  F", "scan"),
            ("esc", "pause"),
            ("M", "sound"),
            ("N", "music"),
        )
        for key, action in controls:
            blit(self.screen, fonts["small"], key, 58, y, CYAN)
            blit(self.screen, fonts["small"], action, 250, y, DIM)
            y += 28
        spec = sim.PROCESSES[self.start_level - 1]
        blit(self.screen, fonts["body"], f"Enter   mount {spec.path}", 58, 560, GREEN)
        blit(self.screen, fonts["small"], "Q   quit     Ctrl+Enter   fullscreen / window", 58, 598, DIM)
        blit(self.screen, fonts["tiny"], f"seed {self.seed}", 58, 742, CYAN_DIM)
        self.draw_legend()

    def draw_legend(self) -> None:
        pg = engine()
        rect = pg.Rect(760, 86, 470, 620)
        panel(self.screen, rect, CYAN_DIM)
        blit(self.screen, self.fonts["small"], "SIGNATURES", 788, 108, CYAN_DIM)
        rows = (
            ("worm", "WORM.BIN", "Replicates, and the copies corrupt nearby memory.", True),
            ("trojan", "TROJAN.COM", "Looks like an ordinary file until a scan exposes it.", False),
            ("spyware", "SPY.DLL", "Watches you and calls the other processes over.", True),
            ("ransom", "LOCK.EXE", "Locks the room it is in. The room opens again.", True),
        )
        y = 160
        for kind, name, blurb, awake in rows:
            enemy = self._icon(kind, awake)
            paint_enemy(self.screen, enemy, 830, y + 18, self.now, self.fonts["tiny"])
            blit(self.screen, self.fonts["small"], name, 880, y, KIND_COLOR[kind])
            for line in wrap(self.fonts["tiny"], blurb, 300):
                y += 18
                blit(self.screen, self.fonts["tiny"], line, 880, y, DIM)
            y += 58
        kernel = "KERNEL is the protected center. POLY.SYS fails the system while it lives."
        y = 640
        for line in wrap(self.fonts["tiny"], kernel, 410):
            blit(self.screen, self.fonts["tiny"], line, 788, y, RED)
            y += 16

    def _icon(self, kind: str, awake: bool) -> sim.Enemy:
        stat = sim.STATS[kind]
        return sim.Enemy(
            kind=kind,
            x=0,
            y=0,
            radius=stat["radius"],
            hp=stat["hp"],
            max_hp=stat["hp"],
            speed=stat["speed"],
            damage=stat["damage"],
            awake=awake,
            facing=-0.4,
            cover="cache.rs" if kind == "trojan" and not awake else "",
        )

    def paint_code_field(self) -> None:
        pg = engine()
        self.screen.fill(BG)
        font = self.fonts["byte"]
        tint = (36, 78, 62)
        hot = lift(tint, 140)
        sweep = int(self.now * 10) % (VIEW_W // sim.CELL + 1)
        for r in range(VIEW_H // sim.CELL + 1):
            for c in range(VIEW_W // sim.CELL + 1):
                text, mix = cell_byte(c, r, self.seed)
                color = hot if abs(c - sweep) <= 1 or mix % 19 == 0 else tint
                image = self.glyph(text, color)
                self.screen.blit(image, (c * sim.CELL + 8, r * sim.CELL + 12))
        band = pg.Surface((VIEW_W, 3), pg.SRCALPHA)
        band.fill((160, 230, 190, 30))
        self.screen.blit(band, (0, int(self.now * 70) % VIEW_H))

    def draw_world(self) -> None:
        assert self.session is not None
        pg = engine()
        world = self.session.world
        cam_x, cam_y = self.cam()
        self.screen.fill(BG)
        if self.layer is None or self.layer.world is not world:
            self.layer = MapLayer(self, world)
        layer = self.layer
        layer.sync()
        self.screen.blit(layer.surface, (-math.ceil(cam_x), -math.ceil(cam_y)))
        c0 = max(0, int(cam_x // sim.CELL) - 1)
        r0 = max(0, int(cam_y // sim.CELL) - 1)
        c1 = min(sim.COLS, int((cam_x + VIEW_W) // sim.CELL) + 2)
        r1 = min(sim.ROWS, int((cam_y + VIEW_H) // sim.CELL) + 2)
        if self.flash_wash is None:
            self.flash_wash = pg.Surface((sim.CELL, sim.CELL), pg.SRCALPHA)
            self.flash_wash.fill((170, 40, 80, 110))
        for c, r, _life in world.flashes:
            if c0 <= c < c1 and r0 <= r < r1 and layer.is_floor(c, r):
                self.screen.blit(self.flash_wash, (int(c * sim.CELL - cam_x), int(r * sim.CELL - cam_y)))
        # The bright sweep moves every frame, so it is drawn over the layer.
        sweep = int(self.now * 9) % sim.COLS
        for c in range(max(c0, sweep - 1), min(c1, sweep + 2)):
            for r in range(r0, r1):
                if not layer.is_floor(c, r):
                    continue
                text, mix = cell_byte(c, r, world.seed)
                if mix % 17 == 0:
                    continue
                image = self.glyph(text, layer.hot)
                sx = int(c * sim.CELL - cam_x)
                sy = int(r * sim.CELL - cam_y)
                self.screen.blit(image, image.get_rect(center=(sx + sim.CELL // 2, sy + sim.CELL // 2)))
        # Damaged cells pulse more visibly after combat, when restoration is optional.
        if world.secured and world.restoration_remaining():
            bright = int(65 + 55 * (0.5 + 0.5 * math.sin(self.now * 3.4)))
            for r in range(r0, r1):
                for c in range(c0, c1):
                    if world.tile[r][c] in (sim.LATENT, sim.CORRUPT):
                        sx, sy = int(c * sim.CELL - cam_x), int(r * sim.CELL - cam_y)
                        pg.draw.rect(self.screen, (bright + 80, 70, 65),
                                     (sx + 5, sy + 5, sim.CELL - 10, sim.CELL - 10), 2)
                        pg.draw.line(self.screen, (bright + 80, 90, 80),
                                     (sx + 12, sy + 12), (sx + sim.CELL - 12, sy + sim.CELL - 12), 2)
        for hx, hy, hw, hh, _life in world.held:
            wash = pg.Surface((hw * sim.CELL, hh * sim.CELL), pg.SRCALPHA)
            wash.fill((180, 110, 32, 36))
            self.screen.blit(wash, (int(hx * sim.CELL - cam_x), int(hy * sim.CELL - cam_y)))
        self._paint_traffic(world, cam_x, cam_y)
        label_font = self.fonts["tiny"]
        for name, x, y in world.labels:
            sx = int(x - cam_x)
            sy = int(y - cam_y)
            width, height = label_font.size(name)
            pg.draw.rect(self.screen, (6, 14, 16), (sx - 3, sy - 2, width + 6, height + 4))
            blit(self.screen, label_font, name, sx, sy, (120, 186, 150))
        for decoy in world.decoys:
            sx = int(decoy.x - cam_x)
            sy = int(decoy.y - cam_y)
            if decoy.checked:
                _paint_checked(self.screen, decoy.name, sx, sy, label_font)
            else:
                _paint_cover(self.screen, decoy.name, sx, sy, label_font)
        # A rare repair node is guarded by ransomware rather than dropped at random.
        module = world.repair_module
        if module is not None:
            mx = int(module.x - cam_x)
            my = int(module.y - cam_y)
            pulse = 0.5 + 0.5 * math.sin(self.now * 4.2)
            teal = (62, 210, 179)
            pg.draw.circle(self.screen, (14, 56, 57), (mx, my), 21)
            pg.draw.circle(self.screen, teal, (mx, my), 16 + int(2 * pulse), 2)
            pg.draw.polygon(self.screen, (21, 90, 87), [
                (mx, my - 13), (mx + 12, my - 6), (mx + 12, my + 6),
                (mx, my + 13), (mx - 12, my + 6), (mx - 12, my - 6),
            ])
            pg.draw.line(self.screen, (170, 255, 225), (mx - 7, my), (mx + 7, my), 4)
            pg.draw.line(self.screen, (170, 255, 225), (mx, my - 7), (mx, my + 7), 4)
            blit(self.screen, label_font, "+25", mx - 10, my - 31, teal)
        self._paint_exit(world, cam_x, cam_y)
        for ring in self.rings:
            radius = int(ring[2] / 0.48 * sim.SCAN_RADIUS)
            if radius > 0:
                pg.draw.circle(
                    self.screen,
                    CYAN,
                    (int(ring[0] - cam_x), int(ring[1] - cam_y)),
                    radius,
                    1,
                )
        for alert in self.alerts:
            radius = int(22 + alert[2] / 0.9 * 34)
            pg.draw.circle(
                self.screen,
                (186, 92, 64),
                (int(alert[0] - cam_x), int(alert[1] - cam_y)),
                radius,
                2,
            )
        if self.current() == "play":
            for index, (x, y) in enumerate(self.trail):
                pg.draw.circle(
                    self.screen,
                    (20, 50, 62),
                    (int(x - cam_x), int(y - cam_y)),
                    4 + index,
                    1,
                )
        for shot in world.shots:
            self._paint_shot(shot, cam_x, cam_y)
        for enemy in world.enemies:
            if enemy.alive:
                paint_enemy(
                    self.screen,
                    enemy,
                    int(enemy.x - cam_x),
                    int(enemy.y - cam_y),
                    self.now,
                    self.fonts["tiny"],
                )
        for spark in self.sparks:
            sx = int(spark[0] - cam_x)
            sy = int(spark[1] - cam_y)
            pg.draw.rect(self.screen, spark[5], (sx, sy, 3, 3))
        player = world.player
        paint_player(self.screen, player, int(player.x - cam_x), int(player.y - cam_y), self.now)
        for pop in world.pops:
            color = GREEN if pop.kind == "kill" else AMBER if pop.kind == "reveal" else CYAN
            width, _height = self.fonts["tiny"].size(pop.text)
            blit(self.screen, self.fonts["tiny"], pop.text, int(pop.x - cam_x - width / 2), int(pop.y - cam_y), color)

    def _paint_traffic(self, world: sim.World, cam_x: float, cam_y: float) -> None:
        pg = engine()
        font = self.fonts["tiny"]
        for carrier in world.carriers:
            if not carrier.cells:
                continue
            c, r = carrier.cells[carrier.index]
            x, y = sim.cell_center(c, r)
            pace = 0.22 if carrier.name == "" else 0.55
            nxt = carrier.index + carrier.forward
            if not carrier.halted and 0 <= nxt < len(carrier.cells):
                slide = min(1.0, carrier.step / pace)
                nx, ny = sim.cell_center(*carrier.cells[nxt])
                x += (nx - x) * slide
                y += (ny - y) * slide
            sx, sy = int(x - cam_x), int(y - cam_y)
            if carrier.name == "":
                color = (70, 78, 88) if carrier.halted else (150, 214, 232)
                pg.draw.circle(self.screen, color, (sx, sy), 4, 1)
                if not carrier.halted:
                    pg.draw.circle(self.screen, (210, 244, 250), (sx, sy), 2)
                if carrier.halted:
                    pg.draw.line(self.screen, (120, 64, 78), (sx - 4, sy - 4), (sx + 4, sy + 4), 1)
                    pg.draw.line(self.screen, (120, 64, 78), (sx - 4, sy + 4), (sx + 4, sy - 4), 1)
                continue
            color = (90, 78, 78) if carrier.halted else (150, 176, 168)
            width, height = font.size(carrier.name)
            pg.draw.rect(self.screen, (6, 14, 16), (sx - 2, sy - 1, width + 4, height + 2))
            blit(self.screen, font, carrier.name, sx, sy, color)

    def _paint_exit(self, world: sim.World, cam_x: float, cam_y: float) -> None:
        pg = engine()
        sx = int(world.exit_x - cam_x)
        sy = int(world.exit_y - cam_y)
        open_exit = world.exit_open
        pulse = 0.7 + 0.3 * math.sin(self.now * 4) if open_exit else 0.55
        base = GREEN if open_exit else (90, 98, 108)
        color = tuple(int(channel * pulse) for channel in base)
        rect = pg.Rect(sx - 28, sy - 10, 56, 34)
        tab = [(sx - 28, sy - 10), (sx - 28, sy - 20), (sx - 6, sy - 20), (sx + 2, sy - 10)]
        pg.draw.polygon(self.screen, color, tab)
        pg.draw.rect(self.screen, color, rect, border_radius=3)
        pg.draw.rect(self.screen, INK, (sx - 22, sy - 2, 44, 16), border_radius=2)
        label = "EXIT / RESTORE" if open_exit and world.restoration_remaining() else "CLEAN.EXIT" if open_exit else "LOCKED"
        width, _height = self.fonts["tiny"].size(label)
        blit(self.screen, self.fonts["tiny"], label, sx - width // 2, sy + 28, color)

    def _paint_shot(self, shot: sim.Shot, cam_x: float, cam_y: float) -> None:
        pg = engine()
        sx, sy = int(shot.x - cam_x), int(shot.y - cam_y)
        px, py = int(shot.px - cam_x), int(shot.py - cam_y)
        if shot.friendly:
            pg.draw.line(self.screen, CYAN, (px, py), (sx, sy), 3)
            pg.draw.circle(self.screen, WHITE, (sx, sy), 3)
        else:
            pg.draw.line(self.screen, RED, (px, py), (sx, sy), 2)
            pg.draw.rect(self.screen, RED, (sx - 4, sy - 4, 8, 8))

    def draw_hud(self) -> None:
        assert self.session is not None
        world = self.session.world
        font = self.fonts["tiny"]
        spec = world.spec
        pg = engine()
        dock_y = VIEW_H - DOCK_H
        plate(self.screen, pg.Rect(0, dock_y, VIEW_W, DOCK_H))
        stats_y = dock_y + 8
        x = 20

        def text(msg: str, color: tuple[int, int, int], gap: int = 16) -> None:
            nonlocal x
            width, _height = blit(self.screen, font, msg, x, stats_y, color)
            x += width + gap

        text(spec.path, DIM)
        text(sim.address(*world.player_cell()), CYAN_DIM, 20)
        text("INTEGRITY", DIM, 8)
        integrity = world.player.hp / 100
        fill = GREEN if world.player.hp > 40 else AMBER if world.player.hp > 20 else RED
        bar(self.screen, x, stats_y + 3, 84, 10, integrity, fill)
        x += 90
        text(str(world.player.hp), fill, 18)
        text("SCAN", DIM, 8)
        bar(self.screen, x, stats_y + 3, 84, 10, world.player.scan / 100, CYAN)
        x += 100
        threats = world.threat_count()
        text(f"THREATS {threats}", RED if threats else GREEN, 12)
        if world.secured and world.restoration_total:
            text(f"RESTORE {world.restoration_cleaned}/{world.restoration_total}",
                 GREEN if world.restoration_remaining() == 0 else AMBER, 0)
        if world.weapons_locked():
            text("  PURGE JAMMED", RED, 0)

        score = self.session.score + world.kills_score
        right_bits = (
            (f"SCORE {score}", WHITE),
            (f"{self.session.level}/{len(sim.PROCESSES)}  {spec.title}", CYAN_DIM),
            (format_time(self.session.play_time), DIM),
        )
        gap = 16
        total = sum(font.size(msg)[0] for msg, _color in right_bits) + gap * (len(right_bits) - 1)
        rx = max(x + 16, VIEW_W - 20 - total)
        for msg, color in right_bits:
            width, _height = blit(self.screen, font, msg, rx, stats_y, color)
            rx += width + gap

        hint = ("THREATS CLEARED — scan damaged cells to restore, or use exit"
                if world.secured and world.restoration_remaining()
                else "SECTOR RESTORED — exit when ready"
                if world.secured and world.restoration_total
                else "PURGE JAMMED — scan or evade until lockdown ends" if world.weapons_locked()
                else "WASD move     mouse aim     click purge     shift scan     esc pause")
        hint_w, _height = font.size(hint)
        controls_y = dock_y + 32
        blit(self.screen, font, hint, (VIEW_W - hint_w) // 2, controls_y, CYAN)
        blit(self.screen, font, f"seed {self.session.seed}", 20, controls_y, CYAN_DIM)
        if not self.audio.enabled:
            blit_right(self.screen, font, "MUTE", VIEW_W - 20, controls_y, AMBER)
        if world.level == len(sim.PROCESSES) and not world.arena:
            sys_color = GREEN if world.system > 40 else AMBER if world.system > 15 else RED
            right = VIEW_W - 20
            if not self.audio.enabled:
                right -= font.size("MUTE")[0] + 18
            value = str(int(world.system))
            value_w = font.size(value)[0]
            bar_w = 72
            label_w = font.size("SYS")[0]
            left = right - (label_w + 8 + bar_w + 8 + value_w)
            blit(self.screen, font, "SYS", left, controls_y, DIM)
            bar(self.screen, left + label_w + 8, controls_y + 3, bar_w, 10, world.system / 100, sys_color)
            blit(self.screen, font, value, left + label_w + 8 + bar_w + 8, controls_y, sys_color)

        self.draw_minimap()
        lines = self.feed[-3:]
        if lines:
            feed_h = 18 * len(lines) + 8
            top = dock_y - 12 - feed_h
            plate(self.screen, pg.Rect(16, top, 248, feed_h))
            for index, item in enumerate(lines):
                blit(self.screen, font, f"purged {item[0]}", 28, top + 6 + index * 18, GREEN)

    def draw_minimap(self) -> None:
        assert self.session is not None
        pg = engine()
        world = self.session.world
        scale = 4
        if self.map_key != world.map_rev:
            mini = pg.Surface((sim.COLS * scale, sim.ROWS * scale))
            mini.fill(BG)
            for r in range(sim.ROWS):
                for c in range(sim.COLS):
                    kind = world.tile[r][c]
                    if kind == sim.CORRUPT:
                        color = (150, 48, 84)
                    elif kind == sim.LATENT and world.secured:
                        color = (180, 105, 65)
                    elif kind == sim.SEAL:
                        color = (190, 140, 48)
                    elif kind == sim.GATE:
                        color = (46, 140, 158)
                    elif world.solid[r][c]:
                        color = WALL
                    else:
                        color = (16, 28, 40)
                    pg.draw.rect(mini, color, (c * scale, r * scale, scale, scale))
            self.map_surface = mini
            self.map_key = world.map_rev
        width = sim.COLS * scale
        height = sim.ROWS * scale
        origin_x = VIEW_W - width - 24
        dock_y = VIEW_H - DOCK_H
        origin_y = dock_y - height - 16
        # Run the plate to the screen edge and the dock so floor glyphs
        # cannot show in the corner beside the map.
        plate(
            self.screen,
            pg.Rect(origin_x - 8, origin_y - 8, VIEW_W - (origin_x - 8), dock_y - (origin_y - 8)),
        )
        self.screen.blit(self.map_surface, (origin_x, origin_y))
        exit_color = GREEN if world.exit_open else (70, 78, 88)
        pg.draw.rect(
            self.screen,
            exit_color,
            (origin_x + world.exit_cell[0] * scale, origin_y + world.exit_cell[1] * scale, scale, scale),
        )
        for enemy in world.enemies:
            if not enemy.alive or not (enemy.awake or enemy.marked):
                continue
            c = int(enemy.x // sim.CELL)
            r = int(enemy.y // sim.CELL)
            color = KIND_COLOR.get(enemy.kind, RED)
            if not enemy.awake:
                color = (150, 86, 110)
            pg.draw.rect(
                self.screen,
                color,
                (origin_x + c * scale, origin_y + r * scale, scale, scale),
            )
        if world.repair_module is not None:
            c = int(world.repair_module.x // sim.CELL)
            r = int(world.repair_module.y // sim.CELL)
            pg.draw.rect(self.screen, (62, 210, 179),
                         (origin_x + c * scale, origin_y + r * scale, scale, scale))
        pc, pr = world.player_cell()
        pg.draw.rect(self.screen, CYAN, (origin_x + pc * scale, origin_y + pr * scale, scale, scale))

    def draw_crosshair(self) -> None:
        pg = engine()
        mx, my = pg.mouse.get_pos()
        pg.draw.circle(self.screen, CYAN, (mx, my), 8, 1)
        pg.draw.line(self.screen, CYAN, (mx - 12, my), (mx - 4, my), 1)
        pg.draw.line(self.screen, CYAN, (mx + 4, my), (mx + 12, my), 1)
        pg.draw.line(self.screen, CYAN, (mx, my - 12), (mx, my - 4), 1)
        pg.draw.line(self.screen, CYAN, (mx, my + 4), (mx, my + 12), 1)

    def veil(self, alpha: int) -> None:
        pg = engine()
        shade = pg.Surface((VIEW_W, VIEW_H), pg.SRCALPHA)
        shade.fill((4, 6, 10, alpha))
        self.screen.blit(shade, (0, 0))

    def draw_brief(self) -> None:
        assert self.session is not None
        session = self.session
        world = session.world
        rect = engine().Rect(300, 150, 680, 460)
        panel(self.screen, rect, CYAN)
        fonts = self.fonts
        blit(self.screen, fonts["tiny"], f"PROCESS {session.level} OF {len(sim.PROCESSES)}", 332, 176, CYAN_DIM)
        blit(self.screen, fonts["head"], world.spec.title, 332, 204, WHITE)
        blit(self.screen, fonts["small"], world.spec.path, 332, 250, CYAN)
        y = 300
        for line in wrap(fonts["body"], world.spec.tip, 600):
            blit(self.screen, fonts["body"], line, 332, y, WHITE)
            y += 28
        y += 16
        blit(self.screen, fonts["small"], f"threats     {world.threat_count()}", 332, y, RED)
        blit(self.screen, fonts["small"], f"integrity   {session.integrity}", 332, y + 28, GREEN)
        if session.cleared_name:
            blit(
                self.screen,
                fonts["small"],
                f"{session.cleared_name} clean    +{session.last_bonus}",
                332,
                y + 64,
                GREEN,
            )
        blit(self.screen, fonts["body"], "Enter   mount", 332, 530, GREEN)
        blit(self.screen, fonts["small"], "Esc title     Q quit", 520, 534, DIM)

    def draw_pause(self) -> None:
        assert self.session is not None
        rect = engine().Rect(390, 220, 500, 320)
        panel(self.screen, rect, CYAN)
        fonts = self.fonts
        blit(self.screen, fonts["head"], "PAUSED", 422, 250, WHITE)
        blit(self.screen, fonts["body"], "Esc      resume", 422, 320, CYAN)
        blit(self.screen, fonts["body"], "R        retry this process", 422, 356, WHITE)
        blit(self.screen, fonts["body"], "M        sound     N   music", 422, 392, WHITE)
        blit(self.screen, fonts["body"], "Q        quit", 422, 428, WHITE)
        sound = "on" if self.audio.enabled else "off"
        music = "on" if self.audio.score and self.audio.score.enabled else "off"
        blit(self.screen, fonts["tiny"], f"seed {self.session.seed}    sound {sound}    music {music}", 422, 490, CYAN_DIM)

    def draw_crash(self) -> None:
        assert self.session is not None
        session = self.session
        rect = engine().Rect(340, 180, 600, 420)
        panel(self.screen, rect, RED)
        fonts = self.fonts
        blit(self.screen, fonts["head"], "AEGIS SENTINEL HALTED", 372, 210, RED)
        lost_system = (
            session.world.level == len(sim.PROCESSES)
            and session.world.system <= 0
            and session.world.player.hp > 0
        )
        reason = "The kernel lost the system." if lost_system else "Integrity reached 0."
        blit(self.screen, fonts["body"], reason, 372, 268, WHITE)
        blit(self.screen, fonts["small"], f"process    {session.world.spec.title}", 372, 320, DIM)
        blit(self.screen, fonts["small"], f"threats    {session.world.threat_count()}", 372, 348, DIM)
        blit(self.screen, fonts["small"], f"score      {session.score}", 372, 376, DIM)
        blit(self.screen, fonts["tiny"], "Kills in this process were not kept.", 372, 414, AMBER)
        blit(self.screen, fonts["body"], "R    retry this process", 372, 470, GREEN)
        blit(self.screen, fonts["body"], "Q    quit", 372, 508, WHITE)

    def draw_win(self) -> None:
        assert self.session is not None
        session = self.session
        rect = engine().Rect(330, 150, 620, 480)
        panel(self.screen, rect, GREEN)
        fonts = self.fonts
        blit(self.screen, fonts["head"], "SYSTEM CLEAN", 362, 180, GREEN)
        blit(self.screen, fonts["body"], "The address space is quiet.", 362, 236, WHITE)
        rows = (
            ("score", str(session.score)),
            ("integrity", str(session.integrity)),
            ("time", format_time(session.play_time)),
            ("seed", str(session.seed)),
        )
        y = 290
        for label, value in rows:
            blit(self.screen, fonts["small"], label, 362, y, DIM)
            blit(self.screen, fonts["small"], value, 520, y, WHITE)
            y += 32
        blit(self.screen, fonts["body"], "Enter    run this seed again", 362, 470, GREEN)
        blit(self.screen, fonts["body"], "N        new seed", 362, 508, CYAN)
        blit(self.screen, fonts["body"], "Q        quit", 362, 546, WHITE)

    def frame(self) -> None:
        engine().draw.rect(self.screen, (24, 42, 56), (10, 10, VIEW_W - 20, VIEW_H - 20), 1)

    def glyph(self, text: str, color: tuple[int, int, int]):
        key = (text, color)
        image = self.cache.get(key)
        if image is None:
            image = self.fonts["byte"].render(text, True, color)
            self.cache[key] = image
        return image


def play(opts: Options) -> int:
    pg = engine()
    pg.init()
    pg.display.set_caption("AEGIS Sentinel")
    try:
        flags = pg.SCALED | (pg.FULLSCREEN if opts.fullscreen else 0)
        screen = pg.display.set_mode((VIEW_W, VIEW_H), flags)
    except pg.error as err:
        print(f"antivirus.py: {err}", file=sys.stderr)
        return 1
    seed = opts.seed if opts.seed is not None else random.SystemRandom().randrange(sim.MASK64 + 1)
    app = App(screen, seed, opts.level, opts.mute, opts.fullscreen)
    try:
        return app.run()
    finally:
        app.release_mouse()
        pg.quit()


def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    if argv is None:
        argv = sys.argv
    try:
        opts = parse_args(argv)
    except UsageError as err:
        print(f"antivirus.py: {err}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2
    if opts.help:
        print(__doc__.rstrip("\n"))
        return 0
    if opts.check:
        return run_checks()
    try:
        engine()
    except ImportError:
        print("antivirus.py: pygame is not installed for this Python.", file=sys.stderr)
        print("Double-click Antivirus.command. It looks for Python 3.9", file=sys.stderr)
        print("through 3.13 and installs pygame there. pygame 2.6 has", file=sys.stderr)
        print("macOS wheels for those versions and does not build on 3.14 or 3.15.", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 1
    try:
        return play(opts)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
