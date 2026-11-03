"""Answering the app's own question dialog (src/static/js/app-dialogs.js)
from a Playwright test.

Since 1.6.0 (QA round 3) the app asks nothing through the browser's
alert(), confirm() or prompt(): a test that used to answer
``page.once('dialog', ...)`` before the gesture now makes the gesture and
then answers the dialog that opens (answer_app_dialog), or has every
question answered by a callback for the whole page (auto_answer_app_dialogs).
"""

DIALOG = '.app-ask-modal'


def answer_app_dialog(pg, accept=True, text=None, timeout=5000):
    """Wait for the app's question, type `text` into it when given (a
    prompt), then press its primary button (accept) or Esc (cancel). Returns
    the question's text."""
    pg.wait_for_selector(DIALOG, state='visible', timeout=timeout)
    modal = pg.locator(DIALOG).last
    message = modal.locator('.app-ask-text').text_content()
    if text is not None:
        modal.locator('.app-ask-input').fill(text)
    before = pg.locator(DIALOG).count()
    if accept:
        modal.locator('.app-ask-buttons .btn-primary').click()
    else:
        pg.keyboard.press('Escape')
    pg.wait_for_function("(n) => document.querySelectorAll('.app-ask-modal').length < n",
                         arg=before, timeout=timeout)
    return message


# Every question the page asks goes to the test's `handler(message)`; its
# answer (True / False, or (True, text) for a prompt) presses the button.
_AUTO_JS = r"""
(() => {
  if (window.__lrdAutoAnswer) return;
  window.__lrdAutoAnswer = true;
  const seen = new WeakSet();
  const answer = async (modal) => {
    if (seen.has(modal)) return;
    seen.add(modal);
    const text = (modal.querySelector('.app-ask-text') || {}).textContent || '';
    const got = await window.__lrdAnswerAppDialog(text);
    if (!modal.isConnected) return;
    const [yes, typed] = Array.isArray(got) ? got : [got, null];
    const input = modal.querySelector('.app-ask-input');
    if (input && typed != null) input.value = typed;
    if (yes) modal.querySelector('.app-ask-buttons .btn-primary').click();
    else window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  };
  const scan = () => document.querySelectorAll('.app-ask-modal').forEach(answer);
  const start = () => new MutationObserver(scan).observe(document.body, { childList: true });
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);
})();
"""


def auto_answer_app_dialogs(pg, handler):
    """Answer every app question on `pg` (before it navigates) with
    `handler(message)`."""
    pg.expose_function('__lrdAnswerAppDialog', handler)
    pg.add_init_script(_AUTO_JS)
