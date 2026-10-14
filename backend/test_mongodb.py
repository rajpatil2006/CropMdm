
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

uri = os.getenv("MONGODB_URI")
database_name = os.getenv("MONGODB_DATABASE", "cropmind")

if not uri:
    raise ValueError("MONGODB_URI is missing from the .env file")

client = MongoClient(uri, serverSelectionTimeoutMS=10000)

try:
    client.admin.command("ping")
    print("MongoDB connection successful!")
    print("Database:", database_name)
finally:
    client.close()
