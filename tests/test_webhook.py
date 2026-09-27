"""tests/test_webhook.py — HMAC, dedup, límites, payloads inválidos.
El secreto es obligatorio aquí (a diferencia de Peluquería): toda petición
sin firmar debe rechazarse con 403 (design.md, 6.4)."""
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import make_payload, sign_body

client = TestClient(app)


def test_verify_webhook_ok(monkeypatch):
    monkeypatch.setattr("app.handlers.webhook.WHATSAPP_VERIFY_TOKEN", "tok123")
    resp = client.get("/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": "tok123", "hub.challenge": "42",
    })
    assert resp.status_code == 200
    assert resp.text == "42"


def test_verify_webhook_wrong_token(monkeypatch):
    monkeypatch.setattr("app.handlers.webhook.WHATSAPP_VERIFY_TOKEN", "tok123")
    resp = client.get("/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42",
    })
    assert resp.status_code == 403


def test_post_without_signature_rejected():
    body = make_payload("34600000000", text="hola")
    resp = client.post("/webhook", data=json.dumps(body),
                        headers={"Content-Type": "application/json"})
    assert resp.status_code == 403


def test_post_with_invalid_signature_rejected():
    body = make_payload("34600000000", text="hola")
    resp = client.post(
        "/webhook", data=json.dumps(body),
        headers={"Content-Type": "application/json",
                 "X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert resp.status_code == 403


def test_post_with_valid_signature_dispatches(monkeypatch):
    body = make_payload("34600000000", text="hola")
    raw, sig = sign_body(body)
    with patch("app.handlers.webhook.handle_message") as mocked:
        resp = client.post(
            "/webhook", data=raw,
            headers={"Content-Type": "application/json",
                     "X-Hub-Signature-256": sig},
        )
        assert resp.status_code == 200
        assert mocked.called


def test_post_non_json_content_type_ignored():
    resp = client.post("/webhook", data="not json",
                        headers={"Content-Type": "text/plain"})
    assert resp.status_code == 200


def test_post_oversized_payload_rejected():
    body = make_payload("34600000000", text="x" * 100)
    raw, sig = sign_body(body)
    # Fuerza el límite de tamaño simulando un cuerpo mayor a 64 KB.
    huge = raw + b" " * 70_000
    resp = client.post(
        "/webhook", data=huge,
        headers={"Content-Type": "application/json",
                 "X-Hub-Signature-256": sig},
    )
    assert resp.status_code == 413


def test_dedup_same_message_id_only_dispatched_once():
    from app.handlers import webhook as wh

    msg_id = "dup_test_1"
    body = {
        "entry": [{"changes": [{"value": {"messages": [
            {"from": "34600000099", "id": msg_id, "type": "text",
             "text": {"body": "hola"}},
        ]}}]}]
    }
    raw, sig = sign_body(body)
    with patch("app.handlers.webhook.handle_message") as mocked:
        client.post("/webhook", data=raw,
                     headers={"Content-Type": "application/json",
                              "X-Hub-Signature-256": sig})
        client.post("/webhook", data=raw,
                     headers={"Content-Type": "application/json",
                              "X-Hub-Signature-256": sig})
        assert mocked.call_count == 1
    wh._deduplicator.forget(msg_id)


# ── Portados de Peluquería (docs/rds_fase4_correcciones.md) ────────────────


def _post(body: dict):
    raw, sig = sign_body(body)
    return client.post(
        "/webhook", data=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )


def test_verify_webhook_wrong_mode(monkeypatch):
    monkeypatch.setattr("app.handlers.webhook.WHATSAPP_VERIFY_TOKEN", "tok123")
    resp = client.get("/webhook", params={
        "hub.mode": "unsubscribe", "hub.verify_token": "tok123", "hub.challenge": "42",
    })
    assert resp.status_code == 403


def test_verify_webhook_missing_params():
    resp = client.get("/webhook")
    assert resp.status_code == 403


def test_button_reply_dispatched(monkeypatch):
    body = make_payload("34600000201", interactive_id="menu_horarios")
    with patch("app.handlers.webhook.handle_message") as mocked:
        resp = _post(body)
        assert resp.status_code == 200
        mocked.assert_called_once_with(
            identifier="34600000201", phone="34600000201",
            text=None, interactive_id="menu_horarios",
        )


def test_list_reply_dispatched():
    body = make_payload("34600000202", interactive_id="dia:2026-03-23")
    with patch("app.handlers.webhook.handle_message") as mocked:
        _post(body)
        mocked.assert_called_once_with(
            identifier="34600000202", phone="34600000202",
            text=None, interactive_id="dia:2026-03-23",
        )


def test_unsupported_message_type_triggers_unknown_input():
    body = {
        "entry": [{"changes": [{"value": {"messages": [
            {"from": "34600000203", "id": "audio_1", "type": "audio"},
        ]}}]}]
    }
    with patch("app.handlers.webhook.handle_message") as mocked:
        resp = _post(body)
        assert resp.status_code == 200
        mocked.assert_called_once_with(
            identifier="34600000203", phone="34600000203",
            text="__unknown__", interactive_id=None,
        )


def test_two_messages_distinct_ids_both_dispatched():
    p2 = {
        "entry": [{"changes": [{"value": {"messages": [
            {"from": "34600000204", "id": "distinct_1", "type": "text",
             "text": {"body": "hola"}},
            {"from": "34600000204", "id": "distinct_2", "type": "text",
             "text": {"body": "adios"}},
        ]}}]}]
    }
    with patch("app.handlers.webhook.handle_message") as mocked:
        _post(p2)
        assert mocked.call_count == 2


def test_empty_body_returns_ok():
    resp = _post({})
    assert resp.status_code == 200


def test_invalid_json_returns_ok():
    raw = b"not json"
    import hashlib
    import hmac as _hmac

    from tests.conftest import TEST_APP_SECRET

    sig = "sha256=" + _hmac.new(
        TEST_APP_SECRET.encode("utf-8"), raw, hashlib.sha256
    ).hexdigest()
    resp = client.post("/webhook", data=raw,
                        headers={"Content-Type": "application/json",
                                 "X-Hub-Signature-256": sig})
    assert resp.status_code == 200


def test_no_messages_key_returns_ok():
    body = {"entry": [{"changes": [{"value": {}}]}]}
    with patch("app.handlers.webhook.handle_message") as mocked:
        resp = _post(body)
        assert resp.status_code == 200
        mocked.assert_not_called()


def test_empty_text_body_not_dispatched():
    body = make_payload("34600000205", text="   ")
    with patch("app.handlers.webhook.handle_message") as mocked:
        _post(body)
        mocked.assert_not_called()


def test_empty_interactive_id_not_dispatched():
    body = {
        "entry": [{"changes": [{"value": {"messages": [
            {"from": "34600000206", "id": "m1", "type": "interactive",
             "interactive": {"type": "button_reply", "button_reply": {"id": ""}}},
        ]}}]}]
    }
    with patch("app.handlers.webhook.handle_message") as mocked:
        _post(body)
        mocked.assert_not_called()


def test_missing_phone_not_dispatched():
    body = {
        "entry": [{"changes": [{"value": {"messages": [
            {"id": "m1", "type": "text", "text": {"body": "hi"}},
        ]}}]}]
    }
    with patch("app.handlers.webhook.handle_message") as mocked:
        resp = _post(body)
        assert resp.status_code == 200
        mocked.assert_not_called()


def test_multiple_entries_each_dispatched_once():
    body = {
        "entry": [
            {"changes": [{"value": {"messages": [
                {"from": "34600000207", "id": "multi_1", "type": "text",
                 "text": {"body": "Hola"}},
            ]}}]},
            {"changes": [{"value": {"messages": [
                {"from": "34600000208", "id": "multi_2", "type": "text",
                 "text": {"body": "Adios"}},
            ]}}]},
        ]
    }
    with patch("app.handlers.webhook.handle_message") as mocked:
        resp = _post(body)
        assert resp.status_code == 200
        assert mocked.call_count == 2


def test_multiple_changes_in_single_entry_each_dispatched_once():
    body = {
        "entry": [{"changes": [
            {"value": {"messages": [
                {"from": "34600000209", "id": "multi_3", "type": "text",
                 "text": {"body": "Hola"}},
            ]}},
            {"value": {"messages": [
                {"from": "34600000210", "id": "multi_4", "type": "text",
                 "text": {"body": "Adios"}},
            ]}},
        ]}]
    }
    with patch("app.handlers.webhook.handle_message") as mocked:
        resp = _post(body)
        assert resp.status_code == 200
        assert mocked.call_count == 2


def test_dedup_before_rate_limit_does_not_consume_budget():
    from app.handlers.webhook import ip_rate_limiter, phone_rate_limiter

    identifier = "34611112222"
    phone_rate_limiter.reset(identifier)
    try:
        first = make_payload(identifier, text="Hola")
        first["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = "rl_dup_1"
        with patch("app.handlers.webhook.handle_message") as mocked:
            _post(first)
            for _ in range(25):
                _post(first)
            second = make_payload(identifier, text="Adios")
            second["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = "rl_dup_2"
            resp = _post(second)
            assert resp.status_code == 200
            assert mocked.call_count == 2
    finally:
        phone_rate_limiter.reset(identifier)
        ip_rate_limiter.reset("testclient")


def test_rate_limited_message_redelivered_after_forget():
    from app.handlers.webhook import ip_rate_limiter, phone_rate_limiter

    identifier = "34633334444"
    phone_rate_limiter.reset(identifier)
    try:
        with patch("app.handlers.webhook.handle_message") as mocked:
            for i in range(20):
                payload = make_payload(identifier, text="x")
                msgs = payload["entry"][0]["changes"][0]["value"]["messages"]
                msgs[0]["id"] = f"rl_fill_{i}"
                _post(payload)
            assert mocked.call_count == 20

            rejected = make_payload(identifier, text="rejected")
            r_msgs = rejected["entry"][0]["changes"][0]["value"]["messages"]
            r_msgs[0]["id"] = "rl_rejected"
            _post(rejected)
            assert mocked.call_count == 20

            phone_rate_limiter.reset(identifier)
            _post(rejected)
            assert mocked.call_count == 21
    finally:
        phone_rate_limiter.reset(identifier)
        ip_rate_limiter.reset("testclient")


class TestWebhookBsuid:
    BSUID = "ES.1A2B3C4D5E6F"
    PHONE = "34600000211"

    def test_bsuid_in_user_id_phone_in_from(self):
        body = make_payload(self.PHONE, text="Hola", user_id=self.BSUID)
        body["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = "bsuid_001"
        with patch("app.handlers.webhook.handle_message") as mocked:
            resp = _post(body)
            assert resp.status_code == 200
            mocked.assert_called_once_with(
                identifier=self.BSUID, phone=self.PHONE,
                text="Hola", interactive_id=None,
            )

    def test_bsuid_in_both_user_id_and_from(self):
        body = make_payload(self.BSUID, text="Hola", user_id=self.BSUID)
        body["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = "bsuid_002"
        with patch("app.handlers.webhook.handle_message") as mocked:
            resp = _post(body)
            assert resp.status_code == 200
            mocked.assert_called_once_with(
                identifier=self.BSUID, phone=None,
                text="Hola", interactive_id=None,
            )

    def test_phone_only_no_user_id_backward_compat(self):
        body = make_payload(self.PHONE, text="Hola")
        body["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = "bsuid_003"
        with patch("app.handlers.webhook.handle_message") as mocked:
            resp = _post(body)
            assert resp.status_code == 200
            mocked.assert_called_once_with(
                identifier=self.PHONE, phone=self.PHONE,
                text="Hola", interactive_id=None,
            )

    def test_invalid_user_id_not_dispatched(self):
        body = make_payload(self.PHONE, text="Hola", user_id="!invalid!")
        body["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = "bsuid_004"
        with patch("app.handlers.webhook.handle_message") as mocked:
            resp = _post(body)
            assert resp.status_code == 200
            mocked.assert_not_called()

    def test_valid_bsuid_in_user_id_no_from(self):
        msg = {"id": "bsuid_005", "type": "text", "text": {"body": "Hola"},
               "user_id": self.BSUID}
        body = {"entry": [{"changes": [{"value": {"messages": [msg]}}]}]}
        with patch("app.handlers.webhook.handle_message") as mocked:
            resp = _post(body)
            assert resp.status_code == 200
            mocked.assert_called_once_with(
                identifier=self.BSUID, phone=None,
                text="Hola", interactive_id=None,
            )


def test_ip_rate_limit_returns_429():
    from app.handlers.webhook import ip_rate_limiter

    ip_rate_limiter.reset("testclient")
    try:
        with patch("app.handlers.webhook.handle_message"):
            for i in range(60):
                body = make_payload("34600000212", text="x")
                body["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = f"ip_{i}"
                resp = _post(body)
                assert resp.status_code == 200
            body = make_payload("34600000212", text="y")
            body["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = "ip_over"
            resp = _post(body)
            assert resp.status_code == 429
    finally:
        ip_rate_limiter.reset("testclient")


def test_phone_rate_limit_21st_not_dispatched():
    from app.handlers.webhook import ip_rate_limiter, phone_rate_limiter

    identifier = "34600000213"
    phone_rate_limiter.reset(identifier)
    try:
        with patch("app.handlers.webhook.handle_message") as mocked:
            for i in range(20):
                body = make_payload(identifier, text="x")
                msgs = body["entry"][0]["changes"][0]["value"]["messages"]
                msgs[0]["id"] = f"phl_{i}"
                _post(body)
            assert mocked.call_count == 20
            body = make_payload(identifier, text="rejected")
            body["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = "phl_over"
            resp = _post(body)
            assert resp.status_code == 200
            assert mocked.call_count == 20
    finally:
        phone_rate_limiter.reset(identifier)
        ip_rate_limiter.reset("testclient")


def test_interactive_id_too_long_not_dispatched():
    long_id = "x" * 300
    body = make_payload("34600000214", interactive_id=long_id)
    with patch("app.handlers.webhook.handle_message") as mocked:
        resp = _post(body)
        assert resp.status_code == 200
        mocked.assert_not_called()
