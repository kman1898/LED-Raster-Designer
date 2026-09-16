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
            { h: 'Tours that show you',
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
