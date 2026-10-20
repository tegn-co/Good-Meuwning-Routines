<p align="center">
  <img src="docs/banner.png" alt="GOOD MEUWNING – a morning checklist with a pixel cat" width="720">
</p>

<p align="center"><i>Dont forget you morning routines, and dont forget to feed you cat!</i></p>

---

**Morning Routine** is a tiny Linux desktop app that pops up every morning with your checklist,
helps you plan the day, keeps track of your hours and overtime, runs a pomodoro timer – and has a
pixel cat living on top of the title. The cat walks on the letters, hops over the spaces, naps,
eats lunch, chases butterflies and cheers when you check things off.

<img src="docs/cat-walk.png" alt="" width="120">

## What's inside

| | |
|---|---|
| ☀️ **Morning checklist** | Email, Jira, today's meetings, meeting prep and a plan for the day – plus your own routine items that come back every day. Drag the numbers to reorder; delete items under ⚙ (it asks twice). |
| 📝 **Plan for the day** | Write tasks as `- task` lines and check them off in the side panel. Unfinished tasks move to tomorrow. |
| ⏱ **Hours & overtime** | A reminder at 15:00 to log your hours; the overtime balance adds up for you. Weekends and days off expect 0 h, and you can fix past days under ⚙. |
| 🔥 **Streaks** | Finish the whole list several working days in a row – the cat notices and unlocks things to wear. |
| 🍅 **Pomodoro** | Focus timer with adjustable lengths. The cat sleeps while you work and plays in the breaks. |
| 🐈 **The cat** | Eight breeds including a fluffy Maine Coon, every color editable, and you decide what it says. |
| 🕗 **Your schedule** | Choose when the list opens, when you're reminded (and on which weekdays), when it saves & closes, and when the cat has lunch. |
| 💾 **Backup** | Export everything to one .zip, restore it later, and export your hours as CSV for your timesheet. |
| 🔄 **Updates** | The app tells you when a new version is out and updates itself with one click. |
| 🌗 **Light & dark** | Follows your system theme, or pick one. |
| 🇳🇴 **English & Norwegian** | Follows your system language, or pick one under ⚙. |

## Meet the cat

<table>
  <tr>
    <td align="center"><img src="docs/cat-walk.png" width="110"><br><sub><b>walk</b><br>strolls along the letters</sub></td>
    <td align="center"><img src="docs/cat-run.png" width="110"><br><sub><b>play</b><br>chases the cursor</sub></td>
    <td align="center"><img src="docs/cat-sleep.png" width="110"><br><sub><b>sleep</b><br>the letters breathe with it</sub></td>
    <td align="center"><img src="docs/cat-sit.png" width="110"><br><sub><b>sit</b><br>swats at the cursor</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/cat-butterfly.png" width="110"><br><sub><b>butterfly</b><br>pounces on a butterfly</sub></td>
    <td align="center"><img src="docs/cat-groom.png" width="110"><br><sub><b>groom</b><br>washes its paw</sub></td>
    <td align="center"><img src="docs/cat-stretch.png" width="130"><br><sub><b>stretch</b><br>a big morning stretch</sub></td>
    <td align="center"><img src="docs/cat-eat.png" width="130"><br><sub><b>eat</b><br>lunch – the bowl empties</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/cat-love.png" width="110"><br><sub><b>♥</b><br>click the title</sub></td>
    <td align="center" colspan="3"><sub><b>jump</b> – hops between the words · <b>climb</b> – walks around the window frame<br><br>
    Scroll the title away and the cat climbs into the frame to keep you company.<br>
    It yawns in the morning and gets sleepy after 16:00.</sub></td>
  </tr>
</table>

The animation changes every 15 minutes. Check something off and it says **good job!**

<p align="center"><img src="docs/accessories.png" alt="bow tie, coffee cup, beanie, Santa hat, ghost" width="560"><br>
<sub>bow tie (3 days in a row) · coffee cup (5) · beanie (10) · Santa hat in December · boo in Halloween week</sub></p>

<p align="center"><img src="docs/breeds.png" alt="orange tabby, grey tabby, black, tuxedo, calico, white, siamese, maine coon" width="720"><br>
<sub>orange tabby · grey tabby · black · tuxedo · calico · white · siamese · maine coon</sub></p>

