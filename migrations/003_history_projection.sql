ALTER TABLE job_dispatches
  ADD COLUMN source_label VARCHAR(255)
    GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload, '$.user_label'))) STORED,
  ADD COLUMN prompt_text TEXT
    GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(payload, '$.prompt'))) STORED;
