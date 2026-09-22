"""
Export routes: the raster renders (PNG, layered PSD, layer ZIP), the
client-rendered image exports (ZIP, PDF from images, PDF from binder page
display lists, PSD and PSD ZIP from images) and the Resolume Advanced
Output XML - every /api/export/* route and the render helpers only they
use.

The project is read as app.current_project at call time - never bound at
import - because conftest and the project routes REASSIGN that attribute
(see routes_preferences.py). The unit model and the XML geometry live in
resolume_geometry.py; this module only turns them into HTTP responses.
"""
import base64
import io
import json
import math

from flask import Blueprint, request, jsonify, send_file
from PIL import Image
import numpy as np

import app
from app import log_event
from resolume_geometry import _export_units, _export_unit_bounds, generate_resolume_xml

export_bp = Blueprint('export', __name__)


def _empty_psd_layer_mask(psd_layers):
    """Create a no-op layer mask that serializes as absent mask data."""
    class EmptyLayerMask(psd_layers.LayerMask):
        def length(self, header):
            return 0

        def total_length(self, header):
            return 4

        def write(self, fd, header):
            fd.write(b'\x00\x00\x00\x00')

    return EmptyLayerMask()


def render_layer_to_image(layer, raster_width, raster_height, include_borders=True):
    """Render a single layer to a PIL Image with transparency"""
    # Create RGBA image (transparent background)
    img = Image.new('RGBA', (raster_width, raster_height), (0, 0, 0, 0))
    pixels = img.load()
    
    # Get layer colors
    color1 = layer.get('color1', {'r': 64, 'g': 70, 'b': 128})
    color2 = layer.get('color2', {'r': 149, 'g': 156, 'b': 184})
    border_color_hex = layer.get('border_color', '#ffffff')
    
    # Parse border color
    border_color = (255, 255, 255)  # default white
    if border_color_hex.startswith('#') and len(border_color_hex) == 7:
        border_color = (
            int(border_color_hex[1:3], 16),
            int(border_color_hex[3:5], 16),
            int(border_color_hex[5:7], 16)
        )
    
    show_borders = layer.get('show_panel_borders', True) and include_borders
    
    # Render each panel
    for panel in layer['panels']:
        if panel.get('hidden', False):
            continue
            
        px = int(panel['x'])
        py = int(panel['y'])
        pw = int(panel['width'])
        ph = int(panel['height'])
        
        # Get panel color
        color = color1 if panel.get('is_color1', True) else color2
        rgb = (color['r'], color['g'], color['b'], 255)
        
        # Fill panel pixels
        for y in range(max(0, py), min(raster_height, py + ph)):
            for x in range(max(0, px), min(raster_width, px + pw)):
                pixels[x, y] = rgb
        
        # Draw borders (2 pixels wide, inside the panel)
        if show_borders:
            border_rgba = (border_color[0], border_color[1], border_color[2], 255)
            # Top and bottom borders (2 pixels each)
            for y in range(max(0, py), min(raster_height, py + 2)):
                for x in range(max(0, px), min(raster_width, px + pw)):
                    pixels[x, y] = border_rgba
            for y in range(max(0, py + ph - 2), min(raster_height, py + ph)):
                for x in range(max(0, px), min(raster_width, px + pw)):
                    pixels[x, y] = border_rgba
            # Left and right borders (2 pixels each)
            for y in range(max(0, py), min(raster_height, py + ph)):
                for x in range(max(0, px), min(raster_width, px + 2)):
                    pixels[x, y] = border_rgba
                for x in range(max(0, px + pw - 2), min(raster_width, px + pw)):
                    pixels[x, y] = border_rgba
    
    return img


def _export_unit_drawn_members(members):
    """The members of an export unit that actually put ink on the page.

    A hidden member contributes nothing: Resolume already filters on
    layer.visible before units are built, and an ungrouped hidden screen has
    always reached Photoshop as its own record at opacity 0. Grouping broke
    that - render_unit_to_image composited every member without ever reading
    visible, so a group of two with the second hidden arrived as ONE record at
    opacity 255, bounds covering both, the hidden member's pixels fully there.
    The PSD handed to graphics showed a section the designer was told had been
    struck from the build.

    A unit with NO visible member keeps all of them, which is what makes the
    ungrouped case identical to what it always was: the record is emitted at
    opacity 0 (invisible in Photoshop) with its pixels intact, so switching it
    back on in Photoshop still shows the screen.
    """
    members = [l for l in (members or []) if isinstance(l, dict)]
    drawn = [l for l in members if l.get('visible', True)]
    return drawn or members


def render_unit_to_image(members, raster_width, raster_height, include_borders=True):
    """Render one export unit - a lone layer, or every member of a screen
    group - onto a single raster-sized RGBA image.

    v0.11.0: a group has to reach Photoshop as ONE Photoshop layer, so its
    members composite into one image first. A single member returns exactly
    what render_layer_to_image returned before groups existed.
    """
    members = _export_unit_drawn_members(members)
    if not members:
        return Image.new('RGBA', (raster_width, raster_height), (0, 0, 0, 0))
    img = render_layer_to_image(members[0], raster_width, raster_height, include_borders)
    for member in members[1:]:
        member_img = render_layer_to_image(member, raster_width, raster_height, include_borders)
        img = Image.alpha_composite(img, member_img)
    return img


# View name mapping
VIEW_NAMES = {
    'pixel-map': 'Pixel Map',
    'cabinet-id': 'Cabinet ID',
    'data-flow': 'Data',
    'power': 'Power'
}


def render_view_to_image(view_mode, include_borders=True):
    """Render a specific view mode to an image"""
    raster_width = app.current_project.get('raster_width', 1920)
    raster_height = app.current_project.get('raster_height', 1080)
    
    # Create base image (black background)
    final_img = Image.new('RGB', (raster_width, raster_height), (0, 0, 0))
    
    # For now, render the pixel map view (panels with colors)
    # TODO: Implement different rendering for each view mode
    for layer in app.current_project['layers']:
        if layer.get('visible', True):
            layer_img = render_layer_to_image(layer, raster_width, raster_height, include_borders)
            # Composite onto final
            final_img.paste(layer_img, mask=layer_img.split()[3])
    
    return final_img


