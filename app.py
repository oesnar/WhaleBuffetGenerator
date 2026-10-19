import os
import json
from queue import Empty, Queue
import random
import re
import subprocess
import sys
from lan_api import LanApiServer, get_lan_ipv4_address
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from tkinter import filedialog
from urllib import request

from whalebuffetgenerator import assign_roles, build_role_counts
from whalebuffetgenerator.logic import ROLE_EFFECTS, ROLE_OPTIONS, ROLE_ORDER

ROLE_COLORS = {
    "townsfolk": "#164e9c",
    "outsider": "#3d7ab5",
    "minion": "#b14b4b",
    "demon": "#9d1515",
}
SUMMONER_EFFECT = "No Demon"
BOUNTY_HUNTER_EFFECT = "Turns a Townsfolk evil"
LIL_MONSTA_EFFECT = "Becomes a Minion"


def parse_imported_player(data):
    fields = {"name", *ROLE_ORDER}
    if not isinstance(data, dict):
        raise ValueError("The JSON file must contain one player object.")

    missing = fields - data.keys()
    unexpected = data.keys() - fields
    if missing or unexpected:
        details = []
        if missing:
            details.append("missing fields: " + ", ".join(sorted(missing)))
        if unexpected:
            details.append("unexpected fields: " + ", ".join(sorted(unexpected)))
        raise ValueError("Expected exactly name, townsfolk, outsider, minion, and demon (" + "; ".join(details) + ").")

    if any(not isinstance(data[field], str) for field in fields):
        raise ValueError("All five fields must contain text values.")

    name = data["name"].strip()
    if not name:
        raise ValueError("Player name cannot be empty.")

    return {
        "name": name,
        "preferred_roles": {role: data[role].strip() for role in ROLE_ORDER},
    }


def normalize_room_code(room_code):
    normalized = str(room_code).strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{6,12}", normalized):
        raise ValueError("Room codes must be 6 to 12 letters or numbers.")
    return normalized


def get_grimoire_storage_path():
    if os.name == "nt":
        data_root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        data_root = Path.home() / "Library" / "Application Support"
    else:
        data_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return data_root / "WhaleBuffetGenerator" / "grimoire.json"


def build_remembered_grimoire(players):
    return {
        "version": 1,
        "players": [
            {
                "name": player["name"],
                "preferred_roles": {role: player.get("preferred_roles", {}).get(role, "") for role in ROLE_ORDER},
            }
            for player in players
        ],
    }


def parse_remembered_grimoire(data):
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("players"), list):
        raise ValueError("Saved Grimoire data has an unsupported format.")

    players = []
    names = set()
    for saved_player in data["players"]:
        if not isinstance(saved_player, dict) or set(saved_player) != {"name", "preferred_roles"}:
            raise ValueError("Saved player data has an invalid format.")
        preferred_roles = saved_player["preferred_roles"]
        if not isinstance(preferred_roles, dict) or set(preferred_roles) != set(ROLE_ORDER):
            raise ValueError("Saved player preferences must include all four role types.")
        player = parse_imported_player({"name": saved_player["name"], **preferred_roles})
        key = player["name"].casefold()
        if key in names:
            raise ValueError("Saved Grimoire contains duplicate player names.")
        names.add(key)
        players.append(player)
    return players


def build_available_dummy_name(existing_names, candidate_names=None):
    names = list(candidate_names) if candidate_names is not None else [
        "Barnacle Bess",
        "Wobblewump",
        "Mothball Mabel",
        "Puddle Pockets",
        "Sir Nibblenips",
        "Gizmo Gert",
        "Captain Crumble",
        "Noodle Nance",
        "Biscuit Bert",
        "Tallow Toot",
    ]
    names = list(dict.fromkeys(names))
    used_names = set(existing_names)
    available = [name for name in names if name not in used_names]
    if available:
        return random.choice(available)

    if names:
        base_name = names[0]
        for suffix in range(2, 1000):
            candidate = f"{base_name} {suffix}"
            if candidate not in used_names:
                return candidate

    for suffix in range(1, 1000):
        candidate = f"Dummy Player {suffix}"
        if candidate not in used_names:
            return candidate

    return "Dummy Player"


def assign_roles_for_counts(players, role_counts):
    player_list = [
        {"name": player["name"], "preferred_roles": player.get("preferred_roles", {})}
        for player in players
    ]
    assignments = []

    for role_name in ROLE_ORDER:
        count = role_counts.get(role_name, 0)
        if count <= 0:
            continue

        available = [player for player in player_list if player["name"] not in {name for name, _ in assignments}]
        preferred_players = [player for player in available if player["preferred_roles"].get(role_name)]
        pool = preferred_players if preferred_players else available
        chosen = random.sample(pool, k=min(count, len(pool))) if pool else []
        for player in chosen:
            assignments.append((player["name"], role_name))

        assigned_names = {name for name, _ in assignments}
        player_list = [player for player in player_list if player["name"] not in assigned_names]

    assignments.sort(key=lambda item: ROLE_ORDER.index(item[1]))
    return assignments


def parse_distribution_effect(effect_text):
    if not isinstance(effect_text, str):
        return None

    match = re.search(r"\+(\d+)\s+(outsider|outsiders|townsfolk|townsfolks|minion|minions|demon|demons)", effect_text.strip().lower())
    if not match:
        return None

    amount = int(match.group(1))
    raw_target = match.group(2).lower().rstrip("s")
    if raw_target not in {"outsider", "townsfolk", "minion", "demon"}:
        return None
    return amount, raw_target


def format_pin_display(is_pinned):
    return "📌" if is_pinned else ""


def format_assignment_export(rows):
    headers = ("#", "Player", "Character", "Effect", "Pin")
    lines = ["\t".join(headers)]
    lines.extend("\t".join(str(value) for value in row) for row in rows)
    return "\n".join(lines)


def format_effect_display(effect_text, is_consumed=False):
    if not effect_text:
        return ""
    stripped = str(effect_text).strip()
    if not stripped:
        return ""
    return f"{stripped} ✓" if is_consumed else stripped


def build_assignment_row_tags(role, is_pinned=False, effect_applied=False, effect_targeted=False, effect_clickable=False, is_evil=False):
    if is_evil and effect_targeted:
        return ("evil_targeted",)

    tags = [role]
    if is_pinned:
        tags.append("pinned")
    if effect_applied:
        tags.append("effect_applied")
    elif effect_targeted:
        tags.append("effect_targeted")
    if effect_clickable and not effect_applied:
        tags.append("effect_clickable")
    return tuple(tags)


def describe_effect_candidate(player_name, target_role, players_by_name, character_names):
    player = players_by_name.get(player_name, {})
    preferred_roles = player.get("preferred_roles", {})
    role_options = ROLE_OPTIONS.get(target_role, [])
    new_character = preferred_roles.get(target_role) or (role_options[0] if role_options else target_role.title())
    current_character = character_names.get(player_name, "Unknown")
    return player_name, current_character, new_character


