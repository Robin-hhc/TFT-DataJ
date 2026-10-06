"""One capture per trigger, exclusive scene routing, and late-result rejection."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
from app import QApplication
from PIL import Image
import test_game_resource_inputs as fixtures
CATALOG=fixtures.CATALOG


class ConditionControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])
    response=fixtures.GameResourceInputTests.response
    flush=fixtures.GameResourceInputTests.flush
    tearDown=fixtures.GameResourceInputTests.tearDown
    def setUp(self):
        fixtures.GameResourceInputTests.setUp(self)
        self.binding=SimpleNamespace(hwnd=7,pid=1,process='MuMuNxDevice.exe',rect=(0,0,1920,1080),dpi=96)
        self.p.binding=self.binding
        self.stack.enter_context(patch('app.win.describe',return_value=self.binding))
        self.stack.enter_context(patch('app.win.foreground_root',return_value=7))
        self.stack.enter_context(patch('app.QTimer.singleShot',side_effect=lambda ms,fn:fn()))
        self.stack.enter_context(patch('condition_controller.capture_image',return_value=(Image.new('RGB',(1920,1080)),self.binding)))

    def test_detail_capture_happens_before_expand_and_does_not_record_selection(self):
        p=self.p
        p.conditions.reader=Mock()
        p.conditions.reader.read.return_value={'route':'detail','status':'resolved','entity':CATALOG['hex'][0], 'candidates':[], 'elapsed_ms':3}
        events=[]
        with patch.object(p,'showNormal',side_effect=lambda:events.append('expanded')):
            p.conditions.trigger()
            self.assertEqual(events,[])
            self.assertEqual(len(self.pending),1)
            self.flush()
        self.assertEqual(events,['expanded'])
        self.assertEqual(p.browser.scope[1]['id'],'20778')
        self.assertEqual(p.selected_resources.events,())


if __name__=='__main__':
    import unittest
    unittest.main()