@export_bp.route('/api/export', methods=['POST'])
def export_unified():
    """Unified export endpoint handling PNG, PSD, and PDF formats"""
    import zipfile
    
    data = request.get_json() or {}
    project_name = data.get('project_name', 'Project')
    format_type = data.get('format', 'png')
    views = data.get('views', ['pixel-map'])
    include_borders = data.get('include_borders', True)
    
    raster_width = app.current_project.get('raster_width', 1920)
    raster_height = app.current_project.get('raster_height', 1080)
    
    if format_type == 'pdf':
        # PDF: All views combined into one multi-page document
        try:
            from reportlab.lib.pagesizes import letter, landscape
            from reportlab.pdfgen import canvas as pdf_canvas
            from reportlab.lib.utils import ImageReader
        except ImportError:
            return jsonify({'error': 'PDF export requires reportlab library'}), 500
        
        pdf_bytes = io.BytesIO()
        
        # Calculate page size to match raster aspect ratio
        page_width = raster_width
        page_height = raster_height
        
        c = pdf_canvas.Canvas(pdf_bytes, pagesize=(page_width, page_height))
        
        for view in views:
            # Render this view
            img = render_view_to_image(view, include_borders)
            
            # Add title
            view_name = VIEW_NAMES.get(view, view)
            
            # Draw the image
            img_reader = ImageReader(img)
            c.drawImage(img_reader, 0, 0, width=page_width, height=page_height)
            
            # Add label at top
            c.setFillColorRGB(1, 1, 1)  # White text
            c.setFont("Helvetica-Bold", 24)
            c.drawString(20, page_height - 40, f"{project_name} - {view_name}")
            
            c.showPage()
        
        c.save()
        pdf_bytes.seek(0)
        
        return send_file(
            pdf_bytes,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{project_name}.pdf"
        )
    
    elif format_type == 'psd':
        # PSD: Each view as a separate file with screen layers
        # If multiple views, package in ZIP
        try:
            import pytoshop
            from pytoshop import layers as psd_layers
            from pytoshop.enums import ColorMode
        except ImportError:
            return jsonify({'error': 'PSD export requires pytoshop library. Install with: pip3 install pytoshop'}), 500
        
        if len(views) == 1:
            # Single PSD file
            psd_bytes = create_psd_for_view(views[0], project_name, include_borders)
            view_name = VIEW_NAMES.get(views[0], views[0])
            
            return send_file(
                psd_bytes,
                mimetype='application/octet-stream',
                as_attachment=True,
                download_name=f"{project_name} - {view_name}.psd"
            )
        else:
            # Multiple PSDs in a ZIP
            zip_bytes = io.BytesIO()
            with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
                for view in views:
                    psd_bytes = create_psd_for_view(view, project_name, include_borders)
                    view_name = VIEW_NAMES.get(view, view)
                    zf.writestr(f"{project_name} - {view_name}.psd", psd_bytes.getvalue())
            
            zip_bytes.seek(0)
            return send_file(
                zip_bytes,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"{project_name} - PSD Files.zip"
            )
    
    else:
        # PNG: Each view as a separate file
        if len(views) == 1:
            # Single PNG file
            img = render_view_to_image(views[0], include_borders)
            view_name = VIEW_NAMES.get(views[0], views[0])
            
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            return send_file(
                img_bytes,
                mimetype='image/png',
                as_attachment=True,
                download_name=f"{project_name} - {view_name}.png"
            )
        else:
            # Multiple PNGs in a ZIP
            zip_bytes = io.BytesIO()
            with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
                for view in views:
                    img = render_view_to_image(view, include_borders)
                    view_name = VIEW_NAMES.get(view, view)
                    
                    img_bytes = io.BytesIO()
                    img.save(img_bytes, format='PNG')
                    zf.writestr(f"{project_name} - {view_name}.png", img_bytes.getvalue())
            
            zip_bytes.seek(0)
            return send_file(
                zip_bytes,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"{project_name} - PNG Files.zip"
            )


def create_psd_for_view(view_mode, project_name, include_borders):
    """Create a PSD file for a specific view with screen layers"""
    import pytoshop
    from pytoshop import layers as psd_layers
    from pytoshop.enums import ColorMode, Compression
    
    raster_width = app.current_project.get('raster_width', 1920)
    raster_height = app.current_project.get('raster_height', 1080)
    
    # Create PSD
    psd = pytoshop.PsdFile(num_channels=3, height=raster_height, width=raster_width, color_mode=ColorMode.rgb)
    
    layer_records = []

    # v0.11.0: one Photoshop layer per export unit. A screen group is one
    # screen, so it gets ONE Photoshop layer named for the group - anything
    # else and the person opening the PSD sees the seam we exist to hide.
    for unit_name, members in _export_units(app.current_project, app.current_project['layers']):
        layer = members[0]
        # Render the unit to image (a group composites its members first)
        layer_img = render_unit_to_image(members, raster_width, raster_height, include_borders)

        # Get unit bounds. Hidden members neither draw nor widen the record -
        # see _export_unit_drawn_members.
        bounds = _export_unit_bounds(_export_unit_drawn_members(members))
        offset_x = bounds['x']
        offset_y = bounds['y']
        layer_width = bounds['width']
        layer_height = bounds['height']

        # Clamp to raster bounds (int() ensures native Python ints for pytoshop)
        left = int(max(0, offset_x))
        top = int(max(0, offset_y))
        right = int(min(raster_width, offset_x + layer_width))
        bottom = int(min(raster_height, offset_y + layer_height))

        if right <= left or bottom <= top:
            continue

        # Crop to content bounds
        cropped_img = layer_img.crop((left, top, right, bottom))
        img_array = np.array(cropped_img.convert('RGB'))

        # Layer name from the group's name, or the screen's when ungrouped
        layer_name = unit_name if unit_name is not None else f"Screen {layer['id']}"

        # Create layer record
        layer_record = psd_layers.LayerRecord(
            name=layer_name,
            top=top,
            left=left,
            bottom=bottom,
            right=right,
            opacity=255 if any(m.get('visible', True) for m in members) else 0,
            channels={
                0: psd_layers.ChannelImageData(image=img_array[:, :, 0].copy(), compression=Compression.raw),
                1: psd_layers.ChannelImageData(image=img_array[:, :, 1].copy(), compression=Compression.raw),
                2: psd_layers.ChannelImageData(image=img_array[:, :, 2].copy(), compression=Compression.raw),
            }
        )
        layer_records.append(layer_record)

    psd.layer_and_mask_info.layer_info.layer_records = layer_records

    psd_bytes = io.BytesIO()
    psd.write(psd_bytes)
    psd_bytes.seek(0)

    return psd_bytes


