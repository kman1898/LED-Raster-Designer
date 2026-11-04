/*
 * whatsnew_content.js: curated highlights for the "What's New" splash.
 *
 * Keyed by MAJOR.MINOR ("0.12", "1.0", ...). One entry per feature release.
 * A patch release (0.12.1 -> 0.12.2) re-opens the window only when it added
 * Advanced Guide steps (a step's `since`, quickstart.js); it may carry an
 * entry of its own keyed by the full version ("1.5.3"), and without one the
 * window lists the new steps' titles. An update that skips a patch shows
 * every patch entry since the version last run, newest first. This is NOT the changelog: VERSION.txt
 * is the full record; each entry here is 4-8 short items a person can read
 * in a minute.
 *
 * Ships with the app (offline, no network). tests/test_whats_new.py fails
 * when VERSION.txt's top version has no entry here, so a new MAJOR.MINOR
 * cannot ship without its highlights.
 *
 * Shape: { 'MAJOR.MINOR' | 'X.Y.Z': { title: str, items: [{ h: str, d: str }] } }
 *   h: short heading, d: one or two plain sentences. No markup, no emoji.
 */
window.WHATS_NEW_CONTENT = {
    '1.6': {
        title: 'A start page, cables named by their connector, US circuits at 80%, a power in for every distro, your panels on the pull sheet, mixed redundancy, mirror screens, a Fiber page and Z flow patterns',
        items: [
            { h: 'TRUE1 or powerCON, Cat6 or etherCON',
              d: 'The pull sheet and the binder say exactly which cable to pull. Power reads TRUE1 or powerCON from each screen\'s breakout, and data reads Cat6 or etherCON from each box\'s own outputs. The ≡ on a processor\'s header opens one cable list of every box on it.' },
            { h: 'A panel input for Edison and L6-20 screens',
              d: 'An Edison or L6-20 breakout now asks which connector your panels take, TRUE1 or powerCON, and the jumpers and splitters follow it. Each circuit gets one cable from its Edison or L6-20 plug to that panel input, with the 2fers at the panels.' },
            { h: 'US circuits filled to 80%',
              d: 'A circuit on a US distro, or on a screen with no distro at 208 V or below, is now filled to 80% of its breaker unless the distro\'s breakers are 100% rated, so a US screen may need more circuits than before. You still type the breaker size in the Amperage box, and the amps you can use now show beside it.' },
            { h: 'A power in for every distro',
              d: 'Open a distro\'s gear, type its power in length and pick whether it\'s powered from the service or thru another distro. A 400 A cam input lists a 400 A cam set with 5-wire, and the power in is on the pull sheet even before you type a length.' },
            { h: 'A start page, and your panels and cable stock on the pull sheet',
              d: 'The app opens on a start page: start a new project, open a file, or pick one of your recent files, which now opens as you last saved it. A new project opens the panel library first, and the panel you pick makes its first screen. Add Screen with nothing picked uses the last screen\'s panel. A panel you pick from the library is saved on the screen, and the pull sheet counts your panels by name, a row for each type on each screen. In Preferences > Cable stock, tick A list for each kind of cable to give multis, data, power, power in cables and the rest their own lengths.' },
            { h: 'Mixed redundancy, mirror screens and a Fiber page',
              d: 'On a chassis like an H series, the redundancy bar has a Mixed choice, so card 1 can be backed up 1:1 by card 2 while card 3 pairs its own ports. With an H_4xfiber in Copy mode, or an MX40 Pro with a box set to Mirror, drag it onto one screen and then onto a matching second screen, and the second becomes its copy with its runs off the copy OPTs. A show that uses fiber gets a Fiber page in the binder: every processor to its breakout boxes on one sheet, with the strands at both ends, the strand maps and the fiber cables to pull. The CVT10, CVT10 Pro and CVT4K come as single mode and multimode boxes, and each box, fiber cable and cable stock list says which.' },
            { h: 'Z flow patterns, and long rows cut into ports and circuits',
              d: 'Data and power get eight Z flow patterns, where every row starts again from the same side. Organized now cuts a row too long for one port or circuit into whole cabinets, Port numbers and Circuit numbers set the order, and Ports required shows the fewest ports a screen needs.' },
            { h: 'Check paperwork you\'ve already ordered from',
              d: 'US screens may need more circuits, powerCON screens listed TRUE1 jumpers, Edison and L6-20 screens had the wrong cables, and saved 2fers and 3fers past 80% now read OVER. If you ordered from an older pull sheet, export it again and compare.' }
        ]
    },
    '1.5.3': {
        title: '2fers and 3fers in custom mode, the cable you stock, and house power as a service',
        items: [
            { h: '2fers and 3fers in custom mode and groups',
              d: 'With Share circuits via splitters on, a fill in custom mode makes 2fers and 3fers one run per column, the same as automatic mode, and a group shares them as one wall. Right-click the screen and pick 3fer this screen: a circuit that spans three columns splits into its own three legs, and it never builds an OVER.' },
            { h: 'Right-click to 3fer a circuit',
              d: 'Right-click a circuit and pick 3fer it to split it into one leg per column on that same circuit, or 2fer it and 4fer it for two and four columns. The menu says what it does now: Un-share is Remove 3fer, and the tray\'s Clear multi and Clear circuit are Unplug multi and Unplug circuit.' },
            { h: 'Cable stock',
              d: 'In Preferences > Cable stock, type the lengths you own, like 25, 50 and 100. A 125 ft run then reads 100\'+25\' on the map, the pull sheet and the binder, and you can save the list as a preset for each shop.' },
            { h: 'House power as a service',
              d: 'Add the house service in the Hardware tray, say 600 A, and drag your distros onto its card. It adds up their legs against the service with the 80% rule, and the binder prints a Service sheet.' },
            { h: 'A tidier distro card',
              d: 'The OUTPUTS row shows one chip per connector type, like Socapex 208V x 3, and dragging it hands out the next free output. Grab the whole header bar to drag the distro onto a screen.' },
            { h: 'Redraws leave other circuits alone',
              d: 'Redrawing a circuit or a data port on an automatic screen can\'t take a cabinet another one already feeds. It tells you which circuit or port has it.' },
            { h: 'Half-size cabinets draw half the watts',
              d: 'A half cabinet now counts half the watts of a full one, unless the panel library lists its own. It used to count 65%, so a wall with a row of half cabinets read a few percent heavy.' },
            { h: 'See it in the app',
              d: 'Show me plays the new Advanced Guide steps one at a time, right in the app, and puts your show back when you\'re done. Help > What\'s New opens this window any time.' }
        ]
    },
    '1.5': {
        title: 'Distros built from their outputs, cable lengths in meters, and custom mode that stays on',
        items: [
            { h: 'Distros built from their outputs',
              d: 'Pick a power system, an input and amps per leg, then list the outputs: Socapex, L21-30, or TRUE1, powerCON, Edison and CEE outlets straight off the distro face. Start from a preset of a common US or EU distro, or save your own.' },
            { h: 'Every circuit checked against its breaker',
              d: 'US distros hold circuits to 80% of the breaker unless the breakers are 100% rated, and the distro to 80% of its rating unless the main is. Accept overload turns a red OVER amber, and the binder\'s Load line shows every leg and the 3-phase total.' },
            { h: 'Feet or meters',
              d: 'Preferences > Pull sheet & cables sets the unit new shows start in, and the Unit dropdown under the jumper fields switches the show you have open. Every cable length, tag, pull sheet row and binder table follows the show.' },
            { h: 'Metric long jumpers',
              d: 'A long jumper in a meters show is measured along the panels plus 0.3 m and rounded up to 1, 2, 3, 5 or 10 m. Both stock lists can be edited in Preferences.' },
            { h: 'Cabinets across screens',
              d: 'Drag over several selected screens on the Pixel Map to select cabinets on all of them, then blank or half-tile them in one step. A group acts as one screen.' },
            { h: 'Custom from a right-click',
              d: 'Right-click a screen or a group for Custom runs on the Data tab, or Custom circuits on the Power tab.' },
            { h: 'Custom mode stays on',
              d: 'A pattern button never takes a screen out of custom mode. With a screen or group selected and no cabinets, it fills the whole screen or group as custom runs.' },
            { h: 'Mixed cabinet sizes, read plainly',
              d: 'A custom run over two cabinet sizes reads its load in pixels, and a circuit over cabinets drawing different watts reads in watts. A group with different cabinet sizes says why its runs stay per screen.' }
        ]
    },
    '1.4': {
        title: 'Fiber by the strand, a backup processor in one switch, and panels you can move',
        items: [
            { h: 'Fiber by the strand',
              d: 'A breakout box\'s cable sheet opens on its Fiber section: each link picks a cable and the strands it rides. Pick the same TAC or MTP on another box and it takes the next free strands.' },
            { h: 'TAC, MTP and opticalCON',
              d: 'A TAC or MTP takes any strand count, with ST or LC duplex ends on a TAC. A TAC, MTP or opticalCON is shared across boxes by the strand, and NovaStar and Megapixel boxes have a BiDi switch for one strand per link.' },
            { h: 'Strands named the standard way',
              d: 'Strands read by the TIA-598 colors, with a tracer past 12, by number, or by subunit of 12, and any strand can be renamed. The binder prints each processor\'s fiber connections, a TAC pair flipped between its ends, and a strand map for every cable; the pull sheet counts each cable once.' },
            { h: 'A backup processor is one switch',
              d: 'Turn on Backup processor in the main\'s gear and name it. It mirrors the main output for output, lands on the same boxes\' X2 or OPT 2 inputs, and an SX40 sets its loops as A to B and C to D.' },
            { h: 'Panels go where you want them',
              d: 'Drag Settings, Screens or the hardware tray by its title bar to any edge of the window, or two to one edge side by side. View > Layouts saves the arrangement by name for every window connected to the app.' },
            { h: 'More in the Advanced Guide',
              d: 'New steps for the backup processor, the data and power jumper lengths, the fiber to a box, and picking its strands.' },
            { h: 'Power tags sit by their circuit',
              d: 'A power map\'s cable tags go above the disc when the circuit runs down, right or left, and under it when it runs up, with the 2fer or 3fer tag centered under the cable. Tags that would run off the screen go to the other side of the disc.' },
            { h: 'A grouped wall\'s whole load',
              d: 'The binder\'s show totals and a screen\'s FACTS count the circuits the whole wall carries, and FACTS has a Wall load row naming the screens.' }
        ]
    },
    '1.3': {
        title: 'A default for every screen color, TRUE1 and powerCON on 120V, whole-row fills, a rear view binder',
        items: [
            { h: 'A default for every screen color',
              d: 'Preferences has a labeled color for every mark a screen draws, on the Look, Data and Power tabs. A new screen takes them all and keeps them; existing screens are not touched.' },
            { h: 'TRUE1 and powerCON on 110V and 120V',
              d: 'A screen at or below 120V can be set to Multi → TRUE1 or Multi → powerCON as well as Edison, and a Multi 120 output feeds any of the three.' },
            { h: 'Every screen carries a breakout',
              d: 'The Preferences breakout is the default when the voltage allows it; otherwise Edison at or below 120V and TRUE1 above. Edison is not offered above 120V and L21-30 stays 208V only.' },
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
              d: 'A port is on a socket because you put it there, Clear always takes it off, and the drawing prints the socket it sits on (6, 7, 8, 9), the same numbers the tray shows.' },
            { h: 'Redundancy is one bar',
              d: 'Off, Whole unit, Per card or Per port, behind the processor’s gear, with exactly one thing beneath it. Every tray header wears a gold pill that reads the shape in force.' },
            { h: 'Power that adds up',
              d: 'A distro has a rating, a voltage and a phase, its legs are summed the way a genset spec means it, and every number on it is a plug you drag: Multi 208, Multi 120, L21-30. Shared circuits never pass their amps unless you draw the runs yourself.' },
            { h: 'Every cable on paper',
              d: 'A cable sheet on every multi and card, snakes under a blue bracket, an extension off the fan-out, and Show Cable Tags to print them on the wall.' },
            { h: 'Beaches',
              d: 'A position the show keeps. Screens, distros and boxes pick theirs (select several screens and right-click to put them on one), and the pull sheet and binder follow that order.' },
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
              d: 'An image can cast a drop shadow, with its color, opacity, angle, distance, spread and size. It is drawn into the artwork, so it exports exactly as you see it.' },
            { h: 'Export asks where to save',
              d: 'On the machine running the app, export asks for a folder even when you opened the app at its network address, and canceling the chooser actually cancels.' }
        ]
    }
};
