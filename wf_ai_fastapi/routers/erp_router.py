from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
data = []
class Book(BaseModel):
   id: int
   title: str
   author: str
   publisher: str

data = [{"id":1,"title":"Python programming","author":"James","publisher":"Gala Publishing"},
        {"id":2,"title":"Java programming","author":"David Burns","publisher":"Melbourne Publishing"},
        {"id":3,"title":"FastAPI programming","author":"Michael","publisher":"Aus Publishing"}]

router = APIRouter(
    prefix="/erp",
    tags=["ERP"])


fake_items_db = {"1": {"name": "Plumbus"}, "2": {"name": "Portal Gun"}}

@router.post("/book")
def add_book(book: Book):
   data.append(book.dict())
   return data

@router.get("/")
def get_books():
   return data

@router.get("/{id}")
def get_book(id: int):
   id = id - 1
   return data[id]

@router.put("/{id}")
def add_book(id: int, book: Book):
   data[id-1] = book
   return data

@router.delete("/{id}")
def delete_book(id: int):
   data.pop(id-1)
   return data

