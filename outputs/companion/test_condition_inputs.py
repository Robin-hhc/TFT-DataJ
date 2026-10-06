"""Actual Qt input controls; candidate cards never become selected shortcuts."""
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QSignalSpy
from condition_inputs import ConditionInputs


class ConditionInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])

    def test_confirmed_resource_click_emits_exactly_one_condition(self):
        bar=ConditionInputs()
        calls=QSignalSpy(bar.entitySelected)
        item={'kind':'hex','entity':{'id':'20778','name':'黑暗仪式','level':2}}
        bar.set_resources([item])
        bar.chips[0].click()
        self.assertEqual(calls.count(),1)
        self.assertEqual(calls.at(0),['hex',item['entity']])
        bar.deleteLater();self.qt.processEvents()

    def test_overflow_and_explicit_confirmation_are_separate_from_search(self):
        bar=ConditionInputs();queries=QSignalSpy(bar.entitySelected);confirms=QSignalSpy(bar.confirmRequested)
        resources=[{'kind':'equip','entity':{'id':str(i),'name':'装备'+str(i)}} for i in range(5)]
        bar.set_resources(resources)
        self.assertEqual(len(bar.chips),3)
        self.assertEqual(len(bar.menu.actions()),2)
        self.assertFalse(bar.more.isHidden())
        bar.set_condition('equip',resources[0]['entity'],can_confirm=True)
        self.assertEqual(queries.count(),0)
        self.assertEqual(confirms.count(),0)
        bar.confirm.click();self.assertEqual(confirms.count(),1)
        bar.menu.actions()[0].trigger()
        self.assertEqual(queries.at(0),['equip',resources[3]['entity']])
        bar.set_resources([]);self.assertFalse(bar.empty.isHidden());self.assertTrue(bar.more.isHidden())
        bar.deleteLater();self.qt.processEvents()


if __name__=='__main__':unittest.main()
