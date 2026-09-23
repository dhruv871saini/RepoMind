from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import delete
from pydantic import BaseModel
from app.db.models import Repository
from app.db.postgres import get_db

router = APIRouter(prefix="/repo",tags=["repo"])

@router.get('/')
def getRepo(db:Session=Depends(get_db)):
    try:
        print()
        data = db.query(Repository).all()
        db.commit()
        return {
            "data": data
        }

    except Exception as e :
        print(f"there is getting issue ==> {e}") 
        raise HTTPException(status_code=500,detail=str(e))
    

@router.delete('/{id}')
def deleteRepo(id:str,db:Session=Depends(get_db)):
    try:
        result = db.execute(
            delete(Repository).where(Repository.id == id)
        )

        if result.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Repository not found"
            )

        db.commit()

        return {
            "message": "Repository deleted successfully",
            "id": id
        }
    except Exception as e:
        print(f"there is delete issue ==> {e}")
        raise HTTPException(status_code=500, detail=str(e))
