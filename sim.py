#!/usr/bin/env python3
"""Rules for AEGIS Sentinel. The window is elsewhere. This file opens nothing.

A process is a room-and-hall map of packed pages and live memory. The
player is the scanner. Malicious code is a process too: it replicates,
hides, locks a region, and calls the others in. CLEAN.EXIT opens when
nothing hostile is left.
"""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field

MASK64 = (1 << 64) - 1
CELL = 40
COLS = 48
ROWS = 32
WIDTH_PX = COLS * CELL
HEIGHT_PX = ROWS * CELL
DT_MAX = 1 / 30

PLAYER_SPEED = 230
PLAYER_RADIUS = 12
IFRAMES = 0.8
REPAIR = 17
MODULE_REPAIR = 25
MODULE_CHANCE = 0.45  # Checked only in processes containing ransomware.
MODULE_RADIUS = 18
CLEAR_BONUS = 500
INTEGRITY_BONUS = 5
RESTORE_PARTIAL_SCORE = 300
RESTORE_COMPLETE_SCORE = 800
RESTORE_COMPLETE_HP = 5

SCAN_COST = 36.0
SCAN_REGEN = 20.0
SCAN_RADIUS = 180.0
SCAN_GAP = 0.28
SLOW_TIME = 1.15
SLOW_FACTOR = 0.45

FIRE_GAP = 0.2
BOLT_SPEED = 820.0
BOLT_LIFE = 0.46
PACKET_SPEED = 175.0
PACKET_LIFE = 2.8
PACKET_DAMAGE = 9

TROJAN_WAKE = 64.0
TROJAN_DASH_SPEED = 260.0
TROJAN_DASH_TIME = 0.22
TROJAN_DASH_CD = 1.5

RANSOM_RADIUS = 90.0
RANSOM_BLAST = 16
PULSE_TIME = 1.15
ROUTE_REFRESH = 0.3

# Tile kinds. PACKED, SEAL, GATE, and CORRUPT block movement. LATENT is still floor.
OPEN = 0
PACKED = 1
LATENT = 2
SEAL = 3
CORRUPT = 4
GATE = 5

CORRUPT_EVERY = 4.0
LATENT_LIFE = 6.0
WORM_SEALS = 2
# How long a ransomware region stays shut. The pulse can repeat sooner;
# LOCK_GAP keeps the same room from locking on every pulse.
SEAL_TIME = 4.0
LOCK_GAP = 8.0
UNSTABLE_OPEN = 6.5
UNSTABLE_SHUT = 1.5
SPREAD_EVERY = 3.2
SPREAD_BOSS = 1.6
MAX_TAINT = 16
ALERT_TIME = 6.0
MEMORY_TIME = 4.5
SYSTEM_DRAIN = 1.6
SYSTEM_HARDEN = 6.0
SYSTEM_CLEAN = 4.0

# The kernel boss speeds up and sprays wider as it loses HP.
BOSS_RAGE_SPEED = 0.6
BOSS_RAGE_CHASE = 0.45
DAEMON_REST = 0.2
BOLT_WALL = 1.0

MAX_ENEMIES = 48
WORM_CAP = 10
REPL_CAP = 16
WORM_REPLICATION_INTERVAL = 4.5
WORM_REPLICATION_LIMIT = 3

BOSS_PHASES = (
    ("chase", 2.5),
    ("spawn", 0.4),
    ("spray", 0.55),
)

NAMES = {
    "worm": "WORM.BIN",
    "trojan": "TROJAN.COM",
    "spyware": "SPY.DLL",
    "ransom": "LOCK.EXE",
    "boss": "POLY.SYS",
}
SCORES = {
    "worm": 100,
    "trojan": 150,
    "spyware": 200,
    "ransom": 350,
    "boss": 1000,
}
STATS = {
    "worm": {"radius": 13, "hp": 1, "speed": 100, "damage": 10, "awake": True},
    "trojan": {"radius": 13, "hp": 1, "speed": 84, "damage": 14, "awake": False},
    "spyware": {"radius": 12, "hp": 1, "speed": 68, "damage": 8, "awake": True},
    "ransom": {"radius": 15, "hp": 3, "speed": 52, "damage": 12, "awake": True},
    "boss": {"radius": 26, "hp": 8, "speed": 74, "damage": 18, "awake": True},
}

FILE_NAMES = (
    "main.c",
    "auth.js",
    "cache.rs",
    "boot.asm",
    "net.h",
    "parse.py",
    "io.go",
    "crypt.c",
    "dns.lua",
    "tmp.sh",
    "cfg.ini",
    "log.txt",
    "page.h",
    "user.rs",
    "notes.md",
    "photo.jpg",
    "report.pdf",
    "index.html",
    "app.swift",
    "sync.db",
    "ui.css",
    "font.ttf",
    "key.pem",
    "todo.txt",
)


@dataclass(frozen=True)
class Process:
    """One level. `rooms` is how many chambers the generator tries to cut."""

    slug: str
    title: str
    path: str
    tip: str
    worms: int
    trojans: int
    spyware: int
    ransom: int
    boss: bool
    rooms: int
    tint: tuple[int, int, int]
    # Hall cells that shut and open, harmless floor filenames, and walking daemons.
    gates: int = 0
    decoys: int = 0
    daemons: int = 2
    # Smaller rooms pack more of them, and more halls, into the same map.
    compact: bool = False


PROCESSES = (
    Process(
        "downloads",
        "DOWNLOADS",
        "~/downloads",
        "Worms corrupt nearby memory and replicate through it. Scan to quarantine a cell before it hardens.",
        8, 0, 0, 0, False, 7,
        (42, 86, 64),
    ),
    Process(
        "browser",
        "BROWSER.CACHE",
        "~/library/caches",
        "Trojans look like ordinary files, and some files are only files. A scan exposes a trojan and leaves it asleep, and marks a plain file clean. Hall gates open and close.",
        5, 6, 0, 0, False, 8,
        (36, 90, 98),
        gates=1, decoys=3,
    ),
    Process(
        "documents",
        "DOCUMENTS",
        "~/documents",
        "Ransomware seals rooms and jams your purge emitter while you are trapped inside. Scan still works. Escape or wait for the seal.",
        5, 3, 0, 2, False, 8,
        (84, 92, 44),
        gates=1, decoys=4,
    ),
    Process(
        "home",
        "HOME",
        "~",
        "Your whole home folder. More rooms and more halls than any process so far, so threats can come from any side. Keep scanning as you move.",
        6, 5, 0, 2, False, 12,
        (74, 64, 108),
        gates=2, decoys=4, compact=True,
    ),
    Process(
        "startup",
        "STARTUP",
        "~/library/launch-agents",
        "Spyware calls the other processes to your location. Access gates along the halls open and close.",
        4, 4, 5, 0, False, 8,
        (104, 84, 46),
        gates=2, decoys=3,
    ),
    Process(
        "applications",
        "APPLICATIONS",
        "/applications",
        "Every app here is running. Twice as many daemons walk the rooms, stopping and starting. Scan a filename before you trust it.",
        5, 4, 4, 2, False, 9,
        (98, 58, 92),
        gates=2, decoys=4, daemons=4,
    ),
    Process(
        "system",
        "SYSTEM32",
        "/system/library",
        "Two lockers guard the system library. Watch for two amber rings at once.",
        5, 4, 5, 3, False, 9,
        (52, 74, 112),
        gates=2, decoys=4,
    ),
    Process(
        "drivers",
        "DRIVERS",
        "/system/drivers",
        "The drivers sit beside the kernel. More access gates shut along the halls, and every kind of threat is loose.",
        6, 5, 5, 3, False, 9,
        (108, 66, 38),
        gates=4, decoys=4,
    ),
    Process(
        "kernel",
        "KERNEL",
        "/kernel",
        "This is the protected center. While POLY.SYS lives, the system fails. Clear it before the machine is lost.",
        5, 4, 4, 2, True, 8,
        (112, 52, 64),
        gates=3, decoys=4,
    ),
)


def roster(spec: Process) -> list[str]:
    kinds = (
        ["worm"] * spec.worms
        + ["trojan"] * spec.trojans
        + ["spyware"] * spec.spyware
        + ["ransom"] * spec.ransom
    )
    if spec.boss:
        kinds.append("boss")
    return kinds


def cell_center(c: int, r: int) -> tuple[float, float]:
    return c * CELL + CELL / 2, r * CELL + CELL / 2


def address(c: int, r: int) -> str:
    return f"0x{(r * COLS + c) * 16:04X}"


class Room(tuple):
    """x, y, w, h in cells. A plain tuple so the map stays easy to print."""

    def __new__(cls, x: int, y: int, w: int, h: int) -> Room:
        return tuple.__new__(cls, (x, y, w, h))

    @property
    def x(self) -> int:
        return self[0]

    @property
    def y(self) -> int:
        return self[1]

    @property
    def w(self) -> int:
        return self[2]

    @property
    def h(self) -> int:
        return self[3]


def _center(room: Room) -> tuple[int, int]:
    return room.x + room.w // 2, room.y + room.h // 2


def _overlap(a: Room, b: Room, pad: int) -> bool:
    return not (
        a.x + a.w + pad <= b.x
        or b.x + b.w + pad <= a.x
        or a.y + a.h + pad <= b.y
        or b.y + b.h + pad <= a.y
    )


def _stamp(solid: list[list[bool]], c: int, r: int) -> None:
    """Open a 2x2 hall so a scanner and a worm can pass."""
    for dc in (0, 1):
        for dr in (0, 1):
            cc = c + dc
            rr = r + dr
            if 1 <= cc < COLS - 1 and 1 <= rr < ROWS - 1:
                solid[rr][cc] = False