@export_bp.route('/api/export/png', methods=['POST'])
def export_png():
    """Export as flattened PNG"""
    data = request.get_json() or {}
    include_borders = data.get('include_borders', True)
    
    raster_width = app.current_project.get('raster_width', 1920)
    raster_height = app.current_project.get('raster_height', 1080)
    
    # Create base image (black background)
    final_img = Image.new('RGBA', (raster_width, raster_height), (0, 0, 0, 255))
    
    # Render and composite each visible layer
    for layer in app.current_project['layers']:
        if layer.get('visible', True):
            layer_img = render_layer_to_image(layer, raster_width, raster_height, include_borders)
            final_img = Image.alpha_composite(final_img, layer_img)
    
    # Convert to RGB for PNG (no transparency needed for final)
    final_rgb = Image.new('RGB', final_img.size, (0, 0, 0))
    final_rgb.paste(final_img, mask=final_img.split()[3])
    
    # Save to bytes
    img_bytes = io.BytesIO()
    final_rgb.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return send_file(
        img_bytes,
        mimetype='image/png',
        as_attachment=True,
        download_name=f"{app.current_project['name']}.png"
    )


@export_bp.route('/api/export/psd', methods=['POST'])
def export_psd():
    """Export as PSD with layers - each screen as a named layer at correct position"""
    data = request.get_json() or {}
    include_borders = data.get('include_borders', True)
    
    raster_width = app.current_project.get('raster_width', 1920)
    raster_height = app.current_project.get('raster_height', 1080)
    
    try:
        import pytoshop
        from pytoshop import layers as psd_layers
        from pytoshop.enums import ColorMode, Compression
    except ImportError:
        # Fall back to creating a ZIP of individual layer PNGs
        return export_layers_as_zip(include_borders, raster_width, raster_height)
    
    # Create PSD using pytoshop
    psd = pytoshop.PsdFile(num_channels=3, height=raster_height, width=raster_width, color_mode=ColorMode.rgb)
    
    # We need to build layer list
    layer_records = []
    
    # Add each export unit (in reverse order so first layer is on bottom in a
    # layer panel). v0.11.0: a screen group is ONE Photoshop layer, named for
    # the group - see create_psd_for_view.
    for unit_name, members in _export_units(app.current_project, app.current_project['layers']):
        layer = members[0]
        # Render the unit to image (full raster size with transparency)
        layer_img = render_unit_to_image(members, raster_width, raster_height, include_borders)

        # Get unit bounds (where the actual content is). Hidden members neither
        # draw nor widen the record - see _export_unit_drawn_members.
        bounds = _export_unit_bounds(_export_unit_drawn_members(members))
        offset_x = bounds['x']
        offset_y = bounds['y']
        layer_width = bounds['width']
        layer_height = bounds['height']
        
        # Crop to just the layer content area for efficiency
        # But clamp to raster bounds (int() ensures native Python ints for pytoshop)
        left = int(max(0, offset_x))
        top = int(max(0, offset_y))
        right = int(min(raster_width, offset_x + layer_width))
        bottom = int(min(raster_height, offset_y + layer_height))
        
        if right <= left or bottom <= top:
            continue  # Layer is completely outside raster
        
        # Crop the layer image to content bounds
        cropped_img = layer_img.crop((left, top, right, bottom))
        
        # Convert to numpy array (RGB only, no alpha for simplicity)
        img_array = np.array(cropped_img.convert('RGB'))
        
        # Get layer name from the group's name, or the screen's when ungrouped
        layer_name = unit_name if unit_name is not None else f"Screen {layer['id']}"

        # Create layer record with position
        layer_record = psd_layers.LayerRecord(
            name=layer_name,
            top=top,
            left=left,
            bottom=bottom,
            right=right,
            opacity=255 if any(m.get('visible', True) for m in members) else 0,
            channels={
                0: psd_layers.ChannelImageData(image=img_array[:, :, 0].copy(), compression=Compression.raw),
                1: psd_layers.ChannelImageData(image=img_array[:, :, 1].copy(), compression=Compression.raw),
                2: psd_layers.ChannelImageData(image=img_array[:, :, 2].copy(), compression=Compression.raw),
            }
        )
        layer_records.append(layer_record)
    
    # Add layers to PSD
    psd.layer_and_mask_info.layer_info.layer_records = layer_records
    
    # Save to bytes
    psd_bytes = io.BytesIO()
    psd.write(psd_bytes)
    psd_bytes.seek(0)
    
    return send_file(
        psd_bytes,
        mimetype='application/octet-stream',
        as_attachment=True,
        download_name=f"{app.current_project['name']}.psd"
    )


def export_layers_as_zip(include_borders, raster_width, raster_height):
    """Fallback: Export layers as individual PNGs in a ZIP file"""
    import zipfile
    
    zip_bytes = io.BytesIO()
    
    # v0.11.0: one PNG per export unit, so a screen group leaves one file
    # named for the group rather than one file per member.
    units = _export_units(app.current_project, app.current_project['layers'])

    with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add each unit as a separate PNG
        for unit_name, members in units:
            layer_img = render_unit_to_image(members, raster_width, raster_height, include_borders)

            # Convert to RGB with transparency info preserved
            img_bytes = io.BytesIO()
            layer_img.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            layer_name = unit_name if unit_name is not None else f"Layer_{members[0]['id']}"
            # Sanitize filename
            safe_name = "".join(c for c in layer_name if c.isalnum() or c in (' ', '-', '_')).strip()
            zf.writestr(f"{safe_name}.png", img_bytes.getvalue())

        # Add a manifest with unit info
        def manifest_entry(unit_name, members):
            bounds = _export_unit_bounds(_export_unit_drawn_members(members))
            # A lone layer keeps reporting its own nominal offset, as it always
            # has; a group has no single offset, so it reports the union's.
            offset = (members[0] if len(members) == 1 else None)
            return {
                'name': unit_name if unit_name is not None else f"Layer_{members[0]['id']}",
                'offset_x': offset.get('offset_x', 0) if offset else bounds['x'],
                'offset_y': offset.get('offset_y', 0) if offset else bounds['y'],
                'width': bounds['width'],
                'height': bounds['height'],
                'visible': any(m.get('visible', True) for m in members)
            }

        manifest = {
            'project_name': app.current_project['name'],
            'raster_width': raster_width,
            'raster_height': raster_height,
            'layers': [manifest_entry(n, ms) for n, ms in units]
        }
        zf.writestr('manifest.json', json.dumps(manifest, indent=2))
    
    zip_bytes.seek(0)
    
    return send_file(
        zip_bytes,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"{app.current_project['name']}_layers.zip"
    )


