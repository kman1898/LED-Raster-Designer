# LED Raster Designer v1.6.0

LED Raster Designer is a free app for planning LED video walls for live
events, concerts, broadcast and installs. You lay out the cabinets, wire
the data and power, and it gives you the paperwork: pixel maps, wiring
drawings, a pull sheet and a full binder a crew can build from.

It runs on Mac and Windows, opens in your web browser, and works without
an internet connection.

**Who it's for:** LED techs, video engineers, crew chiefs and anyone who
has to get a wall from a design to a truck pack to a working screen.

---

## Download and install

### Mac
1. **[Download the latest Mac release](../../releases/latest)** (a `.dmg` file)
2. Open the `.dmg` and **drag LED Raster Designer onto the Applications folder** shown in the window
3. Open **LED Raster Designer** from your Applications folder (or Launchpad)
   - **The first time**, macOS will say it can't check the app and won't open it.
     Click **Done**, then open **System Settings > Privacy & Security**, scroll
     down to **Security**, and click **Open Anyway** next to LED Raster Designer.
     Click **Open Anyway** again when asked and enter your Mac password. You only
     have to do this once.
4. When macOS asks, **allow it to access devices on your Local Network**. Your browser talks to the app over the network, so this is needed even on one computer
5. Your browser opens on the app, and you can start
6. Look for the 💡 in your menu bar to reopen the browser or quit

