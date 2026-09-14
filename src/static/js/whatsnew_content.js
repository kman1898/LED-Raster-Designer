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
        title: 'The hardware tray, and papers that match the rack',
        items: [
            { h: 'Hardware lives in a tray',
              d: 'Processors and power distros sit in a tray along the bottom of the window, and the middle sidebars are gone. Wire a screen by dragging a port, card, box, multi or distro onto it, so there is one place to see the whole patch; a red flag on the tray header counts what is still unattached, and a row flies you to the screen. The tray is a fixed grid, so opening a sheet never shuffles the row, and the ⋮⋮ on a processor or distro drags along the tray to reorder them.' },
            { h: 'Nothing lands by itself',
              d: 'Auto-numbering is retired: a port is on a card only because you dragged it there, Clear always releases it, and the flag counts what is left. An attached port prints the socket it sits on - 6, 7, 8, 9 on an unnamed card, H9-6 on a named one - the same numbers the tray shows.' },
            { h: 'Redundancy, one bar and a pill',
              d: 'One raised bar behind the processor’s gear sets it - Off, Whole unit, Per card, Per port - with exactly one thing beneath: a mirrored-by pick, a partner per slot, or Sequential / Split / Manual chips, the split reading OPT Split on a card whose face names its trunks. Every tray header wears a gold pill that reads the shape in force; click it to open the bar. A card’s breakout box picker offers only boxes that fit it - its vendor and its trunks - and keeps your pick after an add.' },
            { h: 'A multi lands as its plug and takes what is free',
              d: 'Every number on a distro carries a type chip - Multi 208, Multi 120, L21-30; click the spare one’s to pick, drag it onto a screen and it lands as that plug, and the distro’s OUTPUTS row holds the same plugs with a live preview of the circuits the drop will feed. The span starts at the first circuit of the six and grows to the one under your cursor, capped at what is free - it says "took 5 of 6" when short. Clear circuit takes one circuit off while the other five stay put; clearing a multi welds the wall back to its natural six-circuit grid.' },
            { h: 'Drawing stops at capacity',
              d: 'In custom mode a circuit or port takes only as many cabinets as its settings allow, and a flow pattern applied to a block deals it out at capacity, every run starting from the same side. The readout ("S4-4 · 14/14 on circuit · full") now sits in the strip beside Fit and 1:1 instead of over the wall.' },
            { h: 'Every circuit and every port carries its cable',
              d: 'The ≡ beside the chips flips them into a cable sheet - a length and connector per circuit, Tab walking the column, a count at the foot - and a chip wears its cable in its corner. On the data side, hold Alt and sweep port chips and right-click Snake these N, or tick them in the sheet and press Snake: a snake reads as a blue bracket (SNAKE A · 6 channel · 100’) and can hold sockets off any unit, a snaked port carries an ext length for a shorter extension off the fan-out, and a backup port’s run is typed on the backup card’s or box’s own sheet. Show Cable Tags, per screen and off by default, prints them beside the labels on the wall and in the export; Show 2fer / 3fer Tags drops the gang text and keeps the bracket.' },
            { h: 'Beaches, and the papers that follow them',
              d: 'A beach is a position the show keeps: add one from the Beaches line in the Screens panel or from any picker’s + New beach, drag to reorder, rename or remove. Each screen picks its beach in Screen Info, each distro and breakout box behind its gear. The pull sheet lists the beaches in that order and the binder runs its screens the same way, sorted within a beach by the Screen order you pick in the export dialog - alphabetical unless you say otherwise. In the Ports table every card and box is its own section, a backup box as its own.' },
            { h: 'The binder is a drawing set, with a wiring sheet behind every map',
              d: 'Numbered sheets by subject - 1.x overview, 2.x the screens, 3.x pull sheets, 4.x hardware - that grow to fill their page, each map a numbered view with its tables beside it and a title block down the right edge: your logo, a revision log written on export, venue, dates, designer, project manager, drafter. Tabloid 17 x 11 by default or any sheet size, the text real text in the PDF; turn Border and title block off and the drawing takes the whole sheet, the numbered view bubble at the foot naming it. One Wiring tick adds Power Wiring behind each Power sheet and Data Wiring behind each Data sheet, on pages of their own: every circuit wired to its slot on the breakout, every port to its socket on its card or box, each run leaving the wall’s own label disc by a clear edge and dropping into its socket on the unit across the foot, never crossing a label; the printer palette tells the units apart by a dash pattern each.' }
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
