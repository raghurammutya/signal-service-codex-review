Okay, this is a comprehensive handover\! I'll provide you with the content for the detailed architecture document, structured logically with all the considerations we've discussed. You can then copy this into Google Docs and add diagrams/formatting.

-----

**Signal Service: Detailed Architecture Handover Document**

**Version:** 1.0
**Date:** June 23, 2025

-----

**1. Executive Summary**

The Signal Service is a Python-based microservice designed to process real-time and historical market tick data, compute various financial and technical indicators, and generate outputs for downstream services. It adheres to a stateless, event-driven architecture, leveraging Redis Streams for efficient data ingestion and output, Redis for caching, TimescaleDB for historical data, and Kubernetes for scalable deployment. Its primary goal is sub-second computation response times to support high-frequency trading and analytical needs.

-----

**2. Detailed Requirements**

The Signal Service is built to fulfill the following requirements:

  * **Serverless-like Operation:** Primarily focused on computation, triggered by incoming data streams, with minimal internal state.
  * **Real-Time Tick Processing:** Must process individual tick data points within milliseconds.
  * **Historical Data Processing (Backtesting Support):** Capable of processing historical tick data streams from a backtesting server, treating historical timestamps as the "current" time for computations.
  * **Statelessness with Smart Caching:** The service instances are stateless, but they leverage Redis for fast access to historical data and configurations, significantly reducing TimescaleDB lookups. Redis caches are updated frequently for failover resilience.
  * **Symbol-Specific Processing & Routing:** Designed to process computations for specific sets of instruments/symbols, routed efficiently via Redis Streams' partitioning.
  * **Diverse Computations:** Supports the execution of:
      * **Option Greeks:** Using `py_vollib`, requiring synchronized data for options, underlying assets, and INDVIX. Calculations are performed for Open, High, Low, and Close prices.
      * **Technical Indicators:** Using `pandas_ta`, executed efficiently via dynamically built strategies for batches.
      * **Internal Python Functions:** Custom methods defined within the Signal Service.
      * **External Python Functions:** Dynamically imported and securely executed code from external files.
  * **Parallel Computation:** Independent computations (Greeks, TAs, custom functions) are processed in parallel within a single tick processing cycle to meet sub-second response times.
  * **Dynamic Configuration:** The service receives configuration JSONs periodically from the Subscription Manager, defining which computations to run, with what parameters, frequency, and data timeframes.
  * **Output Persistence & Publication:**
      * Computation results are appended to Redis Lists for consumption by downstream services.
      * (Future Work/Consideration): Output may also be published to dedicated Redis Streams or updated in TimescaleDB for persistent storage.

-----

**3. High-Level Architecture**

**(Imagine a diagram here: "System Context Diagram")**

  * **Ticker Service:** Publishes raw tick data to Redis Streams.
  * **Redis Streams:** Acts as the high-throughput message queue for tick data and potentially configuration updates. Also used for internal caching.
  * **Signal Service:** Consumes from Redis Streams, performs computations, and outputs results.
  * **Subscription Manager:** Manages and publishes configuration data (originally to RabbitMQ, now effectively to Redis Streams) and serves historical data via API if not found in TimescaleDB. Stores its primary configuration data in MongoDB.
  * **TimescaleDB:** Stores comprehensive historical market data.
  * **MongoDB:** (Used by Subscription Manager for its primary config storage).

**Key Architectural Shifts from Original Design:**

  * **Redis Streams as Primary Ingestion:** Replaces RabbitMQ for real-time tick data delivery.
  * **Redis as Central Hub:** Redis is now critical for:
      * Tick ingestion.
      * Configuration updates.
      * Raw tick caching.
      * Aggregated data caching.
      * Computation results caching.

-----

**4. Detailed Technical Architecture**

**(Imagine a diagram here: "Signal Service Internal Component Diagram")**

