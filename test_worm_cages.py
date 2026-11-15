"""Protect live worms from sealing themselves inside permanent corruption."""
import unittest
import sim


class WormCageTests(unittest.TestCase):
    def setUp(self):
        self.w = sim.World(arena=True)
        self.w.arena = False
        self.w.enemies.clear()
        self.w.player.x, self.w.player.y = sim.cell_center(12, 10)
        self.w.exit_cell = (14, 10)
        self.w.exit_x, self.w.exit_y = sim.cell_center(*self.w.exit_cell)
        self.worm = self.w.spawn('worm', *sim.cell_center(8, 10))
        self.assertIsNotNone(self.worm)

    def test_last_two_escapes_cannot_harden(self):
        w = self.w
        w._fill(7, 10, sim.CORRUPT)
        w._fill(8, 9, sim.CORRUPT)
        # Only the right and lower neighbors remain open.
        self.assertEqual(w._worm_egress(self.worm), 2)
        self.assertTrue(w._would_strand(9, 10))
        self.assertTrue(w._would_strand(8, 11))
        self.assertEqual(w._worm_egress(self.worm), 2)

    def test_latent_cannot_harden_into_cage(self):
        w = self.w
        w._fill(7, 10, sim.CORRUPT)
        w._fill(8, 9, sim.CORRUPT)
        w.tile[10][9] = sim.LATENT
        w.latents = [(9, 10, 0.01)]
        w._memory(0.1)
        self.assertEqual(w.tile[10][9], sim.LATENT)
        self.assertFalse(w.solid[10][9])

    def test_non_worm_tiles_can_harden_normally(self):
        w = self.w
        self.assertFalse(w._would_cage_worm(20, 20))

if __name__ == '__main__':
    unittest.main()