def _hline(solid: list[list[bool]], x1: int, x2: int, y: int) -> None:
    for x in range(min(x1, x2), max(x1, x2) + 1):
        _stamp(solid, x, y)


def _vline(solid: list[list[bool]], y1: int, y2: int, x: int) -> None:
    for y in range(min(y1, y2), max(y1, y2) + 1):
        _stamp(solid, x, y)


def _carve_room(solid: list[list[bool]], room: Room) -> None:
    for y in range(room.y, room.y + room.h):
        for x in range(room.x, room.x + room.w):
            solid[y][x] = False


def _carve_hall(solid: list[list[bool]], a: tuple[int, int], b: tuple[int, int], rng: random.Random) -> None:
    ax, ay = a
    bx, by = b
    if rng.randrange(2) == 0:
        _hline(solid, ax, bx, ay)
        _vline(solid, ay, by, bx)
    else:
        _vline(solid, ay, by, ax)
        _hline(solid, ax, bx, by)


@dataclass
class Input:
    dx: float = 0.0
    dy: float = 0.0
    aim_x: float = 0.0
    aim_y: float = 0.0
    fire: bool = False
    scan: bool = False


@dataclass
class Player:
    x: float
    y: float
    radius: float = PLAYER_RADIUS
    hp: int = 100
    facing: float = 0.0
    aim: float = 0.0
    scan: float = 100.0
    fire_cd: float = 0.0
    scan_cd: float = 0.0
    hurt: float = 0.0
    muzzle: float = 0.0


@dataclass
class Enemy:
    kind: str
    x: float
    y: float
    radius: float
    hp: int
    max_hp: int
    speed: float
    damage: int
    awake: bool = True
    facing: float = 0.0
    slow: float = 0.0
    flash: float = 0.0
    cooldown: float = 0.0
    dash: float = 0.0
    dash_cd: float = 1.0
    pulse: float = 0.0
    pulse_cd: float = 2.2
    phase: int = 0
    phase_t: float = 0.0
    acted: bool = False
    orbit: int = 1
    alive: bool = True
    stuck: bool = False
    marked: bool = False
    infect: float = 2.2
    seals: int = 0
    cover: str = ""
    child: bool = False
    copied: bool = False
    copies: int = 0
    replicate_cd: float = WORM_REPLICATION_INTERVAL
    lockout: float = 0.0
    memory_x: float = 0.0
    memory_y: float = 0.0
    memory_t: float = 0.0
    route: list[tuple[int, int]] = field(default_factory=list)
    route_goal: tuple[int, int] | None = None
    route_at: float = -10.0
    route_rev: int = -1


@dataclass
class Carrier:
    """A packet (empty name) or a background process walking a short loop."""

    name: str
    cells: list[tuple[int, int]]
    index: int = 0
    step: float = 0.0
    forward: int = 1
    halted: bool = False
    rest: float = 0.0


@dataclass
class Shot:
    x: float
    y: float
    px: float
    py: float
    vx: float
    vy: float
    radius: float
    life: float
    friendly: bool
    damage: int
    dead: bool = False


@dataclass
class Pop:
    text: str
    x: float
    y: float
    life: float
    kind: str


@dataclass
class Decoy:
    """An ordinary file on the floor. A scan marks it clean."""

    name: str
    x: float
    y: float
    checked: bool = False


@dataclass
class RepairModule:
    """A one-use integrity pickup inside a ransomware-guarded room."""

    x: float
    y: float
    amount: int = MODULE_REPAIR


