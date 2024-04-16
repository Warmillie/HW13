
from typing import List, Optional, Callable
from fastapi.staticfiles import StaticFiles
from roles import RoleAccess

from fastapi import FastAPI, Path, Query, Depends, HTTPException, status, Request, Security, APIRouter
from sqlalchemy.orm import Session

from db import get_db
import models
import schemas
import crud
from sqlalchemy.exc import IntegrityError

from passlib.context import CryptContext

from fastapi.security import HTTPBearer
import auth_services
import auth
from config import config
import redis.asyncio as redis
from fastapi_limiter import FastAPILimiter
from fastapi.middleware.cors import CORSMiddleware
from ipaddress import ip_address
from fastapi.responses import JSONResponse


app = FastAPI()

app.mount('/static', StaticFiles(directory='./static'), name='static')
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
access_to_route_all = RoleAccess([models.Role.admin, models.Role.moderator])
app.include_router(auth.router, prefix="/api")
get_refresh_token = HTTPBearer()

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


banned_ips = [ip_address("192.168.1.1"), ip_address("192.168.1.2")]


@app.middleware("http")
async def ban_ips(request: Request, call_next: Callable):
    ip = ip_address(request.client.host)
    if ip in banned_ips:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "You are banned"})
    response = await call_next(request)
    return response

@app.on_event("startup")
async def startup():
    r = await redis.Redis(
        host=config.REDIS_DOMAIN,
        port=config.REDIS_PORT,
        db=0,
        password=config.REDIS_PASSWORD,
    )
    await FastAPILimiter.init(r)

@app.get('/')
def root():
    return {"message": "Application!"}

@app.post("/contacts/", response_model=schemas.Contact)
def create_contact(contact: schemas.ContactCreate, db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth_services.Auth.get_current_user)):
    try:
        return crud.create_contact(db=db, contact=contact)
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Contact already exists")

@app.get("/contacts/", response_model=List[schemas.Contact])
def read_contacts(
    q: Optional[str] = None,
    db: Session = Depends(get_db), current_user: models.User = Depends(auth_services.Auth.get_current_user)
):
    return crud.get_contacts(db=db, q=q)

@app.get("/contacts/{contact_id}", response_model=schemas.Contact)
def read_contact(contact_id: int, db: Session = Depends(get_db),
                 current_user: models.User = Depends(auth_services.Auth.get_current_user)):
    db_contact = crud.get_contact(db=db, contact_id=contact_id)
    if db_contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return db_contact

@app.put("/contacts/{contact_id}", response_model=schemas.Contact)
def update_contact(contact_id: int, contact: schemas.ContactUpdate, db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth_services.Auth.get_current_user)):
    db_contact = crud.get_contact(db=db, contact_id=contact_id)
    if db_contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return crud.update_contact(db=db, contact_id=contact_id, contact=contact)

@app.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth_services.Auth.get_current_user)):
    db_contact = crud.get_contact(db=db, contact_id=contact_id)
    if db_contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    crud.delete_contact(db=db, contact_id=contact_id)
    return {"message": "Contact deleted successfully"}

@app.get("/contacts/birthdays/", response_model=List[schemas.Contact])
def upcoming_birthdays(db: Session = Depends(get_db),
                       current_user: models.User = Depends(auth_services.Auth.get_current_user)):
    return crud.get_upcoming_birthdays(db=db)

