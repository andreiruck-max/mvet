from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from . import bling
from .xml_discounts import enrich


@override_settings(BLING_NETWORK_ENABLED=False)
class LaboratoryNetworkTests(SimpleTestCase):
    def test_all_remote_operations_block_before_transport(self):
        with patch('apps.integrations.bling.build_opener') as transport:
            for path, options in [('/nfe', {}), ('/oauth/token', {'form': {'grant_type': 'refresh_token'}}),
                                  ('/produtos/1', {'method': 'PATCH', 'payload': {'preco': 1}}),
                                  ('/estoques', {'method': 'POST', 'payload': {}})]:
                with self.subTest(path=path), self.assertRaisesMessage(bling.BlingError, 'bloqueada'):
                    bling.request_json(path, **options)
            transport.assert_not_called()

    def test_oauth_and_database_credentials_are_not_accessed(self):
        with self.assertRaisesMessage(bling.BlingError, 'bloqueada'):
            bling.configured()
        with patch('apps.integrations.bling.get') as query:
            with self.assertRaisesMessage(bling.BlingError, 'bloqueada'):
                bling.read('/nfe')
            query.assert_not_called()

    def test_signed_xml_download_is_blocked(self):
        with patch('apps.integrations.xml_discounts.build_opener') as transport:
            with self.assertRaisesMessage(bling.BlingError, 'bloqueada'):
                enrich({'xml': 'https://www.bling.com.br/documento?token=synthetic'})
            transport.assert_not_called()
