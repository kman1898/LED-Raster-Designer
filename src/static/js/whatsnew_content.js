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
            { h: 'The type chip',
              d: 'Every number on a distro carries a chip - Multi 208, Multi 120, L21-30. Click the spare one’s chip to pick, drag it onto a screen and it lands as that plug; the distro’s OUTPUTS row holds the same plugs. While you drag, the circuits the drop will feed light up with a pill, and a screen set to a different breakout refuses with the reason.' },
            { h: 'A multi takes what is free',
              d: 'Drag a multi over a wall and the span starts at the first circuit of the six and grows to the one under your cursor, capped at what is free - it says "took 5 of 6" when short. Right-click a circuit chip and Clear circuit takes that one circuit off while the other five stay put; clearing a multi welds the wall back to its natural six-circuit grid.' },
            { h: 'Drawing stops at capacity',
              d: 'In custom mode a circuit or port takes only as many cabinets as its settings allow, and a flow pattern applied to a block deals it out at capacity, every run starting from the same side. The readout ("S4-4 · 14/14 on circuit · full") now sits in the strip beside Fit and 1:1 instead of over the wall.' },
            { h: 'Every circuit carries its cable',
              d: 'The ≡ beside the chips flips them into a cable sheet - a length and connector per circuit, Tab walking the column, a count at the foot - and a chip wears its cable in its corner. Show Cable Tags, per screen and off by default, prints them beside the labels on the wall and in the export; Show 2fer / 3fer Tags drops the gang text and keeps the bracket.' },
            { h: 'Ports snake',
              d: 'Hold Alt and sweep the port chips of one card or box, then right-click Snake these N - or tick them in the card’s cable sheet and press Snake. A snake reads as a blue bracket (SNAKE A · 6-way · 100’) under its ports, a loose port carries its own length, a snaked port can carry an ext length for a shorter extension off the fan-out, and a backup port’s run is typed on the backup card’s or box’s own sheet and counted on the papers. The papers pull gear where its distro or breakout box sits - a Beach picked on the gear, on each screen in Screen Info, or made on the spot; a project keeps its beaches as a list, in the order the pull sheet and binder run - and list the CVTs and distros themselves. The Data panel’s Show Cable Tags prints them on the wall. The binder is a drawing set now: numbered sheets by subject (1.x overview, 2.x the screens in beach order and, within a beach, the Screen order you pick in the export dialog - alphabetical unless you say otherwise - each one’s power sheet then its data sheet, 3.x the pull sheets with positions side by side, 4.x hardware) that grow to fill their sheet with a title block down the right edge - your logo, a revision log written on export, venue, dates, designer, project manager, drafter - each map a numbered view with its tables beside it, on Tabloid 17 x 11 by default or any sheet size, the text real text in the PDF. A third sheet per screen, Signal + Power, draws the wall over the devices its ports and circuits land on: a run leaves the wall’s own label disc - no second tag over the panels - travels out at its own row and drops into its socket on the unit standing across the foot of the sheet, the units ordered by where their own runs stand and named inside themselves, and a run whose socket sits under its own column steps out past the wall’s edge and comes back rather than dropping through the discs below it. Every port is wired to its socket on its box or card, backups included, every circuit to its slot on the multi’s breakout; white casing under every line keeps it readable over the panels, and the printer palette tells the devices apart by a dash pattern per device instead of a hue. The tray itself is a fixed grid of columns: a unit keeps its place and its width whatever it is doing, so opening a cable sheet or folding a section only changes height and never shuffles the row - and the ⋮⋮ on a processor’s or a distro’s line drags along the tray to reorder them, with the papers following the order you set.' }
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
