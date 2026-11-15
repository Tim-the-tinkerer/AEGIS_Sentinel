#!/usr/bin/env python3
"""Checks for antivirus.py. Run: python3 antivirus/test_antivirus.py"""

from __future__ import annotations

import importlib.util
import io
import math
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import antivirus
import sim


def run(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = antivirus.main(["antivirus.py", *argv])
    return code, stdout.getvalue(), stderr.getvalue()


def counts(world: sim.World) -> dict[str, int]:
    found: dict[str, int] = {}
    for enemy in world.enemies:
        found[enemy.kind] = found.get(enemy.kind, 0) + 1
    return found


def expected(spec: sim.Process) -> dict[str, int]:
    found: dict[str, int] = {}
    for kind in sim.roster(spec):
        found[kind] = found.get(kind, 0) + 1
    return found


class CliTest(unittest.TestCase):
    def test_help(self) -> None:
        for flag in ("--help", "-h"):
            code, out, err = run([flag])
            self.assertEqual(code, 0, flag)
            self.assertEqual(err, "")
            self.assertIn("AEGIS", out)
            self.assertIn("--seed", out)
            self.assertIn("--check", out)

    def test_rejects_bad_arguments(self) -> None:
        samples = (
            ["--seed"],
            ["--seed", "nope"],
            ["--seed", "-1"],
            ["--seed", str(sim.MASK64 + 1)],
            ["--seed="],
            ["--seed=no"],
            ["--level", "0"],
            ["--level", "10"],
            ["--level", "x"],
            ["extra"],
        )
        for args in samples:
            code, _out, err = run(args)
            self.assertEqual(code, 2, args)
            self.assertIn("usage:", err)
            self.assertTrue(err.startswith("antivirus.py:"), err)

    def test_parse_equals_and_mute(self) -> None:
        opts = antivirus.parse_args(["antivirus.py", "--seed=4", "--level", "3", "--mute"])
        self.assertEqual(opts.seed, 4)
        self.assertEqual(opts.level, 3)
        self.assertTrue(opts.mute)

    def test_fullscreen_option(self) -> None:
        opts = antivirus.parse_args(["antivirus.py", "--fullscreen", "--seed", "7"])
        self.assertTrue(opts.fullscreen)
        self.assertEqual(opts.seed, 7)
        self.assertFalse(antivirus.parse_args(["antivirus.py"]).fullscreen)

    def test_mac_friendly_fullscreen_shortcuts(self) -> None:
        pg = SimpleNamespace(K_RETURN=13, K_F11=1073741892, KMOD_CTRL=0x00C0, KMOD_ALT=0x0300)
        handler = antivirus.App.fullscreen_shortcut
        self.assertTrue(handler(pg.K_RETURN, pg.KMOD_CTRL, pg))
        self.assertTrue(handler(pg.K_RETURN, pg.KMOD_ALT, pg))
        self.assertFalse(handler(pg.K_RETURN, 0, pg))
        self.assertFalse(handler(pg.K_F11, 0, pg))
        self.assertFalse(handler(32, pg.KMOD_CTRL, pg))

    def test_missing_pygame_is_reported(self) -> None:
        if importlib.util.find_spec("pygame") is not None:
            self.skipTest("pygame is installed for this interpreter")
        code, _out, err = run(["--seed", "1"])
        self.assertEqual(code, 1)
        self.assertIn("pygame", err)


class MapTest(unittest.TestCase):
    def test_seed_repeats_and_changes(self) -> None:
        def sig(seed: int, level: int) -> tuple:
            world = sim.World(seed, level)
            enemies = tuple((e.kind, round(e.x, 2), round(e.y, 2)) for e in world.enemies)
            solid = tuple(tuple(row) for row in world.solid)
            return solid, enemies, world.exit_cell

        self.assertEqual(sig(4, 3), sig(4, 3))
        self.assertNotEqual(sig(4, 3)[0], sig(5, 3)[0])

    def test_levels_are_connected_and_fully_staffed(self) -> None:
        for level, spec in enumerate(sim.PROCESSES, start=1):
            for seed in range(8):
                world = sim.World(seed, level)
                self.assertEqual(counts(world), expected(spec), (seed, level))
                self.assertGreaterEqual(len(world.rooms), 4, (seed, level))
                reached = world.reachable()
                self.assertIn(world.exit_cell, reached, (seed, level))
                self.assertTrue(world.fits(world.player.x, world.player.y, world.player.radius))
                for enemy in world.enemies:
                    cell = (int(enemy.x // sim.CELL), int(enemy.y // sim.CELL))
                    self.assertIn(cell, reached, (seed, level, enemy.kind))
                    self.assertTrue(world.fits(enemy.x, enemy.y, enemy.radius), (seed, level, enemy.kind))
                self.assertFalse(world.exit_open)

    def test_level_range(self) -> None:
        with self.assertRaises(ValueError):
            sim.World(1, 0)
        with self.assertRaises(ValueError):
            sim.Session(1, len(sim.PROCESSES) + 1)


class PlayTest(unittest.TestCase):
    def world(self) -> sim.World:
        return sim.World(arena=True)

    def test_diagonal_is_not_faster(self) -> None:
        def travel(dx: float, dy: float) -> float:
            world = self.world()
            x0, y0 = world.player.x, world.player.y
            for _ in range(30):
                world.step(1 / 60, sim.Input(dx=dx, dy=dy, aim_x=world.player.x + 20, aim_y=world.player.y))
            return math.hypot(world.player.x - x0, world.player.y - y0)

        self.assertAlmostEqual(travel(1, 0), travel(1, 1), delta=1.5)

    def test_wall_stops_the_scanner(self) -> None:
        world = self.world()
        world.player.x = (sim.COLS - 2) * sim.CELL + sim.CELL / 2
        world.player.y = (sim.ROWS // 2) * sim.CELL + sim.CELL / 2
        for _ in range(90):
            world.step(1 / 60, sim.Input(dx=1, aim_x=world.player.x + 30, aim_y=world.player.y))
        self.assertTrue(world.fits(world.player.x, world.player.y, world.player.radius))
        stopped = world.player.x
        for _ in range(30):
            world.step(1 / 60, sim.Input(dx=1, aim_x=world.player.x + 30, aim_y=world.player.y))
        self.assertAlmostEqual(world.player.x, stopped, delta=0.01)

    def test_bolt_purges_a_worm(self) -> None:
        world = self.world()
        worm = world.spawn("worm", world.player.x + 160, world.player.y)
        assert worm is not None
        worm.speed = 0
        aim = sim.Input(aim_x=worm.x, aim_y=worm.y, fire=True)
        world.step(1 / 60, aim)
        for _ in range(40):
            world.step(1 / 60, sim.Input(aim_x=worm.x, aim_y=worm.y))
        self.assertFalse(any(enemy.kind == "worm" for enemy in world.enemies))
        self.assertEqual(world.kills_score, sim.SCORES["worm"])

    def test_wall_stops_a_bolt(self) -> None:
        world = self.world()
        column = int(world.player.x // sim.CELL) + 3
        for row in range(sim.ROWS):
            world.solid[row][column] = True
        worm = world.spawn("worm", world.player.x + 8 * sim.CELL, world.player.y)
        assert worm is not None
        worm.speed = 0
        for _ in range(50):
            world.step(1 / 60, sim.Input(aim_x=worm.x, aim_y=worm.y, fire=True))
        self.assertTrue(worm.alive)
        self.assertEqual(world.kills_score, 0)

    def test_fire_cooldown(self) -> None:
        world = self.world()
        aim_x = world.player.x + 100
        aim_y = world.player.y
        world.step(1 / 60, sim.Input(aim_x=aim_x, aim_y=aim_y, fire=True))
        world.step(1 / 60, sim.Input(aim_x=aim_x, aim_y=aim_y, fire=True))
        self.assertEqual(len(world.shots), 1)

    def test_scan_reveals_only_the_near_trojan(self) -> None:
        world = self.world()
        near = world.spawn("trojan", world.player.x + 80, world.player.y)
        far = world.spawn("trojan", world.player.x + 400, world.player.y)
        assert near is not None and far is not None
        world.step(1 / 60, sim.Input(aim_x=world.player.x + 10, aim_y=world.player.y, scan=True))
        self.assertTrue(near.marked)
        self.assertFalse(near.awake)
        self.assertFalse(far.marked)
        self.assertFalse(far.awake)
        self.assertAlmostEqual(world.player.scan, 100 - sim.SCAN_COST)
        charge = world.player.scan
        world.step(1 / 60, sim.Input(scan=True, aim_x=world.player.x + 10, aim_y=world.player.y))
        self.assertAlmostEqual(world.player.scan, charge + sim.SCAN_REGEN / 60)

    def test_scan_names_a_trojan_through_a_wall(self) -> None:
        world = self.world()
        trojan = world.spawn("trojan", world.player.x + 120, world.player.y)
        assert trojan is not None
        trojan.speed = 0
        column = int(world.player.x // sim.CELL) + 2
        for row in range(sim.ROWS):
            world.solid[row][column] = True
        world.step(1 / 60, sim.Input(aim_x=trojan.x, aim_y=trojan.y, scan=True))
        self.assertTrue(trojan.marked)
        self.assertFalse(trojan.awake)

    def test_scan_quarantines_infected_memory(self) -> None:
        world = sim.World(1, 1)
        world.neutral = True
        worm = next(enemy for enemy in world.enemies if enemy.kind == "worm")
        for enemy in world.enemies:
            enemy.speed = 0
            enemy.infect = 999
        worm.infect = 0.01
        world.step(1 / 60, sim.Input())
        latent = [
            (c, r)
            for r in range(sim.ROWS)
            for c in range(sim.COLS)
            if world.tile[r][c] == sim.LATENT
        ]
        self.assertTrue(latent)
        c, r = latent[0]
        world.player.x, world.player.y = sim.cell_center(c, r)
        world.step(1 / 60, sim.Input(scan=True, aim_x=world.player.x + 20, aim_y=world.player.y))
        self.assertEqual(world.tile[r][c], sim.OPEN)
        self.assertFalse(world.solid[r][c])
        self.assertAlmostEqual(world.player.scan, 100 - sim.SCAN_COST)

    def test_worm_corruption_hardens_without_closing_the_exit(self) -> None:
        world = sim.World(1, 1)
        world.neutral = True
        worm = next(enemy for enemy in world.enemies if enemy.kind == "worm")
        for enemy in world.enemies:
            enemy.speed = 0
            enemy.infect = 999
        worm.infect = 0.01
        world.step(1 / 60, sim.Input())
        self.assertTrue(any(world.tile[r][c] == sim.LATENT for r in range(sim.ROWS) for c in range(sim.COLS)))
        for _ in range(int(sim.LATENT_LIFE * 30) + 5):
            world.step(1 / 30, sim.Input())
        self.assertTrue(any(world.tile[r][c] == sim.CORRUPT for r in range(sim.ROWS) for c in range(sim.COLS)))
        self.assertIn(world.exit_cell, world.reachable())
        for enemy in world.enemies:
            cell = (int(enemy.x // sim.CELL), int(enemy.y // sim.CELL))
            self.assertIn(cell, world.reachable())

    def test_ransom_seal_opens_again(self) -> None:
        world = sim.World(1, 7)
        world.neutral = True
        ransom = next(enemy for enemy in world.enemies if enemy.kind == "ransom")
        for enemy in world.enemies:
            enemy.speed = 0
            enemy.infect = 999
            enemy.pulse_cd = 999
        ransom.pulse_cd = 0.01
        world.step(1 / 30, sim.Input())
        sealed = [
            (c, r)
            for r in range(sim.ROWS)
            for c in range(sim.COLS)
            if world.tile[r][c] == sim.SEAL
        ]
        self.assertTrue(sealed)
        self.assertTrue(world.held)
        self.assertGreater(ransom.lockout, 0)
        for _ in range(int(sim.SEAL_TIME * 30) + 3):
            world.step(1 / 30, sim.Input())
        for c, r in sealed:
            self.assertNotEqual(world.tile[r][c], sim.SEAL)
        self.assertIn(world.exit_cell, world.reachable())
        self.assertFalse(world.held)

    def test_unstable_hall_shuts_and_opens(self) -> None:
        self.assertEqual(sim.World(1, 1).unstable, [])
        self.assertEqual(len(sim.World(1, 2).unstable), 1)
        world = sim.World(1, 3)
        self.assertGreaterEqual(len(world.unstable), 1)
        for enemy in world.enemies:
            enemy.speed = 0
            enemy.infect = 999
        c, r, _timer, _closed = world.unstable[0]
        world.unstable[0] = (c, r, 0.01, False)
        world.step(1 / 30, sim.Input())
        self.assertEqual(world.tile[r][c], sim.GATE)
        self.assertTrue(world.solid[r][c])
        world.unstable[0] = (c, r, 0.01, True)
        world.step(1 / 30, sim.Input())
        self.assertEqual(world.tile[r][c], sim.OPEN)
        self.assertFalse(world.solid[r][c])
        self.assertIn(world.exit_cell, world.reachable())

    def test_close_trojan_wakes_without_touching(self) -> None:
        world = self.world()
        trojan = world.spawn("trojan", world.player.x + 50, world.player.y)
        assert trojan is not None
        trojan.speed = 0
        trojan.dash_cd = 10
        world.step(1 / 60, sim.Input())
        self.assertTrue(trojan.awake)
        self.assertEqual(world.player.hp, 100)

    def test_sleeping_trojan_is_purged_by_a_shot(self) -> None:
        world = self.world()
        trojan = world.spawn("trojan", world.player.x + 170, world.player.y)
        assert trojan is not None
        trojan.speed = 0
        trojan.dash_cd = 10
        world.step(1 / 60, sim.Input(aim_x=trojan.x, aim_y=trojan.y, fire=True))
        for _ in range(40):
            world.step(1 / 60, sim.Input(aim_x=trojan.x, aim_y=trojan.y))
        self.assertFalse(any(enemy.kind == "trojan" for enemy in world.enemies))
        self.assertEqual(world.kills_score, sim.SCORES["trojan"])

    def test_sleeping_trojan_holds_the_exit_shut(self) -> None:
        world = self.world()
        trojan = world.spawn("trojan", 900, 900)
        assert trojan is not None
        world.step(1 / 60, sim.Input())
        self.assertFalse(trojan.awake)
        self.assertFalse(world.exit_open)

    def test_iframes_block_a_second_hit(self) -> None:
        world = self.world()
        world.player.hp = 80
        worm = world.spawn("worm", world.player.x, world.player.y)
        assert worm is not None
        worm.speed = 0
        world.step(1 / 60, sim.Input())
        self.assertEqual(world.player.hp, 80 - worm.damage)
        world.step(1 / 60, sim.Input())
        self.assertEqual(world.player.hp, 80 - worm.damage)

    def test_packet_damages_the_scanner(self) -> None:
        world = self.world()
        world.player.x, world.player.y = 400, 400
        spy = world.spawn("spyware", 760, 400)
        assert spy is not None
        spy.speed = 0
        spy.cooldown = 0
        world.step(1 / 60, sim.Input(aim_x=760, aim_y=400))
        packets = [shot for shot in world.shots if not shot.friendly]
        self.assertTrue(packets)
        packet = packets[0]
        packet.x = world.player.x - 8
        packet.y = world.player.y
        packet.vx = 200
        packet.vy = 0
        packet.life = 1
        world.step(1 / 60, sim.Input())
        self.assertLess(world.player.hp, 100)

    def test_lock_ring_hits_inside_and_misses_outside(self) -> None:
        outside = self.world()
        ransom = outside.spawn("ransom", 700, 500)
        assert ransom is not None
        ransom.speed = 0
        ransom.pulse = 0.02
        outside.player.x = ransom.x + sim.RANSOM_RADIUS + 40
        outside.player.y = ransom.y
        outside.step(1 / 30, sim.Input())
        self.assertEqual(outside.player.hp, 100)

        inside = self.world()
        ransom = inside.spawn("ransom", 700, 500)
        assert ransom is not None
        ransom.speed = 0
        ransom.pulse = 0.02
        inside.player.x = ransom.x + 40
        inside.player.y = ransom.y
        inside.step(1 / 30, sim.Input())
        self.assertEqual(inside.player.hp, 100 - sim.RANSOM_BLAST)

    def test_exit_opens_after_the_last_threat(self) -> None:
        world = self.world()
        worm = world.spawn("worm", 800, 800)
        assert worm is not None
        worm.speed = 0
        world.step(1 / 60, sim.Input())
        self.assertFalse(world.exit_open)
        worm.alive = False
        world.player.x = world.exit_x
        world.player.y = world.exit_y
        world.step(1 / 60, sim.Input())
        self.assertEqual(world.result, "clear")

    def test_worm_walks_around_a_wall(self) -> None:
        world = self.world()
        world.neutral = True
        world.player.x, world.player.y = 280.0, 400.0
        column = int(world.player.x // sim.CELL) + 5
        for row in range(1, sim.ROWS - 1):
            if 4 <= row <= 5:
                continue
            world.solid[row][column] = True
            world.solid[row][column + 1] = True
        worm = world.spawn("worm", world.player.x + 360, world.player.y)
        assert worm is not None
        world.alert_x = world.player.x
        world.alert_y = world.player.y
        world.alert_t = 30.0
        start = math.hypot(worm.x - world.player.x, worm.y - world.player.y)
        for _ in range(12 * 60):
            world.step(1 / 60, sim.Input())
            if math.hypot(worm.x - world.player.x, worm.y - world.player.y) < 40:
                break
        end = math.hypot(worm.x - world.player.x, worm.y - world.player.y)
        self.assertLess(end, 48)
        self.assertLess(end, start / 2)
        self.assertTrue(world.fits(worm.x, worm.y, worm.radius))

    def test_boss_walks_through_a_narrow_gap(self) -> None:
        world = self.world()
        world.neutral = True
        world.player.x, world.player.y = 280.0, 400.0
        column = int(world.player.x // sim.CELL) + 5
        for row in range(1, sim.ROWS - 1):
            if 4 <= row <= 5:
                continue
            world.solid[row][column] = True
            world.solid[row][column + 1] = True
        boss = world.spawn("boss", world.player.x + 360, world.player.y)
        assert boss is not None
        for _ in range(18 * 60):
            world.step(1 / 60, sim.Input())
            if math.hypot(boss.x - world.player.x, boss.y - world.player.y) < 50:
                break
        self.assertLess(math.hypot(boss.x - world.player.x, boss.y - world.player.y), 60)
        self.assertTrue(world.fits(boss.x, boss.y, boss.radius))

    def test_boss_spawns_worms(self) -> None:
        self.assertEqual(sim.BOSS_PHASES[1][0], "spawn")
        world = self.world()
        world.player.x, world.player.y = 220, 220
        boss = world.spawn("boss", 640, 420)
        assert boss is not None
        boss.phase = 1
        boss.acted = False
        boss.phase_t = 0
        before = world.threat_count()
        world.step(1 / 60, sim.Input())
        self.assertGreater(world.threat_count(), before)
        self.assertTrue(any(enemy.kind == "worm" for enemy in world.enemies))

    def test_unalerted_worm_stays_behind_the_wall(self) -> None:
        world = self.world()
        world.neutral = True
        world.player.x, world.player.y = 280.0, 400.0
        column = int(world.player.x // sim.CELL) + 5
        for row in range(1, sim.ROWS - 1):
            if 4 <= row <= 5:
                continue
            world.solid[row][column] = True
            world.solid[row][column + 1] = True
        worm = world.spawn("worm", world.player.x + 360, world.player.y)
        assert worm is not None
        start = worm.x
        for _ in range(3 * 60):
            world.step(1 / 60, sim.Input())
        self.assertAlmostEqual(worm.x, start, delta=8)
        self.assertGreater(math.hypot(worm.x - world.player.x, worm.y - world.player.y), 200)

    def test_spy_alert_calls_a_worm_through_the_wall(self) -> None:
        world = self.world()
        world.neutral = True
        world.player.x, world.player.y = 280.0, 400.0
        column = int(world.player.x // sim.CELL) + 5
        for row in range(1, sim.ROWS - 1):
            if 4 <= row <= 5:
                continue
            world.solid[row][column] = True
            world.solid[row][column + 1] = True
        worm = world.spawn("worm", world.player.x + 360, world.player.y)
        spy = world.spawn("spyware", world.player.x + 40, world.player.y)
        assert worm is not None and spy is not None
        spy.speed = 0
        spy.cooldown = 99
        start = math.hypot(worm.x - world.player.x, worm.y - world.player.y)
        for _ in range(12 * 60):
            world.step(1 / 60, sim.Input())
            if math.hypot(worm.x - world.player.x, worm.y - world.player.y) < 48:
                break
        end = math.hypot(worm.x - world.player.x, worm.y - world.player.y)
        self.assertLess(end, start / 2)
        self.assertGreater(world.alert_t, 0)

    def test_worm_replicates_through_multiple_generations_and_respects_cap(self) -> None:
        world = sim.World(1, 1)
        world.neutral = True
        parents = [enemy for enemy in world.enemies if enemy.kind == "worm"]
        self.assertEqual(len(parents), sim.PROCESSES[0].worms)
        # Force just one parent to reproduce twice without passing through
        # regular game time; this tests the mechanism independently of AI.
        parent = parents[0]
        for enemy in world.enemies:
            enemy.infect = 999
            enemy.replicate_cd = 999
            enemy.speed = 0
        self.assertTrue(world._replicate(parent))
        parent.copies += 1
        self.assertTrue(world._replicate(parent))
        parent.copies += 1
        children = [enemy for enemy in world.enemies if enemy.child]
        self.assertEqual(len(children), 2)
        self.assertTrue(world._replicate(children[0]))
        while sum(e.alive and e.kind == "worm" for e in world.enemies) < sim.REPL_CAP:
            if not any(world._replicate(e) for e in list(world.enemies) if e.kind == "worm"):
                self.fail("Could not fill worm population to cap")
        self.assertFalse(world._replicate(parent))
        self.assertEqual(sum(e.alive and e.kind == "worm" for e in world.enemies), sim.REPL_CAP)

    def test_ransomware_jams_purge_only_inside_sealed_room(self) -> None:
        world = sim.World(2, 7)
        world.neutral = True
        room = world._room_at(*world.player_cell())
        self.assertIsNotNone(room)
        world.held.append((room.x, room.y, room.w, room.h, 2.0))
        self.assertTrue(world.weapons_locked())
        before = len(world.shots)
        world.step(1 / 60, sim.Input(aim_x=world.player.x + 80, aim_y=world.player.y, fire=True))
        self.assertEqual(len(world.shots), before)
        self.assertEqual(world.player.fire_cd, 0)
        # Scanning remains available as the defensive countermeasure.
        scan_before = world.player.scan
        world.step(1 / 60, sim.Input(scan=True))
        self.assertLess(world.player.scan, scan_before)
        world.held.clear()
        self.assertFalse(world.weapons_locked())
        world.step(1 / 60, sim.Input(aim_x=world.player.x + 80, aim_y=world.player.y, fire=True))
        self.assertTrue(any(shot.friendly for shot in world.shots))

    def test_corruption_spreads_into_a_neighbor(self) -> None:
        world = sim.World(1, 1)
        world.neutral = True
        for enemy in world.enemies:
            enemy.speed = 0
            enemy.infect = 999
        spot = None
        for r in range(1, sim.ROWS - 1):
            for c in range(1, sim.COLS - 1):
                if world.tile[r][c] != sim.OPEN or world._open_count(c, r) < 4:
                    continue
                if world._occupied(c, r) or world._would_strand(c, r):
                    continue
                for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nc, nr = c + dc, r + dr
                    if world.tile[nr][nc] != sim.OPEN or world._occupied(nc, nr):
                        continue
                    if world._would_strand(nc, nr) or world._open_count(nc, nr) < 3:
                        continue
                    spot = (c, r)
                    break
                if spot:
                    break
            if spot:
                break
        self.assertIsNotNone(spot)
        assert spot is not None
        c, r = spot
        world._fill(c, r, sim.CORRUPT)
        world.spread_t = 0.01
        world.step(1 / 30, sim.Input())
        self.assertTrue(any(
            world.tile[r + dr][c + dc] == sim.LATENT
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1))
        ))

    def test_trojan_wears_a_file_name(self) -> None:
        world = sim.World(1, 2)
        trojan = next(enemy for enemy in world.enemies if enemy.kind == "trojan")
        self.assertIn(trojan.cover, sim.FILE_NAMES)
        self.assertFalse(trojan.marked)
        self.assertFalse(trojan.awake)

    def test_kernel_system_drains_and_can_crash(self) -> None:
        quiet = sim.World(1, 1)
        quiet.neutral = True
        for _ in range(30):
            quiet.step(1 / 30, sim.Input())
        self.assertEqual(quiet.system, 100)
        self.assertIsNone(quiet.result)

        world = sim.World(1, len(sim.PROCESSES))
        world.neutral = True
        self.assertEqual(world.system, 100)
        for enemy in world.enemies:
            enemy.speed = 0
            enemy.infect = 999
        for _ in range(30):
            world.step(1 / 30, sim.Input())
        self.assertLess(world.system, 100)
        self.assertGreater(world.system, 98)

        world.system = 40
        pc, pr = world.player_cell()
        world.tile[pr][pc] = sim.LATENT
        world.latents.append((pc, pr, 5.0))
        world.player.scan = 100
        world.step(1 / 60, sim.Input(scan=True, aim_x=world.player.x + 20, aim_y=world.player.y))
        self.assertGreater(world.system, 40)
        self.assertEqual(world.tile[pr][pc], sim.OPEN)

        cell = None
        for r in range(2, sim.ROWS - 2):
            for c in range(2, sim.COLS - 2):
                if world.tile[r][c] != sim.OPEN or world._occupied(c, r):
                    continue
                if world._open_count(c, r) < 4 or world._would_strand(c, r):
                    continue
                cell = (c, r)
                break
            if cell:
                break
        self.assertIsNotNone(cell)
        assert cell is not None
        before = world.system
        world.tile[cell[1]][cell[0]] = sim.LATENT
        world.latents.append((cell[0], cell[1], 0.01))
        world.step(1 / 30, sim.Input())
        self.assertEqual(world.tile[cell[1]][cell[0]], sim.CORRUPT)
        self.assertLess(world.system, before - sim.SYSTEM_HARDEN + 0.2)

        boss = next(enemy for enemy in world.enemies if enemy.kind == "boss" and enemy.alive)
        boss.alive = False
        held = world.system
        for _ in range(30):
            world.step(1 / 30, sim.Input())
        self.assertAlmostEqual(world.system, held)
        boss.alive = True
        world.enemies.append(boss)
        world.system = 0.01
        world.step(1 / 30, sim.Input())
        self.assertEqual(world.result, "crash")
        self.assertIn(("crash",), world.events)

    def test_defeated_poly_sys_stops_all_sys_integrity_loss(self) -> None:
        world = sim.World(1, len(sim.PROCESSES))
        world.neutral = True
        boss = next(e for e in world.enemies if e.kind == "boss")
        boss.alive = False
        world.system = 50.0
        # Infection already planted before the boss was defeated can still
        # mature, but must no longer destroy system integrity.
        cell = None
        for r in range(2, sim.ROWS - 2):
            for c in range(2, sim.COLS - 2):
                if (world.tile[r][c] == sim.OPEN and not world._occupied(c, r)
                        and world._open_count(c, r) == 4 and not world._would_strand(c, r)):
                    cell = (c, r)
                    break
            if cell:
                break
        self.assertIsNotNone(cell)
        c, r = cell
        world.tile[r][c] = sim.LATENT
        world.latents.append((c, r, 0.001))
        world.step(1 / 30, sim.Input())
        self.assertEqual(world.tile[r][c], sim.CORRUPT)
        self.assertEqual(world.system, 50.0)
        self.assertIsNone(world.result)
        world._strain_system(100)
        self.assertEqual(world.system, 50.0)
        for _ in range(90):
            world.step(1 / 30, sim.Input())
        self.assertEqual(world.system, 50.0)

    def test_traffic_stops_on_corrupt_memory(self) -> None:
        world = sim.World(1, 1)
        packets = [carrier for carrier in world.carriers if carrier.name == ""]
        daemons = [carrier for carrier in world.carriers if carrier.name]
        self.assertGreaterEqual(len(packets), 1)
        self.assertGreaterEqual(len(daemons), 1)
        packet = packets[0]
        self.assertFalse(packet.halted)
        c, r = packet.cells[packet.index]
        world._fill(c, r, sim.CORRUPT)
        world.step(1 / 60, sim.Input())
        self.assertTrue(packet.halted)



class ChangeTest(unittest.TestCase):
    def test_decoys_sit_on_the_floor_and_a_scan_marks_them_clean(self) -> None:
        for level in range(1, len(sim.PROCESSES) + 1):
            for seed in range(4):
                world = sim.World(seed, level)
                self.assertLessEqual(len(world.decoys), sim.PROCESSES[level - 1].decoys)
                for decoy in world.decoys:
                    self.assertIn(decoy.name, sim.FILE_NAMES)
                    c, r = world._clamp_cell(decoy.x, decoy.y)
                    self.assertFalse(world.solid[r][c])
        world = sim.World(2, 2)
        self.assertTrue(world.decoys)
        decoy = world.decoys[0]
        world.player.x, world.player.y = decoy.x + 40, decoy.y
        world.step(1 / 60, sim.Input(scan=True))
        self.assertTrue(decoy.checked)
        self.assertEqual(world.threat_count(), sim.World(2, 2).threat_count())

    def test_kernel_boss_rages_as_it_weakens(self) -> None:
        world = sim.World(arena=True)
        boss = world.spawn("boss", 640, 420)
        assert boss is not None
        self.assertEqual(world.boss_rage(boss), 0.0)
        boss.hp = 1
        self.assertEqual(world.boss_rage(boss), 1.0)
        boss.phase = 2
        boss.acted = False
        before = len(world.shots)
        world._update_boss(boss, 1 / 60)
        self.assertEqual(len(world.shots) - before, 7)

    def test_bolt_passes_a_corner_its_center_clears(self) -> None:
        world = sim.World(arena=True)
        c, r = 12, 10
        world.solid[r][c] = True
        world.tile[r][c] = sim.PACKED
        # Fly along a line 2 px past the block's lower edge.
        y = (r + 1) * sim.CELL + 2
        world.shots.append(sim.Shot(
            x=c * sim.CELL - 30, y=y, px=0, py=0, vx=sim.BOLT_SPEED, vy=0,
            radius=4, life=0.2, friendly=True, damage=1,
        ))
        world.step(1 / 60, sim.Input())
        self.assertTrue(world.shots and not world.shots[0].dead)

    def test_daemons_sometimes_rest(self) -> None:
        world = sim.World(1, 3)
        world.neutral = True
        rested = False
        for _ in range(60 * 30):
            world.step(1 / 30, sim.Input())
            if any(carrier.rest > 0 for carrier in world.carriers if carrier.name):
                rested = True
                break
        self.assertTrue(rested)

    def test_map_layer_tracks_changed_cells(self) -> None:
        if importlib.util.find_spec("pygame") is None:
            self.skipTest("pygame is not installed for this interpreter")
        import os
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        pg = antivirus.engine()
        pg.init()
        try:
            screen = pg.display.set_mode((antivirus.VIEW_W, antivirus.VIEW_H))
            app = antivirus.App(screen, 1, 1, True)
            app.session = sim.Session(1, 1)
            app.session.mount()
            app.draw()
            layer = app.layer
            assert layer is not None
            world = app.session.world
            c, r = world.player_cell()
            c += 1
            before = tuple(layer.surface.get_at((c * sim.CELL + 20, r * sim.CELL + 20)))
            world._fill(c, r, sim.CORRUPT)
            app.draw()
            after = tuple(layer.surface.get_at((c * sim.CELL + 20, r * sim.CELL + 20)))
            self.assertNotEqual(before, after)
            self.assertEqual(layer.rev, world.map_rev)
        finally:
            pg.quit()


class StageTest(unittest.TestCase):
    def test_nine_processes_end_at_the_kernel(self) -> None:
        self.assertEqual(len(sim.PROCESSES), 9)
        self.assertEqual(sim.PROCESSES[-1].slug, "kernel")
        self.assertEqual([spec.boss for spec in sim.PROCESSES].count(True), 1)
        self.assertEqual(len({spec.slug for spec in sim.PROCESSES}), len(sim.PROCESSES))

    def test_gates_and_daemons_follow_the_spec(self) -> None:
        for level, spec in enumerate(sim.PROCESSES, start=1):
            for seed in range(3):
                world = sim.World(seed, level)
                self.assertLessEqual(len(world.unstable), spec.gates, (seed, level))
                daemons = [carrier for carrier in world.carriers if carrier.name]
                self.assertLessEqual(len(daemons), spec.daemons, (seed, level))
        apps = next(i for i, spec in enumerate(sim.PROCESSES, start=1) if spec.slug == "applications")
        self.assertGreater(max(
            len([c for c in sim.World(seed, apps).carriers if c.name]) for seed in range(4)
        ), 2)

    def test_filenames_on_the_floor_do_not_repeat(self) -> None:
        for level in range(1, len(sim.PROCESSES) + 1):
            for seed in range(3):
                world = sim.World(seed, level)
                names = [label for label, _x, _y in world.labels]
                names += [decoy.name for decoy in world.decoys]
                names += [enemy.cover for enemy in world.enemies if enemy.cover]
                names += [carrier.name for carrier in world.carriers if carrier.name]
                self.assertEqual(len(names), len(set(names)), (seed, level, names))


class SessionTest(unittest.TestCase):
    def test_clear_banks_the_bonus_and_mounts_the_next_process(self) -> None:
        session = sim.Session(5, 1)
        session.world = sim.World(arena=True)
        session.mode = "play"
        session.world.player.x = session.world.exit_x
        session.world.player.y = session.world.exit_y
        session.step(1 / 60, sim.Input())
        self.assertEqual(session.mode, "brief")
        self.assertEqual(session.level, 2)
        self.assertEqual(session.cleared_name, "DOWNLOADS")
        self.assertEqual(session.integrity, 100)
        self.assertEqual(session.score, sim.CLEAR_BONUS + 100 * sim.INTEGRITY_BONUS)
        self.assertEqual(session.world.solid, sim.World(5, 2).solid)
        self.assertIn(("clear",), session.world.events)

    def test_crash_drops_the_process_and_retry_restores_it(self) -> None:
        session = sim.Session(3, 1)
        session.world = sim.World(arena=True)
        session.mode = "play"
        session.world.player.hp = 5
        worm = session.world.spawn("worm", session.world.player.x, session.world.player.y)
        assert worm is not None
        worm.speed = 0
        session.step(1 / 60, sim.Input())
        self.assertEqual(session.mode, "crash")
        self.assertEqual(session.score, 0)
        self.assertEqual(session.level, 1)
        session.retry()
        self.assertEqual(session.mode, "play")
        self.assertEqual(session.world.player.hp, 100)
        self.assertFalse(session.world.arena)
        self.assertEqual(counts(session.world), expected(sim.PROCESSES[0]))

    def test_kernel_clear_wins(self) -> None:
        session = sim.Session(1, len(sim.PROCESSES))
        session.world = sim.World(arena=True)
        session.mode = "play"
        session.world.player.x = session.world.exit_x
        session.world.player.y = session.world.exit_y
        session.step(1 / 60, sim.Input())
        self.assertEqual(session.mode, "win")
        self.assertEqual(session.level, len(sim.PROCESSES))
        self.assertEqual(session.score, sim.CLEAR_BONUS + 100 * sim.INTEGRITY_BONUS)


if __name__ == "__main__":
    unittest.main()

class RepairModuleTest(unittest.TestCase):
    def test_modules_are_rare_seeded_and_ransomware_guarded(self) -> None:
        for seed in range(6):
            for level in range(1, 10):
                world = sim.World(seed, level)
                repeat = sim.World(seed, level)
                module = world.repair_module
                self.assertEqual(module, repeat.repair_module)
                if not world.spec.ransom:
                    self.assertIsNone(module)
                if module is None:
                    continue
                room = world._room_at(*world._clamp_cell(module.x, module.y))
                self.assertIsNotNone(room)
                self.assertTrue(any(e.kind == "ransom" and
                    world._room_at(*world._clamp_cell(e.x, e.y)) == room
                    for e in world.enemies))
                self.assertIn(world._clamp_cell(module.x, module.y), world.reachable())
                self.assertTrue(world.fits(module.x, module.y, sim.MODULE_RADIUS))

    def test_pickup_heals_without_exceeding_cap(self) -> None:
        world = sim.World(1, 4)
        self.assertIsNotNone(world.repair_module)
        module = world.repair_module
        world.player.hp = 60
        world.player.x, world.player.y = module.x, module.y
        world._collect_repair_module()
        self.assertEqual(world.player.hp, 85)
        self.assertIsNone(world.repair_module)
        self.assertIn(("repair", 25, module.x, module.y), world.events)
        world.repair_module = sim.RepairModule(module.x, module.y)
        world.player.hp = 95
        world._collect_repair_module()
        self.assertEqual(world.player.hp, 100)
        self.assertIsNone(world.repair_module)

    def test_full_health_does_not_waste_pickup(self) -> None:
        world = sim.World(1, 4)
        module = world.repair_module
        self.assertIsNotNone(module)
        world.player.x, world.player.y = module.x, module.y
        world._collect_repair_module()
        self.assertIs(world.repair_module, module)
        world.player.hp = 77
        world._collect_repair_module()
        self.assertIsNone(world.repair_module)
        self.assertEqual(world.player.hp, 100)

    def test_lockdown_does_not_prevent_pickup_or_linger(self) -> None:
        world = sim.World(1, 4)
        module = world.repair_module
        self.assertIsNotNone(module)
        room = world._room_at(*world._clamp_cell(module.x, module.y))
        self.assertIsNotNone(room)
        world.held.append((room.x, room.y, room.w, room.h, 0.05))
        world.player.hp = 50
        world.player.x, world.player.y = module.x, module.y
        self.assertTrue(world.weapons_locked())
        world._collect_repair_module()
        self.assertEqual(world.player.hp, 75)
        self.assertIsNone(world.repair_module)
        world._memory(0.1)
        self.assertFalse(world.weapons_locked())

    def test_existing_between_stage_repair_is_unchanged(self) -> None:
        self.assertEqual(sim.REPAIR, 17)
