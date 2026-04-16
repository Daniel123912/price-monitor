from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@localhost:5432/price_monitor")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    article = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(500), nullable=False)
    our_price = Column(Float, nullable=False)
    our_url = Column(String(500))
    category = Column(String(200))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PriceHistory(Base):
    __tablename__ = "price_history"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    competitor_name = Column(String(200), nullable=False)
    price = Column(Float)
    url = Column(String(500))
    in_stock = Column(Boolean, default=True)
    error_message = Column(String(500))
    parsed_date = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Связь с продуктом
    product = relationship("Product", backref="price_history")

class DailySnapshot(Base):
    __tablename__ = "daily_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(DateTime, default=datetime.utcnow, unique=True, index=True)
    total_products = Column(Integer)
    products_with_prices = Column(Integer)
    critical_count = Column(Integer)
    avg_our_price = Column(Float)
    avg_competitor_price = Column(Float)
    data = Column(JSON)  # Полный слепок данных за день

class PriceChange(Base):
    __tablename__ = "price_changes"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    competitor_name = Column(String(200))
    old_price = Column(Float)
    new_price = Column(Float)
    change_percent = Column(Float)
    change_date = Column(DateTime, default=datetime.utcnow, index=True)
    notification_sent = Column(Boolean, default=False)
    
    # Индексы для быстрого поиска
    __table_args__ = (
        Index('idx_product_competitor_date', 'product_id', 'competitor_name', 'change_date'),
    )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()