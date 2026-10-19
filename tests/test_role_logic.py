import pytest

from app import (
    apply_distribution_effect,
    apply_lil_monsta_effect,
    apply_pinned_assignments,
    apply_summoner_effect,
    build_available_dummy_name,
    build_assignment_row_tags,
    collect_bounty_hunter_candidates,
    collect_effect_candidates,
    collect_summoner_candidates,
    describe_effect_candidate,
    format_assignment_export,
    format_effect_display,
    format_lil_monsta_character,
    format_pin_display,
    is_lil_monsta_character,
    parse_distribution_effect,
    preserve_pins_for_assignments,
)
from whalebuffetgenerator import build_role_counts, assign_roles
from whalebuffetgenerator.logic import (
    ROLE_ORDER,
    build_role_dictionary,
    extract_distribution_effect,
    resolve_preferred_role,
)


@pytest.mark.parametrize(
    ("player_count", "expected"),
    [
        (5, {"townsfolk": 3, "outsider": 0, "minion": 1, "demon": 1}),
        (6, {"townsfolk": 3, "outsider": 1, "minion": 1, "demon": 1}),
        (7, {"townsfolk": 5, "outsider": 0, "minion": 1, "demon": 1}),
        (8, {"townsfolk": 5, "outsider": 1, "minion": 1, "demon": 1}),
        (9, {"townsfolk": 5, "outsider": 2, "minion": 1, "demon": 1}),
        (10, {"townsfolk": 7, "outsider": 0, "minion": 2, "demon": 1}),
        (11, {"townsfolk": 7, "outsider": 1, "minion": 2, "demon": 1}),
        (12, {"townsfolk": 7, "outsider": 2, "minion": 2, "demon": 1}),
        (13, {"townsfolk": 9, "outsider": 0, "minion": 3, "demon": 1}),
        (14, {"townsfolk": 9, "outsider": 1, "minion": 3, "demon": 1}),
        (15, {"townsfolk": 9, "outsider": 2, "minion": 3, "demon": 1}),
    ],
)
def test_build_role_counts(player_count, expected):
    assert build_role_counts(player_count) == expected


def test_assign_roles_returns_expected_distribution():
    players = [f"Player {i}" for i in range(1, 9)]
    assignments = assign_roles(players)

    assert len(assignments) == len(players)
    role_names = [role for _, role in assignments]
    assert role_names.count("demon") == 1
    assert role_names.count("minion") == 1
    assert role_names.count("outsider") == 1
    assert role_names.count("townsfolk") == 5


def test_assign_roles_supports_player_preference_data():
    players = [
        {
            "name": "Alice",
            "preferred_roles": {
                "townsfolk": "Librarian",
                "outsider": "Recluse",
                "minion": "Baron",
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
                "minion": "Baron",
                "demon": "Imp",
            },
        },
        {
            "name": "Diana",
            "preferred_roles": {
                "townsfolk": "Investigator",
                "outsider": "Saint",
                "minion": "Spy",
                "demon": "Imp",
            },
        },
        {
            "name": "Evan",
            "preferred_roles": {
                "townsfolk": "Librarian",
                "outsider": "Recluse",
                "minion": "Baron",
                "demon": "Imp",
            },
        },
        {
            "name": "Frank",
            "preferred_roles": {
                "townsfolk": "Town Crier",
                "outsider": "Butler",
                "minion": "Cult Leader",
                "demon": "Imp",
            },
        },
        {
            "name": "Grace",
            "preferred_roles": {
                "townsfolk": "Nurse",
                "outsider": "Recluse",
                "minion": "Mare",
                "demon": "Imp",
            },
        },
    ]

    assignments = assign_roles(players)
    assert len(assignments) == len(players)
    assert all(isinstance(name, str) for name, _ in assignments)
    assert all(role in ROLE_ORDER for _, role in assignments)


def test_build_role_dictionary_groups_roles_by_team():
    roles = [
        {"name": "Librarian", "team": "townsfolk"},
        {"name": "Recluse", "team": "outsider"},
        {"name": "Baron", "team": "minion"},
        {"name": "Imp", "team": "demon"},
    ]

    dictionary = build_role_dictionary(roles)
    assert dictionary["townsfolk"] == ["Librarian"]
    assert dictionary["outsider"] == ["Recluse"]
    assert dictionary["minion"] == ["Baron"]
    assert dictionary["demon"] == ["Imp"]


