import requests
import os

USERNAME = "Tonymontana013"
BASE_DIR = "games"
os.makedirs(BASE_DIR, exist_ok=True)

# Get archive URLs
url = f"https://api.chess.com/pub/player/{USERNAME}/games/archives"
headers = {"User-Agent": "chess-analytics-bot"}
response = requests.get(url, headers=headers)
archives = response.json()["archives"]

game_count = 0

for archive_url in archives:
    r = requests.get(archive_url, headers=headers)
    data = r.json()
    games = data["games"]
    for game in games:
        # Save PGN text
        if "pgn" in game:
            game_count += 1
            filename = os.path.join(BASE_DIR, f"game_{game_count}.pgn")
            with open(filename, "w") as f:
                f.write(game["pgn"])

print(f"Downloaded {game_count} games into {BASE_DIR}/")