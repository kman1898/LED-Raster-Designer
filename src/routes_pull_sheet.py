"""
Pull-sheet export route: the client's pull list in, a filled copy of the
user's pull-sheet workbook out.

The list itself is built on the client (app-pull-list.js buildPullList -
the one authority, shared with the binder packet); this route only lays it
into the template (pull_sheet.build_workbook) and streams the xlsx back the
way /api/export/pdf-from-images streams a PDF, so the client saves it
through saveBlobWithPicker like every other export. Warnings that do not
stop the export (a seventh position, a sixty-first row) ride back in the
X-Pull-Sheet-Warnings header as JSON. GET /api/pull-sheet/gear-list serves
the template's vocabulary to the in-app editor's pickers.
"""
import io
import json

from flask import Blueprint, request, jsonify, send_file

import pull_sheet
from app import log_event

pull_sheet_bp = Blueprint('pull_sheet', __name__)


@pull_sheet_bp.route('/api/pull-sheet/gear-list', methods=['GET'])
def pull_sheet_gear_list():
    """The template's GEAR LIST vocabulary - the in-app editor's type and
    length pickers read it, so what the editor offers is what the workbook's
    dropdowns accept (a typed value outside it is warned about, never
    blocked, and the export appends it to the GEAR LIST)."""
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        return jsonify({'types': [], 'lengths': []})
    try:
        return jsonify(pull_sheet.gear_list())
    except FileNotFoundError:
        return jsonify({'error': 'The pull-sheet template is missing from this install'}), 500


@pull_sheet_bp.route('/api/export/pull-sheet', methods=['POST'])
def export_pull_sheet():
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        return jsonify({'error': 'Pull sheet export requires the openpyxl library'}), 500
    data = request.get_json(silent=True) or {}
    pull_list = data.get('pull_list')
    if not isinstance(pull_list, dict):
        return jsonify({'error': 'pull_list must be an object'}), 400
    project_name = str(data.get('project_name') or 'Project').strip() or 'Project'
    meta = {
        'project_name': project_name,
        'engineer': data.get('engineer') or '',
        'rev': data.get('rev'),
        'date': data.get('date') or '',
        'date_iso': data.get('date_iso') or '',
    }
    try:
        xlsx, warnings = pull_sheet.build_workbook(pull_list, meta)
    except FileNotFoundError:
        return jsonify({'error': 'The pull-sheet template is missing from this install'}), 500
    log_event('export_pull_sheet', {
        'name': project_name,
        'positions': len(pull_list.get('positions') or []),
        'warnings': warnings,
    })
    resp = send_file(
        io.BytesIO(xlsx),
        mimetype=pull_sheet.XLSX_MIME,
        as_attachment=True,
        download_name=f'{pull_sheet.safe_filename(project_name)}-pull-sheet.xlsx',
    )
    resp.headers['X-Pull-Sheet-Warnings'] = json.dumps(warnings, ensure_ascii=True)
    return resp
