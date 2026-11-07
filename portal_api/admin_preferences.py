"""Account-specific admin display preferences, shared across browser sessions."""
from flask import g, jsonify, request
from . import db


def register_admin_preferences(app, conn, login_required):
    with app.app_context():
        with db.transaction(conn()):
            conn().execute('''CREATE TABLE IF NOT EXISTS admin_preferences (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                browser_width INTEGER NOT NULL DEFAULT 0 CHECK(browser_width IN (0,1)))''')

    @app.get('/bms_integration_hub/api/admin/preferences')
    @login_required()
    def get_admin_preferences():
        row = conn().execute('SELECT browser_width FROM admin_preferences WHERE user_id=?', (g.user['id'],)).fetchone()
        return jsonify(browser_width=bool(row['browser_width']) if row else False)

    @app.put('/bms_integration_hub/api/admin/preferences')
    @login_required()
    def save_admin_preferences():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or set(data) != {'browser_width'} or type(data['browser_width']) is not bool:
            return jsonify(error='Choose a valid browser width preference'), 400
        with db.transaction(conn()):
            conn().execute('''INSERT INTO admin_preferences(user_id,browser_width) VALUES(?,?)
                ON CONFLICT(user_id) DO UPDATE SET browser_width=excluded.browser_width''',
                (g.user['id'], int(data['browser_width'])))
        return jsonify(browser_width=data['browser_width'])