<sub>Psst: try clicking the cat itself a few times in a row.</sub>

<img src="docs/divider.png" alt="" width="100%">

## Install

One command – downloads the latest release and installs it:

```sh
curl -fsSL https://raw.githubusercontent.com/tegn-co/Good-Meuwning-Routines/main/install.sh | sh
```

On **Ubuntu 24.04+ and Debian** it installs the .deb (apt fetches everything else and asks for your
password once). On **any other Linux** with [Flatpak](https://flatpak.org/setup/) it installs the
Flatpak. Then open **Morning Routine** from the app menu.

<details>
<summary>Prefer to do it by hand?</summary>

Download a file from the [latest release](https://github.com/tegn-co/Good-Meuwning-Routines/releases/latest):

```sh
sudo apt install ./morgen-todo_all.deb            # Ubuntu / Debian
flatpak install --user ./morgen-todo.flatpak      # any Linux with Flatpak
```

Or read [`install.sh`](install.sh) first – it only picks one of these and installs it.
</details>

### Updating

The .deb version checks for new releases once a day and shows a banner – click **update**, type your
password, restart. (You can turn the check off under ⚙.) For the Flatpak, or any time you like, just
run the install command again. Your data stays where it is.

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

| What | .deb | Flatpak |
|---|---|---|
| Checklist, plan, hours | `~/.local/share/morgen-todo/` | `~/.var/app/no.zivid.MorgenTodo/data/morgen-todo/` |
| Settings (work day, schedule, cat, theme) | `~/.config/morgen-todo/` | `~/.var/app/no.zivid.MorgenTodo/config/morgen-todo/` |

Under **⚙ → backup** you can export everything to a single .zip, restore it later (or on another
machine), and export your hours as CSV for your timesheet.

Want the database somewhere else, e.g. on a network drive? Set `"db_path"` in `config.json` (in the
settings folder above) or the `MORGEN_TODO_DB` environment variable. Network drives (CIFS/NFS/SSHFS)
are detected and handled automatically.

<img src="docs/divider.png" alt="" width="100%">

## For developers

<img src="docs/cat-eat.png" align="right" width="130" alt="">

Run from source:

```sh
python3 widget.py              # the app
python3 widget.py --cat=climb  # force an animation: walk, play, sleep, sit, jump, climb,
                               # butterfly, groom, stretch, eat
python3 docs/make_art.py       # regenerate the pixel art in this README
```

Run the tests (they use temporary folders and never touch your real data):

```sh
python3 -m unittest discover -s tests -t . -v
```

Release a new version – GitHub Actions runs the tests, builds the .deb and the .flatpak, checks that
both install, and publishes the release. Nothing is released if a test fails:

```sh
git tag v1.4.0 && git push origin v1.4.0
```

Or build the packages locally:

```sh
./packaging/build-deb.sh 1.4.0      # -> packaging/dist/morgen-todo_1.4.0_all.deb
flatpak-builder --user --install build packaging/flatpak/no.zivid.MorgenTodo.yml
```

| File | |
|---|---|
| `widget.py` | main window: list, plan, hours, settings, backup, updates |
| `cat.py` | the pixel cat, its animations, accessories and seasons |
| `cat_settings.py` | breed, colors, accessories and what the cat says |
| `pomodoro.py` | pomodoro panel |
| `db.py` | SQLite database, streaks, backup and CSV export |
| `schedule.py` | times for opening, reminders, auto close and lunch (systemd timers, or in-app for Flatpak) |
| `onboarding.py` | first-start tutorial and setup |
| `updates.py` | checks GitHub for new versions and installs them |
| `i18n.py` | English and Norwegian |
| `tests/` | unit and app tests |
| `packaging/` | .deb build script, Flatpak manifest, icon generator, fonts |
| `docs/` | README art |

Fonts: [Silkscreen](https://github.com/googlefonts/silkscreen) and
[JetBrains Mono](https://github.com/JetBrains/JetBrainsMono), both under the SIL Open Font License 1.1.

<p align="center"><img src="docs/cat-love.png" width="90" alt=""><br><sub>now go feed your cat</sub></p>
