FROM python:3.9-slim

WORKDIR /worker

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY src/ src/

CMD ["python", "src/main.py"]