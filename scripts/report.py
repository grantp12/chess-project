import sqlite3

conn = sqlite3.connect("chess.db")
cursor = conn.cursor()

print("\n===== CHESS ANALYSIS REPORT =====\n")

# Total analyzed moves
cursor.execute("SELECT COUNT(*) FROM analysis")
total_events = cursor.fetchone()[0]
print(f"Total classified moves: {total_events}")

print("\n--- Mistakes by Player ---")

cursor.execute("""
SELECT player, classification, COUNT(*)
FROM analysis
GROUP BY player, classification
ORDER BY player
""")

rows = cursor.fetchall()

for player, classification, count in rows:
    print(f"{player} {classification}: {count}")

print("\n--- Worst Moves (Largest Eval Drops) ---")

cursor.execute("""
SELECT game_file, move_number, move, eval_drop
FROM analysis
ORDER BY eval_drop DESC
LIMIT 5
""")

worst_moves = cursor.fetchall()

for game, move_num, move, drop in worst_moves:
    print(f"{game} Move {move_num}: {move} ({drop:.2f})")

print("\n--- Average Evaluation Drop ---")

cursor.execute("""
SELECT AVG(eval_drop) FROM analysis
""")

avg_drop = cursor.fetchone()[0]

if avg_drop:
    print(f"Average evaluation loss per mistake: {avg_drop:.2f}")

print("\n--- Most Common Blunder Move ---")

cursor.execute("""
SELECT move, COUNT(*)
FROM analysis
WHERE classification='blunder'
GROUP BY move
ORDER BY COUNT(*) DESC
LIMIT 1
""")

result = cursor.fetchone()

if result:
    move, count = result
    print(f"{move} occurred {count} times")

print("\n===== END REPORT =====\n")

conn.close()