@export_bp.route('/api/export/zip', methods=['POST'])
def export_zip():
    """Export as ZIP of individual layer PNGs"""
    data = request.get_json() or {}
    include_borders = data.get('include_borders', True)
    
    raster_width = app.current_project.get('raster_width', 1920)
    raster_height = app.current_project.get('raster_height', 1080)
    
    return export_layers_as_zip(include_borders, raster_width, raster_height)


# ============================================================================
# CLIENT-RENDERED IMAGE EXPORT ENDPOINTS
# These accept base64 PNG data from client-side canvas capture
# ============================================================================

def decode_base64_image(data_url):
    """Decode a base64 data URL to PIL Image"""
    # Remove the data:image/png;base64, prefix
    if ',' in data_url:
        data_url = data_url.split(',')[1]
    img_data = base64.b64decode(data_url)
    return Image.open(io.BytesIO(img_data))


@export_bp.route('/api/export/zip-images', methods=['POST'])
def export_zip_images():
    """Create a ZIP file from client-rendered images"""
    import zipfile
    
    data = request.get_json() or {}
    project_name = data.get('project_name', 'Project')
    images = data.get('images', [])
    
    zip_bytes = io.BytesIO()
    
    with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
        for img_info in images:
            img = decode_base64_image(img_info['data'])
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            zf.writestr(img_info['name'], img_bytes.getvalue())
    
    zip_bytes.seek(0)
    
    return send_file(
        zip_bytes,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"{project_name} - PNG Files.zip"
    )


@export_bp.route('/api/export/pdf-from-images', methods=['POST'])
def export_pdf_from_images():
    """Create a multi-page PDF from client-rendered images"""
    try:
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.utils import ImageReader
    except ImportError:
        return jsonify({'error': 'PDF export requires reportlab library'}), 500
    
    data = request.get_json() or {}
    project_name = data.get('project_name', 'Project')
    images = data.get('images', [])
    default_width = data.get('width', 1920)
    default_height = data.get('height', 1080)
    
    pdf_bytes = io.BytesIO()
    c = pdf_canvas.Canvas(pdf_bytes, pagesize=(default_width, default_height))
    
    # The binder (app-binder.js) sends finished pages: it asks for real
    # letter-landscape pages in points (`page_size`) with the bitmap scaled
    # to fill them, and no stamped view label (`labels: false`) - its pages
    # carry their own headers. Every other caller keeps today's behaviour:
    # one page per image at the image's pixel size, the label on top.
    labels = data.get('labels', True)

    for img_info in images:
        img = decode_base64_image(img_info['data'])
        page_size = img_info.get('page_size')
        if (isinstance(page_size, (list, tuple)) and len(page_size) == 2
                and all(isinstance(v, (int, float)) and v > 0 for v in page_size)):
            page_width, page_height = float(page_size[0]), float(page_size[1])
        else:
            page_width = int(img_info.get('width') or img.width or default_width)
            page_height = int(img_info.get('height') or img.height or default_height)
        c.setPageSize((page_width, page_height))
        img_reader = ImageReader(img)
        
        # Draw image filling the page
        c.drawImage(img_reader, 0, 0, width=page_width, height=page_height)
        
        # Add view name label at top
        if labels:
            c.setFillColorRGB(1, 1, 1)  # White
            c.setFont("Helvetica-Bold", 24)
            c.drawString(20, page_height - 40, f"{project_name} - {img_info['name']}")
        
        c.showPage()
    
    c.save()
    pdf_bytes.seek(0)
    
    return send_file(
        pdf_bytes,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"{project_name}.pdf"
    )


# The binder's page in points: the page is 200 px/in (2200 px = 11 in =
# 792 pt), so a page px is 72 / 200 pt; each page's own `page_size` is the
# authority and the scale is read off it.
_PAGE_OPS = ('rect', 'line', 'text', 'image')


