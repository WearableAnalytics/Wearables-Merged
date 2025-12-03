
async def mock_lookup_user_in_charite(username: str) -> dict | None:
    user = {"username": username,"name": "Test User", "email": "app.user@mail.com", "age": 40, "weight": 60, "sex": "female"}
    return {"user": user}

