"""Performance monitoring and logging for the SQL Agent.

Tracks:
- Query latency
- Model accuracy
- Error rates
- Database connection pool
- API response times
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


# Configure logging
def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure root logger with file and console handlers."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    logger = logging.getLogger("iads_agent")
    logger.setLevel(log_level)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    
    # File handler
    file_handler = logging.FileHandler(log_dir / "agent.log")
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


logger = setup_logging()


# Metrics tracking
class MetricsCollector:
    """Collects and stores performance metrics."""
    
    def __init__(self, metrics_file: str = "logs/metrics.jsonl"):
        self.metrics_file = Path(metrics_file)
        self.metrics_file.parent.mkdir(exist_ok=True)
        self.metrics = []
    
    def record_query(
        self,
        question: str,
        latency_ms: float,
        accuracy: float,
        rows_returned: int,
        error: str | None = None,
        model_used: str = "gpt-4",
    ) -> None:
        """Record a query execution metric."""
        metric = {
            "timestamp": datetime.utcnow().isoformat(),
            "question": question[:100],  # Truncate for privacy
            "latency_ms": round(latency_ms, 2),
            "accuracy": round(accuracy, 2),
            "rows_returned": rows_returned,
            "error": error,
            "model_used": model_used,
        }
        
        self.metrics.append(metric)
        self._write_metric(metric)
        logger.info(f"Query recorded: {latency_ms:.0f}ms, accuracy={accuracy:.0%}")
    
    def record_db_operation(
        self,
        operation: str,
        duration_ms: float,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Record a database operation."""
        metric = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "db_operation",
            "operation": operation,
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "error": error,
        }
        
        self.metrics.append(metric)
        self._write_metric(metric)
    
    def _write_metric(self, metric: dict) -> None:
        """Append metric to JSONL file."""
        try:
            with open(self.metrics_file, "a") as f:
                f.write(json.dumps(metric) + "\n")
        except IOError as e:
            logger.error(f"Failed to write metric: {e}")
    
    def get_stats(self, hours: int = 24) -> dict[str, Any]:
        """Get statistics for the last N hours."""
        try:
            df = pd.read_json(self.metrics_file, lines=True)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            
            # Filter by time
            cutoff = datetime.utcnow() - pd.Timedelta(hours=hours)
            df = df[df["timestamp"] >= cutoff]
            
            if df.empty:
                return {"error": f"No data for last {hours} hours"}
            
            queries = df[df.get("type") != "db_operation"]
            
            stats = {
                "total_queries": len(queries),
                "avg_latency_ms": round(queries["latency_ms"].mean(), 2),
                "p50_latency_ms": round(queries["latency_ms"].quantile(0.5), 2),
                "p95_latency_ms": round(queries["latency_ms"].quantile(0.95), 2),
                "p99_latency_ms": round(queries["latency_ms"].quantile(0.99), 2),
                "avg_accuracy": round(queries["accuracy"].mean(), 3),
                "error_rate": round((queries["error"].notna().sum() / len(queries)) * 100, 2) if len(queries) > 0 else 0,
                "total_rows_returned": queries["rows_returned"].sum(),
            }
            
            return stats
        
        except Exception as e:
            logger.error(f"Failed to compute stats: {e}")
            return {"error": str(e)}
    
    def get_recent_errors(self, limit: int = 10) -> list[dict]:
        """Get most recent errors."""
        try:
            df = pd.read_json(self.metrics_file, lines=True)
            errors = df[df["error"].notna()].tail(limit)
            return errors.to_dict("records")
        except Exception:
            return []


# Global metrics collector
metrics = MetricsCollector()


# Timing context manager
class Timer:
    """Context manager for measuring execution time."""
    
    def __init__(self, name: str, callback=None):
        self.name = name
        self.start_time = None
        self.callback = callback
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        logger.debug(f"{self.name} took {duration_ms:.2f}ms")
        
        if self.callback:
            self.callback(duration_ms)
    
    @property
    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        return (time.time() - self.start_time) * 1000