**A. Core Principles:**

  * **Asynchronous Processing:** Built entirely on `asyncio` for high concurrency and non-blocking I/O operations.
  * **Dependency Injection:** Leverages FastAPI's `Depends` for managing shared resources and inter-component communication, enhancing testability and modularity.
  * **Modular Design:** Logic is broken down into small, focused classes and functions.
  * **Robust Error Handling:** Uses a custom exception hierarchy and structured logging for clear error identification and handling.
  * **Observability:** Integrated Prometheus metrics and comprehensive logging.

**B. Key Components and Their Responsibilities:**

  * **`app/main.py`:**
      * FastAPI application entry point.
      * Initializes shared connections (`connection_manager.initialize()`).
      * Registers `SignalProcessor`'s `start_consuming_redis_streams` at startup.
      * Defines public API endpoints (`/health`, `/ready`, `/metrics`).
  * **`app/services/signal_processor.py` (Core Orchestrator):**
      * **Role:** The central component, orchestrating the entire tick processing pipeline.
      * **`__init__`:** Initializes all sub-components (`GreeksCalculator`, `RealTimeGreeksCalculator`, `PandasTAExecutor`, `ConfigHandler`). Retrieves all shared connections (Redis, TimescaleDB, RabbitMQ channel for config updates, if still used) via `connection_manager`. Initializes Prometheus metrics.
      * **`start_consuming_redis_streams`:** Manages Redis Streams consumer group creation (`XGROUP CREATE`) and continuous reading (`XREADGROUP`).
      * **`process_redis_stream_message`:** Decodes messages from Redis Stream, filters by `state="U"`, dispatches to `process_tick_async`, updates `state="P"`, and `XACK`s the message.
      * **`process_tick_async`:** Main tick processing loop. Retrieves relevant configuration, fetches/aggregates data, then dispatches to specific computation methods (`compute_greeks`, `compute_technical_indicators`, etc.) concurrently using `asyncio.gather`.
      * **Data Aggregation (`get_aggregated_data`, `get_cached_or_aggregate_data`, `get_data_from_continuous_aggregate`, `get_data_from_raw_timescaledb`, `get_latest_raw_ticks`, `merge_aggregated_with_raw_ticks`):** Manages fetching data from Redis cache or TimescaleDB, combining continuous aggregate data with the very latest raw ticks for the most up-to-date view.
      * **`should_execute`:** Determines if computations should run based on the configured `frequency` and the current (or historical) timestamp.
      * **`load_initial_configurations`:** At startup, loads last-known configurations from Redis (primary) with a MongoDB fallback.
      * **`compute_greeks` (Dispatcher):** Dispatches to `compute_historical_greeks` or `compute_realtime_greeks` based on configuration.
      * **`compute_technical_indicators`:** Prepares data and calls `PandasTAExecutor`.
      * **`compute_python_functions`:** Placeholder for internal Python function execution.
      * **`compute_external_functions`:** Calls `external_function_executor.load_and_execute_external_function`.
  * **`app/services/config_handler.py`:**
      * **Role:** Manages the lifecycle of Signal Service configurations.
      * **`__init__`:** Receives the Redis connection.
      * **`process_config_update`:** Entry point for new configuration JSONs (from Redis Streams, sent by Subscription Manager). Validates the JSON against `ConfigSchema` (Pydantic), manages `current_configs` cache, and orchestrates task cancellation/restart for active configurations.
      * **`apply_config`:** Orchestrates the application of a configuration, primarily by calling `setup_scheduled_tasks`.
      * **`setup_scheduled_tasks`:** Creates and manages long-running `asyncio.Task` instances that periodically call `execute_computations` based on the configured `frequency` (e.g., every 5 minutes, hourly).
      * **`execute_computations`:** This method is the *bridge*. It takes the active configuration and the injected `SignalProcessor` instance, then calls the relevant computation methods (`compute_greeks`, `compute_technical_indicators`, etc.) on the `SignalProcessor` instance.
      * **`validate_config`:** Uses `ConfigSchema` (Pydantic) to validate incoming configuration JSONs.
      * **`invalidate_cache_for_config`:** Deletes relevant cached data from Redis when a configuration is updated or deleted.
  * **`app/services/pandas_ta_executor.py`:**
      * **Role:** Executes technical indicator computations.
      * **`__init__`:** Receives the Redis connection.
      * **`build_strategy`:** Dynamically constructs `pandas_ta` strategy dictionaries from configuration.
      * **`execute_indicators`:** Prepares pandas DataFrame (column renaming, sorting), runs `df.ta.strategy()`, and caches results in Redis.
  * **`app/services/greeks_calculator.py`:**
      * **Role:** Performs batch greeks calculations for historical data.
      * **`calculate_historical_greeks_parallel`:** Orchestrates multiprocessing pool for parallel greeks computation.
      * **`wrapper_function`:** Prepares data for a single historical data point and calls `_calculate_greeks_for_instrument`.
      * **`_calculate_greeks_for_instrument`:** Aligns option, underlying, and INDVIX historical data, then iterates to call the core greeks functions (e.g., `calculate_iv`, `calculate_delta`) for each OHLC point.
  * **`app/services/realtime_greeks_calculator.py`:**
      * **Role:** Performs real-time greeks calculations for single ticks.
      * **`__init__`:** Receives the Redis connection.
      * **`calculate_realtime_greeks`:** Implements data buffering with a short timeout to handle out-of-order underlying/INDVIX tick arrival. Falls back to "last known good" data from Redis. Calls the core greeks functions.
  * **`app/services/greeks_calculation_engine.py` (NEW - Proposed):**
      * **Role:** Contains the core, stateless mathematical functions for calculating IV and individual greeks.
      * **`calculate_iv`, `calculate_delta`, `calculate_gamma`, `calculate_rho`, `calculate_theta`, `calculate_vega`:** These methods perform the actual `py_vollib` calls.
      * **Refactoring Note:** These functions should be moved here from `GreeksCalculator` and `RealTimeGreeksCalculator` to eliminate code duplication.
  * **`app/services/external_function_executor.py`:**
      * **Role:** Manages secure, dynamic loading and execution of external Python code.
      * **`load_and_execute_external_function`:** Uses `importlib.util` and `restrictedpython` to load and run user-provided functions with controlled access to internal methods/metrics.
  * **`app/errors.py`:**
      * **Role:** Defines custom exception hierarchy (`SignalServiceError`, `ConfigurationError`, `DataAccessError`, `ComputationError`, etc.) for structured error handling.

