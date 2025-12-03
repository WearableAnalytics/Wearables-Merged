#!/usr/bin/env just --justfile

up:
	docker compose up --build --detach

db_only:
    docker compose up --detach postgres

down:
    docker compose down -v