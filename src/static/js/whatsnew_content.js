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
    '0.12': {
        title: 'The hardware dock, and power that matches the rack',
        items: [
            { h: 'Hardware lives in a dock',
              d: 'Processors and power distros sit in a dock along the bottom of the window. Wire a screen by dragging it onto a device; ports and circuits are patched right on the dock, so there is one place to see the whole patch. Alt-drag across port chips and right-click to snake them into one home run, or give a loose port its own length in the card’s cable sheet; a Show Cable Tags switch prints them beside the port labels.' },
            { h: 'A flag for unattached screens',
              d: 'While any screen still has unwired ports or circuits, the dock header shows a red flag with the count. Click it for a row per screen, and click a row to fly the view straight to it.' },
            { h: 'Redundancy, one bar and a pill',
              d: 'One bar behind the processor’s gear sets redundancy - Off, Whole unit, Per card or Per port - and a small gold pill on each processor and card header reads the shape in force; click it to open the bar. The redundant end of P1-1 is R1-1, a backup travels with its main, and every box numbers its ports the way its own silkscreen does.' },
            { h: 'Circuits are chips with meters',
              d: 'Each circuit is a chip whose fill bar shows how loaded it is at a glance, and a fully-patched box folds away to keep the dock short. A box also opens into a cable sheet, so each circuit can carry the length and connector of its cable for the paperwork, with a Show Cable Tags switch that prints them beside the labels on the map.' },
            { h: 'Take over one run with Alt',
              d: 'Hold Alt and route a single data run by hand. The rest of the wall keeps auto-cabling around it, so one custom run no longer costs you the automatic layout.' },
            { h: '110V and L21-30 power',
              d: 'Power planning now covers Edison (110V) breakouts and L21-30 feeds splitting to three 208V circuits at 30 A per leg, alongside soca, with True1 and powerCON connectors. Every multi box in the tray wears its connector type on a chip; pick it on the spare box, and the box lands as that plug.' },
            { h: 'A screen only lands on gear that can drive it',
              d: 'Dragging a screen onto hardware from a different product line is refused up front, so a patch that could never work is never drawn.' },
            { h: 'Labels wrap instead of inflating',
              d: 'A spaced port or circuit label breaks at the space before its circle grows, so a name like "SR A1" stacks into two lines instead of swallowing the neighboring cabinets.' }
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
