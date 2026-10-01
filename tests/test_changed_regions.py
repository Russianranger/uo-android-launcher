from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import client_presentation


class ChangedRegionOptionsTests(unittest.TestCase):
    def test_default_and_comparison_choices_survive_standard_display(self):
        for request, expected in (({}, True), ({'dirty_regions': False}, False), ({'dirty_regions': True}, True)):
            result = client_presentation.start(SimpleNamespace(request=request))
            self.assertEqual(result['presentation_active'], 'rfb')
            self.assertIs(result['dirty_regions_requested'], expected)

    def test_non_boolean_region_options_are_rejected(self):
        for value in (0, 1, None, 'false', [], {}):
            with self.assertRaisesRegex(ValueError, 'changed-region'):
                client_presentation.start(SimpleNamespace(request={'dirty_regions': value}))


if __name__ == '__main__':
    unittest.main()
