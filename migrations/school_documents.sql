-- Additive migration. Apply deliberately after backup; never executed by app startup.
CREATE TABLE IF NOT EXISTS school_documents (
  document_id CHAR(36) PRIMARY KEY,
  scope_key CHAR(64) NOT NULL,
  filename VARCHAR(180) NOT NULL,
  payload MEDIUMTEXT NOT NULL,
  status ENUM('draft','approved','published','superseded','withdrawn') NOT NULL DEFAULT 'draft',
  revision INT NOT NULL DEFAULT 1,
  updated_by VARCHAR(100) NOT NULL,
  updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX document_scope (scope_key), INDEX document_status (status)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS school_document_heads (
  scope_key CHAR(64) PRIMARY KEY,
  document_id CHAR(36) NULL,
  version INT NOT NULL DEFAULT 0,
  FOREIGN KEY (document_id) REFERENCES school_documents(document_id)
) ENGINE=InnoDB;
