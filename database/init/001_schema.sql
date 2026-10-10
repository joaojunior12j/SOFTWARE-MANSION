BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    email VARCHAR(200) UNIQUE NOT NULL,
    role VARCHAR(20) NOT NULL
        CHECK (role IN ('OWNER', 'OPERATOR', 'ADMIN')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS correlations (
    correlation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_triggered VARCHAR(50) NOT NULL,
    confidence_score DOUBLE PRECISION
        CHECK (confidence_score BETWEEN 0.0 AND 1.0),
    event_ids UUID[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS devices (
    device_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hardware_id VARCHAR(100) UNIQUE NOT NULL,
    device_type VARCHAR(30) NOT NULL,
    label VARCHAR(100),
    zone_partition VARCHAR(5),
    zone_number INTEGER,
    ip_address VARCHAR(45),
    protocol VARCHAR(20),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    config JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    event_id UUID NOT NULL DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    account_id VARCHAR(10) NOT NULL,
    source_type VARCHAR(30) NOT NULL
        CHECK (source_type IN (
            'PERIMETER_SENSOR',
            'CAMERA',
            'ALARM_PANEL',
            'SIMULATOR'
        )),
    device_hardware_id VARCHAR(100),
    zone_partition VARCHAR(5),
    zone_number INTEGER,
    sia_code VARCHAR(5),
    event_status VARCHAR(20) NOT NULL,
    priority_level VARCHAR(10) NOT NULL
        CHECK (priority_level IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    correlation_id UUID REFERENCES correlations(correlation_id),
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, timestamp)
);

SELECT create_hypertable(
    'events',
    'timestamp',
    if_not_exists => TRUE,
    migrate_data => TRUE
);

CREATE INDEX IF NOT EXISTS idx_events_account_timestamp
    ON events (account_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_zone_timestamp
    ON events (zone_partition, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_correlation
    ON events (correlation_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS alarms (
    alarm_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    correlation_id UUID REFERENCES correlations(correlation_id),
    title VARCHAR(200) NOT NULL,
    description TEXT,
    priority_level VARCHAR(10) NOT NULL
        CHECK (priority_level IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    state VARCHAR(20) NOT NULL DEFAULT 'UNACKNOWLEDGED'
        CHECK (state IN (
            'UNACKNOWLEDGED',
            'ACKNOWLEDGED',
            'RESTORED',
            'CLEARED',
            'SHELVED'
        )),
    zone_partition VARCHAR(5),
    triggered_at TIMESTAMPTZ NOT NULL,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by UUID REFERENCES users(user_id),
    cleared_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alarms_active_priority
    ON alarms (state, priority_level, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alarms_correlation
    ON alarms (correlation_id);

CREATE TABLE IF NOT EXISTS alarm_shelving (
    shelving_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alarm_id UUID NOT NULL REFERENCES alarms(alarm_id),
    justification TEXT NOT NULL,
    shelved_by UUID NOT NULL REFERENCES users(user_id),
    shelved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    unshelved_at TIMESTAMPTZ,
    CHECK (expires_at > shelved_at)
);

CREATE INDEX IF NOT EXISTS idx_alarm_shelving_expiration
    ON alarm_shelving (expires_at)
    WHERE unshelved_at IS NULL;

COMMIT;

