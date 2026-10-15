import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "setup_email", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "setup_email.py"
)
se = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(se)


def test_smtp_vals_lock_sender_and_use_starttls():
    v = se.build_smtp_vals("hola@gatheringsgt.com", "pw")
    assert (v["smtp_host"], v["smtp_port"], v["smtp_encryption"]) == ("smtp.gmail.com", 587, "starttls")
    assert v["from_filter"] == "hola@gatheringsgt.com"
    assert v["smtp_pass"] == "pw"


def test_imap_vals_ssl_and_optional_model():
    v = se.build_imap_vals("hola@gatheringsgt.com", "pw", None)
    assert (v["server"], v["port"], v["is_ssl"], v["server_type"]) == ("imap.gmail.com", 993, True, "imap")
    assert "object_id" not in v
    assert se.build_imap_vals("u", "pw", 7)["object_id"] == 7


def test_params_point_replies_to_mailbox():
    p = se.build_params()
    assert p["mail.catchall.domain"] == "gatheringsgt.com"
    assert p["mail.catchall.alias"] == "hola"
    assert p["mail.default.from"] == "hola@gatheringsgt.com"
