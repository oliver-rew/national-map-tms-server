FROM python:3.10-slim-buster

RUN apt update
RUN apt install -y gcc python3-dev
COPY requirements.txt .
RUN python3 -m pip install --upgrade pip
RUN python3 -m pip install -r requirements.txt

WORKDIR /workdir
COPY *.py .

CMD python3 tms_server.py
