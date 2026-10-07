"""Compact condition controls preserve their existing input contracts."""
import unittest

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from PySide6.QtTest import QSignalSpy

from condition_inputs import ConditionInputs
from ui_theme import STYLE


class CompactConditionInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.host = QWidget()
        self.host.setStyleSheet(STYLE)
        self.layout = QVBoxLayout(self.host)
        self.bar = ConditionInputs()
        self.layout.addWidget(self.bar)
        # The browser owns this action beside its single search input.
        self.layout.insertWidget(0, self.bar.read)
        self.host.show()
        self.qt.processEvents()

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        self.qt.processEvents()

    def test_empty_input_sections_do_not_reserve_rows_after_read_moves(self):
        self.bar.set_resources([])
        self.bar.set_condition(None)
        self.qt.processEvents()

        self.assertFalse(self.bar.current.isVisible())
        self.assertFalse(self.bar.empty.isVisible())
        self.assertTrue(self.bar.resource_container.isHidden())
        self.assertTrue(self.bar.condition_container.isHidden())
        self.assertLessEqual(self.bar.sizeHint().height(), 4)
        self.assertTrue(self.bar.read.isVisible())

    def test_three_long_resource_chips_fit_a_narrow_panel(self):
        self.host.resize(360, 200)
        self.bar.set_resources([
            {'kind': 'hex', 'entity': {'id': str(index), 'name': '这一项名字比较长的强化符文' + str(index)}}
            for index in range(3)
        ])
        self.qt.processEvents()

        self.assertLessEqual(self.host.width(), 360)
        self.assertTrue(self.bar.resource_container.isVisible())
        self.assertTrue(all(chip.isVisible() for chip in self.bar.chips))
        for chip in self.bar.chips:
            self.assertGreaterEqual(chip.x(), 0)
            self.assertLessEqual(chip.geometry().right(), self.bar.resource_container.width())

    def test_identity_alternatives_fit_without_enabling_ambiguous_choices(self):
        self.host.resize(360, 200)
        candidates = [
            {'kind': 'hero', 'id': str(index), 'name': '同名的不同变体弈子',
             'tag': '完整形态' + str(index), 'setId': '18', 'version': '18.3',
             'identity_selectable': index != 0}
            for index in range(4)
        ]
        calls = QSignalSpy(self.bar.alternativeSelected)
        self.bar.show_alternatives(candidates)
        self.qt.processEvents()

        self.assertLessEqual(self.host.width(), 360)
        self.assertTrue(self.bar.condition_container.isVisible())
        self.assertTrue(self.bar.alternatives.isVisible())
        self.assertFalse(self.bar.alternative_buttons[0].isEnabled())
        self.bar.alternative_buttons[0].click()
        self.assertEqual(calls.count(), 0)
        self.bar.alternative_buttons[1].click()
        self.assertEqual(calls.at(0), ['hero', candidates[1]])
        self.assertIn('完整形态1', self.bar.alternative_buttons[1].toolTip())

        self.bar.set_condition(None)
        self.assertTrue(self.bar.alternatives.isVisible())
        self.bar.show_alternatives([])
        self.assertTrue(self.bar.condition_container.isHidden())

    def test_condition_confirmation_is_explicit_and_read_signal_survives_reparent(self):
        entity = {'id': '20778', 'name': '黑暗仪式', 'level': 2,
                  'setId': '18', 'version': '18.3'}
        confirms = QSignalSpy(self.bar.confirmRequested)
        clears = QSignalSpy(self.bar.clearRequested)
        reads = QSignalSpy(self.bar.readRequested)
        queries = QSignalSpy(self.bar.entitySelected)

        self.bar.set_condition('hex', entity, can_confirm=True)
        self.qt.processEvents()
        self.assertTrue(self.bar.condition_container.isVisible())
        self.assertEqual(self.bar.current.text(), '条件 · 黑暗仪式 · 金色')
        self.assertEqual(self.bar.clear.toolTip(), '清除检索条件')
        self.assertEqual(self.bar.confirm.text(), '记为已选')
        self.assertIn('已经选中', self.bar.confirm.toolTip())
        self.assertEqual(confirms.count(), 0)
        self.assertEqual(queries.count(), 0)
        self.assertEqual(self.bar.resources, [])

        self.bar.confirm.click()
        self.bar.clear.click()
        self.bar.read.click()
        self.assertEqual(confirms.count(), 1)
        self.assertEqual(clears.count(), 1)
        self.assertEqual(reads.count(), 1)

        self.bar.set_condition('hex', entity, can_confirm=False)
        self.assertTrue(self.bar.confirm.isHidden())
        self.bar.set_condition(None)
        self.assertTrue(self.bar.condition_container.isHidden())
        self.assertTrue(self.bar.read.isVisible())

    def test_notes_remain_visible_when_condition_clears_and_resources_are_independent(self):
        resource = {'kind': 'equip', 'entity': {
            'id': '2027', 'name': '饮血剑', 'type': '成型装备', 'setId': '18', 'version': '18.3'}}
        self.bar.set_resources([resource])
        self.bar.set_condition('equip', resource['entity'])
        self.bar.show_note('读取失败，请重新打开详情后重试')
        self.bar.set_condition(None)
        self.qt.processEvents()

        self.assertTrue(self.bar.note.isVisible())
        self.assertEqual(self.bar.note.text(), '读取失败，请重新打开详情后重试')
        self.assertTrue(self.bar.condition_container.isVisible())
        self.assertTrue(self.bar.resource_container.isVisible())
        self.assertFalse(self.bar.current.isVisible())

        self.bar.show_note('')
        self.assertTrue(self.bar.condition_container.isHidden())
        self.assertTrue(self.bar.resource_container.isVisible())
        self.bar.set_resources([])
        self.assertTrue(self.bar.resource_container.isHidden())
        self.assertLessEqual(self.bar.sizeHint().height(), 4)


if __name__ == '__main__':
    unittest.main()