def test_resolve_preferred_role_returns_player_preference_for_role_type():
    player = {
        "name": "Alice",
        "preferred_roles": {
            "townsfolk": "Librarian",
            "outsider": "Recluse",
            "minion": "Baron",
            "demon": "Imp",
        },
    }

    assert resolve_preferred_role(player, "townsfolk") == "Librarian"
    assert resolve_preferred_role(player, "demon") == "Imp"
    assert resolve_preferred_role({"name": "Bob", "preferred_roles": {"minion": ""}}, "minion") == "Minion"


def test_assign_roles_handles_duplicate_names():
    players = [
        {"name": "Alex", "preferred_roles": {role: "" for role in ROLE_ORDER}},
        {"name": "Alex", "preferred_roles": {role: "" for role in ROLE_ORDER}},
        {"name": "Bob", "preferred_roles": {role: "" for role in ROLE_ORDER}},
        {"name": "Cora", "preferred_roles": {role: "" for role in ROLE_ORDER}},
        {"name": "Drew", "preferred_roles": {role: "" for role in ROLE_ORDER}},
        {"name": "Evan", "preferred_roles": {role: "" for role in ROLE_ORDER}},
    ]

    assignments = assign_roles(players)
    assert len(assignments) == len(players)
    assert sum(role == "demon" for _, role in assignments) == 1
    assert sum(role == "minion" for _, role in assignments) == 1
    assert sum(role == "outsider" for _, role in assignments) == 1
    assert sum(role == "townsfolk" for _, role in assignments) == 3


def test_build_available_dummy_name_avoids_existing_names():
    existing = {"Biscuit Bert", "Barnacle Bess"}
    name = build_available_dummy_name(existing, ["Biscuit Bert", "Barnacle Bess", "Wobblewump"])

    assert name not in existing
    assert name in {"Wobblewump", "Biscuit Bert 2", "Barnacle Bess 2"}


def test_extract_distribution_effect_parses_bracketed_modifiers():
    ability = "There are extra Outsiders in play. [+2 Outsiders]"
    assert extract_distribution_effect({"name": "Baron", "team": "minion", "ability": ability}) == "+2 Outsiders"
    assert extract_distribution_effect({"name": "Poisoner", "team": "minion", "ability": "Nothing special"}) == ""


def test_parse_distribution_effect_handles_simple_modifier_text():
    assert parse_distribution_effect("+1 Outsider") == (1, "outsider")
    assert parse_distribution_effect("+2 Outsiders") == (2, "outsider")
    assert parse_distribution_effect("Nothing special") is None


def test_format_effect_display_and_pin_display_are_separate():
    assert format_effect_display("+1 Outsider") == "+1 Outsider"
    assert format_effect_display("+1 Outsider", True) == "+1 Outsider ✓"
    assert format_pin_display(True) == "📌"
    assert format_pin_display(False) == ""


def test_format_assignment_export_includes_table_columns():
    assert format_assignment_export([(1, "Alice", "Librarian", "", "")]) == (
        "#\tPlayer\tCharacter\tEffect\tPin\n1\tAlice\tLibrarian\t\t"
    )


def test_describe_effect_candidate_shows_current_and_new_character():
    players = {
        "Alice": {
            "name": "Alice",
            "preferred_roles": {"outsider": "Recluse"},
        }
    }

    assert describe_effect_candidate("Alice", "outsider", players, {"Alice": "Librarian"}) == (
        "Alice",
        "Librarian",
        "Recluse",
    )


def test_summoner_candidates_only_include_available_demon():
    assignments = [
        ("Alice", "townsfolk"),
        ("Bob", "demon"),
        ("Charlie", "minion"),
    ]

    assert collect_summoner_candidates(assignments, excluded_player="Alice") == ["Bob"]
    assert collect_summoner_candidates(assignments, unavailable_players={"Bob"}) == []


def test_bounty_hunter_candidates_are_other_available_townsfolk_only():
    assignments = [
        ("Alice", "townsfolk"),
        ("Bob", "townsfolk"),
        ("Charlie", "outsider"),
        ("Dana", "minion"),
        ("Evan", "demon"),
    ]

    assert collect_bounty_hunter_candidates(assignments, excluded_player="Alice") == ["Bob"]
    assert collect_bounty_hunter_candidates(assignments, unavailable_players={"Alice", "Bob"}) == []


def test_bounty_hunter_target_tags_keep_purple_background_and_minion_red_priority():
    tags = build_assignment_row_tags("townsfolk", effect_targeted=True, is_evil=True)

    assert tags == ("evil_targeted",)


