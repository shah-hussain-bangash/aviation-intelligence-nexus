import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from services.api.configuration import ConfigurationError,diagnostic,validate_environment


class ConfigurationTests(unittest.TestCase):
    def child_env(self,**values):
        env={k:v for k,v in os.environ.items() if not k.startswith('AIN_') and k!='PORT'};env.update(values);return env

    def test_default_and_test_profiles_preserve_local_settings(self):
        c=validate_environment({});self.assertEqual((c.profile,c.web_port,c.api_port,c.container),('local',8080,8002,False))
        c=validate_environment({'AIN_ENV':'test','AIN_AGENT_JOBS':'1','AIN_MONITOR_ENABLED':'0'})
        self.assertTrue(c.agent_jobs);self.assertFalse(c.monitor)
        self.assertFalse(diagnostic({})['production_ready'])

    def test_bad_ports_flags_hosts_profiles_and_cookie_fail_closed(self):
        cases=[{'PORT':'1e3'},{'PORT':' 8080'},{'AIN_API_PORT':'0'},{'PORT':'8002'},
            {'AIN_AGENT_JOBS':'true'},{'AIN_CONTAINER':''},{'AIN_BIND_HOST':'0.0.0.0'},
            {'AIN_API_HOST':'api'},{'AIN_OLLAMA_HOST':'host.docker.internal'},{'AIN_SESSION_COOKIE':'PRIVATE'},
            {'AIN_ENV':'production'},{'AIN_OBSERVER_MOUNTED':'1'},{'AIN_AUTH_PROVIDER':'oidc'},
            {'AIN_RELEASE_REVISION':'PRIVATE-REVISION'},{'AIN_COOKIE_SECURE':'1'}]
        for env in cases:
            with self.subTest(keys=list(env)):
                with self.assertRaises(ConfigurationError):validate_environment(env)

    def test_container_requires_exact_state_contract_and_permitted_routing(self):
        env={'AIN_CONTAINER':'1','AIN_STATE_ROOT':'/app/.local/active','AIN_DB_PATH':'/app/.local/active/ain.sqlite3',
            'AIN_API_HOST':'api','AIN_BIND_HOST':'0.0.0.0','AIN_OLLAMA_HOST':'ollama','AIN_OBSERVER_MOUNTED':'1'}
        self.assertTrue(validate_environment(env).container)
        for name in ('AIN_STATE_ROOT','AIN_DB_PATH'):
            bad=dict(env);bad[name]='/unapproved'
            with self.assertRaises(ConfigurationError):validate_environment(bad)

    def test_native_paths_are_consistent_without_creating_or_opening_database(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=root/'fresh';db=state/'ain.sqlite3'
            with patch('sqlite3.connect',side_effect=AssertionError('must not open database')):
                self.assertTrue(diagnostic({'AIN_STATE_ROOT':str(state),'AIN_DB_PATH':str(db)})['valid'])
                self.assertFalse(diagnostic({'AIN_STATE_ROOT':str(state),'AIN_DB_PATH':str(root/'other/ain.sqlite3')})['valid'])
            self.assertFalse(state.exists())
            for path in ('PRIVATE\x00VALUE','sqlite:///PRIVATE','\\\\PRIVATE\\state'):
                self.assertFalse(diagnostic({'AIN_STATE_ROOT':path})['valid'])

    def test_secret_references_and_public_origin_are_rejected_without_reading_or_echoing(self):
        env={k:'PRIVATE-SECRET-VALUE' for k in ('AIN_SECRET_KEY','AIN_API_KEY','AIN_ADMIN_PASSWORD','AIN_SECRETS_FILE','AIN_DATABASE_URL','AIN_PUBLIC_ORIGIN')}
        with patch('builtins.open',side_effect=AssertionError('must not read secret files')):r=diagnostic(env)
        self.assertFalse(r['valid']);self.assertNotIn('PRIVATE-SECRET-VALUE',json.dumps(r))
        self.assertIn('inline_secret_not_supported',r['errors']);self.assertIn('secret_provider_not_configured',r['errors'])

    def test_actual_api_import_rejects_bad_profile_before_state_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder)/'must-not-exist'
            env=self.child_env(AIN_ENV='production',AIN_STATE_ROOT=str(state),AIN_DB_PATH=str(state/'ain.sqlite3'),AIN_SECRET_KEY='PRIVATE-SECRET-VALUE')
            result=subprocess.run([sys.executable,'-c','import services.api.main'],env=env,capture_output=True,text=True,timeout=20)
            self.assertNotEqual(result.returncode,0);self.assertFalse(state.exists())
            self.assertIn('runtime_profile_not_supported',result.stderr);self.assertNotIn('PRIVATE-SECRET-VALUE',result.stdout+result.stderr)

    def test_cli_has_safe_failure_json_and_api_factory_revalidates_environment(self):
        result=subprocess.run([sys.executable,'-m','services.api.configuration'],env=self.child_env(AIN_SECRETS_FILE='PRIVATE-SECRET-FILE'),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,2);self.assertFalse(json.loads(result.stdout)['valid']);self.assertNotIn('PRIVATE-SECRET-FILE',result.stdout+result.stderr)
        from services.api.main import create_app
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'AIN_AGENT_JOBS':'true'}):
            path=Path(folder)/'ain.sqlite3'
            with self.assertRaises(ConfigurationError):create_app(path)
            self.assertFalse(path.exists())
