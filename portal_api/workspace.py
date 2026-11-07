"""Assigned-project workspace. Uses the same session, CSRF, and live permissions as admin APIs."""
from datetime import date
from flask import g, jsonify
from . import db

PROJECT_FIELDS = {'name':120, 'customer':120, 'site_code':80, 'status':30, 'health':30,
                  'start_date':10, 'rfs_date':10, 'notes':4000}
TASK_FIELDS = {'title':200, 'group_name':120, 'owner_name':200, 'status':30,
               'start_date':10, 'end_date':10, 'notes':4000, 'effort_md':None}
STATUSES = ('planned', 'in_progress', 'completed', 'on_hold')
HEALTH = ('on_track', 'in_progress', 'watch', 'on_hold', 'delayed')


def register_workspace(app, connection, authenticated, payload, Error):
    prefix = '/bms_integration_hub/api'

    def validate(data, fields, creating=False):
        result = {}
        for key, value in data.items():
            if key == 'effort_md':
                if type(value) not in (int, float) or not 0 <= value <= 100000:
                    raise Error('Effort must be between 0 and 100,000 days')
            elif key.endswith('_date'):
                if value in ('', None):
                    value = None
                else:
                    try:
                        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                            raise ValueError()
                    except (ValueError, TypeError):
                        raise Error('Use a valid ISO date (YYYY-MM-DD)')
            else:
                if not isinstance(value, str) or len(value.strip()) > fields[key]:
                    raise Error('Invalid ' + key.replace('_', ' '))
                value = value.strip()
                if key in ('name', 'title', 'group_name') and not value:
                    raise Error('Enter a ' + key.replace('_', ' '))
                if key == 'status' and value not in STATUSES or key == 'health' and value not in HEALTH:
                    raise Error('Choose a valid status')
            result[key] = value
        required = 'name' if fields is PROJECT_FIELDS else 'title'
        if creating and required not in result:
            raise Error('Enter a ' + required)
        return result

    def check_dates(record, end):
        if record.get('start_date') and record.get(end) and record['start_date'] > record[end]:
            raise Error('The end date must be on or after the start date')

    def project_access(project_id, permission):
        if not db.can_access(connection(), g.user, project_id, permission):
            raise Error('Project not found or action not permitted', 404)

    @app.get(prefix + '/workspace')
    @authenticated()
    def workspace():
        conn = connection()
        permitted = db.permissions_for(conn, g.user)
        projects = [dict(row) for row in conn.execute('SELECT * FROM projects ORDER BY name COLLATE NOCASE')
                    if db.can_access(conn, g.user, row['id'], 'projects.view')]
        ids = {p['id'] for p in projects}
        tasks = [dict(row) for row in conn.execute('SELECT * FROM tasks ORDER BY id')
                 if row['project_id'] in ids and db.can_access(conn, g.user, row['project_id'], 'tasks.view')]
        dates = [p['updated_at'] or p['created_at'] for p in projects] + [t['updated_at'] for t in tasks]
        return jsonify(projects=projects, tasks=tasks, permissions=permitted,
                       updated_at=max(dates) if dates else None)

    @app.post(prefix + '/workspace/projects')
    @authenticated(owner=True)
    def create_workspace_project():
        values = validate(payload(PROJECT_FIELDS), PROJECT_FIELDS, True)
        check_dates(values, 'rfs_date')
        conn = connection()
        with db.transaction(conn):
            values.update(created_at=db.now(), updated_at=db.now())
            keys = list(values)
            new_id = conn.execute('INSERT INTO projects (' + ','.join(keys) + ') VALUES (' + ','.join('?' for _ in keys) + ')',
                                  [values[k] for k in keys]).lastrowid
            record = dict(conn.execute('SELECT * FROM projects WHERE id=?', (new_id,)).fetchone())
            db.audit(conn, g.user['id'], 'project.created', 'projects', new_id, after=record)
        return jsonify(project=record), 201

    @app.patch(prefix + '/workspace/projects/<int:project_id>')
    @authenticated()
    def update_project(project_id):
        values = validate(payload(PROJECT_FIELDS), PROJECT_FIELDS)
        conn = connection()
        with db.transaction(conn):
            project_access(project_id, 'planning.edit')
            before = dict(conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone())
            check_dates({**before, **values}, 'rfs_date')
            values['updated_at'] = db.now()
            conn.execute('UPDATE projects SET ' + ','.join(k + '=?' for k in values) + ' WHERE id=?', [*values.values(), project_id])
            after = dict(conn.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone())
            db.audit(conn, g.user['id'], 'project.updated', 'projects', project_id, before, after)
        return jsonify(project=after)

    @app.post(prefix + '/workspace/projects/<int:project_id>/tasks')
    @authenticated()
    def create_task(project_id):
        values = validate(payload(TASK_FIELDS), TASK_FIELDS, True)
        check_dates(values, 'end_date')
        conn = connection()
        with db.transaction(conn):
            project_access(project_id, 'tasks.create')
            values.update(project_id=project_id, created_at=db.now(), updated_at=db.now())
            keys = list(values)
            task_id = conn.execute('INSERT INTO tasks (' + ','.join(keys) + ') VALUES (' + ','.join('?' for _ in keys) + ')',
                                   list(values.values())).lastrowid
            record = dict(conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone())
            db.audit(conn, g.user['id'], 'task.created', 'tasks', task_id, after=record)
        return jsonify(task=record), 201

    @app.patch(prefix + '/workspace/tasks/<int:task_id>')
    @authenticated()
    def update_task(task_id):
        values = validate(payload(TASK_FIELDS), TASK_FIELDS)
        conn = connection()
        with db.transaction(conn):
            row = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if not row:
                raise Error('Task not found', 404)
            project_access(row['project_id'], 'tasks.edit')
            before = dict(row)
            check_dates({**before, **values}, 'end_date')
            values['updated_at'] = db.now()
            conn.execute('UPDATE tasks SET ' + ','.join(k + '=?' for k in values) + ' WHERE id=?', [*values.values(), task_id])
            after = dict(conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone())
            db.audit(conn, g.user['id'], 'task.updated', 'tasks', task_id, before, after)
        return jsonify(task=after)
