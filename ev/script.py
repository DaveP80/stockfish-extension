import chess
import chess.engine

def analyze(engine_file, threads, hash_mb, fen, movetime_sec, max_depth):

    engine = chess.engine.SimpleEngine.popen_uci(engine_file)

    engine.configure({'Threads': threads})
    engine.configure({'Hash': hash_mb})

    limit = chess.engine.Limit(time=movetime_sec, depth=max_depth)
    board = chess.Board(fen, chess960=False)
    stm = board.turn
    stor = []

    with engine.analysis(board, limit=limit) as analysis:
        for info in analysis:
            eng_score = info.get("score")

            if eng_score is not None:
                wdl = eng_score.wdl()  # win/draw/loss info point of view is stm
                wins, draws, losses = wdl[0], wdl[1], wdl[2]
                score = wins + draws/2
                total = wins + draws + losses

                score_rate = score / total
                win_rate = wins / total
                loss_rate = losses / total
                
                white_winning_chances = win_rate if stm==chess.WHITE else loss_rate
                black_winning_chances = win_rate if stm==chess.BLACK else loss_rate

                white_score_rate = score_rate if stm==chess.WHITE else 1 - score_rate
                black_score_rate = score_rate if stm==chess.BLACK else 1 - score_rate
                if stm==chess.WHITE:
                    stor.append({"winning_chances": f'{100 * white_winning_chances:0.2f}', "score_rate": f'{100 * white_score_rate:0.2f}' })
                elif stm==chess.BLACK:
                    stor.append({"winning_chances": f'{100 * black_winning_chances:0.2f}', "score_rate": f'{100 * black_score_rate:0.2f}' })

    engine.quit()
    if len(stor) > 0:
        g = stor.pop()
        return g
    return None
