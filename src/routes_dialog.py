"""
Native OS file-dialog + disk-write routes.

Self-contained except for log_event (imported from app). Lets the browser GUI
trigger a real OS save/pick dialog and stream export blobs straight to disk,
bypassing the browser download flow.
"""
import os
import platform
import subprocess
import base64

from flask import Blueprint, request, jsonify

from app import log_event

dialog_bp = Blueprint('dialog', __name__)

# These endpoints open dialogs on, and write files to, the HOST machine.
# They exist for the GUI running on the host itself; a remote client's saves
# belong on the remote machine (the client falls back to browser downloads).
# Enforce that server-side too: anything not from loopback gets a 403 — an
# unauthenticated LAN peer must not be able to write arbitrary host files.
_LOOPBACK = ('127.0.0.1', '::1')


@dialog_bp.before_request
def _local_only():
    addr = request.remote_addr or ''
    if addr not in _LOOPBACK:
        log_event('native_dialog_rejected_remote', {
            'remote_addr': addr, 'path': request.path})
        return jsonify({'ok': False,
                        'error': 'Native dialogs are only available on the host machine.'}), 403


def decode_base64_bytes(data_url):
    if ',' in data_url:
        data_url = data_url.split(',', 1)[1]
    return base64.b64decode(data_url)


