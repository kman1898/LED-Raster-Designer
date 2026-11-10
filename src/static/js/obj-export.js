// obj-export: the OBJ writer behind Export > OBJ. Plain functions, no DOM:
// tests/test_curve_math.py runs it under node (tests/js/obj_export.test.mjs),
// and the app (app-obj-export.js) hands it the screens' faces already placed
// on the stage.
//
// One OBJ per physical screen: an ungrouped screen, or a group (one object
// per member inside it, each named after its screen). Every face is one
// flat piece of LED as the 3D stage builds it: a cabinet, or the half of
// one a mid-panel fold splits, so faces split at every bend. Each corner
// carries its texture coordinate: where that point of the wall sits in its
// canvas raster (u across, v up from the raster's bottom edge), so content
// mapped by the same raster lands on the right cabinets. Each canvas is
// one material whose image is that canvas's Pixel Map PNG.
//
// Units: meters, +Y up, +Z toward the audience, X to the right, the same
// stage the 3D tab shows (which works in mm). The header says so.

const fmt = (v) => {
    const r = Math.round(v * 1e6) / 1e6;
    return Object.is(r, -0) ? '0' : String(r);
};

// A name as it can sit after `o`, `usemtl` or in a file name: no spaces,
// no characters a file system or a parser trips on.
export function objName(name, fallback = 'Screen') {
    const clean = String(name == null ? '' : name).trim()
        .replace(/[\\/:*?"<>|#\x00-\x1F]/g, '_').replace(/\s+/g, '_');
    return clean || fallback;
}

function normal(a, b, c) {
    const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    const w = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    const n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]];
    const l = Math.hypot(n[0], n[1], n[2]) || 1;
    return [n[0] / l, n[1] / l, n[2] / l];
}

/**
 * One OBJ file's text.
 * unit: { name, kind: 'screen' | 'group', mtl: 'file.mtl',
 *         members: [{ name, material, faces: [{ corners: [[x,y,z] x4], uv: [[u,v] x4] }] }] }
 * Corners are meters on the stage, in the order bottom-left, bottom-right,
 * top-right, top-left as seen from the front, so each face winds
 * counter-clockwise toward the audience.
 */
export function buildObj(unit, opts = {}) {
    const lines = [];
    const members = unit.members || [];
    const faces = members.reduce((t, m) => t + (m.faces || []).length, 0);
    lines.push(`# ${opts.app || 'LED Raster Designer'} OBJ export`);
    lines.push('# Units: meters. +Y is up, +Z is toward the audience, X runs to the right.');
    lines.push(`# ${unit.kind === 'group' ? 'Group' : 'Screen'}: ${unit.name}, ${members.length} screen${members.length === 1 ? '' : 's'}, ${faces} face${faces === 1 ? '' : 's'}.`);
    lines.push('# Each face is one flat piece of LED, split at every bend. Texture coordinates');
    lines.push('# place every corner where it sits in its canvas raster (u across, v up).');
    if (unit.mtl) lines.push(`mtllib ${unit.mtl}`);
    let v = 0, vt = 0, vn = 0;
    for (const m of members) {
        lines.push(`o ${objName(m.name)}`);
        if (m.material) lines.push(`usemtl ${objName(m.material, 'Canvas')}`);
        for (const f of m.faces || []) {
            const c = f.corners;
            for (const p of c) lines.push(`v ${fmt(p[0])} ${fmt(p[1])} ${fmt(p[2])}`);
            for (const t of f.uv) lines.push(`vt ${fmt(t[0])} ${fmt(t[1])}`);
            const n = normal(c[0], c[1], c[2]);
            lines.push(`vn ${fmt(n[0])} ${fmt(n[1])} ${fmt(n[2])}`);
            vn += 1;
            const idx = [0, 1, 2, 3].map(k => `${v + k + 1}/${vt + k + 1}/${vn}`);
            lines.push(`f ${idx.join(' ')}`);
            v += 4;
            vt += 4;
        }
    }
    return lines.join('\n') + '\n';
}

/** A .mtl with one unlit material per canvas: [{ name, image }]. */
export function buildMtl(materials, opts = {}) {
    const lines = [`# ${opts.app || 'LED Raster Designer'} materials: one per canvas, its Pixel Map as the image.`];
    for (const m of materials) {
        lines.push('');
        lines.push(`newmtl ${objName(m.name, 'Canvas')}`);
        lines.push('Ka 1 1 1');
        lines.push('Kd 1 1 1');
        lines.push('Ks 0 0 0');
        lines.push('d 1');
        lines.push('illum 1');
        if (m.image) lines.push(`map_Kd ${m.image}`);
    }
    return lines.join('\n') + '\n';
}

/**
 * Texture coordinates for a point in a canvas raster, in pixels from its
 * top-left: u across, v up from the bottom edge.
 */
export function rasterUv(x, y, rasterW, rasterH) {
    const w = rasterW > 0 ? rasterW : 1;
    const h = rasterH > 0 ? rasterH : 1;
    return [x / w, 1 - y / h];
}

/**
 * Where a point of a screen's own unrotated pixels lands in its canvas once
 * the screen's rotation is applied (turned about its own center, the way
 * the Pixel Map draws it: 90 is a quarter turn clockwise on the raster).
 */
export function rotateInRaster(x, y, bounds, deg) {
    const d = (((Number(deg) || 0) % 360) + 360) % 360;
    if (d !== 90 && d !== 180 && d !== 270) return [x, y];
    const cx = bounds.x + bounds.width / 2, cy = bounds.y + bounds.height / 2;
    const a = d * Math.PI / 180;
    const c = Math.round(Math.cos(a)), s = Math.round(Math.sin(a));
    const dx = x - cx, dy = y - cy;
    return [cx + dx * c - dy * s, cy + dx * s + dy * c];
}

/**
 * Which files an export writes: one OBJ and one MTL per unit, and one PNG
 * per canvas any of them uses, its material named after the canvas.
 * units: [{ name, members: [{ canvasId }] }]; canvases: Map id -> name.
 * Returns { units: [{ unit, obj, mtl, materials: [{ name, image }] }],
 * pngs: [{ canvasId, material, file }] } and sets each member's material.
 */
export function planFiles(project, units, canvases) {
    const base = objName(project, 'Project');
    const pngs = new Map();
    const names = new Set();
    for (const unit of units) {
        for (const m of unit.members || []) {
            if (pngs.has(m.canvasId)) continue;
            const stem = objName(canvases.get(m.canvasId) || 'Canvas', 'Canvas');
            let material = stem;
            for (let k = 2; names.has(material.toLowerCase()); k++) material = `${stem}_${k}`;
            names.add(material.toLowerCase());
            pngs.set(m.canvasId, { canvasId: m.canvasId, material, file: `${base}_${material}_Pixel_Map.png` });
        }
    }
    const taken = new Set();
    const out = units.map(unit => {
        let stem = `${base}_${objName(unit.name)}`;
        for (let k = 2; taken.has(stem.toLowerCase()); k++) stem = `${base}_${objName(unit.name)}_${k}`;
        taken.add(stem.toLowerCase());
        const materials = [];
        for (const m of unit.members || []) {
            const png = pngs.get(m.canvasId);
            m.material = png.material;
            if (!materials.some(x => x.name === png.material)) materials.push({ name: png.material, image: png.file });
        }
        return { unit, obj: `${stem}.obj`, mtl: `${stem}.mtl`, materials };
    });
    return { units: out, pngs: [...pngs.values()] };
}
