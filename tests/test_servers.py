import unittest
from rglauncher_linux.servers import summary

class ServerButtonTests(unittest.TestCase):
    def test_auth_is_not_called_offline_and_stale_never_healthy(self):
        hosts=[{'id':'a','label':'Controller'},{'id':'b','label':'Games <private>'}]
        value=summary(hosts,[{'id':'a','state':'online','age':1},{'id':'b','state':'auth_required'}])
        self.assertEqual(value['text'],'1/2');self.assertEqual(value['class'],'warn')
        self.assertIn('authentication required',value['tooltip']);self.assertIn('&lt;private&gt;',value['tooltip'])
        old=summary(hosts,[{'id':'a','state':'stale','age':30}])
        self.assertEqual(old['text'],'Servers');self.assertNotEqual(old['class'],'ok')
        self.assertIn('30s ago',old['tooltip'])
    def test_empty_inventory_has_setup_message(self):
        self.assertIn('No SSH targets',summary([],[])['tooltip'])
    def test_changed_target_or_closed_publisher_never_healthy(self):
        hosts=[{'id':'a','label':'New host','target':'new.example','port':22}]
        sample={'id':'a','target':'old.example','port':22,'state':'online','age':1}
        self.assertNotEqual(summary(hosts,[sample])['class'],'ok')
        sample.update(target='new.example',cache_active=False,state='connecting')
        value=summary(hosts,[sample])
        self.assertIn('Monitor closed',value['tooltip']);self.assertNotIn('Connecting',value['tooltip'])