@dataclass
class World:
    """One process. `solid` True is a packed page. The simulation never draws."""

    seed: int = 0
    level: int = 1
    integrity: int = 100
    arena: bool = False
    time: float = 0.0
    kills_score: int = 0
    exit_open: bool = False
    secured: bool = False
    restoration_total: int = 0
    restoration_cleaned: int = 0
    result: str | None = None
    neutral: bool = False
    spec: Process = field(init=False)
    rng: random.Random = field(init=False)
    solid: list[list[bool]] = field(init=False)
    rooms: list[Room] = field(init=False)
    labels: list[tuple[str, float, float]] = field(init=False)
    player: Player = field(init=False)
    exit_cell: tuple[int, int] = field(init=False)
    exit_x: float = field(init=False)
    exit_y: float = field(init=False)
    enemies: list[Enemy] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    pops: list[Pop] = field(default_factory=list)
    events: list[tuple] = field(default_factory=list)
    decoys: list[Decoy] = field(default_factory=list)
    repair_module: RepairModule | None = None

    def __post_init__(self) -> None:
        if self.level < 1 or self.level > len(PROCESSES):
            raise ValueError(f"level {self.level} is out of range")
        self.enemies = []
        self.shots = []
        self.pops = []
        self.events = []
        self.decoys = []
        self.repair_module = None
        if self.arena:
            self._build_arena()
        else:
            self._build_level()

    def threat_count(self) -> int:
        return sum(1 for enemy in self.enemies if enemy.alive)

    def restoration_remaining(self) -> int:
        return self._taint_count() if self.secured else 0

    def restoration_fraction(self) -> float:
        if not self.secured or self.restoration_total == 0:
            return 0.0
        return min(1.0, max(0.0, (self.restoration_total - self.restoration_remaining()) /
                                 self.restoration_total))

    def restoration_bonus(self) -> tuple[int, int]:
        """Optional post-combat score and integrity reward, never required to leave."""
        if not self.secured or self.restoration_total <= 0:
            return 0, 0
        fraction = self.restoration_fraction()
        if fraction >= 1:
            return RESTORE_COMPLETE_SCORE, RESTORE_COMPLETE_HP
        if fraction >= 0.5:
            return RESTORE_PARTIAL_SCORE, 0
        return 0, 0

    def _secure(self) -> None:
        if self.secured or self.threat_count() > 0:
            return
        self.secured = True
        self.restoration_total = self._taint_count()
        self.restoration_cleaned = 0
        self.exit_open = True
        self.events.append(("exit",))
        if self.restoration_total:
            self.pops.append(Pop("RESTORE OPTIONAL", self.player.x, self.player.y - 30, 1.8, "scan"))
        else:
            self.pops.append(Pop("SECTOR SECURED", self.player.x, self.player.y - 30, 1.8, "exit"))

    def player_cell(self) -> tuple[int, int]:
        c = int(self.player.x // CELL)
        r = int(self.player.y // CELL)
        return min(max(c, 0), COLS - 1), min(max(r, 0), ROWS - 1)

    def step(self, dt: float, inp: Input) -> None:
        if self.result:
            return
        dt = 0.0 if dt < 0 else min(dt, DT_MAX)
        self.time += dt
        self._timers(dt)
        self._move_player(dt, inp)
        self._collect_repair_module()
        self._act(inp)
        for enemy in list(self.enemies):
            if enemy.alive:
                self._update_enemy(enemy, dt)
        self._memory(dt)
        self._separate()
        self._contact()
        self._update_shots(dt)
        self._secure()
        self._update_pops(dt)
        self._check_exit()
        self.enemies = [enemy for enemy in self.enemies if enemy.alive]
        self.shots = [shot for shot in self.shots if not shot.dead]
        if len(self.events) > 64:
            del self.events[:-64]

    def spawn(self, kind: str, x: float, y: float) -> Enemy | None:
        if kind not in STATS:
            raise ValueError(kind)
        if self.threat_count() >= MAX_ENEMIES:
            return None
        stat = STATS[kind]
        enemy = Enemy(
            kind=kind,
            x=x,
            y=y,
            radius=stat["radius"],
            hp=stat["hp"],
            max_hp=stat["hp"],
            speed=stat["speed"],
            damage=stat["damage"],
            awake=stat["awake"],
            orbit=1 if self.rng.randrange(2) == 0 else -1,
            dash_cd=self.rng.uniform(0.4, 1.2),
            cooldown=self.rng.uniform(0.3, 1.5),
            pulse_cd=self.rng.uniform(1.2, 2.6),
            infect=self.rng.uniform(1.4, 3.2),
            replicate_cd=self.rng.uniform(2.2, 5.2),
            cover=self._pick_cover() if kind == "trojan" else "",
        )
        self.enemies.append(enemy)
        return enemy

    def _pick_cover(self) -> str:
        """A filename for a trojan that no room label or other trojan wears."""
        taken = {label for label, _x, _y in getattr(self, "labels", [])}
        taken |= {enemy.cover for enemy in self.enemies if enemy.cover}
        free = [name for name in FILE_NAMES if name not in taken] or list(FILE_NAMES)
        return free[self.rng.randrange(len(free))]

    def reachable(self) -> set[tuple[int, int]]:
        c, r = self.player_cell()
        if self.solid[r][c]:
            return set()
        seen: set[tuple[int, int]] = set()
        stack = [(c, r)]
        while stack:
            c, r = stack.pop()
            if (c, r) in seen or self.solid[r][c]:
                continue
            seen.add((c, r))
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nc, nr = c + dc, r + dr
                if 0 <= nc < COLS and 0 <= nr < ROWS and (nc, nr) not in seen:
                    stack.append((nc, nr))
        return seen

    def fits(self, x: float, y: float, radius: float) -> bool:
        if x - radius < 0 or y - radius < 0:
            return False
        if x + radius >= WIDTH_PX or y + radius >= HEIGHT_PX:
            return False
        min_c = int((x - radius) / CELL)
        max_c = int((x + radius) / CELL)
        min_r = int((y - radius) / CELL)
        max_r = int((y + radius) / CELL)
        limit = radius * radius
        for r in range(min_r, max_r + 1):
            for c in range(min_c, max_c + 1):
                if not self.solid[r][c]:
                    continue
                left = c * CELL
                top = r * CELL
                qx = min(max(x, left), left + CELL)
                qy = min(max(y, top), top + CELL)
                if (x - qx) ** 2 + (y - qy) ** 2 < limit:
                    return False
        return True

    def _build_arena(self) -> None:
        self.spec = PROCESSES[0]
        self.rng = random.Random(0)
        self.solid = [[True] * COLS for _ in range(ROWS)]
        for r in range(1, ROWS - 1):
            for c in range(1, COLS - 1):
                self.solid[r][c] = False
        self.rooms = [Room(1, 1, COLS - 2, ROWS - 2)]
        self.player = Player(3 * CELL + CELL / 2, 3 * CELL + CELL / 2, hp=self.integrity)
        self.exit_cell = (COLS - 4, ROWS - 4)
        self.exit_x, self.exit_y = cell_center(*self.exit_cell)
        label = cell_center(10, 8)
        self.labels = [("arena.c", label[0], label[1])]
        self._finish_map()

    def _build_level(self) -> None:
        self.spec = PROCESSES[self.level - 1]
        salt = (self.seed + self.level * 0x9E3779B1) & MASK64
        self.rng = random.Random(salt)
        solid = [[True] * COLS for _ in range(ROWS)]
        rooms: list[Room] = []
        for _ in range(400 if self.spec.compact else 160):
            if len(rooms) >= self.spec.rooms:
                break
            if self.spec.compact:
                w = self.rng.randint(6, 9)
                h = self.rng.randint(5, 7)
            else:
                w = self.rng.randint(7, 11)
                h = self.rng.randint(6, 9)
            x = self.rng.randint(1, COLS - w - 1)
            y = self.rng.randint(1, ROWS - h - 1)
            room = Room(x, y, w, h)
            if any(_overlap(room, other, 2) for other in rooms):
                continue
            _carve_room(solid, room)
            if rooms:
                _carve_hall(solid, _center(rooms[-1]), _center(room), self.rng)
            rooms.append(room)
        self.solid = solid
        self.rooms = rooms
        if len(rooms) < 2:
            self._build_arena()
            return
        self._place(rooms)
        self._ensure_connected()
        self._finish_map()

    def _place(self, rooms: list[Room]) -> None:
        sc, sr = _center(rooms[0])
        self.player = Player(*cell_center(sc, sr), hp=self.integrity)
        ec, er = _center(rooms[-1])
        self.exit_cell = (ec, er)
        self.exit_x, self.exit_y = cell_center(ec, er)
        names = list(FILE_NAMES)
        self.rng.shuffle(names)
        self.labels = []
        for index, room in enumerate(rooms[:-1]):
            # Top-left of the room, so the filename is not under the fight.
            x = room.x * CELL + 12
            y = room.y * CELL + 8
            self.labels.append((names[index % len(names)], x, y))
        middle = rooms[1:-1] or rooms[1:]
        used: list[tuple[float, float]] = []
        kinds = roster(self.spec)
        normals = [kind for kind in kinds if kind != "boss"]
        for kind in normals:
            spot = self._pick_spot(middle, 1, used, STATS[kind]["radius"])
            if spot is None:
                spot = self._force_spot(STATS[kind]["radius"], used)
            if spot is None:
                continue
            self.spawn(kind, *spot)
            used.append(spot)
        if self.spec.boss:
            spot = self._pick_spot([rooms[-1]], 2, used, STATS["boss"]["radius"])
            if spot is None:
                spot = self._pick_spot(middle, 2, used, STATS["boss"]["radius"])
            if spot is None:
                spot = self._force_spot(STATS["boss"]["radius"], used)
            if spot is not None:
                self.spawn("boss", *spot)
                used.append(spot)
        self._place_decoys(middle, used)

    def _place_decoys(self, middle: list[Room], used: list[tuple[float, float]]) -> None:
        count = self.spec.decoys
        covers = {enemy.cover for enemy in self.enemies if enemy.cover}
        labels = {label for label, _x, _y in self.labels}
        names = [name for name in FILE_NAMES if name not in covers and name not in labels]
        names = names or [name for name in FILE_NAMES if name not in covers] or list(FILE_NAMES)
        self.rng.shuffle(names)
        for index in range(count):
            spot = self._pick_spot(middle, 1, used, STATS["trojan"]["radius"])
            if spot is None:
                return
            self.decoys.append(Decoy(names[index % len(names)], *spot))
            used.append(spot)

    def _pick_spot(
        self,
        rooms: list[Room],
        inset: int,
        used: list[tuple[float, float]],
        radius: float,
    ) -> tuple[float, float] | None:
        cells: list[tuple[int, int]] = []
        for room in rooms:
            cells.extend(self._inset_cells(room, inset))
        self.rng.shuffle(cells)
        for minimum in (240, 160, 100, 64):
            spot = self._first_fit(cells, used, radius, minimum)
            if spot is not None:
                return spot
        return self._first_fit(cells, used, radius, 0)

    def _first_fit(
        self,
        cells: list[tuple[int, int]],
        used: list[tuple[float, float]],
        radius: float,
        minimum: float,
    ) -> tuple[float, float] | None:
        for c, r in cells:
            if (c, r) == self.exit_cell:
                continue
            x, y = cell_center(c, r)
            if minimum and math.hypot(x - self.player.x, y - self.player.y) < minimum:
                continue
            if any(math.hypot(x - ux, y - uy) < 56 for ux, uy in used):
                continue
            if not self.fits(x, y, radius):
                continue
            return x, y
        return None

    def _force_spot(self, radius: float, used: list[tuple[float, float]]) -> tuple[float, float] | None:
        cells = [(c, r) for r in range(2, ROWS - 2) for c in range(2, COLS - 2)]
        return self._first_fit(cells, used, radius, 48)

    def _inset_cells(self, room: Room, inset: int) -> list[tuple[int, int]]:
        cells = []
        for y in range(room.y + inset, room.y + room.h - inset):
            for x in range(room.x + inset, room.x + room.w - inset):
                if 0 <= x < COLS and 0 <= y < ROWS and not self.solid[y][x]:
                    cells.append((x, y))
        return cells

    def _ensure_connected(self) -> None:
        goals = [self.exit_cell]
        goals.extend((int(enemy.x // CELL), int(enemy.y // CELL)) for enemy in self.enemies)
        for _ in range(4):
            got = self.reachable()
            missing = [cell for cell in goals if cell not in got]
            if not missing:
                return
            pc = self.player_cell()
            for cell in missing:
                _hline(self.solid, pc[0], cell[0], pc[1])
                _vline(self.solid, pc[1], cell[1], cell[0])

    def _finish_map(self) -> None:
        self.tile = [
            [PACKED if self.solid[r][c] else OPEN for c in range(COLS)]
            for r in range(ROWS)
        ]
        self.map_rev = 0
        self.latents: list[tuple[int, int, float]] = []
        self.seals: list[tuple[int, int, float]] = []
        self.flashes: list[tuple[int, int, float]] = []
        self.unstable: list[tuple[int, int, float, bool]] = []
        self.held: list[tuple[int, int, int, int, float]] = []
        self.carriers: list[Carrier] = []
        self.alert_x = 0.0
        self.alert_y = 0.0
        self.alert_t = 0.0
        self.alert_at = -10.0
        self.spread_t = SPREAD_EVERY
        self.system = 100.0
        self._place_unstable()
        self._place_carriers()
        self._place_repair_module()

    def _place_repair_module(self) -> None:
        """Rare, deterministic, and only in a room guarded by living ransomware.

        Keep item-generation randomness separate so enabling pickups does not
        change map geometry, enemy behavior, or other seeded placements.
        """
        if self.arena or not self.spec.ransom:
            return
        randomizer = random.Random((self.seed ^ (self.level * 0xD6E8FEB86659FD93)
                                    ^ 0xA53E9B73F0D19A41) & MASK64)
        if randomizer.random() >= MODULE_CHANCE:
            return
        guarding = []
        for enemy in self.enemies:
            if enemy.alive and enemy.kind == "ransom":
                room = self._room_at(*self._clamp_cell(enemy.x, enemy.y))
                if room is not None and room not in self.rooms[:1] and room is not self.rooms[-1]:
                    guarding.append((enemy, room))
        randomizer.shuffle(guarding)
        reachable = self.reachable()
        for guard, room in guarding:
            cells = self._inset_cells(room, 1)
            randomizer.shuffle(cells)
            # Prefer spots within the guard's vicinity, without landing on it.
            cells.sort(key=lambda cell: abs(cell_center(*cell)[0] - guard.x)
                       + abs(cell_center(*cell)[1] - guard.y))
            for c, r in cells:
                x, y = cell_center(c, r)
                if (c, r) not in reachable or self.tile[r][c] != OPEN:
                    continue
                if self._occupied(c, r) or self._gate_cell(c, r):
                    continue
                if math.hypot(x - guard.x, y - guard.y) < CELL * 1.5:
                    continue
                if not self.fits(x, y, MODULE_RADIUS):
                    continue
                self.repair_module = RepairModule(x, y)
                return

    def _collect_repair_module(self) -> None:
        module = self.repair_module
        if module is None or self.player.hp >= 100:
            return
        if math.hypot(self.player.x - module.x, self.player.y - module.y) > (self.player.radius + 12):
            return
        before = self.player.hp
        self.player.hp = min(100, before + module.amount)
        restored = self.player.hp - before
        self.repair_module = None
        self.events.append(("repair", restored, module.x, module.y))
        self.pops.append(Pop(f"REPAIR +{restored}", module.x, module.y - 25, 1.2, "repair"))

    def _place_unstable(self) -> None:
        """A few access gates. They shut for a moment and are never the only route."""
        if self.arena or self.spec.gates <= 0 or len(self.rooms) < 2:
            return
        home = self.rooms[0]
        cells: list[tuple[int, int]] = []
        for r in range(ROWS):
            for c in range(COLS):
                if self.tile[r][c] != OPEN or self._open_count(c, r) != 3:
                    continue
                if home.x <= c < home.x + home.w and home.y <= r < home.y + home.h:
                    continue
                if (c, r) == self.exit_cell or self._occupied(c, r):
                    continue
                if self._would_strand(c, r):
                    continue
                cells.append((c, r))
        self.rng.shuffle(cells)
        for c, r in cells[: self.spec.gates]:
            self.unstable.append((c, r, UNSTABLE_OPEN, False))

    def _place_carriers(self) -> None:
        """Packets on hall runs, and two daemons looping inside later rooms."""
        if self.arena or len(self.rooms) < 2:
            return
        home = self.rooms[0]
        used: set[tuple[int, int]] = set()

        def outside(c: int, r: int) -> bool:
            return not (home.x <= c < home.x + home.w and home.y <= r < home.y + home.h)

        def grow(start: tuple[int, int], limit: int, halls: bool) -> list[tuple[int, int]]:
            chain = [start]
            seen = {start}
            while len(chain) < limit:
                c, r = chain[-1]
                nxt: list[tuple[int, int]] = []
                for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nc, nr = c + dc, r + dr
                    if (nc, nr) in seen or (nc, nr) in used:
                        continue
                    if not (0 <= nc < COLS and 0 <= nr < ROWS):
                        continue
                    if self.solid[nr][nc] or self.tile[nr][nc] != OPEN:
                        continue
                    count = self._open_count(nc, nr)
                    if halls and count not in (2, 3):
                        continue
                    if not halls and count < 4:
                        continue
                    nxt.append((nc, nr))
                if not nxt:
                    break
                pick = nxt[0]
                if len(chain) >= 2:
                    pc, pr = chain[-2]
                    straight = (c + (c - pc), r + (r - pr))
                    if straight in nxt:
                        pick = straight
                chain.append(pick)
                seen.add(pick)
            return chain

        halls: list[tuple[int, int]] = []
        rooms: dict[int, list[tuple[int, int]]] = {}
        for r in range(1, ROWS - 1):
            for c in range(1, COLS - 1):
                if self.tile[r][c] != OPEN or (c, r) == self.exit_cell or not outside(c, r):
                    continue
                count = self._open_count(c, r)
                if count == 3:
                    halls.append((c, r))
                elif count >= 4:
                    room = self._room_at(c, r)
                    if room is not None and room is not home:
                        rooms.setdefault(id(room), []).append((c, r))
        self.rng.shuffle(halls)
        for start in halls:
            if start in used:
                continue
            chain = grow(start, 7, True)
            if len(chain) < 4:
                continue
            self.carriers.append(Carrier("", chain))
            used.update(chain)
            if sum(1 for item in self.carriers if item.name == "") >= 2:
                break
        taken = {label for label, _x, _y in self.labels} | {decoy.name for decoy in self.decoys}
        taken |= {enemy.cover for enemy in self.enemies if enemy.cover}
        names = [name for name in FILE_NAMES if name not in taken]
        if not names:
            names = list(FILE_NAMES)
        placed = 0
        order = list(rooms.values())
        self.rng.shuffle(order)
        for cells in order:
            if placed >= self.spec.daemons:
                break
            self.rng.shuffle(cells)
            chain = grow(cells[0], 4, False)
            if len(chain) < 3:
                continue
            self.carriers.append(Carrier(names[placed % len(names)], chain))
            used.update(chain)
            placed += 1

    def _room_at(self, c: int, r: int) -> Room | None:
        for room in self.rooms:
            if room.x <= c < room.x + room.w and room.y <= r < room.y + room.h:
                return room
        return None

    def _open_count(self, c: int, r: int) -> int:
        count = 0
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nc, nr = c + dc, r + dr
            if 0 <= nc < COLS and 0 <= nr < ROWS and not self.solid[nr][nc]:
                count += 1
        return count

    def _body_near_cell(self, c: int, r: int) -> bool:
        """Don't turn a tile solid while a body overlaps its *edges*.

        A cell-center occupancy check alone misses bodies partly over the next
        tile, creating the impression that corruption has trapped them.
        """
        left, top = c * CELL, r * CELL
        for body in (self.player, *(e for e in self.enemies if e.alive)):
            qx = min(max(body.x, left), left + CELL)
            qy = min(max(body.y, top), top + CELL)
            if (body.x - qx) ** 2 + (body.y - qy) ** 2 < (body.radius + 1) ** 2:
                return True
        return False

    def _occupied(self, c: int, r: int) -> bool:
        if self._body_near_cell(c, r) or self.exit_cell == (c, r):
            return True
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            ec, er = self._clamp_cell(enemy.x, enemy.y)
            if (ec, er) == (c, r):
                return True
        for decoy in self.decoys:
            if self._clamp_cell(decoy.x, decoy.y) == (c, r):
                return True
        if self.repair_module is not None and self._clamp_cell(
            self.repair_module.x, self.repair_module.y
        ) == (c, r):
            return True
        return False

    def _worm_egress(self, worm: Enemy) -> int:
        """Count directions a worm can physically escape toward from its cell.

        Unlike checking the cell center alone, each route must clear the
        worm's collision circle. Temporary ransomware doors are allowed to
        be closed; the protection is concerned with lasting corruption.
        """
        c, r = self._clamp_cell(worm.x, worm.y)
        options = 0
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nc, nr = c + dc, r + dr
            if not (0 <= nc < COLS and 0 <= nr < ROWS):
                continue
            if self.tile[nr][nc] in (PACKED, CORRUPT):
                continue
            tx, ty = cell_center(nc, nr)
            # A closed ransomware seal/gate is temporary, and must not
            # count as a permanent imprisonment.
            options += 1
        return options

    def _would_cage_worm(self, c: int, r: int) -> bool:
        """Never harden the last exits around a live worm.

        The player's reachability alone isn't enough: a route may only
        skim a worm's center or be temporarily cut by a security gate.
        Leave a small breathing space so infections don't manufacture
        invulnerable, permanently walled-in targets.
        """
        for worm in self.enemies:
            if not worm.alive or worm.kind != "worm":
                continue
            wc, wr = self._clamp_cell(worm.x, worm.y)
            if abs(wc - c) + abs(wr - r) > 2:
                continue
            before = self._worm_egress(worm)
            if before >= 2:
                previous_tile = self.tile[r][c]
                self.tile[r][c] = CORRUPT
                try:
                    after = self._worm_egress(worm)
                finally:
                    self.tile[r][c] = previous_tile
                if after < 2:
                    return True
            elif before == 1 and abs(wc-c) + abs(wr-r) == 1:
                return True
        return False

    def _would_strand(self, c: int, r: int) -> bool:
        """True when blocking this open cell cuts an enemy or the exit off."""
        if self.solid[r][c] or self._would_cage_worm(c, r):
            return True
        self.solid[r][c] = True
        got = self.reachable()
        self.solid[r][c] = False
        if self.exit_cell not in got:
            return True
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            ec, er = self._clamp_cell(enemy.x, enemy.y)
            if self.solid[er][ec]:
                continue
            if (ec, er) not in got:
                return True
        return False

    def _fill(self, c: int, r: int, kind: int) -> None:
        self.tile[r][c] = kind
        self.solid[r][c] = True
        self.map_rev += 1

    def _clear_cell(self, c: int, r: int) -> None:
        if self.tile[r][c] == PACKED:
            return
        self.tile[r][c] = OPEN
        self.solid[r][c] = False
        self.map_rev += 1

    def _taint_count(self) -> int:
        return sum(
            1
            for r in range(ROWS)
            for c in range(COLS)
            if self.tile[r][c] in (LATENT, CORRUPT)
        )

    def _worm_corrupt(self, enemy: Enemy, dt: float) -> None:
        if self.arena:
            return
        # Each generation can reproduce, but the entire sector is population-
        # limited. A surviving parent can produce several copies over time.
        enemy.replicate_cd -= dt
        if enemy.replicate_cd <= 0 and enemy.copies < WORM_REPLICATION_LIMIT:
            if self._replicate(enemy):
                enemy.copies += 1
                enemy.copied = True  # retained for existing diagnostics
                enemy.replicate_cd = WORM_REPLICATION_INTERVAL + self.rng.uniform(0, 2)
            else:
                enemy.replicate_cd = 1.2  # retry if the floor is crowded
        if enemy.seals >= WORM_SEALS:
            return
        enemy.infect -= dt
        if enemy.infect > 0:
            return
        if self._taint_count() >= MAX_TAINT:
            enemy.infect = CORRUPT_EVERY
            return
        spot = self._infect_spot(enemy)
        if spot is None:
            enemy.infect = 0.8
            return
        c, r = spot
        self.tile[r][c] = LATENT
        self.latents.append((c, r, LATENT_LIFE))
        enemy.seals += 1
        enemy.infect = CORRUPT_EVERY

    def _replicate(self, parent: Enemy) -> bool:
        """Bounded multi-generation replication. No single-copy restriction."""
        living = sum(1 for enemy in self.enemies if enemy.alive and enemy.kind == "worm")
        if self.arena or living >= REPL_CAP or self.threat_count() >= MAX_ENEMIES:
            return False
        c, r = self._clamp_cell(parent.x, parent.y)
        spots: list[tuple[float, float]] = []
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2)):
            nc, nr = c + dc, r + dr
            if not (1 <= nc < COLS - 1 and 1 <= nr < ROWS - 1):
                continue
            if self.solid[nr][nc] or self._occupied(nc, nr):
                continue
            x, y = cell_center(nc, nr)
            if self.fits(x, y, STATS["worm"]["radius"]):
                spots.append((x, y))
        if not spots:
            return False
        self.rng.shuffle(spots)
        child = self.spawn("worm", *spots[0])
        if child is None:
            return False
        child.child = True
        child.infect = CORRUPT_EVERY
        child.replicate_cd = WORM_REPLICATION_INTERVAL + self.rng.uniform(1.0, 3.0)
        self.pops.append(Pop("COPY", child.x, child.y - 16, 0.7, "reveal"))
        return True

    def weapons_locked(self) -> bool:
        """Ransomware jams purging only while the player is inside its sealed room."""
        c, r = self.player_cell()
        return any(x <= c < x + w and y <= r < y + h and life > 0
                   for x, y, w, h, life in self.held)

    def _infect_spot(self, enemy: Enemy) -> tuple[int, int] | None:
        c, r = self._clamp_cell(enemy.x, enemy.y)
        picks: list[tuple[int, int]] = []
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                if dc == 0 and dr == 0:
                    continue
                nc, nr = c + dc, r + dr
                if nc < 0 or nr < 0 or nc >= COLS or nr >= ROWS:
                    continue
                if self.tile[nr][nc] != OPEN or self._occupied(nc, nr):
                    continue
                if self._open_count(nc, nr) < 4:
                    continue
                if (nc, nr) == self.exit_cell or self._gate_cell(nc, nr):
                    continue
                if self._would_strand(nc, nr):
                    continue
                picks.append((nc, nr))
        if not picks:
            return None
        self.rng.shuffle(picks)
        return picks[0]

    def _gate_cell(self, c: int, r: int) -> bool:
        return any(cell[0] == c and cell[1] == r for cell in self.unstable)

    def _seal_region(self, enemy: Enemy) -> None:
        """Shut the doors of the room this process is standing in."""
        if self.arena:
            return
        c, r = self._clamp_cell(enemy.x, enemy.y)
        room = self._room_at(c, r)
        if room is None:
            self._seal_corridor(enemy)
            return
        chosen: list[tuple[int, int]] = []
        for y in range(room.y, room.y + room.h):
            for x in range(room.x, room.x + room.w):
                if self.tile[y][x] != OPEN or self._gate_cell(x, y):
                    continue
                if (x, y) == self.exit_cell or self._occupied(x, y):
                    continue
                outside = False
                for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dc, y + dr
                    if not (0 <= nx < COLS and 0 <= ny < ROWS):
                        continue
                    if room.x <= nx < room.x + room.w and room.y <= ny < room.y + room.h:
                        continue
                    if not self.solid[ny][nx]:
                        outside = True
                        break
                if outside:
                    chosen.append((x, y))
        if not chosen:
            self._seal_corridor(enemy)
            return
        chosen.sort(key=lambda cell: abs(cell[0] - c) + abs(cell[1] - r))
        for x, y in chosen[:8]:
            self._fill(x, y, SEAL)
            self.seals.append((x, y, SEAL_TIME))
        self.held.append((room.x, room.y, room.w, room.h, SEAL_TIME))

    def _seal_corridor(self, enemy: Enemy) -> None:
        if self.arena:
            return
        c, r = self._clamp_cell(enemy.x, enemy.y)
        reserved = {(cell[0], cell[1]) for cell in self.unstable}
        doors: list[tuple[int, int, int]] = []
        halls: list[tuple[int, int, int]] = []
        for dr in range(-7, 8):
            for dc in range(-7, 8):
                nc, nr = c + dc, r + dr
                if nc < 0 or nr < 0 or nc >= COLS or nr >= ROWS:
                    continue
                if self.tile[nr][nc] != OPEN or (nc, nr) in reserved:
                    continue
                if (nc, nr) == self.exit_cell or self._occupied(nc, nr):
                    continue
                count = self._open_count(nc, nr)
                dist = abs(nc - c) + abs(nr - r)
                if count == 2:
                    doors.append((dist, nc, nr))
                elif count == 3:
                    halls.append((dist, nc, nr))
        doors.sort()
        halls.sort()
        chosen = doors[:2] if doors else halls[:1]
        for _dist, nc, nr in chosen:
            self._fill(nc, nr, SEAL)
            self.seals.append((nc, nr, SEAL_TIME))

    def _restore_corruption(self, x: float, y: float) -> bool:
        """A secured sector is repaired with the existing scanner, one cell per pulse.

        Hardened cells block movement, so scan range permits repairing from a
        neighboring accessible tile. The exit remains usable throughout.
        """
        if not self.secured or self.restoration_remaining() <= 0:
            return False
        cells = []
        for r in range(ROWS):
            for c in range(COLS):
                if self.tile[r][c] not in (LATENT, CORRUPT):
                    continue
                cx, cy = cell_center(c, r)
                distance = math.hypot(cx - x, cy - y)
                if distance <= SCAN_RADIUS:
                    cells.append((distance, c, r))
        if not cells:
            return False
        _, c, r = min(cells)
        self._clear_cell(c, r)
        self.latents = [(lc, lr, life) for lc, lr, life in self.latents if (lc, lr) != (c, r)]
        self.restoration_cleaned += 1
        self.flashes.append((c, r, 0.65))
        self.events.append(("restore", c, r))
        remaining = self.restoration_remaining()
        label = "MEMORY RESTORED" if remaining == 0 else f"REPAIRED {self.restoration_cleaned}/{self.restoration_total}"
        self.pops.append(Pop(label, *cell_center(c, r), 0.85, "scan"))
        return True

    def _quarantine(self, x: float, y: float) -> bool:
        cleaned = False
        kept: list[tuple[int, int, float]] = []
        for c, r, life in self.latents:
            cx, cy = cell_center(c, r)
            if self.tile[r][c] == LATENT and math.hypot(cx - x, cy - y) <= SCAN_RADIUS:
                self._clear_cell(c, r)
                self.flashes.append((c, r, 0.55))
                self._restore_system(SYSTEM_CLEAN)
                cleaned = True
            else:
                kept.append((c, r, life))
        self.latents = kept
        return cleaned

    def _memory(self, dt: float) -> None:
        kept: list[tuple[int, int, float]] = []
        for c, r, life in self.latents:
            if self.secured:
                kept.append((c, r, life))
                continue
            life -= dt
            if self.tile[r][c] != LATENT:
                continue
            if life > 0:
                kept.append((c, r, life))
                continue
            if self._occupied(c, r) or self._would_strand(c, r):
                kept.append((c, r, 0.6))
                continue
            self._fill(c, r, CORRUPT)
            self._strain_system(SYSTEM_HARDEN)
        self.latents = kept
        seals: list[tuple[int, int, float]] = []
        for c, r, life in self.seals:
            life -= dt
            if life > 0:
                seals.append((c, r, life))
                continue
            if self.tile[r][c] == SEAL:
                self._clear_cell(c, r)
        self.seals = seals
        held: list[tuple[int, int, int, int, float]] = []
        for x, y, w, h, life in self.held:
            life -= dt
            if life > 0:
                held.append((x, y, w, h, life))
        self.held = held
        for index, (c, r, timer, closed) in enumerate(self.unstable):
            timer -= dt
            if timer > 0:
                self.unstable[index] = (c, r, timer, closed)
                continue
            if closed:
                if self.tile[r][c] == GATE:
                    self._clear_cell(c, r)
                self.unstable[index] = (c, r, UNSTABLE_OPEN, False)
                continue
            if self._occupied(c, r) or self.tile[r][c] != OPEN or self._would_strand(c, r):
                self.unstable[index] = (c, r, UNSTABLE_OPEN, False)
                continue
            self._fill(c, r, GATE)
            self.unstable[index] = (c, r, UNSTABLE_SHUT, True)
        if not self.secured and self.threat_count() > 0:
            self._spread(dt)
        self._advance_carriers(dt)
        self._watch_system(dt)
        flashes: list[tuple[int, int, float]] = []
        for c, r, life in self.flashes:
            life -= dt
            if life > 0:
                flashes.append((c, r, life))
        self.flashes = flashes

    def _spread_wait(self) -> float:
        if self.level == len(PROCESSES) and any(
            enemy.alive and enemy.kind == "boss" for enemy in self.enemies
        ):
            return SPREAD_BOSS
        return SPREAD_EVERY

    def _spread(self, dt: float) -> None:
        """A hardened cell plants one neighbor. The exit stays reachable."""
        if self.arena:
            return
        self.spread_t -= dt
        if self.spread_t > 0:
            return
        self.spread_t = self._spread_wait()
        if self._taint_count() >= MAX_TAINT:
            return
        cells = [
            (c, r)
            for r in range(ROWS)
            for c in range(COLS)
            if self.tile[r][c] == CORRUPT
        ]
        if not cells:
            return
        self.rng.shuffle(cells)
        for c, r in cells:
            neighbors: list[tuple[int, int]] = []
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nc, nr = c + dc, r + dr
                if not (0 <= nc < COLS and 0 <= nr < ROWS):
                    continue
                if self.tile[nr][nc] != OPEN or self._occupied(nc, nr):
                    continue
                if (nc, nr) == self.exit_cell or self._gate_cell(nc, nr):
                    continue
                if self._open_count(nc, nr) < 3 or self._would_strand(nc, nr):
                    continue
                neighbors.append((nc, nr))
            if not neighbors:
                continue
            self.rng.shuffle(neighbors)
            nc, nr = neighbors[0]
            self.tile[nr][nc] = LATENT
            self.latents.append((nc, nr, LATENT_LIFE))
            return

    def _advance_carriers(self, dt: float) -> None:
        for carrier in self.carriers:
            if carrier.halted or not carrier.cells:
                continue
            c, r = carrier.cells[carrier.index]
            if self._traffic_blocked(c, r):
                carrier.halted = True
                continue
            if carrier.rest > 0:
                carrier.rest = max(0.0, carrier.rest - dt)
                continue
            carrier.step += dt
            pace = 0.22 if carrier.name == "" else 0.55
            if carrier.step < pace:
                continue
            carrier.step = 0.0
            nxt = carrier.index + carrier.forward
            if nxt < 0 or nxt >= len(carrier.cells):
                carrier.forward *= -1
                nxt = carrier.index + carrier.forward
            if nxt < 0 or nxt >= len(carrier.cells):
                continue
            nc, nr = carrier.cells[nxt]
            if self._traffic_blocked(nc, nr):
                carrier.halted = True
                continue
            carrier.index = nxt
            # A daemon sometimes sits still, so a filename that is not
            # moving is not proof of a trojan.
            if carrier.name and self.rng.random() < DAEMON_REST:
                carrier.rest = self.rng.uniform(1.5, 4.0)

    def _traffic_blocked(self, c: int, r: int) -> bool:
        if not (0 <= c < COLS and 0 <= r < ROWS):
            return True
        return self.solid[r][c] or self.tile[r][c] in (CORRUPT, SEAL, GATE, PACKED)

    def _kernel_threat_active(self) -> bool:
        """The kernel's integrity is no longer under attack once POLY.SYS dies."""
        return any(enemy.alive and enemy.kind == "boss" for enemy in self.enemies)

    def _strain_system(self, amount: float) -> None:
        if (self.arena or self.level != len(PROCESSES) or self.result
                or not self._kernel_threat_active()):
            return
        self.system = max(0.0, self.system - amount)
        if self.system <= 0:
            self._system_crash()

    def _restore_system(self, amount: float) -> None:
        if self.arena or self.level != len(PROCESSES) or self.result:
            return
        self.system = min(100.0, self.system + amount)

    def _watch_system(self, dt: float) -> None:
        if self.arena or self.level != len(PROCESSES) or self.result:
            return
        if not self._kernel_threat_active():
            return
        self.system = max(0.0, self.system - SYSTEM_DRAIN * dt)
        if self.system <= 0:
            self._system_crash()

    def _system_crash(self) -> None:
        if self.result:
            return
        self.system = 0.0
        self.result = "crash"
        self.events.append(("crash",))

    def _timers(self, dt: float) -> None:
        player = self.player
        player.fire_cd = max(0.0, player.fire_cd - dt)
        player.scan_cd = max(0.0, player.scan_cd - dt)
        player.hurt = max(0.0, player.hurt - dt)
        player.muzzle = max(0.0, player.muzzle - dt)
        if player.scan < 100:
            player.scan = min(100.0, player.scan + SCAN_REGEN * dt)
        self.alert_t = max(0.0, self.alert_t - dt)
        for enemy in self.enemies:
            enemy.slow = max(0.0, enemy.slow - dt)
            enemy.flash = max(0.0, enemy.flash - dt)
            enemy.memory_t = max(0.0, enemy.memory_t - dt)
            if enemy.kind == "ransom":
                enemy.lockout = max(0.0, enemy.lockout - dt)

    def _move_player(self, dt: float, inp: Input) -> None:
        player = self.player
        dx, dy = inp.dx, inp.dy
        mag = math.hypot(dx, dy)
        if mag > 0:
            dx /= mag
            dy /= mag
            player.facing = math.atan2(dy, dx)
            self._slide(player, dx * PLAYER_SPEED, dy * PLAYER_SPEED, dt, PLAYER_SPEED)
        ax = inp.aim_x - player.x
        ay = inp.aim_y - player.y
        if math.hypot(ax, ay) > 6:
            player.aim = math.atan2(ay, ax)
        else:
            player.aim = player.facing

    def _act(self, inp: Input) -> None:
        player = self.player
        if inp.scan and player.scan_cd <= 0 and player.scan >= SCAN_COST:
            player.scan -= SCAN_COST
            player.scan_cd = SCAN_GAP
            self.events.append(("scan", player.x, player.y))
            found = False
            for enemy in self.enemies:
                if not enemy.alive:
                    continue
                if math.hypot(enemy.x - player.x, enemy.y - player.y) > SCAN_RADIUS:
                    continue
                enemy.slow = SLOW_TIME
                # Name a sleeping trojan through walls. It stays asleep
                # until something touches it or a purge hits it.
                if enemy.kind == "trojan" and not enemy.awake and not enemy.marked:
                    enemy.marked = True
                    found = True
                    self.events.append(("reveal", enemy.x, enemy.y))
                    self.pops.append(Pop(NAMES["trojan"], enemy.x, enemy.y - 18, 0.9, "reveal"))
            for decoy in self.decoys:
                if decoy.checked:
                    continue
                if math.hypot(decoy.x - player.x, decoy.y - player.y) > SCAN_RADIUS:
                    continue
                decoy.checked = True
                found = True
                self.pops.append(Pop("clean", decoy.x, decoy.y - 18, 0.8, "scan"))
            if self.secured:
                found = self._restore_corruption(player.x, player.y) or found
            elif self._quarantine(player.x, player.y):
                found = True
                self.pops.append(Pop("QUARANTINE", player.x, player.y - 36, 0.9, "scan"))
            if not found:
                self.pops.append(Pop("NO SIGNATURE", player.x, player.y - 22, 0.55, "scan"))
        if inp.fire and player.fire_cd <= 0 and not self.weapons_locked():
            player.fire_cd = FIRE_GAP
            player.muzzle = 0.06
            ang = player.aim
            ox = math.cos(ang) * (player.radius + 8)
            oy = math.sin(ang) * (player.radius + 8)
            x, y = player.x + ox, player.y + oy
            self.shots.append(Shot(
                x=x, y=y, px=x, py=y,
                vx=math.cos(ang) * BOLT_SPEED,
                vy=math.sin(ang) * BOLT_SPEED,
                radius=4,
                life=BOLT_LIFE,
                friendly=True,
                damage=1,
            ))
            self.events.append(("fire",))

    def _update_enemy(self, enemy: Enemy, dt: float) -> None:
        if enemy.kind == "trojan" and not enemy.awake:
            if math.hypot(enemy.x - self.player.x, enemy.y - self.player.y) <= TROJAN_WAKE:
                enemy.awake = True
                self.events.append(("reveal", enemy.x, enemy.y))
                self.pops.append(Pop(NAMES["trojan"], enemy.x, enemy.y - 18, 0.9, "reveal"))
            else:
                return
        if enemy.kind == "boss":
            self._update_boss(enemy, dt)
            return
        if enemy.kind == "spyware":
            self._update_spy(enemy, dt)
            return
        if enemy.kind == "ransom":
            self._update_ransom(enemy, dt)
            return
        if enemy.kind == "worm":
            self._worm_corrupt(enemy, dt)
        speed = enemy.speed
        if enemy.kind == "trojan":
            if enemy.dash > 0:
                speed = TROJAN_DASH_SPEED
                enemy.dash -= dt
            else:
                enemy.dash_cd -= dt
                if enemy.dash_cd <= 0:
                    enemy.dash = TROJAN_DASH_TIME
                    enemy.dash_cd = TROJAN_DASH_CD
                    speed = TROJAN_DASH_SPEED
        if enemy.kind == "worm" and self._sees(enemy.x, enemy.y, self.player.x, self.player.y):
            # Split the pack: alternate worms take offset approach lanes until
            # close enough to lunge. Never choose an impassable flank point.
            dx = self.player.x - enemy.x
            dy = self.player.y - enemy.y
            dist = math.hypot(dx, dy)
            if 90 < dist < 400:
                offset = 88 * enemy.orbit
                tx = self.player.x - dy / dist * offset
                ty = self.player.y + dx / dist * offset
                if self.fits(tx, ty, enemy.radius):
                    self._approach(enemy, tx, ty, speed, dt)
                    return
        self._pursue(enemy, speed, dt)

    def _update_spy(self, enemy: Enemy, dt: float) -> None:
        dx = self.player.x - enemy.x
        dy = self.player.y - enemy.y
        dist = math.hypot(dx, dy) or 1.0
        sees = self._sees(enemy.x, enemy.y, self.player.x, self.player.y)
        # A spy is the scout. It can cross the map. The others cannot,
        # until it tells them where the scanner is.
        if sees:
            self._raise_alert(self.player.x, self.player.y)
        if dist < 155:
            tx = enemy.x - dx / dist * 48
            ty = enemy.y - dy / dist * 48
        elif dist > 310 or not sees:
            tx, ty = self.player.x, self.player.y
        else:
            tx = enemy.x + (-dy / dist) * enemy.orbit * 36
            ty = enemy.y + (dx / dist) * enemy.orbit * 36
        self._approach(enemy, tx, ty, enemy.speed, dt)
        if enemy.cooldown <= 0 and sees and dist < 460:
            self._spit(enemy, 0.0)
            enemy.cooldown = 1.85
        else:
            enemy.cooldown = max(0.0, enemy.cooldown - dt)

    def _update_ransom(self, enemy: Enemy, dt: float) -> None:
        if enemy.pulse > 0:
            enemy.pulse -= dt
            if enemy.pulse <= 0:
                enemy.pulse = 0.0
                enemy.pulse_cd = 3.3
                self.events.append(("lock", enemy.x, enemy.y))
                if math.hypot(self.player.x - enemy.x, self.player.y - enemy.y) <= RANSOM_RADIUS:
                    self._hurt(RANSOM_BLAST, enemy.x, enemy.y)
            return
        enemy.pulse_cd -= dt
        self._pursue(enemy, enemy.speed, dt)
        if enemy.pulse_cd <= 0:
            enemy.pulse = PULSE_TIME
            if enemy.lockout <= 0:
                self._seal_region(enemy)
                enemy.lockout = LOCK_GAP
            self.events.append(("windup", enemy.x, enemy.y))

    def boss_rage(self, enemy: Enemy) -> float:
        """0 at full HP, approaching 1 as the boss nears death."""
        if enemy.max_hp <= 1:
            return 0.0
        return min(1.0, max(0.0, 1 - (enemy.hp - 1) / (enemy.max_hp - 1)))

    def _update_boss(self, enemy: Enemy, dt: float) -> None:
        name, dur = BOSS_PHASES[enemy.phase]
        rage = self.boss_rage(enemy)
        if name == "chase":
            dur *= 1 - BOSS_RAGE_CHASE * rage
        if not enemy.acted:
            enemy.acted = True
            if name == "spawn":
                self._boss_adds(enemy)
            elif name == "spray":
                offsets = (-0.7, -0.35, 0.0, 0.35, 0.7)
                if rage >= 0.5:
                    offsets = (-1.05, -0.7, -0.35, 0.0, 0.35, 0.7, 1.05)
                for offset in offsets:
                    self._spit(enemy, offset)
        if name == "chase":
            speed = enemy.speed * (1 + BOSS_RAGE_SPEED * rage)
            self._approach(enemy, self.player.x, self.player.y, speed, dt)
        # The kernel infection knows where the scanner is. The ring is the
        # spy's tell; this only hands the location to the other processes.
        self._raise_alert(self.player.x, self.player.y, announce=False)
        enemy.phase_t += dt
        if enemy.phase_t >= dur:
            enemy.phase = (enemy.phase + 1) % len(BOSS_PHASES)
            enemy.phase_t = 0.0
            enemy.acted = False

    def _boss_adds(self, boss: Enemy) -> None:
        living = sum(1 for enemy in self.enemies if enemy.alive and enemy.kind == "worm")
        ang = math.atan2(self.player.y - boss.y, self.player.x - boss.x)
        side = ang + math.pi / 2
        for sign in (1, -1):
            if living >= WORM_CAP:
                return
            x = boss.x + math.cos(side) * 40 * sign
            y = boss.y + math.sin(side) * 40 * sign
            if not self.fits(x, y, STATS["worm"]["radius"]):
                x, y = boss.x, boss.y
            if self.spawn("worm", x, y) is not None:
                living += 1

    def _spit(self, enemy: Enemy, offset: float) -> None:
        ang = math.atan2(self.player.y - enemy.y, self.player.x - enemy.x) + offset
        x = enemy.x + math.cos(ang) * (enemy.radius + 10)
        y = enemy.y + math.sin(ang) * (enemy.radius + 10)
        if not self.fits(x, y, 5):
            x, y = enemy.x, enemy.y
        self.shots.append(Shot(
            x=x, y=y, px=x, py=y,
            vx=math.cos(ang) * PACKET_SPEED,
            vy=math.sin(ang) * PACKET_SPEED,
            radius=5,
            life=PACKET_LIFE,
            friendly=False,
            damage=PACKET_DAMAGE,
        ))

    def _raise_alert(self, x: float, y: float, announce: bool = True) -> None:
        fresh = self.alert_t <= 0 or self.time - self.alert_at >= 1.4
        self.alert_x = x
        self.alert_y = y
        self.alert_t = ALERT_TIME
        if announce and fresh:
            self.events.append(("alert", x, y))
            self.alert_at = self.time

    def _pursue(self, enemy: Enemy, speed: float, dt: float) -> None:
        """Chase by sight, by a spy's call, or by the last place it saw you."""
        px, py = self.player.x, self.player.y
        if self._sees(enemy.x, enemy.y, px, py):
            enemy.memory_x = px
            enemy.memory_y = py
            enemy.memory_t = MEMORY_TIME
            self._approach(enemy, px, py, speed, dt)
            return
        if self.alert_t > 0:
            enemy.memory_x = self.alert_x
            enemy.memory_y = self.alert_y
            enemy.memory_t = max(enemy.memory_t, MEMORY_TIME)
        if enemy.memory_t > 0:
            self._approach(enemy, enemy.memory_x, enemy.memory_y, speed, dt)

    def _approach(self, enemy: Enemy, tx: float, ty: float, speed: float, dt: float) -> None:
        if enemy.slow > 0:
            speed *= SLOW_FACTOR
        if speed <= 0:
            return
        # A straight steer stops cold on a packed page. Follow the halls
        # until the line to the target is open again.
        if enemy.stuck or not self._body_clear_line(enemy.x, enemy.y, tx, ty, enemy.radius):
            point = self._steer_point(enemy, tx, ty)
            if point is not None:
                tx, ty = point
        dx, dy = tx - enemy.x, ty - enemy.y
        mag = math.hypot(dx, dy)
        if mag < 1:
            enemy.stuck = False
            return
        vx, vy = dx / mag * speed, dy / mag * speed
        enemy.facing = math.atan2(vy, vx)
        ox, oy = enemy.x, enemy.y
        self._slide(enemy, vx, vy, dt, speed)
        moved = math.hypot(enemy.x - ox, enemy.y - oy)
        if moved < speed * dt * 0.35:
            enemy.stuck = True
            self._unstick(enemy, tx, ty, speed, dt)
        elif moved > speed * dt * 0.7:
            enemy.stuck = False

    def _body_clear_line(self, x0: float, y0: float, x1: float, y1: float,
                         radius: float) -> bool:
        """Check movement clearance, not just the zero-width sight ray."""
        distance = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, math.ceil(distance / 6))
        for i in range(steps + 1):
            t = i / steps
            if not self.fits(x0 + (x1-x0)*t, y0 + (y1-y0)*t, radius):
                return False
        return True

    def _steer_point(self, enemy: Enemy, tx: float, ty: float) -> tuple[float, float] | None:
        gc, gr = self._clamp_cell(tx, ty)
        if self.solid[gr][gc]:
            return None
        goal = (gc, gr)
        if (
            enemy.route_goal != goal
            or enemy.route_rev != self.map_rev
            or self.time - enemy.route_at > ROUTE_REFRESH
        ):
            sc, sr = self._stand_cell(enemy.x, enemy.y)
            if sc < 0 or (sc, sr) == goal:
                enemy.route = []
            else:
                enemy.route = self._find_route(sc, sr, gc, gr)
            enemy.route_goal = goal
            enemy.route_at = self.time
            enemy.route_rev = self.map_rev
        route = enemy.route
        if not route:
            return None
        here = self._clamp_cell(enemy.x, enemy.y)
        if here in route:
            del route[: route.index(here) + 1]
        while route:
            wx, wy = self._nav_point(route[0][0], route[0][1], enemy.radius)
            if math.hypot(enemy.x - wx, enemy.y - wy) > 18:
                break
            route.pop(0)
        if not route:
            return None
        pick = route[0]
        for cell in route[:5]:
            wx, wy = self._nav_point(cell[0], cell[1], enemy.radius)
            if not self._body_clear_line(enemy.x, enemy.y, wx, wy, enemy.radius):
                break
            pick = cell
        return self._nav_point(pick[0], pick[1], enemy.radius)

    def _find_route(self, sc: int, sr: int, gc: int, gr: int) -> list[tuple[int, int]]:
        parent: dict[tuple[int, int], tuple[int, int] | None] = {(sc, sr): None}
        queue: deque[tuple[int, int]] = deque([(sc, sr)])
        found = False
        while queue:
            c, r = queue.popleft()
            if (c, r) == (gc, gr):
                found = True
                break
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nc, nr = c + dc, r + dr
                if nc < 0 or nr < 0 or nc >= COLS or nr >= ROWS:
                    continue
                if (nc, nr) in parent or self.solid[nr][nc]:
                    continue
                parent[(nc, nr)] = (c, r)
                queue.append((nc, nr))
        if not found:
            return []
        path: list[tuple[int, int]] = []
        cur: tuple[int, int] | None = (gc, gr)
        while cur is not None and cur != (sc, sr):
            path.append(cur)
            cur = parent[cur]
        path.reverse()
        return path

    def _nav_point(self, c: int, r: int, radius: float) -> tuple[float, float]:
        x, y = cell_center(c, r)
        # A body of radius 18 still clears a packed neighbor from a cell center.
        # Larger bodies, the kernel boss, have to ride the middle of a hall.
        if radius <= 18 or self.fits(x, y, radius):
            return x, y
        best: tuple[float, float] | None = None
        best_d = 1e9
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nc, nr = c + dc, r + dr
            if nc < 0 or nr < 0 or nc >= COLS or nr >= ROWS or self.solid[nr][nc]:
                continue
            mx = (x + nc * CELL + CELL / 2) / 2
            my = (y + nr * CELL + CELL / 2) / 2
            if not self.fits(mx, my, radius):
                continue
            dist = (mx - x) ** 2 + (my - y) ** 2
            if dist < best_d:
                best_d = dist
                best = (mx, my)
        return best if best is not None else (x, y)

    def _unstick(self, enemy: Enemy, tx: float, ty: float, speed: float, dt: float) -> None:
        step = max(4.0, speed * dt)
        best_x, best_y = enemy.x, enemy.y
        best_d = math.hypot(tx - enemy.x, ty - enemy.y)
        for ang in range(8):
            theta = ang * math.pi / 4
            sx = enemy.x + math.cos(theta) * step
            sy = enemy.y + math.sin(theta) * step
            if not self.fits(sx, sy, enemy.radius):
                continue
            dist = math.hypot(tx - sx, ty - sy)
            if dist < best_d - 0.4:
                best_d = dist
                best_x, best_y = sx, sy
        enemy.x, enemy.y = best_x, best_y

    def _clamp_cell(self, x: float, y: float) -> tuple[int, int]:
        c = min(max(int(x // CELL), 0), COLS - 1)
        r = min(max(int(y // CELL), 0), ROWS - 1)
        return c, r

    def _stand_cell(self, x: float, y: float) -> tuple[int, int]:
        c, r = self._clamp_cell(x, y)
        if not self.solid[r][c]:
            return c, r
        best: tuple[int, int] | None = None
        best_d = 1e9
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                nc, nr = c + dc, r + dr
                if nc < 0 or nr < 0 or nc >= COLS or nr >= ROWS or self.solid[nr][nc]:
                    continue
                cx, cy = cell_center(nc, nr)
                dist = (cx - x) ** 2 + (cy - y) ** 2
                if dist < best_d:
                    best_d = dist
                    best = (nc, nr)
        return best if best is not None else (-1, -1)

    def _slide(self, body: Player | Enemy, vx: float, vy: float, dt: float, speed: float) -> None:
        ox, oy = body.x, body.y
        nx = ox + vx * dt
        if self.fits(nx, oy, body.radius):
            body.x = nx
        ny = oy + vy * dt
        if self.fits(body.x, ny, body.radius):
            body.y = ny
        # Ordinary wall sliding is already handled by X/Y movement above.
        # At an outside corner both axes can reject the desired diagonal even
        # when a slightly rotated direction is clear. Try nearby headings,
        # closest to the user's intended input first, without teleporting.
        if speed <= 0 or abs(vx) <= 1 or abs(vy) <= 1:
            return
        if body.x != ox or body.y != oy:
            return
        direction = math.atan2(vy, vx)
        distance = math.hypot(vx, vy) * dt
        for degrees in (15, -15, 30, -30, 45, -45, 60, -60, 75, -75, 90, -90):
            angle = direction + math.radians(degrees)
            nx = ox + math.cos(angle) * distance
            ny = oy + math.sin(angle) * distance
            if self._body_clear_line(ox, oy, nx, ny, body.radius):
                body.x, body.y = nx, ny
                break

    def _separate(self) -> None:
        bodies = [enemy for enemy in self.enemies if enemy.alive]
        for _ in range(2):
            for i, left in enumerate(bodies):
                for right in bodies[i + 1:]:
                    dx = right.x - left.x
                    dy = right.y - left.y
                    dist = math.hypot(dx, dy)
                    need = left.radius + right.radius
                    if dist >= need:
                        continue
                    if dist == 0:
                        dx, dy, dist = 1.0, 0.0, 1.0
                    push = (need - dist) / 2
                    ux, uy = dx / dist, dy / dist
                    self._nudge(left, -ux * push, -uy * push)
                    self._nudge(right, ux * push, uy * push)

    def _nudge(self, body: Enemy, dx: float, dy: float) -> None:
        nx = body.x + dx
        if self.fits(nx, body.y, body.radius):
            body.x = nx
        ny = body.y + dy
        if self.fits(body.x, ny, body.radius):
            body.y = ny

    def _contact(self) -> None:
        player = self.player
        for enemy in self.enemies:
            if not enemy.alive or not enemy.awake:
                continue
            if math.hypot(enemy.x - player.x, enemy.y - player.y) <= enemy.radius + player.radius:
                self._hurt(enemy.damage, enemy.x, enemy.y)
                if self.result:
                    return

    def _update_shots(self, dt: float) -> None:
        for shot in self.shots:
            if shot.dead or self.result == "crash":
                continue
            shot.life -= dt
            if shot.life <= 0:
                shot.dead = True
                continue
            dist = math.hypot(shot.vx, shot.vy) * dt
            steps = max(1, int(dist // 8) + 1)
            hdt = dt / steps
            shot.px, shot.py = shot.x, shot.y
            for _ in range(steps):
                nx = shot.x + shot.vx * hdt
                ny = shot.y + shot.vy * hdt
                # A purge bolt only stops on a wall its center line meets, so a
                # shot past a door corner is not eaten by the corner.
                wall = BOLT_WALL if shot.friendly else shot.radius
                if not self.fits(nx, ny, wall):
                    shot.dead = True
                    break
                shot.x, shot.y = nx, ny
                if shot.friendly:
                    for enemy in self.enemies:
                        reach = enemy.radius + shot.radius
                        if enemy.alive and math.hypot(enemy.x - shot.x, enemy.y - shot.y) <= reach:
                            self._strike(enemy, shot.damage)
                            shot.dead = True
                            break
                elif math.hypot(self.player.x - shot.x, self.player.y - shot.y) <= self.player.radius + shot.radius:
                    self._hurt(shot.damage, shot.x, shot.y)
                    shot.dead = True
                if shot.dead or self.result == "crash":
                    break

    def _strike(self, enemy: Enemy, damage: int) -> None:
        if not enemy.alive:
            return
        if enemy.kind == "trojan" and not enemy.awake:
            enemy.awake = True
            self.events.append(("reveal", enemy.x, enemy.y))
        enemy.hp -= damage
        enemy.flash = 0.09
        if enemy.hp <= 0:
            enemy.alive = False
            gained = SCORES[enemy.kind]
            self.kills_score += gained
            self.events.append(("kill", enemy.kind, enemy.x, enemy.y))
            self.pops.append(Pop(
                f"{NAMES[enemy.kind]}  +{gained}",
                enemy.x,
                enemy.y - 16,
                0.95,
                "kill",
            ))

    def _hurt(self, amount: int, srcx: float, srcy: float) -> None:
        if self.result or self.neutral:
            return
        player = self.player
        if player.hurt > 0:
            return
        player.hp = max(0, player.hp - amount)
        player.hurt = IFRAMES
        self.events.append(("hurt", amount))
        dx, dy = player.x - srcx, player.y - srcy
        mag = math.hypot(dx, dy) or 1.0
        kx = player.x + dx / mag * 16
        ky = player.y + dy / mag * 16
        if self.fits(kx, player.y, player.radius):
            player.x = kx
        if self.fits(player.x, ky, player.radius):
            player.y = ky
        if player.hp <= 0:
            player.hp = 0
            self.result = "crash"
            self.events.append(("crash",))

    def _sees(self, x0: float, y0: float, x1: float, y1: float) -> bool:
        dist = math.hypot(x1 - x0, y1 - y0)
        steps = int(dist / 8) + 1
        for i in range(1, steps):
            t = i / steps
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            c = int(x / CELL)
            r = int(y / CELL)
            if not (0 <= c < COLS and 0 <= r < ROWS) or self.solid[r][c]:
                return False
        return True

    def _update_pops(self, dt: float) -> None:
        for pop in self.pops:
            pop.life -= dt
            pop.y -= 22 * dt
        self.pops = [pop for pop in self.pops if pop.life > 0]

    def _check_exit(self) -> None:
        if self.result:
            return
        self._secure()
        if not self.exit_open:
            return
        reach = CELL * 0.62
        if math.hypot(self.player.x - self.exit_x, self.player.y - self.exit_y) <= reach:
            self.result = "clear"
            self.events.append(("clear",))


class Session:
    """A run across every process, ending at the kernel. Score banks when a process is cleared."""

    def __init__(self, seed: int, level: int = 1) -> None:
        if level < 1 or level > len(PROCESSES):
            raise ValueError(f"level {level} is out of range")
        self.seed = seed
        self.level = level
        self.score = 0
        self.integrity = 100
        self.play_time = 0.0
        self.mode = "brief"
        self.cleared_name = ""
        self.last_bonus = 0
        self.world = World(seed, level, 100)

    def step(self, dt: float, inp: Input) -> None:
        if self.mode != "play":
            return
        dt = 0.0 if dt < 0 else min(dt, DT_MAX)
        self.play_time += dt
        self.world.step(dt, inp)
        if self.world.result == "crash":
            self.mode = "crash"
        elif self.world.result == "clear":
            self._resolve_clear()

    def mount(self) -> None:
        if self.mode == "brief":
            self.mode = "play"

    def retry(self) -> None:
        if self.mode not in ("play", "crash"):
            return
        self.world = World(self.seed, self.level, self.integrity)
        self.mode = "play"

    def restart(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = seed
        fresh = Session(self.seed, 1)
        self.__dict__.update(fresh.__dict__)

    def _resolve_clear(self) -> None:
        world = self.world
        restore_score, restore_hp = world.restoration_bonus()
        if restore_hp:
            world.player.hp = min(100, world.player.hp + restore_hp)
        bonus = CLEAR_BONUS + max(0, world.player.hp) * INTEGRITY_BONUS + restore_score
        kept = list(world.events)
        self.last_bonus = world.kills_score + bonus
        self.score += self.last_bonus
        self.integrity = min(100, world.player.hp + REPAIR)
        self.cleared_name = world.spec.title
        if self.level >= len(PROCESSES):
            self.mode = "win"
            return
        self.level += 1
        self.world = World(self.seed, self.level, self.integrity)
        self.world.events.extend(kept)
        self.mode = "brief"
