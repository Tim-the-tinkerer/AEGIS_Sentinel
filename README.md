# AEGIS Sentinel

**AEGIS Sentinel** is a resident antivirus game (`antivirus.py`). You move through a process map drawn as live memory. Packed pages are walls. The open cells are code, and ordinary processes keep moving through them until an infection takes the sector. You scan, quarantine, and purge.

Python 3.9 or newer runs the rules and the tests. The window needs pygame. pygame 2.6 has macOS wheels for Python 3.9 through 3.13 and does not build on 3.14 or 3.15. The launcher picks the newest of those versions and keeps its own environment.

## Run it

On a Mac, double-click `AEGIS Sentinel.command`. The first launch creates the environment and installs pygame. Later launches go straight to the window.

From a terminal, the same launcher is:

```bash
"./AEGIS Sentinel.command"
"./AEGIS Sentinel.command" --seed 1
"./AEGIS Sentinel.command" --level 3 --mute
"./AEGIS Sentinel.command" --fullscreen
```

If pygame is already installed for the `python3` you run:

```bash
python3 antivirus.py
python3 antivirus.py --seed 1
python3 antivirus.py --level 2 --mute
python3 antivirus.py --check
```

| Argument | Meaning |
| --- | --- |
| `--seed N` | Repeats the processes. `N` is an integer from 0 through 2^64 - 1. With no seed, the run picks one and shows it on the title. |
| `--level N` | Starts at that process, from 1 through 9. Integrity starts full. |
| `--mute` | Starts with the sound off. `M` switches it during play. |
| `--fullscreen` | Opens directly in fullscreen. You can still toggle with Control+Enter or Option+Enter. |
| `--check` | Runs the tests. No window. |

`--seed=1` is the same as `--seed 1`. The same is true for `--level`.

## How to play

The run is nine processes, from your own files inward to the kernel:

| # | Process | Path | What is new |
| --- | --- | --- | --- |
| 1 | DOWNLOADS | `~/downloads` | Worms. |
| 2 | BROWSER.CACHE | `~/library/caches` | Trojans, harmless decoy files, and the first access gate. |
| 3 | DOCUMENTS | `~/documents` | Ransomware. |
| 4 | HOME | `~` | Smaller rooms, so the most rooms and halls of any process. |
| 5 | STARTUP | `~/library/launch-agents` | Spyware. |
| 6 | APPLICATIONS | `/applications` | Twice as many walking daemons. |
| 7 | SYSTEM32 | `/system/library` | Two lockers at once. |
| 8 | DRIVERS | `/system/drivers` | Four access gates, and every threat but the boss. |
| 9 | KERNEL | `/kernel` | `POLY.SYS` and the SYS meter. |

Each one is a set of rooms joined by halls. You begin in the first room. `CLEAN.EXIT` is in the last room, and it stays locked until every threat is gone. Step onto it to mount the next process. After all threats are gone, the sector is secured and you may **exit immediately** or remain to restore the damage.

A cleared process repairs 17 integrity, and never past 100. The score banks the purge points, plus 500, plus 5 for each point of integrity you had left. If a secured process contains residual corruption, scanning it clean before exiting awards **+300 score for at least 50% restoration**, or **+800 score and +5 integrity at 100% restoration** (rather than both score awards). This restoration reward is awarded only if corrupted cells were present at the moment the sector was secured. The +5 is applied before the usual 17-point stage recovery; both respect the 100-integrity cap. A halt drops the points from the process you were in. `R` retries that process from the pause menu or the halt screen. A retry rebuilds it from the same seed, and your integrity returns to the value from when you mounted it. There is no extra cost.

| Key | Action |
| --- | --- |
| `W` `A` `S` `D` or arrows | Move |
| Mouse | Aim |
| Click or space | Purge. Hold to keep firing. |
| Shift or `F` or right click | Scan. It spends scan charge. In range, through walls, it names a sleeping trojan without waking it, quarantines *latent* infected memory during combat, and slows whatever it touches. Once enemies are gone, each scan pulse restores one nearby damaged memory cell, including hardened corruption. |
| `Esc` or `P` | Pause (and release the mouse) |
| `Control+Enter` or `Option+Enter` | Toggle fullscreen / windowed mode |
| `M` | All sound on or off |
| `N` | Procedural music on or off (effects remain enabled) |
| `R` | Retry the process, from pause or after a halt |
| `Q` | Quit, from a menu |

The title and the cards say the same keys. `Enter` mounts a process.

