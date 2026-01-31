from easysql_api.services.session_store import SessionStore


def test_session_store_add_message_and_get():
    store = SessionStore()
    session = store.create("session-1")
    assert session is not None

    message_id = "msg-1"
    store.add_message(
        session.session_id,
        message_id=message_id,
        thread_id="thread-1",
        role="user",
        content="hello",
        parent_id=None,
    )

    message = store.get_message(message_id)
    assert message is not None
    assert message.message_id == message_id
    assert message.thread_id == "thread-1"
