// A small describe / it / expect for the plain-JS math modules, so their
// tests run under node with nothing installed. tests/test_curve_math.py runs
// each *.test.mjs file here and reads the JSON line `report()` prints.
//
// Only what the tests use: toBe, toEqual (deep, Sets and Maps too),
// toBeCloseTo (the usual "digits" meaning: |a - b| < 10^-digits / 2),
// toContain, toMatch, toHaveLength, the four comparisons, toBeDefined,
// and .not for each.

const results = [];
const stack = [];

export function describe(name, fn) {
    stack.push(name);
    try {
        fn();
    } catch (err) {
        // A describe body that throws is a failure of everything in it.
        results.push({ name: stack.join(' > '), ok: false, error: `describe threw: ${err && err.stack || err}` });
    }
    stack.pop();
}

export function it(name, fn) {
    const full = [...stack, name].join(' > ');
    try {
        fn();
        results.push({ name: full, ok: true });
    } catch (err) {
        results.push({ name: full, ok: false, error: String(err && err.message || err) });
    }
}

export const test = it;

function show(v) {
    try {
        return JSON.stringify(v, (k, x) => (x instanceof Set ? [...x] : x instanceof Map ? [...x] : (typeof x === 'number' && !Number.isFinite(x) ? String(x) : x)));
    } catch (_) {
        return String(v);
    }
}

function deepEqual(a, b) {
    if (Object.is(a, b)) return true;
    if (typeof a === 'number' && typeof b === 'number') return a === b;
    if (a instanceof Set || b instanceof Set) {
        if (!(a instanceof Set && b instanceof Set) || a.size !== b.size) return false;
        for (const x of a) if (![...b].some(y => deepEqual(x, y))) return false;
        return true;
    }
    if (a instanceof Map || b instanceof Map) {
        if (!(a instanceof Map && b instanceof Map) || a.size !== b.size) return false;
        for (const [k, v] of a) if (!b.has(k) || !deepEqual(v, b.get(k))) return false;
        return true;
    }
    if (Array.isArray(a) || Array.isArray(b)) {
        if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
        return a.every((x, i) => deepEqual(x, b[i]));
    }
    if (a && b && typeof a === 'object' && typeof b === 'object') {
        const ka = Object.keys(a).filter(k => a[k] !== undefined);
        const kb = Object.keys(b).filter(k => b[k] !== undefined);
        if (ka.length !== kb.length) return false;
        return ka.every(k => deepEqual(a[k], b[k]));
    }
    return false;
}

function matchers(actual, negate) {
    const check = (pass, what) => {
        if (pass === negate) throw new Error(`expected ${show(actual)} ${negate ? 'not ' : ''}${what}`);
    };
    return {
        toBe: (v) => check(Object.is(actual, v), `to be ${show(v)}`),
        toEqual: (v) => check(deepEqual(actual, v), `to equal ${show(v)}`),
        toBeCloseTo: (v, digits = 2) => {
            const pass = (actual === Infinity && v === Infinity) || (actual === -Infinity && v === -Infinity)
                || Math.abs(actual - v) < Math.pow(10, -digits) / 2;
            check(pass, `to be close to ${show(v)} (${digits} digits)`);
        },
        toContain: (v) => check(actual != null && actual.includes(v), `to contain ${show(v)}`),
        toMatch: (re) => check(typeof actual === 'string' && (re instanceof RegExp ? re.test(actual) : actual.includes(re)), `to match ${re}`),
        toHaveLength: (n) => check(actual != null && actual.length === n, `to have length ${n}`),
        toBeGreaterThan: (v) => check(actual > v, `to be greater than ${show(v)}`),
        toBeGreaterThanOrEqual: (v) => check(actual >= v, `to be at least ${show(v)}`),
        toBeLessThan: (v) => check(actual < v, `to be less than ${show(v)}`),
        toBeLessThanOrEqual: (v) => check(actual <= v, `to be at most ${show(v)}`),
        toBeDefined: () => check(actual !== undefined, 'to be defined'),
    };
}

export function expect(actual) {
    const m = matchers(actual, false);
    m.not = matchers(actual, true);
    return m;
}

// One JSON line on stdout: { passed, failed: [{ name, error }] }.
export function report() {
    const failed = results.filter(r => !r.ok);
    console.log(JSON.stringify({ passed: results.length - failed.length, total: results.length, failed }));
}
