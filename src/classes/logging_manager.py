"""
Professional Logging Manager
Provides clean, informative logging with periodic summaries and spam reduction.
"""

import time
import logging
from collections import defaultdict
from typing import Dict, Any, Optional
from dataclasses import dataclass
from threading import Lock

@dataclass
class ConnectionStatus:
    """Track connection status for clean logging."""
    is_connected: bool = False
    last_connected_time: Optional[float] = None
    last_disconnected_time: Optional[float] = None
    connection_attempts: int = 0
    successful_connections: int = 0
    last_error: Optional[str] = None
    consecutive_failures: int = 0
    last_log_time: float = 0.0

class LoggingManager:
    """
    Professional logging manager that provides:
    - Spam reduction for repetitive messages
    - Periodic summary reports
    - Status-at-a-glance logging
    - Connection state tracking
    """
    
    def __init__(self, summary_interval: float = 15.0):
        self.summary_interval = summary_interval
        self._lock = Lock()
        
        # Connection status tracking
        self._connections: Dict[str, ConnectionStatus] = {}
        
        # Polling statistics
        self._polling_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'total_polls': 0,
            'successful_polls': 0,
            'failed_polls': 0,
            'last_poll_time': 0.0,
            'last_success_time': 0.0,
            'last_failure_time': 0.0,
            'last_summary_time': 0.0,
            'current_status': 'unknown'
        })
        
        # Operation counters
        self._operation_counters: Dict[str, int] = defaultdict(int)
        
        # Spam prevention
        self._spam_filter: Dict[str, float] = {}
        self._spam_cooldown = 5.0  # 5 seconds between similar messages
    
    def log_connection_status(self, logger: logging.Logger, service_name: str, 
                            is_connected: bool, details: str = "") -> None:
        """
        Log connection status with spam reduction.
        
        Args:
            logger: Logger instance
            service_name: Name of the service (e.g., 'MAVLink', 'PX4', 'Video')
            is_connected: Current connection status
            details: Additional details for the log
        """
        with self._lock:
            status = self._connections.get(service_name, ConnectionStatus())
            current_time = time.time()
            
            # Check if status actually changed
            status_changed = status.is_connected != is_connected
            
            if is_connected:
                if status_changed:
                    status.successful_connections += 1
                    status.last_connected_time = current_time
                    status.consecutive_failures = 0
                    logger.info(f"[{service_name}] Connected {details}".strip())
                    
                status.is_connected = True
            else:
                status.connection_attempts += 1
                status.consecutive_failures += 1
                status.last_disconnected_time = current_time
                
                if status_changed:
                    logger.warning(f"[{service_name}] Disconnected {details}".strip())
                elif self._should_log_failure(service_name, current_time):
                    uptime = int(current_time - (status.last_connected_time or current_time))
                    logger.warning(f"[{service_name}] Still disconnected "
                                 f"({status.consecutive_failures} attempts, {uptime}s) {details}".strip())
                
                status.is_connected = False
                status.last_error = details
            
            status.last_log_time = current_time
            self._connections[service_name] = status
    
    def log_polling_activity(self, logger: logging.Logger, service_name: str, 
                           success: bool, details: str = "") -> None:
        """
        Log polling activity with periodic summaries.
        
        Args:
            logger: Logger instance
            service_name: Name of the polling service
            success: Whether the poll was successful
            details: Additional details
        """
        with self._lock:
            stats = self._polling_stats[service_name]
            current_time = time.time()
            
            stats['total_polls'] += 1
            
            if success:
                stats['successful_polls'] += 1
                stats['last_success_time'] = current_time
                stats['current_status'] = 'healthy'
            else:
                stats['failed_polls'] += 1
                stats['last_failure_time'] = current_time
                if stats['failed_polls'] > stats['successful_polls']:
                    stats['current_status'] = 'degraded'
            
            stats['last_poll_time'] = current_time
            
            # Log periodic summary
            if current_time - stats['last_summary_time'] >= self.summary_interval:
                self._log_polling_summary(logger, service_name, stats)
                stats['last_summary_time'] = current_time
    
    def log_operation(self, logger: logging.Logger, operation: str, 
                     level: str = 'info', details: str = "") -> None:
        """
        Log operations with spam reduction.
        
        Args:
            logger: Logger instance
            operation: Operation name
            level: Log level ('debug', 'info', 'warning', 'error')
            details: Additional details
        """
        if self._should_log_operation(operation):
            message = f"[{operation}] {details}".strip() if details else f"[{operation}]"
            
            log_func = getattr(logger, level, logger.info)
            log_func(message)
            
            with self._lock:
                self._operation_counters[operation] += 1
    
    def log_system_summary(self, logger: logging.Logger) -> None:
        """Log a comprehensive system status summary."""
        with self._lock:
            current_time = time.time()
            
            logger.info("=== SYSTEM STATUS SUMMARY ===")
            
            # Connection status
            if self._connections:
                logger.info("Connection Status:")
                for service, status in self._connections.items():
                    if status.is_connected:
                        uptime = int(current_time - (status.last_connected_time or current_time))
                        logger.info(f"  {service}: CONNECTED ({uptime}s uptime)")
                    else:
                        downtime = int(current_time - (status.last_disconnected_time or current_time))
                        logger.info(f"  {service}: DISCONNECTED ({downtime}s down, {status.consecutive_failures} failures)")
            
            # Polling status
            if self._polling_stats:
                logger.info("Polling Status:")
                for service, stats in self._polling_stats.items():
                    success_rate = (stats['successful_polls'] / max(stats['total_polls'], 1)) * 100
                    logger.info(f"  {service}: {stats['current_status'].upper()} "
                               f"({success_rate:.1f}% success, {stats['total_polls']} total)")
            
            # Operation counts (top 5)
            if self._operation_counters:
                top_ops = sorted(self._operation_counters.items(), key=lambda x: x[1], reverse=True)[:5]
                logger.info("Top Operations:")
                for op, count in top_ops:
                    logger.info(f"  {op}: {count}")
            
            logger.info("=============================")
    
    def _should_log_failure(self, service_name: str, current_time: float) -> bool:
        """Determine if we should log a failure message (spam reduction)."""
        last_log = self._connections.get(service_name, ConnectionStatus()).last_log_time
        return current_time - last_log >= self._spam_cooldown
    
    def _should_log_operation(self, operation: str) -> bool:
        """Determine if we should log an operation (spam reduction)."""
        current_time = time.time()
        last_log = self._spam_filter.get(operation, 0)
        
        if current_time - last_log >= self._spam_cooldown:
            self._spam_filter[operation] = current_time
            return True
        return False
    
    def _log_polling_summary(self, logger: logging.Logger, service_name: str, stats: Dict[str, Any]) -> None:
        """Log a polling summary."""
        total = stats['total_polls']
        successful = stats['successful_polls']
        failed = stats['failed_polls']
        success_rate = (successful / max(total, 1)) * 100
        
        status_symbol = {
            'healthy': 'OK',
            'degraded': 'WARN',
            'unknown': '?'
        }.get(stats['current_status'], '?')
        
        logger.info(f"[{service_name}] Poll Summary: {stats['current_status'].upper()} "
                   f"({success_rate:.1f}% success, {total} polls in {self.summary_interval}s)")

# Global logging manager instance
logging_manager = LoggingManager()