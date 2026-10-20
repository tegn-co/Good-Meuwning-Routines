"""Cat settings side panel (slides out like the plan and pomodoro panels).

Pick a breed, adjust each part's color (including the outline) and edit what the cat says.
The title cat updates immediately and serves as the preview.
Saved in ~/.config/morgen-todo/cat.json.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

import cat
from translations import _


def label(text, *classes):
    lbl = Gtk.Label(label=_(text), xalign=0, wrap=True)
    for c in classes:
        lbl.add_css_class(c)
    return lbl


def to_rgba(hexc):
    rgba = Gdk.RGBA()
    rgba.parse(hexc)
    return rgba


def to_hex(rgba):
    return "#{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in (rgba.red, rgba.green, rgba.blue)))


class CatPanel(Gtk.Box):
    def __init__(self, title_cat):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.title_cat = title_cat
        self.updating = False  # keeps programmatic changes from being saved as user choices

        head = Gtk.Box(margin_bottom=6)
        head.append(label("cat", "big"))
        reset = Gtk.Button(label=_("reset"), hexpand=True, halign=Gtk.Align.END,
                           tooltip_text=_("Back to orange tabby and default phrases"))
        reset.add_css_class("flat")
        reset.connect("clicked", self.on_reset)
        head.append(reset)
        self.append(head)

        # --- Breed ---
        self.append(label("breed", "num"))
        self.breed = Gtk.DropDown.new_from_strings([_(b) for b in cat.BREEDS] + [_("custom")])
        self.breed.connect("notify::selected", self.on_breed)
        self.append(self.breed)

        # --- Colors ---
        colors_title = label("colors", "num")
        colors_title.set_margin_top(10)
        self.append(colors_title)
        grid = Gtk.Grid(row_spacing=4, column_spacing=12)
        self.color_btns = {}
        for row, (key, name) in enumerate(cat.PARTS):
            grid.attach(label(name, "detail"), 0, row, 1, 1)
            btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False, title=_("Cat {part}").format(part=_(name))),
                                        hexpand=True, halign=Gtk.Align.END)
            btn.connect("notify::rgba", self.on_color, key)
            grid.attach(btn, 1, row, 1, 1)
            self.color_btns[key] = btn
        self.append(grid)

        # --- Accessories (unlocked by streaks) ---
        wear_title = label("accessories", "num")
        wear_title.set_margin_top(10)
        self.append(wear_title)
        self.append(label("Unlocked by finishing the whole list several working days in a row.", "detail", "muted"))
        self.wear_checks = {}
        for key, days, name in cat.UNLOCKS:
            cb = Gtk.CheckButton(label=_(name))
            cb.add_css_class("detail")
            cb.connect("toggled", self.on_wear, key)
            self.append(cb)
            self.wear_checks[key] = (cb, days, name)
        self.refresh_wear()

        # --- Phrases ---
        phrases_title = label("what the cat says", "num")
        phrases_title.set_margin_top(10)
        self.append(phrases_title)
        self.append(label("Separate options with | to pick one at random. Leave empty for just a ♥.", "detail", "muted"))
        self.phrase_entries = {}
        for key, when in cat.EVENTS:
            self.append(label(_("when {event}").format(event=_(when)), "detail", "muted"))
            entry = Gtk.Entry()
            entry.connect("changed", self.on_phrase, key)
            self.append(entry)
            self.phrase_entries[key] = entry

        self.show_current_settings()

    def show_current_settings(self):
        self.updating = True
        names = list(cat.BREEDS)
        breed = cat.SETTINGS["breed"]
        self.breed.set_selected(names.index(breed) if breed in names else len(names))
        for key, btn in self.color_btns.items():
            btn.set_rgba(to_rgba(cat.COLORS[key]))
        for key, entry in self.phrase_entries.items():
            entry.set_text(cat.PHRASES[key])
        self.updating = False

    def refresh_wear(self):
        """Show what is unlocked (also called by the window when the streak changes)."""
        self.updating = True
        for key, (cb, days, name) in self.wear_checks.items():
            unlocked = key in cat.UNLOCKED
            cb.set_sensitive(unlocked)
            cb.set_label(_(name) if unlocked else _("{name} – {days} days in a row").format(name=_(name), days=days))
            cb.set_active(unlocked and cat.SETTINGS.get("wear", {}).get(key, True))
        self.updating = False

    def on_wear(self, cb, key):
        if self.updating:
            return
        cat.SETTINGS.setdefault("wear", {})[key] = cb.get_active()
        self.save_and_redraw()

    def save_and_redraw(self):
        cat.save_cat_settings()
        self.title_cat.queue_draw()

    def on_breed(self, dropdown, _pspec):
        if self.updating:
            return
        names = list(cat.BREEDS)
        i = dropdown.get_selected()
        if i >= len(names):  # "custom" is selected automatically when a color changes
            return
        cat.SETTINGS["breed"] = names[i]
        cat.COLORS.update(cat.BREEDS[names[i]])
        cat.set_shape(cat.BREED_SHAPES.get(names[i], "normal"))
        self.show_current_settings()
        self.title_cat.say(_("{breed}!").format(breed=_(names[i])))
        self.save_and_redraw()

    def on_color(self, btn, _, key):
        if self.updating:
            return
        cat.COLORS[key] = to_hex(btn.get_rgba())
        if cat.BREEDS.get(cat.SETTINGS["breed"], {}).get(key) != cat.COLORS[key]:
            cat.SETTINGS["breed"] = "custom"
            self.updating = True
            self.breed.set_selected(len(cat.BREEDS))
            self.updating = False
        self.save_and_redraw()

    def on_phrase(self, entry, key):
        if self.updating:
            return
        cat.PHRASES[key] = entry.get_text()
        self.save_and_redraw()

    def on_reset(self, _):
        cat.SETTINGS["breed"] = "orange tabby"
        cat.COLORS.update(cat.BREEDS["orange tabby"])
        cat.set_shape("normal")
        cat.PHRASES.update(cat.DEFAULT_PHRASES)
        self.show_current_settings()
        self.save_and_redraw()
