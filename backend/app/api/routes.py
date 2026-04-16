from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from ..database import get_db, Product, PriceHistory, DailySnapshot, PriceChange
from ..schemas import ProductCreate, ProductResponse, DailyComparison, AnalysisReport
from ..analytics.comparator import PriceComparator
from ..workers.celery_tasks import start_daily_parsing

router = APIRouter()

# ============ Products ============
@router.get("/products", response_model=List[ProductResponse])
def get_products(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.is_active == True).offset(skip).limit(limit).all()
    return products

@router.post("/products", response_model=ProductResponse)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    db_product = Product(**product.model_dump())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = False
    db.commit()
    return {"message": "Product deleted"}

# ============ Parse ============
@router.post("/parse/start")
def start_parsing(background_tasks: BackgroundTasks):
    """Запуск парсинга в фоне"""
    from ..workers.celery_tasks import start_daily_parsing
    task = start_daily_parsing.delay()
    return {"task_id": task.id, "status": "started"}

@router.get("/parse/status/{task_id}")
def get_parse_status(task_id: str):
    from ..workers.celery_tasks import celery_app
    task = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "status": task.status, "result": task.result if task.ready() else None}

# ============ Comparison (сравнение с предыдущим днем) ============
@router.get("/compare/today-vs-yesterday", response_model=AnalysisReport)
def compare_with_yesterday(db: Session = Depends(get_db)):
    """Сравнение цен сегодня vs вчера"""
    comparator = PriceComparator(db)
    report = comparator.compare_days()
    return report

@router.get("/compare/product/{product_id}")
def compare_product_history(
    product_id: int, 
    days: int = 7, 
    db: Session = Depends(get_db)
):
    """История изменений цены товара за N дней"""
    comparator = PriceComparator(db)
    history = comparator.get_product_history(product_id, days)
    return history

@router.get("/compare/statistics")
def get_statistics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """Статистика изменений за период"""
    if not start_date:
        start_date = datetime.utcnow() - timedelta(days=30)
    if not end_date:
        end_date = datetime.utcnow()
    
    changes = db.query(PriceChange).filter(
        PriceChange.change_date.between(start_date, end_date)
    ).all()
    
    stats = {
        "total_changes": len(changes),
        "price_increases": len([c for c in changes if c.new_price > c.old_price]),
        "price_decreases": len([c for c in changes if c.new_price < c.old_price]),
        "avg_change_percent": sum(c.change_percent for c in changes if c.change_percent) / len(changes) if changes else 0,
        "most_changed_product": None
    }
    
    return stats

# ============ Snapshots (история по дням) ============
@router.get("/snapshots")
def get_snapshots(limit: int = 30, db: Session = Depends(get_db)):
    """Список всех дневных слепков"""
    snapshots = db.query(DailySnapshot).order_by(DailySnapshot.snapshot_date.desc()).limit(limit).all()
    return snapshots

@router.get("/snapshots/{date}")
def get_snapshot_by_date(date: datetime, db: Session = Depends(get_db)):
    """Получить слепок за конкретный день"""
    snapshot = db.query(DailySnapshot).filter(
        DailySnapshot.snapshot_date.cast(db.Date) == date.date()
    ).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot

# ============ WebSocket для реального времени ==========
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"Update: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)