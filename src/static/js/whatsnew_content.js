/*
 * whatsnew_content.js: curated highlights for the "What's New" splash.
 *
 * Keyed by MAJOR.MINOR ("0.12", "1.0", ...). One entry per feature release;
 * patch releases (0.12.1 -> 0.12.2) never get their own entry and never
 * re-open the splash. This is NOT the changelog - VERSION.txt is the full
 * record; each entry here is 4-8 short items a person can read in a minute.
 *
 * Ships with the app (offline, no network). tests/test_whats_new.py fails
 * when VERSION.txt's top version has no entry here, so a new MAJOR.MINOR
 * cannot ship without its highlights.
 *
 * Shape: { 'MAJOR.MINOR': { title: str, items: [{ h: str, d: str }] } }
 *   h - short heading, d - one or two plain sentences. No markup, no emoji.
 */
window.WHATS_NEW_CONTENT = {
    '1.3': {
        title: 'A default for every screen colour, True1 and powerCON on 120V, whole-row fills, a rear view binder',
        items: [
            { h: 'A default for every screen colour',
              d: 'Preferences has a labelled colour for every mark a screen draws, on the Look, Data and Power tabs. A new screen takes them all and keeps them; existing screens are not touched.' },
            { h: 'True1 and powerCON on 110V and 120V',
              d: 'A screen at or below 120V can be set to Multi → True1 or Multi → powerCON as well as Edison, and a Multi 120 output feeds any of the three.' },
            { h: 'Every screen carries a breakout',
              d: 'The Preferences breakout is the default when the voltage allows it; otherwise Edison at or below 120V and True1 above. Edison is not offered above 120V and L21-30 stays 208V only.' },
            { h: 'Apply Pattern fills whole rows',
              d: 'In custom mode on an Organized screen a circuit or port takes another row or column only when all of it fits, so a run never starts in the middle of a row; Max Capacity and Maximize Power Use pack each run full. The marquee clears when the fill lands.' },
            { h: 'Deleting a canvas keeps shown screens',
              d: 'A screen shown on another canvas moves there instead of going with the deleted canvas, groups that move together stay grouped, and the confirm warns about overlaps.' },
            { h: 'Grouped names above the cables',
              d: 'On the Data and Power tabs a grouped screen\'s name draws on top of the runs that cross it.' },
            { h: 'Clear clears the whole circuit',
              d: 'Clear Circuit, Clear Port and Clear All on a grouped screen clear that circuit on every member, including a run a peer drew across it. A locked member is left alone.' },
            { h: 'Front or rear view in the binder',
              d: 'The binder has a Front / Rear choice for its Power and Data maps, saved with the project, and every screen sheet names its view in the heading. The overview is always the front.' }
        ]
    },
    '1.2': {
        title: 'PSD layers for every element, and an SVG export for Illustrator',
        items: [
            { h: 'A PSD layer for every element',
              d: 'Pick "Elements per screen" under PSD layers in the export dialog and each screen becomes a Photoshop group with its panels, borders, cabinet ids, data, power and name as separate layers.' },
            { h: 'The PSD you had is still the default',
              d: '"One layer per screen" stays the default and makes exactly the file it always did. The choice is remembered.' },
            { h: 'SVG export',
              d: 'A new export format with every label as real text and every cabinet and run as a shape, grouped per screen and per element. Illustrator opens it with named layers; Photoshop places it as a smart object.' },
            { h: 'PSD thumbnails',
              d: 'PSD files now carry a flattened preview, so Finder and Preview show the picture instead of a black thumbnail.' }
        ]
    },
    '1.1': {
        title: 'Change a screen’s cabinet type, Ctrl+A selects all screens, guide fixes',
        items: [
            { h: 'Change a screen’s cabinet type',
              d: 'Right-click a screen, or click the cabinet button next to the eye, and pick a different cabinet from the catalog. Only the cabinet changes; columns, rows, position, ports and circuits stay.' },
            { h: 'Ctrl+A selects all screens',
              d: 'Cmd+A or Ctrl+A selects every screen on the canvas, or every cabinet of a screen when you are selecting cabinets. It no longer selects the text on the page.' },
            { h: 'The guides no longer stop on a folded panel',
              d: 'A folded Screen Info section or a collapsed sidebar used to stop the Advanced Guide with "this step did not take". The guides now open what a step needs and put it back when you leave.' },
            { h: 'Go to takes you straight to a step',
              d: 'In a guide, type a step number into the Go to box and you are on that step right away, with everything before it already done, instead of watching the steps in between play at high speed.' }
        ]
    },
    '1.0': {
        title: 'The rack is in the app, and the papers match it',
        items: [
            { h: 'Hardware lives in a tray',
              d: 'Processors, cards, breakout boxes and distros sit in a tray under the canvas, and the middle sidebars are gone. Drag a port, a card, a multi or a whole unit onto a screen to wire it; a red flag on the tray counts what is still unattached and flies you to it.' },
            { h: 'Nothing lands by itself',
              d: 'A port is on a socket because you put it there, Clear always takes it off, and the drawing prints the socket it sits on - 6, 7, 8, 9 - the same numbers the tray shows.' },
            { h: 'Redundancy is one bar',
              d: 'Off, Whole unit, Per card or Per port, behind the processor’s gear, with exactly one thing beneath it. Every tray header wears a gold pill that reads the shape in force.' },
            { h: 'Power that adds up',
              d: 'A distro has a rating, a voltage and a phase, its legs are summed the way a genset spec means it, and every number on it is a plug you drag - Multi 208, Multi 120, L21-30. Shared circuits never pass their amps unless you draw the runs yourself.' },
            { h: 'Every cable on paper',
              d: 'A cable sheet on every multi and card, snakes under a blue bracket, an extension off the fan-out, and Show Cable Tags to print them on the wall.' },
            { h: 'Beaches',
              d: 'A position the show keeps. Screens, distros and boxes pick theirs - select several screens and right-click to put them on one - and the pull sheet and binder follow that order.' },
            { h: 'The binder is a drawing set',
              d: 'Numbered sheets with a title block and a revision log, real text in the PDF, a wiring sheet behind every map, and a screen’s own amps on the legs that feed it. Export Pull Sheet fills the shop workbook.' },
            { h: 'Guides that show you each step',
              d: 'Every step of the Quick Start, What’s New and Advanced Guide performs a real action in front of you, at a person’s pace. Enter is Next, Go to jumps to a step, and your own project comes back the moment you leave.' }
        ]
    },
    '0.11': {
        title: 'Screen groups',
        items: [
            { h: 'Group screens into one wall',
              d: 'Select several screens, right-click, and Group Screens. A wall built from more than one cabinet size now behaves as a single screen: one name, one set of totals, one thing to drag.' },
            { h: 'Cabinet numbers run straight through',
              d: 'Cabinet IDs continue across a group by where each cabinet actually sits, instead of restarting on every screen.' },
            { h: 'Wire across the join',
              d: 'Draw a data port or a power circuit straight across a group. Arrow keys carry the run into the neighboring screen and find the cabinet that is physically next door, even across different cabinet sizes.' },
            { h: 'Patterns follow the physical wall',
              d: 'Drag-select across a whole group and apply a serpentine or any other flow pattern. The run snakes the group in the order you would walk it.' },
            { h: 'Export treats a group as one screen',
              d: 'One shape in the Resolume XML named for the group, one Photoshop layer, and a rectangular group exports as a plain rectangle.' },
            { h: 'Drop shadows on logos and images',
              d: 'An image layer can cast a drop shadow - colour, opacity, angle, distance, spread and size. It is drawn into the artwork, so it exports exactly as you see it.' },
            { h: 'Export asks where to save',
              d: 'On the machine running the app, export asks for a folder even when you opened the app at its network address, and cancelling the chooser actually cancels.' }
        ]
    }
};
