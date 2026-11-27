from sqlalchemy.orm import Session

from app.models import PriceSnapshot, Product


def evaluate_watches(
    db: Session, product: Product, previous: PriceSnapshot | None, current: PriceSnapshot
) -> None:
    """Milestone 6. No-op for now."""
