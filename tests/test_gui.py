"""GUI tests use synthetic data in disposable temporary directories only."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import backend as b
import gui
from test_backend import ACCOUNT,make_fixture


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.fixture=make_fixture()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='modifier_gui_')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.path=self.root/str(ACCOUNT)/'S0000.sl2'
        self.path.parent.mkdir()
        self.path.write_bytes(self.fixture)
        for name,value in [('find_saves',[self.path]),('game_running',False)]:
            patcher=patch.object(b,name,return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app=gui.App()
        self.app.withdraw()
        self.app.update()
        self.addCleanup(self.app.destroy)

    def choose(self,key):
        self.app.tree.selection_set(str(key))
        self.app.update()

    def test_name_and_single_save_button(self):
        def children(w):
            result=[]
            for child in w.winfo_children():result.append(child);result.extend(children(child))
            return result
        self.assertEqual(self.app.title(),'Sekiro Resource Modifier')
        buttons=[w for w in children(self.app) if w.winfo_class()=='TButton']
        self.assertEqual([w.cget('text') for w in buttons],['保存'])
        self.assertEqual(len(self.app.tree.get_children()),50)

    def test_save_selector_uses_slot_time(self):
        self.assertEqual(self.app.slotvar.get(),'存档 1 | 2026-10-02 21:11:59.344')
        self.assertEqual(self.app.slots[self.app.slotvar.get()],0)

    def test_no_inline_explanations_or_status(self):
        def labels(w):
            result=[]
            for child in w.winfo_children():
                if child.winfo_class()=='TLabel':result.append(child)
                result.extend(labels(child))
            return result
        self.assertFalse(hasattr(self.app,'status'))
        text=[w.cget('text') for w in labels(self.app)]
        self.assertIn('存档',text)
        self.assertNotIn('角色',text)
        for w in labels(self.app):self.assertFalse(str(w.cget('foreground')))
        self.assertNotIn('policy',self.app.tree.cget('columns'))

    def test_fields_update_targets_automatically(self):
        self.choose(3440)
        self.app.carry.set('2')
        self.app.store.set('321')
        self.assertEqual(self.app.targets['3440'],{'carry':2,'storage':321})
        self.assertEqual(self.path.read_bytes(),self.fixture)

    def test_save_commits_current_fields_without_history(self):
        self.choose(3440)
        self.app.carry.set('3')
        self.app.store.set('9999')
        self.app.sen.set('12345')
        with patch.object(gui.messagebox,'showinfo'),patch.object(gui.messagebox,'showerror',side_effect=AssertionError):self.app.apply()
        saved=b.Save(self.path.read_bytes(),ACCOUNT)
        self.assertEqual(saved.quantities(0,3440),(3,9999))
        self.assertEqual(b.u32(saved.slot(0),b.SEN),12345)
        self.assertEqual(list(self.path.parent.iterdir()),[self.path])
        self.assertEqual(list(self.root.iterdir()),[self.path.parent])

    def test_invalid_field_prevents_save(self):
        self.choose(3440)
        self.app.carry.set('4')
        with patch.object(gui.messagebox,'showerror') as error:
            self.app.apply()
            error.assert_called_once()
        self.assertEqual(self.path.read_bytes(),self.fixture)

    def test_invalid_field_not_silently_discarded_on_selection(self):
        self.choose(3440)
        self.app.store.set('invalid')
        with patch.object(gui.messagebox,'showerror') as error:
            self.choose(3020)
            error.assert_called_once()
        self.assertEqual(self.app.tree.selection(),('3440',))
        self.assertEqual(self.app.store.get(),'invalid')

    def test_maximum_updates_selected_fields(self):
        self.choose(3440)
        self.app.maxvar.set(True)
        self.app.maximum()
        self.assertEqual(self.app.carry.get(),'3')
        self.assertEqual(self.app.store.get(),'9999')
        self.assertEqual(self.app.sen.get(),str(b.SEN_LIMIT))
        self.assertEqual(self.path.read_bytes(),self.fixture)

    def test_protected_unowned_disabled(self):
        self.choose(3053)
        self.assertEqual(str(self.app.centry.cget('state')),'disabled')
        self.assertEqual(str(self.app.sentry.cget('state')),'disabled')
        _,_,items=self.app.plan()
        self.assertNotIn('3053',items)

    def test_running_game_save_refused(self):
        self.app.sen.set('12345')
        with patch.object(b,'game_running',return_value=True),patch.object(gui.messagebox,'showerror') as error:
            self.app.apply()
            error.assert_called_once()
        self.assertEqual(self.path.read_bytes(),self.fixture)

    def test_no_configuration_or_history_on_load(self):
        self.app.load()
        self.assertEqual(list(self.root.iterdir()),[self.path.parent])
        self.assertEqual(list(self.path.parent.iterdir()),[self.path])


if __name__=='__main__':unittest.main(verbosity=2)