def _pdf_page_replay(c, page, ImageReader, pdfmetrics, HexColor):
    """Replay one binder page - its display list (app-binder.js's _bRecCtx)
    - onto the reportlab canvas `c`, sized to the page. Raises ValueError
    on a malformed page."""
    if not isinstance(page, dict):
        raise ValueError('a page must be an object')
    page_size = page.get('page_size')
    if not (isinstance(page_size, (list, tuple)) and len(page_size) == 2
            and all(isinstance(v, (int, float)) and v > 0 for v in page_size)):
        raise ValueError('page_size must be [width, height] in points')
    width, height = page.get('width'), page.get('height')
    if not all(isinstance(v, (int, float)) and v > 0 for v in (width, height)):
        raise ValueError('width and height must be positive page pixels')
    ops = page.get('ops')
    if not isinstance(ops, list):
        raise ValueError('ops must be a list')
    images = page.get('images') or {}
    if not isinstance(images, dict):
        raise ValueError('images must be an object of id -> data URL')
    pw, ph = float(page_size[0]), float(page_size[1])
    sx, sy = pw / float(width), ph / float(height)
    s = sx                                  # one scale: the page keeps its aspect
    c.setPageSize((pw, ph))

    def num(v, what):
        if not isinstance(v, (int, float)):
            raise ValueError(f'{what} must be a number')
        return float(v)

    def colour(v):
        try:
            return HexColor(v if isinstance(v, str) and v else '#000000')
        except Exception:
            raise ValueError(f'bad colour {v!r}')

    readers = {}
    for op in ops:
        if not isinstance(op, dict) or op.get('op') not in _PAGE_OPS:
            raise ValueError('every op must be one of ' + ', '.join(_PAGE_OPS))
        kind = op['op']
        if kind == 'rect':
            x, y = num(op.get('x'), 'x') * s, num(op.get('y'), 'y') * sy
            w, h = num(op.get('w'), 'w') * s, num(op.get('h'), 'h') * sy
            fill = op.get('fill')
            stroke = op.get('stroke')
            if not fill and not stroke:
                continue
            if fill:
                c.setFillColor(colour(fill))
            if stroke:
                c.setStrokeColor(colour(stroke))
                c.setLineWidth(num(op.get('width', 1), 'width') * s)
                c.setDash([])
            c.rect(x, ph - y - h, w, h, stroke=1 if stroke else 0, fill=1 if fill else 0)
        elif kind == 'line':
            points = op.get('points')
            if not isinstance(points, list) or len(points) < 2:
                raise ValueError('a line needs at least two points')
            c.setStrokeColor(colour(op.get('stroke') or '#000000'))
            c.setLineWidth(num(op.get('width', 1), 'width') * s)
            dash = op.get('dash') or []
            if not isinstance(dash, list):
                raise ValueError('dash must be a list')
            c.setDash([num(d, 'dash') * s for d in dash] if dash else [])
            path = c.beginPath()
            for i, pt in enumerate(points):
                if not (isinstance(pt, (list, tuple)) and len(pt) == 2):
                    raise ValueError('a point is [x, y]')
                px, py = num(pt[0], 'x') * s, ph - num(pt[1], 'y') * sy
                (path.moveTo if i == 0 else path.lineTo)(px, py)
            c.drawPath(path, stroke=1, fill=0)
        elif kind == 'text':
            text = op.get('text')
            if not isinstance(text, str):
                raise ValueError('text must be a string')
            size = num(op.get('size', 24), 'size') * s
            weight = op.get('weight', 400)
            font = 'Helvetica-Bold' if isinstance(weight, (int, float)) and weight >= 600 else 'Helvetica'
            x, y = num(op.get('x'), 'x') * s, num(op.get('y'), 'y') * sy
            align = op.get('align') or 'left'
            baseline = op.get('baseline') or 'alphabetic'
            rotate = num(op.get('rotate', 0), 'rotate')
            tw = pdfmetrics.stringWidth(text, font, size)
            dx = -tw / 2 if align == 'center' else (-tw if align in ('right', 'end') else 0.0)
            # the canvas baselines, as an offset from the alphabetic one
            # (canvas y grows down; these are in page-down terms)
            dy = {'middle': size * 0.35, 'top': size * 0.8, 'hanging': size * 0.8,
                  'bottom': -size * 0.2, 'ideographic': -size * 0.2}.get(baseline, 0.0)
            c.setFillColor(colour(op.get('color') or '#000000'))
            c.setFont(font, size)
            if rotate:
                c.saveState()
                c.translate(x, ph - y)
                # a canvas rotation is clockwise in a y-down space: the
                # same turn in PDF's y-up space is the negative angle
                c.rotate(-rotate * 180.0 / math.pi)
                c.drawString(dx, -dy, text)
                c.restoreState()
            else:
                c.drawString(x + dx, ph - (y + dy), text)
        elif kind == 'image':
            iid = op.get('id')
            data = images.get(iid) if isinstance(iid, str) else None
            if not isinstance(data, str):
                raise ValueError(f'image {iid!r} has no bitmap')
            x, y = num(op.get('x'), 'x') * s, num(op.get('y'), 'y') * sy
            w, h = num(op.get('w'), 'w') * s, num(op.get('h'), 'h') * sy
            if iid not in readers:
                try:
                    readers[iid] = ImageReader(decode_base64_image(data))
                except Exception:
                    raise ValueError(f'image {iid!r} is not a PNG data URL')
            c.drawImage(readers[iid], x, ph - y - h, width=w, height=h, mask='auto')


@export_bp.route('/api/export/pdf-from-pages', methods=['POST'])
def export_pdf_from_pages():
    """Create a multi-page PDF from client-laid pages sent as DISPLAY LISTS
    (the binder, app-binder.js): every page is { name, width, height,
    page_size, ops, images } - rects, lines and text as vector ops in page
    pixels, the bitmaps (the maps, the cover's raster) by id - so the text
    in the PDF is real text, set in Helvetica, and only the maps are
    images. pdf-from-images beside this keeps every other export."""
    try:
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfbase import pdfmetrics
        from reportlab.lib.colors import HexColor
    except ImportError:
        return jsonify({'error': 'PDF export requires reportlab library'}), 500

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Expected a JSON object with pages'}), 400
    project_name = data.get('project_name') or 'Project'
    pages = data.get('pages')
    if not isinstance(pages, list) or not pages:
        return jsonify({'error': 'pages must be a non-empty list'}), 400

    pdf_bytes = io.BytesIO()
    c = pdf_canvas.Canvas(pdf_bytes, pagesize=(792, 612))
    c.setTitle(str(project_name))
    for i, page in enumerate(pages):
        try:
            _pdf_page_replay(c, page, ImageReader, pdfmetrics, HexColor)
        except ValueError as e:
            return jsonify({'error': f'page {i + 1}: {e}'}), 400
        c.showPage()
    c.save()
    pdf_bytes.seek(0)

    return send_file(
        pdf_bytes,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"{project_name}.pdf"
    )


# ── PSD "Elements" (issue #12) ────────────────────────────────────────────
# The client renders a view once per STAGE - the cabinet fills, the borders,
# the test pattern, the cabinet numbers, the data runs, the circuits, the
# screen name - each on a transparent canvas, and posts them all in one
# request with mode='elements'. Each screen becomes a PSD GROUP named for the
# screen, holding one layer per stage cropped to the screen's rectangle (the
# same rectangle the one-layer-per-screen export crops), top to bottom in
# PSD_SCREEN_STAGES order. The stages that are not any one screen's - the
# images, the text, the canvas outline - go in a top-level "Canvas" group
# over the screens, cropped to the whole picture. A stage whose crop is
# fully transparent is left out, and a group left with nothing is too. An
# opaque export gets a solid "Background" layer under everything.
#
# The one-layer-per-screen path (mode absent) is not touched by any of this.

