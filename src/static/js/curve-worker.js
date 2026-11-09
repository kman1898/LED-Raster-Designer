// curve-worker: the Curve's calculator, off the page's thread. A module
// worker (app-curve.js starts it): each message is { id, input } for
// curve-math.js screenCurve, and the answer goes back as { id, out }, or
// { id, error } when the math threw. The page never waits on it: a wall of
// forty panels and four lit sizes takes a second or two to fit.
import { screenCurve } from './curve-math.js';

self.onmessage = (event) => {
    const { id, input } = event.data || {};
    try {
        self.postMessage({ id, out: screenCurve(input) });
    } catch (err) {
        self.postMessage({ id, error: String((err && err.message) || err) });
    }
};
