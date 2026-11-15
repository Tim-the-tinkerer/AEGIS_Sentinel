"""Regression checks for AEGIS Sentinel's full-body collision handling."""
import unittest
import sim

class CollisionFixTest(unittest.TestCase):
    def setUp(self):
        self.w = sim.World(arena=True)
        self.w.enemies.clear()

    def test_corruption_cannot_harden_over_player_edge(self):
        w = self.w
        x, y = sim.cell_center(5, 5)
        w.player.x = 6 * sim.CELL + 2
        w.player.y = y
        self.assertEqual(w.player_cell(), (6,5))
        self.assertTrue(w._occupied(5,5))
        w.player.x = 7 * sim.CELL + 20
        self.assertFalse(w._occupied(5,5))

    def test_corruption_cannot_harden_over_enemy_edge(self):
        w = self.w
        enemy = w.spawn('worm', 6*sim.CELL + 3, 5*sim.CELL + 20)
        self.assertIsNotNone(enemy)
        self.assertTrue(w._occupied(5,5))

    def test_thin_sight_ray_is_not_full_body_clearance(self):
        w = self.w
        w._fill(5,5,sim.CORRUPT)
        # Ray passes just below the tile; a Sentinel-sized body cannot.
        self.assertTrue(w._sees(4*sim.CELL+20, 6*sim.CELL+2, 6*sim.CELL+20, 6*sim.CELL+2))
        self.assertFalse(w._body_clear_line(4*sim.CELL+20, 6*sim.CELL+2,
                                            6*sim.CELL+20, 6*sim.CELL+2, 12))

    def test_collision_does_not_allow_phasing(self):
        w = self.w
        w._fill(5,5,sim.CORRUPT)
        w.player.x, w.player.y = sim.cell_center(4,5)
        for _ in range(30):
            w._slide(w.player, 200, 0, 1/30, 200)
            self.assertTrue(w.fits(w.player.x, w.player.y, w.player.radius))
        self.assertLess(w.player.x, 5*sim.CELL)

if __name__ == '__main__': unittest.main()