# Top to bottom, as Photoshop lists them.
PSD_SCREEN_STAGES = ['Screen name', 'Power', 'Data', 'Cabinet IDs', 'Test pattern',
                     'Borders', 'Panels']
PSD_CANVAS_STAGES = ['Canvas outline', 'Text', 'Image']
PSD_CANVAS_GROUP = 'Canvas'
PSD_BACKGROUND_LAYER = 'Background'


# How an element layer's channels are stored: ZIP (PSD compression 2,
# zlib), a fifth of raw - the Experts Only power map is 25 MB against 133.
# Photoshop 2026 opened a zipped-layers file (Matt, 2026-09-22) once the
# MERGED PREVIEW was raw: the first files had the preview zipped as well,
# and Photoshop refused them whole ("not compatible with this version").
# pytoshop's RLE needs its compiled packbits extension, which the app's
# environment does not carry.
PSD_ELEMENT_COMPRESSION = 'zip'


def _psd_pixel_layer(psd_layers, Compression, name, top, left, rgba):
    """One pixel layer at (top, left) from an RGBA array, built the way the
    one-layer-per-screen export builds its layers. Channel compression per
    PSD_ELEMENT_COMPRESSION."""
    comp = getattr(Compression, PSD_ELEMENT_COMPRESSION)
    channels = {
        -1: psd_layers.ChannelImageData(image=rgba[:, :, 3].copy(), compression=comp),
        0: psd_layers.ChannelImageData(image=rgba[:, :, 0].copy(), compression=comp),
        1: psd_layers.ChannelImageData(image=rgba[:, :, 1].copy(), compression=comp),
        2: psd_layers.ChannelImageData(image=rgba[:, :, 2].copy(), compression=comp),
    }
    record = psd_layers.LayerRecord(
        name=name, top=top, left=left,
        bottom=top + rgba.shape[0], right=left + rgba.shape[1],
        opacity=255, channels=channels)
    record.mask = _empty_psd_layer_mask(psd_layers)
    return record


def _psd_group_records(psd_layers, name, members_top_to_bottom):
    """The records of one PSD group in FILE order (bottom to top): the
    bounding divider, the members bottom first, then the folder record
    carrying the group's name. That is the order pytoshop's own reader and
    psd_tools walk a group from; the folder record last is what makes the
    name land on the folder rather than on a member."""
    from pytoshop import tagged_block
    from pytoshop.enums import SectionDividerSetting
    closer = psd_layers.LayerRecord(
        name='</Layer group>',
        blocks=[tagged_block.SectionDividerSetting(type=SectionDividerSetting.bounding)],
        pixel_data_irrelevant=True)
    closer.mask = _empty_psd_layer_mask(psd_layers)
    folder = psd_layers.LayerRecord(
        name=name,
        blocks=[tagged_block.SectionDividerSetting(type=SectionDividerSetting.open)],
        pixel_data_irrelevant=True)
    folder.mask = _empty_psd_layer_mask(psd_layers)
    return [closer] + list(reversed(members_top_to_bottom)) + [folder]


def _psd_screen_rects(layers_info, width, height):
    """The (name, left, top, right, bottom) of every visible screen that
    lands inside the picture - the crop the one-layer-per-screen export
    makes, computed the same way."""
    rects = []
    for layer_info in layers_info:
        if not layer_info.get('visible', True):
            continue
        offset_x = int(layer_info.get('offset_x', 0))
        offset_y = int(layer_info.get('offset_y', 0))
        left = max(0, offset_x)
        top = max(0, offset_y)
        right = min(width, offset_x + int(layer_info.get('width', 100)))
        bottom = min(height, offset_y + int(layer_info.get('height', 100)))
        if right <= left or bottom <= top:
            continue
        rects.append((layer_info.get('name', 'Screen'), left, top, right, bottom))
    return rects


def _psd_elements_layer_records(psd_layers, Compression, stages, layers_info,
                                width, height, background=None):
    """Build the layer records (file order) of an Elements PSD.

    `stages` is [{name, image_data}] - one full-picture RGBA render per
    stage. Each is decoded once, cropped for every screen (and, for a canvas
    stage, kept whole), and dropped before the next is decoded, so at most
    one full render is in memory at a time on top of the crops kept."""
    rects = _psd_screen_rects(layers_info, width, height)
    # name -> {stage: rgba}; the screens by index so two screens with one
    # name stay two groups.
    screen_crops = [dict() for _ in rects]
    canvas_crops = {}
    for stage in stages:
        stage_name = stage.get('name')
        if stage_name not in PSD_SCREEN_STAGES and stage_name not in PSD_CANVAS_STAGES:
            continue
        image = decode_base64_image(stage.get('image_data', '')).convert('RGBA')
        try:
            if stage_name in PSD_CANVAS_STAGES:
                # No screen bounds a canvas stage, so its layer is cut to
                # its ink, the way Photoshop itself bounds a layer.
                whole = image.crop((0, 0, width, height))
                box = whole.getchannel('A').getbbox()
                if box:
                    canvas_crops[stage_name] = (box[0], box[1], np.array(whole.crop(box)))
                continue
            for index, (_name, left, top, right, bottom) in enumerate(rects):
                crop = np.array(image.crop((left, top, right, bottom)))
                if crop[:, :, 3].any():
                    screen_crops[index][stage_name] = crop
        finally:
            image.close()

    records = []
    if background:
        rgb = background.lstrip('#')
        r, g, b = (int(rgb[i:i + 2], 16) for i in (0, 2, 4)) if len(rgb) == 6 else (0, 0, 0)
        solid = np.empty((height, width, 4), dtype=np.uint8)
        solid[:, :, 0], solid[:, :, 1], solid[:, :, 2], solid[:, :, 3] = r, g, b, 255
        records.append(_psd_pixel_layer(psd_layers, Compression, PSD_BACKGROUND_LAYER, 0, 0, solid))
    for index, (name, left, top, _right, _bottom) in enumerate(rects):
        crops = screen_crops[index]
        members = [_psd_pixel_layer(psd_layers, Compression, stage_name, top, left, crops[stage_name])
                   for stage_name in PSD_SCREEN_STAGES if stage_name in crops]
        if members:
            records.extend(_psd_group_records(psd_layers, name, members))
    members = [_psd_pixel_layer(psd_layers, Compression, stage_name,
                                canvas_crops[stage_name][1], canvas_crops[stage_name][0],
                                canvas_crops[stage_name][2])
               for stage_name in PSD_CANVAS_STAGES if stage_name in canvas_crops]
    if members:
        records.extend(_psd_group_records(psd_layers, PSD_CANVAS_GROUP, members))
    return records


