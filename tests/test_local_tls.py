from contextlib import closing
from datetime import timedelta
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
from threading import Thread
import unittest

from cryptography import x509
from infra.local_tls import CERT, KEY, MANIFEST, ROOT, create, validate


class LocalTLSTests(unittest.TestCase):
    def setUp(self):
        (ROOT / '.local').mkdir(exist_ok=True)
        self.folder=tempfile.TemporaryDirectory(dir=ROOT / '.local');self.addCleanup(self.folder.cleanup)
        self.base=Path(self.folder.name);self.bundle=self.base/'bundle'
        self.record=create(self.bundle);self.pin=self.record['certificate_sha256']

    def test_bundle_is_pinned_local_only_and_has_restrictive_modes_where_supported(self):
        self.assertTrue(validate(self.bundle,self.pin)['valid'])
        self.assertFalse(self.record['production_ready']);self.assertFalse(self.record['trust_installed'])
        self.assertFalse(self.record['service_started']);self.assertEqual(self.record['hosts'],['localhost','127.0.0.1'])
        self.assertNotIn('PRIVATE KEY',json.dumps(self.record))
        if os.name!='nt':self.assertEqual((self.bundle/KEY).stat().st_mode & 0o777,0o600)

    def test_existing_outside_and_traversal_outputs_are_refused(self):
        original=(self.bundle/KEY).read_bytes()
        for target in (self.bundle,ROOT/'outside-private-tls',self.base/'..'/'escape'):
            with self.assertRaises(ValueError):create(target)
        self.assertEqual((self.bundle/KEY).read_bytes(),original)

    def test_wrong_pin_changed_key_manifest_and_appended_certificate_are_refused(self):
        with self.assertRaises(ValueError):validate(self.bundle,'0'*64)
        other=self.base/'other';create(other)
        key=(self.bundle/KEY).read_bytes();(self.bundle/KEY).write_bytes((other/KEY).read_bytes())
        with self.assertRaises(ValueError):validate(self.bundle,self.pin)
        (self.bundle/KEY).write_bytes(key)
        cert=(self.bundle/CERT).read_bytes();(self.bundle/CERT).write_bytes(cert+b'EXTRA')
        with self.assertRaises(ValueError):validate(self.bundle,self.pin)
        (self.bundle/CERT).write_bytes(cert)
        record=json.loads((self.bundle/MANIFEST).read_bytes());record['production_ready']=True
        (self.bundle/MANIFEST).write_text(json.dumps(record),encoding='utf-8')
        with self.assertRaises(ValueError):validate(self.bundle,self.pin)

    def test_not_yet_valid_and_expired_material_are_refused(self):
        cert=x509.load_pem_x509_certificate((self.bundle/CERT).read_bytes())
        for clock in (cert.not_valid_before_utc-timedelta(seconds=1),cert.not_valid_after_utc):
            with self.assertRaises(ValueError):validate(self.bundle,self.pin,now=clock)

    def test_real_loopback_tls_requires_explicit_trust_and_correct_hostname(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(b'AIN synthetic TLS fixture')
            def log_message(self,*args):pass
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(self.bundle/CERT,self.bundle/KEY)
        server=HTTPServer(('127.0.0.1',0),Handler)
        server.socket=context.wrap_socket(server.socket,server_side=True)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with self.assertRaises(ssl.SSLCertVerificationError):
                with closing(http.client.HTTPSConnection('127.0.0.1',server.server_port,timeout=3)) as client:client.request('GET','/')
            trusted=ssl.create_default_context(cafile=str(self.bundle/CERT))
            for hostname in ('127.0.0.1','localhost'):
                with closing(http.client.HTTPSConnection(hostname,server.server_port,context=trusted,timeout=3)) as client:
                    client.request('GET','/');response=client.getresponse()
                    self.assertEqual(response.status,200);self.assertEqual(response.read(),b'AIN synthetic TLS fixture')
            with self.assertRaises(ssl.SSLCertVerificationError):
                with socket.create_connection(('127.0.0.1',server.server_port),timeout=3) as connection:
                    trusted.wrap_socket(connection,server_hostname='outside.invalid')
        finally:server.shutdown();server.server_close();thread.join(timeout=3)
        self.assertFalse(thread.is_alive())

    def test_cli_failure_does_not_echo_untrusted_input(self):
        result=subprocess.run([sys.executable,'-m','infra.local_tls','check','--directory',str(self.bundle),
            '--certificate-sha256','PRIVATE-INVALID-PIN'],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,2);self.assertEqual(json.loads(result.stdout)['error'],'local_tls_material_rejected')
        self.assertNotIn('PRIVATE-INVALID-PIN',result.stdout+result.stderr)
