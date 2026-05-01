
from os import environ 

class Config:
    API_ID = environ.get("API_ID", "24989803")
    API_HASH = environ.get("API_HASH", "1f42d3bb1ac54fed8941aa7befe39111")
    BOT_TOKEN = environ.get("BOT_TOKEN", "") 
    BOT_SESSION = environ.get("BOT_SESSION", "bot") 
    DATABASE_URI = environ.get("DATABASE", "mongodb+srv://hellobhaikya:hellobhaikya@cluster0.v1evswq.mongodb.net/?appName=Cluster0")
    DATABASE_NAME = environ.get("DATABASE_NAME", "forward-bost")
    BOT_OWNER_ID = [int(id) for id in environ.get("BOT_OWNER_ID", '7955996369').split()]    #6286894502, #7955996369

class temp(object): 
    lock = {}
    CANCEL = {}
    forwardings = 0
    BANNED_USERS = []
    IS_FRWD_CHAT = []
