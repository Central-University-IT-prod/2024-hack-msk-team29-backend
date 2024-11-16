from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
from pymongo import MongoClient
from bson import ObjectId
import jwt
from bson.json_util import dumps
import json

JWT_SECRET = "{{sensitive_data}}"

client = MongoClient("mongodb://{{sensitive_data}}:{{sensitive_data}}@{{sensitive_data}}:27017/?authSource={{sensitive_data}}")
database = client.PROD
collection = database.collections
app = FastAPI()
security = HTTPBearer()

# Модели данных (Pydantic для валидации)
class PaidStatusEnum(int, Enum):
    not_paid = 0
    partially_paid = 1
    fully_paid = 2

class User(BaseModel):
    name: str
    phone_number: str | None = None
    bank: str | None = None
class UserUpd(BaseModel):
    field: str
    newVal: str
class Gues(BaseModel):
    id: str = Field(..., alias="_id")
    debt: int
    paid_status: PaidStatusEnum

class Bill(BaseModel):
    name: str
    org: str | None = None
    total_paid: int
    guys: List[Gues]

class Event(BaseModel):
    name: str
    user_list: List[User]
    bills: List[Bill]
    token: str | None = None

class BillResp(BaseModel):
    id: str = Field(..., alias="_id")
    name: str
    total_paid: int
    guys: List[dict]
    debt: Optional[int]
    paid_status: PaidStatusEnum
class UserResp(BaseModel):
    id: str = Field(..., alias="_id")
    name: str
    phone_number: str | None = None
    bank: str | None = None
    
class EventResp(BaseModel):
    id: str = Field(..., alias="_id")
    name: str
    user_list: List[UserResp]
    bills: List[BillResp]
    token: str | None = None


# Модель для валидации тела запроса для PUT /user
class UserName(BaseModel):
    name: str

class TokenResponse(BaseModel):
    token: str

# Мидлварь для проверки JWT токена
def validate_token(authorization: str = Depends(security)):
    token = authorization.credentials
    enc = {}
    try:
        enc = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except:
        raise HTTPException(status_code=403, detail="Invalid or missing token")
    return enc["collection_id"]

def get_user_id(user_id: str):
    return user_id

# Эндпоинт для создания события
@app.put("/event", response_model=TokenResponse)
async def create_event(event: Event):
    event_dict = event.dict(by_alias=True)
    result = collection.insert_one(event_dict)
    encoded_jwt = jwt.encode({"collection_id": str(result.inserted_id)}, JWT_SECRET, algorithm="HS256")
    collection.update_one({"_id": result.inserted_id}, {"$set": {"token": encoded_jwt}})
    return {"token": encoded_jwt}

# Эндпоинт для получения информации о событии
@app.get("/event", dependencies=[Depends(validate_token)])
async def get_event(event_id: str = Depends(validate_token)):
    event = collection.find_one({"_id": ObjectId(event_id)})
    return json.loads(dumps(event))

# Эндпоинт для создания/обновления счета
@app.put("/bill", dependencies=[Depends(validate_token)])
async def create_bill(bill: Bill, event_id: str = Depends(validate_token), user_id: str = Depends(get_user_id)):
    bill_dict = bill.dict(by_alias=True)
    bill_dict["org"] = ObjectId(user_id)
    new_id = ObjectId()
    bill_dict["_id"] = new_id
    result = collection.update_one(
        {"_id": ObjectId(event_id)},
        {"$push": {"bills": bill_dict}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Event not found or Bill not created")
    return {"message": "Bill created", "bill_id": str(new_id)}

# Эндпоинт для изменения пользователя
@app.post("/user", dependencies=[Depends(validate_token)])
async def update_user(user: UserUpd, event_id: str = Depends(validate_token), user_id: str = Depends(get_user_id)):
    result = collection.update_one(
        { "user_list._id": ObjectId(user_id) },  # Условие поиска по _id внутри users
        { "$set": { f"user_list.$[elem].{user.field}": user.newVal } },  # Обновляем имя
        array_filters=[{ "elem._id": ObjectId(user_id) }]  # Фильтр массива по _id
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="User not found or already val set")
    else:
        return ""

@app.put("/user", dependencies=[Depends(validate_token)])
async def create_user_in_event(user: User, event_id: str = Depends(validate_token)):
    # Проверяем, существует ли событие с таким ID
    event = collection.find_one({"_id": ObjectId(event_id)})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Преобразуем объект пользователя в словарь
    user_dict = user.dict()
    new_user_objid = ObjectId()
    user_dict["_id"] = new_user_objid
    print(user_dict)

    # Вставляем нового пользователя в список user_list
    result = collection.update_one(
        {"_id": ObjectId(event_id)},
        {"$push": {"user_list": user_dict}}
    )
    print(result, new_user_objid)

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to add user to event")

    return {"user_id": str(new_user_objid)}

# # Эндпоинт для оплаты счета
# @app.post("/pay/{bill_id}", dependencies=[Depends(validate_token)])
# async def pay_bill(bill_id: str, event_id: str = Depends(validate_token), user_id: str = Depends(get_user_id)):
#     # ID event
#     bll_id = ObjectId(bill_id)
#     # ID 
#     usr_id = ObjectId(user_id)

#     # Выполняем обновление пользователя внутри конкретной группы
#     result = collection.update_one(
#         { "bills._id": bll_id, "bills.guys._id": usr_id },  # Ищем по _id группы и _id пользователя
#         { "$set": { "bills.$[bill].guys.$[guy].paid_status": 1 } },  # Обновляем имя пользователя
#         array_filters=[
#             { "bill._id": bll_id },  # Фильтр для конкретной группы
#             { "guy._id": usr_id }     # Фильтр для конкретного пользователя
#         ]
#     )
#     print(result)
#     raise HTTPException(status_code=404, detail="Bill not found")

# # Эндпоинт для верификации оплаты (только для хоста)
# @app.put("/pay/{bill_id}", dependencies=[Depends(validate_token)])
# async def verification_pay(bill_id: str, event_id: str = Depends(validate_token), user_id: str = Depends(get_user_id)):
#     # тут проверка должна быть что вызывал хост, иначе отрыгивать
#     raise HTTPException(status_code=404, detail="Bill not found")
