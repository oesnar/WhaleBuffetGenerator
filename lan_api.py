import secrets
import socket
from queue import Queue
from threading import Event, Thread

from flask import Flask, jsonify, render_template, request
from werkzeug.serving import make_server


class PlayerSubmission:
    def __init__(self, player):
        self.player = player
        self.event = Event()
        self.status_code = None
        self.message = ""

    def resolve(self, status_code, message):
        self.status_code = status_code
        self.message = message
        self.event.set()


class LanApiServer:
    def __init__(self, player_parser, roles_provider, submissions, host="0.0.0.0", port=8765, room_code=None):
        self.host = host
        self.requested_port = port
        self.port = port
        self.room_code = room_code or "".join(secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(6))
        self.player_parser = player_parser
        self.roles_provider = roles_provider
        self.submissions = submissions
        self._server = None
        self._thread = None
        self.app = Flask(__name__)
        self._register_routes()

    def _register_routes(self):
        @self.app.get("/")
        def get_player_client():
            return render_template("player_client.html")

        @self.app.get("/session")
        def get_session():
            if not self._authorized():
                return jsonify(error="Invalid room code."), 403
            return jsonify(active=True)

        @self.app.get("/roles")
        def get_roles():
            if not self._authorized():
                return jsonify(error="Invalid room code."), 403
            return jsonify(roles=self.roles_provider())

        @self.app.post("/player")
        def post_player():
            if not self._authorized():
                return jsonify(error="Invalid room code."), 403

            try:
                player = self.player_parser(request.get_json(silent=True))
            except ValueError as exc:
                return jsonify(error=str(exc)), 400

            submission = PlayerSubmission(player)
            self.submissions.put(submission)
            if not submission.event.wait(timeout=10):
                return jsonify(error="WBG did not process the submission in time."), 503
            return jsonify(message=submission.message), submission.status_code

    def _authorized(self):
        supplied_code = request.headers.get("X-Room-Code", "").strip().upper()
        return secrets.compare_digest(supplied_code, self.room_code)

    def start(self):
        if self._server is not None:
            return
        self._server = make_server(self.host, self.requested_port, self.app, threaded=True)
        self.port = self._server.server_port
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None


def get_lan_ipv4_address():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()
