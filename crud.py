from datetime import date, timedelta
from passlib.context import CryptContext
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
import schemas

def create_contact(db: Session, contact: schemas.ContactCreate):
    db_contact = models.Contact(**contact.dict())
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact

def get_contacts(db: Session, q: str = None):
    query = db.query(models.Contact)
    if q:
        query = query.filter(
            models.Contact.first_name.ilike(f"%{q}%") |
            models.Contact.last_name.ilike(f"%{q}%") |
            models.Contact.email.ilike(f"%{q}%")
        )
    return query.all()

def get_contact(db: Session, contact_id: int):
    return db.query(models.Contact).filter(models.Contact.id == contact_id).first()

def update_contact(db: Session, contact_id: int, contact: schemas.ContactUpdate):
    db_contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    for key, value in contact.dict(exclude_unset=True).items():
        setattr(db_contact, key, value)
    db.commit()
    db.refresh(db_contact)
    return db_contact

def delete_contact(db: Session, contact_id: int):
    db_contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    db.delete(db_contact)
    db.commit()

def get_upcoming_birthdays(db: Session):
    today = date.today()
    week_later = today + timedelta(days=7)
    return db.query(models.Contact).filter(
        func.date_trunc('day', models.Contact.birthday) >= today,
        func.date_trunc('day', models.Contact.birthday) <= week_later
    ).all()




