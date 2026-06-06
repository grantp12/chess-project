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
    is_user INTEGER,
    move TEXT,
    classification TEXT,
    eval_drop REAL,
    eval_before REAL,
    eval_after REAL,
    cpl REAL,
    accuracy REAL,
    phase TEXT
)
""")

conn.commit()
conn.close()

print("Database initialized")
