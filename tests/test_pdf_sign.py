import datetime
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HAS_SIGN_DEPS = all(
    importlib.util.find_spec(m) is not None
    for m in ("pyhanko", "cryptography", "pypdf", "reportlab")
)


def _create_test_pfx(destination, password, *, key_type="rsa"):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
    from cryptography.x509.oid import NameOID

    if key_type == "ecdsa":
        key = ec.generate_private_key(ec.SECP256R1())
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    now = datetime.datetime.now(datetime.timezone.utc)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, f"Prueba {key_type.upper()}"),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, "IDCES-12345678Z"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PDFiu Tests"),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    data = pkcs12.serialize_key_and_certificates(
        b"test", key, cert, None, BestAvailableEncryption(password.encode("utf-8"))
    )
    Path(destination).write_bytes(data)


@unittest.skipUnless(HAS_SIGN_DEPS, "Signing dependencies not installed in this environment")
class PdfSignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._patch = patch.dict(sys.modules, {"translations": type("M", (), {"tr": staticmethod(lambda s: s)})()})
        cls._patch.start()
        import pdf_ops
        import pdf_sign

        cls.pdf_ops = pdf_ops
        cls.pdf_sign = pdf_sign

    @classmethod
    def tearDownClass(cls):
        cls._patch.stop()

    def _assert_sign_and_inspect(self, key_type):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "doc.pdf"
            self.pdf_ops.blank_pdf(src, 595, 842)
            pfx = root / f"cert_{key_type}.pfx"
            _create_test_pfx(pfx, "clave-prueba", key_type=key_type)

            signer = self.pdf_sign.load_signer(pfx=str(pfx), password="clave-prueba")
            signed = root / f"signed_{key_type}.pdf"
            self.pdf_sign.sign_with(src, signed, 0, (60, 60, 260, 140), signer)

            signatures = self.pdf_sign.inspect_pdf_signatures(signed)
            self.assertEqual(len(signatures), 1)
            sig = signatures[0]
            self.assertTrue(sig["integrity"])
            self.assertEqual(sig["coverage_name"], "ENTIRE_FILE")
            self.assertEqual(sig["identifier"], "12345678Z")

    def test_sign_and_verify_rsa_pfx(self):
        self._assert_sign_and_inspect("rsa")

    def test_sign_and_verify_ecdsa_pfx(self):
        self._assert_sign_and_inspect("ecdsa")


if __name__ == "__main__":
    unittest.main()
