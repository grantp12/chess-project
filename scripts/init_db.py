import sqlite3

conn = sqlite3.connect("chess.db")
cursor = conn.cursor()

cursor.execute("DROP TABLE IF EXISTS analysis")
cursor.execute("""
CREATE TABLE analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_file TEXT,
    move_number INTEGER,
    player TEXT,
    move TEXT,
    classification TEXT,
    eval_drop REAL
)
""")

conn.commit()
conn.close()

print("Database initialized")
