import os
import sqlite3
import chess
import chess.pgn
from stockfish import Stockfish

BASE_DIR = "games"
STOCKFISH_PATH = "/opt/homebrew/bin/stockfish"

conn = sqlite3.connect("chess.db")
cursor = conn.cursor()

stockfish = Stockfish(STOCKFISH_PATH)
stockfish.set_depth(18)
stockfish.update_engine_parameters({
    "Threads": 2,
    "Hash": 256
})
for filename in os.listdir(BASE_DIR):

    if filename.endswith(".pgn"):

        filepath = os.path.join(BASE_DIR, filename)

        with open(filepath) as f:
            game = chess.pgn.read_game(f)

        print(f"Analyzing {filename}")

        board = game.board()

        previous_eval = None
        move_number = 1

        for move in game.mainline_moves():

            board.push(move)

            stockfish.set_fen_position(board.fen())
            eval_score = stockfish.get_evaluation()

            if eval_score["type"] != "cp":
                continue

            current_eval = eval_score["value"] / 100

            if previous_eval is not None:

                drop = previous_eval - current_eval
                classification = None

                if drop > 2:
                    classification = "blunder"

                elif drop > 1:
                    classification = "mistake"

                elif drop > 0.5:
                    classification = "inaccuracy"

                if classification:

                    player = "white" if move_number % 2 == 1 else "black"
 
                    print(f"{filename} Move {move_number}: {move} {classification} ({drop:.2f}) by {player}")

                    cursor.execute("""
                        INSERT INTO analysis (game_file, move_number, player, move, classification, eval_drop)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (filename, move_number, player, str(move), classification, drop))

            previous_eval = current_eval
            move_number += 1

conn.commit()
conn.close()