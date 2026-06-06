import os
import sqlite3
import chess.pgn
from collections import defaultdict
import json
from datetime import datetime

USERNAME = "Tonymontana013"
BASE_DIR = "games"
DB_PATH = "chess.db"
OUTPUT = "dashboard.html"

# ── Extract game metadata from PGNs ──

games_data = []

pgn_files = [f for f in os.listdir(BASE_DIR) if f.endswith(".pgn")]
for filename in sorted(pgn_files, key=lambda f: int(f.replace("game_", "").replace(".pgn", ""))):
    filepath = os.path.join(BASE_DIR, filename)
    with open(filepath) as f:
        game = chess.pgn.read_game(f)
    if game is None:
        continue

    headers = game.headers
    is_white = headers.get("White", "") == USERNAME
    player_color = "white" if is_white else "black"
    rating = int(headers.get("WhiteElo" if is_white else "BlackElo", 0))
    opponent_rating = int(headers.get("BlackElo" if is_white else "WhiteElo", 0))
    result_str = headers.get("Result", "*")

    if result_str == "1-0":
        result = "win" if is_white else "loss"
    elif result_str == "0-1":
        result = "loss" if is_white else "win"
    else:
        result = "draw"

    date_str = headers.get("UTCDate", headers.get("Date", ""))
    eco = headers.get("ECO", "?")
    eco_url = headers.get("ECOUrl", "")
    opening_name = eco_url.split("/")[-1].replace("-", " ") if eco_url else eco
    time_control = headers.get("TimeControl", "?")
    termination = headers.get("Termination", "")

    # Count full moves (mainline yields half-moves/plies)
    move_count = (sum(1 for _ in game.mainline_moves()) + 1) // 2

    games_data.append({
        "file": filename,
        "date": date_str,
        "color": player_color,
        "rating": rating,
        "opponent_rating": opponent_rating,
        "result": result,
        "eco": eco,
        "opening": opening_name,
        "time_control": time_control,
        "termination": termination,
        "moves": move_count,
    })

# ── Query analysis DB ──

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# User's mistakes per game (only user's moves, excluding "good")
cursor.execute("""
    SELECT game_file, classification, COUNT(*)
    FROM analysis
    WHERE is_user = 1 AND classification != 'good'
    GROUP BY game_file, classification
""")
mistakes_by_game = defaultdict(lambda: {"blunder": 0, "mistake": 0, "inaccuracy": 0})
for game_file, classification, count in cursor.fetchall():
    mistakes_by_game[game_file][classification] = count

# Accuracy per game: mean of per-move accuracy (win%-based, computed at analysis time)
cursor.execute("""
    SELECT game_file, AVG(accuracy)
    FROM analysis
    WHERE is_user = 1
    GROUP BY game_file
""")
accuracy_by_game = {}
for game_file, avg_acc in cursor.fetchall():
    accuracy_by_game[game_file] = round(avg_acc or 0, 1)

# Phase analysis: user's mean accuracy and average centipawn loss (ACPL) by phase
cursor.execute("""
    SELECT phase, AVG(accuracy), AVG(cpl), COUNT(*)
    FROM analysis
    WHERE is_user = 1
    GROUP BY phase
""")
phase_stats = {}
for phase, avg_acc, avg_cpl, count in cursor.fetchall():
    phase_stats[phase] = {"accuracy": round(avg_acc or 0, 1), "moves": count, "acpl": round(avg_cpl or 0)}

# Phase mistakes breakdown (user only)
cursor.execute("""
    SELECT phase, classification, COUNT(*)
    FROM analysis
    WHERE is_user = 1 AND classification != 'good'
    GROUP BY phase, classification
""")
phase_mistakes = defaultdict(lambda: {"blunder": 0, "mistake": 0, "inaccuracy": 0})
for phase, classification, count in cursor.fetchall():
    phase_mistakes[phase][classification] = count

# Worst moves (user only)
cursor.execute("""
    SELECT game_file, move_number, player, move, classification, eval_drop, phase
    FROM analysis
    WHERE is_user = 1 AND classification != 'good'
    ORDER BY eval_drop DESC
    LIMIT 10
""")
worst_moves = cursor.fetchall()

conn.close()

# ── Attach stats to game data ──

for g in games_data:
    m = mistakes_by_game.get(g["file"], {"blunder": 0, "mistake": 0, "inaccuracy": 0})
    g["blunders"] = m["blunder"]
    g["mistakes"] = m["mistake"]
    g["inaccuracies"] = m["inaccuracy"]
    g["accuracy"] = accuracy_by_game.get(g["file"], 0)