**Mouse confinement:** While actively playing, AEGIS Sentinel captures the mouse so it cannot wander onto the desktop or another monitor. On the title screen, process cards, pause menu, and ending screens, the mouse is released. Press `Esc` or `P` to pause and free the pointer. Switching away from AEGIS Sentinel automatically pauses and releases it; return to the game and press `Esc` or `P` to resume. `Control+Enter` switches fullscreen without resetting the campaign; `Option+Enter` also works. The macOS Mission Control F11 shortcut is not used.

## Threats

| Signature | What it does |
| --- | --- |
| `WORM.BIN` | Chases when it can see you, remember you, or hear a call. It infects nearby floor and can spawn multiple generations of copies, within a population limit. The infection is invisible, then it hardens, and a corrupt page can spread to a neighbor. A scan quarantines a cell before it hardens. |
| `TROJAN.COM` | Asleep, drawn as an ordinary filename. A scan exposes it and leaves it asleep, including through a wall. A purge can hit it while it sleeps. Walk on top of it and it wakes. Some filenames on the floor are only files, and the walking daemons sometimes stop, so a still filename is not proof. A scan marks a plain file clean. |
| `SPY.DLL` | Keeps its distance, fires corrupt packets, and, while it can see you, tells the other processes where you are. |
| `LOCK.EXE` | Draws an amber ring and locks the doors of the room it is in. Leave the ring before it closes. The room opens again. Three purges. |
| `POLY.SYS` | The kernel only. It chases, splits off worms, and sprays packets. As it loses HP it moves faster, chases in shorter bursts, and its spray widens. While it lives, the SYS meter falls. At 0 the run halts even if your integrity is left. |

Packets travel the halls, and a couple of background processes walk a loop in a room. From the browser cache on, a few hall cells are access gates. They shut, then open, and they are never the only way through. A corrupt page, a seal, or a shut gate stops that traffic. Gates are steel. Seals are amber. Corrupt pages are the lasting damage, and the floor beside them darkens.

A worm, an awake trojan, or ransomware comes for you when it can see you, when it remembers where it saw you, or when spyware or the kernel has called it in. Otherwise a worm keeps infecting where it stands, and ransomware holds its room. They path through the halls. A corrupt page or a seal sends them around it.

On the kernel the dock shows SYS. It falls about 1.6 a second while `POLY.SYS` is alive, so you have roughly a minute, and it falls further when memory hardens. A scan that quarantines infection gives a little of it back.

The map in the corner shows packed pages, corrupt pages, amber seals, steel gates, the exit, threats that are awake, and a trojan after a scan has exposed it. A trojan that still looks like a file is not on that map.

## Memory Repair Modules

Some ransomware-infested processes contain a **Memory Repair Module**: a glowing teal hexagonal node marked `+25`. Only rooms initially guarded by `LOCK.EXE` are eligible. A module has roughly a 45% chance to appear in each eligible process, so modules are uncommon across a full run. Placement is reproducible for a given seed and stage.

Walking over a module restores up to **25 integrity points** (maximum 100). If integrity is already full, the module stays on the floor until you need it. The module does not activate or end a ransomware lockdown: `LOCK.EXE` follows its existing behavior, possibly sealing the room and temporarily disabling the purge emitter. Scanning and movement remain available during a lockdown; the seals expire normally. The module is never a required objective, and the existing **17-point** recovery after clearing a stage is unchanged.

## Sound and procedural soundtrack

The AEGIS Sentinel replaces the simple triangle: a small hovering security construct with four rotating armor vanes, a hexagonal processor, an illuminated core, animated perimeter arcs, and a forward-facing purge emitter. It is rendered directly with pygame shapes; there are no external art assets or changes to its collision box.

Each of the nine process regions has its own reproducible two-bar electronic score. The procedural composer derives a minor-mode drone, pulsed bass, intermittent melodic pings, and code-like high-frequency percussion from the run seed and stage. As nearby enemies close in or integrity falls, an additional rhythmic threat layer becomes louder. Music loops and remains quiet enough to leave room for combat effects. The same seed and level produce the same musical structure. No audio files or Internet connection are required.

`N` toggles music only; `M` toggles all sound, including effects. `--mute` begins with everything silent. On pause and menus the score is silent. If the audio device cannot open, the game plays without sound.


## Errors

`--help` and `-h` print the module docstring and exit 0.

Argument errors exit 2. The line starts with `antivirus.py:`.

A missing pygame install exits 1 and names `AEGIS Sentinel.command`.

Ctrl-C exits 130.

## Tests

```bash
python3 test_antivirus.py
```

`python3 antivirus.py --check` runs that same file. The tests do not open a window. They build every process for several seeds, then purge, scan, and clear an open arena where the positions are known.

## Tuning

The balance numbers sit at the top of `sim.py`. The ones most worth adjusting:

