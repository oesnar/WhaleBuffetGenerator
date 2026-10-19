import json
import random
import re
import urllib.request
from typing import Dict, Iterable, List, Tuple, Union

ROLE_ORDER = ["townsfolk", "outsider", "minion", "demon"]

ROLE_COUNTS = {
    5: {"townsfolk": 3, "outsider": 0, "minion": 1, "demon": 1},
    6: {"townsfolk": 3, "outsider": 1, "minion": 1, "demon": 1},
    7: {"townsfolk": 5, "outsider": 0, "minion": 1, "demon": 1},
    8: {"townsfolk": 5, "outsider": 1, "minion": 1, "demon": 1},
    9: {"townsfolk": 5, "outsider": 2, "minion": 1, "demon": 1},
    10: {"townsfolk": 7, "outsider": 0, "minion": 2, "demon": 1},
    11: {"townsfolk": 7, "outsider": 1, "minion": 2, "demon": 1},
    12: {"townsfolk": 7, "outsider": 2, "minion": 2, "demon": 1},
    13: {"townsfolk": 9, "outsider": 0, "minion": 3, "demon": 1},
    14: {"townsfolk": 9, "outsider": 1, "minion": 3, "demon": 1},
    15: {"townsfolk": 9, "outsider": 2, "minion": 3, "demon": 1},
}

FALLBACK_ROLE_OPTIONS = {
    "townsfolk": [
        "Librarian",
        "Washerwoman",
        "Investigator",
        "Fortune Teller",
        "Town Crier",
        "Nurse",
    ],
    "outsider": ["Recluse", "Drunk", "Butler", "Saint"],
    "minion": ["Baron", "Poisoner", "Spy", "Mare", "Cult Leader"],
    "demon": ["Imp", "Fang Gu", "Vigormortis", "No Dashii", "Shabaloth"],
}


def build_role_dictionary(raw_roles: Iterable[dict]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {role: [] for role in ROLE_ORDER}
    for item in raw_roles:
        team = item.get("team") if isinstance(item, dict) else None
        name = item.get("name") if isinstance(item, dict) else None
        if team in grouped and name:
            grouped.setdefault(team, [])
            if name not in grouped[team]:
                grouped[team].append(name)

    for role_type in ROLE_ORDER:
        grouped[role_type] = sorted(grouped.get(role_type, []))
    return grouped


def extract_distribution_effect(role_data: Union[str, dict, None]) -> str:
    """Return the bracketed role-distribution modifier from a role ability, if present."""
    if role_data is None:
        return ""

    ability_text = role_data if isinstance(role_data, str) else role_data.get("ability", "")
    if not isinstance(ability_text, str):
        return ""

    matches = re.findall(r"\[([^\]]+)\]", ability_text)
    for match in reversed(matches):
        modifier = match.strip()
        if not modifier:
            continue
        if any(keyword in modifier.lower() for keyword in ["outsider", "outsiders", "townsfolk", "minion", "demon"]):
            return modifier
    return ""


def fetch_role_dictionary(url: str = "https://release.botc.app/resources/data/roles.json") -> Dict[str, List[str]]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        return build_role_dictionary(data)
    except Exception:
        return FALLBACK_ROLE_OPTIONS


def fetch_role_effects(url: str = "https://release.botc.app/resources/data/roles.json") -> Dict[str, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        return {
            item.get("name"): extract_distribution_effect(item)
            for item in data if isinstance(item, dict) and item.get("name") and extract_distribution_effect(item)
        }
    except Exception:
        return {}


ROLE_OPTIONS = fetch_role_dictionary()
ROLE_EFFECTS = fetch_role_effects()


def normalize_player(player: Union[str, dict]) -> dict:
    if isinstance(player, str):
        return {"name": player, "preferred_roles": {role: "" for role in ROLE_ORDER}}

    if not isinstance(player, dict):
        raise TypeError("Players must be strings or dictionaries with a name.")

    name = player.get("name")
    if not name:
        raise ValueError("Each player must include a name.")

    preferred_roles = player.get("preferred_roles", {})
    if not isinstance(preferred_roles, dict):
        raise ValueError("Each player's preferred_roles must be a dictionary.")

    normalized = {role: preferred_roles.get(role, "") for role in ROLE_ORDER}
    return {"name": str(name), "preferred_roles": normalized}


def build_role_counts(player_count: int) -> Dict[str, int]:
    """Return the role distribution for a given player count."""
    if player_count not in ROLE_COUNTS:
        raise ValueError(
            "Unsupported player count. Whale buffet table supports 5-15 players only."
        )
    return dict(ROLE_COUNTS[player_count])


def resolve_preferred_role(player: Union[str, dict], role_name: str) -> str:
    """Return the preferred character name for the given role team, or the role label as fallback."""
    normalized = normalize_player(player)
    preferred = normalized.get("preferred_roles", {}).get(role_name, "")
    return preferred or role_name.title()


def assign_roles(players: Iterable[Union[str, dict]]) -> List[Tuple[str, str]]:
    """Randomize a list of players into whale-buffet role assignments."""
    player_list = [normalize_player(player) for player in players]
    if not player_list:
        return []

    count = len(player_list)
    role_counts = build_role_counts(count)
    remaining = [{"id": index, **player} for index, player in enumerate(player_list)]
    assignments: List[Tuple[int, str, str]] = []

    for role_name in ROLE_ORDER:
        assigned_ids = {player_id for player_id, _, _ in assignments}
        available = [player for player in remaining if player["id"] not in assigned_ids]
        preferred_players = [
            player for player in available if player["preferred_roles"].get(role_name)
        ]
        pool = preferred_players if preferred_players else available
        target = min(role_counts[role_name], len(pool))
        chosen = random.sample(pool, k=target) if pool else []

        for player in chosen:
            assignments.append((player["id"], player["name"], role_name))

        remaining = [player for player in remaining if player["id"] not in {item["id"] for item in chosen}]

    assignments.sort(key=lambda item: ROLE_ORDER.index(item[2]))
    return [(player_name, role_name) for _, player_name, role_name in assignments]