> **Why Applications matters:** macOS only shows the Local Network permission prompt for apps installed in `/Applications`. If you run it from the Downloads folder or directly from the disk image, the prompt never appears and the app can't be reached over your network. Always install it to Applications first.
>
> If you ever need them, logs live in **`~/Library/Logs/LED Raster Designer/`** (also reachable via the app's **Show Logs → Open Folder** button).

### Windows
1. **[Download the latest Windows release](../../releases/latest)**
2. Unzip the file
3. Double-click **LED Raster Designer.exe**
   - **The first time**, Windows may show "Windows protected your PC". Click
     **More info**, then **Run anyway**. You only have to do this once.
4. Your browser opens on the app, and you can start
5. Look for the lightbulb in your system tray (bottom-right) to reopen the browser or quit

### Using it from another computer

Anyone on the same network can use the app by opening `http://[your-ip]:8050`
in their browser. The exact address shows when the app starts.

---

## Your first wall

1. Click **Add Screen** and pick your cabinet from the catalog. Set how many
   cabinets wide and high the wall is.
2. The **Pixel Map** tab shows the layout your processor expects. Use
   **Show Look** to arrange the screens the way they sit on stage.
3. On the **Data** tab, click **Add Processor**, then drag its ports onto the
   wall. Pick a flow pattern or draw the runs by hand.
4. On the **Power** tab, click **+ Add distro** and drag its multis onto the
   wall. The amps on every leg add up as you go.
5. Open **File > Export Binder** for the drawing set, or **Export Pull Sheet**
   for the cable list.

Not sure where to start? **Help > Quick Start Guide** walks through all of
this on a demo show, one step at a time, and puts your own project back
when you're done.

---

## What it does

### Five views

| Tab | What it does |
|-----|-------------|
| **Pixel Map** | The layout your processor expects. Checkerboard and circle test patterns, cabinet borders, screen labels, blanks and half-tiles for non-rectangular walls. |
| **Cabinet ID** | Cabinet numbering in the style you choose (A1, 1,1, 01 and more). An id never leaves its cabinet. |
| **Show Look** | Rearrange the screens to match the stage. Pixel Map keeps the processor layout; Show Look drives the Data and Power views, so wiring and power maps read the way the show is built. |
| **Data** | Ports snaked across the wall in any of eight flow patterns or drawn by hand, wired to the processor, card and breakout box that carry them. |
| **Power** | Circuits across the wall the same way, wired to the distro and the multi that feed them, with the amps on every leg. |

### Screens

- A catalog of over 2,600 cabinets from 180 manufacturers, plus your own
  presets. The catalog updates itself from GitHub, and if a figure is wrong
  the app opens a pre-filled issue so it can be fixed.
- Put screens on as many **canvases** as you need, each with its own raster.
- **Group** screens built from different cabinet sizes and they act as one
  wall: one name, one set of totals, and runs that cross the seam.
- Blank cabinets and half tiles for walls that aren't rectangles.
- **Beaches** for the positions your show uses (SR, SL, upstage). The pull
  sheet and the binder follow their order.
- Image, logo and text layers, and multi-select to edit many screens at once.

### Data

- 62 processors from NovaStar, Brompton and Megapixel, with every figure
  taken from the maker's own specs.
- Drag ports, cards, breakout boxes or a whole processor onto a screen.
  Nothing is wired until you put it there, and a red flag on the tray counts
  what's still unattached.
- Redundancy is set in one place: whole processor, per card or per port. A
  backup processor is a single switch.
- Fiber to breakout boxes by the strand: TAC, MTP and opticalCON, with
  strands named by color.

### Power

- Build a distro from the outputs it really has: Socapex, L21-30, True1,
  powerCON, Edison and CEE, on US or EU power. Start from a preset or build
  your own.
- Every circuit is checked against its breaker, and US distros follow the
  80% rule. Balance spreads the multis across the legs for you.
- Drag a multi onto the wall and the circuits it will feed light up with
  the amps they add before you let go. Share circuits through a 2fer or 3fer.

### Cables

- Cable lengths in feet or meters, per show.
- A cable sheet for every multi and card, with a length and connector per
  circuit or port. Snake data ports under one home run.
- Jumper lengths for every screen, with long jumpers measured and rounded up
  to stock lengths.

### Paperwork

Click the red **Export** button, or pick an export from the **File** menu.
Everything saves straight to a file, with no print dialogs.

| Export | What you get |
|--------|-------------|
| **PNG / PDF / PSD** | Any of the five views, per canvas. One PNG per view, one PDF with a page per view, one PSD with a layer per screen, or with each screen's panels, borders, cabinet ids, data, power and name as separate layers in a group per screen. |
| **SVG** | Any view as vector artwork: labels as real text, cabinets and runs as shapes, grouped per screen and per element. Opens in Illustrator with everything editable, and in Photoshop as a smart object. |
| **Resolume XML** | Advanced Output screens, one per canvas, sized to its raster. |
| **Pull Sheet** | A filled copy of the shop's pull-sheet workbook: one block per beach, multis with their home runs, True1 by length, 2fers and 3fers, breakouts, snakes, extensions, barrels and jumpers. File > Pull Sheet edits the list in the app first. |
| **Binder** | One PDF as numbered sheets: overview, a Power and a Data sheet per screen with the wall, its circuits, ports, cables and facts, pull sheets, hardware. Tabloid by default, or Letter, ARCH C, ARCH D, A4, A3. Every sheet carries a border and a title block with your logo and a revision log. Tick Wiring and each map gets a wiring sheet behind it, every run drawn port to socket. Real text in the PDF, so it is sharp and searchable. Right-click a screen for Export this screen. |

### Preferences

Set a default for nearly everything you create: wall, look, data, power,
distros, the binder and the pull sheet. A default only applies to what you
make next, so it never changes a show you already have.

### Keyboard shortcuts

**Help > Keyboard Shortcuts** lists them all. The ones you'll use first:

| Shortcut | What it does |
|----------|-------------|
| **Cmd/Ctrl + Z**, **Cmd/Ctrl + Shift + Z** | Undo, redo. Every action is covered, including tray and distro edits. |
| **Cmd/Ctrl + O**, **Cmd/Ctrl + S** | Open, save a project |
| **Option/Alt + S**, **Cmd/Ctrl + Option/Alt + S** | Export PNG, export PSD |
| **Cmd/Ctrl + C / V**, **Cmd/Ctrl + J** | Copy, paste, duplicate a layer |
| **Cmd/Ctrl + Shift + 1**, **Cmd/Ctrl + Shift + 2** | Fit to view, zoom to selection at 1:1 |
| **Space + drag**, **scroll wheel** | Pan, zoom |
| **Shift + drag a screen** | Move it (in Show Look, its stage position) |
| **Alt + click a cabinet**, **Alt + Shift + click** | Blank it, make it a half-tile |
| **Hold Alt on a run** | Light it; Alt-click takes that port or circuit over for hand redrawing |
| **Tab / Shift + Tab** | Next, previous port or circuit in custom mode |

### Projects

- Shows save as `.json` files you can keep anywhere. **File > Recent Files**
  gets you back to them.
- A show from any earlier version opens and is brought up to date.
- The app checks for new releases and offers them from **Help**.

---

## Questions

**Does it need the internet?** No. It runs on your computer. When you're
online it checks for updates and refreshes the cabinet catalog.

**Is it really free?** Yes, including for paid shows. See [License](#license).

**Where are the logs?** **Help > Show Logs**. On a Mac they're also in
`~/Library/Logs/LED Raster Designer/`.

**Found a bug or want a feature?** Open an [issue](../../issues). For a bug,
attach the log from **Help > Show Logs > Copy**. For a feature, tell us how
you'd use it.

---

## Building from source

Most people should [download a release](../../releases/latest). To build the
app yourself you'll need **Python 3.10 or newer** from
[python.org](https://www.python.org/downloads/). On Windows, tick **Add Python
to PATH** during the install.

- **Mac:** open Terminal in the project folder and run `make mac`, then open
  **LED Raster Designer.app**. `make clean` removes the build files.
- **Windows:** double-click **Build Windows.bat**, then open
  **LED Raster Designer App\LED Raster Designer.exe**. Run
  `Build Windows.bat clean` from Command Prompt to remove the build files.

The source is in `src/`.

---

## License

LED Raster Designer is free to use for any lawful purpose, including paid shows and productions, and anything you make with it is yours. It is licensed under the LED Raster Designer License, a source-available license; see [LICENSE](LICENSE) for the full terms.

- You may not sell it, include it in paid software or a commercial product, or run it as a paid online service without a commercial license: contact kman1898@gmail.com.
- Forks are shared free, under the same license, say "Based on LED Raster Designer", and use a different name.
- Third-party components keep their own licenses; see [THIRD-PARTY-NOTICES](THIRD-PARTY-NOTICES).

---

## Contact

Questions and feedback are welcome as [issues](../../issues).
