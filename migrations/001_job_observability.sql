CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(128) PRIMARY KEY, checksum CHAR(64) NOT NULL, applied_at DATETIME(6) NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
  job_id CHAR(36) PRIMARY KEY, request_id CHAR(36) NULL, status VARCHAR(16) NOT NULL,
  workflow_id VARCHAR(128) NULL, workflow_version VARCHAR(64) NULL, workflow_category VARCHAR(64) NULL, model_name VARCHAR(255) NULL,
  worker_id VARCHAR(255) NULL, comfyui_prompt_id VARCHAR(255) NULL, current_node_id VARCHAR(128) NULL, current_node_type VARCHAR(255) NULL,
  last_completed_node_id VARCHAR(128) NULL, progress TINYINT UNSIGNED NOT NULL DEFAULT 0,
  submitted_at DATETIME(6) NULL, queued_at DATETIME(6) NULL, started_at DATETIME(6) NULL, completed_at DATETIME(6) NULL,
  failed_at DATETIME(6) NULL, cancelled_at DATETIME(6) NULL, queue_wait_ms BIGINT UNSIGNED NULL, execution_ms BIGINT UNSIGNED NULL, total_ms BIGINT UNSIGNED NULL,
  retry_count INT UNSIGNED NOT NULL DEFAULT 0, error_stage VARCHAR(64) NULL, error_code VARCHAR(64) NULL, sanitized_error_message VARCHAR(1000) NULL,
  output_count INT UNSIGNED NOT NULL DEFAULT 0, cancel_requested_at DATETIME(6) NULL, last_event_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL, updated_at DATETIME(6) NOT NULL, version BIGINT UNSIGNED NOT NULL DEFAULT 0,
  INDEX ix_jobs_status_submitted (status, submitted_at), INDEX ix_jobs_workflow_submitted (workflow_id, submitted_at),
  INDEX ix_jobs_model_submitted (model_name, submitted_at), INDEX ix_jobs_worker_submitted (worker_id, submitted_at),
  INDEX ix_jobs_error_submitted (error_code, submitted_at), INDEX ix_jobs_prompt (comfyui_prompt_id)
);
CREATE TABLE IF NOT EXISTS job_events (
  event_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, event_key CHAR(64) NOT NULL, job_id CHAR(36) NOT NULL,
  event_type VARCHAR(64) NOT NULL, stage VARCHAR(64) NULL, resulting_status VARCHAR(16) NULL, node_id VARCHAR(128) NULL,
  node_type VARCHAR(255) NULL, progress_milestone TINYINT UNSIGNED NULL, error_code VARCHAR(64) NULL,
  sanitized_message VARCHAR(1000) NULL, metadata JSON NULL, created_at DATETIME(6) NOT NULL,
  UNIQUE KEY uq_job_events_key (job_id, event_key), INDEX ix_job_events_job_created (job_id, created_at, event_id),
  INDEX ix_job_events_type_created (event_type, created_at), CONSTRAINT fk_job_events_job FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);
CREATE TABLE IF NOT EXISTS job_outputs (
  output_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, job_id CHAR(36) NOT NULL, source_node_id VARCHAR(128) NULL,
  output_type VARCHAR(32) NOT NULL, storage_uri VARCHAR(512) NOT NULL, filename VARCHAR(255) NOT NULL, size_bytes BIGINT UNSIGNED NOT NULL,
  checksum CHAR(64) NULL, metadata JSON NULL, persisted_at DATETIME(6) NOT NULL,
  UNIQUE KEY uq_job_outputs_uri (job_id, storage_uri), CONSTRAINT fk_job_outputs_job FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);
