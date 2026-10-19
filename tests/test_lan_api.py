from queue import Queue
from threading import Thread

from app import normalize_room_code, parse_imported_player, resolve_player_character
from lan_api import CharacterRequest, LanApiServer


ROOM_CODE = "ABCD23"
PLAYER = {
    "name": "Alice",
    "townsfolk": "Librarian",
    "outsider": "Recluse",
    "minion": "Baron",
    "demon": "Imp",
}


def make_server():
    submissions = Queue()
    server = LanApiServer(
        player_parser=parse_imported_player,
        roles_provider=lambda: {"townsfolk": ["Librarian"]},
        submissions=submissions,
        host="127.0.0.1",
        room_code=ROOM_CODE,
    )
    return server, submissions


def test_session_and_roles_require_room_code():
    server, _ = make_server()
    client = server.app.test_client()

    assert client.get("/session").status_code == 403
    assert client.get("/roles", headers={"X-Room-Code": ROOM_CODE}).json == {"roles": {"townsfolk": ["Librarian"]}}
    assert client.get("/session", headers={"X-Room-Code": ROOM_CODE}).json == {"active": True}


def test_character_endpoint_requires_room_and_player_tokens():
    server, _ = make_server()
    client = server.app.test_client()

    assert client.get("/character", headers={"X-Room-Code": ROOM_CODE}).status_code == 401
    assert client.get("/character", headers={"X-Player-Token": "token"}).status_code == 403


def test_character_endpoint_passes_token_request_to_wbg_queue():
    server, submissions = make_server()
    responses = []

    def request_character():
        with server.app.test_client() as client:
            responses.append(
                client.get(
                    "/character",
                    headers={"X-Room-Code": ROOM_CODE, "X-Player-Token": "player-token"},
                )
            )

    request_thread = Thread(target=request_character, daemon=True)
    request_thread.start()
    character_request = submissions.get(timeout=2)
    assert isinstance(character_request, CharacterRequest)
    assert character_request.player_token == "player-token"
    character_request.resolve(423, {"error": "Wait for the Storyteller to lock roles."})
    request_thread.join(timeout=2)

    assert not request_thread.is_alive()
    assert responses[0].status_code == 423
    assert "Wait for the Storyteller" in responses[0].json["error"]


def test_character_lookup_waits_for_locked_grimoire():
    status_code, response = resolve_player_character(
        "player-token",
        {"player-token": "Alice"},
        False,
        [("Alice", "townsfolk")],
        {"Alice": "Librarian"},
    )

    assert status_code == 423
    assert "wait" in response["error"].lower()


def test_character_lookup_returns_only_the_token_owners_assignment():
    status_code, response = resolve_player_character(
        "player-token",
        {"player-token": "Alice"},
        True,
        [("Alice", "townsfolk"), ("Bob", "demon")],
        {"Alice": "Librarian", "Bob": "Imp"},
        {"Alice"},
    )

    assert status_code == 200
    assert response == {"player": "Alice", "role": "townsfolk", "character": "Librarian", "evil": True}


def test_room_code_is_normalized_and_validated():
    assert normalize_room_code("  abc123  ") == "ABC123"
    for invalid_code in ("", "short", "bad-code", "waytoolongroomcode"):
        try:
            normalize_room_code(invalid_code)
        except ValueError:
            continue
        raise AssertionError(f"Expected invalid room code: {invalid_code!r}")


def test_player_client_page_prompts_for_room_code():
    server, _ = make_server()

    response = server.app.test_client().get("/")

    assert response.status_code == 200
    assert b"Room code" in response.data
    assert b"/session" in response.data
    assert b"/roles" in response.data
    assert b"/player" in response.data


def test_post_player_rejects_invalid_schema():
    server, submissions = make_server()
    client = server.app.test_client()

    response = client.post(
        "/player",
        json={"name": "Alice"},
        headers={"X-Room-Code": ROOM_CODE},
    )

    assert response.status_code == 400
    assert submissions.empty()


def test_post_player_returns_wbg_submission_result():
    server, submissions = make_server()
    responses = []

    def submit_player():
        with server.app.test_client() as client:
            responses.append(
                client.post(
                    "/player",
                    json=PLAYER,
                    headers={"X-Room-Code": ROOM_CODE},
                )
            )

    request_thread = Thread(target=submit_player, daemon=True)
    request_thread.start()
    submission = submissions.get(timeout=2)
    assert submission.player == parse_imported_player(PLAYER)
    submission.resolve(201, "Player preferences received.")
    request_thread.join(timeout=2)

    assert not request_thread.is_alive()
    assert responses[0].status_code == 201
    assert responses[0].json["message"] == "Player preferences received."
    assert responses[0].json["player_token"]