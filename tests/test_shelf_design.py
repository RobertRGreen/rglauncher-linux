"""Shelf adaptation must preserve actions, prevent duplicates and fit outputs."""
import copy
import unittest
from rglauncher_linux.shelf_design import compose,stylesheet,ROOT
from rglauncher_linux.editor import load_jsonc

class ShelfDesignTests(unittest.TestCase):
    def base(self):
        c=load_jsonc((ROOT/'share/waybar/config.jsonc').read_text())
        c['custom/remote']={'format':'{text}','exec':'private-read-only-status','on-click':'private-menu','on-click-right':'private-stop'}
        c['custom/camera']={'exec':'private-camera-status','on-click':'private-camera-panel'}
        c['modules-right']+=['custom/remote','custom/camera']
        return c
    def test_retains_private_actions_and_never_mutates_source(self):
        base=self.base();original=copy.deepcopy(base)
        result=compose(base,{'name':'TEST','width':3440,'height':1440,'scale':1})
        self.assertEqual(base,original)
        self.assertEqual(result['custom/remote'],{**base['custom/remote'],'max-length':12})
        self.assertEqual(result['custom/camera'],base['custom/camera'])
        self.assertIn('custom/remote',result['modules-right'])
        self.assertIn('custom/camera',result['rgl-tool-items'])
        from rglauncher_linux.shelf import tool_tabs
        commands=[row[2] for row in tool_tabs(result)[0][1]]
        self.assertIn('private-camera-panel',commands)
        self.assertTrue(any(row[1]=='Camera' for row in tool_tabs(result)[0][1]))
        self.assertFalse(any('/' in row[1] for row in tool_tabs(result)[0][1]))
        self.assertFalse(result['exclusive']);self.assertEqual(result['layer'],'overlay')
    def test_scale_rotation_and_narrow_disclosure(self):
        base=self.base()
        for width,scale,transform in [(3840,1,0),(2560,2,0),(1920,2,0),(2160,2,1)]:
            m={'name':'TEST','width':width,'height':1920,'scale':scale,'transform':transform}
            result=compose(base,m)
            logical=(m['height'] if transform%2 else width)/scale
            self.assertLessEqual(result['width'],logical-32)
            self.assertTrue(all(key in result for key in result['modules-left']+result['modules-center']+result['modules-right']))
            self.assertEqual(result['network']['on-click'],base['network']['on-click'])
        narrow=compose(base,{'name':'TEST','width':960,'height':1080,'scale':1})
        self.assertNotIn('image#rgl-terminal',narrow['group/rgl-launch']['modules'])
        self.assertIn('image#rgl-terminal',narrow['rgl-tool-items'])
    def test_image_modules_have_native_tooltips_and_no_polling(self):
        result=compose(self.base(),{'name':'TEST','width':3440,'height':1440,'scale':1})
        for key,value in result.items():
            if key.startswith('image#'):
                self.assertEqual(value['interval'],'once')
                self.assertIn('printf',value['exec'])
                self.assertTrue(value['tooltip'])
        self.assertIn('window#waybar.hidden {opacity:0;}',stylesheet())

    def test_status_uses_actual_state_and_preserves_evidence(self):
        from rglauncher_linux.shelf_design import clean_status
        data={'text':'REMOTE ● HOSTED','class':'controlled','tooltip':'This machine is being controlled'}
        result=clean_status(data,'custom/remote')
        self.assertEqual(result,{**data,'text':'Hosted'})
        server={'text':'\U000f048b DOWN','class':'down','tooltip':'No response'}
        self.assertEqual(clean_status(server,'custom/server'),{**server,'text':'DOWN'})
        self.assertEqual(server['text'],'\U000f048b DOWN')

    def test_nested_groups_and_middle_actions_survive_without_cycles(self):
        from rglauncher_linux.shelf import tool_tabs
        config={'rgl-tool-items':['group/parent'],'group/parent':{'modules':['custom/child','group/parent']},
                'custom/child':{'on-click':'open-child','on-click-middle':'middle-child'}}
        rows=tool_tabs(config)[0][1]
        self.assertEqual([r[2] for r in rows],['open-child','middle-child'])
