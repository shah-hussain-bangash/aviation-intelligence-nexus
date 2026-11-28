"""Prepare pinned self-signed localhost material; never installs trust or starts a service."""
import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import re

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from infra.research_model_recovery import ordinary, unique_object
from pipelines.synthetic_ingestion import host, local
from rag.semantic_review import new_output, require
from services.api.paths import ROOT

CERT = 'certificate.pem'
KEY = 'private-key.pem'
MANIFEST = 'manifest.json'


def summary(cert):
    return {'format': 'ain-local-tls-v1', 'certificate_sha256': cert.fingerprint(hashes.SHA256()).hex(),
            'expires_at': cert.not_valid_after_utc.isoformat(), 'hosts': ['localhost', '127.0.0.1'],
            'scope': 'Self-signed local research material; explicit client trust only',
            'trust_installed': False, 'service_started': False, 'production_ready': False}


def validate(directory, certificate_sha256, *, now=None):
    host(); directory = local(directory)
    require(directory.is_relative_to(ROOT / '.local') and directory != ROOT / '.local', 'Private TLS directory required')
    require(isinstance(certificate_sha256, str) and re.fullmatch('[0-9a-f]{64}', certificate_sha256), 'Exact certificate pin required')
    raw_cert = ordinary(directory / CERT, 64000).read_bytes()
    cert = x509.load_pem_x509_certificate(raw_cert)
    require(raw_cert == cert.public_bytes(serialization.Encoding.PEM), 'Single canonical certificate required')
    require(cert.fingerprint(hashes.SHA256()).hex() == certificate_sha256, 'Certificate pin mismatch')
    raw_key = ordinary(directory / KEY, 16000).read_bytes()
    key = serialization.load_pem_private_key(raw_key, password=None)
    require(isinstance(key, rsa.RSAPrivateKey) and key.key_size >= 2048, 'Local RSA key required')
    require(raw_key == key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()), 'Single canonical private key required')
    public = cert.public_key()
    require(isinstance(public, rsa.RSAPublicKey) and key.public_key().public_numbers() == public.public_numbers(), 'Certificate and key mismatch')
    require(cert.issuer == cert.subject and isinstance(cert.signature_hash_algorithm, hashes.SHA256), 'Self-signed SHA256 certificate required')
    public.verify(cert.signature, cert.tbs_certificate_bytes, padding.PKCS1v15(), cert.signature_hash_algorithm)
    clock = datetime.now(timezone.utc) if now is None else now
    require(isinstance(clock, datetime) and clock.utcoffset() is not None, 'Timezone-aware clock required')
    require(cert.not_valid_before_utc <= clock < cert.not_valid_after_utc
            and cert.not_valid_after_utc - cert.not_valid_before_utc <= timedelta(days=7, minutes=1), 'Local certificate validity rejected')
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    require(set(san) == {x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))}, 'Exact loopback names required')
    require(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False, 'CA certificates refused')
    require(list(cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value) == [ExtendedKeyUsageOID.SERVER_AUTH], 'Server-only usage required')
    usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
    require(usage.digital_signature and usage.key_encipherment and not usage.key_cert_sign and not usage.crl_sign, 'Local key usage rejected')
    raw_manifest = ordinary(directory / MANIFEST, 16000).read_text(encoding='utf-8')
    record = json.loads(raw_manifest, object_pairs_hook=unique_object)
    require(record == summary(cert), 'TLS manifest changed')
    return {'valid': True, **record}


def write_private(path, value):
    # No key material in logs or Git; mode is restrictive where the OS supports it.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream: stream.write(value)


def create(output):
    host(); target = new_output(output)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'AIN local research only')])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=7))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True,
                data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=None, decipher_only=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    target.mkdir(mode=0o700, exist_ok=False)
    write_private(target / CERT, cert.public_bytes(serialization.Encoding.PEM))
    write_private(target / KEY, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    record = summary(cert)
    write_private(target / MANIFEST, (json.dumps(record, indent=2) + '\n').encode())
    return validate(target, record['certificate_sha256'])


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='action', required=True)
    prepare = sub.add_parser('create'); prepare.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('check'); check.add_argument('--directory', type=Path, required=True); check.add_argument('--certificate-sha256', required=True)
    args = parser.parse_args()
    try: result = create(args.output) if args.action == 'create' else validate(args.directory, args.certificate_sha256)
    except Exception:
        print(json.dumps({'valid': False, 'error': 'local_tls_material_rejected', 'production_ready': False})); return 2
    print(json.dumps(result, indent=2)); return 0


if __name__ == '__main__': raise SystemExit(main())
