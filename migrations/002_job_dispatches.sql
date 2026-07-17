CREATE TABLE IF NOT EXISTS job_dispatches (
  job_id CHAR(36) PRIMARY KEY,
  payload JSON NOT NULL,
  state VARCHAR(16) NOT NULL DEFAULT 'pending',
  attempts INT UNSIGNED NOT NULL DEFAULT 0,
  last_error VARCHAR(1000) NULL,
  created_at DATETIME(6) NOT NULL,
  dispatched_at DATETIME(6) NULL,
  updated_at DATETIME(6) NOT NULL,
  INDEX ix_job_dispatches_state_created (state, created_at),
  CONSTRAINT fk_job_dispatches_job FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);
