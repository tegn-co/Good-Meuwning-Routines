"""Velkomst ved første oppstart: en kort gjennomgang med katten, og et lite oppsett til slutt
(arbeidstid, overtid man allerede har, påminnelser og om appen skal festes i oppgavelinja).
Kan vises igjen fra ⚙ → show tutorial.
"""
from gi.repository import Adw, Gio, GLib, Gtk

import db
import schedule
from cat import TitleCat

APP_DESKTOP = "no.zivid.MorgenTodo.desktop"

# (tittel over katten, kattens animasjon, tekst)
PAGES = [
    ("hi there", "walk",
     "Morning Routine is a small daily companion: a morning checklist, a plan for the day, "
     "hours and overtime, a pomodoro timer – and a cat.\n\nThis takes one minute."),
    ("your list", "sit",
     "Check things off as you go – the cat notices.\n\n"
     "Drag the number (01, 02 …) to change the order.\n\n"
     "Add your own items at the bottom of the list. They come back every day. "
     "Delete items under ⚙."),
    ("plan", "jump",
     "Write today's tasks in item 05, one per line, starting with a dash:\n\n"
     "    - fix the bug\n    - review PR\n\n"
     "Open plan ▸ to check them off. Unfinished tasks move to the next day."),
    ("hours", "eat",
     "Log your hours in the ⏱ field at the bottom. The overtime balance adds up for you.\n\n"
     "Weekends and days off (tick «day off») expect 0 hours. "
     "Forgot a day? Fix it under ⚙ → hours for another day."),
    ("more", "play",
     "pomo – a focus timer. The cat sleeps while you work and plays in the breaks.\n\n"
     "cat – breed, colors and what the cat says.\n\n"
     "⚙ – when the list opens, reminders, auto close and lunch."),
]


def on_gnome():
    source = Gio.SettingsSchemaSource.get_default()
    return bool(source and source.lookup("org.gnome.shell", True))


def pin_to_dock():
    """Legg appen til favorittene i GNOME/Ubuntu-docken (oppgavelinja)."""
    if not on_gnome():
        return False
    settings = Gio.Settings.new("org.gnome.shell")
    favorites = list(settings.get_strv("favorite-apps"))
    if APP_DESKTOP not in favorites:
        settings.set_strv("favorite-apps", favorites + [APP_DESKTOP])
    return True


def label(text, *classes):
    lbl = Gtk.Label(label=text, xalign=0, wrap=True)
    for c in classes:
        lbl.add_css_class(c)
    return lbl


def time_picker(hhmm):
    t = schedule.parse(hhmm)
    box = Gtk.Box(spacing=2, hexpand=True, halign=Gtk.Align.END)
    spins = []
    for value, top, step in ((t.hour, 23, 1), (t.minute - t.minute % 5, 55, 5)):
        spin = Gtk.SpinButton.new_with_range(0, top, step)
        spin.set_value(value)
        spin.set_wrap(True)
        spin.connect("output", lambda sp: sp.set_text(f"{int(sp.get_value()):02d}") or True)
        if spins:
            box.append(label(":", "detail"))
        box.append(spin)
        spins.append(spin)
    return box, lambda: f"{int(spins[0].get_value()):02d}:{int(spins[1].get_value()):02d}"


