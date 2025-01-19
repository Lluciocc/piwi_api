import pymysql
from fastapi import FastAPI, HTTPException, Request, Query, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
import uuid
import jwt
from datetime import datetime, timedelta, timezone
from pymysql.cursors import DictCursor
from cachetools import TTLCache
from contextlib import contextmanager

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting configuration
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Constants
SECRET_KEY = "B!47kqAt9jA4$o5P#35$XjrStkP&h6R3"
DB_CONFIG = {
    "host": "sql.freedb.tech",
    "port": 3306,
    "database": "freedb_piwiflix",
    "user": "freedb_nightkikko",
    "password": "&x%u%s#6Y7&xzZt"
}

# Create caches for movies and series
movies_cache = TTLCache(maxsize=100, ttl=300)  # Cache for 5 minutes
series_cache = TTLCache(maxsize=100, ttl=300)  # Cache for 5 minutes

@contextmanager
def get_db_connection():
    connection = pymysql.connect(**DB_CONFIG, cursorclass=DictCursor)
    try:
        yield connection
    finally:
        connection.close()

def validate_pseudo_length(pseudo: str):
    if len(pseudo) < 3:
        raise ValueError("Le pseudo doit être plus long que 3 caractères !")
    return pseudo

def generate_account_id(pseudo: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, pseudo))

@app.post("/create-account")
async def create_account(pseudo: str):
    try:
        validate_pseudo_length(pseudo)

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM accounts WHERE pseudo = %s", (pseudo,))
                if cursor.fetchone()["count"] > 0:
                    raise HTTPException(status_code=400, detail="Le pseudo est déjà pris")

                user_id = generate_account_id(pseudo)
                created_at = datetime.now().isoformat()

                cursor.execute(
                    "INSERT INTO accounts (id, pseudo, created_at, isPremium, premium_claimed_at) VALUES (%s, %s, %s, %s, %s)",
                    (user_id, pseudo, created_at, False, None)
                )
                conn.commit()

        return {
            "id": user_id,
            "pseudo": pseudo,
            "created_at": created_at,
            "isPremium": False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création du compte : {str(e)}")

@app.post("/login")
async def login(credentials: dict):
    user_id = credentials.get("id")
    if not user_id:
        raise HTTPException(status_code=400, detail="ID non fourni")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM accounts WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                if user:
                    return {"success": True}
                return {"success": False, "message": "Utilisateur non trouvé"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la connexion : {str(e)}")

@app.get("/user/{user_id}")
async def get_user_info(user_id: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM accounts WHERE id = %s", (user_id,))
                user_info = cursor.fetchone()
                if user_info is None:
                    raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
        return user_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des informations utilisateur : {str(e)}")

@app.get("/movies")
async def get_movies(page: int = Query(1, ge=1), per_page: int = Query(15, ge=1, le=50)):
    cache_key = f"movies_page_{page}"
    if cache_key in movies_cache:
        return movies_cache[cache_key]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                offset = (page - 1) * per_page
                cursor.execute("SELECT * FROM movies LIMIT %s OFFSET %s", (per_page, offset))
                movies = cursor.fetchall()
        
        result = {"page": page, "per_page": per_page, "movies": movies}
        movies_cache[cache_key] = result
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des films : {str(e)}")

@app.get("/movies/total_pages")
async def get_movies_total_pages(per_page: int = Query(15, ge=1, le=50)):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as total FROM movies")
                total = cursor.fetchone()["total"]
        
        total_pages = (total + per_page - 1) // per_page
        return {"total_pages": total_pages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du calcul du nombre total de pages : {str(e)}")

@app.get("/movies/{movie_id}")
async def get_movie(movie_id: int):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM movies WHERE id = %s", (movie_id,))
                movie = cursor.fetchone()
                if movie is None:
                    raise HTTPException(status_code=404, detail="Movie not found")
        return movie
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération du film : {str(e)}")

@app.get("/series")
async def get_series(page: int = Query(1, ge=1), per_page: int = Query(15, ge=1, le=50)):
    cache_key = f"series_page_{page}"
    if cache_key in series_cache:
        return series_cache[cache_key]

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                offset = (page - 1) * per_page
                cursor.execute("SELECT * FROM series LIMIT %s OFFSET %s", (per_page, offset))
                series = cursor.fetchall()
        
        result = {"page": page, "per_page": per_page, "series": series}
        series_cache[cache_key] = result
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des séries : {str(e)}")

@app.get("/series/total_pages")
async def get_series_total_pages(per_page: int = Query(15, ge=1, le=50)):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as total FROM series")
                total = cursor.fetchone()["total"]
        
        total_pages = (total + per_page - 1) // per_page
        return {"total_pages": total_pages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du calcul du nombre total de pages : {str(e)}")

@app.get("/series/{series_id}")
async def get_series_by_id(series_id: int):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM series WHERE id = %s", (series_id,))
                series = cursor.fetchone()
                if series is None:
                    raise HTTPException(status_code=404, detail="Series not found")
        return series
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération de la série : {str(e)}")

@app.get("/generate_claim-link")
async def generate_claim_link(pseudo: str):
    try:
        expiration_time = datetime.now(timezone.utc) + timedelta(hours=24)
        payload = {"pseudo": pseudo, "exp": expiration_time}
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        claim_link = f"/claim-premium?token={token}"
        return {"claim_link": claim_link}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la génération du lien de réclamation : {str(e)}")

@app.get("/claim-premium")
@limiter.limit("1/12hours")
async def claim_premium(token: str, request: Request):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        pseudo = payload["pseudo"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Le jeton a expiré.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Le jeton est invalide.")

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM accounts WHERE pseudo = %s", (pseudo,))
                account = cursor.fetchone()

                if account is None:
                    raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

                last_claim = account["premium_claimed_at"]
                if last_claim:
                    last_claim_time = datetime.fromisoformat(last_claim)
                    if datetime.now() - last_claim_time < timedelta(hours=12):
                        raise HTTPException(status_code=400, detail="Vous ne pouvez réclamer le premium qu'une fois toutes les 12 heures")

                cursor.execute(
                    "UPDATE accounts SET isPremium = %s, premium_claimed_at = %s WHERE pseudo = %s",
                    (True, datetime.now().isoformat(), pseudo)
                )
                conn.commit()

        return {"message": "Vous avez récupéré un compte premium pour 12 heures. Profitez bien !"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la réclamation premium : {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