def _run_dialog_command(cmd, what='dialog'):
    """Run an OS dialog helper. Returns (path_or_None, status).

    status is 'ok', 'cancelled' (the user dismissed it) or 'unavailable' (the
    dialog could not be opened at all). The caller MUST tell those apart: a
    cancel means "do nothing", while unavailable means "fall back to a browser
    download". Conflating them is why cancelling an export still dropped the
    files into Downloads.

    Failures are LOGGED, not swallowed. This used to return a bare None on any
    non-zero exit, so when the Windows dialog failed to open the export fell
    silently through to a browser download and the only symptom was "the files
    went to Downloads" with nothing anywhere saying why.
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        # The helper itself is missing - powershell/osascript/zenity not on PATH.
        log_event('native_dialog_helper_missing', {'what': what, 'cmd': cmd[0]})
        return None, 'unavailable'
    except Exception as exc:
        log_event('native_dialog_command_error', {
            'what': what, 'cmd': cmd[0], 'error': str(exc)})
        return None, 'unavailable'
    if result.returncode != 0:
        log_event('native_dialog_command_failed', {
            'what': what,
            'cmd': cmd[0],
            'returncode': result.returncode,
            # Trimmed: a PowerShell stack trace is long and the first lines
            # carry the reason.
            'stderr': (result.stderr or '').strip()[:600],
        })
        return None, 'unavailable'
    value = (result.stdout or '').strip()
    if not value:
        # Exit 0 with no path is a genuine user cancel, not a fault.
        log_event('native_dialog_cancelled', {'what': what})
        return None, 'cancelled'
    return value, 'ok'


# Windows: WinForms dialogs must run in a single-threaded apartment, and with
# no owner window they can open BEHIND the browser where the user never sees
# them - which reads as "the dialog never appeared" and ends in a silent
# fallback to Downloads. So: force -STA, and hand ShowDialog a TopMost owner
# so the dialog is guaranteed to come to the front.
_WIN_PS = ['powershell', '-NoProfile', '-STA', '-Command']

_WIN_OWNER_PREAMBLE = (
    'Add-Type -AssemblyName System.Windows.Forms;'
    'Add-Type -AssemblyName System.Drawing;'
    '$owner=New-Object System.Windows.Forms.Form;'
    '$owner.TopMost=$true;'
    '$owner.ShowInTaskbar=$false;'
    '$owner.StartPosition="CenterScreen";'
    '$owner.Size=New-Object System.Drawing.Size(1,1);'
    '$owner.Opacity=0;'
    '$owner.Show();'
    '$owner.Activate();'
)


def _ps_quote(value):
    """Quote a value for a PowerShell double-quoted string.

    A project called Wall "A" or a path with a $ in it would otherwise break
    the script, or - worse - be interpreted. Backtick is PowerShell's escape.
    """
    return (str(value)
            .replace('`', '``')
            .replace('"', '`"')
            .replace('$', '`$'))


def _native_choose_save_file(suggested_name):
    system = platform.system()
    if system == 'Darwin':
        script = f'POSIX path of (choose file name with prompt "Save File" default name "{suggested_name}")'
        return _run_dialog_command(['osascript', '-e', script], 'save_file')
    if system == 'Windows':
        script = (
            _WIN_OWNER_PREAMBLE
            + '$d=New-Object System.Windows.Forms.SaveFileDialog;'
            + f'$d.FileName="{_ps_quote(suggested_name)}";'
            + 'try{if($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK)'
              '{Write-Output $d.FileName}}finally{$owner.Close()}'
        )
        return _run_dialog_command(_WIN_PS + [script], 'save_file')
    # Linux fallback (if zenity is installed)
    return _run_dialog_command(
        ['zenity', '--file-selection', '--save', '--confirm-overwrite',
         f'--filename={suggested_name}'], 'save_file')


def _native_choose_directory():
    system = platform.system()
    if system == 'Darwin':
        script = 'POSIX path of (choose folder with prompt "Select Export Folder")'
        return _run_dialog_command(['osascript', '-e', script], 'choose_directory')
    if system == 'Windows':
        # FolderBrowserDialog is the tree-view picker; on Vista+ setting
        # UseDescriptionForTitle gives it a real title bar instead of the
        # legacy description label.
        script = (
            _WIN_OWNER_PREAMBLE
            + '$d=New-Object System.Windows.Forms.FolderBrowserDialog;'
              '$d.Description="Select Export Folder";'
              '$d.UseDescriptionForTitle=$true;'
              'try{if($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK)'
              '{Write-Output $d.SelectedPath}}finally{$owner.Close()}'
        )
        return _run_dialog_command(_WIN_PS + [script], 'choose_directory')
    return _run_dialog_command(
        ['zenity', '--file-selection', '--directory'], 'choose_directory')


@dialog_bp.route('/api/native-dialog/save-file', methods=['POST'])
def native_dialog_save_file():
    data = request.get_json() or {}
    suggested_name = data.get('suggested_name', 'output.bin')
    try:
        log_event('native_dialog_save_file_start', {'suggested_name': suggested_name})
        file_path, status = _native_choose_save_file(suggested_name)
        if not file_path:
            # 'cancelled' means the user said no and NOTHING should be saved.
            # 'unavailable' means the dialog never opened, and the caller should
            # fall back to a browser download rather than lose the export.
            log_event('native_dialog_save_file_no_path',
                      {'suggested_name': suggested_name, 'status': status})
            return jsonify({'ok': False,
                            'cancelled': status == 'cancelled',
                            'unavailable': status == 'unavailable'})
        log_event('native_dialog_save_file', {'path': file_path})
        return jsonify({'ok': True, 'path': file_path})
    except Exception as e:
        log_event('native_dialog_save_file_error', {'error': str(e)})
        return jsonify({'ok': False, 'error': str(e)}), 500


@dialog_bp.route('/api/native-dialog/select-directory', methods=['POST'])
def native_dialog_select_directory():
    try:
        log_event('native_dialog_select_directory_start', {})
        directory, status = _native_choose_directory()
        if not directory:
            log_event('native_dialog_select_directory_no_path', {'status': status})
            return jsonify({'ok': False,
                            'cancelled': status == 'cancelled',
                            'unavailable': status == 'unavailable'})
        log_event('native_dialog_select_directory', {'directory': directory})
        return jsonify({'ok': True, 'path': directory})
    except Exception as e:
        log_event('native_dialog_select_directory_error', {'error': str(e)})
        return jsonify({'ok': False, 'error': str(e)}), 500


@dialog_bp.route('/api/native-dialog/write-file', methods=['POST'])
def native_dialog_write_file():
    """Write blob bytes to a chosen path on disk.

    Accepts EITHER:
      - JSON body with {path, data_url} where data_url is a base64 data URI
        (legacy v0.8.6 path; works for small blobs but blows up JSON.stringify
        on the client when the blob exceeds ~25 MB).
      - multipart/form-data with `path` field and `file` field (v0.8.7+).
        This skips the JSON string allocation and is the only path large PSD
        exports survive, the client streams the raw blob to the server.
    """
    file_path = None
    content = None
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        file_path = request.form.get('path')
        f = request.files.get('file')
        if f is not None:
            content = f.read()
    else:
        data = request.get_json(silent=True) or {}
        file_path = data.get('path')
        data_url = data.get('data_url')
        if data_url:
            try:
                content = decode_base64_bytes(data_url)
            except Exception as e:
                log_event('native_dialog_write_file_decode_error', {'error': str(e)})
                content = None
    if not file_path or content is None:
        log_event('native_dialog_write_file_invalid', {'has_path': bool(file_path), 'has_data': content is not None})
        return jsonify({'ok': False, 'error': 'path and file/data_url are required'}), 400
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'wb') as f:
            f.write(content)
        exists = os.path.exists(file_path)
        size = os.path.getsize(file_path) if exists else 0
        log_event('native_dialog_write_file', {'path': file_path, 'bytes': len(content), 'exists': exists, 'size': size})
        return jsonify({'ok': True})
    except Exception as e:
        log_event('native_dialog_write_file_error', {'path': file_path, 'error': str(e)})
        return jsonify({'ok': False, 'error': str(e)}), 500


@dialog_bp.route('/api/native-dialog/write-multiple', methods=['POST'])
def native_dialog_write_multiple():
    data = request.get_json() or {}
    directory = data.get('directory')
    files = data.get('files', [])
    if not directory or not isinstance(files, list):
        return jsonify({'ok': False, 'error': 'directory and files are required'}), 400
    try:
        os.makedirs(directory, exist_ok=True)
        written = 0
        for item in files:
            filename = item.get('filename')
            data_url = item.get('data_url')
            if not filename or not data_url:
                continue
            safe_name = os.path.basename(filename)
            file_path = os.path.join(directory, safe_name)
            content = decode_base64_bytes(data_url)
            with open(file_path, 'wb') as f:
                f.write(content)
            written += 1
        log_event('native_dialog_write_multiple', {'directory': directory, 'requested': len(files), 'written': written})
        return jsonify({'ok': True, 'written': written})
    except Exception as e:
        log_event('native_dialog_write_multiple_error', {'directory': directory, 'error': str(e)})
        return jsonify({'ok': False, 'error': str(e)}), 500