**C. Data Flow within Signal Service (Detailed):**

1.  **Tick Ingestion:**

      * Ticker Service `XADD`s tick data (JSON, with `state="U"`) to `tick_stream:EXCH@STOCK`.
      * `SignalProcessor.start_consuming_redis_streams` loops `XREADGROUP` for its assigned streams.
      * `SignalProcessor.process_redis_stream_message` receives messages, decodes them.
      * If `state="U"`, dispatches to `SignalProcessor.process_tick_async`.
      * After `process_tick_async` completes, it `XADD`s the tick back to the stream with `state="P"` and `XACK`s the original message.

2.  **Configuration Update Flow:**

      * Subscription Manager publishes config JSON (with `action="update"` or `delete`) to `signal_config_updates` Redis Stream.
      * `SignalProcessor` has a dedicated consumer for this stream (similar to tick consumption, to be fully integrated).
      * `SignalProcessor.handle_config_update` receives the message.
      * Calls `ConfigHandler.process_config_update`.
      * `ConfigHandler.process_config_update` validates (Pydantic), stores in `current_configs`, cancels/waits for old task, starts new `apply_config` task.
      * `ConfigHandler.apply_config` then calls `setup_scheduled_tasks`.
      * `ConfigHandler.setup_scheduled_tasks` creates an `asyncio.Task` that runs `execute_computations` periodically based on the configured `frequency` (e.g., every 5 seconds).

