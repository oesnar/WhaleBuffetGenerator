from whalebuffetgenerator.night_order import filter_night_order, parse_night_order_csv, render_night_order_html


def test_parse_night_order_csv_uses_spreadsheet_order_and_symbols():
    csv_text = """,,,,,,,,\n,,,,First Night,,,Other Nights,\n,,,,Dusk,,,Dusk,\n,,,,Balloonist,blue,,Imp,red\n,,,,Dawn,,,Dawn,\n"""

    first_night, other_nights = parse_night_order_csv(csv_text)

    assert first_night == [("Dusk", ""), ("Balloonist", "blue"), ("Dawn", "")]
    assert other_nights == [("Dusk", ""), ("Imp", "red"), ("Dawn", "")]


def test_filter_includes_assigned_roles_in_both_phases_and_requested_townsfolk():
    first_order = [("Dusk", ""), ("Librarian", "blue"), ("Imp", "red"), ("Dawn", "")]
    other_order = [("Dusk", ""), ("Imp", "red"), ("Librarian", "blue"), ("Dawn", "")]
    assignments = [("Alice", "demon"), ("Bob", "townsfolk")]
    players = [
        {"name": "Alice", "preferred_roles": {"townsfolk": "Washerwoman"}},
        {"name": "Bob", "preferred_roles": {"townsfolk": "Librarian"}},
    ]
    characters = {"Alice": "Imp", "Bob": "Fortune Teller"}

    first, other = filter_night_order(first_order, other_order, assignments, players, characters)

    assert first == [("Dusk", ""), ("Librarian", "blue"), ("Imp", "red"), ("Dawn", "")]
    assert other == [("Dusk", ""), ("Imp", "red"), ("Librarian", "blue"), ("Dawn", "")]


def test_rendered_night_order_escapes_role_names_and_has_both_phases():
    document = render_night_order_html([("Dusk", ""), ("Chef <test>", "blue")], [("Dawn", "")])

    assert "First Night" in document
    assert "Other Nights" in document
    assert "Chef &lt;test&gt;" in document
    assert "window.print()" in document
