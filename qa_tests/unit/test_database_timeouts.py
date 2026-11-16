import pytest

from app.db.urls import connection_args, configure_statement_timeout
from unittest.mock import Mock

URL = 'postgresql+psycopg://unit@ep-unit.neon.tech/unit?sslmode=verify-full'


def test_dead_socket_detection_does_not_override_startup_options():
    args = connection_args(URL + '&options=-c%20search_path%3Dpublic')
    assert args['connect_timeout'] == 10
    assert args['tcp_user_timeout'] == 30000
    assert args['keepalives'] == 1 and args['keepalives_count'] == 3
    assert 'options' not in args
    assert not set(args) & {'host', 'hostaddr', 'sslmode', 'password', 'user', 'dbname'}


def test_migrations_have_socket_protection_without_a_ddl_deadline():
    assert 'options' not in connection_args(URL)


@pytest.mark.parametrize('timeout', [0, -1, True, 999, 600001, '30000'])
def test_invalid_runtime_deadlines_are_rejected(timeout):
    with pytest.raises(ValueError):
        configure_statement_timeout(Mock(), timeout)


def test_runtime_deadline_is_transaction_local_and_pooler_compatible(monkeypatch):
    from app.db import urls
    callbacks = []
    monkeypatch.setattr(urls.event, 'listens_for', lambda engine, name: lambda callback: callbacks.append((name, callback)) or callback)
    configure_statement_timeout(Mock(), 30000)
    name, callback = callbacks[0]
    assert name == 'begin'
    connection = Mock()
    callback(connection)
    connection.exec_driver_sql.assert_called_once_with('SET LOCAL statement_timeout = 30000')
