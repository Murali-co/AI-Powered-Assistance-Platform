import pytest


@pytest.mark.parametrize('kind', ['verification', 'reset'])
def test_delivery_failure_never_logs_link_token_or_recipient(monkeypatch, caplog, kind):
    from app.services.email_service import EmailService
    monkeypatch.setenv('TESTING', 'false')
    monkeypatch.setattr(EmailService, 'send_email', lambda **kwargs: False)
    method = EmailService.send_verification_email if kind == 'verification' else EmailService.send_password_reset_email
    assert method('private-address@example.com', 'Private Name', 'http://localhost/verify?token=private-secret-token') is False
    assert 'private-secret-token' not in caplog.text
    assert 'private-address' not in caplog.text
    assert 'Private Name' not in caplog.text
    assert EmailService._last_sent_verification_token is None
    assert EmailService._last_sent_password_reset_token is None