# ── Compute stats ──

total = len(games_data)
wins = sum(1 for g in games_data if g["result"] == "win")
losses = sum(1 for g in games_data if g["result"] == "loss")
draws = sum(1 for g in games_data if g["result"] == "draw")

white_games = [g for g in games_data if g["color"] == "white"]
black_games = [g for g in games_data if g["color"] == "black"]

avg_accuracy = round(sum(g["accuracy"] for g in games_data) / total, 1) if total else 0

# Opening stats
opening_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "draws": 0, "total": 0})
for g in games_data:
    o = g["opening"]
    opening_stats[o]["total"] += 1
    key = g["result"] + "s" if g["result"] != "loss" else "losses"
    opening_stats[o][key] += 1

top_openings = sorted(opening_stats.items(), key=lambda x: x[1]["total"], reverse=True)[:10]

# Rating range
ratings = [g["rating"] for g in games_data]
rating_min = min(ratings)
rating_max = max(ratings)

# Phase data for chart
phases_order = ["opening", "middlegame", "endgame"]
phase_labels = json.dumps(["Opening", "Middlegame", "Endgame"])
phase_accuracy_data = json.dumps([phase_stats.get(p, {}).get("accuracy", 0) for p in phases_order])
phase_blunders = json.dumps([phase_mistakes.get(p, {}).get("blunder", 0) for p in phases_order])
phase_mistakes_data = json.dumps([phase_mistakes.get(p, {}).get("mistake", 0) for p in phases_order])
phase_inaccuracies = json.dumps([phase_mistakes.get(p, {}).get("inaccuracy", 0) for p in phases_order])

