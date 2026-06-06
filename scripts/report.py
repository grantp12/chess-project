import sqlite3

conn = sqlite3.connect("chess.db")
cursor = conn.cursor()

print("\n===== CHESS ANALYSIS REPORT =====\n")

# Total analyzed moves
cursor.execute("SELECT COUNT(*) FROM analysis")
total_events = cursor.fetchone()[0]
print(f"Total moves analyzed: {total_events}")

cursor.execute("SELECT COUNT(*) FROM analysis WHERE is_user = 1")
user_moves = cursor.fetchone()[0]
print(f"Your moves: {user_moves}")

# Accuracy (win%-based per-move accuracy and capped centipawn loss, from analysis)
cursor.execute("""
    SELECT AVG(accuracy), AVG(cpl)
    FROM analysis WHERE is_user = 1
""")
avg_acc, avg_cpl = cursor.fetchone()
print(f"Overall accuracy: {(avg_acc or 0):.1f}%")
print(f"Average centipawn loss: {(avg_cpl or 0):.0f}")

print("\n--- Your Mistakes by Classification ---")

cursor.execute("""
    SELECT classification, COUNT(*)
    FROM analysis
    WHERE is_user = 1 AND classification != 'good'
    GROUP BY classification
    ORDER BY COUNT(*) DESC
""")
for classification, count in cursor.fetchall():
    print(f"  {classification}: {count}")

print("\n--- Your Accuracy by Phase ---")

cursor.execute("""
    SELECT phase, AVG(accuracy), AVG(cpl), COUNT(*)
    FROM analysis
    WHERE is_user = 1
    GROUP BY phase
    ORDER BY CASE phase WHEN 'opening' THEN 1 WHEN 'middlegame' THEN 2 ELSE 3 END
""")
for phase, avg_acc, avg_cpl, count in cursor.fetchall():
    print(f"  {phase:12s}: {(avg_acc or 0):.1f}% accuracy ({count} moves, {(avg_cpl or 0):.0f} ACPL)")

print("\n--- Your Worst Moves ---")

cursor.execute("""
    SELECT game_file, move_number, move, eval_drop, phase
    FROM analysis
    WHERE is_user = 1 AND classification != 'good'
    ORDER BY eval_drop DESC
    LIMIT 5
""")
for game, move_num, move, drop, phase in cursor.fetchall():
    print(f"  {game} Move {move_num}: {move} (-{drop:.2f}) [{phase}]")

print("\n===== END REPORT =====\n")

conn.close()
