import unittest
from choice_reader import normalize_name, read_choice, exact_catalog_matches

class ChoiceReaderTest(unittest.TestCase):
    def test_s18_punctuation_and_refresh_buttons(self):
        def row(text,x,y,width=80,height=12,score=.96):
            return {'text':text,'score':score,'box':[[x,y],[x+width,y],[x+width,y+height],[x,y+height]]}
        rows=[row('请选择一个强化付又',220,22,200),row('¿2-1',222,1,26)]
        rows += [row(name,x,150,100,12,.84) for x,name in zip([120,268,416],['银汤匙','耐心是一种美德','战时补给:巨人腰带'])]
        rows += [row('C1',x,105,22,20) for x in [160,308,456]]
        result=read_choice(rows,(640,360))
        self.assertEqual([r['raw_text'] for r in result['cards']],['银汤匙','耐心是一种美德','战时补给:巨人腰带'])
        self.assertFalse(result['header_exact'])
        rows[0]['text']='请选择其他操作'
        self.assertEqual(read_choice(rows,(640,360))['scene'],'unknown')

    def test_tiers_are_not_fuzzy_merged(self):
        self.assertEqual(normalize_name("治疗法球 Ⅱ"), "治疗法球II")
        self.assertNotEqual(normalize_name("秘法帮派1"), normalize_name("秘法帮派 I"))
        self.assertNotEqual(normalize_name("纹章树+"), normalize_name("纹章树++"))

    def test_no_scene_header_rejects_arbitrary_labels(self):
        rows = [{"text":"厨神阿福", "score":1, "box":[[200,200],[300,200],[300,230],[200,230]]}]
        self.assertEqual(read_choice(rows, (1000,600))["cards"], [])

    def test_duplicate_catalog_names_stay_ambiguous(self):
        catalog = [{"id":1,"name":"示例"},{"id":2,"name":"示例"}]
        self.assertEqual(len(exact_catalog_matches("示例", catalog)), 2)
        self.assertEqual(exact_catalog_matches("示侧", catalog), [])

if __name__ == "__main__":
    unittest.main()
