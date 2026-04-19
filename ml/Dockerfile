FROM python:3.12-slim

WORKDIR /app

# Install git and any OS dependencies (like opencv dependencies)
RUN apt-get update && apt-get install -y git libgl1-mesa-glx && apt-get clean

COPY requirements.txt ./

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "app.py"]
