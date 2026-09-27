import unittest
from core import Session, resolve_name, parse_comp_url


class CoreTests(unittest.TestCase):
    def test_late_responses_and_new_game(self):
        s = Session()
        a = s.token()
        s.set_choices('2-1', ['1', '2', '3'])
        self.assertFalse(s.accepts(a))
        b = s.token()
        s.set_target('112')
        self.assertFalse(s.accepts(b))
        c = s.token()
        s.reset()
        self.assertFalse(s.accepts(c))
        self.assertIsNone(s.target)

    def test_invalidate_then_identical_candidates(self):
        s = Session()
        s.set_choices('2-1', ['1', '2', '3'])
        old = s.token()
        s.invalidate()
        s.set_choices('2-1', ['1', '2', '3'])
        self.assertFalse(s.accepts(old))

    def test_ambiguous_name_not_resolved_by_statistics(self):
        rows = [{'id':'1','name':'兽性本能','level':2}, {'id':'2','name':'兽性本能','level':2}]
        self.assertEqual(resolve_name(['兽性本能']*3, rows)['status'], 'ambiguous')

    def test_roman_consensus_never_substitutes_characters(self):
        rows = [{'id':'1','name':'护甲 I'}, {'id':'2','name':'护甲 II'}]
        self.assertEqual(resolve_name(['护甲1']*3, rows)['status'], 'unrecognized')
        self.assertEqual(resolve_name(['护甲1','护甲Ⅰ','护甲 I'], rows)['id'], '1')
        self.assertEqual(resolve_name(['护甲 I','护甲 II','护甲 I'], rows)['status'], 'conflict')
        self.assertEqual(resolve_name(['护甲1','护甲 I'], rows)['status'], 'unrecognized')

    def test_comp_url_host_and_path(self):
        self.assertEqual(parse_comp_url('https://www.dataj.cc/comp/112'), '112')
        for url in ['https://www.dataj.cc.evil.test/comp/112','file:///comp/112','https://evil.test/comp/112','https://www.dataj.cc/comp/112/extra']:
            with self.assertRaises(ValueError): parse_comp_url(url)


if __name__ == '__main__':
    unittest.main()
