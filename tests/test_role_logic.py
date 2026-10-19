import pytest
from typing import cast

from app import (
    apply_distribution_effect,
    apply_lil_monsta_effect,
    apply_minionless_demon_rule,
    apply_pinned_assignments,
    apply_summoner_effect,
    build_available_dummy_name,
    build_assignment_row_tags,
    build_remembered_grimoire,
    collect_bounty_hunter_candidates,
    collect_effect_candidates,
    collect_summoner_candidates,
    describe_effect_candidate,
    format_assignment_export,
    format_effect_display,
    format_lil_monsta_character,
    NumericSetupEffect,
    numeric_effect_choices,
    format_pin_display,
    is_lil_monsta_character,
    numeric_effect_choices,
    parse_distribution_effect,
    parse_imported_player,
    parse_remembered_grimoire,
    preserve_pins_for_assignments,
)
from whalebuffetgenerator import build_role_counts, assign_roles
from whalebuffetgenerator.logic import (
    ROLE_ORDER,
    build_role_dictionary,
    extract_distribution_effect,
    normalize_player,
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


def test_build_role_dictionary_excludes_unselectable_characters():
    dictionary = build_role_dictionary(
        [
            {"name": "Drunk", "team": "outsider"},
            {"name": "Lunatic", "team": "outsider"},
            {"name": "Marionette", "team": "minion"},
            {"name": "Recluse", "team": "outsider"},
        ]
    )

    assert dictionary["outsider"] == ["Recluse"]
    assert dictionary["minion"] == []


def test_normalize_player_removes_unselectable_character_preferences():
    normalized = normalize_player(
        {
            "name": "Alice",
            "preferred_roles": {
                "townsfolk": "Lunatic",
                "outsider": "Drunk",
                "minion": "Marionette",
                "demon": "Imp",
            },
        }
    )

    assert normalized["preferred_roles"] == {
        "townsfolk": "",
        "outsider": "",
        "minion": "",
        "demon": "Imp",
    }


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
    parsed = parse_distribution_effect("+1 Outsider")
    assert isinstance(parsed, NumericSetupEffect)
    assert parsed.role == "outsider"
    assert [(choice.value, choice.label) for choice in parsed.choices] == [(1, "+1 Outsider")]
    assert parse_distribution_effect("Nothing special") is None


@pytest.mark.parametrize(
    ("effect_text", "expected_role", "expected_choices", "expected_mode"),
    [
        ("+0 or +1 Outsider", "outsider", [(0, "+0 Outsiders"), (1, "+1 Outsider")], "delta"),
        ("-0 or -1 Outsider", "outsider", [(0, "-0 Outsiders"), (-1, "-1 Outsider")], "delta"),
        ("-1 or +1 Outsider", "outsider", [(-1, "-1 Outsider"), (1, "+1 Outsider")], "delta"),
        (
            "+0 to +2 Village Idiots. 1 of the extras is drunk",
            "village idiot",
            [(0, "+0 Village Idiots"), (1, "+1 Village Idiot"), (2, "+2 Village Idiots")],
            "copies",
        ),
        ("X Outsiders", "outsider", [], "total"),
        (
            "Evil characters are in a line. You are in the middle. +1 Minion. -? to +? Outsiders",
            "outsider",
            [],
            "flex_range",
        ),
    ],
)
def test_parse_distribution_effect_supports_setup_numeric_formats(effect_text, expected_role, expected_choices, expected_mode):
    parsed = parse_distribution_effect(effect_text)

    assert parsed is not None
    assert parsed.role == expected_role
    assert [(choice.value, choice.label) for choice in parsed.choices] == expected_choices
    assert parsed.mode == expected_mode


def test_numeric_effect_choices_filter_by_available_players():
    assignments = [("Town 1", "townsfolk"), ("Town 2", "townsfolk"), ("Out 1", "outsider")]

    balloonist = numeric_effect_choices(parse_distribution_effect("+0 or +1 Outsider"), assignments)
    hermit = numeric_effect_choices(parse_distribution_effect("-0 or -1 Outsider"), assignments)
    godfather = numeric_effect_choices(parse_distribution_effect("-1 or +1 Outsider"), assignments)

    assert [choice.value for choice in balloonist] == [0, 1]
    assert [choice.value for choice in hermit] == [0, -1]
    assert [choice.value for choice in godfather] == [-1, 1]


def test_apply_distribution_effect_supports_positive_negative_and_zero_choices():
    assignments = [
        ("Town 1", "townsfolk"),
        ("Town 2", "townsfolk"),
        ("Out 1", "outsider"),
        ("Minion", "minion"),
        ("Demon", "demon"),
    ]

    added = apply_distribution_effect(assignments, "+1 Outsider", ["Town 1"], effect_choice=1)
    removed = apply_distribution_effect(assignments, "-1 Outsider", ["Out 1"], effect_choice=-1)
    added_minion = apply_distribution_effect(assignments, "+1 Minion", ["Town 1"], effect_choice=1)
    zero = apply_distribution_effect(assignments, "+0 or +1 Outsider", [], effect_choice=0)

    assert ("Town 1", "outsider") in added
    assert ("Out 1", "townsfolk") in removed
    assert ("Town 1", "minion") in added_minion
    assert zero == assignments


def test_xaan_effect_uses_absolute_outsider_total():
    assignments = [
        ("Town 1", "townsfolk"),
        ("Town 2", "townsfolk"),
        ("Town 3", "townsfolk"),
        ("Out 1", "outsider"),
        ("Minion", "minion"),
        ("Demon", "demon"),
    ]

    updated = apply_distribution_effect(assignments, "X Outsiders", ["Town 1", "Town 2"], effect_choice=3)

    assert sum(role == "outsider" for _, role in updated) == 3
    assert ("Town 1", "outsider") in updated
    assert ("Town 2", "outsider") in updated


def test_format_effect_display_and_pin_display_are_separate():
    assert format_effect_display("+1 Outsider") == "+1 Outsider"
    assert format_effect_display("+1 Outsider", True) == "+1 Outsider ✓"
    assert format_pin_display(True) == "📌"
    assert format_pin_display(False) == ""


def test_format_assignment_export_includes_table_columns():
    assert format_assignment_export([(1, "Alice", "Librarian", "", "")]) == (
        "#\tPlayer\tCharacter\tEffect\tPin\n1\tAlice\tLibrarian\t\t"
    )


def test_parse_imported_player_requires_exact_five_fields_and_skips_role_validation():
    imported = parse_imported_player(
        {
            "name": "  Alice  ",
            "townsfolk": "Unknown Townsfolk",
            "outsider": "Custom Outsider",
            "minion": "Custom Minion",
            "demon": "Custom Demon",
        }
    )

    assert imported == {
        "name": "Alice",
        "preferred_roles": {
            "townsfolk": "Unknown Townsfolk",
            "outsider": "Custom Outsider",
            "minion": "Custom Minion",
            "demon": "Custom Demon",
        },
    }


@pytest.mark.parametrize(
    "data",
    [
        {"name": "Alice", "townsfolk": "A", "outsider": "B", "minion": "C"},
        {"name": "Alice", "townsfolk": "A", "outsider": "B", "minion": "C", "demon": "D", "extra": "E"},
    ],
)
def test_parse_imported_player_rejects_missing_or_extra_fields(data):
    with pytest.raises(ValueError):
        parse_imported_player(data)


@pytest.mark.parametrize("role_name", ["Drunk", "Lunatic", "Marionette"])
def test_parse_imported_player_rejects_unselectable_preferences(role_name):
    with pytest.raises(ValueError, match="cannot be selected"):
        parse_imported_player(
            {
                "name": "Alice",
                "townsfolk": "Librarian",
                "outsider": role_name,
                "minion": "Baron",
                "demon": "Imp",
            }
        )


def test_remembered_grimoire_round_trip_preserves_players_and_empty_roster():
    players = [
        {
            "name": "Alice",
            "preferred_roles": {"townsfolk": "Librarian", "outsider": "Recluse", "minion": "Baron", "demon": "Imp"},
        }
    ]

    assert parse_remembered_grimoire(build_remembered_grimoire(players)) == players
    assert parse_remembered_grimoire(build_remembered_grimoire([])) == []


def test_remembered_grimoire_rejects_duplicate_names():
    player = {
        "name": "Alice",
        "preferred_roles": {"townsfolk": "Librarian", "outsider": "Recluse", "minion": "Baron", "demon": "Imp"},
    }
    saved = build_remembered_grimoire([player, {**player, "name": "alice"}])

    with pytest.raises(ValueError, match="duplicate"):
        parse_remembered_grimoire(saved)


def test_remembered_grimoire_clears_newly_unselectable_preferences():
    player = {
        "name": "Alice",
        "preferred_roles": {"townsfolk": "Librarian", "outsider": "Drunk", "minion": "Baron", "demon": "Imp"},
    }

    restored = parse_remembered_grimoire(build_remembered_grimoire([player]))

    assert restored[0]["preferred_roles"]["outsider"] == ""
    assert restored[0]["preferred_roles"]["townsfolk"] == "Librarian"


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


@pytest.mark.parametrize("demon_name", ["Kazali", "Lord of Typhon"])
def test_minionless_demon_variants_convert_minion_slots_to_townsfolk(demon_name):
    assignments = [("Alice", "townsfolk"), ("Bob", "minion"), ("Charlie", "demon")]

    updated, converted = apply_minionless_demon_rule(assignments, {"Charlie": demon_name})

    assert updated == [("Alice", "townsfolk"), ("Bob", "townsfolk"), ("Charlie", "demon")]
    assert converted == {"Bob"}
    assert apply_minionless_demon_rule(assignments, {"Charlie": "Imp"}) == (assignments, set())


def test_gui_generation_removes_minions_for_kazali():
    from app import WhaleBuffetApp

    window = WhaleBuffetApp()
    try:
        window.players = [
            {
                "name": f"Player {index}",
                "preferred_roles": {
                        "townsfolk": "" if index == 0 else "Librarian",
                    "outsider": "Recluse",
                    "minion": "" if index == 0 else "Baron",
                    "demon": "Kazali" if index == 0 else "",
                },
            }
            for index in range(5)
        ]
        window.refresh_player_table()
        window.generate_roles()

        assignments = cast(list[tuple[str, str]], window.assignment_rows)
        assert len(assignments) == 5
        assert sum(role == "demon" for _, role in assignments) == 1
        assert sum(role == "minion" for _, role in assignments) == 0
        assert sum(role == "townsfolk" for _, role in assignments) == 4
        assert "Kazali" in window.assignment_display_roles.values()
    finally:
        window.destroy()


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