3.  **Computation Execution (Triggered by `process_tick_async` or `execute_computations`):**

      * **Data Aggregation/Retrieval:** `SignalProcessor.get_aggregated_data` is called with `instrument_key`, `interval`, `current_time`.
          * Checks Redis cache (`agg_data:`) first.
          * If not found, queries TimescaleDB Continuous Aggregates (for known intervals).
          * If not in CAs, queries raw TimescaleDB (`time_bucket`).
          * All TimescaleDB queries use `self.timescaledb_conn`.
          * Combines aggregated data with `raw_ticks:` from Redis.
      * **Computation Dispatch:** `SignalProcessor.process_tick_async` or `ConfigHandler.execute_computations` (via `asyncio.gather`) concurrently call:
          * `SignalProcessor.compute_greeks` (which dispatches to `HistoricalGreeksCalculator` or `RealTimeGreeksCalculator`).
          * `SignalProcessor.compute_technical_indicators` (calls `PandasTAExecutor`).
          * `SignalProcessor.compute_python_functions`.
          * `SignalProcessor.compute_external_functions`.
      * **Computation Output:** Results of computations are written to Redis Lists (e.g., `computed_data:{symbol}`).

**D. Error Handling Strategy:**

  * **Custom Exception Hierarchy (`app/errors.py`):**
      * `SignalServiceError` (base)
      * `ConfigurationError`, `InvalidConfigurationError`
      * `DataAccessError`, `TimescaleDBConnectionError`, `RedisConnectionError`
      * `ExternalServiceError`, `SubscriptionManagerAPIError`, `RabbitMQError` (though RabbitMQ is mostly removed now)
      * `ComputationError`, `ExternalFunctionExecutionError`
  * **`try...except` Blocks:** Specific exception types are caught first, with a general `Exception` as a fallback.
  * **Structured Logging:** Replaced `print` statements with `logging` (lazy `%` formatting, `exc_info=True` for tracebacks).
  * **Exception Chaining:** `raise MyCustomError(...) from original_e` is used to preserve the traceback.
  * **Resilience:** Errors in one computation or data fetch ideally do not halt the entire tick processing, but are logged and result in `None` or an error message. Critical errors lead to `RuntimeError` at startup or service crash for Kubernetes restart.

**E. Logging and Metrics:**

  * **Logging:** Configured using Python's `logging` module. Logs include timestamp, service name, message, and potentially `exc_info` for tracebacks.
  * **Prometheus Metrics:**
      * Exposed via `/metrics` endpoint on port 8001.
      * `Histogram`: `signal_service_processing_time` (measures tick processing duration).
      * `Counter`: `signal_service_tick_count` (total ticks processed), `signal_service_error_count` (total errors encountered).
      * `Gauge`: `signal_service_queue_length` (pending messages in Redis Stream).

**F. Scalability (Kubernetes Focus):**

  * **Horizontal Pod Autoscaling (HPA):**
      * Driven by Kubernetes Custom Metrics API, monitoring:
          * CPU Utilization (e.g., target 70%).
          * Custom metrics like `signal_service_processing_time_bucket` (average/P95 latency).
          * Potentially, `signal_service_queue_length` from Redis Streams (via custom metrics adapter).
      * `minReplicas` and `maxReplicas` defined in `deployment.yaml`.
  * **Readiness and Liveness Probes:**
      * `/health` and `/ready` endpoints ensure Kubernetes can correctly manage pod lifecycle and traffic routing.
  * **Resource Requests and Limits:**
      * Defined in `deployment.yaml` to ensure fair resource allocation and prevent resource exhaustion.
  * **Stateless Design:** Signal Service instances are stateless (rely on external Redis/TimescaleDB), enabling easy horizontal scaling.

-----

**5. Database Design and Interactions**

