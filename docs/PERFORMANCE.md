# Performance Optimization - Implementation Guide

## Overview

This document describes the performance optimizations implemented for the ACGS Enterprise Manager to support 50-500 concurrent users with <200ms response times.

## Components

### 1. Database Query Optimization

**File:** `/database/indexes.sql`

Comprehensive indexing strategy including:
- **Primary indexes** on frequently queried columns (status, type, dates)
- **Composite indexes** for common query patterns (e.g., assignee + status)
- **Full-text search indexes** using PostgreSQL's pg_trgm extension
- **JSONB GIN indexes** for efficient JSON field queries
- **Partial indexes** for specific conditions (active records, pending approvals)

**Apply indexes:**
```bash
psql -U postgres -d acgs_manager -f database/indexes.sql
```

### 2. Redis Caching Layer

**Files:**
- `/backend/cache/redis_client.py` - Redis client with connection pooling
- `/backend/cache/__init__.py` - Cache module exports
- `/backend/middleware/caching.py` - HTTP caching middleware

**Features:**
- Async Redis client with connection pooling (max 50 connections)
- Automatic caching of GET requests
- Configurable TTL per endpoint (60s - 3600s)
- Cache invalidation on write operations
- Cache hit/miss tracking via X-Cache header

**Configuration:**
```bash
# Environment variables
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_DB=0
export REDIS_PASSWORD=  # Optional
```

**Cache TTL Settings:**
- Short TTL (60s): Recommendations, AI operations
- Default TTL (300s): Tasks, assets, projects, infrastructure, financial, documents
- Long TTL (3600s): Health checks, static data

### 3. Connection Pooling

**File:** `/backend/database.py`

SQLAlchemy async engine with:
- Connection pre-ping for health verification
- Connection recycling after 1 hour
- Automatic connection management

### 4. Load Testing

**File:** `/tests/load/locustfile.py`

Locust-based load testing simulating realistic user behavior:
- 90% regular users, 10% admin users
- Weighted task distribution matching real usage patterns
- Authentication flow simulation
- CRUD operations across all domains

**Run load tests:**
```bash
# Install locust
pip install locust

# Run with web UI
locust -f tests/load/locustfile.py --host=http://localhost:8000

# Run headless (500 users, 50 users/sec spawn rate, 5 min duration)
locust -f tests/load/locustfile.py --host=http://localhost:8000 \
  --users 500 --spawn-rate 50 --run-time 5m --headless
```

## Performance Targets

✅ **Concurrent Users:** 50-500 users  
✅ **Response Time:** <200ms for common operations  
✅ **Database Queries:** Optimized with indexes  
✅ **Cache Hit Rate:** >70% for read operations  
✅ **Connection Pooling:** Efficient resource usage  

## Monitoring

### Health Check Endpoint

```bash
curl http://localhost:8000/health
```

Response includes:
- Overall system status
- Database health
- Redis cache health

### Response Time Headers

All responses include:
- `X-Process-Time`: Request processing time in seconds
- `X-Cache`: HIT or MISS (for cached responses)

### Cache Statistics

Monitor Redis:
```bash
redis-cli INFO stats
redis-cli INFO keyspace
```

## Cache Invalidation

Cache is automatically invalidated on write operations:

```python
from backend.middleware.caching import invalidate_cache_for_domain

# Invalidate all tasks cache
await invalidate_cache_for_domain("tasks")

# Invalidate specific entity
await invalidate_cache_for_entity("tasks", task_id)
```

## Deployment Checklist

1. **Install Redis:**
   ```bash
   # Ubuntu/Debian
   sudo apt-get install redis-server
   
   # macOS
   brew install redis
   
   # Start Redis
   redis-server
   ```

2. **Apply Database Indexes:**
   ```bash
   psql -U postgres -d acgs_manager -f database/indexes.sql
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment:**
   ```bash
   export REDIS_HOST=localhost
   export REDIS_PORT=6379
   export DATABASE_URL=postgresql+asyncpg://user:pass@localhost/acgs_manager
   ```

5. **Run Load Tests:**
   ```bash
   locust -f tests/load/locustfile.py --host=http://localhost:8000
   ```

6. **Verify Performance:**
   - Check response times in Locust dashboard
   - Monitor cache hit rate in Redis
   - Verify database query performance with EXPLAIN ANALYZE

## Optimization Results

Expected improvements:
- **50-70% reduction** in database query time (with indexes)
- **60-80% reduction** in API response time (with caching)
- **3-5x increase** in throughput (concurrent requests)
- **70-90% cache hit rate** for read-heavy operations

## Troubleshooting

### Redis Connection Issues

```bash
# Check Redis is running
redis-cli ping

# Check Redis logs
tail -f /var/log/redis/redis-server.log
```

### Slow Queries

```sql
-- Enable query logging in PostgreSQL
ALTER DATABASE acgs_manager SET log_min_duration_statement = 100;

-- View slow queries
SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;
```

### Cache Issues

```python
# Clear all cache
redis-cli FLUSHDB

# Monitor cache operations
redis-cli MONITOR
```

## Future Enhancements

- [ ] Add database query result caching at ORM level
- [ ] Implement read replicas for database scaling
- [ ] Add CDN for static frontend assets
- [ ] Implement request rate limiting
- [ ] Add database connection pool monitoring
- [ ] Implement cache warming strategies
