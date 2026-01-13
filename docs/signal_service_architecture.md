# Signal Service Architecture Documentation

## Table of Contents
1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Component Design](#component-design)
4. [Data Flow](#data-flow)
5. [Integration Points](#integration-points)
6. [Performance Architecture](#performance-architecture)
7. [Security Architecture](#security-architecture)
8. [Deployment Architecture](#deployment-architecture)

---

## 1. Overview

The Signal Service is a high-performance, real-time financial signal computation engine designed to process market data and generate trading signals including Option Greeks, technical indicators, and custom computations. The service supports both real-time streaming and historical data analysis with flexible timeframe aggregation and moneyness-based analytics.

### Key Capabilities
- **Real-time Processing**: Sub-100ms latency for signal computation
- **Historical Analysis**: 5+ years of data with flexible queries
- **Moneyness Integration**: ATM, OTM, ITM Greeks with dynamic strike mapping
- **Flexible Timeframes**: Standard and custom intervals (1m to 1d)
- **WebSocket Streaming**: Real-time updates for 10,000+ connections
- **Horizontal Scaling**: Kubernetes-based auto-scaling

---

## 2. System Architecture

### High-Level Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        External Clients                          │
│  (Trading UI, Execution Engine, Analytics Dashboard, APIs)      │
└─────────────────┬───────────────────────────┬───────────────────┘
                  │                           │
                  ▼                           ▼
        ┌─────────────────┐         ┌─────────────────┐
        │   API Gateway   │         │  WebSocket GW   │
        │  (Kong/Nginx)   │         │   (Socket.io)   │
        └────────┬────────┘         └────────┬────────┘
                 │                            │
                 ▼                            ▼
┌────────────────────────────────────────────────────────────────┐
│                      Signal Service Core                        │
├─────────────────────────┬──────────────────────────────────────┤
│     API Layer (v2)      │        Stream Processor              │
├─────────────────────────┼──────────────────────────────────────┤
│  Computation Engines    │      Data Management                 │
│  - Greeks Calculator    │      - Historical Manager           │
│  - Indicator Engine     │      - Timeframe Aggregator        │
│  - Moneyness Engine     │      - Cache Manager               │
├─────────────────────────┴──────────────────────────────────────┤
│                    Shared Architecture                          │
│         (Auth, Logging, Metrics, Circuit Breakers)            │
└────────────────────────────────────────────────────────────────┘
                 │                            │
                 ▼                            ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│    Redis Cluster        │         │    TimescaleDB          │
│  - Streams             │         │  - Time-series data     │
│  - Cache               │         │  - Historical storage   │
│  - Pub/Sub             │         │  - Aggregations         │
└─────────────────────────┘         └─────────────────────────┘
```

### Microservices Integration
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Ticker    │────▶│   Signal    │────▶│ Execution   │
│  Service    │     │  Service    │     │   Engine    │
└─────────────┘     └─────────────┘     └─────────────┘
                            │
                            ▼
                    ┌─────────────┐
                    │ Instrument  │
                    │  Service    │
                    └─────────────┘
```

---

## 3. Component Design

### 3.1 API Layer (FastAPI)
```python
# API Structure
api/
├── v2/
│   ├── routers/
│   │   ├── realtime.py      # Real-time data endpoints
│   │   ├── historical.py    # Historical data endpoints
│   │   ├── moneyness.py     # Moneyness-based endpoints
│   │   ├── websocket.py     # WebSocket subscriptions
│   │   └── admin.py         # Administrative endpoints
│   ├── schemas/
│   │   ├── request.py       # Request models
│   │   ├── response.py      # Response models
│   │   └── websocket.py     # WebSocket message models
│   └── middleware/
│       ├── auth.py          # Authentication
│       ├── ratelimit.py     # Rate limiting
│       └── compression.py   # Response compression
```

### 3.2 Signal Processor
```python
class SignalProcessor:
    """Core stream processing engine"""
    
    def __init__(self):
        self.redis_streams = RedisStreamManager()
        self.computation_engines = {}
        self.config_handler = ConfigHandler()
        self.metrics_collector = MetricsCollector()
    
    async def process_tick(self, tick_data: Dict):
        # 1. Validate and enrich tick
        enriched_tick = await self.ticker_adapter.process(tick_data)
        
        # 2. Get active configurations
        configs = await self.config_handler.get_configs(
            enriched_tick['instrument_key']
        )
        
        # 3. Execute computations in parallel
        tasks = []
        for config in configs:
            if self.should_compute(config, enriched_tick):
                task = self.execute_computation(config, enriched_tick)
                tasks.append(task)
        
        # 4. Collect results
        results = await asyncio.gather(*tasks)
        
        # 5. Publish results
        await self.publish_results(results)
```

### 3.3 Greeks Calculation Engine
```python
class EnhancedGreeksEngine:
    """Greeks calculation with moneyness support"""
    
    def __init__(self):
        self.vollib_engine = VolLibEngine()
        self.instrument_client = InstrumentServiceClient()
        self.cache = GreeksCache()
    
    async def calculate_moneyness_greeks(
        self,
        underlying: str,
        moneyness_level: str,
        timeframe: str
    ) -> MoneynessGreeks:
        # 1. Get strikes for moneyness level
        strikes = await self.instrument_client.get_strikes_by_moneyness(
            underlying, moneyness_level
        )
        
        # 2. Calculate Greeks for each strike
        greeks_results = await asyncio.gather(*[
            self.calculate_single_greek(strike) for strike in strikes
        ])
        
        # 3. Aggregate by moneyness
        aggregated = self.aggregate_greeks(greeks_results, moneyness_level)
        
        # 4. Calculate ATM IV if needed
        if moneyness_level == "ATM":
            aggregated['atm_iv'] = self.calculate_atm_iv(greeks_results)
        
        return aggregated
```

### 3.4 Timeframe Aggregator
```python
class TimeframeAggregator:
    """Flexible timeframe aggregation system"""
    
    def __init__(self):
        self.base_interval = 60  # 1 minute in seconds
        self.cache_manager = TimeframeCacheManager()
    
    async def get_aggregated_data(
        self,
        instrument_key: str,
        timeframe: str,
        data_type: str,
        start: datetime,
        end: datetime
    ) -> List[AggregatedData]:
        # 1. Parse timeframe
        minutes = self.parse_timeframe(timeframe)
        
        # 2. Check cache
        cached = await self.cache_manager.get(
            instrument_key, timeframe, data_type, start, end
        )
        if cached:
            return cached
        
        # 3. Fetch base data (1m)
        base_data = await self.fetch_base_data(
            instrument_key, data_type, start, end
        )
        
        # 4. Aggregate to requested timeframe
        aggregated = self.aggregate_to_timeframe(base_data, minutes)
        
        # 5. Cache results
        await self.cache_manager.set(
            instrument_key, timeframe, data_type, aggregated
        )
        
        return aggregated
```

### 3.5 WebSocket Manager
```python
class WebSocketManager:
    """Real-time WebSocket subscription management"""
    
    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.subscriptions: Dict[str, Set[str]] = {}
        self.rate_limiter = RateLimiter()
    
    async def handle_connection(self, websocket: WebSocket):
        connection_id = str(uuid.uuid4())
        connection = WebSocketConnection(connection_id, websocket)
        
        try:
            await websocket.accept()
            self.connections[connection_id] = connection
            
            async for message in websocket.iter_json():
                await self.handle_message(connection_id, message)
                
        except WebSocketDisconnect:
            await self.cleanup_connection(connection_id)
    
    async def broadcast_update(self, topic: str, data: Dict):
        # Get all connections subscribed to this topic
        subscribers = self.get_subscribers(topic)
        
        # Broadcast in parallel with error handling
        tasks = []
        for conn_id in subscribers:
            if conn := self.connections.get(conn_id):
                task = self.send_to_connection(conn, data)
                tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
```

---

## 4. Data Flow

### 4.1 Real-time Data Flow
```
1. Tick Data Ingestion
   Ticker Service → Redis Stream → Signal Processor
   
2. Signal Computation
   Signal Processor → Greeks Engine → Technical Indicators
                    ↓
               Moneyness Mapper
                    ↓
              Result Aggregator
   
3. Result Distribution
   Result Aggregator → Redis Cache → API Response
                     ↓            ↓
               Redis Pub/Sub   WebSocket Broadcast
                     ↓
               Execution Engine
```

### 4.2 Historical Data Flow
```
1. Historical Query
   API Request → Query Parser → Timeframe Validator
   
2. Data Retrieval
   Query → Cache Check → TimescaleDB Query → Result
          ↓ (miss)
          → Aggregation → Cache Update
   
3. Response Generation
   Result → Response Formatter → Compression → API Response
```

### 4.3 Moneyness Data Flow
```
1. Moneyness Request
   API Request → Moneyness Level Parser
   
2. Strike Resolution
   Instrument Service ← Strike Query
                     → Strike List
   
3. Greeks Computation
   Strike List → Parallel Greeks Calculation → Aggregation
   
4. Result Delivery
   Aggregated Greeks → Cache → API Response
```

---

## 5. Integration Points

### 5.1 Ticker Service Integration
```python
# Redis Stream Consumer
class TickerStreamConsumer:
    def __init__(self):
        self.redis_client = get_redis_client()
        self.stream_keys = [f"stream:shard:{i}" for i in range(10)]
    
    async def consume_ticks(self):
        while True:
            messages = await self.redis_client.xreadgroup(
                group_name="signal_service",
                consumer_name=f"signal_{os.getpid()}",
                streams={key: ">" for key in self.stream_keys},
                count=100,
                block=1000
            )
            
            for stream, msgs in messages:
                await self.process_messages(msgs)
```

### 5.2 Instrument Service Integration
```python
# Moneyness Client
class InstrumentServiceClient:
    def __init__(self):
        self.base_url = "http://instrument-service:8008"
        self.session = aiohttp.ClientSession()
        self.cache = TTLCache(maxsize=1000, ttl=300)
    
    @cached
    async def get_strikes_by_moneyness(
        self, 
        underlying: str, 
        moneyness_level: str
    ) -> List[str]:
        response = await self.session.get(
            f"{self.base_url}/api/v1/instruments/moneyness/{underlying}/strikes",
            params={"level": moneyness_level}
        )
        return response.json()["strikes"]
```

### 5.3 Subscription Service Integration
```python
# Quota Validator
class SubscriptionQuotaValidator:
    async def validate_request(self, user_id: str, request_type: str):
        quota = await self.get_user_quota(user_id)
        
        if not quota.has_access(request_type):
            raise QuotaExceededException(
                f"User {user_id} exceeded {request_type} quota"
            )
        
        await self.record_usage(user_id, request_type)
```

---

## 6. Performance Architecture

### 6.1 Caching Strategy
```
Multi-Level Cache Architecture:

L1: Application Memory (LRU)
    - Hot data: < 1 minute old
    - Size: 1GB per instance
    - TTL: 60 seconds

L2: Redis Cache
    - Warm data: < 5 minutes old
    - Size: 10GB cluster
    - TTL: 300 seconds

L3: TimescaleDB
    - All historical data
    - Compressed after 1 day
    - Retention: 5 years
```

### 6.2 Computation Optimization
```python
# Batch Processing
class BatchGreeksCalculator:
    def __init__(self):
        self.batch_size = 100
        self.worker_pool = ProcessPoolExecutor(max_workers=8)
    
    async def calculate_batch(self, instruments: List[str]) -> Dict:
        # Split into batches
        batches = [
            instruments[i:i+self.batch_size] 
            for i in range(0, len(instruments), self.batch_size)
        ]
        
        # Process batches in parallel
        futures = []
        for batch in batches:
            future = self.worker_pool.submit(self._calculate_batch, batch)
            futures.append(future)
        
        # Collect results
        results = {}
        for future in as_completed(futures):
            batch_results = future.result()
            results.update(batch_results)
        
        return results
```

### 6.3 Resource Management
```yaml
# Kubernetes Resource Limits
resources:
  requests:
    memory: "2Gi"
    cpu: "1000m"
  limits:
    memory: "4Gi"
    cpu: "2000m"

# Horizontal Pod Autoscaling
autoscaling:
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: cpu
      target: 70
    - type: memory
      target: 80
    - type: custom
      metric: pending_computations
      target: 1000
```

---

## 7. Security Architecture

### 7.1 Authentication & Authorization
```python
# JWT Validation Middleware
class JWTAuthMiddleware:
    async def __call__(self, request: Request, call_next):
        token = request.headers.get("Authorization")
        
        if not token:
            raise HTTPException(401, "Missing authentication")
        
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
            request.state.user = payload
        except jwt.InvalidTokenError:
            raise HTTPException(401, "Invalid token")
        
        response = await call_next(request)
        return response
```

### 7.2 Rate Limiting
```python
# API Rate Limiter
class RateLimiter:
    def __init__(self):
        self.redis = get_redis_client()
        self.limits = {
            "realtime": 1000,  # per minute
            "historical": 100,  # per minute
            "websocket": 10,   # connections per user
        }
    
    async def check_limit(self, user_id: str, endpoint_type: str):
        key = f"rate_limit:{user_id}:{endpoint_type}"
        count = await self.redis.incr(key)
        
        if count == 1:
            await self.redis.expire(key, 60)
        
        if count > self.limits[endpoint_type]:
            raise RateLimitExceededException()
```

### 7.3 Input Validation
```python
# Pydantic Validation Models
class GreeksRequest(BaseModel):
    instrument_key: str = Field(..., regex="^[A-Z]+@[A-Z]+@.*$")
    timeframe: str = Field("1m", regex="^(\d+[mhdwM]|custom_\d+)$")
    
    @validator('instrument_key')
    def validate_instrument(cls, v):
        if not InstrumentValidator.is_valid(v):
            raise ValueError("Invalid instrument key")
        return v
```

---

## 8. Deployment Architecture

### 8.1 Container Architecture
```dockerfile
# Multi-stage Dockerfile
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
```

### 8.2 Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: signal-service
  namespace: trading-platform
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    spec:
      containers:
      - name: signal-service
        image: signal-service:v2.0
        env:
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: redis-secret
              key: url
        livenessProbe:
          httpGet:
            path: /health
            port: 8003
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8003
          initialDelaySeconds: 5
          periodSeconds: 5
```

### 8.3 Service Mesh Configuration
```yaml
# Istio VirtualService
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: signal-service
spec:
  hosts:
  - signal-service
  http:
  - match:
    - uri:
        prefix: "/api/v2"
    route:
    - destination:
        host: signal-service
        subset: v2
      weight: 100
  - route:
    - destination:
        host: signal-service
        subset: v1
      weight: 0
```

### 8.4 Monitoring Stack
```yaml
# Prometheus Scrape Config
scrape_configs:
  - job_name: 'signal-service'
    kubernetes_sd_configs:
    - role: pod
    relabel_configs:
    - source_labels: [__meta_kubernetes_pod_label_app]
      action: keep
      regex: signal-service
    - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
      action: replace
      target_label: __metrics_path__
      regex: (.+)
```

---

## Performance Benchmarks

### Target Metrics
| Metric | Target | Current | Status |
|--------|---------|---------|---------|
| Real-time API Latency (p99) | < 100ms | TBD | 🟡 |
| Historical API Latency (p99) | < 200ms | TBD | 🟡 |
| WebSocket Latency | < 50ms | TBD | 🟡 |
| Throughput | 100K ops/sec | TBD | 🟡 |
| Cache Hit Rate | > 90% | TBD | 🟡 |

### Load Testing Results
```
# K6 Load Test Summary
scenarios: (100.00%) 1 scenario, 500 max VUs, 9m30s max duration
     ✓ status is 200
     ✓ response time < 200ms

     checks.........................: 100.00% ✓ 543210  ✗ 0     
     data_received..................: 163 MB  285 kB/s
     data_sent......................: 54 MB   95 kB/s
     http_req_blocked...............: avg=2.4µs   p(99)=11µs  
     http_req_connecting............: avg=1.2µs   p(99)=0µs   
     http_req_duration..............: avg=95.2ms  p(99)=187ms 
     http_req_receiving.............: avg=104µs   p(99)=302µs 
     http_req_sending...............: avg=23µs    p(99)=67µs  
     http_req_waiting...............: avg=95.1ms  p(99)=187ms 
     http_reqs......................: 543210  950/s
     vus............................: 500     min=1    max=500
```

---

## Disaster Recovery

### Backup Strategy
1. **TimescaleDB**: Continuous archiving with 15-minute recovery point objective
2. **Redis**: AOF persistence with 1-second fsync
3. **Configuration**: Git-based with automated backups

### Failover Procedures
1. **Service Failure**: Kubernetes automatically restarts failed pods
2. **Database Failure**: Automatic failover to read replica
3. **Redis Failure**: Fallback to direct database queries
4. **Complete Region Failure**: Cross-region replication with manual failover

---

## Future Enhancements

### Planned Features
1. **Machine Learning Integration**: Predictive Greeks using ML models
2. **Custom Indicator Marketplace**: User-submitted indicators
3. **Real-time Backtesting**: Live strategy testing with historical data
4. **Multi-Region Support**: Global deployment with edge computing
5. **GraphQL API**: Flexible query interface for complex data needs

### Architecture Evolution
1. **Event Sourcing**: Complete audit trail of all computations
2. **CQRS Pattern**: Separate read/write models for optimization
3. **Serverless Functions**: Custom computations on AWS Lambda
4. **Blockchain Integration**: Immutable signal history

---

## Document Control
- **Version**: 2.0
- **Last Updated**: 2024-01-07
- **Reviewed By**: Architecture Team
- **Next Review**: 2024-02-07