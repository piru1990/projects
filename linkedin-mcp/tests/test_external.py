import external


def kind(url=None, ats=None):
    r = external.classify(url, ats)
    return r and (r["external_kind"], r["account_hint"])


def test_urls_seen_on_06_10_2026():
    r = external.classify("https://sapiens.viterbit.net/es/job/123?utm_source=linkedin&utm_medium=jobs&ref=abc")
    assert r == {"external_kind": "ats:viterbit", "site": "Viterbit", "account_hint": "no",
                 "clean_url": "https://sapiens.viterbit.net/es/job/123?ref=abc"}
    assert kind("https://www.unmejorempleo.com.gt/oferta/123") == ("job_board", "si")
    assert kind("https://gt.trabajosdiarios.com/oferta-trabajo/abc") == ("job_board", "desconocido")


def test_ats_continue_uses_the_ats_name():
    # 4398844859 (cbc): its only URL points back to linkedin.com, so the name decides.
    assert kind(None, "SmartRecruiters") == ("ats:smartrecruiters", "a_veces")
    assert kind(None, "Workday") == ("ats:workday", "si")
    assert kind(None, "AcmeHire") == ("ats:acmehire", "desconocido")


def test_forms():
    assert kind("https://docs.google.com/forms/d/e/1FAIpQ/viewform?usp=sf_link") == ("google_forms", "no")
    assert kind("https://forms.gle/abc123") == ("google_forms", "no")
    assert kind("https://forms.office.com/r/XYZ") == ("microsoft_forms", "no")
    assert kind("https://forms.cloud.microsoft/r/XYZ") == ("microsoft_forms", "no")
    assert kind("https://docs.google.com/document/d/1") == ("company_site", "desconocido")


def test_safety_go_is_unwrapped_and_tracking_dropped():
    wrapped = ("https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fjobs.smartrecruiters.com%2Fcbc%2F123"
               "%3Ftrk%3Dabc%26utm_campaign%3Dx%26lang%3Des&trk=flagship")
    r = external.classify(wrapped)
    assert r["external_kind"] == "ats:smartrecruiters"
    assert r["clean_url"] == "https://jobs.smartrecruiters.com/cbc/123?lang=es"


def test_host_suffix_is_matched_on_dot_boundaries():
    assert kind("https://acme.wd5.myworkdayjobs.com/es/careers/job/1") == ("ats:workday", "si")
    assert kind("https://notlever.co.example.com/x") == ("company_site", "desconocido")
    assert kind("https://careers.acme.com/jobs/1", "Greenhouse") == ("ats:greenhouse", "no")


def test_odd_urls_never_raise():
    double = "https://www.linkedin.com/safety/go/?url=https%253A%252F%252Fjobs.smartrecruiters.com%252Fcbc%252F123"
    assert external.classify(double)["clean_url"] == "https://jobs.smartrecruiters.com/cbc/123"
    assert kind("https%3A%2F%2Fjobs.lever.co%2Facme") == ("ats:lever", "no")
    assert kind("jobs.lever.co/acme/123") == ("ats:lever", "no")
    assert kind("https://docs.google.com/a/acme.com/forms/d/e/1FA/viewform") == ("google_forms", "no")
    for bad in ("https://[bad/x", "https://acme.com]/x", "palabras sueltas"):
        assert external.classify(bad) == {"external_kind": "unknown", "site": "", "account_hint": "desconocido",
                                          "clean_url": None}
    # only LinkedIn's own redirect is unwrapped
    assert kind("https://evil.example/safety/go/?url=https%3A%2F%2Fforms.gle%2Fx") == ("company_site", "desconocido")


def test_nothing_to_classify():
    assert external.classify(None) is None
    assert external.classify("") is None
