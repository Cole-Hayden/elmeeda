from datetime import date, datetime
from zoneinfo import ZoneInfo

# Every mock truck and shop is in Illinois, so "today" means today in Central time.
CENTRAL = ZoneInfo("America/Chicago")


def central_today() -> date:
    return datetime.now(CENTRAL).date()
