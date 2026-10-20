<p align="center">
  <img src="docs/banner.png" alt="GOOD MEUWNING – a morning checklist with a pixel cat" width="720">
</p>

<p align="center"><i>Dont forget you morning routines, and dont forget to feed you cat!</i></p>

---

**Morning Routine** is a tiny desktop app for Ubuntu that pops up every morning with your checklist,
helps you plan the day, keeps track of your hours and overtime, runs a pomodoro timer – and has a
pixel cat living on top of the title. The cat walks on the letters, hops over the spaces, naps,
eats lunch, chases the cursor and cheers when you check things off.

<img src="docs/cat-walk.png" alt="" width="120">

## What's inside

| | |
|---|---|
| ☀️ **Morning checklist** | Email, Jira, today's meetings, meeting prep and a plan for the day – plus your own routine items that come back every day. Drag the numbers to reorder. |
| 📝 **Plan for the day** | Write tasks as `- task` lines and check them off in the side panel. Unfinished tasks move to tomorrow. |
| ⏱ **Hours & overtime** | Log your hours at 15:00; the overtime balance adds up for you. Weekends and days off count as 0 h expected. |
| 🍅 **Pomodoro** | Focus timer with adjustable lengths. The cat sleeps while you work and plays in the breaks. |
| 🐈 **The cat** | Seven breeds (plus a fluffy Maine Coon), every color editable, and you decide what it says. |
| 🕗 **Your schedule** | Choose when the list opens, when you're reminded, which weekdays, when it saves & closes, and when the cat has lunch. |
| 🌗 **Light & dark** | Follows your system theme, or pick one. |

## Meet the cat

<table>
  <tr>
    <td align="center"><img src="docs/cat-walk.png" width="110"><br><sub><b>walk</b><br>strolls along the letters</sub></td>
    <td align="center"><img src="docs/cat-run.png" width="110"><br><sub><b>play</b><br>chases the cursor</sub></td>
    <td align="center"><img src="docs/cat-sleep.png" width="110"><br><sub><b>sleep</b><br>the letters breathe with it</sub></td>
    <td align="center"><img src="docs/cat-sit.png" width="110"><br><sub><b>sit</b><br>swats at the cursor</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/cat-eat.png" width="130"><br><sub><b>eat</b><br>lunch – the bowl empties</sub></td>
    <td align="center"><img src="docs/cat-love.png" width="110"><br><sub><b>♥</b><br>click the title</sub></td>
    <td align="center" colspan="2"><sub><b>jump</b> – hops between the words<br><b>climb</b> – walks around the window frame<br><br>Scroll the title away and the cat climbs<br>into the frame to keep you company.</sub></td>
  </tr>
</table>

It also chases butterflies, washes, stretches, yawns in the morning and gets sleepy after 16:00.
The animation changes every 15 minutes. Check something off and it says **good job!**

Finish your whole list several working days in a row and the cat unlocks things to wear –
a bow tie, a coffee cup and a beanie. In December it wears a Santa hat, and in Halloween week… boo.

<sub>Psst: try clicking the cat itself a few times in a row.</sub>

<p align="center"><img src="docs/breeds.png" alt="orange tabby, grey tabby, black, tuxedo, calico, white, siamese, maine coon" width="720"><br>
<sub>orange tabby · grey tabby · black · tuxedo · calico · white · siamese · maine coon</sub></p>

<img src="docs/divider.png" alt="" width="100%">

## Install

One command – downloads the latest release and installs it:

```sh
curl -fsSL https://raw.githubusercontent.com/tegn-co/Good-Meuwning-Routines/main/install.sh | sh
```

Then open **Morning Routine** from the app menu. Run the same command again to update –
your data stays where it is.

<details>
<summary>Prefer to do it by hand?</summary>

Download `morgen-todo_all.deb` from the [latest release](https://github.com/tegn-co/Good-Meuwning-Routines/releases/latest)
and run:

```sh
sudo apt install ./morgen-todo_all.deb
```

Or read [`install.sh`](install.sh) first – it only downloads the .deb and runs `apt install`.
</details>

Requires Ubuntu 24.04 or newer (GTK ≥ 4.12, libadwaita ≥ 1.4). apt installs everything else.

### First start

<img src="docs/cat-sit.png" align="right" width="110" alt="">

A short tutorial walks you through the app (with the cat, of course) and asks:

- how long your normal work day is
- how much overtime you already have
- when the list should open and when to remind you about hours
- whether to **pin Morning Routine to the dock**

Everything can be changed later under **⚙**, and the tutorial is there too.

## Your data stays yours

Every user starts with a fresh, local database – nothing is shared or uploaded.

| What | Where |
|---|---|
| Checklist, plan, hours | `~/.local/share/morgen-todo/morgen-todo.db` |
| Settings (work day, schedule, cat, theme) | `~/.config/morgen-todo/` |

Want the database somewhere else, e.g. on a network drive? Set `"db_path"` in
`~/.config/morgen-todo/config.json` or the `MORGEN_TODO_DB` environment variable.
Network drives (CIFS/NFS/SSHFS) are detected and handled automatically.

<img src="docs/divider.png" alt="" width="100%">

## For developers

<img src="docs/cat-eat.png" align="right" width="130" alt="">

Run the tests (they use temporary folders and never touch your real data):

```sh
python3 -m unittest discover -s tests -t . -v
```

Release a new version – GitHub Actions runs the tests, builds the .deb and publishes the release:

```sh
git tag v1.0.1 && git push origin v1.0.1
```

Or build the package locally:

```sh
./packaging/build-deb.sh 1.0.0      # -> packaging/dist/morgen-todo_1.0.0_all.deb
```

Run from source:

```sh
python3 widget.py              # the app
python3 widget.py --cat=climb  # force an animation: walk, play, sleep, sit, jump, climb, eat
python3 docs/make_art.py       # regenerate the pixel art in this README
```

| File | |
|---|---|
| `widget.py` | main window: list, plan, hours, settings |
| `cat.py` | the pixel cat and the title animations |
| `cat_settings.py` | breed, colors and what the cat says |
| `pomodoro.py` | pomodoro panel |
| `db.py` | SQLite database |
| `schedule.py` | times for opening, reminders, auto close and lunch |
| `onboarding.py` | first-start tutorial and setup |
| `packaging/` | .deb build script, icon generator, fonts |
| `docs/` | README art |

Fonts: [Silkscreen](https://github.com/googlefonts/silkscreen) and
[JetBrains Mono](https://github.com/JetBrains/JetBrainsMono), both under the SIL Open Font License 1.1.

<p align="center"><img src="docs/cat-love.png" width="90" alt=""><br><sub>now go feed your cat</sub></p>