class Onboarding(Adw.Window):
    def __init__(self, parent, palette, on_done, opening=0.0):
        super().__init__(application=parent.get_application(), transient_for=parent, modal=True,
                         title="Welcome", default_width=420, default_height=560)
        self.on_done = on_done
        self.initial_opening = opening  # vist på nytt fra ⚙: behold det man har
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("bg")
        root.append(Adw.HeaderBar(show_title=False))

        self.carousel = Adw.Carousel(vexpand=True, allow_scroll_wheel=False)
        self.cats = []
        for title, anim, text in PAGES:
            self.carousel.append(self.page(palette, title, anim, label(text, "detail")))
        self.carousel.append(self.page(palette, "set up", "sit", self.setup_form()))
        self.carousel.connect("page-changed", self.on_page)
        root.append(self.carousel)

        nav = Gtk.Box(margin_start=24, margin_end=24, margin_bottom=18, spacing=8)
        self.back = Gtk.Button(label="back")
        self.back.add_css_class("pixel")
        self.back.connect("clicked", lambda _: self.go(-1))
        nav.append(self.back)
        nav.append(Adw.CarouselIndicatorDots(carousel=self.carousel, hexpand=True))
        self.next = Gtk.Button(label="next")
        self.next.add_css_class("pixel")
        self.next.add_css_class("go")
        self.next.connect("clicked", lambda _: self.go(1))
        nav.append(self.next)
        root.append(nav)
        self.set_content(root)
        self.on_page(self.carousel, 0)

    def page(self, palette, title, anim, content):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_start=24, margin_end=24, hexpand=True)
        cat = TitleCat(palette, forced=anim, title=title)
        self.cats.append(cat)
        box.append(cat)
        box.append(content)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, hexpand=True)
        scroll.set_child(box)
        return scroll

    def setup_form(self):
        sch = schedule.load()
        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        form.append(label("A few choices – everything can be changed later under ⚙.", "detail", "muted"))

        def row(text, widget):
            r = Gtk.Box(spacing=8)
            r.append(label(text, "detail"))
            widget.set_hexpand(True)
            widget.set_halign(Gtk.Align.END)
            r.append(widget)
            form.append(r)

        self.expected = Gtk.SpinButton.new_with_range(0, 24, 0.5)
        self.expected.set_digits(1)
        self.expected.set_value(db.EXPECTED_HOURS)
        row("normal work day (hours)", self.expected)
        self.opening = Gtk.SpinButton.new_with_range(-500, 500, 0.25)
        self.opening.set_digits(2)
        self.opening.set_value(self.initial_opening)
        row("overtime you already have (hours)", self.opening)

        self.morning_on = Gtk.CheckButton(label="open the list on weekdays at", active=sch["morning_on"])
        self.morning_on.add_css_class("detail")
        picker, self.morning_time = time_picker(sch["morning"])
        r = Gtk.Box(spacing=8)
        r.append(self.morning_on)
        r.append(picker)
        form.append(r)
        self.hours_on = Gtk.CheckButton(label="remind me to log hours at", active=sch["hours_on"])
        self.hours_on.add_css_class("detail")
        picker, self.hours_time = time_picker(sch["hours"])
        r = Gtk.Box(spacing=8)
        r.append(self.hours_on)
        r.append(picker)
        form.append(r)

        self.pin = Gtk.CheckButton(label="pin Morning Routine to the dock", active=True)
        self.pin.add_css_class("detail")
        self.pin.set_visible(on_gnome())
        form.append(self.pin)
        self.result = label("", "detail", "muted")
        form.append(self.result)
        return form

    def go(self, step):
        i = round(self.carousel.get_position()) + step
        n = self.carousel.get_n_pages()
        if i >= n:
            self.finish()
            return
        if 0 <= i < n:
            self.carousel.scroll_to(self.carousel.get_nth_page(i), True)

    def on_page(self, carousel, index):
        last = index == carousel.get_n_pages() - 1
        self.next.set_label("let's go!" if last else "next")
        self.back.set_sensitive(index > 0)

    def finish(self):
        expected = self.expected.get_value()
        sch = dict(schedule.load(), morning=self.morning_time(), morning_on=self.morning_on.get_active(),
                   hours=self.hours_time(), hours_on=self.hours_on.get_active())
        db.update_config(onboarded=True, expected_hours=expected)
        db.EXPECTED_HOURS = expected
        schedule.save(sch)
        problems = []
        try:
            schedule.apply_timers(sch)
        except Exception as e:  # noqa: BLE001 – f.eks. uten systemd; appen virker likevel
            problems.append(f"reminders: {e}")
        if self.pin.get_visible() and self.pin.get_active():
            try:
                pin_to_dock()
            except GLib.Error as e:
                problems.append(f"dock: {e.message}")
        opening = self.opening.get_value()
        self.on_done(opening if opening != self.initial_opening else None, sch, problems)
        self.close()