def test_apply_summoner_effect_replaces_selected_demon_with_townsfolk():
    assignments = [
        ("Alice", "townsfolk"),
        ("Bob", "demon"),
        ("Charlie", "minion"),
    ]

    result = apply_summoner_effect(assignments, "Bob")

    assert result == [
        ("Alice", "townsfolk"),
        ("Bob", "townsfolk"),
        ("Charlie", "minion"),
    ]
    assert apply_summoner_effect(assignments, "Alice") == assignments


def test_lil_monsta_effect_changes_only_its_own_demon_team_to_minion():
    assignments = [
        ("Alice", "townsfolk"),
        ("Bob", "demon"),
        ("Charlie", "minion"),
    ]

    assert apply_lil_monsta_effect(assignments, "Bob") == [
        ("Alice", "townsfolk"),
        ("Bob", "minion"),
        ("Charlie", "minion"),
    ]
    assert apply_lil_monsta_effect(assignments, "Alice") == assignments


def test_lil_monsta_display_retains_original_and_minion_character():
    assert is_lil_monsta_character("Lil' Monsta")
    assert is_lil_monsta_character("Lil’ Monsta")
    assert format_lil_monsta_character("Lil' Monsta", "Baron") == "Lil' Monsta (Baron)"


def test_preserve_pins_for_assignments_keeps_valid_pins_across_rerolls():
    assert preserve_pins_for_assignments({"Alice": "townsfolk", "Bob": "demon"}, [("Alice", "townsfolk"), ("Bob", "demon")]) == {
        "Alice": "townsfolk",
        "Bob": "demon",
    }
    assert preserve_pins_for_assignments({"Alice": "townsfolk", "Bob": "demon"}, [("Alice", "outsider"), ("Bob", "demon")]) == {
        "Bob": "demon",
    }


def test_apply_distribution_effect_changes_selected_townsfolk_to_outsider():
    assignments = [
        ("Alice", "townsfolk"),
        ("Bob", "townsfolk"),
        ("Charlie", "demon"),
        ("Dana", "minion"),
        ("Evan", "townsfolk"),
    ]

    result = apply_distribution_effect(assignments, "+2 Outsiders", selected_players=["Alice", "Evan"])

    assert ("Alice", "outsider") in result
    assert ("Evan", "outsider") in result
    assert sum(role == "townsfolk" for _, role in result) == 1
    assert sum(role == "outsider" for _, role in result) == 2


def test_collect_effect_candidates_excludes_applied_and_self_players():
    assignments = [
        ("Alice", "townsfolk"),
        ("Bob", "townsfolk"),
        ("Charlie", "townsfolk"),
        ("Dana", "townsfolk"),
    ]
    character_names = {
        "Alice": "Librarian",
        "Bob": "Balloonist",
        "Charlie": "Washerwoman",
        "Dana": "Investigator",
    }
    role_effects = {"Balloonist": "+1 Outsider"}

    eligible = collect_effect_candidates(
        assignments,
        "+1 Outsider",
        role_effects=role_effects,
        applied_effect_players={"Dana"},
        character_names=character_names,
        excluded_player="Bob",
    )

    assert eligible == ["Alice", "Charlie"]


def test_apply_pinned_assignments_keeps_pinned_rows_and_roles():
    players = [
        {"name": "Alice", "preferred_roles": {role: "" for role in ROLE_ORDER}},
        {"name": "Bob", "preferred_roles": {role: "" for role in ROLE_ORDER}},
        {"name": "Charlie", "preferred_roles": {role: "" for role in ROLE_ORDER}},
        {"name": "Dana", "preferred_roles": {role: "" for role in ROLE_ORDER}},
        {"name": "Evan", "preferred_roles": {role: "" for role in ROLE_ORDER}},
    ]
    previous = [
        ("Alice", "townsfolk"),
        ("Bob", "demon"),
        ("Charlie", "outsider"),
        ("Dana", "minion"),
        ("Evan", "townsfolk"),
    ]
    pinned = {"Alice": "townsfolk", "Charlie": "outsider"}

    result = apply_pinned_assignments(players, previous, pinned)

    assert result[0] == ("Alice", "townsfolk")
    assert result[2] == ("Charlie", "outsider")
    assert set(name for name, _ in result) == {"Alice", "Bob", "Charlie", "Dana", "Evan"}


def test_invalid_player_count_raises():
    with pytest.raises(ValueError):
        build_role_counts(4)
