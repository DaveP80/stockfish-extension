import asyncio
import os
from fastapi import FastAPI, Query, HTTPException, Request
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from fastapi.middleware.cors import CORSMiddleware
from stockfish import Stockfish
from pydantic import BaseModel
from bs4 import BeautifulSoup
import chess
from scrappy import getAvatars
from google.cloud import firestore
from Instance.instance import instance_info, get_instance_info
from ev import analyze
import hashlib
from datetime import datetime
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


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

def filter_dict(original_dict, keys_to_keep):
    return {key: original_dict[key] for key in keys_to_keep if key in original_dict}

async def query_stockfish(fen: str, gotime, default_bestmove: str = "(none)"):
    engine = await asyncio.create_subprocess_exec(
        '/usr/games/stockfish',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    bestmove = default_bestmove
    ze = {"type": "cp", "value": 0}

    engine.stdin.write(f'position fen {fen}\n'.encode())
    engine.stdin.write(b'setoption name Threads value 2\n')
    await engine.stdin.drain()
    engine.stdin.write(f'go depth 22 movetime {gotime}\n'.encode())
    await engine.stdin.drain()

    eval_sign = 1 if "w" in fen else -1
    while True:
        line = await engine.stdout.readline()
        if not line:
            break
        line = line.decode().strip()
        parts = line.split(" ")
        for i, j in enumerate(parts):
            if "score" == j:
                if i + 2 < len(parts):
                    eval_type = parts[i + 1]
                    eval_val_raw = parts[i + 2]
                    val = 0.00
                    try:
                        val = int(eval_val_raw)
                    except ValueError:
                        pass
                    if eval_type == "cp":
                        val *= eval_sign
                        ze = {"type": eval_type, "value": val}
                    if eval_type == "mate":
                        ze = {"type": eval_type, "value": eval_val_raw}

        if parts and parts[0] == "bestmove":
            if len(parts) > 1:
                bestmove = parts[1]
            break

    engine.stdin.write(b"quit\n")
    await engine.stdin.drain()
    await engine.wait()
    return bestmove, ze

@app.get('/', tags=['Default'])
def index():

    return {'message': 'Welcome to stockfish chess helper API.'}


@app.get('/suggest-move/', tags=['Chess Engine'])
@limiter.limit("400/hour;20/minute")
async def suggest_move(request: Request, moves: str = Query(None), gameid: str = Query(None), time: str = Query(None)):
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

            if len(gameid) < 4:
                gameid = ""
            if len(formatted) > 0 and "newgame" not in moves:
                board_fen = generate_fen(formatted)
            if not isinstance(board_fen, str):
                k = board_fen.fen()
                res = instance_info.get_info(k)
                if res and ("data" in res or "board" in res or "turn" in res or "evaluation" in res):
                    return filter_dict(res, ["data", "board", "turn", "evaluation"])
                try:
                    bestmove, ze = await query_stockfish(k, gotime, default_bestmove="")
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
                            gdoc_ref = gameid_ref.document(gameid + "-lichess")
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
        except:
            return { "nodata": "error reading query param string" }
    else:
        return { "nodata": "no move list sent to server"}

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
                    bestmove, ze = await query_stockfish(k, gotime, default_bestmove="")
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