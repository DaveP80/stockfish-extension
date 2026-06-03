import os
from fastapi import FastAPI, Query, HTTPException, Request
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
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
import subprocess
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

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

#Below setup is for local docker development
#db = firestore.Client()

app = FastAPI(
    title='lichess helper',
    description=DESCRIPTION,
    version='1.26.0'
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
#gotimes standard: 2000
#blitz: 1000
#classical: 5000

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
@limiter.limit("400/hour;20/minute")
async def suggest_move(request: Request, gameid: str, time: str | None = None):

    board_fen = scrape_kwdb_text(gameid)
    gotime = 2000
    if time:
        if time == "go":
            gotime = 500
        else:
            gotime = time
    if isinstance(board_fen, str):
        return { "nodata": "unable to read fen or stockfish error" }
    k = board_fen.fen()
    res = instance_info.get_info(k)
    if res and ("data" in res or "board" in res or "turn" in res or "evaluation" in res):
        return filter_dict(res, ["data", "board", "turn", "evaluation"])
    try:

        engine = subprocess.Popen('/usr/games/stockfish', universal_newlines=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        #stockfish.set_depth(22)  
        bestmove = "(none)"
        #evaluation
        ze = {"type": "cp", "value": 0}

        engine.stdin.write(f'position fen {k}\n')
        engine.stdin.write('setoption name Threads value 2\n')
        engine.stdin.flush()
        # Get engine move
        engine.stdin.write(f'go depth 22 movetime {gotime}\n')
        engine.stdin.flush()

        evalSign = 1 if "w" in k else -1
        # Process output
        while True:
            line = engine.stdout.readline()
            if not line:
                break
            line = line.strip()
            parts = line.split(" ")
            for i,j in enumerate(parts):

                if "score" == j:
                    if i + 2 < len(parts):
                        eval_type = parts[i + 1]   # "cp" or "mate"
                        eval_val_raw = parts[i + 2]
                        val = 0.00
                        try:
                            val = int(eval_val_raw)
                        except ValueError:
                            pass
                        if eval_type == "cp":
                            val *= evalSign  # make positive for side to move
                            ze = {"type": eval_type, "value": val}
                        if eval_type == "mate":
                            ze = {"type": eval_type, "value": eval_val_raw} 

            if parts and parts[0] == "bestmove":
                if len(parts) > 1:
                    bestmove = parts[1]
                break

        # Clean up the engine
        engine.stdin.write("quit\n")
        engine.stdin.flush()
        engine.wait()
        try:
            whosturn = "white"
            if board_fen.turn != chess.WHITE:
                whosturn = "black"
            if bestmove != "(none)":
                move = chess.Move.from_uci(bestmove)
                board_fen.push(move)
            boardstr = board_fen.fen()
            result = chess.Board(boardstr)
            if res:
                res.update({"data": bestmove, "board": str(result), "turn": whosturn, "evaluation": ze })
                instance_info.set_info(k, res)
            else:
                instance_info.set_info(k, {"data": bestmove, "board": str(result), "turn": whosturn, "evaluation": ze })
            gameid_ref = db.collection("gamecollection")
            gdoc_ref = gameid_ref.document(gameid + "-lichess")
            now = datetime.now()

# Get the current date in ISO format
            iso_date = now.date().isoformat()
            gdoc_ref.set({"info": iso_date})
            return {"data": bestmove, "board": str(result), "turn": whosturn, "evaluation": ze }
        except:
            if res:
                res.update({"data": bestmove, "evaluation": ze })
                instance_info.set_info(k, res)
            else:
                instance_info.set_info(k, {"data": bestmove, "evaluation": ze })
            if bestmove:
                gameid_ref = db.collection("gamecollection")
                gdoc_ref = gameid_ref.document(gameid + "-lichess")
                now = datetime.now()
                iso_date = now.date().isoformat()
                gdoc_ref.set({"info": iso_date})
            return {"data": bestmove, "evaluation": ze }
    except Exception as e:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="An internal server error occurred"
        )

@app.get('/chesscom/')
@limiter.limit("400/hour;20/minute")
async def chessdotcom(request: Request, moves: str = Query(None), gameid: str = Query(None), time: str = Query(None)):
    if moves:
        try:
            board_fen = None
            gotime = 2000
            if time:
                if time == "go":
                    gotime = 500
                else:
                    gotime = time
            if "newgame" in moves:
                board_fen = generate_fen(None)

            formatted = moves.split(" ")
            intcheck = False
            try:
                int(gameid)
                intcheck = True
            except:
                print("no chess.com gameid found")
            if len(gameid) < 9 or not intcheck:
                gameid = ""
            if len(formatted) > 0 and "newgame" not in moves:
                board_fen = generate_fen(formatted)
            if not isinstance(board_fen, str):
                k = board_fen.fen()
                res = instance_info.get_info(k)
                if res and ("data" in res or "board" in res or "turn" in res or "evaluation" in res):
                    return filter_dict(res, ["data", "board", "turn", "evaluation"])
                try:
                    engine = subprocess.Popen('/usr/games/stockfish', universal_newlines=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
                    #stockfish.set_depth(22)  

                    bestmove = ""
                    #evaluation
                    ze = {"type": "cp", "value": 0}

                    engine.stdin.write(f'position fen {k}\n')
                    engine.stdin.write('setoption name Threads value 2\n')
                    engine.stdin.flush()
                    # Get engine move
                    engine.stdin.write(f'go depth 22 movetime {gotime}\n')
                    engine.stdin.flush()

                    evalSign = 1 if "w" in k else -1
                    while True:
                        line = engine.stdout.readline()
                        if not line:
                            break
                        line = line.strip()
                        parts = line.split(" ")
                        for i,j in enumerate(parts):

                            if "score" == j:
                                if i + 2 < len(parts):
                                    eval_type = parts[i + 1]   # "cp" or "mate"
                                    eval_val_raw = parts[i + 2]
                                    val = 0.00
                                    try:
                                        val = int(eval_val_raw)
                                    except ValueError:
                                        pass
                                    if eval_type == "cp":
                                        val *= evalSign  # make positive for side to move
                                        ze = {"type": eval_type, "value": val}
                                    if eval_type == "mate":
                                        ze = {"type": eval_type, "value": eval_val_raw} 

                        if parts and parts[0] == "bestmove":
                            if len(parts) > 1:
                                bestmove = parts[1]
                            break

                    # Clean up the engine
                    engine.stdin.write("quit\n")
                    engine.stdin.flush()
                    engine.wait()
                    try:
                        whosturn = "white"
                        if board_fen.turn != chess.WHITE:
                            whosturn = "black"
                        if bestmove != "(none)":
                            move = chess.Move.from_uci(bestmove)
                            board_fen.push(move)
                        else:
                            move = ""
                        boardstr = board_fen.fen()
                        result = chess.Board(boardstr)
                        if res:
                            res.update({"data": bestmove, "board": str(result), "turn": whosturn, "evaluation": ze })
                            instance_info.set_info(k, res)
                        else:
                            instance_info.set_info(k, {"data": bestmove, "board": str(result), "turn": whosturn, "evaluation": ze })
                        if gameid:
                            gameid_ref = db.collection("gamecollection")
                            gdoc_ref = gameid_ref.document(gameid + "-chesscom")
                            now = datetime.now()
# Get the current date in ISO format
                            iso_date = now.date().isoformat()
                            gdoc_ref.set({"info": iso_date})
                        return {"data": bestmove, "board": str(result), "turn": whosturn, "evaluation": ze }
                    except:
                        if res:
                            res.update({"data": bestmove, "evaluation": ze})
                            instance_info.set_info(k, res)
                        else:
                            instance_info.set_info(k, {"data": bestmove, "evaluation": ze})
                        if bestmove and gameid:
                            gameid_ref = db.collection("gamecollection")
                            gdoc_ref = gameid_ref.document(gameid + "-chesscom")
                            now = datetime.now()
                            iso_date = now.date().isoformat()
                            gdoc_ref.set({"info": iso_date})
                        return {"data": bestmove, "evaluation": ze }
                except Exception as e:
                    raise HTTPException(
                                    status_code=HTTP_500_INTERNAL_SERVER_ERROR, 
                                    detail="An internal server error occurred"
                                )
        except:
            return { "nodata": "error reading query param string" }
    else:
        return { "nodata": "no move list sent to server"}


@app.get("/evaluation/")
@limiter.limit("18/minute")
async def eval_fen(request: Request, fen: str = Query(None)):
    if fen:
        try:
            stockfish = Stockfish(path=STOCKFISH_PATH, parameters={"Threads": 3, "Ponder": "False"})
            stockfish.set_depth(22)
            fen.replace("%20", " ")

            stockfish.set_fen_position(fen)
            bestmove = stockfish.get_best_move_time(3000)
            ze = stockfish.get_evaluation()
            evalboard = chess.Board(fen)
            return {"data": bestmove, "board": str(evalboard), "evaluation": ze }
        except Exception as e:
            raise HTTPException(
                status_code=HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="An internal server error occurred"
            )
    else:
        return {"message": "No query parameter provided"}

# @app.get('/get-avatars', tags=['urls'])
# async def get_urls():
#     getAvatars()
#     return {}

@app.post('/set-avatar')
@limiter.limit("5/minute")
async def set_avatar(request: Request, user: UserBody):
    collection_ref = db.collection("chessextension")
    if user.user and user.img:
      doc_ref = collection_ref.document(user.user)
  
      doc_ref.set({"user": user.user, "img": user.img})
      return { "data": f"document set for {user.user}"}
    else:
        return { "nodata": "missing username string and image string" }

@app.get('/get-useravatar/{username}', tags=['fetch avatar'])
@limiter.limit("5/minute")
async def get_useravatar(request: Request, username: str):
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
