import os
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from stockfish import Stockfish
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import re
import chess
from scrappy import getAvatars
from google.cloud import firestore
from Instance.instance import instance_info, get_instance_info
from ev import analyze
import hashlib
from datetime import datetime

first_moves = [
    "1. e4", "1. d4", "1. Nf3", "1. Nc3", "1. Bc4", "1. Bf4", "1. g3", "1. b3", "1. f4", "1. c4",
    "1. a3", "1. a4", "1. b4", "1. c3", "1. d3", "1. e3", "1. f3", "1. h3", "1. h4", "1. Na3", "1. Nh3"
]

gamestart = ["Game is still ongoing", "is playing"]


GCP_PROJECT = os.getenv('GCP_PROJECT_ID')
STOCKFISH_PATH = os.getenv('STOCKFISH_PATH') or 'stockfish'
DESCRIPTION = """
This API takes a chess game and returns the
best next move. This is designed to give move advice for and active lichess game
with the url template of: https://lichess.org/<gameid>
"""
db = firestore.Client(project=GCP_PROJECT)

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

def filter_dict(original_dict, keys_to_keep):
    return {key: original_dict[key] for key in keys_to_keep if key in original_dict}

@app.get('/', tags=['Default'])
def index():

    return {'message': 'Welcome to stockfish chess helper API.'}


@app.get('/suggest-move/{gameid}', tags=['Chess Engine'])
async def suggest_move(gameid: str, time: str | None = None):

    board_fen = scrape_kwdb_text(gameid)
    gotime = 1000
    if time:
        gotime = 500
    if isinstance(board_fen, str):
        return { "nodata": "unable to read fen or stockfish error" }
    k = board_fen.fen()
    res = instance_info.get_info(k)
    if res and ("data" in res or "board" in res or "turn" in res):
        return filter_dict(res, ["data", "board", "turn"])

    stockfish = Stockfish(path=STOCKFISH_PATH, parameters={"Threads": 2, "Ponder": "true"})
    stockfish.set_depth(20)  

    stockfish.set_fen_position(k)
    
    stockfish._go_time(gotime)
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
            if res:
                res.update({"data": last_text, "board": str(result), "turn": whosturn })
                instance_info.set_info(k, res)
            else:
                instance_info.set_info(k, {"data": last_text, "board": str(result), "turn": whosturn })
            gameid_ref = db.collection("gamecollection")
            gdoc_ref = gameid_ref.document(gameid + "-lichess")
            now = datetime.now()

# Get the current date in ISO format
            iso_date = now.date().isoformat()
            gdoc_ref.set({"info": iso_date})
            return {"data": last_text, "board": str(result), "turn": whosturn }
    except:
        if res:
            res.update({"data": last_text})
            instance_info.set_info(k, res)
        else:
            instance_info.set_info(k, {"data": last_text})
        if last_text:
            gameid_ref = db.collection("gamecollection")
            gdoc_ref = gameid_ref.document(gameid + "-lichess")
            now = datetime.now()
            iso_date = now.date().isoformat()
            gdoc_ref.set({"info": iso_date})
        return {"data": last_text }

@app.get('/chesscom/')
async def chessdotcom(moves: str = Query(None), time: str = Query(None)):
    if moves:
        try:
            board_fen = None
            gotime = 1000
            if time:
                gotime = 500
            if "newgame" in moves:
                board_fen = generate_fen(None)
            str_with_sp = moves.replace("%20", " ")
            formatted = str_with_sp.split(" ")
            gameid = formatted[-1:][0]
            intcheck = False
            try:
                int(gameid)
                intcheck = True
            except:
                print("no chess.com gameid found")
            if len(gameid) > 9 and intcheck:
                formatted.pop()
            else:
                gameid = None
            if len(formatted) > 0 and "newgame" not in moves:
                board_fen = generate_fen(formatted)
            if not isinstance(board_fen, str):
                k = board_fen.fen()
                res = instance_info.get_info(k)
                if res and ("data" in res or "board" in res or "turn" in res):
                    return filter_dict(res, ["data", "board", "turn"])

                stockfish = Stockfish(path=STOCKFISH_PATH, parameters={"Threads": 2, "Ponder": "true"})
                stockfish.set_depth(20)  

                stockfish.set_fen_position(k)
                
                stockfish._go_time(gotime)
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
                        if res:
                            res.update({"data": last_text, "board": str(result), "turn": whosturn })
                            instance_info.set_info(k, res)
                        else:
                            instance_info.set_info(k, {"data": last_text, "board": str(result), "turn": whosturn })
                        if gameid:
                            gameid_ref = db.collection("gamecollection")
                            gdoc_ref = gameid_ref.document(gameid + "-chesscom")
                            now = datetime.now()

# Get the current date in ISO format
                            iso_date = now.date().isoformat()
                            gdoc_ref.set({"info": iso_date})
                        return {"data": last_text, "board": str(result), "turn": whosturn }
                except:
                    if res:
                        res.update({"data": last_text})
                        instance_info.set_info(k, res)
                    else:
                        instance_info.set_info(k, {"data": last_text})
                    if last_text and gameid:
                        gameid_ref = db.collection("gamecollection")
                        gdoc_ref = gameid_ref.document(gameid + "-chesscom")
                        now = datetime.now()
                        iso_date = now.date().isoformat()
                        gdoc_ref.set({"info": iso_date})
                    return {"data": last_text }
            return { "nodata": "error with stockfish getting moves from move list" }
        except:
            return { "nodata": "error reading query param string" }
    return { "nodata": "no move list sent to server"}

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

# @app.get('/get-avatars', tags=['urls'])
# async def get_urls():
#     getAvatars()
#     return {}

@app.post('/set-avatar')
async def set_avatar(user: UserBody):
    collection_ref = db.collection("chessextension")
    if user.user and user.img:
      doc_ref = collection_ref.document(user.user)
  
      doc_ref.set({"user": user.user, "img": user.img})
      return { "data": f"document set for {user.user}"}
    else:
        return { "nodata": "missing username string and image string" }

@app.get('/get-useravatar/{username}', tags=['fetch avatar'])
async def get_useravatar(username: str):
    doc_ref = db.collection(u'chessextension').document(username)
    doc = doc_ref.get()

    if doc.exists:
        data = doc.to_dict()
        return data
    else:
        return { "nodata": "user not found" }

@app.get('/winning/{gameid}', tags=['Winning Percentage'])
async def winning_perc(gameid: str):
    return {}
    board_fen = scrape_kwdb_text(gameid)
    if isinstance(board_fen, str):
        return { "nodata": "unable to read fen or stockfish error" }
    k = board_fen.fen()
    res = instance_info.get_info(k)
    if res and ('winning' in res):
        return res.get("winning")
    try:
        shorth = hashlib.sha256(k.encode()).hexdigest()
        shorth = shorth[:10]
        analyze(STOCKFISH_PATH, 1, 64, k, 2, 20, shorth)
        winobj = instance_info.get_info(shorth)
        if res and winobj:
            res["winning"] = winobj
            instance_info.set_info(k, res)
        elif not res and winobj:
            instance_info.set_info(k, { "winning": winobj })
        if winobj:
            return winobj
        else: return {"nodata": "error setting Instance object"}
    except:
        return {"nodata": "error getting winning percentage"}
