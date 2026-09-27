import unittest
from stat_colors import placement_color

class StatColorTest(unittest.TestCase):
    def test_dataj_gradient_endpoints(self):
        self.assertEqual(placement_color(3.81),'rgb(191,254,127)')
        self.assertEqual(placement_color(4.83),'rgb(255,90,100)')
        self.assertEqual(placement_color(4.5),'rgb(255,189,121)')

if __name__=='__main__':unittest.main()