def collect_summoner_candidates(assignments, unavailable_players=None, excluded_player=None):
    unavailable_players = set(unavailable_players or [])
    return [
        name
        for name, role in assignments
        if role == "demon"
        and name not in unavailable_players
        and name != excluded_player
    ]


def collect_bounty_hunter_candidates(assignments, unavailable_players=None, excluded_player=None):
    unavailable_players = set(unavailable_players or [])
    return [
        name
        for name, role in assignments
        if role == "townsfolk"
        and name not in unavailable_players
        and name != excluded_player
    ]


def apply_summoner_effect(assignments, selected_player):
    if not any(name == selected_player and role == "demon" for name, role in assignments):
        return list(assignments)

    updated = [
        (name, "townsfolk" if name == selected_player and role == "demon" else role)
        for name, role in assignments
    ]
    updated.sort(key=lambda item: ROLE_ORDER.index(item[1]))
    return updated


def is_lil_monsta_character(character_name):
    return re.sub(r"[^a-z]", "", str(character_name).casefold()) == "lilmonsta"


def format_lil_monsta_character(lil_monsta_character, minion_character):
    return f"{lil_monsta_character} ({minion_character})"


def apply_lil_monsta_effect(assignments, player_name):
    if not any(name == player_name and role == "demon" for name, role in assignments):
        return list(assignments)

    updated = [
        (name, "minion" if name == player_name and role == "demon" else role)
        for name, role in assignments
    ]
    updated.sort(key=lambda item: ROLE_ORDER.index(item[1]))
    return updated


def collect_effect_candidates(assignments, effect_text, role_effects=None, applied_effect_players=None, character_names=None, excluded_player=None):
    parsed = parse_distribution_effect(effect_text)
    if parsed is None:
        return []

    amount, target_role = parsed
    if amount <= 0:
        return []

    source_role = "townsfolk" if target_role == "outsider" else "outsider"
    if source_role == target_role:
        return []

    applied_effect_players = set(applied_effect_players or [])
    candidates = []

    for name, role in assignments:
        if role != source_role:
            continue
        if name in applied_effect_players:
            continue
        if excluded_player is not None and name == excluded_player:
            continue
        candidates.append(name)

    return candidates


def apply_distribution_effect(assignments, effect_text, selected_players=None):
    parsed = parse_distribution_effect(effect_text)
    if parsed is None:
        return list(assignments)

    amount, target_role = parsed
    if not assignments:
        return []

    if target_role == "outsider":
        source_role = "townsfolk"
    elif target_role == "townsfolk":
        source_role = "outsider"
    else:
        return list(assignments)

    if source_role == target_role:
        return list(assignments)

    current = {name: role for name, role in assignments}
    eligible = [name for name, role in assignments if role == source_role]

    if selected_players is not None:
        chosen = []
        for player_name in selected_players:
            if player_name in current and current[player_name] == source_role:
                chosen.append(player_name)
        chosen = chosen[:amount]
    else:
        chosen = eligible[:amount]

    if not chosen:
        return list(assignments)

    updated = []
    for name, role in assignments:
        if name in chosen:
            updated.append((name, target_role))
        else:
            updated.append((name, role))

    updated.sort(key=lambda item: ROLE_ORDER.index(item[1]))
    return updated


def apply_pinned_assignments(players, previous_assignments, pinned_assignments):
    if not previous_assignments:
        return []

    current_names = {player["name"] for player in players}
    prior_names = {name for name, _ in previous_assignments}
    if current_names != prior_names:
        return []

    pinned = {
        name: role
        for name, role in previous_assignments
        if name in pinned_assignments and pinned_assignments[name] == role
    }

    if not pinned:
        return list(previous_assignments)

    total_counts = build_role_counts(len(players))
    remaining_counts = total_counts.copy()
    for name, role in pinned.items():
        remaining_counts[role] = max(0, remaining_counts.get(role, 0) - 1)

    remaining_players = [player for player in players if player["name"] not in pinned]
    remaining_assignments = assign_roles_for_counts(remaining_players, remaining_counts)

    final = [None] * len(previous_assignments)
    for index, (name, role) in enumerate(previous_assignments):
        if name in pinned:
            final[index] = (name, pinned[name])

    remaining_index = 0
    for index in range(len(final)):
        if final[index] is None:
            final[index] = remaining_assignments[remaining_index]
            remaining_index += 1

    return final


def preserve_pins_for_assignments(current_pins, assignments):
    if not current_pins:
        return {}

    next_pins = {}
    assignment_roles = {name: role for name, role in assignments}
    for name, role in current_pins.items():
        if name in assignment_roles and assignment_roles[name] == role:
            next_pins[name] = role
    return next_pins


class WhaleBuffetApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Whale Buffet Role Randomizer")
        self.geometry("920x650")
        self.minsize(860, 620)
        self.configure_favicon()
        self.dark_mode = False
        self.dark_mode_var = tk.BooleanVar(value=False)
        self.remember_grimoire_var = tk.BooleanVar(value=False)
        self.remember_grimoire_path = get_grimoire_storage_path()
        self.remember_grimoire_load_warning = ""
        self.grimoire_locked = False
        self.lan_submissions = Queue()
        self.lan_session_server = None
        self.style = ttk.Style(self)

        self._build_menu_bar()
        self.protocol("WM_DELETE_WINDOW", self.close_app)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(self, padding=(16, 16, 16, 16))
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=0)
        main_frame.rowconfigure(2, weight=1)
        main_frame.rowconfigure(3, weight=0)

        players_frame = ttk.LabelFrame(main_frame, text="Players", padding=(12, 10))
        players_frame.grid(row=0, column=0, sticky="nsew")
        players_frame.columnconfigure(0, weight=1)
        players_frame.rowconfigure(0, weight=1)
        players_frame.rowconfigure(1, weight=0)

        self.players = [
            {
                "name": "Alice",
                "preferred_roles": {
                    "townsfolk": "Librarian",
                    "outsider": "Recluse",
                    "minion": "Spy",
                    "demon": "Imp",
                },
            },
            {
                "name": "Bob",
                "preferred_roles": {
                    "townsfolk": "Washerwoman",
                    "outsider": "Drunk",
                    "minion": "Poisoner",
                    "demon": "Imp",
                },
            },
            {
                "name": "Charlie",
                "preferred_roles": {
                    "townsfolk": "Fortune Teller",
                    "outsider": "Recluse",
                    "minion": "Summoner",
                    "demon": "Pukka",
                },
            },
            {
                "name": "Dora",
                "preferred_roles": {
                    "townsfolk": "Balloonist",
                    "outsider": "Drunk",
                    "minion": "Baron",
                    "demon": "Fang Gu",
                },
            },
            {
                "name": "Evan",
                "preferred_roles": {
                    "townsfolk": "Balloonist",
                    "outsider": "Drunk",
                    "minion": "Baron",
                    "demon": "Fang Gu",
                },
            },
        ]
        self._load_remembered_grimoire()
        self.assignment_rows = []
        self.assignment_pins = {}
        self.base_assignment_rows = []
        self.assignment_display_roles = {}
        self.applied_effect_players = set()
        self.effect_source_players = set()
        self.effect_target_players = set()
        self.evil_players = set()
        self.lil_monsta_minion_players = {}

        self.player_table = ttk.Treeview(
            players_frame,
            columns=("row", "name", "townsfolk", "outsider", "minion", "demon"),
            show="headings",
            height=8,
        )
        self.player_table.heading("row", text="#")
        self.player_table.heading("name", text="Player")
        self.player_table.heading("townsfolk", text="Townsfolk")
        self.player_table.heading("outsider", text="Outsider")
        self.player_table.heading("minion", text="Minion")
        self.player_table.heading("demon", text="Demon")
        self.player_table.column("row", width=48, anchor="center", stretch=False)
        self.player_table.column("name", width=180, anchor="w")
        for role in ("townsfolk", "outsider", "minion", "demon"):
            self.player_table.column(role, width=130, anchor="center")

        self.player_scroll = ttk.Scrollbar(players_frame, orient="vertical", command=self.player_table.yview)
        self.player_scroll.grid(row=0, column=1, sticky="ns")
        self.player_table.configure(yscrollcommand=self.player_scroll.set)
        self.player_table.grid(row=0, column=0, sticky="nsew")
        self.player_table.configure(selectmode="browse")

        self.style.configure("Minimal.Vertical.TScrollbar", background="#c7d1df", troughcolor="#eef3ff", borderwidth=0, arrowcolor="#6b7c98")
        self.style.map("Minimal.Vertical.TScrollbar", background=[("active", "#b5c4d6")], arrowcolor=[("active", "#4d5b74")])
        self.player_scroll.configure(style="Minimal.Vertical.TScrollbar")

        self.refresh_player_table()

        buttons = ttk.Frame(players_frame)
        buttons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        buttons.columnconfigure(2, weight=1)
        buttons.columnconfigure(3, weight=1)

        self.player_action_buttons = [
            ttk.Button(buttons, text="Add player", command=self.add_player),
            ttk.Button(buttons, text="Edit player", command=self.edit_player),
            ttk.Button(buttons, text="Remove player", command=self.remove_player),
            ttk.Button(buttons, text="Clear players", command=self.clear_players),
        ]
        for index, button in enumerate(self.player_action_buttons):
            left_pad = 0 if index == 0 else 6
            right_pad = 0 if index == 3 else 6
            button.grid(row=0, column=index, sticky="ew", padx=(left_pad, right_pad))

        controls = ttk.Frame(main_frame)
        controls.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        controls.columnconfigure(0, weight=0)
        controls.columnconfigure(1, weight=0)
        controls.columnconfigure(2, weight=0)
        controls.columnconfigure(3, weight=0)
        controls.columnconfigure(4, weight=1)

        self.generate_button = ttk.Button(controls, text="Generate roles", command=self.generate_roles)
        self.generate_button.grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.pin_button = ttk.Button(controls, text="Pin selected", command=self.toggle_selected_assignment_pin)
        self.pin_button.grid(row=0, column=1, sticky="w", padx=(0, 8))

        self.revert_effects_button = ttk.Button(controls, text="Revert effects", command=self.revert_assignment_effects)
        self.revert_effects_button.grid(row=0, column=2, sticky="w", padx=(0, 12))

        self.status_var = tk.StringVar(value=self.remember_grimoire_load_warning)
        self.status_label = ttk.Label(controls, textvariable=self.status_var, foreground="#0b5d1d")
        self.status_label.grid(row=0, column=4, sticky="w")

        output_frame = ttk.LabelFrame(main_frame, text="Assignments", padding=(12, 10))
        output_frame.grid(row=2, column=0, sticky="nsew")
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)

        self.output = ttk.Treeview(
            output_frame,
            columns=("row", "player", "character", "effect", "pin"),
            show="headings",
            height=7,
        )
        self.output.heading("row", text="#")
        self.output.heading("player", text="Player")
        self.output.heading("character", text="Character")
        self.output.heading("effect", text="Effect")
        self.output.heading("pin", text="Pin")
        self.output.column("row", width=52, anchor="center", stretch=False)
        self.output.column("player", width=180, anchor="center")
        self.output.column("character", width=220, anchor="center")
        self.output.column("effect", width=140, anchor="center")
        self.output.column("pin", width=56, anchor="center", stretch=False)

        self.output_scroll = ttk.Scrollbar(output_frame, orient="vertical", command=self.output.yview)
        self.output_scroll.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=self.output_scroll.set)
        self.output.grid(row=0, column=0, sticky="nsew")
        self.output.tag_configure("townsfolk", foreground=ROLE_COLORS["townsfolk"], font=("Segoe UI", 10, "bold"))
        self.output.tag_configure("outsider", foreground=ROLE_COLORS["outsider"], font=("Segoe UI", 10, "bold"))
        self.output.tag_configure("minion", foreground=ROLE_COLORS["minion"], font=("Segoe UI", 10, "bold"))
        self.output.tag_configure("demon", foreground=ROLE_COLORS["demon"], font=("Segoe UI", 10, "bold"))
        self.output.tag_configure("effect_clickable", foreground="#1d4fb9", font=("Segoe UI", 10, "bold"))
        self.output.tag_configure("effect_applied", foreground="#1d2430", font=("Segoe UI", 10, "bold", "overstrike"))
        self.output.tag_configure("effect_targeted", background="#e9defd", foreground="#3f2d5a", font=("Segoe UI", 10, "bold"))
        self.output.tag_configure("evil_targeted", background="#e9defd", foreground=ROLE_COLORS["minion"], font=("Segoe UI", 10, "bold"))
        self.output_scroll.configure(style="Minimal.Vertical.TScrollbar")
        self.output.bind("<Double-Button-1>", self.toggle_selected_assignment_pin)
        self.output.bind("<ButtonRelease-1>", self._handle_effect_click)

        footer = ttk.Frame(main_frame)
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        footer.columnconfigure(0, weight=1)
        self.lock_button = ttk.Button(footer, text="Lock grimoire", command=self.toggle_grimoire_lock, style="Botc.TButton")
        self.lock_button.grid(row=0, column=1, sticky="e", padx=(0, 8))
        self.export_button = ttk.Button(footer, text="Export assignments", command=self.export_assignments, style="Botc.TButton")
        self.export_button.grid(row=0, column=2, sticky="e")

        self.output.tag_configure("outsider", foreground=ROLE_COLORS["outsider"], font=("Segoe UI", 10, "bold"))
        self.output.tag_configure("minion", foreground=ROLE_COLORS["minion"], font=("Segoe UI", 10, "bold"))
        self.output.tag_configure("demon", foreground=ROLE_COLORS["demon"], font=("Segoe UI", 10, "bold"))

        self.apply_theme()
        self.after(100, self._process_lan_submissions)

    def _build_menu_bar(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Refresh", command=self.refresh_app)
        file_menu.add_command(label="Close", command=self.destroy)
        file_menu.add_separator()
        file_menu.add_checkbutton(
            label="Enable dark mode",
            variable=self.dark_mode_var,
            command=self.toggle_theme,
        )
        file_menu.add_checkbutton(
            label="Remember Grimoire",
            variable=self.remember_grimoire_var,
            command=self.toggle_remember_grimoire,
        )
        menubar.add_cascade(label="File", menu=file_menu)
        self.file_menu = file_menu

        manage_menu = tk.Menu(menubar, tearoff=0)
        manage_menu.add_command(label="Add dummy", command=self.add_dummy_player)
        manage_menu.add_command(label="Add player", command=self.add_player)
        manage_menu.add_command(label="Import player", command=self.import_player)
        manage_menu.add_command(label="Edit player", command=self.edit_player)
        manage_menu.add_command(label="Remove player", command=self.remove_player)
        manage_menu.add_command(label="Clear players", command=self.clear_players)
        menubar.add_cascade(label="Manage", menu=manage_menu)
        self.manage_menu = manage_menu

        session_menu = tk.Menu(menubar, tearoff=0)
        session_menu.add_command(label="Start LAN session", command=self.start_lan_session)
        session_menu.add_command(label="Show room details", command=self.show_lan_session_details, state="disabled")
        session_menu.add_command(label="Stop LAN session", command=self.stop_lan_session, state="disabled")
        menubar.add_cascade(label="LAN Session", menu=session_menu)
        self.session_menu = session_menu

    def _detect_system_theme(self):
        return False

    def refresh_app(self):
        try:
            subprocess.Popen([sys.executable, __file__], cwd=str(Path(__file__).resolve().parent))
        except Exception:
            pass
        finally:
            self.close_app()

    def start_lan_session(self):
        if self.lan_session_server is not None:
            self.show_lan_session_details()
            return

        room_code = simpledialog.askstring(
            "Start LAN session",
            "Choose a room code (6 to 12 letters or numbers):",
            parent=self,
        )
        if room_code is None:
            return
        try:
            room_code = normalize_room_code(room_code)
        except ValueError as exc:
            messagebox.showerror("Invalid room code", str(exc), parent=self)
            return

        self.lan_session_server = LanApiServer(
            player_parser=parse_imported_player,
            roles_provider=lambda: ROLE_OPTIONS,
            submissions=self.lan_submissions,
            room_code=room_code,
        )
        try:
            self.lan_session_server.start()
        except OSError as exc:
            self.lan_session_server = None
            messagebox.showerror("LAN Session", f"Could not start the LAN session: {exc}", parent=self)
            return

        self.session_menu.entryconfigure(0, state="disabled")
        self.session_menu.entryconfigure(1, state="normal")
        self.session_menu.entryconfigure(2, state="normal")
        self.show_lan_session_details()

    def show_lan_session_details(self):
        if self.lan_session_server is None:
            return
        address = get_lan_ipv4_address()
        messagebox.showinfo(
            "LAN Session",
            f"Players can connect to WBG at:\nhttp://{address}:{self.lan_session_server.port}\n\n"
            f"Room code: {self.lan_session_server.room_code}\n\n"
            "API endpoints: GET /session, GET /roles, POST /player",
            parent=self,
        )

    def stop_lan_session(self):
        if self.lan_session_server is None:
            return
        self.lan_session_server.stop()
        self.lan_session_server = None
        self.session_menu.entryconfigure(0, state="normal")
        self.session_menu.entryconfigure(1, state="disabled")
        self.session_menu.entryconfigure(2, state="disabled")
        self.status_var.set("LAN session stopped.")

    def close_app(self):
        self.stop_lan_session()
        self.destroy()

    def _process_lan_submissions(self):
        while True:
            try:
                submission = self.lan_submissions.get_nowait()
            except Empty:
                break

            if self.lan_session_server is None:
                submission.resolve(503, "LAN session is no longer active.")
                continue
            if self.grimoire_locked:
                submission.resolve(423, "The Storyteller has locked the grimoire.")
                continue

            player = submission.player
            existing_names = {existing["name"].casefold() for existing in self.players}
            if player["name"].casefold() in existing_names:
                submission.resolve(409, "A player with this name already exists.")
                continue

            self.players.append(player)
            self.refresh_player_table()
            self.status_var.set(f"Received preferences from {player['name']}.")
            self._save_remembered_grimoire()
            submission.resolve(201, "Player preferences received.")

        if self.winfo_exists():
            self.after(100, self._process_lan_submissions)

    def add_dummy_player(self):
        if self.grimoire_locked:
            return
        used_names = {player["name"] for player in self.players}
        random_name = build_available_dummy_name(used_names)
        preferred_roles = {}
        for role in ROLE_ORDER:
            options = ROLE_OPTIONS.get(role, [])
            preferred_roles[role] = random.choice(options) if options else ""

        self.players.append({"name": random_name, "preferred_roles": preferred_roles})
        self.refresh_player_table()
        self.status_var.set(f"Added dummy player {random_name}.")
        self._save_remembered_grimoire()

    def configure_favicon(self):
        icon_dir = Path(__file__).resolve().parent / "assets"
        icon_dir.mkdir(exist_ok=True)
        icon_path = icon_dir / "botc_icon.ico"

        if not icon_path.exists():
            try:
                from PIL import Image
                import io

                image_data = request.urlopen("https://wiki.bloodontheclocktower.com/images/9/92/Icon_lycanthrope.png", timeout=15).read()
                image = Image.open(io.BytesIO(image_data))
                image.save(icon_path, format="ICO")
            except Exception:
                return

        try:
            self.iconbitmap(str(icon_path))
        except Exception:
            pass

    def apply_theme(self):
        if self.dark_mode:
            bg = "#101822"
            panel = "#1b2733"
            panel_alt = "#243244"
            fg = "#edf3ff"
            muted = "#a7b6d6"
            accent = "#b71f2d"
            border = "#3d4d63"
            title_bar = "#111827"
            title_bar_button = "#1a2230"
            status_green = "#9ef0b6"
        else:
            bg = "#f4f6fb"
            panel = "#ffffff"
            panel_alt = "#eef3ff"
            fg = "#1d2430"
            muted = "#5f6b7b"
            accent = "#4c7ef3"
            border = "#d9e0ec"
            title_bar = "#edf3ff"
            title_bar_button = "#eef3ff"
            status_green = "#0b5d1d"

        self.configure(bg=bg)
        try:
            self.update_idletasks()
            if self.dark_mode:
                self.wm_attributes("-darkmode", True)
            else:
                self.wm_attributes("-darkmode", False)
        except Exception:
            pass

        self.style.theme_use("clam")
        self.style.configure("Botc.TFrame", background=bg)
        self.style.configure("Botc.TLabel", background=bg, foreground=fg)
        self.style.configure("Botc.TLabelframe", background=bg)
        self.style.configure("Botc.TLabelframe.Label", background=bg, foreground=fg)
        self.style.configure("Botc.TButton", background=panel_alt, foreground=fg, borderwidth=1, relief="flat")
        self.style.map("Botc.TButton", background=[("active", panel), ("pressed", panel)], foreground=[("active", fg), ("pressed", fg)])
        self.style.configure("Botc.Treeview", background=panel, fieldbackground=panel, foreground=fg, rowheight=28)
        self.style.map("Botc.Treeview", background=[("selected", panel_alt)], foreground=[("selected", fg)])
        self.style.configure("Botc.Treeview.Heading", background=panel_alt, foreground=fg, relief="flat")
        self.style.map("Botc.Treeview.Heading", background=[("active", border)], foreground=[("active", fg)])
        self.style.configure("Minimal.Vertical.TScrollbar", background="#c7d1df", troughcolor=panel, borderwidth=0, arrowcolor=fg)
        self.style.map("Minimal.Vertical.TScrollbar", background=[("active", "#b5c4d6")], arrowcolor=[("active", fg)])
        self.style.configure("Botc.TEntry", fieldbackground=panel, foreground=fg, background=panel)
        self.style.configure("Botc.TCombobox", fieldbackground=panel, foreground=fg, background=panel)

        if hasattr(self, "generate_button"):
            self.generate_button.configure(style="Botc.TButton")
        if hasattr(self, "pin_button"):
            self.pin_button.configure(style="Botc.TButton")
        if hasattr(self, "status_label"):
            self.status_label.configure(foreground=status_green)
        if hasattr(self, "player_table"):
            self.player_table.configure(style="Botc.Treeview")
        if hasattr(self, "output"):
            self.output.configure(style="Botc.Treeview")
            self.output.tag_configure("townsfolk", foreground=ROLE_COLORS["townsfolk"], font=("Segoe UI", 10, "bold"))
            self.output.tag_configure("outsider", foreground=ROLE_COLORS["outsider"], font=("Segoe UI", 10, "bold"))
            self.output.tag_configure("minion", foreground=ROLE_COLORS["minion"], font=("Segoe UI", 10, "bold"))
            self.output.tag_configure("demon", foreground=ROLE_COLORS["demon"], font=("Segoe UI", 10, "bold"))
            self.output.tag_configure("effect_clickable", foreground="#1d4fb9", font=("Segoe UI", 10, "bold"))
            self.output.tag_configure("effect_applied", foreground="#1d2430", font=("Segoe UI", 10, "bold", "overstrike"))
            self.output.tag_configure("effect_targeted", background="#e9defd", foreground="#3f2d5a", font=("Segoe UI", 10, "bold"))
            self.output.tag_configure("evil_targeted", background="#e9defd", foreground=ROLE_COLORS["minion"], font=("Segoe UI", 10, "bold"))

        for widget in self.winfo_children():
            try:
                if isinstance(widget, tk.Frame):
                    widget.configure(bg=bg)
                if isinstance(widget, tk.LabelFrame):
                    widget.configure(bg=bg, fg=fg)
                if isinstance(widget, tk.Text):
                    widget.configure(background=panel, foreground=fg, insertbackground=fg)
                if isinstance(widget, tk.Entry):
                    widget.configure(background=panel, foreground=fg, insertbackground=fg)
                if isinstance(widget, tk.Label):
                    widget.configure(background=bg, foreground=fg)
            except Exception:
                pass

    def toggle_theme(self):
        self.dark_mode = bool(self.dark_mode_var.get())
        self.apply_theme()

    def _load_remembered_grimoire(self):
        if not self.remember_grimoire_path.exists():
            return
        try:
            saved_data = json.loads(self.remember_grimoire_path.read_text(encoding="utf-8"))
            self.players = parse_remembered_grimoire(saved_data)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            self.remember_grimoire_load_warning = f"Could not load remembered Grimoire: {exc}"
            return
        self.remember_grimoire_var.set(True)

    def _save_remembered_grimoire(self):
        if not self.remember_grimoire_var.get():
            return True
        temporary_path = self.remember_grimoire_path.with_suffix(".tmp")
        try:
            self.remember_grimoire_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(build_remembered_grimoire(self.players), indent=2),
                encoding="utf-8",
            )
            temporary_path.replace(self.remember_grimoire_path)
        except OSError as exc:
            self.status_var.set(f"Could not save remembered Grimoire: {exc}")
            return False
        return True

    def toggle_remember_grimoire(self):
        if self.remember_grimoire_var.get():
            if self._save_remembered_grimoire():
                self.status_var.set("Grimoire will be remembered on this computer.")
            else:
                self.remember_grimoire_var.set(False)
            return

        try:
            self.remember_grimoire_path.unlink(missing_ok=True)
            self.status_var.set("Remembered Grimoire disabled; defaults will load next time.")
        except OSError as exc:
            self.remember_grimoire_var.set(True)
            self.status_var.set(f"Could not remove remembered Grimoire: {exc}")

    def toggle_grimoire_lock(self):
        self.grimoire_locked = not self.grimoire_locked
        widget_state = "disabled" if self.grimoire_locked else "normal"
        self.lock_button.configure(text="Unlock grimoire" if self.grimoire_locked else "Lock grimoire")

        managed_buttons = self.player_action_buttons + [
            self.generate_button,
            self.pin_button,
            self.revert_effects_button,
        ]
        for button in managed_buttons:
            button.configure(state=widget_state)

        last_manage_entry = self.manage_menu.index("end")
        if last_manage_entry is not None:
            for index in range(last_manage_entry + 1):
                self.manage_menu.entryconfigure(index, state=widget_state)
        self.file_menu.entryconfigure(0, state=widget_state)
        self.status_var.set("Grimoire locked." if self.grimoire_locked else "Grimoire unlocked.")

    def export_assignments(self):
        rows = [self.output.item(item, "values") for item in self.output.get_children()]
        rows = [row for row in rows if len(row) >= 5 and row[1]]
        if not rows:
            self.status_var.set("Generate assignments before exporting.")
            return

        self.clipboard_clear()
        self.clipboard_append(format_assignment_export(rows))
        self.update_idletasks()
        self.export_button.configure(text="Copied!")
        self.status_var.set("Assignments copied to clipboard.")
        self.after(1800, lambda: self.export_button.configure(text="Export assignments"))

    def clear_assignment_pins(self):
        self.assignment_pins.clear()
        self.assignment_rows = []

    def refresh_player_table(self):
        for row in self.player_table.get_children():
            self.player_table.delete(row)

        for index, player in enumerate(self.players, start=1):
            preferred = player["preferred_roles"]
            values = [
                index,
                player["name"],
                preferred.get("townsfolk", ""),
                preferred.get("outsider", ""),
                preferred.get("minion", ""),
                preferred.get("demon", ""),
            ]
            self.player_table.insert("", "end", values=values)

    def toggle_selected_assignment_pin(self, event=None):
        if self.grimoire_locked:
            return
        selected = self.output.selection()
        if not selected:
            self.status_var.set("Select an assignment to pin or unpin.")
            return

        item = selected[0]
        values = self.output.item(item, "values")
        if not values or len(values) < 4:
            return

        player_name = values[1]
        if not player_name:
            return

        current_role = next((role for name, role in self.assignment_rows if name == player_name), None)
        if current_role is None:
            self.status_var.set(f"No current assignment exists for {player_name}.")
            return

        if player_name in self.assignment_pins:
            del self.assignment_pins[player_name]
            label = "unpinned"
        else:
            self.assignment_pins[player_name] = current_role
            label = "pinned"

        self._refresh_assignment_output(self.assignment_rows)
        self.status_var.set(f"{player_name} {label}.")

    def _refresh_assignment_output(self, assignments):
        for row in self.output.get_children():
            self.output.delete(row)

        player_lookup = {player["name"]: player for player in self.players}
        self.assignment_display_roles = {}
        for index, (name, role) in enumerate(assignments, start=1):
            player = player_lookup.get(name, {})
            preferred_role = player.get("preferred_roles", {}).get(role, "")
            fallback = ROLE_OPTIONS.get(role, [role.title()])
            display_role = preferred_role or (fallback[0] if isinstance(fallback, list) and fallback else role.title())
            original_lil_monsta = self.lil_monsta_minion_players.get(name)
            if role == "minion" and original_lil_monsta:
                display_role = format_lil_monsta_character(original_lil_monsta, display_role)
            self.assignment_display_roles[name] = display_role
            effect = ROLE_EFFECTS.get(display_role, "") or ROLE_EFFECTS.get(role, "") or ""
            if original_lil_monsta:
                effect = LIL_MONSTA_EFFECT
            elif is_lil_monsta_character(display_role):
                effect = LIL_MONSTA_EFFECT
            elif display_role.casefold() == "summoner":
                effect = SUMMONER_EFFECT
            elif display_role.casefold() == "bounty hunter":
                effect = BOUNTY_HUNTER_EFFECT
            is_clickable = parse_distribution_effect(effect) is not None or effect in {SUMMONER_EFFECT, BOUNTY_HUNTER_EFFECT, LIL_MONSTA_EFFECT}
            is_pinned = name in self.assignment_pins and self.assignment_pins[name] == role
            effect_display = format_effect_display(effect, name in self.effect_source_players)
            pin_label = format_pin_display(is_pinned)
            row_tags = build_assignment_row_tags(
                role,
                is_pinned=is_pinned,
                effect_applied=name in self.effect_source_players,
                effect_targeted=name in self.effect_target_players,
                effect_clickable=is_clickable,
                is_evil=name in self.evil_players,
            )

            self.output.insert("", "end", values=(index, name, display_role, effect_display, pin_label), tags=row_tags)

        self.output.tag_configure("pinned", foreground="#8a93a6")

    def _handle_effect_click(self, event):
        if self.grimoire_locked:
            return
        region = self.output.identify_region(event.x, event.y)
        if region != "cell":
            return

        column = self.output.identify_column(event.x)
        if column != "#4":
            return

        item_id = self.output.identify_row(event.y)
        if not item_id:
            return

        values = self.output.item(item_id, "values")
        if len(values) < 4:
            return

        player_name = values[1]
        if player_name in self.effect_source_players:
            return

        effect_text = values[3]
        if effect_text == SUMMONER_EFFECT:
            self._open_summoner_effect_dialog(player_name)
            return
        if effect_text == BOUNTY_HUNTER_EFFECT:
            self._open_bounty_hunter_dialog(player_name)
            return
        if effect_text == LIL_MONSTA_EFFECT:
            self._apply_lil_monsta_effect(player_name)
            return

        if not effect_text or parse_distribution_effect(effect_text) is None:
            return

        self._open_distribution_effect_dialog(effect_text, player_name)

    def _apply_lil_monsta_effect(self, player_name):
        current_role = next((role for name, role in self.assignment_rows if name == player_name), None)
        lil_monsta_character = self.assignment_display_roles.get(player_name, "")
        if current_role != "demon" or not is_lil_monsta_character(lil_monsta_character):
            self.status_var.set("Lil' Monsta can only change its own Demon assignment.")
            return

        self.assignment_pins.clear()
        self.lil_monsta_minion_players[player_name] = lil_monsta_character
        self.effect_source_players.add(player_name)
        self.applied_effect_players.add(player_name)
        self.assignment_rows = apply_lil_monsta_effect(self.assignment_rows, player_name)
        self._refresh_assignment_output(self.assignment_rows)
        self.status_var.set(f"{player_name} is Lil' Monsta and is now also a Minion.")

    def _open_summoner_effect_dialog(self, current_player_name=None):
        eligible = collect_summoner_candidates(
            self.assignment_rows,
            unavailable_players=self.effect_target_players | self.applied_effect_players,
            excluded_player=current_player_name,
        )
        if not eligible:
            self.status_var.set("No valid Demon players are available to convert.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Apply Summoner effect")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry(f"+{self.winfo_rootx() + 120}+{self.winfo_rooty() + 80}")
        tk.Label(dialog, text="Choose the Demon player to replace with their preferred Townsfolk character:").pack(
            anchor="w", padx=12, pady=(12, 8)
        )

        candidate_names = list(eligible)
        players_by_name = {player["name"]: player for player in self.players}
        candidate_frame = ttk.Frame(dialog)
        candidate_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        candidate_table = ttk.Treeview(
            candidate_frame,
            columns=("player", "current", "new"),
            show="headings",
            selectmode="browse",
            height=min(8, max(4, len(eligible))),
        )
        candidate_table.heading("player", text="Player")
        candidate_table.heading("current", text="Current Demon")
        candidate_table.heading("new", text="New Townsfolk")
        candidate_table.column("player", width=140, anchor="w")
        candidate_table.column("current", width=180, anchor="w")
        candidate_table.column("new", width=180, anchor="w")
        candidate_scroll = ttk.Scrollbar(candidate_frame, orient="vertical", command=candidate_table.yview)
        candidate_table.configure(yscrollcommand=candidate_scroll.set)
        candidate_table.grid(row=0, column=0, sticky="nsew")
        candidate_scroll.grid(row=0, column=1, sticky="ns")
        candidate_frame.rowconfigure(0, weight=1)
        candidate_frame.columnconfigure(0, weight=1)

        for index, name in enumerate(candidate_names):
            candidate_table.insert(
                "",
                "end",
                iid=str(index),
                values=describe_effect_candidate(name, "townsfolk", players_by_name, self.assignment_display_roles),
            )
        candidate_table.selection_set("0")

        def apply_choice():
            selected = candidate_table.selection()
            if len(selected) != 1:
                messagebox.showwarning("Select a player", "Please select one Demon player.", parent=dialog)
                return

            selected_player = candidate_names[int(selected[0])]
            self.assignment_pins.clear()
            if current_player_name is not None:
                self.effect_source_players.add(current_player_name)
                self.applied_effect_players.add(current_player_name)
            self.effect_target_players.add(selected_player)
            self.applied_effect_players.add(selected_player)
            self.assignment_rows = apply_summoner_effect(self.assignment_rows, selected_player)
            self._refresh_assignment_output(self.assignment_rows)
            self.status_var.set("Applied Summoner effect.")
            dialog.destroy()

        ttk.Button(dialog, text="Apply", command=apply_choice).pack(pady=(0, 12))

    def _open_bounty_hunter_dialog(self, current_player_name=None):
        eligible = collect_bounty_hunter_candidates(
            self.assignment_rows,
            unavailable_players=self.effect_target_players | self.applied_effect_players | self.evil_players,
            excluded_player=current_player_name,
        )
        if not eligible:
            self.status_var.set("No valid Townsfolk players are available to turn evil.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Apply Bounty Hunter effect")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry(f"+{self.winfo_rootx() + 120}+{self.winfo_rooty() + 80}")
        tk.Label(dialog, text="Choose a Townsfolk to turn evil. Their character and team remain unchanged:").pack(
            anchor="w", padx=12, pady=(12, 8)
        )

        candidate_names = list(eligible)
        candidate_frame = ttk.Frame(dialog)
        candidate_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        candidate_table = ttk.Treeview(
            candidate_frame,
            columns=("player", "character"),
            show="headings",
            selectmode="browse",
            height=min(8, max(4, len(eligible))),
        )
        candidate_table.heading("player", text="Player")
        candidate_table.heading("character", text="Current Townsfolk")
        candidate_table.column("player", width=160, anchor="w")
        candidate_table.column("character", width=220, anchor="w")
        candidate_scroll = ttk.Scrollbar(candidate_frame, orient="vertical", command=candidate_table.yview)
        candidate_table.configure(yscrollcommand=candidate_scroll.set)
        candidate_table.grid(row=0, column=0, sticky="nsew")
        candidate_scroll.grid(row=0, column=1, sticky="ns")
        candidate_frame.rowconfigure(0, weight=1)
        candidate_frame.columnconfigure(0, weight=1)

        for index, name in enumerate(candidate_names):
            candidate_table.insert(
                "",
                "end",
                iid=str(index),
                values=(name, self.assignment_display_roles.get(name, "Unknown")),
            )
        candidate_table.selection_set("0")

        def apply_choice():
            selected = candidate_table.selection()
            if len(selected) != 1:
                messagebox.showwarning("Select a player", "Please select one Townsfolk player.", parent=dialog)
                return

            selected_player = candidate_names[int(selected[0])]
            self.assignment_pins.clear()
            if current_player_name is not None:
                self.effect_source_players.add(current_player_name)
                self.applied_effect_players.add(current_player_name)
            self.evil_players.add(selected_player)
            self.effect_target_players.add(selected_player)
            self.applied_effect_players.add(selected_player)
            self._refresh_assignment_output(self.assignment_rows)
            self.status_var.set(f"{selected_player} remains Townsfolk and is now evil.")
            dialog.destroy()

        ttk.Button(dialog, text="Apply", command=apply_choice).pack(pady=(0, 12))

    def _open_distribution_effect_dialog(self, effect_text, current_player_name=None):
        parsed = parse_distribution_effect(effect_text)
        if parsed is None:
            return

        amount, target_role = parsed
        source_role = "townsfolk" if target_role == "outsider" else "outsider"
        if source_role == target_role:
            self.status_var.set("This effect cannot convert a player to the same role type.")
            return

        eligible = collect_effect_candidates(
            self.assignment_rows,
            effect_text,
            role_effects=ROLE_EFFECTS,
            applied_effect_players=self.applied_effect_players,
            character_names=self.assignment_display_roles,
            excluded_player=current_player_name,
        )
        if not eligible:
            self.status_var.set(f"No valid {source_role} players are available to convert.")
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"Apply {effect_text}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry(f"+{self.winfo_rootx() + 120}+{self.winfo_rooty() + 80}")

        tk.Label(dialog, text=f"Choose {amount} {source_role} player(s) to convert to {target_role}:").pack(anchor="w", padx=12, pady=(12, 8))

        candidate_names = list(eligible)
        players_by_name = {player["name"]: player for player in self.players}
        candidate_frame = ttk.Frame(dialog)
        candidate_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        candidate_table = ttk.Treeview(
            candidate_frame,
            columns=("player", "current", "new"),
            show="headings",
            selectmode="extended",
            height=min(8, max(4, len(eligible))),
        )
        candidate_table.heading("player", text="Player")
        candidate_table.heading("current", text="Current character")
        candidate_table.heading("new", text=f"New {target_role.title()}")
        candidate_table.column("player", width=140, anchor="w")
        candidate_table.column("current", width=180, anchor="w")
        candidate_table.column("new", width=180, anchor="w")
        candidate_scroll = ttk.Scrollbar(candidate_frame, orient="vertical", command=candidate_table.yview)
        candidate_table.configure(yscrollcommand=candidate_scroll.set)
        candidate_table.grid(row=0, column=0, sticky="nsew")
        candidate_scroll.grid(row=0, column=1, sticky="ns")
        candidate_frame.rowconfigure(0, weight=1)
        candidate_frame.columnconfigure(0, weight=1)

        for index, name in enumerate(candidate_names):
            candidate_table.insert(
                "",
                "end",
                iid=str(index),
                values=describe_effect_candidate(name, target_role, players_by_name, self.assignment_display_roles),
            )

        for index in range(min(amount, len(eligible))):
            candidate_table.selection_add(str(index))

        def apply_choice():
            selected = [candidate_names[int(item_id)] for item_id in candidate_table.selection()]
            if len(selected) != amount:
                messagebox.showwarning(
                    "Select players",
                    f"Please select exactly {amount} {source_role} player(s) to convert.",
                    parent=dialog,
                )
                return

            self.assignment_pins.clear()
            if current_player_name is not None:
                self.effect_source_players.add(current_player_name)
                self.applied_effect_players.add(current_player_name)
            self.effect_target_players.update(selected)
            self.applied_effect_players.update(selected)
            self.assignment_rows = apply_distribution_effect(self.assignment_rows, effect_text, selected_players=selected)
            self._refresh_assignment_output(self.assignment_rows)
            self.status_var.set(f"Applied {effect_text} effect.")
            dialog.destroy()

        ttk.Button(dialog, text="Apply", command=apply_choice).pack(pady=(0, 12))

    def revert_assignment_effects(self):
        if self.grimoire_locked:
            return
        if self.base_assignment_rows:
            self.assignment_rows = list(self.base_assignment_rows)
        else:
            self.assignment_rows = []
        self.assignment_pins.clear()
        self.applied_effect_players.clear()
        self.effect_source_players.clear()
        self.effect_target_players.clear()
        self.evil_players.clear()
        self.lil_monsta_minion_players.clear()
        self._refresh_assignment_output(self.assignment_rows)
        self.status_var.set("All assignment effects have been reverted.")

    def _player_dialog(self, mode: str, current_player=None):
        dialog = tk.Toplevel(self)
        dialog.title("Add player" if mode == "add" else "Edit player")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry(
            f"+{self.winfo_rootx() + 120}+{self.winfo_rooty() + 80}"
        )

        name_var = tk.StringVar(value=current_player["name"] if current_player else "")
        preferred_vars = {
            role: tk.StringVar(value=current_player["preferred_roles"].get(role, "") if current_player else "")
            for role in ROLE_ORDER
        }

        ttk.Label(dialog, text="Player name:").grid(row=0, column=0, padx=12, pady=(12, 6), sticky="w")
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=35)
        name_entry.grid(row=0, column=1, padx=(0, 12), pady=(12, 6), sticky="ew")
        name_entry.focus_set()

        row_index = 1
        for role in ROLE_ORDER:
            ttk.Label(dialog, text=f"{role.title()}:").grid(row=row_index, column=0, padx=12, pady=(6, 6), sticky="w")
            combo = ttk.Combobox(dialog, textvariable=preferred_vars[role], values=ROLE_OPTIONS.get(role, []), width=35)
            combo.grid(row=row_index, column=1, padx=(0, 12), pady=(6, 6), sticky="ew")
            row_index += 1

        def save_player():
            name = name_var.get().strip()
            if not name:
                self.status_var.set("Player name cannot be empty.")
                return

            preferred_roles = {role: preferred_vars[role].get().strip() for role in ROLE_ORDER}
            player = {"name": name, "preferred_roles": preferred_roles}
            if mode == "add":
                self.players.append(player)
                self.status_var.set(f"Added {name}.")
            else:
                index = self.players.index(current_player)
                self.players[index] = player
                self.status_var.set(f"Updated {name}.")

            self.refresh_player_table()
            self._save_remembered_grimoire()
            dialog.destroy()

        ttk.Button(dialog, text="Save", command=save_player).grid(row=row_index, column=0, columnspan=2, pady=(8, 12))

    def add_player(self):
        if self.grimoire_locked:
            return
        self.clear_assignment_pins()
        self._player_dialog("add")

    def import_player(self):
        if self.grimoire_locked:
            return

        file_path = filedialog.askopenfilename(
            parent=self,
            title="Import player preferences",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if not file_path:
            return

        try:
            with open(file_path, encoding="utf-8") as player_file:
                player = parse_imported_player(json.load(player_file))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            messagebox.showerror("Import player", str(exc), parent=self)
            return

        existing_names = {existing["name"].casefold() for existing in self.players}
        if player["name"].casefold() in existing_names:
            messagebox.showerror("Import player", f"A player named {player['name']} already exists.", parent=self)
            return

        self.players.append(player)
        self.refresh_player_table()
        self.status_var.set(f"Imported player {player['name']}.")
        self._save_remembered_grimoire()

    def edit_player(self):
        if self.grimoire_locked:
            return
        selected = self.player_table.selection()
        if not selected:
            self.status_var.set("Select a player to edit first.")
            return

        children = self.player_table.get_children()
        index = children.index(selected[0])
        current_player = self.players[index]
        self.clear_assignment_pins()
        self._player_dialog("edit", current_player)

    def remove_player(self):
        if self.grimoire_locked:
            return
        selected = self.player_table.selection()
        if not selected:
            self.status_var.set("Select a player to remove first.")
            return

        children = self.player_table.get_children()
        index = children.index(selected[0])
        player_name = self.players[index]["name"]
        del self.players[index]
        self.clear_assignment_pins()
        self.refresh_player_table()
        self.status_var.set(f"Removed {player_name}.")
        self._save_remembered_grimoire()

    def clear_players(self):
        if self.grimoire_locked:
            return
        if not self.players:
            self.status_var.set("There are no players to clear.")
            if hasattr(self, "output"):
                for row in self.output.get_children():
                    self.output.delete(row)
                self.clear_assignment_pins()
            self._save_remembered_grimoire()
            return

        confirm = tk.messagebox.askyesno(
            "Clear Grimoire",
            "Are you sure you want to wipe the Grimoire?",
            parent=self,
        )
        if not confirm:
            self.status_var.set("Clear cancelled.")
            return

        self.players.clear()
        self.clear_assignment_pins()
        self.refresh_player_table()
        if hasattr(self, "output"):
            for row in self.output.get_children():
                self.output.delete(row)
        self.status_var.set("The Grimoire has been wiped.")
        self._save_remembered_grimoire()

    def generate_roles(self):
        if self.grimoire_locked:
            return
        players = self.players
        if not players:
            self.status_var.set("Add at least one player.")
            return

        current_pins = dict(self.assignment_pins)

        try:
            counts = build_role_counts(len(players))
        except ValueError as exc:
            self.status_var.set(str(exc))
            for row in self.output.get_children():
                self.output.delete(row)
            self.output.insert("", "end", values=("", "Role assignment is only supported for 5 to 15 players.", "", "", ""), tags=("townsfolk",))
            self.assignment_rows = []
            self.assignment_pins.clear()
            return

        if self.assignment_rows and current_pins:
            assignments = apply_pinned_assignments(players, self.assignment_rows, current_pins)
            if not assignments:
                current_pins.clear()
                assignments = assign_roles(players)
        else:
            assignments = assign_roles(players)

        self.base_assignment_rows = list(assignments)
        self.assignment_rows = list(assignments)
        self.assignment_pins = preserve_pins_for_assignments(current_pins, assignments)
        self.applied_effect_players.clear()
        self.effect_source_players.clear()
        self.effect_target_players.clear()
        self.evil_players.clear()
        self.lil_monsta_minion_players.clear()
        self._refresh_assignment_output(assignments)

        self.status_var.set(
            "Counts: "
            + ", ".join(f"{role}={count}" for role, count in counts.items())
            + "."
        )


if __name__ == "__main__":
    app = WhaleBuffetApp()
    app.mainloop()
