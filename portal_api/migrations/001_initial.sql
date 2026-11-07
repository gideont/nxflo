CREATE TABLE roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK(length(trim(name)) BETWEEN 1 AND 80),
    description TEXT NOT NULL DEFAULT '',
    is_builtin INTEGER NOT NULL DEFAULT 0 CHECK(is_builtin IN (0,1)),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    google_subject TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    display_name TEXT NOT NULL,
    email_verified INTEGER NOT NULL CHECK(email_verified IN (0,1)),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','revoked')),
    role_id INTEGER REFERENCES roles(id) ON DELETE RESTRICT,
    is_owner INTEGER NOT NULL DEFAULT 0 CHECK(is_owner IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT,
    status_changed_at TEXT,
    status_changed_by INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    CHECK(status != 'approved' OR is_owner = 1 OR role_id IS NOT NULL),
    CHECK(is_owner = 0 OR (status = 'approved' AND role_id IS NULL))
);
CREATE UNIQUE INDEX only_one_owner ON users(is_owner) WHERE is_owner = 1;
CREATE INDEX users_status_created ON users(status,created_at);
CREATE INDEX users_role ON users(role_id);
CREATE TRIGGER protect_owner_update BEFORE UPDATE OF is_owner,status,google_subject ON users
WHEN OLD.is_owner = 1 AND (NEW.is_owner != 1 OR NEW.status != 'approved' OR NEW.google_subject != OLD.google_subject)
BEGIN
    SELECT RAISE(ABORT,'The portal owner is protected');
END;
CREATE TRIGGER protect_owner_delete BEFORE DELETE ON users WHEN OLD.is_owner = 1
BEGIN
    SELECT RAISE(ABORT,'The portal owner is protected');
END;
CREATE TABLE permissions (
    key TEXT PRIMARY KEY,
    module TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('view','create','edit','delete')),
    label TEXT NOT NULL,
    UNIQUE(module,action)
);
CREATE TABLE role_permissions (
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_key TEXT NOT NULL REFERENCES permissions(key) ON DELETE RESTRICT,
    PRIMARY KEY(role_id,permission_key)
);
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK(length(trim(name)) BETWEEN 1 AND 120),
    created_at TEXT NOT NULL
);
CREATE TABLE user_project_access (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    granted_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    PRIMARY KEY(user_id,project_id)
);
CREATE INDEX project_access_project ON user_project_access(project_id);
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX sessions_user ON sessions(user_id);
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    subject_user_id INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX audit_subject ON audit_log(subject_user_id,id);
