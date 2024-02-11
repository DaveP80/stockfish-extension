import requests
from bs4 import BeautifulSoup
import re
import chess

first_moves = [
    "1. e4", "1. d4", "1. Nf3", "1. Nc3", "1. Bc4", "1. Bf4", "1. g3", "1. b3", "1. f4", "1. c4",
    "1. a3", "1. a4", "1. b4", "1. c3", "1. d3", "1. e3", "1. f3", "1. h3", "1. h4", "1. Na3", "1. Nh3"
]


def extract_chess_moves(text_blob):
    pattern = r'\b(?:' + '|'.join(re.escape(move) for move in first_moves) + r')\b'

    match = re.search(pattern, text_blob)
    if match:
        start_index = match.start()
        end_index = text_blob.find("*", start_index)  
        if end_index == -1:  
            end_index = len(text_blob)
        region = text_blob[start_index:end_index]
        return region
    else:
        return ""

def generate_fen(moves):
    board = chess.Board()
    for move in moves:
        board.push_san(move)
    return board.fen()

def scrape_kwdb_text(url):
    response = requests.get(url)
    if response.status_code == 200:
        chess_moves = extract_chess_moves(response.text)
        if len(chess_moves) > 0:
            l = chess_moves.split(" ")
            pattern = r'^\d+\.$|^$'

            filtered_notations = [item for item in l if not re.match(pattern, item)]
            if len(filtered_notations) > 1:
                fengen = generate_fen(filtered_notations)
                if len(fengen) > 5:
                    stockfish = requests.get(f"https://stockfish.online/api/stockfish.php?s=i&fen={fengen}&depth=5&mode=bestmove")
                    if stockfish.status_code == 200:
                        return stockfish.json()
                    else:
                        return { "error": "unable to reach stockfish api" }

        else: return { "error": "error parsing lichess page" }

    else:
        print("Error: Unable to fetch webpage")
        return { "error": "error parsing lichess page" }