**A. Redis**

  * **Purpose:** High-performance, in-memory cache and message queue.
  * **Key Patterns:**
      * `tick_stream:{exchange}@{stock_code}`: Redis Stream for incoming raw ticks (Ticker Service publishes, Signal Service consumes).
      * `signal_config_updates`: Redis Stream for configuration updates (Subscription Manager publishes, Signal Service consumes).
      * `config:{instrument_key}-{interval}-{frequency}` (String): Stores the latest configuration JSON for a specific computation type. Updated by `ConfigHandler`.
      * `agg_data:{instrument_key}:{interval}` (String): Caches the latest aggregated data (from TimescaleDB Continuous Aggregates or raw `time_bucket` queries). Managed by `SignalProcessor`.
      * `raw_ticks:{instrument_key}` (String/List - as discussed, list with LTRIM is preferred): Stores the most recent raw ticks for an instrument. Updated by `SignalProcessor` upon tick arrival.
      * `computed_data:{symbol}` (List): Appends the combined original tick data and computation results (greeks, TAs) for downstream consumption.
      * `ta_results:{instrument_key}:{interval}:{frequency}` (String): Caches the results of technical indicator computations.
  * **Memory Management:**
      * Configured via `redis.conf` with `maxmemory` (e.g., `1gb`) and `maxmemory-policy` (e.g., `allkeys-lru`).
      * Expiry times (`EX`) are set on individual keys (`redis_cache_expiry`, `raw_ticks_expiry`) to manage freshness and memory.
  * **Persistence:** Relies on the Redis instance's AOF/RDB configuration (controlled outside the Signal Service).

**B. TimescaleDB**

  * **Purpose:** Long-term persistent storage for raw and aggregated historical market data.
  * **Schema (Relevant to Signal Service):**
      * `historical_data` table (raw ticks):
          * `time` (TIMESTAMP with timezone, PRIMARY KEY)
          * `instrument_key` (Text, PRIMARY KEY)
          * `interval` (Text, PRIMARY KEY)
          * `open` (Double), `high` (Double), `low` (Double), `close` (Double), `volume` (BigInteger), `oi` (BigInteger)
          * `expiry_date` (Date), `option_type` (Text), `strikeprice` (Double)
          * (Optional: Columns for pre-computed greeks if stored by Ticker Service)
      * **Continuous Aggregates:**
          * Tables like `1min_aggregate`, `5min_aggregate`, `1hr_aggregate` (or dynamically named) automatically created and maintained by TimescaleDB for known intervals. These store pre-aggregated OHLCV, OI, etc.
  * **Optimization:** Leverages TimescaleDB's `time_bucket` function for efficient aggregation on raw data, and directly queries Continuous Aggregates for common intervals.
  * **Connection:** Managed via `shared_architecture.connection_manager.get_timescaledb_session()`.

**C. MongoDB**

  * **Purpose:** Fallback mechanism for initial configuration loading if Redis is unavailable or empty at Signal Service startup. (Primary configuration storage for Subscription Manager).
  * **Collection:** Assumed to be `configurations` (contains JSON documents representing Signal Service configurations).
  * **Connection:** Managed via `shared_architecture.connection_manager.get_mongo_client()`.

-----

**6. Interfaces & APIs**

**A. External APIs Exposed by Signal Service (FastAPI Endpoints):**

  * **`GET /health`**
      * **Purpose:** Basic health check, returns `{"status": "ok"}`.
      * **Usage:** For Kubernetes liveness probes.
  * **`GET /ready`**
      * **Purpose:** Readiness check, verifies essential dependencies (TimescaleDB, Redis, RabbitMQ channel). Returns `{"status": "ok"}` if ready.
      * **Usage:** For Kubernetes readiness probes.
  * **`GET /metrics`**
      * **Purpose:** Exposes Prometheus-compatible application metrics.
      * **Usage:** Scraped by Prometheus for monitoring and HPA.

**B. External Interfaces Consumed by Signal Service:**

  * **Ticker Service (via Redis Streams):**
      * **Stream Name Pattern:** `tick_stream:{exchange}@{stock_code}` (e.g., `tick_stream:NSE@NIFTY`).
      * **Consumption:** `XREADGROUP GROUP <consumer_group_name> <consumer_name> COUNT 10 STREAMS <stream_name> >` (reading unprocessed ticks).
      * **Acknowledgment:** `XACK <stream_name> <consumer_group_name> <message_id>`.
      * **State Update:** `XADD <stream_name> FIELDS {..., "state": "P"}` (publishing back processed ticks).
      * **Tick Data Format:** JSON object including `instrument_key`, `ltt`, OHLCV, `state` (`"U"` or `"P"`), and other tick attributes.
  * **Subscription Manager API:**
      * **Endpoint:** `GET /historical_data`
      * **Query Parameters:** `instrument_key=<key>`, `start_time=<ts>`, `end_time=<ts>`, `interval=<interval>`.
      * **Response:** JSON array of historical data points, each including `datetime`, OHLCV, and other relevant fields.
  * **Subscription Manager (via Redis Streams - for configs):**
      * **Stream Name:** `signal_config_updates`
      * **Consumption:** `XREADGROUP` to receive config update messages.
      * **Message Format:** JSON object with `{"config_json": <full_config_json_string>, "action": "update"|"delete"}`.

