from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict
from ..database import Product, PriceHistory, PriceChange, DailySnapshot
from ..schemas import DailyComparison, AnalysisReport
from loguru import logger

class PriceComparator:
    """Сравнение цен с предыдущими днями"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def compare_days(self, today: datetime = None) -> AnalysisReport:
        """Сравнение сегодняшних цен с вчерашними"""
        if not today:
            today = datetime.utcnow()
        
        yesterday = today - timedelta(days=1)
        
        # Получаем цены за сегодня
        today_prices = self._get_prices_for_date(today)
        
        # Получаем цены за вчера
        yesterday_prices = self._get_prices_for_date(yesterday)
        
        comparisons = []
        critical_changes = []
        price_increases = 0
        price_decreases = 0
        
        for product_id, today_data in today_prices.items():
            yesterday_data = yesterday_prices.get(product_id, {})
            
            # Сравниваем нашего конкурента
            if product_id in yesterday_prices:
                # Наша цена
                our_price_change = today_data.get('our_price', 0) - yesterday_data.get('our_price', 0)
                if our_price_change != 0:
                    if our_price_change > 0:
                        price_increases += 1
                    else:
                        price_decreases += 1
                
                # Цены конкурентов
                all_competitors = set(today_data['competitors'].keys()) | set(yesterday_data['competitors'].keys())
                
                for competitor in all_competitors:
                    today_price = today_data['competitors'].get(competitor)
                    yesterday_price = yesterday_data['competitors'].get(competitor)
                    
                    if today_price and yesterday_price and today_price != yesterday_price:
                        change_percent = ((today_price - yesterday_price) / yesterday_price) * 100
                        
                        # Сохраняем изменение
                        change = PriceChange(
                            product_id=product_id,
                            competitor_name=competitor,
                            old_price=yesterday_price,
                            new_price=today_price,
                            change_percent=change_percent,
                            change_date=datetime.utcnow()
                        )
                        self.db.add(change)
                        
                        # Критическое изменение (>10%)
                        if abs(change_percent) > 10:
                            comparison = DailyComparison(
                                product_id=product_id,
                                product_name=today_data['name'],
                                article=today_data['article'],
                                our_price=today_data['our_price'],
                                yesterday_price=yesterday_data.get('our_price'),
                                today_price=today_data['our_price'],
                                price_change=our_price_change,
                                change_percent=(our_price_change / yesterday_data.get('our_price', 1)) * 100 if yesterday_data.get('our_price') else 0,
                                competitor_prices_today=today_data['competitors'],
                                competitor_prices_yesterday=yesterday_data['competitors'],
                                recommendation=f"⚠️ Критическое изменение цены {competitor}: {change_percent:+.1f}%"
                            )
                            critical_changes.append(comparison)
        
        self.db.commit()
        
        # Создаем дневной слепок
        snapshot = DailySnapshot(
            snapshot_date=datetime.utcnow(),
            total_products=len(today_prices),
            products_with_prices=len([p for p in today_prices.values() if p['competitors']]),
            critical_count=len(critical_changes),
            avg_our_price=sum(p['our_price'] for p in today_prices.values()) / len(today_prices) if today_prices else 0,
            avg_competitor_price=self._calculate_avg_competitor_price(today_prices),
            data=today_prices
        )
        self.db.add(snapshot)
        self.db.commit()
        
        return AnalysisReport(
            date=datetime.utcnow(),
            total_products=len(today_prices),
            products_with_changes=price_increases + price_decreases,
            price_increases=price_increases,
            price_decreases=price_decreases,
            critical_changes=critical_changes,
            summary={
                "avg_our_price": snapshot.avg_our_price,
                "avg_competitor_price": snapshot.avg_competitor_price,
                "total_changes": price_increases + price_decreases
            }
        )
    
    def get_product_history(self, product_id: int, days: int = 7) -> List[Dict]:
        """История цен товара за N дней"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        history = self.db.query(PriceHistory).filter(
            PriceHistory.product_id == product_id,
            PriceHistory.parsed_date >= start_date
        ).order_by(PriceHistory.parsed_date).all()
        
        # Группируем по дням
        daily_data = defaultdict(lambda: {'our_price': None, 'competitors': {}})
        
        for record in history:
            date_key = record.parsed_date.date()
            if record.competitor_name == '_our_':
                daily_data[date_key]['our_price'] = record.price
            else:
                daily_data[date_key]['competitors'][record.competitor_name] = record.price
        
        return [{'date': date, 'data': data} for date, data in sorted(daily_data.items())]
    
    def _get_prices_for_date(self, date: datetime) -> Dict:
        """Получает все цены за конкретный день"""
        start = datetime(date.year, date.month, date.day, 0, 0, 0)
        end = start + timedelta(days=1)
        
        prices = self.db.query(PriceHistory).filter(
            PriceHistory.parsed_date >= start,
            PriceHistory.parsed_date < end
        ).all()
        
        result = {}
        for price in prices:
            if price.product_id not in result:
                product = self.db.query(Product).filter(Product.id == price.product_id).first()
                result[price.product_id] = {
                    'id': price.product_id,
                    'article': product.article,
                    'name': product.name,
                    'our_price': product.our_price,
                    'competitors': {}
                }
            
            if price.competitor_name == '_our_':
                result[price.product_id]['our_price'] = price.price
            else:
                result[price.product_id]['competitors'][price.competitor_name] = price.price
        
        return result
    
    def _calculate_avg_competitor_price(self, prices: Dict) -> float:
        """Средняя цена конкурентов"""
        all_prices = []
        for product in prices.values():
            all_prices.extend(product['competitors'].values())
        
        return sum(all_prices) / len(all_prices) if all_prices else 0