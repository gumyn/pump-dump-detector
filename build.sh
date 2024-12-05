docker build -t pump-dump-detector .
docker run -it --env-file .env pump-dump-detector