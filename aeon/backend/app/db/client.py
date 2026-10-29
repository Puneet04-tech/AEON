from motor.motor_asyncio import AsyncIOMotorClient
from app.settings import settings
import structlog

logger = structlog.get_logger()

class Database:
    client: AsyncIOMotorClient = None
    db = None


db = Database()


async def connect_to_mongo():
    logger.info("Connecting to MongoDB", uri=settings.MONGODB_URI[:20] + "...")
    db.client = AsyncIOMotorClient(settings.MONGODB_URI)
    db.db = db.client[settings.MONGODB_DB]
    logger.info("Connected to MongoDB", db=settings.MONGODB_DB)


async def close_mongo_connection():
    logger.info("Closing MongoDB connection")
    db.client.close()


def get_database():
    return db.db
