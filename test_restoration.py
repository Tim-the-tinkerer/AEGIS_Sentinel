"""Optional post-combat restoration regression tests."""
import unittest
import sim


class RestorationTest(unittest.TestCase):
    def secure_with_damage(self, kind=sim.CORRUPT, cells=2):
        w = sim.World(4, 2, arena=True)
        w.enemies = []
        spots = [(4+i,3) for i in range(cells)]
        for c,r in spots:
            w._fill(c,r,kind)
            if kind == sim.LATENT:
                w.latents.append((c,r,0.01))
        w._secure()
        return w, spots

    def test_clear_can_exit_without_restoration(self):
        w, _ = self.secure_with_damage()
        self.assertTrue(w.exit_open)
        self.assertEqual(w.restoration_bonus(), (0,0))
        w.player.x, w.player.y = w.exit_x, w.exit_y
        w._check_exit()
        self.assertEqual(w.result, 'clear')
        self.assertEqual(w.restoration_remaining(), 2)

    def test_scan_restores_hardened_and_latent(self):
        for kind in (sim.CORRUPT, sim.LATENT):
            w, cells = self.secure_with_damage(kind)
            for c,r in cells:
                w.player.x, w.player.y = sim.cell_center(c-1,r)
                w.player.scan=100
                w.player.scan_cd=0
                w._act(sim.Input(scan=True))
                self.assertEqual(w.tile[r][c], sim.OPEN)
                self.assertFalse(w.solid[r][c])
            self.assertEqual(w.restoration_remaining(), 0)
            self.assertEqual(w.restoration_bonus(), (800,5))

    def test_no_spread_after_secure(self):
        w, spots = self.secure_with_damage(sim.LATENT)
        count = w.restoration_remaining()
        for _ in range(250):
            w._memory(1/30)
        self.assertEqual(w.restoration_remaining(), count)
        self.assertTrue(all(w.tile[r][c] == sim.LATENT for c,r in spots))

    def test_partial_and_full_rewards(self):
        w, _ = self.secure_with_damage(cells=4)
        self.assertEqual(w.restoration_bonus(), (0,0))
        w._clear_cell(4,3)
        self.assertEqual(w.restoration_bonus(), (0,0))
        w._clear_cell(5,3)
        self.assertEqual(w.restoration_bonus(), (300,0))
        w._clear_cell(6,3)
        w._clear_cell(7,3)
        self.assertEqual(w.restoration_bonus(), (800,5))

    def test_clean_sector_gets_no_free_reward(self):
        w = sim.World(4,2,arena=True)
        w.enemies=[]
        w._secure()
        self.assertTrue(w.exit_open)
        self.assertEqual(w.restoration_total, 0)
        self.assertEqual(w.restoration_bonus(), (0,0))

    def test_threats_prevent_secured_phase(self):
        w, _ = self.secure_with_damage()
        w.secured = False
        w.exit_open = False
        w.spawn('worm', *sim.cell_center(15,12))
        w._secure()
        self.assertFalse(w.secured)
        self.assertFalse(w.exit_open)

if __name__ == '__main__':
    unittest.main()
