import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

from infra.local_https_rehearsal import verify, ROOT
from infra.local_tls import create
from services.api.configuration import ConfigurationError, validate_environment
from tests.test_june_http_rehearsal import ports


class LocalHTTPSTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(dir=ROOT/'.local');self.addCleanup(self.folder.cleanup)
        self.base=Path(self.folder.name)

    def settings(self,**values):
        return {'AIN_ENV':'test','AIN_LOCAL_HTTPS':'1','AIN_LOCAL_TLS_DIRECTORY':str(self.base/'tls'),
                'AIN_LOCAL_TLS_SHA256':'e'*64,'AIN_SESSION_COOKIE':'ain_test_session',
                'AIN_STATE_ROOT':str(self.base/'state'),'AIN_DB_PATH':str(self.base/'state/ain.sqlite3'),**values}

    def test_mode_requires_native_test_namespace_and_pinned_private_material(self):
        self.assertTrue(validate_environment(self.settings()).local_https)
        self.assertFalse(validate_environment({}).local_https)
        for change in ({'AIN_ENV':'local'},{'AIN_CONTAINER':'1'},{'AIN_SESSION_COOKIE':'ain_session'},
                       {'AIN_LOCAL_HTTPS':'true'},{'AIN_LOCAL_TLS_SHA256':'invalid'},
                       {'AIN_LOCAL_TLS_DIRECTORY':str(ROOT/'outside')},{'AIN_LOCAL_HTTPS':'0'},
                       {'AIN_STATE_ROOT':''},{'AIN_STATE_ROOT':str(ROOT/'.local'),'AIN_DB_PATH':str(ROOT/'.local/ain.sqlite3')}):
            with self.subTest(change=change),self.assertRaises(ConfigurationError):validate_environment(self.settings(**change))

    def test_real_verified_https_signin_cookie_origin_roles_and_logout(self):
        web,api=ports();result=verify(self.base/'run',web_port=web,api_port=api)
        self.assertTrue(result['passed'],result);self.assertTrue(all(result['checks'].values()))
        self.assertTrue(result['checks']['secure_cookie_not_sent_over_http'])
        self.assertTrue(result['checks']['logout_revokes_old_cookie'])
        for port in (web,api):
            with socket.socket() as probe:self.assertNotEqual(probe.connect_ex(('127.0.0.1',port)),0)

    def test_gateway_refuses_wrong_pin_before_listening_without_echoing_input(self):
        bundle=self.base/'bundle';create(bundle)
        env={k:v for k,v in os.environ.items() if not k.startswith('AIN_') and k!='PORT'}
        env.update(self.settings(AIN_LOCAL_TLS_DIRECTORY=str(bundle),AIN_LOCAL_TLS_SHA256='f'*64))
        result=subprocess.run(['node','scripts/dev.mjs'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,1);self.assertNotIn('AIN dashboard:',result.stdout)
        self.assertNotIn(str(bundle),result.stderr);self.assertNotIn('f'*64,result.stderr)
        self.assertIn('Local HTTPS startup refused.',result.stderr)

    def test_existing_output_or_occupied_port_is_preserved_before_state(self):
        with self.assertRaises(ValueError):verify(self.base)
        with socket.socket() as busy:
            busy.bind(('127.0.0.1',0));busy.listen();web=busy.getsockname()[1]
            with socket.socket() as other:other.bind(('127.0.0.1',0));api=other.getsockname()[1]
            with self.assertRaises(ValueError):verify(self.base/'blocked',web_port=web,api_port=api)
            self.assertFalse((self.base/'blocked').exists())
