import json
from copy import deepcopy
from pathlib import Path
import unittest

from hex_family import FamilyNameResolver, resolve_family_name


# Frozen independent set-18 source, canonical catalog SHA256
# 6554f11c481fc39904f42b7e24a1461f7a51d05e8f63a774bca427467b12ce46.
# (literal complete base, real ID, original name, source level, original icon).
FROZEN_ROWS = (('值得等待', '20021', '值得等待', 2, 'https://img.dataj.cc/images/hex/worththewait2.png'),
 ('值得等待', '30021', '值得等待 II', 3, 'https://img.dataj.cc/images/hex/worththewait3.png'),
 ('嘀个痛快!', '1134', '嘀个痛快！ I', 1, 'https://img.dataj.cc/images/hex/rollingfordays1.png'),
 ('好事成双', '2133', '好事成双 II', 2, 'https://img.dataj.cc/images/hex/doubletrouble2.png'),
 ('并肩作战', '1019', '并肩作战 I', 1, 'https://img.dataj.cc/images/hex/standunited1.png'),
 ('应急护甲', '1023', '应急护甲 I', 1, 'https://img.dataj.cc/images/hex/makeshift1.png'),
 ('应急护甲', '2023', '应急护甲 II', 2, 'https://img.dataj.cc/images/hex/makeshift2.png'),
 ('投资策略', '20217', '投资策略 I', 2, 'https://img.dataj.cc/images/hex/investmentstrategy2.png'),
 ('投资策略', '30217', '投资策略 II', 3, 'https://img.dataj.cc/images/hex/investmentstrategy3.png'),
 ('拥抱', '10615', '拥抱 I', 1, 'https://img.dataj.cc/images/hex/grouphugi1.png'),
 ('拥抱', '10616', '拥抱 II', 2, 'https://img.dataj.cc/images/hex/grouphugii2.png'),
 ('星界赐福', '2022', '星界赐福 II', 2, 'https://img.dataj.cc/images/hex/celestialblessing2.png'),
 ('星界赐福', '3022', '星界赐福 III', 3, 'https://img.dataj.cc/images/hex/celestialblessing3.png'),
 ('有用之材', '1789', '有用之材 I', 1, 'https://img.dataj.cc/images/hex/goodforsomething1.png'),
 ('治疗法球', '1634', '治疗法球 I', 1, 'https://img.dataj.cc/images/hex/healingorbs1.png'),
 ('治疗法球', '2634', '治疗法球 II', 2, 'https://img.dataj.cc/images/hex/healingorbs2.png'),
 ('潘朵拉的装备', '1007', '潘朵拉的装备 I', 1, 'https://img.dataj.cc/images/hex/pandora1.png'),
 ('潘朵拉的装备', '2007', '潘朵拉的装备 II', 2, 'https://img.dataj.cc/images/hex/pandora2.png'),
 ('潘朵拉的装备', '3007', '潘朵拉的装备 III', 3, 'https://img.dataj.cc/images/hex/pandora3.png'),
 ('玻璃大炮', '10253', '玻璃大炮 I', 1, 'https://img.dataj.cc/images/hex/glasscannon1.png'),
 ('玻璃大炮', '20253', '玻璃大炮 II', 2, 'https://img.dataj.cc/images/hex/glasscannon2.png'),
 ('珍藏财宝', '3486', '珍藏财宝III', 3, 'https://img.dataj.cc/images/hex/buriedtreasureslegend3.png'),
 ('珠光莲花', '2128', '珠光莲花 I', 2, 'https://img.dataj.cc/images/hex/jeweledlotus2.png'),
 ('珠光莲花', '3128', '珠光莲花 II', 3, 'https://img.dataj.cc/images/hex/jeweledlotus3.png'),
 ('电火花', '10708', '电火花 I', 1, 'https://img.dataj.cc/images/hex/electrocharging1.png'),
 ('电火花', '20708', '电火花 II', 2, 'https://img.dataj.cc/images/hex/electrocharging2.png'),
 ('纵深', '10750', '纵深 I', 1, 'https://img.dataj.cc/images/hex/verticality1.png'),
 ('纵深', '20750', '纵深 II', 2, 'https://img.dataj.cc/images/hex/verticality2.png'),
 ('纵深', '30750', '纵深 III', 3, 'https://img.dataj.cc/images/hex/verticality3.png'),
 ('终身黄铜', '10242', '终身黄铜 I', 2, 'https://img.dataj.cc/images/hex/bronzeforlifei2.png'),
 ('终身黄铜', '20242', '终身黄铜 II', 3, 'https://img.dataj.cc/images/hex/bronzeforlifei3.png'),
 ('装备百宝袋', '1006', '装备百宝袋 I', 1, 'https://img.dataj.cc/images/hex/itemgrabbag1.png'),
 ('资本利得', '10755', '资本利得 I', 1, 'https://img.dataj.cc/images/hex/capitalgains1.png'),
 ('资本利得', '20755', '资本利得 II', 2, 'https://img.dataj.cc/images/hex/capitalgains2.png'))