def _psd_set_preview(psd, flat):
    """Write the flattened picture into the PSD as its merged image.

    Photoshop rebuilds the composite from the layers, so it never needed
    this - but Quick Look, Preview, Illustrator's Place and every viewer
    that is not Photoshop read the merged image, and without it our PSDs
    thumbnailed solid black (found 2026-09-22 while checking the element
    layers; the one-layer-per-screen PSD had always been the same). `flat`
    is the PIL image the client rendered; a transparent export is
    flattened onto black, which is what the canvas shows behind it.
    """
    if flat is None:
        return
    from pytoshop import image_data as psd_image_data
    from pytoshop.enums import Compression
    rgba = np.array(flat.convert('RGBA'))
    if rgba.shape[0] != psd.height or rgba.shape[1] != psd.width:
        return
    alpha = rgba[:, :, 3:4].astype(np.uint16)
    rgb = ((rgba[:, :, :3].astype(np.uint16) * alpha) // 255).astype(np.uint8)
    # RAW: Photoshop accepts only raw or RLE for the merged image; a zipped
    # preview made Photoshop 2026 refuse the whole file.
    psd.image_data = psd_image_data.ImageData(
        channels=np.stack([rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]]), compression=Compression.raw)


def _psd_bytes(PsdFile, ColorMode, width, height, layer_records, flat=None):
    psd = PsdFile(num_channels=3, height=height, width=width, color_mode=ColorMode.rgb)
    psd.layer_and_mask_info.layer_info.layer_records = layer_records
    _psd_set_preview(psd, flat)
    out = io.BytesIO()
    psd.write(out)
    out.seek(0)
    return out


