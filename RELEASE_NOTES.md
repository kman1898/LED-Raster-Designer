# LED Raster Designer v0.10.9

Screen groups: a wall built from more than one cabinet size now behaves as a single
screen. Plus corrected capacity figures and a number of fixes worth reading if you
have drawings already out.

## What's new

The headline of this release.

- **Screen groups** — You can now group screens, so a wall built from more than one cabinet
  size behaves as a single screen. If your crew owns 1m x 1m panels and 0.5m x 0.5m panels
  and hangs them on the same wall, you have had to draw them as two screens, because one
  screen uses one cabinet size all the way through. The wall was one wall, but the app
  treated it as two - two names on the drawing, two sets of totals to add up in your head,
  two things to drag, and cabinet numbers that started again halfway across. To make a
  group: select the screens that make up the wall - click one, then Shift-click or
  Cmd/Ctrl-click the rest - then right-click and choose "Group Screens". To take one apart,
  right-click and choose "Ungroup Screens". To drop a single screen out and leave the rest
  grouped, use "Remove From Group". Once grouped:
  - Cabinets, weight, watts, amps, ports and circuits add up across the whole group. Each
    screen keeps its own cabinet weight and wattage, so a 1m x 1m cabinet and a 0.5m x 0.5m
    cabinet are never assumed to weigh the same.
  - The drawing shows one name and one set of figures, and dragging any part of the group
    moves all of it.
  - Cabinet IDs run straight through the group instead of restarting on each screen,
    numbered by where each cabinet actually sits.
  - Exports treat it as one screen: one shape in the Resolume XML named for the group, one
    Photoshop layer, and a group that happens to form a rectangle exports as a plain
    rectangle.

  A group can hold any number of screens - two, or a dozen - and you can keep as many groups
  as you like in a project. Screens in a group need to agree on processor, bit depth and
  frame rate. If they do not when you group them, the app tells you which settings differ
  and lets you pick one value to apply to the whole group.

- **Screen groups** — Draw a data port or a power circuit straight across a group. In custom
  mode, click cabinets in any screen and they all join the same port - the line draws
  through the join, the "on port" count includes the cabinets on the far side, and a
  colour-coded circuit tints every cabinet on it. When you reach the edge of a screen, the
  arrow keys carry on into the next one and find the cabinet that is physically next door,
  even where the two screens use different cabinet sizes. A cabinet already wired to another
  port is still refused, now across the whole group, and the message tells you which screen
  it is wired to - "port 1 on Upper Wall" - because a cabinet reference on its own is
  ambiguous once two grids are in play.

- **Screen groups** — Drag-select across a whole group and apply a flow pattern to it.
  Serpentine and the other patterns follow where each cabinet physically sits, so a run
  across a 1m x 1m screen and a 0.5m x 0.5m screen snakes across the group in the order you
  would walk it. The two screens' grids do not line up when the cabinet sizes differ, and
  the pattern no longer pretends they do.

- **Low latency** — Low Latency is now a tickbox on any screen, instead of being buried as a
  separate "Brompton Tessera (ULL)" entry in the processor list. Tick it and the app applies
  what your processor actually does:
  - Brompton: halves the pixels per port, matching Brompton's own published Ultra Low
    Latency figures. (ULL is an SX40/S8 feature; HDMI in, no SDI.)
  - Megapixel HELIOS: pixels per port are unchanged - HELIOS low latency costs daisy-chain
    length, not bandwidth.
  - NovaStar, legacy and COEX: ports have to run vertically and start at the top of the
    canvas. A port starting lower down loses capacity in proportion, so you get fewer
    cabinets on that port and the app tells you why. Confirmed directly with NovaStar, who
    also confirmed the old 512-pixel port width limit is gone on current firmware - the
    published manuals are out of date and are being revised. You need a receiving card that
    supports it; MRV328 and MRV336 do not.

