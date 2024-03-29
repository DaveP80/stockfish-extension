import os
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from stockfish import Stockfish
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import re
import chess

first_moves = [
    "1. e4", "1. d4", "1. Nf3", "1. Nc3", "1. Bc4", "1. Bf4", "1. g3", "1. b3", "1. f4", "1. c4",
    "1. a3", "1. a4", "1. b4", "1. c3", "1. d3", "1. e3", "1. f3", "1. h3", "1. h4", "1. Na3", "1. Nh3"
]

gamestart = ["Game is still ongoing", "is playing"]

STOCKFISH_PATH = os.getenv('STOCKFISH_PATH') or 'stockfish'
DESCRIPTION = """
This API takes a chess game and returns the
best next move. This is designed to give move advice for and active lichess game
with the url template of: https://lichess.org/<gameid>
"""
app = FastAPI(
    title='lichess helper',
    description=DESCRIPTION,
    version='1.0.0'
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

class UserBody(BaseModel):
    user: str
    img: str

def check_substrings(text_blob, substrings):
    for substring in substrings:
        if substring.lower() in text_blob.lower():
            return True
    return False

def extract_chess_moves(text_blob):

    match = None
    for fm in first_moves:
        match = re.search(f"({fm}[^\*]+)|({fm}\*)", text_blob)
        if match:
            break
    if match:
        return match.group()
    else:
        return ""

def generate_fen(moves):
    board = chess.Board()
    try:
        if moves:
            for move in moves:
                board.push_san(move)
            return board
        else: return board
    except:
        return ""

def scrape_kwdb_text(args):
    response = requests.get(f"https://lichess.org/{args}")
    if response.status_code == 200:
        chess_moves = extract_chess_moves(response.text)
        if len(chess_moves) > 0:
            l = chess_moves.split(" ")
            pattern = r'^\d+\.$|^$'

            filtered_notations = [item for item in l if not re.match(pattern, item)]
            if len(filtered_notations) > 0:
                fengen = generate_fen(filtered_notations)
                if not isinstance(fengen, str):
                    return fengen
        elif len(chess_moves) == 0 and check_substrings(response.text, gamestart):
            newgame = generate_fen(None)
            return newgame
    return ""

@app.get('/', tags=['Default'])
def index():

    return {'message': 'Welcome to stockfish chess helper API.'}


@app.get('/suggest-move/{gameid}', tags=['Chess Engine'])
async def suggest_move(gameid: str):

    board_fen = scrape_kwdb_text(gameid)
    if isinstance(board_fen, str):
        return { "nodata": "unable to read fen or stockfish error" }

    stockfish = Stockfish(path=STOCKFISH_PATH, parameters={"Threads": 2, "Ponder": "true"})
    stockfish.set_depth(20)  

    stockfish.set_fen_position(board_fen.fen())
    stockfish._go_time(1000)
    movetopush = ""
    last_text = ""
    count = 0
    while True:
        if count > 5000:
            break
        text = stockfish._read_line()
        splitted_text = text.split(" ")
        if splitted_text[0] == "bestmove":
            stockfish.info = last_text
            last_text = None if splitted_text[1] == "(none)" else " ".join(splitted_text)
            if last_text != None:
                movetopush = splitted_text[1]
            break
        last_text = text
        count += 1
    if count > 4999 or last_text == None:
        return { "nodata": "unable to read fen or stockfish error" } 
    try:
        if movetopush != "":
            whosturn = "white"
            if board_fen.turn != chess.WHITE:
                whosturn = "black"
            move = chess.Move.from_uci(movetopush)
            board_fen.push(move)
            boardstr = board_fen.fen()
            result = chess.Board(boardstr)
            return {"data": last_text, "board": str(result), "turn": whosturn }
    except:
        return {"data": last_text }

@app.get("/evaluation/")
async def eval_fen(fen: str = Query(None)):
    if fen:
        try:
            stockfish = Stockfish(path=STOCKFISH_PATH, parameters={"Threads": 3, "Ponder": "true"})
            stockfish.set_depth(20)
            fen.replace("%20", " ")

            stockfish.set_fen_position(fen)
            stockfish._go_time(1300)
            last_text = ""
            count = 0
            while True:
                if count > 5000:
                    break
                text = stockfish._read_line()
                splitted_text = text.split(" ")
                if splitted_text[0] == "bestmove":
                    stockfish.info = last_text
                    last_text = None if splitted_text[1] == "(none)" else " ".join(splitted_text)
                    break
                last_text = text
                count += 1
            if count > 4999 or last_text == None:
                return { "nodata": "unable to read fen or stockfish error" } 

            evalboard = chess.Board(fen)
            return {"data": last_text, "board": str(evalboard) }
        except:
            return { "nodata": "bad fen string"}
    else:
        return {"message": "No query parameter provided"}