@export_bp.route('/api/export/psd-from-image', methods=['POST'])
def export_psd_from_image():
    """Create a PSD from client-rendered image with screen layers"""
    try:
        from pytoshop import PsdFile
        from pytoshop import layers as psd_layers
        from pytoshop.enums import ColorMode, Compression
    except ImportError as e:
        print(f"PSD export error - pytoshop import failed: {e}")
        return jsonify({'error': f'PSD export requires pytoshop library: {e}'}), 500
    
    try:
        data = request.get_json() or {}
        project_name = data.get('project_name', 'Project')
        view_name = data.get('view_name', 'View')
        image_data = data.get('image_data', '')
        width = data.get('width', 1920)
        height = data.get('height', 1080)
        layers_info = data.get('layers', [])

        print(f"PSD export: {project_name} - {view_name}, {width}x{height}, {len(layers_info)} layers")

        if data.get('mode') == 'elements':
            stages = data.get('stages') or []
            layer_records = _psd_elements_layer_records(
                psd_layers, Compression, stages, layers_info, width, height,
                background=data.get('background'))
            flat = decode_base64_image(image_data) if image_data else None
            psd_bytes = _psd_bytes(PsdFile, ColorMode, width, height, layer_records, flat=flat)
            print(f"PSD elements export complete: {psd_bytes.getbuffer().nbytes} bytes, "
                  f"{len(stages)} stages, {len(layer_records)} records")
            log_event('export_psd_elements', {
                'project_name': project_name, 'view_name': view_name,
                'size': f'{width}x{height}', 'stages': len(stages),
                'records': len(layer_records)})
            return send_file(
                psd_bytes,
                mimetype='application/octet-stream',
                as_attachment=True,
                download_name=f"{project_name} - {view_name}.psd"
            )

        # Decode the full image
        full_img = decode_base64_image(image_data)
        full_img = full_img.convert('RGBA')  # Convert to RGBA for alpha support
        
        # Keep the merged document RGB; layer transparency is stored in each
        # layer's -1 channel. Advertising a document alpha channel without
        # merged alpha data triggers warnings in some PSD readers.
        psd = PsdFile(num_channels=3, height=height, width=width, color_mode=ColorMode.rgb)
        
        layer_records = []
        
        # Create a layer for each screen by cropping the full image
        # Each layer is ONLY the size of the screen, positioned correctly
        for layer_info in layers_info:
            layer_name = layer_info.get('name', 'Screen')
            offset_x = int(layer_info.get('offset_x', 0))
            offset_y = int(layer_info.get('offset_y', 0))
            layer_width = int(layer_info.get('width', 100))
            layer_height = int(layer_info.get('height', 100))
            visible = layer_info.get('visible', True)
            
            if not visible:
                continue
            
            # Calculate actual bounds (clamped to raster)
            left = max(0, offset_x)
            top = max(0, offset_y)
            right = min(width, offset_x + layer_width)
            bottom = min(height, offset_y + layer_height)
            
            if right <= left or bottom <= top:
                continue
            
            # Crop ONLY this layer's region from the full image
            cropped = full_img.crop((left, top, right, bottom))
            img_array = np.array(cropped)
            
            actual_width = right - left
            actual_height = bottom - top
            
            print(f"  Layer '{layer_name}': pos({left},{top}) size({actual_width}x{actual_height}), array shape: {img_array.shape}")
            
            # Create ChannelImageData for RGB + Alpha
            # Channel -1 is the alpha/transparency mask
            channels = {
                -1: psd_layers.ChannelImageData(image=img_array[:, :, 3].copy(), compression=Compression.raw),
                0: psd_layers.ChannelImageData(image=img_array[:, :, 0].copy(), compression=Compression.raw),
                1: psd_layers.ChannelImageData(image=img_array[:, :, 1].copy(), compression=Compression.raw),
                2: psd_layers.ChannelImageData(image=img_array[:, :, 2].copy(), compression=Compression.raw),
            }
            
            # Create layer record - bounds define position AND size
            layer_record = psd_layers.LayerRecord(
                name=layer_name,
                top=top,
                left=left,
                bottom=bottom,
                right=right,
                opacity=255,
                channels=channels
            )
            layer_record.mask = _empty_psd_layer_mask(psd_layers)
            layer_records.append(layer_record)
        
        psd.layer_and_mask_info.layer_info.layer_records = layer_records
        _psd_set_preview(psd, full_img)
        
        psd_bytes = io.BytesIO()
        psd.write(psd_bytes)
        psd_bytes.seek(0)
        
        print(f"PSD export complete: {psd_bytes.getbuffer().nbytes} bytes, {len(layer_records)} layers")
        
        return send_file(
            psd_bytes,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=f"{project_name} - {view_name}.psd"
        )
    except Exception as e:
        print(f"PSD export error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'PSD export failed: {str(e)}'}), 500


@export_bp.route('/api/export/psd-zip-from-images', methods=['POST'])
def export_psd_zip_from_images():
    """Create multiple PSDs from client-rendered images, packaged in a ZIP"""
    import zipfile
    
    try:
        from pytoshop import PsdFile
        from pytoshop import layers as psd_layers
        from pytoshop.enums import ColorMode, Compression
    except ImportError as e:
        return jsonify({'error': f'PSD export requires pytoshop library: {e}'}), 500
    
    try:
        data = request.get_json() or {}
        project_name = data.get('project_name', 'Project')
        images = data.get('images', [])
        width = data.get('width', 1920)
        height = data.get('height', 1080)
        layers_info = data.get('layers', [])
        
        zip_bytes = io.BytesIO()
        
        with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
            for img_info in images:
                view_name = img_info['name']
                if data.get('mode') == 'elements':
                    # Each image carries its own stage renders; see
                    # _psd_elements_layer_records.
                    layer_records = _psd_elements_layer_records(
                        psd_layers, Compression, img_info.get('stages') or [],
                        layers_info, width, height,
                        background=img_info.get('background', data.get('background')))
                    flat = decode_base64_image(img_info['data']) if img_info.get('data') else None
                    psd_bytes_inner = _psd_bytes(PsdFile, ColorMode, width, height, layer_records, flat=flat)
                    zf.writestr(f"{project_name} - {view_name}.psd", psd_bytes_inner.getvalue())
                    continue
                full_img = decode_base64_image(img_info['data']).convert('RGBA')
                
                # Keep the merged document RGB; layer transparency is stored in
                # each layer's -1 channel.
                psd = PsdFile(num_channels=3, height=height, width=width, color_mode=ColorMode.rgb)
                layer_records = []
                
                # Create a layer for each screen
                for layer_info in layers_info:
                    layer_name = layer_info.get('name', 'Screen')
                    offset_x = int(layer_info.get('offset_x', 0))
                    offset_y = int(layer_info.get('offset_y', 0))
                    layer_width = int(layer_info.get('width', 100))
                    layer_height = int(layer_info.get('height', 100))
                    visible = layer_info.get('visible', True)
                    
                    if not visible:
                        continue
                    
                    left = max(0, offset_x)
                    top = max(0, offset_y)
                    right = min(width, offset_x + layer_width)
                    bottom = min(height, offset_y + layer_height)
                    
                    if right <= left or bottom <= top:
                        continue
                    
                    cropped = full_img.crop((left, top, right, bottom))
                    img_array = np.array(cropped)
                    
                    actual_width = right - left
                    actual_height = bottom - top
                    
                    # Create ChannelImageData for RGB + Alpha
                    channels = {
                        -1: psd_layers.ChannelImageData(image=img_array[:, :, 3].copy(), compression=Compression.raw),
                        0: psd_layers.ChannelImageData(image=img_array[:, :, 0].copy(), compression=Compression.raw),
                        1: psd_layers.ChannelImageData(image=img_array[:, :, 1].copy(), compression=Compression.raw),
                        2: psd_layers.ChannelImageData(image=img_array[:, :, 2].copy(), compression=Compression.raw),
                    }
                    
                    layer_record = psd_layers.LayerRecord(
                        name=layer_name,
                        top=top,
                        left=left,
                        bottom=bottom,
                        right=right,
                        opacity=255,
                        channels=channels
                    )
                    layer_record.mask = _empty_psd_layer_mask(psd_layers)
                    layer_records.append(layer_record)
                
                psd.layer_and_mask_info.layer_info.layer_records = layer_records
                _psd_set_preview(psd, full_img)
                
                psd_bytes_inner = io.BytesIO()
                psd.write(psd_bytes_inner)
                zf.writestr(f"{project_name} - {view_name}.psd", psd_bytes_inner.getvalue())
        
        zip_bytes.seek(0)
        
        return send_file(
            zip_bytes,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"{project_name} - PSD Files.zip"
        )
    except Exception as e:
        print(f"PSD ZIP export error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'PSD export failed: {str(e)}'}), 500


@export_bp.route('/api/export/resolume', methods=['POST'])
def export_resolume_xml():
    """Export project as Resolume Arena Advanced Output XML."""
    try:
        data = request.get_json() or {}
        project_name = data.get('project_name', app.current_project.get('name', 'Untitled Project'))
        raster_w = int(data.get('raster_width', app.current_project.get('raster_width', 3840)))
        raster_h = int(data.get('raster_height', app.current_project.get('raster_height', 2160)))

        xml_content = generate_resolume_xml(app.current_project, project_name, raster_w, raster_h)

        log_event('export_resolume', {
            'project_name': project_name,
            'raster': f'{raster_w}x{raster_h}',
            'layers': len([l for l in app.current_project.get('layers', []) if l.get('type') == 'screen' and l.get('visible', True)])
        })

        return send_file(
            io.BytesIO(xml_content.encode('utf-8')),
            mimetype='application/xml',
            as_attachment=True,
            download_name=f"{project_name}.xml"
        )
    except Exception as e:
        print(f"Resolume export error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Resolume export failed: {str(e)}'}), 500