class HexFamilyTests(unittest.TestCase):
    def hug_catalog(self):
        path = Path(__file__).with_name('fixtures') / 'hex-hug-i-title-context-20261020.json'
        return json.loads(path.read_text(encoding='utf-8'))['catalog']

    def test_two_complete_hug_prefixes_and_silver_recover_reviewed_i(self):
        result = resolve_family_name(['拥抱', '拥抱1'], self.hug_catalog(), 1)
        self.assertIsNotNone(result)
        self.assertEqual(result['status'], 'resolved')
        self.assertEqual(result['id'], '10615')

    def test_arabic_two_three_tail_is_noise_and_never_supplies_quality(self):
        for level,identity in ((1,'10615'),(2,'10616')):
            with self.subTest(level=level):
                result=resolve_family_name(['拥抱2','拥抱3'],self.hug_catalog(),level)
                self.assertIsNotNone(result)
                self.assertEqual(result['id'],identity)


    def catalog(self):
        return [dict(id=identity, name=name, level=level, icon=icon, setId='18')
                for base, identity, name, level, icon in FROZEN_ROWS]

    def test_all_34_reviewed_members_resolve_from_complete_base_and_true_quality(self):
        self.assertEqual(len(FROZEN_ROWS), 34)
        for base, identity, name, quality, icon in FROZEN_ROWS:
            with self.subTest(identity=identity, name=name):
                result = resolve_family_name([base + '1', base + 'l'], self.catalog(), quality)
                self.assertIsNotNone(result)
                self.assertEqual(result['status'], 'resolved')
                self.assertEqual(result['id'], identity)
                self.assertEqual(result['name'], name)

    def test_complete_catalog_title_inconsistent_with_quality_vetoes(self):
        for readings, quality in [(['拥抱 II', '拥抱1', '拥抱l'], 1),
                                  (['值得等待', '值得等待1', '值得等待l'], 3)]:
            with self.subTest(readings=readings):
                result = resolve_family_name(readings, self.catalog(), quality)
                self.assertEqual(result['status'], 'conflict')
                self.assertNotIn('id', result)

    def test_conflicting_complete_titles_and_other_identity_cannot_be_outvoted(self):
        for readings in [(['拥抱 I', '拥抱 II', '拥抱1', '拥抱l']),
                         (['拥抱1', '拥抱l', '应急护甲 I'])]:
            with self.subTest(readings=readings):
                result = resolve_family_name(readings, self.catalog(), 1)
                self.assertEqual(result['status'], 'conflict')
                self.assertNotIn('id', result)

    def test_two_different_complete_family_bases_conflict(self):
        result = resolve_family_name(['拥抱1', '拥抱l', '应急护甲1', '应急护甲l'], self.catalog(), 1)
        self.assertEqual(result['status'], 'conflict')
        self.assertNotIn('id', result)

    def test_unknown_quality_and_non_integer_quality_do_not_authorize_identity(self):
        for quality in (None, 0, 4, True, False, 1.0, '1'):
            with self.subTest(quality=quality):
                self.assertIsNone(resolve_family_name(['拥抱', '拥抱1'], self.catalog(), quality))
        self.assertIsNone(resolve_family_name(['拥抱', '拥抱1'], self.catalog(), 3))

    def test_one_complete_base_or_wrong_chinese_is_not_enough(self):
        for readings in (['拥抱'], ['拥抱', ''], ['拥抱', '拥'], ['拥抱', '拥炮'],
                         ['拥炮', '拥炮'], ['拥抱额外', '拥抱额外'],
                         ['拥', '拥1'], ['星界喝福', '星界喝福1'],
                         ['拥抱+', '拥抱++'], ['嘀个痛快1', '嘀个痛快l']):
            with self.subTest(readings=readings):
                self.assertIsNone(resolve_family_name(readings, self.catalog(), 1))

    def test_normalization_keeps_punctuation_and_gold_i_uses_source_level(self):
        self.assertEqual(resolve_family_name(['拥 抱 Ⅰ', '拥抱I'], self.catalog(), 1)['id'], '10615')
        self.assertEqual(resolve_family_name(['嘀个痛快！！', '嘀个痛快！1'], self.catalog(), 1)['id'], '1134')
        for base, identity in [('投资策略', '20217'), ('珠光莲花', '2128'), ('终身黄铜', '10242')]:
            with self.subTest(base=base):
                self.assertEqual(resolve_family_name([base + '1', base + 'l'], self.catalog(), 2)['id'], identity)
                self.assertIsNone(resolve_family_name([base + '1', base + 'l'], self.catalog(), 1))

    def test_family_catalog_drift_or_partial_family_disables_completion(self):
        for field, value in [('id', 'other'), ('name', '拥抱 III'), ('level', None),
                             ('level', True), ('level', '1'), ('setId', '17'),
                             ('setId', None), ('icon', 'https://example.com/new.png'),
                             ('catalog_alias_ids', ['10615', 'other'])]:
            with self.subTest(field=field, value=value):
                catalog = self.catalog()
                next(row for row in catalog if row['id'] == '10615')[field] = value
                self.assertIsNone(resolve_family_name(['拥抱', '拥抱1'], catalog, 1))
        catalog = [row for row in self.catalog() if row['id'] != '10616']
        self.assertIsNone(resolve_family_name(['拥抱', '拥抱1'], catalog, 1))

    def test_duplicate_extra_plus_and_unknown_quality_family_rows_cannot_be_filtered_away(self):
        hug = next(row for row in self.catalog() if row['id'] == '10615')
        for extra in [deepcopy(hug), {**hug, 'id': '999'}, {**hug, 'id': '999', 'level': None},
                      {**hug, 'level': None}, {**hug, 'id': '999', 'name': '拥抱+'},
                      {**hug, 'id': '999', 'name': '拥抱 IV'}]:
            with self.subTest(extra=extra):
                self.assertIsNone(resolve_family_name(['拥抱', '拥抱1'], self.catalog() + [extra], 1))

    def test_unreviewed_and_plus_mixed_families_are_not_new_identity_routes(self):
        cases = [('护甲', [{'id': '1', 'name': '护甲 I', 'level': 1}]),
                 ('弈子配送', [{'id': '10751', 'name': '弈子配送', 'level': 1},
                            {'id': '10752', 'name': '弈子配送+', 'level': 1}]),
                 ('秘法帮派', [{'id': '3068', 'name': '秘法帮派 II', 'level': 3},
                            {'id': '30679', 'name': '秘法帮派 II++', 'level': 3}])]
        for base, extra in cases:
            with self.subTest(base=base):
                catalog = [{**row, 'setId': '18', 'icon': 'https://example.com/icon.png'} for row in extra]
                self.assertIsNone(resolve_family_name([base, base + '1'], catalog, 1))
                self.assertIsNone(resolve_family_name([base, base + '1'], catalog, 3))

    def test_malformed_catalog_does_not_raise_or_discard_an_unknown_row(self):
        for catalog in (None, {}, [None], self.catalog() + [{}],
                        self.catalog() + [{'name': None}], self.catalog() + [{'name': 12}]):
            with self.subTest(catalog=catalog):
                self.assertIsNone(resolve_family_name(['拥抱', '拥抱1'], catalog, 1))

    def test_observed_only_reads_never_add_prefix_votes(self):
        self.assertIsNone(resolve_family_name(['拥抱1'], self.catalog(), 1,
                                             observed_readings=['拥抱1', '拥抱l', '拥抱']))

    def test_observed_complete_title_from_duplicate_pixels_still_vetoes(self):
        result = resolve_family_name(['拥抱1', '拥抱l'], self.catalog(), 1,
                                     observed_readings=['拥抱1', '拥抱l', '拥抱 II'])
        self.assertEqual(result['status'], 'conflict')
        self.assertNotIn('id', result)

    def test_real_id_reused_under_another_catalog_name_disables_family(self):
        hug = next(row for row in self.catalog() if row['id'] == '10615')
        catalog = self.catalog() + [{**hug, 'name': '未知新身份'}]
        self.assertIsNone(resolve_family_name(['拥抱', '拥抱1'], catalog, 1))

    def test_all_34_exact_titles_keep_identity_and_wrong_quality_vetoes(self):
        for base, identity, name, quality, icon in FROZEN_ROWS:
            with self.subTest(identity=identity):
                result = resolve_family_name([name, name], self.catalog(), quality)
                self.assertEqual(result['id'], identity)
                wrong_quality = 2 if quality == 1 else 1
                conflict = resolve_family_name([name, name], self.catalog(), wrong_quality)
                self.assertEqual(conflict['status'], 'conflict')
                self.assertNotIn('id', conflict)

    def test_vote_titles_cannot_be_hidden_with_an_empty_observed_list(self):
        result = resolve_family_name(['拥抱 I', '拥抱1'], self.catalog(), 2, observed_readings=[])
        self.assertEqual(result['status'], 'conflict')
        self.assertNotIn('id', result)

    def test_existing_core_contract_still_rejects_prefix_and_suffix_substitution(self):
        from core import resolve_name
        for readings in (['拥抱', '拥抱'], ['拥抱1', '拥抱1'], ['星界喝福', '星界喝福']):
            with self.subTest(readings=readings):
                self.assertNotEqual(resolve_name(readings, self.catalog())['status'], 'resolved')

    def test_frame_snapshot_is_independent_of_later_input_rows_and_nested_alias_changes(self):
        catalog = self.catalog()
        hug = next(row for row in catalog if row['id'] == '10615')
        hug['catalog_alias_ids'] = []
        resolver = FamilyNameResolver(catalog)
        hug['catalog_alias_ids'].append('new-alias')
        hug['icon'] = 'https://example.com/drift.png'
        catalog.append({**hug, 'id': 'new-plus', 'name': '拥抱+'})
        result = resolver.resolve(['拥抱1', '拥抱l'], 1)
        self.assertIsNotNone(result)
        self.assertEqual(result['id'], '10615')
        self.assertIsNone(FamilyNameResolver(catalog).resolve(['拥抱1', '拥抱l'], 1))
        self.assertIsNone(resolve_family_name(['拥抱1', '拥抱l'], catalog, 1))

    def test_returned_candidate_edits_do_not_mutate_frame_snapshot(self):
        catalog = self.catalog()
        resolver = FamilyNameResolver(catalog)
        first = resolver.resolve(['拥抱1', '拥抱l'], 1)
        first['candidates'][0]['name'] = '被外部修改'
        first['candidates'][0]['level'] = 3
        first['candidates'][0]['catalog_alias_ids'] = ['foreign-id']
        catalog.clear()
        second = resolver.resolve(['拥抱1', '拥抱l'], 1)
        self.assertIsNotNone(second)
        self.assertEqual(second['id'], '10615')
        self.assertEqual(second['name'], '拥抱 I')
        self.assertEqual(second['candidates'][0]['level'], 1)

    def test_reused_frame_resolver_checks_each_batch_titles_and_quality_again(self):
        resolver = FamilyNameResolver(self.catalog())
        for base, identity, name, quality, icon in FROZEN_ROWS:
            with self.subTest(identity=identity):
                self.assertEqual(resolver.resolve([base + '1', base + 'l'], quality)['id'], identity)
                conflict = resolver.resolve([base + '1', base + 'l'], quality,
                                            observed_readings=[name, '拥抱 II' if name != '拥抱 II' else '拥抱 I'])
                self.assertEqual(conflict['status'], 'conflict')
                self.assertNotIn('id', conflict)


if __name__ == '__main__':
    unittest.main()
