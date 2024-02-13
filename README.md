## Api for Lichess.org extension

### Features

- dockerfiles to apt get stockfishapi
- Api scrapes lichess for moves and sends fen to stockfish for evaluation
- Returns best_move

### Environment Variables

| Name           | Description                                   | Required                                      |
| -------------- | --------------------------------------------- | --------------------------------------------- |
| STOCKFISH_PATH | The path to call Stockfish from the terminal. | True, if Stockfish is not available globally. |

### Getting Started

1. Ensure python and pip are installed on your machine.
1. Ensure Stockfish is installed on your machine.
1. Ensure the environment variables are set up as needed.
1. Install python dependencies by running `pip install -r requirements.txt`
1. Run `uvicorn main:app --reload` to run the project.
1. It is encouraged to run this in a Docker container

### Running with Docker

1. Run `docker build -t stockfishapi:latest ./`
2. Run `docker run -p 8080:8080 stockfishapi` ensuring the port is exposed.