- **Low latency** — Ticking Low Latency lists the rules it is applying, under the
  Pixels/Port readout, for whichever processor that screen is set to. Brompton tells you
  pixels per port is halved. Megapixel tells you pixels per port are unchanged but the daisy
  chain is halved. NovaStar lists the vertical and top-of-canvas requirement, what a port
  starting lower costs you, and which receiving cards cannot do it. NovaStar 5G adds the
  128-pixel narrow-port rule. They sit under that readout because Pixels/Port is a
  whole-screen figure and cannot show you what an individual port costs.

- **Port mapping** — Port Mapping now works on NovaStar (Legacy). "Organized" and "Max
  Capacity" were both greyed out on Legacy screens. That processor reserves a pixel
  rectangle around each port, and only Organized knew about it; Max Capacity now does the
  same maths, so both modes work and every port stays inside its limit. This matters most on
  wide walls: a screen whose full row was too big for one port could not be mapped at all
  before - it just showed a capacity error - and Max Capacity can now split it into ports
  that work. The rectangle rule applies only to NovaStar (Legacy). COEX 1G/5G, Brompton,
  Brompton ULL and Megapixel HELIOS are unchanged.

- **Capacity figures** — NovaStar 5G narrow ports are now costed properly. NovaStar reserve
  a band at least 128 pixels wide per Ethernet port, so a port narrower than that wastes the
  rest of the band and carries less than the headline pixels-per-port figure - a port 120 px
  wide loses (128 - 120) x its height. NovaStar 5G only. It bites hardest on tall narrow
  ports, which is exactly the shape low latency encourages, and it can be the difference
  between a port that works and one that is quietly overloaded.

## Changes worth knowing about

Behaviour that is deliberately different from the last version.

- **Totals & shapes** — Frame rates are now limited to the ones your processor actually
  publishes a figure for. The list used to offer the same 19 rates to everything, and
  NovaStar publish nothing at 48, 72, 100, 150, 180, 192 or 200 Hz - so the app was
  estimating between the rates either side and coming out as much as 11% HIGH at 100 Hz. Too
  high means too few ports. If you open a project set to a rate its processor does not
  publish, the screen drops to the nearest published rate BELOW it and tells you so. Your
  port count will change. Brompton is unaffected - it publishes every rate the app offers.

- **Export & Windows** — On Windows the app now clears the "downloaded from the internet"
  tag from its own files on first run, so nothing has to be unblocked by hand. Windows puts
  that tag on everything extracted from a downloaded zip. Being straight with you: we first
  thought that tag was what stopped the app opening in its own window on one tester's PC,
  and we tested it - a fully tagged copy started normally, so that was not the cause. The
  tag is cleared anyway because it costs nothing and is what an installer would have done.
  If the app still opens in a browser instead of its own window, please send a log (Help >
  Show Logs); this build records what we need to find the real cause. Nothing about your
  antivirus or Windows security changes.

- **Port mapping** — Opening an older project with "Max Capacity" saved on a Legacy screen
  switches it to "Organized". That is what it was really drawing before
  - the setting was being ignored - so maps you have already issued keep

  rendering exactly as they are. Choosing Max Capacity yourself from now on sticks,
  including through undo.

## Fixes that change numbers on drawings you already have

These correct figures you may have already read off a drawing and ordered against. Worth a
minute before your next show.

- **Export & Windows** — Export now asks where to put the files when you are on the machine
  running the app, even when you reach it at its network address. The launcher lets you
  serve the app on your network so another machine can open the drawing. When you did that,
  YOUR OWN browser also reached it at that address - and the app could not tell that apart
  from a laptop across the room, so it treated you as a remote viewer and quietly sent the
  files to your downloads folder with no way to choose a folder. A machine connected over
  the network still downloads to itself, which is what you want - it just does not get asked
  where, because browsers only offer a folder chooser over a secure connection.

- **Totals & shapes** — A wall with a GAP in it exported as one solid rectangle straight
  over the gap. Two screens with air between them, or one screen split in two by hidden
  cabinets, traced only one side and shipped it as a plain rectangle - so content was mapped
  across the hole, both screens landed shifted, and anything in the gap went to the floor.
  Each separate piece of wall now exports as its own shape, at its own position.

