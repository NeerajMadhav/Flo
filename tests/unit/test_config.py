# tests/unit/test_config.py
"""Settings validation — trailing slash strip + NLP model chains."""

from app.config import Settings, get_settings


def _base(**kwargs):
    return Settings(
        telegram_bot_token="1234567890:ABC",
        telegram_webhook_secret="x" * 32,
        openrouter_api_key="sk-test-key",
        api_secret_key="y" * 32,
        **kwargs,
    )


def test_backend_url_strips_slash():
    s = _base(backend_url="https://example.com/")
    assert s.backend_url == "https://example.com"


def test_get_settings_cached():
    a = get_settings()
    b = get_settings()
    assert a is b


def test_parse_model_chain_has_role_fallbacks_then_global():
    s = _base()
    chain = s.parse_model_chain()
    assert chain[0] == s.nlp_parse_model
    assert s.nlp_parse_fallback_1 in chain
    assert s.nlp_parse_fallback_2 in chain
    assert s.nlp_parse_fallback_3 in chain
    assert chain[-1] == s.nlp_global_fallback_model
    assert len(chain) == 5  # 4 role + global


def test_report_model_chain_has_role_fallbacks_then_global():
    s = _base()
    chain = s.report_model_chain()
    assert chain[0] == s.nlp_report_model
    assert s.nlp_report_fallback_1 in chain
    assert s.nlp_report_fallback_2 in chain
    assert s.nlp_report_fallback_3 in chain
    assert chain[-1] == s.nlp_global_fallback_model
    assert len(chain) == 5


def test_model_chain_dedupes_when_global_equals_role():
    s = _base(
        nlp_parse_model="a:free",
        nlp_parse_fallback_1="b:free",
        nlp_parse_fallback_2="c:free",
        nlp_parse_fallback_3="a:free",  # dup of primary
        nlp_global_fallback_model="b:free",  # dup of fallback_1
    )
    chain = s.parse_model_chain()
    assert chain == ["a:free", "b:free", "c:free"]
