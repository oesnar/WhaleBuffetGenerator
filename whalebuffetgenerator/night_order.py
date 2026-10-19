import csv
import html
import io
import urllib.request
from collections import Counter


NIGHT_ORDER_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/1eJkBC6rF-VU6J0h0KJvyiXjs2HLl6Yjzw9jfVYHOW34/export?format=csv&gid=0"
)

ROLE_ALIASES = {
    "budhist": "buddhist",
    "bureaucrate": "bureaucrat",
    "inkeeper": "innkeeper",
}


def parse_night_order_csv(csv_text):
    first_night = []
    other_nights = []
    for row in csv.reader(io.StringIO(csv_text)):
        if len(row) < 9:
            continue
        first_name, first_symbol = row[4].strip(), row[5].strip()
        other_name, other_symbol = row[7].strip(), row[8].strip()
        if first_name and first_name.casefold() not in {"first night", "last updated"}:
            first_night.append((first_name, first_symbol))
        if other_name and other_name.casefold() not in {"other nights", "last updated"}:
            other_nights.append((other_name, other_symbol))
    return first_night, other_nights


def fetch_night_order(url=NIGHT_ORDER_CSV_URL):
    with urllib.request.urlopen(url, timeout=15) as response:
        csv_text = response.read().decode("utf-8-sig")
    return parse_night_order_csv(csv_text)


def normalize_order_role(role_name):
    normalized = " ".join(str(role_name).casefold().split())
    return ROLE_ALIASES.get(normalized, normalized)


def filter_night_order(first_night, other_nights, assignments, players, character_names, extra_character_players=None, lil_monsta_players=None):
    role_counts = Counter()
    extra_character_players = set(extra_character_players or {})
    lil_monsta_players = set(lil_monsta_players or {})
    demon_present = False
    minion_present = False

    for player_name, role in assignments:
        if player_name in lil_monsta_players:
            role_counts[normalize_order_role("Lil' Monsta")] += 1
            demon_present = True
            minion_present = True
            continue
        if player_name in extra_character_players:
            role_counts[normalize_order_role("Village Idiot")] += 1
        else:
            character_name = character_names.get(player_name, "")
            if character_name:
                if character_name.casefold().startswith("village idiot ("):
                    character_name = "Village Idiot"
                role_counts[normalize_order_role(character_name)] += 1
        demon_present = demon_present or role == "demon"
        minion_present = minion_present or role == "minion"

    requested_townsfolk = {
        normalize_order_role(player.get("preferred_roles", {}).get("townsfolk", ""))
        for player in players
        if player.get("preferred_roles", {}).get("townsfolk", "").strip()
    }

    def filter_phase(rows):
        remaining_role_counts = role_counts.copy()
        filtered = []
        for role_name, symbol in rows:
            normalized = normalize_order_role(role_name)
            if normalized in {"dusk", "dawn"}:
                filtered.append((role_name, symbol))
                continue
            if normalized == "minion info":
                if minion_present or demon_present:
                    filtered.append((role_name, symbol))
                continue
            if normalized == "demon info & bluffs":
                if demon_present:
                    filtered.append((role_name, symbol))
                continue

            if normalized in requested_townsfolk:
                repetitions = max(1, remaining_role_counts.pop(normalized, 0))
            else:
                repetitions = remaining_role_counts.pop(normalized, 0)
            filtered.extend([(role_name, symbol)] * repetitions)
        return filtered

    return filter_phase(first_night), filter_phase(other_nights)


def render_night_order_html(first_night, other_nights):
    def render_phase(title, rows):
        entries = "\n".join(
            f'<li><span class="symbol">{html.escape(symbol)}</span><span>{html.escape(role_name)}</span></li>'
            for role_name, symbol in rows
        )
        return f"<section><h2>{html.escape(title)}</h2><ol>{entries}</ol></section>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Whale Buffet Night Order</title>
<style>
body {{ color: #20282a; font-family: Arial, sans-serif; margin: 32px auto; max-width: 900px; padding: 0 24px; }}
h1 {{ border-bottom: 3px solid #9d1515; font-family: Georgia, serif; padding-bottom: 12px; }}
.phases {{ display: grid; gap: 32px; grid-template-columns: repeat(2, minmax(0, 1fr)); }}
h2 {{ background: #eef3f1; border-left: 4px solid #246b67; font-size: 20px; padding: 10px 12px; }}
ol {{ line-height: 1.55; padding-left: 38px; }}
li {{ border-bottom: 1px solid #e1e6e4; padding: 5px 0; }}
.symbol {{ display: inline-block; margin-right: 10px; min-width: 22px; }}
.print-button {{ background: #9d1515; border: 0; border-radius: 4px; color: white; cursor: pointer; font-size: 15px; font-weight: bold; margin: 16px 0; padding: 11px 18px; }}
@media (max-width: 700px) {{ .phases {{ grid-template-columns: 1fr; }} }}
@media print {{ body {{ margin: 0; max-width: none; padding: 0; }} .phases {{ gap: 18px; }} .print-button {{ display: none; }} h2 {{ break-after: avoid; }} li {{ break-inside: avoid; }} }}
</style>
</head>
<body>
<h1>Whale Buffet Night Order</h1>
<button class="print-button" onclick="window.print()">Print</button>
<main class="phases">{render_phase("First Night", first_night)}{render_phase("Other Nights", other_nights)}</main>
<script>window.addEventListener("load", () => window.print());</script>
</body>
</html>"""
