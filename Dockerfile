FROM python:3.11
ENV PYTHONUNBUFFERED True

RUN apt-get update
RUN apt-get install -y stockfish

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

ENV STOCKFISH_PATH='/usr/games/stockfish'

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

