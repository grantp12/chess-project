import os
import sqlite3
import chess
import chess.pgn
from stockfish import Stockfish

USERNAME = "Tonymontana013"
BASE_DIR = "games"
STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"
MATE_SCORE = 100  # treat mate as +/- 100 pawns

conn = sqlite3.connect("chess.db")
cursor = conn.cursor()

# Clear old analysis to avoid duplicates on re-run
cursor.execute("DELETE FROM analysis")
conn.commit()

stockfish = Stockfish(STOCKFISH_PATH)
stockfish.set_depth(18)
stockfish.update_engine_parameters({
    "Threads": 2,
    "Hash": 256
})

def get_phase(move_number):
    """Classify move into game phase."""
    if move_number <= 15:
        return "opening"
    elif move_number <= 30:
        return "middlegame"
    else:
        return "endgame"

for filename in sorted(os.listdir(BASE_DIR), key=lambda f: int(f.replace("game_", "").replace(".pgn", ""))):
    if not filename.endswith(".pgn"):
        continue

    filepath = os.path.join(BASE_DIR, filename)

    with open(filepath) as f:
        game = chess.pgn.read_game(f)

    if game is None:
        continue

    print(f"Analyzing {filename}")

    # Determine which color the user is playing
    headers = game.headers
    user_is_white = headers.get("White", "") == USERNAME

    board = game.board()
    previous_eval = None
    move_number = 1

    for move in game.mainline_moves():
        # Determine who just moved (before pushing)
        is_white_move = board.turn == chess.WHITE

        board.push(move)

        stockfish.set_fen_position(board.fen())
        eval_score = stockfish.get_evaluation()

        # Convert eval to white's perspective in pawns
        if eval_score["type"] == "cp":
            current_eval = eval_score["value"] / 100
        elif eval_score["type"] == "mate":
            mate_in = eval_score["value"]
            if mate_in > 0:
                current_eval = MATE_SCORE
            elif mate_in < 0:
                current_eval = -MATE_SCORE
            else:
                current_eval = 0
        else:
            move_number += 1
            continue

        player = "white" if is_white_move else "black"
        is_user = 1 if (is_white_move == user_is_white) else 0
        phase = get_phase(move_number)

        if previous_eval is not None:
            # Eval drop from the moving player's perspective
            if is_white_move:
                drop = previous_eval - current_eval
            else:
                drop = current_eval - previous_eval

            classification = None
            if drop > 2:
                classification = "blunder"
            elif drop > 1:
                classification = "mistake"
            elif drop > 0.5:
                classification = "inaccuracy"
            else:
                classification = "good"

            if classification != "good":
                print(f"  Move {move_number}: {move} {classification} ({drop:.2f}) by {player}")

            cursor.execute("""
                INSERT INTO analysis (game_file, move_number, player, is_user, move, classification, eval_drop, eval_before, eval_after, phase)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (filename, move_number, player, is_user, str(move), classification, drop, previous_eval, current_eval, phase))

        previous_eval = current_eval
        move_number += 1

conn.commit()
conn.close()
print("Analysis complete.")