- **Totals & shapes** — A blanked cabinet now changes the exported shape on ANY screen. It
  already did inside a group, but a screen on its own still shipped a full rectangle - so
  the same wall gave two different files depending on whether anyone had pressed Group
  Screens.

- **Totals & shapes** — Project totals no longer blend screens running on different voltages
  into one figure. A project with a 110 V wall and a 208 V wall took whichever voltage it
  happened to see first and divided EVERY screen's watts by it, so the amps belonged to
  neither wall. Each voltage is now reported on its own line. A project can of course hold
  walls on different supplies - that is normal - but screens grouped into one wall now have
  to agree on voltage, the same way they agree on processor and bit depth.

- **Totals & shapes** — The project circuit total was worked out by dividing total watts by
  the watts a circuit carries, which ignores how circuits actually pack along rows and
  columns. It read 2 circuits where the map you drew needs 3. It now counts the map. The
  same readout also ignored hand-drawn power and port maps entirely, showing the automatic
  figure instead of what you drew.

- **Capacity figures** — Corrected the NovaStar 5G pixels-per-port figures against
  NovaStar's published Ethernet Port Load Capacity table. Their calculation multiplies by 24
  / 32 / 48 for 8 / 10 / 12-bit; ours used 36 at 12-bit, which overstated 12-bit capacity by
  about 17% and under-counted the ports a screen needs. 12-bit at 60 Hz drops from 1,728,000
  to 1,475,600 per port. 8-bit and 10-bit go up (2,592,000 to 2,951,200 at 8-bit/60 Hz).
  Your 5G screens will show different port counts than before. These are NovaStar's
  published numbers. Projects saved as "Brompton Tessera (ULL)" open as Brompton with Low
  Latency ticked. 46 of the 48 old figures come out identical. The other two differ by a
  single pixel per port, because halving an odd published figure rounds down: 12-bit at 144
  Hz reads 72,916 where the old table said 72,917, and at 192 Hz 54,687 where it said
  54,688. One pixel in roughly 73,000 cannot change how many cabinets fit on a port, so no
  real screen moves - but the two numbers are not identical and it would be wrong to say
  they were.

- **Capacity figures** — Corrected the Megapixel HELIOS pixels-per-port figures. Ours came
  from Megapixel's older switch spec sheets and were up to 6% higher than the current
  official HELIOS User Guide. Too high is the dangerous direction, because it under-counts
  how many ports a screen needs. 40 of the 44 figures were affected, the worst at 60 Hz -
  the most common show frame rate - where 12-bit 1G read 425,000 pixels per port against an
  official 401,000. Both HELIOS entries now match the published table. Your HELIOS projects
  may show slightly more ports required than before. That is the correct number.

- **Export** — The Resolume XML export now follows the real shape of your screen. It worked
  out where each cabinet sat by multiplying rows and columns by the full cabinet size, so
  half tiles were ignored completely: a wall with a half-height bottom row exported a shape
  a whole cabinet too tall, and a half-width edge column one too wide. It now traces the
  actual cabinets. A plain rectangular wall exports exactly as before; anything else exports
  a polygon that follows only where cabinets really are. Blanked cabinets are left out too,
  matching the cabinet, weight and power totals, which have always ignored them.

## Other fixes

Everything else that was wrong and now is not.

- **Screen groups** — Drag-select in Power now lights up the cabinets as you drag, the way
  Data always has. In Power you saw nothing at all until you let go of the button, so you
  were picking a box blind and only finding out what you had caught once it was too late to
  adjust. Both views now behave the same.

- **Export & Windows** — Cancelling the folder chooser now cancels. It used to save
  everything to your downloads folder anyway.

- **Export & Windows** — If the folder chooser cannot open at all, the files still get saved
  - to your downloads folder - and the app says so instead of leaving you to work it out.
  The reason is written to the log.