-----

**7. File Structure Design**

```
signal_service/
├── app/                                 # Core application logic
│   ├── __init__.py                      # App-level initialization
│   ├── main.py                          # Entry point for FastAPI/Service, API endpoints
│   ├── api/
│   │   ├── __init__.py
│   │   └── endpoints/                   # Specific endpoints (example.py for generic API)
│   │       └── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                    # Configuration management (environment variables)
│   │   ├── dependencies.py              # Dependency injection setup (e.g., for get_db)
│   │   └── security.py                  # Security (e.g., JWT, hashing - if needed)
│   ├── models/                          # SQLAlchemy models/enums specific to this service
│   │   ├── __init__.py                  # Imports shared_architecture.models and local models
│   │   └── example.py                   # Example model (remove if not needed)
│   ├── schemas/                         # Pydantic schemas for request/response validation
│   │   ├── __init__.py
│   │   └── config_schema.py             # Defines ConfigSchema (moved from config_handler.py)
│   ├── services/                        # Business logic and core service components
│   │   ├── __init__.py
│   │   ├── signal_processor.py          # Main processing orchestrator
│   │   ├── config_handler.py            # Handles config lifecycle and scheduled tasks
│   │   ├── external_function_executor.py# Handles secure dynamic external code execution
│   │   ├── greeks_calculator.py         # Historical batch greeks calculation
│   │   ├── realtime_greeks_calculator.py# Real-time single tick greeks calculation
│   │   ├── pandas_ta_executor.py        # Technical indicator execution
│   │   └── greeks_calculation_engine.py # NEW: Core stateless greeks calculation functions
│   ├── utils/                           # Utility functions
│   │   ├── __init__.py
│   │   └── helper.py                    # Example helper function (remove if not needed)
│   └── errors.py                        # Custom exception definitions
├── tests/                               # Unit/Integration tests
│   ├── __init__.py
│   ├── test_example.py                  # Example test file
│   ├── test_signal_processor.py         # Tests for SignalProcessor logic
│   ├── test_config_handler.py           # Tests for ConfigHandler logic
│   └── test_greeks_calculation.py       # Tests for both greeks calculators and engine
├── docker/                              # Docker-related files
│   ├── Dockerfile
│   └── docker-compose.yml
├── kubernetes/                          # Kubernetes manifests
│   ├── service.yaml
│   └── deployment.yaml
├── README.md                            # Project overview
├── requirements.txt                     # Python dependencies
└── .env                                 # Environment variables (local/testing)
```

**Refactoring Notes for File Structure:**

  * **`config_schema.py`:** I've explicitly placed `ConfigSchema` into `app/schemas/config_schema.py`. This is good practice as schemas are shared data definitions. It would then be imported into `config_handler.py`.
  * **`greeks_calculation_engine.py`:** This is the new file to hold the shared core greeks math, preventing duplication.

-----

**8. Gaps and Future Work (Not Coded/Implemented)**

This section outlines the functionality that has been designed and discussed but requires further implementation or external configuration.

