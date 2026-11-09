import json
import unittest
from rglauncher_linux.editor import merge_preferences,jsonc_tokens,load_jsonc


class EditorMergeTests(unittest.TestCase):
    def parse(self,text):
        import re
        return json.loads(re.sub(r',([}\]])',r'\1',''.join(t[0] for t in jsonc_tokens(text))))

    def test_keeps_comments_nested_settings_urls_and_trailing_comma(self):
        original = '''{ // keep my choices
 "editor.fontSize": 17,
 "object": {"workbench.colorTheme":"nested", "url":"https://example.org/a//b"},
 "workbench.colorTheme": "old", /* theme note */
}'''
        out=merge_preferences(original,{'workbench.colorTheme':'new','workbench.iconTheme':'icons'})
        data=self.parse(out)
        self.assertEqual(data['editor.fontSize'],17)
        self.assertEqual(data['object']['workbench.colorTheme'],'nested')
        self.assertEqual(data['workbench.colorTheme'],'new')
        self.assertIn('// keep my choices',out);self.assertIn('/* theme note */',out)
        self.assertEqual(data['workbench.iconTheme'],'icons')

    def test_empty_and_duplicate_preference(self):
        self.assertEqual(self.parse(merge_preferences('{}',{'a':'b'})),{'a':'b'})
        with self.assertRaises(ValueError):merge_preferences('{"a":1,"a":2}',{'a':3})

    def test_does_not_change_unrelated_text(self):
        text='{ "a": true, "b": [1,2] }\n'
        self.assertEqual(merge_preferences(text,{}),text)

    def test_jsonc_comments_without_whitespace_and_string_literals(self):
        self.assertEqual(load_jsonc('{"a":true/*comment*/,"b":",}","c":"https://a/b",}'),
                         {'a':True,'b':',}','c':'https://a/b'})
        with self.assertRaises(ValueError):load_jsonc('{"a"=:true}')