| Constant | Effect |
| --- | --- |
| `SYSTEM_DRAIN` | SYS lost per second while `POLY.SYS` lives. |
| `BOSS_RAGE_SPEED`, `BOSS_RAGE_CHASE` | How much faster, and how much shorter its chases, the kernel boss gets near death. |
| `PROCESSES` | One entry per stage: the threat counts, room count, and the `gates`, `decoys`, `daemons`, and `compact` fields. Add, remove, or reorder entries to change the run. The last entry is always the kernel. |
| `DAEMON_REST` | Chance a walking daemon stops for a few seconds at each step. |
| `BOLT_WALL` | How thick a purge bolt is against walls. Enemies are still hit at its full size. |

## Difficulty revision — aggressive infection

- More enemies populate each of the nine processes. The first stage starts with eight worms instead of five.
- Worms spread to opposite flanks when they have a clear path to the Sentinel, rather than exclusively forming a single shooting line.
- Worms can replicate repeatedly, and their descendants can replicate too. A per-worm offspring limit and global worm/hostile caps prevent runaway spawning. Killing worms early helps contain an outbreak.
- Ransomware room seals jam the **purge weapon** while the Sentinel is within the sealed room. Scanning, movement, and evasive play remain available until the seal expires. An on-screen **PURGE JAMMED** warning appears.
- Inter-stage integrity repair is reduced from 25 to 17 points.
- All nine processes, procedural music, fullscreen control, and mouse capture are retained.

### Automated playbot and Kernel diagnostics

Run `python3 playbot.py --seed 1 --verbose` to test the real simulation without
running the graphical game. The bot uses omniscient simulation positions, so it
is **not** representative of human difficulty. It prioritizes POLY.SYS in the
Kernel, strafes while firing, and reports `cause=SYS` or `cause=INTEGRITY`,
remaining SYS, and the boss's HP upon a failed attempt. The Kernel is deliberately
challenging and a particular seed may still defeat the bot.

Defeating POLY.SYS now stops *all* SYS integrity loss, including damage from
previously planted corruption that matures afterward. Other enemies can remain
alive and must still be defeated before exiting.


### Headless playbot diagnostics

Run the automated simulation player from the game folder:

```sh
python3 playbot.py --seed 1 --boss-log
```

`--boss-log` prints a Kernel combat report every two simulated seconds,
including boss health, SYS, firing opportunity, line-of-sight percentage,
weapon-jammed seconds, shots fired and measured boss damage. The `BOSS_SUMMARY`
line is printed after each failed Kernel attempt and on victory. The bot uses
perfect enemy position information and is **not** a human difficulty benchmark.
Its controller never adjusts enemy health, SYS or the session's progression.
Use `--max-retries 0` for a one-attempt run or `--seconds 60` for a short test.

## Optional memory restoration

After eliminating the last malicious process, **CLEAN.EXIT opens immediately**. You can leave with no penalty, or stay to repair residual corrupted memory using the same scan control (`Shift`, `F`, or right click). Scans consume charge and regenerate normally. A scan repairs one nearby latent or hardened cell and removes that obstacle from the map. Damaged cells pulse in the world and show on the minimap; the HUD tracks `RESTORE repaired/total`. Once secured, corruption stops spreading and latent cells no longer harden, so there is no rush. Ransomware's temporary locks expire normally.

Restoration has a modest reward: 50–99% = **+300 score**; 100% = **+800 score and +5 integrity**. Existing between-stage recovery remains +17; Memory Repair Modules still restore +25 when collected. No restoration reward is added when a stage has no residual corruption. The Kernel's SYS meter does not drain after POLY.SYS is defeated.

The procedural soundtrack settles as damage is repaired: its tension layer reduces as the percentage of un-restored corruption decreases, leaving the ambient layer.

## Automated playbot

The included `playbot.py` retains its usual fast clear-and-exit policy by default:

```bash
python3 playbot.py --seed 1
```

To have it perform optional restoration after **every** secured stage:

```bash
python3 playbot.py --seed 1 --restore
```

It reports `RESTORED` for each fully restored stage and summarizes `restored_cells` at the end. Its combat and boss-fight diagnostics continue to work, including `--boss-log`. Repair-module collection and memory restoration are independent mechanics.

### Corner and corruption collision improvement

Movement now takes the Sentinel's and enemies' full collision radius into account
when checking short paths around obstacles. Tight corners allow a small change
of heading instead of always stopping a diagonal move. Dynamic corruption and
gates will not solidify on the edge of an occupied character. These adjustments
do not change enemy damage, counts, replication, or the Kernel difficulty.