**A. Core Business Logic Implementation:**

  * **`compute_greeks` (Full Implementation):**
      * The core logic within `greeks_calculation_engine.py` needs to be fully integrated with `py_vollib` for all greeks.
      * `_calculate_greeks_for_instrument` in `greeks_calculator.py` and `calculate_realtime_greeks` in `realtime_greeks_calculator.py` need to correctly call these engine functions.
      * **Critical:** The `UnderlyingClass` placeholder in `prepare_data_for_greeks` and the related Pydantic model (`Underlying`) need to be replaced with the actual data structure for the underlying asset.
      * **INDVIX Data:** Ensure `indvix_data` is properly retrieved and used in greeks calculations.
  * **`compute_technical_indicators` (Full Implementation):**
      * While `PandasTAExecutor` is ready, the `compute_technical_indicators` method in `SignalProcessor` needs to fully prepare the data and correctly utilize the `PandasTAExecutor`.
  * **`compute_python_functions` (Full Implementation):**
      * Logic for dynamically finding and executing *internal* Python functions based on `config.get("functions")` needs to be implemented. This will involve using `getattr` to call methods on the `SignalProcessor` or other utility classes.
  * **`compute_external_functions` (Full Implementation):**
      * The `external_function_executor.py` provides the framework. However, thorough testing of its sandboxing for security and its ability to correctly import and execute *your specific external files* with their functions and parameters is required.

**B. Data Management & Persistence:**

  * **Output Publication to TimescaleDB/Redis Streams:**
      * Currently, computation results are written to Redis Lists (`computed_data:{symbol}`).
      * **Major Gap:** The original requirement also mentioned publishing results via RabbitMQ and updating TimescaleDB. Given the shift to Redis Streams for input, publishing *computation results to dedicated Redis Streams* (e.g., `signal_output_stream:EXCH@STOCK`) for downstream consumption (e.g., by the Strategy Service) would be the consistent and high-performance approach.
      * Implementation for periodically updating TimescaleDB with computed results (if persistent storage beyond Redis is needed for signals) is also outstanding.

**C. Infrastructure & Deployment:**

  * **Redis Memory Management Configuration:**
      * The `maxmemory` and `maxmemory-policy` (e.g., `allkeys-lru`) settings must be explicitly configured for the Redis instance used by the service (via `redis.conf` mounted in Docker Compose/Kubernetes).
  * **TimescaleDB Continuous Aggregates Definition:**
      * The actual `CREATE MATERIALIZED VIEW` statements for all `known_intervals` (1min, 5min, 1hr, etc.) need to be defined and applied to TimescaleDB. These will create the optimized aggregate tables.
  * **RabbitMQ/Redis Streams Configuration for Config Updates:**
      * The Subscription Manager needs to be configured to publish configuration updates to the `signal_config_updates` Redis Stream in the correct format.
      * The Signal Service needs to fully integrate a consumer for this stream.

**D. Robustness & Observability:**

  * **Comprehensive Edge Case Handling:**
      * Detailed implementation and testing are needed for scenarios like:
          * Missing `ltt` in tick data.
          * Corrupted or malformed tick data.
          * Network interruptions during data fetches (TimescaleDB, Subscription Manager API, Redis).
          * Longer-than-expected computation times.
          * Concurrent configuration updates causing data inconsistencies (beyond the "wait for completion" strategy).
      * Data validation should be applied at ingestion points where possible.
  * **Advanced Frequency Scheduling:**
      * For "daily", "weekly", "monthly" frequencies, where `asyncio.sleep` might not be precise enough for specific times of day/week/month, consider integrating a dedicated scheduler library like `APScheduler` or relying on Kubernetes CronJobs.
  * **Detailed Logging Configuration:**
      * Set up a proper logging handler (e.g., to file, to `stdout` for container logs) and formatter (structured JSON logging is highly recommended).
  * **Kubernetes Autoscaling (HPA Custom Metrics):**
      * While Prometheus metrics are exposed, configuring Kubernetes HPA to use *custom metrics* (like average processing time or Redis Stream pending messages) requires defining Custom Metrics APIs or External Metrics Adapters in Kubernetes, which is an external configuration task.

subsequently we have removed mongodb from the infrastructure as it was being used only for communication between signal_service and subscription_service
-----

This document provides a comprehensive overview for handing over the Signal Service. It details the design, architecture, interfaces, and outlines the remaining implementation efforts and considerations.

-----