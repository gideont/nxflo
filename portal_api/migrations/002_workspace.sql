ALTER TABLE projects ADD COLUMN customer TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN site_code TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','in_progress','completed','on_hold'));
ALTER TABLE projects ADD COLUMN health TEXT NOT NULL DEFAULT 'on_track' CHECK(health IN ('on_track','in_progress','watch','on_hold','delayed'));
ALTER TABLE projects ADD COLUMN start_date TEXT;
ALTER TABLE projects ADD COLUMN rfs_date TEXT;
ALTER TABLE projects ADD COLUMN notes TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN updated_at TEXT;
UPDATE projects SET updated_at=created_at;
CREATE TABLE tasks (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
 group_name TEXT NOT NULL DEFAULT 'Implementation',
 owner_name TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','in_progress','completed','on_hold')),
 effort_md REAL NOT NULL DEFAULT 0 CHECK(effort_md>=0 AND effort_md<=100000),
 start_date TEXT,
 end_date TEXT,
 notes TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 CHECK(start_date IS NULL OR end_date IS NULL OR start_date<=end_date)
);
CREATE INDEX tasks_project ON tasks(project_id,id);
