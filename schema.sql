-- =============================================================================
-- xxzw-video · PostgreSQL 目标 schema（阶段 5a，自 P1 `rag-service/schema.sql` 抽取）
-- =============================================================================
-- 只保留 P2 真正需要的 4 张表：
--   rag_user        本地账户（`core/security.py` 按角色判权）
--   rag_session     本地登录会话（Cookie 校验）
--   video_setting   视频 agent 设置，单行（id = 1）
--   rag_video_task  视频任务与分析结果（文件系统状态 JSON 的 PG 镜像）
--
-- 表名沿用 P1 命名（含 `rag_` 前缀）：两个项目使用**独立 database**
-- （方案 §7.1：一个 PG 容器、两个库），同名表不会冲突；改名只会带来无收益的测试改动。
--
-- 不引入 `CREATE EXTENSION vector` —— 本项目没有向量列（向量检索属 P1）。
-- 全部语句均为 IF NOT EXISTS，可重复执行（幂等）。
--
-- 执行方式：psql "$DATABASE_URL" -f schema.sql
-- =============================================================================

-- -----------------------------------------------------------------------------
-- -----------------------------------------------------------------------------
-- rag_user：本地账户。平台身份三列已删除。
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rag_user (
    id             bigserial    PRIMARY KEY,
    username       varchar(100) NOT NULL,
    password_hash  varchar(255) NOT NULL,
    role           varchar(20)  NOT NULL DEFAULT 'user',
    status         varchar(20)  NOT NULL DEFAULT 'active',
    created_at     timestamptz  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     timestamptz  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_rag_user_username UNIQUE (username),
    CONSTRAINT ck_rag_user_role   CHECK (role IN ('user', 'account_admin')),
    CONSTRAINT ck_rag_user_status CHECK (status IN ('active', 'disabled', 'deleting'))
);

-- -----------------------------------------------------------------------------
-- rag_session：本地登录会话（取代原平台会话表）。
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rag_session (
    id           bigserial   PRIMARY KEY,
    user_id      bigint      NOT NULL REFERENCES rag_user (id) ON DELETE CASCADE,
    token_hash   varchar(64) NOT NULL,
    expires_at   timestamptz NOT NULL,
    last_seen_at timestamptz,
    created_at   timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_session_token UNIQUE (token_hash)
);
CREATE INDEX IF NOT EXISTS idx_session_user_expiry ON rag_session (user_id, expires_at);
CREATE INDEX IF NOT EXISTS idx_session_expiry      ON rag_session (expires_at);

-- -----------------------------------------------------------------------------
-- video_setting：视频 agent 设置，单行（id = 1）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS video_setting (
    id               bigserial     PRIMARY KEY,
    asr_provider     varchar(50)   NOT NULL DEFAULT 'volcengine',
    asr_model        varchar(200)  NOT NULL DEFAULT 'bigmodel',
    asr_api_key      varchar(1000) NOT NULL DEFAULT '',
    asr_app_id       varchar(200)  NOT NULL DEFAULT '',
    asr_access_token varchar(1000) NOT NULL DEFAULT '',
    chat_base_url    varchar(500)  NOT NULL DEFAULT '',
    chat_model       varchar(200)  NOT NULL DEFAULT '',
    chat_api_key     varchar(1000) NOT NULL DEFAULT '',
    frames           integer       NOT NULL DEFAULT 12,
    updated_at       timestamptz   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    qa_model         varchar(200)  NOT NULL DEFAULT '',
    qa_base_url      varchar(500)  NOT NULL DEFAULT '',
    qa_api_key       varchar(1000) NOT NULL DEFAULT ''
);


-- -----------------------------------------------------------------------------
-- 视频任务（P2 侧）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rag_video_task (
    id                bigserial     PRIMARY KEY,
    task_id           varchar(36)   NOT NULL,
    source            varchar(2000) NOT NULL,
    kind              varchar(20)   NOT NULL,
    status            varchar(20)   NOT NULL,
    stage             varchar(50),
    created_at        timestamptz   NOT NULL,
    updated_at        timestamptz   NOT NULL,
    output_dir        varchar(1000),
    error             text,
    frames_requested  integer,
    transcript_source varchar(200),
    duration_seconds  double precision,
    transcript        text,
    summary           jsonb,
    report            jsonb,
    keyframes         jsonb,
    cost              jsonb,
    events            jsonb,
    qa_history        jsonb,
    video_path        varchar(1000),
    audio_path        varchar(1000),
    content_type      varchar(20)   NOT NULL DEFAULT 'video',
    post_text         text,
    author            varchar(200),
    hashtags          jsonb,
    publish_time      varchar(100),
    post_images       jsonb,
    image_captions    jsonb,
    owner_user_id     bigint,
    CONSTRAINT uq_video_task_task_id UNIQUE (task_id)
);
CREATE INDEX IF NOT EXISTS idx_video_task_created      ON rag_video_task (created_at);
CREATE INDEX IF NOT EXISTS idx_video_task_status       ON rag_video_task (status);
CREATE INDEX IF NOT EXISTS idx_video_task_kind         ON rag_video_task (kind);
CREATE INDEX IF NOT EXISTS idx_video_task_owner_status ON rag_video_task (owner_user_id, status);

-- 阶段 6：免登录访客影子账号与配额（幂等，可重复执行）
CREATE TABLE IF NOT EXISTS rag_visitor (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    visitor_id       varchar(64)  NOT NULL,
    token_hash       varchar(64)  NOT NULL,
    owner_user_id    bigint       NOT NULL REFERENCES rag_user (id) ON DELETE CASCADE,
    ip_hash          varchar(64),
    upload_count     integer      NOT NULL DEFAULT 0,
    upload_chars     bigint       NOT NULL DEFAULT 0,
    chat_count       integer      NOT NULL DEFAULT 0,
    status           varchar(20)  NOT NULL DEFAULT 'active',
    created_at       timestamptz  NOT NULL DEFAULT now(),
    last_seen_at     timestamptz  NOT NULL DEFAULT now(),
    expires_at       timestamptz,
    CONSTRAINT uq_rag_visitor_visitor_id UNIQUE (visitor_id)
);
CREATE INDEX IF NOT EXISTS idx_rag_visitor_owner ON rag_visitor (owner_user_id);

CREATE TABLE IF NOT EXISTS rag_visitor_quota_log (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    visitor_id   varchar(64)  NOT NULL,
    action       varchar(40)  NOT NULL,
    ref_id       varchar(100),
    amount       integer      NOT NULL DEFAULT 1,
    created_at   timestamptz  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rag_visitor_quota_log_visitor ON rag_visitor_quota_log (visitor_id, action, ref_id);

ALTER TABLE rag_video_task ADD COLUMN IF NOT EXISTS owner_visitor_id varchar(64);
