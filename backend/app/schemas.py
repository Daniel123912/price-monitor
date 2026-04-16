from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict

class ProductCreate(BaseModel):
    article: str
    name: str
    our_price: float
    our_url: Optional[str] = None
    category: Optional[str] = None

class ProductResponse(BaseModel):
    id: int
    article: str
    name: str
    our_price: float
    our_url: Optional[str]
    category: Optional[str]
    
    class Config:
        from_attributes = True

class PriceHistoryResponse(BaseModel):
    product_id: int
    competitor_name: str
    price: Optional[float]
    parsed_date: datetime
    in_stock: bool

class DailyComparison(BaseModel):
    product_id: int
    product_name: str
    article: str
    our_price: float
    yesterday_price: Optional[float]
    today_price: Optional[float]
    price_change: Optional[float]
    change_percent: Optional[float]
    competitor_prices_today: Dict[str, float]
    competitor_prices_yesterday: Dict[str, float]
    recommendation: str

class AnalysisReport(BaseModel):
    date: datetime
    total_products: int
    products_with_changes: int
    price_increases: int
    price_decreases: int
    critical_changes: List[DailyComparison]
    summary: Dict[str, any]