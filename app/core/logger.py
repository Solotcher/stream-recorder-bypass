import logging
import sys
from logging.handlers import RotatingFileHandler
from app.core.config import settings
import contextvars

trace_id = contextvars.ContextVar("trace_id", default="-")

def set_trace_id(value: str):
    """현재 컨텍스트의 trace_id를 설정하고 reset 시 사용할 토큰을 반환합니다."""
    return trace_id.set(value)

def get_trace_id() -> str:
    """현재 컨텍스트의 trace_id를 조회합니다."""
    return trace_id.get()

def reset_trace_id(token):
    """이전 trace_id 컨텍스트 상태로 복구합니다."""
    try:
        trace_id.reset(token)
    except Exception:
        pass

class TraceIdFilter(logging.Filter):
    def filter(self, record):
        record.trace_id = trace_id.get()
        return True

def setup_logger():
    logger = logging.getLogger(settings.APP_NAME)
    
    if logger.hasHandlers():
        return logger

    logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    logger.addFilter(TraceIdFilter())
    
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(trace_id)s] [%(module)s:%(lineno)d] - %(message)s"
    )
    
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # File Handler (10MB 로테이션, 최대 5개 백업)
    file_handler = RotatingFileHandler(
        filename=f"{settings.DATA_DIR}/app.log", 
        encoding="utf-8",
        maxBytes=10 * 1024 * 1024,
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()