- **Export & Windows** — Arrow keys now walk the cable the way you press them in Rear view.
  Right went left and left went right, because the drawing is mirrored in Rear view and the
  keys were not. Up and down were always correct and still are. (Reported as issue #111.)

- **Export & Windows** — The app log can no longer be read or erased by another machine on
  the network, and only the machine running the app can open the log folder.

- **Export & Windows** — Gradients no longer disappear when you reload. Everything in the
  Gradient panel - the colour stops and where they sit, plus type, angle, opacity, blend and
  scope - was being held on screen but never written into the drawing. Reload the page, or
  close and reopen the window, and the gradient came back the way it was at your last save
  with everything since gone. Panel colours, Transparent Fill, and the screen name position
  on the Pixel Map and Show Look tabs were lost the same way. Saving the project or pressing
  undo writes the whole drawing at once, so either of those healed it by accident - which is
  why this came and went instead of failing every time. Files you had already saved were
  never affected; the settings just never reached the drawing in the first place.

- **Export & Windows** — Duplicating or pasting a screen no longer loses the copy's
  gradient. Duplicate looked right on screen but never wrote the copy's gradient, panel
  colours or Transparent Fill into the drawing, so the copy came back plain after a reload.
  Paste dropped them straight away - a pasted screen has been arriving plain for some time.
  Copy/Paste and Duplicate now give you the same screen.

- **Export & Windows** — A gradient stop no longer jumps back on its own. Moving one stop
  and then moving another straight after could send the first one back where it started,
  because the app was still finishing the first change. Undo recorded the jumped-back
  position too, so stepping back walked you through gradients you never chose.

- **Totals & shapes** — An "&" in a screen or group name produced a file Resolume could not
  open at all. "Left & Right" is a perfectly normal wall name.

- **Totals & shapes** — Drag-select now lands on the cabinet you pointed at on a ROTATED
  screen. The highlight was worked out as if the screen were not rotated and then drawn
  rotated, so it sat a cabinet or more away from the one under your cursor - the more
  rotation, the further out it was.

- **Totals & shapes** — Redo after undoing a Delete Screen did not delete it again.

- **Totals & shapes** — Cabinet borders and label colour each took TWO undos to reverse one
  click, so the first Ctrl+Z appeared to do nothing.

- **Port mapping** — The highlight now moves when you pick a Port Mapping mode. Clicking
  "Max Capacity" changed the setting, but "Organized" stayed lit, so there was no way to see
  which mode you were actually using.

- **General** — Drag-select on a rotated screen now selects the cabinets under the box,
  rather than the ones the box would have covered if the screen were not rotated. Pixel Map
  already worked this way; Data and Power did not.

- **General** — A screen missing its fill colours no longer blanks the whole canvas. One
  malformed screen used to take the entire drawing down with it instead of just itself.

- **General** — The Data and Power flow-pattern grids highlighted the wrong tile on a fresh
  project. Data lit "top-right, vertical first" and Power lit nothing at all, when both
  actually default to "top-left, horizontal first". They now show the pattern really in use.

- **General** — A batch of controls that were showing the wrong state, all from the same
  cause:
  - Sliders were drawn as empty bars; they show their coloured fill again.
  - The colour picker's red/green/blue and hue/saturation sliders were flat grey, so you
    could not see the colour you were dragging through. Their ramps are back.
  - The primary screen in a multi-selection had no highlight.
  - Hidden screens lost their red striped look in the screen list.
  - Greyed-out buttons looked clickable: the up/down reorder arrows on the selected screen,
    and the Remove buttons for gradient stops and palette colours. Disabled buttons look
    disabled everywhere now.
  - Renaming a screen or a canvas gave no sign you were editing.
  - An invalid Watts-per-Panel entry showed no warning outline while the field was still
    focused - exactly when you would be looking at it.
  - Bold / Italic / Underline stayed blue instead of following your accent colour, and the
    Pixels/Port and Panels/Port readouts could not show their normal colour at all.

## Install

**macOS** — download the `.dmg` and drag the app to Applications.  
**Windows** — download the `.zip`, extract it, then run `LED Raster Designer.exe`.

SHA-256 checksums for both files are attached as `checksums.txt`.