# ── Build HTML ──

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chess Dashboard — {USERNAME}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: #0f0f0f;
    color: #e0e0e0;
    padding: 24px;
    max-width: 1400px;
    margin: 0 auto;
}}
h1 {{
    font-size: 28px;
    margin-bottom: 4px;
    color: #fff;
}}
.subtitle {{
    color: #888;
    margin-bottom: 32px;
    font-size: 14px;
}}
.stats-row {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
}}
.stat-card {{
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}}
.stat-card .value {{
    font-size: 32px;
    font-weight: 700;
    color: #fff;
}}
.stat-card .label {{
    font-size: 12px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 4px;
}}
.stat-card.win .value {{ color: #4ade80; }}
.stat-card.loss .value {{ color: #f87171; }}
.stat-card.draw .value {{ color: #fbbf24; }}
.stat-card.rating .value {{ color: #60a5fa; }}
.stat-card.accuracy .value {{ color: #a78bfa; }}

.grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-bottom: 24px;
}}
.grid.full {{
    grid-template-columns: 1fr;
}}
.card {{
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 24px;
}}
.card h2 {{
    font-size: 16px;
    color: #ccc;
    margin-bottom: 16px;
    font-weight: 600;
}}
.chart-container {{
    position: relative;
    height: 300px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
}}
th {{
    text-align: left;
    color: #888;
    font-weight: 500;
    padding: 8px 12px;
    border-bottom: 1px solid #2a2a2a;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
td {{
    padding: 10px 12px;
    border-bottom: 1px solid #1f1f1f;
}}
tr:hover td {{
    background: #222;
}}
.badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
}}
.badge.blunder {{ background: #991b1b; color: #fca5a5; }}
.badge.mistake {{ background: #92400e; color: #fcd34d; }}
.badge.inaccuracy {{ background: #1e3a5f; color: #93c5fd; }}
.badge.win {{ background: #14532d; color: #86efac; }}
.badge.loss {{ background: #7f1d1d; color: #fca5a5; }}
.badge.draw {{ background: #713f12; color: #fde68a; }}
.bar-container {{
    display: flex;
    align-items: center;
    gap: 8px;
}}
.bar {{
    height: 8px;
    border-radius: 4px;
    min-width: 2px;
}}
.bar.win-bar {{ background: #4ade80; }}
.bar.loss-bar {{ background: #f87171; }}
.bar.draw-bar {{ background: #fbbf24; }}
.phase-card {{
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 16px;
    background: #222;
    border-radius: 8px;
    flex: 1;
}}
.phase-card .phase-name {{
    font-size: 14px;
    color: #aaa;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 1px;
}}
.phase-card .phase-accuracy {{
    font-size: 36px;
    font-weight: 700;
}}
.phase-card .phase-detail {{
    font-size: 12px;
    color: #666;
    margin-top: 4px;
}}
.phase-row {{
    display: flex;
    gap: 16px;
    margin-bottom: 16px;
}}

@media (max-width: 800px) {{
    .grid {{ grid-template-columns: 1fr; }}
    .phase-row {{ flex-direction: column; }}
}}
</style>
</head>
<body>

<h1>&#9816; {USERNAME}</h1>
<p class="subtitle">{total} games analyzed &middot; {games_data[0]['date'].replace('.', '/')} to {games_data[-1]['date'].replace('.', '/')} &middot; Rating {rating_min} &rarr; {rating_max}</p>

<div class="stats-row">
    <div class="stat-card"><div class="value">{total}</div><div class="label">Games</div></div>
    <div class="stat-card win"><div class="value">{wins}</div><div class="label">Wins</div></div>
    <div class="stat-card loss"><div class="value">{losses}</div><div class="label">Losses</div></div>
    <div class="stat-card draw"><div class="value">{draws}</div><div class="label">Draws</div></div>
    <div class="stat-card rating"><div class="value">{rating_max}</div><div class="label">Peak Rating</div></div>
    <div class="stat-card"><div class="value">{round(wins/total*100)}%</div><div class="label">Win Rate</div></div>
    <div class="stat-card accuracy"><div class="value">{avg_accuracy}%</div><div class="label">Avg Accuracy</div></div>
</div>

<div class="grid full">
    <div class="card">
        <h2>Rating Over Time</h2>
        <div class="chart-container"><canvas id="ratingChart"></canvas></div>
    </div>
</div>

<div class="grid full">
    <div class="card">
        <h2>Accuracy Over Time</h2>
        <div class="chart-container"><canvas id="accuracyChart"></canvas></div>
    </div>
</div>

<div class="grid full">
    <div class="card">
        <h2>Performance by Game Phase</h2>
        <div class="phase-row">
"""

# Phase summary cards
for phase in phases_order:
    ps = phase_stats.get(phase, {"accuracy": 0, "moves": 0, "acpl": 0})
    pm = phase_mistakes.get(phase, {"blunder": 0, "mistake": 0, "inaccuracy": 0})
    label = {"opening": "Opening", "middlegame": "Middlegame", "endgame": "Endgame"}[phase]
    # Color accuracy
    acc = ps["accuracy"]
    if acc >= 70:
        color = "#4ade80"
    elif acc >= 50:
        color = "#fbbf24"
    else:
        color = "#f87171"
    total_mistakes = pm["blunder"] + pm["mistake"] + pm["inaccuracy"]
    html += f"""
            <div class="phase-card">
                <div class="phase-name">{label}</div>
                <div class="phase-accuracy" style="color:{color}">{acc}%</div>
                <div class="phase-detail">{ps['moves']} moves &middot; {ps['acpl']} ACPL</div>
                <div class="phase-detail">{pm['blunder']}B / {pm['mistake']}M / {pm['inaccuracy']}I</div>
            </div>"""

html += """
        </div>
        <div class="chart-container"><canvas id="phaseChart"></canvas></div>
    </div>
</div>

<div class="grid">
    <div class="card">
        <h2>Results</h2>
        <div class="chart-container"><canvas id="resultsChart"></canvas></div>
    </div>
    <div class="card">
        <h2>Your Mistakes Per Game</h2>
        <div class="chart-container"><canvas id="mistakesChart"></canvas></div>
    </div>
</div>

<div class="grid">
    <div class="card">
        <h2>Performance by Color</h2>
        <div class="chart-container"><canvas id="colorChart"></canvas></div>
    </div>
    <div class="card">
        <h2>Top Openings</h2>
        <table>
            <thead><tr><th>Opening</th><th>Games</th><th>Results</th></tr></thead>
            <tbody>
"""

for name, stats in top_openings:
    display_name = name[:40] + "..." if len(name) > 40 else name
    w, l, d = stats["wins"], stats["losses"], stats["draws"]
    t = stats["total"]
    max_bar = max(t, 1)
    html += f"""<tr>
        <td>{display_name}</td>
        <td>{t}</td>
        <td>
            <div class="bar-container">
                <div class="bar win-bar" style="width:{w/max_bar*80}px"></div>
                <div class="bar loss-bar" style="width:{l/max_bar*80}px"></div>
                <div class="bar draw-bar" style="width:{d/max_bar*80}px"></div>
                <span style="font-size:12px;color:#888">{w}W {l}L {d}D</span>
            </div>
        </td>
    </tr>"""

html += """
            </tbody>
        </table>
    </div>
</div>

<div class="grid full">
    <div class="card">
        <h2>Your Worst Moves</h2>
        <table>
            <thead><tr><th>Game</th><th>Move #</th><th>Move</th><th>Phase</th><th>Type</th><th>Eval Drop</th></tr></thead>
            <tbody>
"""

for game_file, move_num, player, move, classification, drop, phase in worst_moves:
    phase_label = phase.capitalize() if phase else "?"
    html += f"""<tr>
        <td>{game_file}</td>
        <td>{move_num}</td>
        <td style="font-family:monospace;font-weight:600">{move}</td>
        <td>{phase_label}</td>
        <td><span class="badge {classification}">{classification}</span></td>
        <td style="color:#f87171;font-weight:600">-{drop:.1f}</td>
    </tr>"""

html += """
            </tbody>
        </table>
    </div>
</div>

<div class="grid full">
    <div class="card">
        <h2>All Games</h2>
        <table>
            <thead><tr><th>#</th><th>Date</th><th>Color</th><th>Rating</th><th>Opp.</th><th>Result</th><th>Accuracy</th><th>Opening</th><th>Blunders</th><th>Mistakes</th><th>Moves</th></tr></thead>
            <tbody>
"""

for i, g in enumerate(games_data, 1):
    result_badge = f'<span class="badge {g["result"]}">{g["result"]}</span>'
    opening_short = g["opening"][:30] + "..." if len(g["opening"]) > 30 else g["opening"]
    acc = g["accuracy"]
    if acc >= 70:
        acc_color = "#4ade80"
    elif acc >= 50:
        acc_color = "#fbbf24"
    else:
        acc_color = "#f87171"
    html += f"""<tr>
        <td>{i}</td>
        <td>{g['date'].replace('.', '/')}</td>
        <td>{'&#9817;' if g['color'] == 'white' else '&#9823;'} {g['color']}</td>
        <td>{g['rating']}</td>
        <td>{g['opponent_rating']}</td>
        <td>{result_badge}</td>
        <td style="color:{acc_color};font-weight:600">{acc}%</td>
        <td>{opening_short}</td>
        <td style="color:#f87171">{g['blunders'] or '-'}</td>
        <td style="color:#fbbf24">{g['mistakes'] or '-'}</td>
        <td>{g['moves']}</td>
    </tr>"""

html += """
            </tbody>
        </table>
    </div>
</div>

<script>
Chart.defaults.color = '#888';
Chart.defaults.borderColor = '#2a2a2a';
"""

# Rating chart data
labels_rating = json.dumps([g["date"].replace(".", "/") for g in games_data])
values_rating = json.dumps([g["rating"] for g in games_data])
results_colors = json.dumps(["#4ade80" if g["result"] == "win" else "#f87171" if g["result"] == "loss" else "#fbbf24" for g in games_data])

html += f"""
new Chart(document.getElementById('ratingChart'), {{
    type: 'line',
    data: {{
        labels: {labels_rating},
        datasets: [{{
            label: 'Rating',
            data: {values_rating},
            borderColor: '#60a5fa',
            backgroundColor: 'rgba(96,165,250,0.1)',
            fill: true,
            tension: 0.3,
            pointBackgroundColor: {results_colors},
            pointRadius: 5,
            pointHoverRadius: 7,
        }}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
            legend: {{ display: false }},
            tooltip: {{
                callbacks: {{
                    afterLabel: function(ctx) {{
                        const results = {json.dumps([g["result"] for g in games_data])};
                        return results[ctx.dataIndex];
                    }}
                }}
            }}
        }},
        scales: {{
            x: {{ display: false }},
            y: {{ grid: {{ color: '#1f1f1f' }} }}
        }}
    }}
}});
"""

# Accuracy over time chart
accuracy_values = json.dumps([g["accuracy"] for g in games_data])
accuracy_colors = json.dumps(["#4ade80" if g["accuracy"] >= 70 else "#fbbf24" if g["accuracy"] >= 50 else "#f87171" for g in games_data])

html += f"""
new Chart(document.getElementById('accuracyChart'), {{
    type: 'line',
    data: {{
        labels: {labels_rating},
        datasets: [{{
            label: 'Accuracy %',
            data: {accuracy_values},
            borderColor: '#a78bfa',
            backgroundColor: 'rgba(167,139,250,0.1)',
            fill: true,
            tension: 0.3,
            pointBackgroundColor: {accuracy_colors},
            pointRadius: 5,
            pointHoverRadius: 7,
        }}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{
            legend: {{ display: false }},
            tooltip: {{
                callbacks: {{
                    afterLabel: function(ctx) {{
                        const results = {json.dumps([g["result"] for g in games_data])};
                        return results[ctx.dataIndex] + ' — ' + ctx.raw + '% accuracy';
                    }}
                }}
            }}
        }},
        scales: {{
            x: {{ display: false }},
            y: {{ min: 0, max: 100, grid: {{ color: '#1f1f1f' }} }}
        }}
    }}
}});
"""

# Phase breakdown chart (stacked bar)
html += f"""
new Chart(document.getElementById('phaseChart'), {{
    type: 'bar',
    data: {{
        labels: {phase_labels},
        datasets: [
            {{ label: 'Blunders', data: {phase_blunders}, backgroundColor: '#f87171' }},
            {{ label: 'Mistakes', data: {phase_mistakes_data}, backgroundColor: '#fbbf24' }},
            {{ label: 'Inaccuracies', data: {phase_inaccuracies}, backgroundColor: '#60a5fa' }},
        ]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'bottom' }} }},
        scales: {{
            x: {{ grid: {{ display: false }} }},
            y: {{ stacked: true, grid: {{ color: '#1f1f1f' }} }}
        }}
    }}
}});
"""

# Results pie chart
html += f"""
new Chart(document.getElementById('resultsChart'), {{
    type: 'doughnut',
    data: {{
        labels: ['Wins', 'Losses', 'Draws'],
        datasets: [{{
            data: [{wins}, {losses}, {draws}],
            backgroundColor: ['#4ade80', '#f87171', '#fbbf24'],
            borderWidth: 0,
        }}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        cutout: '65%',
        plugins: {{
            legend: {{ position: 'bottom' }}
        }}
    }}
}});
"""

# Mistakes per game chart (user only)
game_labels = json.dumps([f"G{i+1}" for i in range(len(games_data))])
blunders_data = json.dumps([g["blunders"] for g in games_data])
mistakes_data = json.dumps([g["mistakes"] for g in games_data])
inaccuracies_data = json.dumps([g["inaccuracies"] for g in games_data])

html += f"""
new Chart(document.getElementById('mistakesChart'), {{
    type: 'bar',
    data: {{
        labels: {game_labels},
        datasets: [
            {{ label: 'Blunders', data: {blunders_data}, backgroundColor: '#f87171' }},
            {{ label: 'Mistakes', data: {mistakes_data}, backgroundColor: '#fbbf24' }},
            {{ label: 'Inaccuracies', data: {inaccuracies_data}, backgroundColor: '#60a5fa' }},
        ]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'bottom' }} }},
        scales: {{
            x: {{ stacked: true, display: false }},
            y: {{ stacked: true, grid: {{ color: '#1f1f1f' }} }}
        }}
    }}
}});
"""

# Color performance chart
white_w = sum(1 for g in white_games if g["result"] == "win")
white_l = sum(1 for g in white_games if g["result"] == "loss")
white_d = sum(1 for g in white_games if g["result"] == "draw")
black_w = sum(1 for g in black_games if g["result"] == "win")
black_l = sum(1 for g in black_games if g["result"] == "loss")
black_d = sum(1 for g in black_games if g["result"] == "draw")

html += f"""
new Chart(document.getElementById('colorChart'), {{
    type: 'bar',
    data: {{
        labels: ['White ({len(white_games)} games)', 'Black ({len(black_games)} games)'],
        datasets: [
            {{ label: 'Wins', data: [{white_w}, {black_w}], backgroundColor: '#4ade80' }},
            {{ label: 'Losses', data: [{white_l}, {black_l}], backgroundColor: '#f87171' }},
            {{ label: 'Draws', data: [{white_d}, {black_d}], backgroundColor: '#fbbf24' }},
        ]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'bottom' }} }},
        scales: {{
            y: {{ grid: {{ color: '#1f1f1f' }} }}
        }}
    }}
}});
"""

html += """
</script>
</body>
</html>
"""

with open(OUTPUT, "w") as f:
    f.write(html)

print(f"Dashboard written to {OUTPUT}")
print(f"Open it with: open {OUTPUT}")
