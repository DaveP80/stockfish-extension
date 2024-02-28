import chess
import chess.engine
from Instance.instance import instance_info

def analyze(engine_file, threads, hash_mb, fen, movetime_sec, max_depth, shorth):
    try:
        engine = chess.engine.SimpleEngine.popen_uci(engine_file)

        limit = chess.engine.Limit(time=movetime_sec, depth=max_depth)
        board = chess.Board(fen, chess960=False)
        stm = board.turn  # stm is Side To Move

        info = engine.analyse(board, limit=limit)
        if "score" in info:
            eng_score = info.get("score")
            if eng_score is not None:
                wdl = eng_score.wdl()  # win/draw/loss info point of view is stm
                wins, draws, losses = wdl[0], wdl[1], wdl[2]
                total = wins + draws + losses

                if total != 0:
                    score = wins + draws/2
                    score_rate = score / total
                    win_rate = wins / total
                    loss_rate = losses / total

                    white_winning_chances = win_rate if stm == chess.WHITE else loss_rate
                    black_winning_chances = win_rate if stm == chess.BLACK else loss_rate

                    white_score_rate = score_rate if stm == chess.WHITE else 1 - score_rate
                    black_score_rate = score_rate if stm == chess.BLACK else 1 - score_rate

                    if stm == chess.WHITE:
                        stor = {"winning_chances": f'{100 * white_winning_chances:0.2f}', "score_rate": f'{100 * white_score_rate:0.2f}' }
                    else:
                        stor = {"winning_chances": f'{100 * black_winning_chances:0.2f}', "score_rate": f'{100 * black_score_rate:0.2f}' }
                else:
                    stor = None
            else:
                stor = None
        else:
            stor = None

        engine.quit()
        if stor:
            instance_info.set_info(shorth, stor)

    except Exception as e:
        print("Error:", str(e))
