-- db_lord is created by POSTGRES_DB. Extra databases for the ML profile:
CREATE USER mlflow WITH PASSWORD 'mlflow';
CREATE DATABASE mlflow OWNER mlflow;
CREATE USER feast_user WITH PASSWORD 'feast';
CREATE DATABASE feast OWNER feast_user;
CREATE USER lakefs WITH PASSWORD 'lakefs';
CREATE DATABASE lakefs OWNER lakefs;
