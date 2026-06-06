import os
import math
import sqlite3
import chess
import chess.pgn
from stockfish import Stockfish

USERNAME = "Tonymontana013"
BASE_DIR = "games"
STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"
MATE_SCORE = 100  # treat mate as +/- 100 pawns (win% formula saturates well before this)


def win_percent(cp):
    """Convert a centipawn eval (from the moving player's perspective) to a win
    probability in [0, 100] using Lichess's logistic model. This is what keeps a
    single mate from blowing up the averages: +1000cp and mate both map to ~100%,
    so the *difference* between them is tiny."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


conn = sqlite3.connect("chess.db")
cursor = conn.cursor()

# Clear old analysis to avoid duplicates on re-run
cursor.execute("DELETE FROM analysis")
conn.commit()

stockfish = Stockfish(STOCKFISH_PATH)
stockfish.set_depth(15)
# By default this library reports the eval from the side-to-move's perspective,
# which flips every ply and makes consecutive evals incomparable. Pin it to a
# stable White-POV frame instead.
stockfish.set_turn_perspective(False)
stockfish.update_engine_parameters({
    "Threads": 2,
    "Hash": 256
})

def get_phase(board):
    """Classify a position into a game phase from the material on the board.

    Non-pawn material is scored knight/bishop = 1, rook = 2, queen = 4 (24 at the
    start). The first 10 full moves are the opening; after that a queenless or
    low-material position is the endgame, otherwise the middlegame."""
    minors = (len(board.pieces(chess.KNIGHT, chess.WHITE)) + len(board.pieces(chess.KNIGHT, chess.BLACK))
              + len(board.pieces(chess.BISHOP, chess.WHITE)) + len(board.pieces(chess.BISHOP, chess.BLACK)))
    rooks = len(board.pieces(chess.ROOK, chess.WHITE)) + len(board.pieces(chess.ROOK, chess.BLACK))
    queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    material = minors + 2 * rooks + 4 * queens

    if board.fullmove_number <= 10:
        return "opening"
    elif queens == 0 or material <= 10:
        return "endgame"
    else:
        return "middlegame"

pgn_files = [f for f in os.listdir(BASE_DIR) if f.endswith(".pgn")]
for filename in sorted(pgn_files, key=lambda f: int(f.replace("game_", "").replace(".pgn", ""))):
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
    previous_eval = None  # White-POV eval (pawns) of the position before this move

    for move in game.mainline_moves():
        # Capture context from the position the move is played in (pre-push).
        is_white_move = board.turn == chess.WHITE
        move_no = board.fullmove_number
        move_san = board.san(move)
        phase = get_phase(board)

        board.push(move)

        stockfish.set_fen_position(board.fen())
        eval_score = stockfish.get_evaluation()

        # Eval after the move, normalized to White's perspective (pawns).
        if eval_score["type"] == "cp":
            current_eval = eval_score["value"] / 100
        elif eval_score["type"] == "mate":
            mate_in = eval_score["value"]
            if mate_in > 0:
                current_eval = MATE_SCORE
            elif mate_in < 0:
                current_eval = -MATE_SCORE
            else:
                # mate 0 == the side to move is checkmated on the board.
                current_eval = -MATE_SCORE if board.turn == chess.WHITE else MATE_SCORE
        else:
            previous_eval = None  # unknown eval; don't bridge a drop across the gap
            continue

        player = "white" if is_white_move else "black"
        is_user = 1 if (is_white_move == user_is_white) else 0

        if previous_eval is not None:
            # Evals from the moving player's perspective (pawns).
            if is_white_move:
                before_p, after_p = previous_eval, current_eval
            else:
                before_p, after_p = -previous_eval, -current_eval

            eval_drop = before_p - after_p  # > 0 means the move gave ground

            # Win-probability loss drives both accuracy and classification, so a
            # single mate (which saturates win%) can't dominate the averages.
            win_loss = max(0.0, win_percent(before_p * 100) - win_percent(after_p * 100))
            accuracy = max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * win_loss) - 3.1669))
            cpl = min(1000.0, max(0.0, eval_drop * 100))  # capped centipawn loss

            if win_loss >= 30:
                classification = "blunder"
            elif win_loss >= 20:
                classification = "mistake"
            elif win_loss >= 10:
                classification = "inaccuracy"
            else:
                classification = "good"

            if classification != "good":
                print(f"  Move {move_no}: {move_san} {classification} (-{win_loss:.0f}% win) by {player}")

            cursor.execute("""
                INSERT INTO analysis
                (game_file, move_number, player, is_user, move, classification,
                 eval_drop, eval_before, eval_after, cpl, accuracy, phase)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (filename, move_no, player, is_user, move_san, classification,
                  eval_drop, previous_eval, current_eval, cpl, accuracy, phase))

        previous_eval = current_eval

conn.commit()
conn.close()
print("Analysis complete.")
