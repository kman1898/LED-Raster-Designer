// app-obj-export: Export > OBJ. The screens on the 3D stage as 3D models in
// real size, bent and curved as the stage builds them, with texture
// coordinates placing every cabinet where it sits in its canvas raster, so
// content mapped by that raster lands right; a PNG of each canvas's Pixel
// Map for checking, and the .mtl that points at it. The OBJ text itself is
// obj-export.js; this gathers the faces and saves the files.
//
// ONE FILE PER PHYSICAL SCREEN (owner, 2026-11-09): an ungrouped screen is
// one OBJ; a group is one OBJ named after the group, a part per member
// named after the screen, unless the group is set to Screens, when each
// member is its own file. "Set to Screens" is the group's Names switch on
// the Show Look tab, the view of the stage as it stands (the 3D tab has
// no Names switch of its own); Group and Both are one physical screen. A
// group whose members sit on different canvases keeps each member on its
// own canvas: one material per canvas in the group's .mtl, one PNG each.
//
// The screens are the 3D stage's: Show Look's visible screens on a canvas
// that is not hidden. Meters, +Y up, +Z toward the audience. Saved straight
// to a folder like every multi-file export (saveMultipleFiles), nothing
// opened.
import { LEDRasterApp } from './app-core.js';
import { sendClientLog } from './helpers.js';
import { quatFromPlacement, quatRotate, s3dBuild } from './app-stage3d.js';
import { buildMtl, buildObj, planFiles, rasterUv, rotateInRaster } from './obj-export.js';

class _ObjExport {
    // The physical screens, in the Screens list's order:
    // [{ name, kind, group, layers }].
    objExportUnits() {
        const items = this._s3dLayout().items;
        const onStage = new Set(items.map(i => i.layer.id));
        const groups = (this.project && this.project.groups) || [];
        const units = [];
        const done = new Set();
        for (const { layer } of items) {
            if (done.has(layer.id)) continue;
            const group = layer.group_id != null ? groups.find(g => g && g.id === layer.group_id) : null;
            const asOne = group && this.groupNameDisplayFor('show-look', group) !== 'screens';
            if (asOne) {
                const ids = new Set(group.layer_ids || []);
                const members = items.map(i => i.layer).filter(l => ids.has(l.id) && onStage.has(l.id));
                members.forEach(l => done.add(l.id));
                units.push({ name: group.name || 'Group', kind: 'group', group, layers: members });
            } else {
                done.add(layer.id);
                units.push({ name: layer.name || `Screen ${layer.id}`, kind: 'screen', group: null, layers: [layer] });
            }
        }
        return units;
    }

    _objCanvasNames() {
        const map = new Map();
        for (const c of (this.project && this.project.canvases) || []) if (c && c.id) map.set(c.id, c.name || 'Canvas');
        return map;
    }

    // What the export writes, planned: obj-export.js planFiles over the units.
    objExportPlan(projectName) {
        const units = this.objExportUnits().map(u => ({
            ...u, members: u.layers.map(l => ({ layer: l, name: l.name || `Screen ${l.id}`, canvasId: l.canvas_id || null })),
        }));
        return planFiles(projectName, units, this._objCanvasNames());
    }

    // The file names, for the export dialog's preview.
    objExportFileNames(projectName) {
        const plan = this.objExportPlan(projectName);
        const out = [];
        plan.units.forEach(u => out.push(u.obj, u.mtl));
        plan.pngs.forEach(p => out.push(p.file));
        return out;
    }

    // One screen's faces on the stage, in meters: each cabinet (or each half
    // of a folded one) as the 3D stage builds it, carried by the screen's
    // place and turn, with its corners' spots in the canvas raster.
    objFacesOf(layer, raster) {
        const placement = this._s3dPlacementOf(layer);
        const built = s3dBuild(layer, placement);
        const q = quatFromPlacement(placement);
        const at = (p) => {
            const r = quatRotate(q, p);
            return [(r[0] + placement.x) / 1000, (r[1] + placement.y) / 1000, (r[2] + placement.z) / 1000];
        };
        const b = built.bounds;
        const bounds = { x: b.x, y: b.y, width: b.w, height: b.h };
        const uv = (x, y) => {
            const [rx, ry] = rotateInRaster(x, y, bounds, layer.rotation);
            return rasterUv(rx, ry, raster.w, raster.h);
        };
        return built.quads.map(qd => {
            const [x, y, w, h] = qd.px;
            return {
                corners: [at(qd.bl), at(qd.br), at(qd.tr), at(qd.tl)],
                uv: [uv(x, y + h), uv(x + w, y + h), uv(x + w, y), uv(x, y)],
            };
        });
    }

    _objRasterOf(canvasId) {
        const c = canvasId ? ((this.project && this.project.canvases) || []).find(x => x && x.id === canvasId) : null;
        const r = window.canvasRenderer;
        return {
            w: c ? (Number(c.raster_width) || 1920) : ((r && r.pixelRasterWidth) || 1920),
            h: c ? (Number(c.raster_height) || 1080) : ((r && r.pixelRasterHeight) || 1080),
        };
    }

    // The OBJ, MTL and PNG files as { filename, blob }, ready to save. The
    // PNGs are each canvas's Pixel Map, rendered as Export > PNG renders it.
    async objExportFiles(projectName) {
        const plan = this.objExportPlan(projectName);
        if (!plan.units.length) return { plan, files: [] };
        const files = [];
        for (const u of plan.units) {
            const unit = {
                name: u.unit.name, kind: u.unit.kind, mtl: u.mtl,
                members: u.unit.members.map(m => ({
                    name: m.name, material: m.material,
                    faces: this.objFacesOf(m.layer, this._objRasterOf(m.canvasId)),
                })),
            };
            files.push({ filename: u.obj, blob: new Blob([buildObj(unit)], { type: 'text/plain' }) });
            files.push({ filename: u.mtl, blob: new Blob([buildMtl(u.materials)], { type: 'text/plain' }) });
        }
        const canvasIds = plan.pngs.map(p => p.canvasId);
        const rendered = await this.performExport(projectName, 'obj', ['pixel-map'], canvasIds);
        plan.pngs.forEach((p, i) => {
            const item = (rendered || []).find(r => r.canvasId === p.canvasId) || (rendered || [])[i];
            if (item) files.push({ filename: p.file, blob: this.dataUrlToBlob(item.dataUrl) });
        });
        return { plan, files };
    }

    async exportObj(projectName) {
        const { plan, files } = await this.objExportFiles(projectName);
        if (!files.length) {
            throw new Error('No screens on the 3D stage to export. Show a screen in Show Look first.');
        }
        sendClientLog('export_obj', {
            units: plan.units.map(u => ({ obj: u.obj, members: u.unit.members.length })),
            pngs: plan.pngs.map(p => p.file),
        });
        await this.saveMultipleFiles(files);
    }
}

for (const k of Object.getOwnPropertyNames(_ObjExport.prototype)) {
    if (k !== 'constructor') {
        Object.defineProperty(LEDRasterApp.prototype, k,
            Object.getOwnPropertyDescriptor(_ObjExport.prototype, k));
    }
}
