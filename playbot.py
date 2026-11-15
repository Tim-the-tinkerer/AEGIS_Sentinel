"""Headless AEGIS Sentinel playtest bot (real simulation inputs, no cheats).

Put this file next to sim.py and run: python3 playbot.py --seed 1
For a quick smoke test: python3 playbot.py --seed 1 --seconds 30
The bot uses simulation information unavailable to a human player; its success
is not a measure of human difficulty. It never edits world health or enemies.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sim

FPS = 30


def distance(a, b, x, y):
    return math.hypot(a - x, b - y)


def unit(x, y):
    d = math.hypot(x, y)
    return (x / d, y / d) if d > 1e-6 else (0., 0.)


def body_clear(world, x0, y0, x1, y1, radius):
    """A bullet-size line of sight is not a body-size navigable corridor."""
    d = math.hypot(x1 - x0, y1 - y0)
    for i in range(1, max(2, int(d / 5) + 1)):
        t = i / max(1, int(d / 5))
        if not world.fits(x0 + (x1 - x0) * t,
                          y0 + (y1 - y0) * t, radius):
            return False
    return True


def nav(world, px, py, destination, route_cache, tick):
    goal = (int(destination[0] // sim.CELL), int(destination[1] // sim.CELL))
    here = world.player_cell()
    path, last_goal = route_cache
    if (tick % 8 == 0 or last_goal != goal or not path
            or (path and world.solid[path[0][1]][path[0][0]])):
        path = world._find_route(*here, *goal)
        last_goal = goal
    if here in path:
        path = path[path.index(here) + 1:]
    route_cache[:] = [path, last_goal]
    if path:
        cell = path[0]
        for candidate in path[:6]:
            cx, cy = sim.cell_center(*candidate)
            if not body_clear(world, px, py, cx, cy, world.player.radius + 1):
                break
            cell = candidate
        wx, wy = sim.cell_center(*cell)
        if not body_clear(world, px, py, wx, wy, world.player.radius + 1):
            # The shortest cell path can still cut a corner when the player
            # stands off-centre. Re-center on the current navigable tile first.
            wx, wy = sim.cell_center(*here)
        return unit(wx - px, wy - py)
    # During a ransomware seal there may genuinely be no route. Avoid
    # steering straight into the wall; wait, dodge, and replan as it expires.
    if body_clear(world, px, py, *destination, world.player.radius + 1):
        return unit(destination[0] - px, destination[1] - py)
    return 0., 0.


def dodge(world, x, y):
    """Repel incoming hostile bolts and close hostile bodies."""
    vx = vy = 0.
    for shot in world.shots:
        if shot.dead or shot.friendly:
            continue
        dx, dy = x - shot.x, y - shot.y
        d = math.hypot(dx, dy)
        if d > 110:
            continue
        vel = math.hypot(shot.vx, shot.vy)
        if vel <= 0:
            continue
        closing = (dx * shot.vx + dy * shot.vy) / (max(d, 1) * vel)
        if closing > 0.15:
            strength = (1 - d / 110) * (1 + closing)
            vx += dx / max(d, 1) * strength * 2
            vy += dy / max(d, 1) * strength * 2
    for enemy in world.enemies:
        if not enemy.alive or not enemy.awake:
            continue
        dx, dy = x - enemy.x, y - enemy.y
        d = math.hypot(dx, dy)
        if 0 < d < 62 and world._sees(x, y, enemy.x, enemy.y):
            strength = (62 - d) / 62
            vx += dx / d * strength * 1.4
            vy += dy / d * strength * 1.4
    return vx, vy


def choose_target(world):
    p = world.player
    alive = [e for e in world.enemies if e.alive]
    if not alive:
        return None
    # The kernel SYS timer makes the boss the priority. Other processes
    # are distractions until the boss is eliminated.
    if world.level == len(sim.PROCESSES):
        bosses = [e for e in alive if e.kind == 'boss']
        if bosses:
            return bosses[0]
    # Target dangerous replication sources and ransomware before remote targets.
    # Prioritize reachable/visible opponents; otherwise move toward the closest.
    here = world.player_cell()
    def score(e):
        d = distance(p.x, p.y, e.x, e.y)
        visible = world._sees(p.x, p.y, e.x, e.y)
        target_cell = (int(e.x // sim.CELL), int(e.y // sim.CELL))
        route = world._find_route(*here, *target_cell)
        reachable = bool(route) or here == target_cell
        preference = {'worm': -45, 'ransom': -35, 'spyware': -10, 'trojan': 5, 'boss': -65}.get(e.kind, 0)
        if e.kind == 'worm' and e.copies < sim.WORM_REPLICATION_LIMIT:
            preference -= 25
        if e.kind == 'trojan' and not e.awake:
            preference += 35
        return d + preference + (10000 if not reachable and not visible else 0) + (90 if not visible else 0)
    return min(alive, key=score)



def boss_movement(world, boss, seed):
    """Choose a legal, shot-aware position while preserving useful boss DPS.

    Evaluate actual world collision at short and medium horizons; avoid
    projectiles based on predicted trajectories, not just their current spot.
    """
    player = world.player
    dx, dy = boss.x-player.x, boss.y-player.y
    ux, uy = unit(dx, dy)
    options = [(0., 0.)]
    for i in range(16):
        a = i*math.tau/16
        options.append((math.cos(a), math.sin(a)))
    best = (-1e20, (0., 0.))
    # Small deterministic variation avoids symmetric local optima on retries.
    preference = 1 if (seed + int(world.time//2))%2 else -1
    for mx, my in options:
        # Simulate a short positional horizon, with intermediate wall tests.
        legal = True
        x, y = player.x, player.y
        for j in range(1, 5):
            nx = player.x + mx*sim.PLAYER_SPEED*.12*j
            ny = player.y + my*sim.PLAYER_SPEED*.12*j
            if not world.fits(nx, ny, player.radius):
                legal = False
                break
            x,y = nx,ny
        if not legal:
            continue
        future_d = math.hypot(boss.x-x,boss.y-y)
        los = world._sees(x,y,boss.x,boss.y)
        score = (10 if los else -24) - abs(future_d-180)*.12
        if future_d < 105: score -= (105-future_d)*.9
        if future_d > 305: score -= (future_d-305)*.35
        if world._sees(player.x,player.y,boss.x,boss.y) and not los:
            score -= 35
        # Predicted nearest approach to hostile packets over the next 0.48s.
        for shot in world.shots:
            if shot.dead or shot.friendly:
                continue
            closest = 1e9
            for t in (.08,.16,.25,.34,.45):
                sx,sy = shot.x+shot.vx*t,shot.y+shot.vy*t
                px,py = player.x+mx*sim.PLAYER_SPEED*t,player.y+my*sim.PLAYER_SPEED*t
                closest=min(closest, math.hypot(px-sx,py-sy))
            danger=player.radius+shot.radius+13
            if closest < danger:
                score -= 125*(1-closest/danger)+22
            elif closest < danger+32:
                score -= (danger+32-closest)*.6
        for enemy in world.enemies:
            if not enemy.alive or not enemy.awake or enemy is boss:
                continue
            nd=math.hypot(x-enemy.x,y-enemy.y)
            if nd<enemy.radius+player.radius+20:
                score -= (enemy.radius+player.radius+20-nd)*1.15
        score += .6*preference*(mx*(-uy)+my*ux)
        # No need to lose time orbiting if there are no imminent threats.
        if mx==0 and my==0 and los and 145<future_d<225:
            score+=3
        if score>best[0]: best=(score,(mx,my))
    return best[1]


class BossMetrics:
    """Per-attempt, measured after each real simulation step."""
    def __init__(self, world):
        self.start = world.time
        self.frames = self.fire_frames = self.jam_frames = self.los_frames = 0
        self.in_range_frames = self.hits = self.shots = 0
        self.boss_hp = next((e.hp for e in world.enemies if e.alive and e.kind == 'boss'), 0)
        self.last_report = world.time

    def update(self, world, boss, firing, jammed, los, in_range, fired_event):
        self.frames += 1
        self.fire_frames += bool(firing)
        self.jam_frames += bool(jammed)
        self.los_frames += bool(los)
        self.in_range_frames += bool(in_range)
        self.shots += bool(fired_event)
        newhp = boss.hp if boss else 0
        if newhp<self.boss_hp:
            self.hits += self.boss_hp-newhp
        self.boss_hp=newhp

    def summary(self, world):
        duration=self.frames/FPS
        ratio=lambda n: 100*n/max(1,self.frames)
        return (f'boss_time={duration:.1f}s firing={ratio(self.fire_frames):.0f}% '
                f'LOS={ratio(self.los_frames):.0f}% in_range={ratio(self.in_range_frames):.0f}% '
                f'jam={self.jam_frames/FPS:.1f}s shots={self.shots} '
                f'boss_hits={self.hits} hit_rate={100*self.hits/max(1,self.shots):.0f}% '
                f'SYS={world.system:.1f}')

def drive(seed=1, maxsteps=60000, max_retries=5, verbose=False, boss_log=False, restore=False):
    session = sim.Session(seed)
    session.mount()
    retries = 0
    last_level = session.level
    route_cache = [[], None]
    stalled = 0
    last_cell = None
    last_position = None
    repairs_collected = 0
    restored_cells = 0
    restore_stage_logged = set()
    max_worms = 0
    jams = 0
    metrics = None
    for step in range(maxsteps):
        if session.mode == 'win':
            break
        if session.mode == 'brief':
            session.mount()
            route_cache[:] = [[], None]
            continue
        if session.mode == 'crash':
            retries += 1
            cause = ('INTEGRITY' if session.world.player.hp <= 0 else
                     'SYS' if session.world.system <= 0 else 'UNKNOWN')
            bosses = [e for e in session.world.enemies if e.alive and e.kind == 'boss']
            boss_status = (f'{bosses[0].hp}/{bosses[0].max_hp}' if bosses else 'defeated')
            print(f'CRASH stage={session.level} cause={cause} t={session.play_time:.1f}s '
                  f'hp={session.world.player.hp} SYS={session.world.system:.1f} '
                  f'boss_hp={boss_status}')
            if metrics is not None:
                print('BOSS_SUMMARY', metrics.summary(session.world))
            if retries > max_retries:
                break
            session.retry()
            metrics = None
            route_cache[:] = [[], None]
            continue
        if session.level != last_level:
            print(f'CLEAR stage={last_level} total={session.play_time:.1f}s score={session.score} integrity={session.integrity}')
            last_level = session.level
            route_cache[:] = [[], None]
            stalled = 0
            metrics = None
        world = session.world
        player = world.player
        enemies = [e for e in world.enemies if e.alive]
        max_worms = max(max_worms, sum(e.kind == 'worm' for e in enemies))
        target = choose_target(world)
        boss_fight = bool(world.level == len(sim.PROCESSES) and target and target.kind == 'boss')
        if boss_fight and metrics is None:
            metrics = BossMetrics(world)
            if boss_log: print(f'BOSS_START retry={retries} t={session.play_time:.1f}s SYS={world.system:.1f}')
        jammed = world.weapons_locked()
        if jammed and step % 30 == 0:
            jams += 1
        module = world.repair_module
        # The repair module is a tactical detour only when it can restore
        # at least 15 integrity and the destination is presently reachable.
        # Keep the player fighting while moving toward it.
        repair_goal = None
        if module and player.hp <= 85:
            goal_cell = (int(module.x // sim.CELL), int(module.y // sim.CELL))
            if world._find_route(*world.player_cell(), *goal_cell):
                repair_goal = (module.x, module.y)
        restoration_goal = None
        if restore and not target and world.secured and world.restoration_remaining():
            # A hardened cell is an obstacle: route to an accessible floor tile
            # from which the scanner can reach it, rather than onto the cell.
            here = world.player_cell()
            possible = []
            for r in range(sim.ROWS):
                for c in range(sim.COLS):
                    if world.tile[r][c] not in (sim.CORRUPT, sim.LATENT):
                        continue
                    cx, cy = sim.cell_center(c, r)
                    if math.hypot(player.x-cx, player.y-cy) <= sim.SCAN_RADIUS - 16:
                        possible.append((0, player.x, player.y))
                        break
                    for dr, dc in ((-1,0),(1,0),(0,-1),(0,1),(-2,0),(2,0),(0,-2),(0,2)):
                        nr,nc = r+dr,c+dc
                        if not (0<=nr<sim.ROWS and 0<=nc<sim.COLS) or world.solid[nr][nc]:
                            continue
                        nx,ny = sim.cell_center(nc,nr)
                        if math.hypot(nx-cx, ny-cy)>sim.SCAN_RADIUS - 16:
                            continue
                        path = world._find_route(*here,nc,nr)
                        if not path and here != (nc,nr):
                            continue
                        possible.append((len(path) + math.hypot(nx-player.x,ny-player.y)/sim.CELL, nx, ny))
                    if possible and possible[-1][0]==0:
                        break
                if possible and possible[-1][0]==0:
                    break
            if possible:
                _, gx, gy = min(possible)
                restoration_goal = (gx, gy)
            elif world.level not in restore_stage_logged:
                print(f'RESTORE_UNREACHABLE stage={world.level} remaining={world.restoration_remaining()}')
                restore_stage_logged.add(world.level)
        tx, ty = ((target.x, target.y) if target else (world.exit_x, world.exit_y))
        aim_d = distance(player.x, player.y, tx, ty)
        # Wall-centre LOS is too permissive for diagonal shots skimming
        # corners. Test the projectile's clearance instead.
        line = body_clear(world, player.x, player.y, tx, ty, 2)
        firing = bool(target and line and aim_d < 360 and not jammed)
        # Close on target until shots reliably hit; don't simply camp at max range.
        if restoration_goal is not None:
            destination = restoration_goal
        elif repair_goal is not None:
            destination = repair_goal
        elif boss_fight and firing and aim_d < 240:
            # Fire while strafing instead of standing in the boss's firing arc.
            # Stay close enough to land repeated hits before corrupted memory
            # drives SYS to zero.
            side = 1 if (seed + int(world.time // 3)) % 2 else -1
            destination = (player.x + side * (ty - player.y),
                           player.y - side * (tx - player.x))
        elif target and firing and aim_d < (62 if target.kind == 'trojan' and not target.awake else 95):
            destination = (player.x, player.y)
        else:
            destination = (tx, ty)
        if boss_fight and (line or aim_d < 205):
            mx, my = boss_movement(world, target, seed + retries)
        else:
            # Long-distance kernel pursuit must use map pathfinding:
            # the strafe evaluator is only useful within boss range.
            mx, my = nav(world, player.x, player.y, (tx, ty) if boss_fight else destination, route_cache, step)
        if target and target.awake and aim_d < 80 and repair_goal is None and not boss_fight:
            back_x, back_y = unit(player.x - tx, player.y - ty)
            mx += back_x * 1.15
            my += back_y * 1.15
        # Detect navigation deadlocks independently of enemy health and map
        # changes. Recover by returning to the centre of our current tile.
        navigating = (not boss_fight and distance(player.x, player.y,
                      *destination) > sim.CELL and not (target and firing))
        if navigating and last_position is not None and distance(
                player.x, player.y, *last_position) < 0.5:
            stalled += 1
        else:
            stalled = 0
        last_position = (player.x, player.y)
        if navigating and stalled >= FPS:
            cx, cy = sim.cell_center(*world.player_cell())
            if distance(player.x, player.y, cx, cy) > 1.5:
                mx, my = unit(cx - player.x, cy - player.y)
            else:
                # Reset the route on the next frame; map doors may have moved.
                route_cache[:] = [[], None]
            if stalled == FPS and verbose:
                print(f'NAV_RECOVER stage={session.level} cell={world.player_cell()}')
        evx, evy = dodge(world, player.x, player.y)
        if boss_fight:
            # Candidate selection already predicts packets; a second repel
            # vector could push us through a wall or out of firing range.
            pass
        else:
            mx, my = unit(mx + evx * 1.10, my + evy * 1.10)
            # Reject a dodge direction that collides with the map; the
            # bot must not spend entire runs pressing into a wall.
            if not world.fits(player.x + mx * 14, player.y + my * 14, player.radius):
                mx, my = nav(world, player.x, player.y, destination, route_cache, step)
        # Avoid holding totally still during an active weapon jam.
        if jammed and mx == 0 and my == 0 and target is not None:
            mx, my = unit(player.y - ty, tx - player.x)
        # The latest engine supports scanning during ransomware weapon suppression.
        scanning = bool((restoration_goal is not None and player.scan >= sim.SCAN_COST
                         and math.hypot(player.x-restoration_goal[0], player.y-restoration_goal[1]) < 25) or
                        (player.scan >= 75 and
                        ((target and aim_d < 170) or
                         (jammed and bool(enemies)) or
                         (world.level == len(sim.PROCESSES) and world.system < 65))))
        before_restored = world.restoration_cleaned
        old_module = world.repair_module
        fire_events = sum(1 for e in world.events if e and e[0] == "fire")
        old_fire_cd = player.fire_cd
        tracked_boss = target if boss_fight else None
        session.step(1 / FPS, sim.Input(dx=mx, dy=my, aim_x=tx, aim_y=ty,
                                         fire=firing, scan=scanning))
        if boss_fight and metrics is not None:
            new_fire_events = sum(1 for e in world.events if e and e[0] == "fire")
            # Event log can roll over at 64 events, so detect a cooldown
            # reset as a fallback for actual firing confirmation.
            fired = (new_fire_events > fire_events or
                     (firing and old_fire_cd <= 1/FPS + 0.001 and
                      player.fire_cd > sim.FIRE_GAP - 1/FPS - 0.001))
            metrics.update(world, tracked_boss, firing, jammed, line, aim_d < 355,
                           fired)
            if boss_log and world.time - metrics.last_report >= 2:
                metrics.last_report = world.time
                hp = tracked_boss.hp if tracked_boss.alive else 0
                print(f'BOSS_TICK t={world.time:.1f}s boss_hp={hp}/{tracked_boss.max_hp} '
                      f'player_hp={player.hp} SYS={world.system:.1f} '
                      + metrics.summary(world))
        if world.restoration_cleaned > before_restored:
            restored_cells += world.restoration_cleaned - before_restored
            if world.restoration_remaining() == 0:
                print(f'RESTORED stage={session.level} cells={world.restoration_cleaned} '
                      f'bonus={world.restoration_bonus()[0]}')
        if old_module is not None and world.repair_module is None:
            repairs_collected += 1
            print(f'REPAIR stage={session.level} hp={world.player.hp}')
        if verbose and step % (FPS * (2 if world.level == len(sim.PROCESSES) else 10)) == 0:
            boss_hp = next((e.hp for e in world.enemies if e.alive and e.kind == 'boss'), 0)
            print(f'progress stage={session.level} t={session.play_time:.1f} '
                  f'hp={world.player.hp} enemies={len(enemies)} '
                  f'jam={jammed} module={module is not None} SYS={world.system:.1f} '
                  f'boss_hp={boss_hp} firing={firing} distance={aim_d:.0f}')
    if metrics is not None and session.mode == 'win':
        print('BOSS_SUMMARY', metrics.summary(session.world))
    print(f'END mode={session.mode} stage={session.level} seed={seed} '
          f'score={session.score} retries={retries} time={session.play_time:.1f}s '
          f'integrity={session.integrity} repairs={repairs_collected} restored_cells={restored_cells} '
          f'peak_worms={max_worms} jam_seconds_sampled={jams}')
    return session.mode == 'win'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('legacy_seed', type=int, nargs='?', help='Optional original positional seed')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--seconds', type=int, help='Limit the simulated run duration')
    parser.add_argument('--max-retries', type=int, default=5)
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--boss-log', action='store_true', help='Show boss HP, SYS and combat-efficiency updates every 2 seconds')
    parser.add_argument('--restore', action='store_true', help='Optionally restore all residual corruption after each stage')
    args = parser.parse_args()
    seed = args.legacy_seed if args.legacy_seed is not None else args.seed
    completed = drive(seed, args.seconds * FPS if args.seconds else 60000,
                      args.max_retries, args.verbose, args.boss_log, args.restore)
    sys.exit(0 if completed or args.seconds else 1)
