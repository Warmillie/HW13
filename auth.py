from fastapi import (APIRouter, HTTPException, Depends, status, Security, BackgroundTasks,
                     Request, Response, UploadFile,File)
from fastapi.security import OAuth2PasswordRequestForm, HTTPAuthorizationCredentials, HTTPBearer
from fastapi_limiter.depends import RateLimiter
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse
import auth_services
import schemas
import users
from db import get_db
from send_email import send_email
import models
import pickle
import cloudinary
import cloudinary.uploader
from config import config

router = APIRouter(prefix='/auth', tags=['auth'])
get_refresh_token = HTTPBearer()
cloudinary.config(
    cloud_name=config.CLD_NAME,
    api_key=config.CLD_API_KEY,
    api_secret=config.CLD_API_SECRET,
    secure=True,
)

@router.post("/signup/", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def signup(body: schemas.UserSchema, bt: BackgroundTasks, request: Request, db: Session = Depends(get_db)):
    if users.get_user_by_email(body.email, db):
        print(1)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",

        )
    body.password = auth_services.Auth.get_password_hash(body.password)
    db_user = users.create_user(body, db)
    bt.add_task(send_email, db_user.email, db_user.username, str(request.base_url))
    return db_user


@router.post("/login/", response_model=schemas.TokenSchema)
def login(body: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    db_user = users.get_user_by_email(body.username, db)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not db_user.confirmed:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not confirmed",
        )

    if not auth_services.Auth.verify_password(body.password, db_user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = auth_services.Auth.create_access_token(data={'sub': db_user.email})
    refresh_token = auth_services.Auth.create_refresh_token(data={'sub': db_user.email})
    users.update_token(db_user, refresh_token, db)
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@router.get("/refresh_token/", response_model=schemas.TokenSchema)
def refresh_token(credentials: HTTPAuthorizationCredentials = Security(get_refresh_token),
                  db: Session = Depends(get_db)):
    token = credentials.credentials
    email = auth_services.Auth.decode_refresh_token()
    user = users.get_user_by_email(email, db)
    if user.refresh_token != token:
        users.update_token(user, None, db)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    access_token = auth_services.Auth.create_access_token(data={'sub': email})
    refresh_token = auth_services.Auth.create_refresh_token(data={'sub': email})
    users.update_token(user, refresh_token, db)
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@router.get('/confirmed_email/{token}')
def confirmed_email(token: str, db: Session = Depends(get_db)):
    email = auth_services.Auth.get_email_from_token(token)
    user = users.get_user_by_email(email, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification error")
    if user.confirmed:
        return {"message": "Your email is already confirmed"}
    users.confirmed_email(email, db)
    return {"message": "Email confirmed"}


@router.post('/request_email')
def request_email(body: schemas.RequestEmail, background_tasks: BackgroundTasks, request: Request,
                  db: Session = Depends(get_db)):
    user = users.get_user_by_email(body.email, db)

    if user.confirmed:
        return {"message": "Your email is already confirmed"}
    if user:
        background_tasks.add_task(send_email, user.email, user.username, str(request.base_url))
    return {"message": "Check your email for confirmation."}


@router.get('/{username}')
def request_email(username: str, response: Response, db: Session = Depends(get_db)):
    print('--------------------------------')
    print(f'{username} зберігаємо що він відкрив email в БД')
    print('--------------------------------')
    return FileResponse("static/open_check.png", media_type="image/png", content_disposition_type="inline")

@router.get('/me', response_model=schemas.UserResponse, dependencies=[Depends(RateLimiter(times=1, seconds=20))],
)
def get_current_user(user: models.User = Depends(auth_services.Auth.get_current_user)):
    return user

@router.patch(
    "/avatar",
    response_model=schemas.UserResponse,
    dependencies=[Depends(RateLimiter(times=1, seconds=20))],
)

def get_current_user(
    file: UploadFile = File(),
    user: models.User = Depends(auth_services.Auth.get_current_user),
    db: Session = Depends(get_db),
):
    public_id = f"HW12/{user.email}"
    res = cloudinary.uploader.upload(file.file, public_id=public_id, owerite=True)
    print(res)
    res_url = cloudinary.CloudinaryImage(public_id).build_url(
        width=250, height=250, crop="fill", version=res.get("version")
    )
    user = users.update_avatar_url(user.email, res_url, db)
    auth_services.Auth.cache.set(user.email, pickle.dumps(user))
    auth_services.Auth.cache.expire(user.email, 300)
    return user