"""Frozen S18 catalog cases, checked against the saved DataJ mapping script.

Source: work/s18-refresh-20260926/catalog.json, SHA-256
0338c0734fc0faec4cbd8d34bc1ffed1d77fae49169855536b4630097730d9c2.
Only identity-relevant fields are copied; this suite needs no private fixtures.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from dataj import DataJ
from entity_identity import EntityResolver, display_label


CATALOG = {
    'hero': [
        {'id': '14503', 'name': '阿木木', 'tag': None, 'heroType': 0, 'price': 4, 'setId': '18'},
        {'id': '24503', 'name': '阿木木', 'tag': None, 'heroType': 0, 'price': 4, 'setId': '18'},
        {'id': '34503', 'name': '阿木木', 'tag': None, 'heroType': 0, 'price': 4, 'setId': '18'},
        {'id': '44503', 'name': '阿木木', 'tag': None, 'heroType': 0, 'price': 4, 'setId': '18'},
        {'id': '11506', 'name': '阿卡丽', 'tag': 'AD', 'heroType': 0, 'price': 1, 'setId': '18'},
        {'id': '21506', 'name': '阿卡丽', 'tag': 'AD', 'heroType': 0, 'price': 1, 'setId': '18'},
        {'id': '31506', 'name': '阿卡丽', 'tag': 'AD', 'heroType': 0, 'price': 1, 'setId': '18'},
        {'id': '41506', 'name': '阿卡丽', 'tag': 'AD', 'heroType': 0, 'price': 1, 'setId': '18'},
        {'id': '11513', 'name': '阿卡丽', 'tag': 'AP', 'heroType': 0, 'price': 1, 'setId': '18'},
        {'id': '21513', 'name': '阿卡丽', 'tag': 'AP', 'heroType': 0, 'price': 1, 'setId': '18'},
        {'id': '31513', 'name': '阿卡丽', 'tag': 'AP', 'heroType': 0, 'price': 1, 'setId': '18'},
        {'id': '41513', 'name': '阿卡丽', 'tag': 'AP', 'heroType': 0, 'price': 1, 'setId': '18'},
    ],
    'hex': [
        {'id': '1023', 'name': '应急护甲 I', 'level': 1, 'descText': '没有携带任何装备的弈子们获得30护甲和魔法抗性。', 'setId': '18'},
        {'id': '2023', 'name': '应急护甲 II', 'level': 2, 'descText': '没有携带任何装备的弈子们获得50护甲和魔法抗性。', 'setId': '18'},
        {'id': '1008', 'name': '打捞桶', 'level': 2, 'descText': '立刻获得1件随机成装，并在8个玩家对战回合之后提供1个基础装备。出售弈子会将其携带的成装拆分成基础装备(冠冕系装备和纹章除外)。', 'setId': '18'},
        {'id': '2008', 'name': '打捞桶+', 'level': 2, 'descText': '立刻获得1件随机成装，并在4个玩家对战回合之后提供1个基础装备。出售弈子会将其携带的成装拆分成基础装备(冠冕系装备和纹章除外)。', 'setId': '18'},
        {'id': '2705', 'name': '成吨的属性！', 'level': 2, 'descText': '你的弈子们获得44生命值、4%物理加成、4%法术加成、4护甲、4魔抗、4%攻击速度和4法力值。', 'setId': '18'},
        {'id': '3705', 'name': '成吨的属性！', 'level': 3, 'descText': '你的弈子们获得88生命值、8%物理加成、8%法术加成、8护甲、8魔抗、8%攻击速度和8法力值。', 'setId': '18'},
        {'id': '1625', 'name': '别再错过', 'level': 1, 'descText': '获得每个1费弈子各1个。', 'setId': '18'},
        {'id': '10784', 'name': '别再错过', 'level': 1, 'descText': '获得每个1费弈子各1个。', 'setId': '18'},
        {'id': '20764', 'name': '兽性本能', 'level': 2, 'descText': '【野兽之灵】额外提供一种【兽灵赐福】。立刻获得1个【蔚】，在3个回合后，获得1个【奈德丽】。  灵龟：每4秒，你的队伍治疗其4最大生命值。蛮熊：【野兽之灵】的伤害会处决生命值低于12的敌人。猛虎：在6秒后，【野兽之灵】弈子们获得35攻击速度，你的队伍获得15攻击速度。凤凰：【野兽之灵】每参与15次击杀，获得1件基础装备。至多获得4件。  参与击杀数：0', 'setId': '18'},
        {'id': '30764', 'name': '兽性本能', 'level': 2, 'descText': '【野兽之灵】额外提供一种【兽灵赐福】。立刻获得1个【蔚】，在3个回合后，获得1个【希维尔】。  灵龟：每4秒，你的队伍治疗其4最大生命值。蛮熊：【野兽之灵】的伤害会处决生命值低于12的敌人。猛虎：在6秒后，【野兽之灵】弈子们获得35攻击速度，你的队伍获得15攻击速度。凤凰：【野兽之灵】每参与15次击杀，获得1件基础装备。至多获得4件。  参与击杀数：0', 'setId': '18'},
        {'id': '20778', 'name': '黑暗仪式', 'level': 2, 'descText': '【魔女】不再提供战利品！ 将【魔女精粹】兑换为奖励时，为【魔女】弈子们提供法术加成。获得1个【卡蜜尔】、1个【伊莉丝】和1个【凯特琳】。  已获得的法术加成：0%', 'setId': '18'},
        {'id': '30772', 'name': '弈子套娃', 'level': 3, 'descText': '当1个弈子在战斗中阵亡后，召唤1个降低1星的复制体，其生命值只有60%。获得3次免费刷新。', 'setId': '18'},
        {'id': '30773', 'name': '弈子套娃', 'level': 3, 'descText': '当1个弈子在战斗中阵亡后，召唤1个降低1星的复制体，其生命值只有60%。获得3次免费刷新。', 'setId': '18'},
        {'id': '30774', 'name': '弈子套娃', 'level': 3, 'descText': '当1个弈子在战斗中阵亡后，召唤1个降低1星的复制体，其生命值只有60%。获得3次免费刷新。', 'setId': '18'},
    ],
    'equip': [
        {'id': '1001', 'name': '暴风之剑', 'type': '基础装备', 'descText': None, 'basicDesc': '+10物理加成', 'setId': '18'},
        {'id': '2811', 'name': '斯塔缇克电刃', 'type': '成型装备', 'descText': '每第3次攻击对4名敌人造成30魔法伤害和持续5秒的30%魔抗击碎。  [怪兽入侵专属] 魔抗击碎：降低魔抗值', 'basicDesc': '+20%攻击速度 +10法力值', 'setId': '18'},
        {'id': '6088', 'name': '斯塔缇克电刃', 'type': '神器装备', 'descText': '每第3次攻击对6名敌人造成15+35%携带者额外法术加成的额外魔法伤害。', 'basicDesc': '+15法术加成 +40%攻击速度', 'setId': '18'},
        {'id': '41810', 'name': '绝命花妖纹章', 'type': '转职纹章', 'descText': '携带者获得【绝命花妖】特质/职业。', 'basicDesc': '+250生命上限 +2法力回复', 'setId': '18'},
        {'id': '41821', 'name': '绝命花妖纹章', 'type': '转职纹章', 'descText': '携带者获得【绝命花妖纹章】特质/职业。  持有该纹章的英雄将获得绝命花妖特质/职业的150%效果。', 'basicDesc': '+250生命上限 +2法力回复', 'setId': '18'},
    ],
    'trait': [
        {'id': '83710101', 'checkId': '343', 'name': '主宰', 'num': 2, 'level': 1, 'realDesc': '(2)4%或20%【伤害减免】', 'setId': '18'},
        {'id': '83710102', 'checkId': '343', 'name': '主宰', 'num': 4, 'level': 2, 'realDesc': '(4)6%或33%【伤害减免】', 'setId': '18'},
        {'id': '83710103', 'checkId': '343', 'name': '主宰', 'num': 6, 'level': 3, 'realDesc': '(6)8%或45%【伤害减免】', 'setId': '18'},
    ],
}


class EntityIdentityTests(unittest.TestCase):
    def setUp(self):
        self.resolver = EntityResolver(CATALOG)

    def test_amumu_raw_stars_collapse_to_site_base_identity(self):
        rows = self.resolver.entries('hero')
        self.assertEqual([(r['id'], r['name']) for r in rows], [('4503', '阿木木'), ('1506', '阿卡丽'), ('1513', '阿卡丽')])
        for identity in ('14503', '24503', '34503', '44503', '4503'):
            with self.subTest(identity=identity):
                result = self.resolver.resolve('hero', '阿木木', entity_id=identity)
                self.assertTrue(result.confirmed)
                self.assertEqual(result.entity['id'], '4503')
                self.assertNotIn('starCount', result.entity)
        self.assertEqual(tuple(self.resolver.resolve('hero', '阿木木').entity['source_ids']), ('14503', '24503', '34503', '44503'))

    def test_akali_ad_ap_are_meaningful_manual_choices(self):
        result = self.resolver.resolve('hero', '阿卡丽')
        self.assertEqual(result.status, 'ambiguous')
        self.assertEqual({r['id'] for r in result.candidates}, {'1506', '1513'})
        self.assertEqual(self.resolver.resolve('hero', '阿卡丽', tag='AD').entity['id'], '1506')
        self.assertEqual(self.resolver.resolve('hero', '阿卡丽', tag='AP').entity['id'], '1513')
        ap = next(r for r in CATALOG['hero'] if r['id'] == '31513')
        self.assertEqual(self.resolver.resolve_selection('hero', ap).entity['id'], '1513')
        self.assertIn('AP', display_label('hero', self.resolver.resolve_selection('hero', ap).entity))

    def test_lux_visible_skill_form_is_distinct_and_elise_identical_forms_stay_unconfirmed(self):
        # Actual S18 one-star rows: the rest of the raw star variants are not
        # needed to demonstrate the independent form identities.
        common = '被动：施放时，所有与【拉克丝】拥有同一特质/职业的己方弈子获得3(【法术加成】)法力值。  主动：向最大的敌群发射一道激光，造成375(【法术加成】)魔法伤害，每命中一个敌人，该伤害衰减25%（最低为40%）。'
        source = copy.deepcopy(CATALOG)
        source['hero'] += [
            {'id': '15459', 'name': '拉克丝', 'heroType': 0, 'price': 5, 'skillName': '终极闪光', 'skillDesc': common, 'setId': '18'},
            {'id': '15461', 'name': '拉克丝', 'heroType': 0, 'price': 5, 'skillName': '终极闪光', 'skillDesc': common + '  【黑荆棘】加成：对命中的目标们造成1秒晕眩。', 'setId': '18'},
            {'id': '15462', 'name': '拉克丝', 'heroType': 0, 'price': 5, 'skillName': '终极闪光', 'skillDesc': common + '  【灵魂莲华】加成：对命中的第一个目标造成10%额外伤害。', 'setId': '18'},
            {'id': '12504', 'name': '伊莉丝', 'heroType': 0, 'price': 2, 'skillName': '蜘蛛女皇', 'skillDesc': '变身为蜘蛛，并获得375最大生命值。处于蜘蛛形态时的攻击造成35(【法术加成】)额外魔法伤害，并治疗自身55(【法术加成】)生命值。后续施放提供在4秒内持续衰减的175%攻击速度。', 'setId': '18'},
            {'id': '12515', 'name': '伊莉丝', 'heroType': 0, 'price': 2, 'skillName': '蜘蛛女皇', 'skillDesc': '变身为蜘蛛，并获得375最大生命值。处于蜘蛛形态时的攻击造成35(【法术加成】)额外魔法伤害，并治疗自身55(【法术加成】)生命值。后续施放提供在4秒内持续衰减的175%攻击速度。', 'setId': '18'},
        ]
        resolver = EntityResolver(source)
        self.assertEqual(resolver.resolve('hero', '拉克丝').status, 'ambiguous')
        blackthorn = resolver.resolve('hero', '拉克丝', description='【黑荆棘】加成')
        self.assertEqual(blackthorn.entity['id'], '5461')
        self.assertIn('黑荆棘', display_label('hero', blackthorn.entity))
        self.assertEqual(resolver.resolve_selection('hero', source['hero'][-4]).entity['id'], '5461')
        self.assertEqual(resolver.resolve('hero', '伊莉丝', entity_id='2504').status, 'ambiguous')
        self.assertEqual(resolver.resolve_selection('hero', source['hero'][-1]).status, 'ambiguous')

    def test_hero_variant_without_observable_context_is_not_an_id_only_choice(self):
        source = {'hero': [
            {'id': '14501', 'name': '莫甘娜', 'heroType': 0, 'price': 4, 'skillName': '枯萎诅咒', 'skillDesc': '被动：获得25%全能汲取。  主动：向附近3个敌人发射一道黑暗震波，造成60(【法术加成】)魔法伤害并诅咒他们4秒。然后，生成一个半径2格的枯萎地带，持续相同时长并且每秒造成33(【法术加成】)魔法伤害。被诅咒的敌人们受到22(【法术加成】)×诅咒数的额外伤害。', 'setId': '18'},
            {'id': '14514', 'name': '莫甘娜', 'heroType': 0, 'price': 4, 'skillName': None, 'skillDesc': None, 'setId': '18'},
        ]}
        resolver = EntityResolver(source)
        self.assertEqual(resolver.resolve_selection('hero', source['hero'][1]).status, 'ambiguous')
        self.assertFalse(next(row for row in resolver.entries('hero') if row['id'] == '4514')['identity_selectable'])
        self.assertEqual(resolver.resolve('hero', '莫甘娜', description='枯萎地带').entity['id'], '4501')

    def test_exact_titles_preserve_plus_and_roman_rank(self):
        for title, identity in [('应急护甲Ⅰ', '1023'), ('应急护甲 II', '2023'), ('打捞桶', '1008'), ('打捞桶＋', '2008')]:
            with self.subTest(title=title):
                self.assertEqual(self.resolver.resolve('hex', title).entity['id'], identity)
        for title in ('应急护甲', '应急护甲 III', '打捞桶++', '黑暗仪'):
            self.assertEqual(self.resolver.resolve('hex', title).status, 'unknown')

    def test_augment_level_and_description_evidence_agree(self):
        self.assertEqual(self.resolver.resolve('hex', '成吨的属性！').status, 'ambiguous')
        self.assertEqual(self.resolver.resolve('hex', '成吨的属性！', level=2).entity['id'], '2705')
        self.assertEqual(self.resolver.resolve('hex', '成吨的属性！', level=3).entity['id'], '3705')
        self.assertEqual(self.resolver.resolve('hex', '成吨的属性！', description='88生命值').entity['id'], '3705')
        self.assertEqual(self.resolver.resolve('hex', '成吨的属性！', level=2, description='88生命值').status, 'unknown')
        self.assertEqual(self.resolver.resolve('hex', '应急护甲 I', level=2).status, 'unknown')

    def test_same_level_distinct_description_is_explainable(self):
        self.assertEqual(self.resolver.resolve('hex', '兽性本能', level=2).status, 'ambiguous')
        self.assertEqual(self.resolver.resolve('hex', '兽性本能', description='奈德丽').entity['id'], '20764')
        self.assertEqual(self.resolver.resolve('hex', '兽性本能', description='希维尔').entity['id'], '30764')
        self.assertEqual(self.resolver.resolve('hex', '兽性本能', description='蔚').status, 'ambiguous')
        self.assertEqual(self.resolver.resolve('hex', '兽性本能', description='奈德丽希维尔').status, 'unknown')
        self.assertEqual(self.resolver.resolve('hex', '兽性本能', entity_id='30764').entity['id'], '30764')

    def test_indistinguishable_catalog_ids_cannot_be_forced_by_manual_id(self):
        for name, ids in [('别再错过', ('1625', '10784')), ('弈子套娃', ('30772', '30773', '30774'))]:
            for identity in ids:
                with self.subTest(name=name, identity=identity):
                    row = next(r for r in CATALOG['hex'] if r['id'] == identity)
                    result = self.resolver.resolve_selection('hex', row)
                    self.assertEqual(result.status, 'ambiguous')
                    self.assertIsNone(result.entity)
                    self.assertEqual({r['id'] for r in result.candidates}, set(ids))
                    self.assertIn('区分', result.reason)
                    self.assertEqual(self.resolver.resolve('hex', name, entity_id=identity, description=row['descText']).status, 'ambiguous')

    def test_equipment_same_name_keeps_category_and_emblem_variant(self):
        self.assertEqual(self.resolver.resolve('equip', '斯塔缇克电刃').status, 'ambiguous')
        self.assertEqual(self.resolver.resolve('equip', '斯塔缇克电刃', category='成装').entity['id'], '2811')
        self.assertEqual(self.resolver.resolve('equip', '斯塔缇克电刃', category='神器').entity['id'], '6088')
        self.assertEqual(self.resolver.resolve('equip', '斯塔缇克电刃', category='光明').status, 'unknown')
        self.assertEqual(self.resolver.resolve('equip', '绝命花妖纹章', category='纹章').status, 'ambiguous')
        self.assertEqual(self.resolver.resolve('equip', '绝命花妖纹章', description='150%效果').entity['id'], '41821')
        self.assertEqual(self.resolver.resolve('equip', '暴风之剑').entity['category'], '基础装备')

    def test_trait_requires_level_count_and_uses_web_check_id(self):
        self.assertEqual(self.resolver.resolve('trait', '主宰').status, 'ambiguous')
        self.assertEqual(self.resolver.resolve('trait', '主宰', num=4).entity['id'], '343')
        self.assertEqual(self.resolver.resolve_selection('trait', CATALOG['trait'][0]).entity['num'], 2)
        self.assertEqual({r['id'] for r in self.resolver.entries('trait')}, {'343'})
        self.assertEqual(self.resolver.resolve('trait', '主宰', num=3).status, 'unknown')

    def test_untrusted_manual_row_must_match_catalog_and_observable_identity(self):
        self.assertEqual(self.resolver.resolve_selection('hex', {'id': '99999', 'name': '黑暗仪式'}).status, 'unknown')
        self.assertEqual(self.resolver.resolve_selection('hex', {'id': '20778', 'name': '打捞桶'}).status, 'unknown')
        self.assertEqual(self.resolver.resolve_selection('hex', {'id': '20778', 'name': '黑暗仪式', 'level': 3}).status, 'unknown')
        self.assertEqual(self.resolver.resolve_selection('equip', {'id': '6088', 'name': '斯塔缇克电刃', 'type': '成型装备'}).status, 'unknown')
        self.assertEqual(self.resolver.resolve('hero', '阿木木', entity_id='54503').status, 'unknown')
        self.assertEqual(self.resolver.resolve_selection('hero', {'id': '1506', 'name': '阿卡丽', 'tag': 'AP'}).status, 'unknown')

    def test_all_paths_emit_one_exact_rule_with_no_hidden_context(self):
        calls = []
        def handle(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={'code': 200, 'success': True, 'data': {'comps': []}})
        with tempfile.TemporaryDirectory() as folder:
            dataj = DataJ(patch='18.3', db=Path(folder) / 'cache.db', transport=httpx.MockTransport(handle))
            for kind, title, expected_id, context in [
                ('hero', '阿木木', '4503', {}),
                ('hero', '阿卡丽', '1513', {'tag': 'AP'}),
                ('hex', '黑暗仪式', '20778', {}),
                ('equip', '斯塔缇克电刃', '6088', {'category': '神器'}),
                ('trait', '主宰', '343', {'num': 4}),
            ]:
                result = self.resolver.resolve(kind, title, **context)
                dataj.next_request = 0
                dataj.explore(kind, result.entity)
                self.assertEqual(calls[-1]['version'], '18.3')
                rules = calls[-1]['filter']['rules']
                self.assertEqual(len(rules), 1)
                self.assertEqual(rules[0]['targetId'], expected_id)
                self.assertEqual({k: rules[0][k] for k in ('starCount', 'hexRound', 'equipCarry', 'equipCount')}, {'starCount': '', 'hexRound': '', 'equipCarry': '', 'equipCount': ''})
                self.assertFalse(rules[0]['exclude'])
            self.assertEqual(calls[-1]['filter']['rules'][0]['traitLevel'], '4')

    def test_resolve_any_rejects_cross_kind_collision_and_leaves_kind_explicit(self):
        self.assertEqual(self.resolver.resolve_any('阿木木').kind, 'hero')
        collision = copy.deepcopy(CATALOG)
        collision['hex'].append({'id': '90000', 'name': '暴风之剑', 'level': 2, 'descText': '测试同名跨类别'})
        result = EntityResolver(collision).resolve_any('暴风之剑')
        self.assertEqual(result.status, 'ambiguous')
        self.assertIsNone(result.entity)
        self.assertEqual({r['kind'] for r in result.candidates}, {'hex', 'equip'})

    def test_resolver_snapshot_and_results_do_not_mutate_shared_catalog(self):
        source = copy.deepcopy(CATALOG)
        resolver = EntityResolver(source)
        source['hero'][0]['name'] = '已被修改'
        self.assertTrue(resolver.resolve('hero', '阿木木').confirmed)
        result = resolver.resolve('hero', '阿木木')
        result.entity['name'] = '污染'
        result.entity['source_ids'].append('999')
        self.assertEqual(resolver.resolve('hero', '阿木木').entity['name'], '阿木木')
        self.assertNotIn('999', resolver.entries('hero')[0]['source_ids'])

    def test_other_season_and_invalid_rows_are_not_accepted(self):
        source = copy.deepcopy(CATALOG)
        source['hex'].extend([{'id': '99900', 'name': '未来赛季', 'setId': '19'}, {'id': '', 'name': '没有身份'}, None])
        resolver = EntityResolver(source)
        self.assertEqual(resolver.resolve('hex', '未来赛季').status, 'unknown')
        self.assertEqual(resolver.resolve('hex', '没有身份').status, 'unknown')
        self.assertEqual(resolver.resolve('unsupported', '黑暗仪式').status, 'unknown')

    def test_large_catalog_build_and_title_lookup_do_not_scan_all_pairs(self):
        # Structural budget protects the hot path without a machine-speed
        # assertion; the complete real-catalog timings are measured separately.
        import entity_identity as module
        source = {'hex': [dict(CATALOG['hex'][0], id=str(90000 + i), name=f'压力样本{i}') for i in range(1000)]}
        with patch.object(module, '_observable_key', wraps=module._observable_key) as observed:
            resolver = EntityResolver(source)
        self.assertLessEqual(observed.call_count, 3000)
        with patch.object(module, '_text', wraps=module._text) as normalize:
            result = resolver.resolve('hex', '压力样本999')
        self.assertEqual(result.entity['id'], '90999')
        self.assertLessEqual(normalize.call_count, 2)

    def test_missing_catalog_collections_do_not_break_all_inputs(self):
        for source in (None, {'data': None}, {'hero': None, 'hex': {'invalid': True}}):
            resolver = EntityResolver(source)
            self.assertEqual(resolver.resolve_any('黑暗仪式').status, 'unknown')


if __name__ == '__main__':
    unittest.main()
