// The OBJ writer (obj-export.js): the text it writes, read back; the files
// an export plans; texture coordinates in the raster. Run by
// tests/test_curve_math.py.
import { describe, it, expect, report } from './harness.mjs';
import { buildMtl, buildObj, objName, planFiles, rasterUv, rotateInRaster } from '../../src/static/js/obj-export.js';

// A small OBJ reader: vertices, texture coordinates, normals, and the
// faces of each object with their material.
function readObj(text) {
    const out = { v: [], vt: [], vn: [], objects: [], mtllib: null, comments: [] };
    let cur = null, mat = null;
    for (const raw of text.split('\n')) {
        const line = raw.trim();
        if (!line) continue;
        if (line.startsWith('#')) { out.comments.push(line); continue; }
        const [tag, ...rest] = line.split(/\s+/);
        if (tag === 'v') out.v.push(rest.map(Number));
        else if (tag === 'vt') out.vt.push(rest.map(Number));
        else if (tag === 'vn') out.vn.push(rest.map(Number));
        else if (tag === 'mtllib') out.mtllib = rest.join(' ');
        else if (tag === 'o') { cur = { name: rest.join(' '), faces: [], material: null }; out.objects.push(cur); }
        else if (tag === 'usemtl') { mat = rest.join(' '); if (cur) cur.material = mat; }
        else if (tag === 'f') cur.faces.push(rest.map(t => t.split('/').map(Number)));
    }
    return out;
}

const square = (x0, x1, uv0, uv1) => ({
    corners: [[x0, 0, 0], [x1, 0, 0], [x1, 0.5, 0], [x0, 0.5, 0]],
    uv: [[uv0, 0.5], [uv1, 0.5], [uv1, 1], [uv0, 1]],
});

describe('buildObj', () => {
    const text = buildObj({
        name: 'CENTER', kind: 'group', mtl: 'Show_CENTER.mtl',
        members: [
            { name: 'WALL L', material: 'Canvas 1', faces: [square(0, 0.5, 0, 0.25), square(0.5, 1, 0.25, 0.5)] },
            { name: 'WALL R', material: 'Canvas 1', faces: [square(1, 1.5, 0.5, 0.75)] },
        ],
    });
    const obj = readObj(text);
    it('says its units in the header', () => {
        expect(obj.comments.join(' ')).toContain('Units: meters');
        expect(obj.comments.join(' ')).toContain('Group: CENTER, 2 screens, 3 faces.');
    });
    it('names its .mtl and one object per member, each on its material', () => {
        expect(obj.mtllib).toBe('Show_CENTER.mtl');
        expect(obj.objects.map(o => o.name)).toEqual(['WALL_L', 'WALL_R']);
        expect(obj.objects.map(o => o.material)).toEqual(['Canvas_1', 'Canvas_1']);
    });
    it('writes four corners, four texture points and a normal per face', () => {
        expect(obj.v).toHaveLength(12);
        expect(obj.vt).toHaveLength(12);
        expect(obj.vn).toHaveLength(3);
        expect(obj.objects[0].faces).toHaveLength(2);
        expect(obj.objects[1].faces[0]).toEqual([[9, 9, 3], [10, 10, 3], [11, 11, 3], [12, 12, 3]]);
    });
    it('winds each face toward the audience (+Z)', () => {
        expect(obj.vn[0]).toEqual([0, 0, 1]);
    });
    it('writes no minus zero and no long tails', () => {
        expect(text.includes('-0 ')).toBe(false);
        const t = buildObj({ name: 'A', members: [{ name: 'A', faces: [{ corners: [[1 / 3, -0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], uv: [[0, 0], [1, 0], [1, 1], [0, 1]] }] }] });
        expect(t).toContain('v 0.333333 0 0');
    });
});

describe('buildMtl', () => {
    it('one unlit material per canvas, its Pixel Map as the image', () => {
        const t = buildMtl([{ name: 'Canvas 1', image: 'Show_Canvas_1_Pixel_Map.png' }]);
        expect(t).toContain('newmtl Canvas_1');
        expect(t).toContain('map_Kd Show_Canvas_1_Pixel_Map.png');
        expect(t).toContain('illum 1');
    });
});

describe('planFiles', () => {
    const canvases = new Map([['c1', 'Canvas 1'], ['c2', 'Side'], ['c3', 'Canvas 1']]);
    it('one OBJ and MTL per unit, one PNG per canvas used', () => {
        const plan = planFiles('My Show', [
            { name: 'CENTER', members: [{ canvasId: 'c1' }, { canvasId: 'c1' }] },
            { name: 'SL', members: [{ canvasId: 'c2' }] },
        ], canvases);
        expect(plan.units.map(u => [u.obj, u.mtl])).toEqual([
            ['My_Show_CENTER.obj', 'My_Show_CENTER.mtl'], ['My_Show_SL.obj', 'My_Show_SL.mtl']]);
        expect(plan.pngs.map(p => p.file)).toEqual(['My_Show_Canvas_1_Pixel_Map.png', 'My_Show_Side_Pixel_Map.png']);
        expect(plan.units[0].materials).toEqual([{ name: 'Canvas_1', image: 'My_Show_Canvas_1_Pixel_Map.png' }]);
    });
    it('a group across two canvases: one material and one PNG for each', () => {
        const plan = planFiles('S', [{ name: 'G', members: [{ canvasId: 'c1' }, { canvasId: 'c2' }] }], canvases);
        expect(plan.units[0].materials.map(m => m.name)).toEqual(['Canvas_1', 'Side']);
        expect(plan.units[0].unit.members.map(m => m.material)).toEqual(['Canvas_1', 'Side']);
    });
    it('two canvases with one name, and two screens with one name, stay apart', () => {
        const plan = planFiles('S', [{ name: 'A', members: [{ canvasId: 'c1' }] }, { name: 'A', members: [{ canvasId: 'c3' }] }], canvases);
        expect(plan.units.map(u => u.obj)).toEqual(['S_A.obj', 'S_A_2.obj']);
        expect(plan.pngs.map(p => p.material)).toEqual(['Canvas_1', 'Canvas_1_2']);
    });
});

describe('texture coordinates', () => {
    it('u across the raster, v up from its bottom edge', () => {
        expect(rasterUv(0, 0, 1920, 1080)).toEqual([0, 1]);
        expect(rasterUv(1920, 1080, 1920, 1080)).toEqual([1, 0]);
        expect(rasterUv(480, 270, 1920, 1080)).toEqual([0.25, 0.75]);
    });
    it('a screen turned on the raster turns its corners about its center', () => {
        const b = { x: 100, y: 100, width: 400, height: 200 };
        expect(rotateInRaster(100, 100, b, 0)).toEqual([100, 100]);
        // a quarter turn clockwise: the top-left corner goes to the top-right
        expect(rotateInRaster(100, 100, b, 90)).toEqual([400, 0]);
        expect(rotateInRaster(100, 100, b, 180)).toEqual([500, 300]);
        expect(rotateInRaster(100, 100, b, 270)).toEqual([200, 400]);
    });
    it('names are file safe', () => {
        expect(objName('Main Wall / Left')).toBe('Main_Wall___Left');
        expect(objName('  ')).toBe('Screen');
    });
});

report();
