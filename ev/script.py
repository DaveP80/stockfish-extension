import chess
import chess.engine
import os


def analyze(engine_file, threads, hash_mb, fen, movetime_sec, max_depth):
    """
    Analyze position fen with the engine_file and stream the winning chances of both sides.
    The engine should support the wdl info.
    """
    engine = chess.engine.SimpleEngine.popen_uci(engine_file)

    # Set threads and hash engine options.
    engine.configure({'Threads': threads})
    engine.configure({'Hash': hash_mb})

    limit = chess.engine.Limit(time=movetime_sec, depth=max_depth)
    board = chess.Board(fen, chess960=False)
    stm = board.turn  # stm is Side To Move

    # Get engine analysis info while it is analyzing the position.
    with engine.analysis(board, limit=limit) as analysis:
        for info in analysis:
            eng_score = info.get("score")

            if eng_score is not None:
                wdl = eng_score.wdl()  # win/draw/loss info point of view is stm
                wins, draws, losses = wdl[0], wdl[1], wdl[2]
                print(wins, draws, losses)

                score = wins + draws/2
                total = wins + draws + losses

                score_rate = score / total
                win_rate = wins / total
                draw_rate = draws / total
                loss_rate = losses / total
                
                white_winning_chances = win_rate if stm==chess.WHITE else loss_rate
                black_winning_chances = win_rate if stm==chess.BLACK else loss_rate

                white_score_rate = score_rate if stm==chess.WHITE else 1 - score_rate
                black_score_rate = score_rate if stm==chess.BLACK else 1 - score_rate

                # Show info.
                print(f'white_winning_chances: {100 * white_winning_chances:0.2f}%, white_score_rate: {100 * white_score_rate:0.2f}%, white_draw_rate: {100 * draw_rate:0.2f}%')
                print(f'black_winning_chances: {100 * black_winning_chances:0.2f}%, black_score_rate: {100 * black_score_rate:0.2f}%, black_draw_rate: {100 * draw_rate:0.2f}%')

    engine.quit()


def main():
    engine_file = os.getenv('STOCKFISH_PATH') or 'stockfish'
    fen = 'rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6'  # sicilian opening
    movetime_sec = 1.5
    max_depth = 20
    threads = 2
    hash_mb = 64
    
    analyze(engine_file, threads, hash_mb, fen, movetime_sec, max_depth)


if __name__ == "__main__":
    main()
