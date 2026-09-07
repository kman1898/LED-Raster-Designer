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
        title: 'The hardware tray, and power that matches the rack',
        items: [
            { h: 'Hardware lives in a tray',
              d: 'Processors and power distros sit in a tray along the bottom of the window, and the middle sidebars are gone. Wire a screen by dragging a port, card, box, multi or distro onto it, so there is one place to see the whole patch. A red flag on the tray header counts what is still unattached; click it and a row flies you to the screen.' },
            { h: 'Nothing lands by itself',
              d: 'Auto-numbering is retired: a port is on a card only because you dragged it there, Clear always releases it, and the flag counts what is left. An attached port prints the socket it sits on - 6, 7, 8, 9 on an unnamed card, H9-6 on a named one - the same numbers the tray shows.' },
            { h: 'Redundancy, one bar and a pill',
              d: 'One raised bar behind the processor’s gear sets it - Off, Whole unit, Per card, Per port - with exactly one thing beneath: a mirrored-by pick, a partner per slot, or Sequential / Halves / Manual chips. Every tray header wears a gold pill that reads the shape in force; click it to open the bar.' },
            { h: 'A breakout wears its type',
              d: 'Every breakout carries a chip - Soca 208, Soca 120, L21-30. Click the spare breakout’s chip to pick, drag that breakout onto a screen and it lands as that plug; the distro’s OUTPUTS row holds the same plugs. While you drag, the circuits the drop will feed light up with a pill, and a screen set to a different breakout refuses with the reason.' },
            { h: 'A multi takes what its breakout has free',
              d: 'Drag a multi over a wall and the span starts at the first circuit of the six and grows to the one under your cursor, capped at what the breakout has free - it says "took 5 of 6" when short. Right-click a circuit chip and Clear circuit takes that one circuit off the breakout while the other five stay put; clearing a multi welds the wall back to its six-per-breakout grid.' },
            { h: 'Drawing stops at capacity',
              d: 'In custom mode a circuit or port takes only as many cabinets as its settings allow, and a flow pattern applied to a block deals it out at capacity, every run starting from the same side. The readout ("S4-4 · 14/14 on circuit · full") now sits in the strip beside Fit and 1:1 instead of over the wall.' },
            { h: 'Every circuit carries its cable',
              d: 'The ≡ on a breakout flips its chips into a cable sheet - a length and connector per circuit, Tab walking the column, a count at the foot - and a chip wears its cable in its corner. Show Cable Tags, per screen and off by default, prints them beside the labels on the wall and in the export; Show 2fer / 3fer Tags drops the gang text and keeps the bracket.' },
            { h: 'Ports snake',
              d: 'Hold Alt and sweep the port chips of one card or box, then right-click Snake these N - or tick them in the card’s cable sheet and press Snake. A snake reads as a blue bracket (SNAKE A · 6-way · 100’) under its ports, a loose port carries its own length, and the Data panel’s Show Cable Tags prints them on the wall.' }
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
