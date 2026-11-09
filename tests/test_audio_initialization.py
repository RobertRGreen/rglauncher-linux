"""The packaged audio UI must not change volume when constructing a row."""
import ast
from pathlib import Path
import unittest


class InitializationTests(unittest.TestCase):
    def test_initial_set_is_blocked(self):
        source=(Path(__file__).resolve().parents[1]/'bin/audio-menu').read_text()
        tree=ast.parse(source)
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_build_row')
        statements=node.body
        block=next(i for i,n in enumerate(statements) if isinstance(n,ast.Expr)
                   and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute)
                   and n.value.func.attr=='handler_block')
        protected=statements[block+1]
        self.assertIsInstance(protected,ast.Try)
        self.assertEqual(protected.body[0].value.func.attr,'set_value')
        self.assertEqual(protected.finalbody[0].value.func.attr,'handler_unblock')
        # Execute the actual initialization fragment against a write-spy scale.
        writes=[]
        class Scale:
            blocked=False
            def handler_block(self,h):self.blocked=True
            def set_value(self,v):
                if not self.blocked:writes.append(v)
            def handler_unblock(self,h):self.blocked=False
        class Label:
            def set_text(self,text):self.text=text
        scope={'scale':Scale(),'hid':1,'item':{'pct':62},'val':Label()}
        exec(compile(ast.Module(body=statements[block:block+3],type_ignores=[]),'initialization','exec'),scope)
        self.assertEqual(writes,[])
        self.assertEqual(scope['val'].text,'62%')
        scope['scale'].set_value(63)
        self.assertEqual(writes,[63])


if __name__=='__main__':unittest.main()
