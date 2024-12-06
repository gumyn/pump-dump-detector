FROM python:3.9-slim

WORKDIR /app

# Copier les fichiers nécessaires
COPY requirements.txt .
COPY app.py .

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Exposer le port pour Flask
EXPOSE 5000

# Démarrer l'application
CMD ["python", "app.py"]