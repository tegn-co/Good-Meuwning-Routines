"""Cat settings side panel (slides out like the plan and pomodoro panels).

Pick a breed, adjust each part's color (including the outline) and edit what the cat says.
Any look, Maine Coon shape or not, can be saved under a name and then shows up among the breeds.
An unsaved look ("custom") is kept while trying other breeds, and "random" makes up a new one.
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
        randomize = Gtk.Button(label=_("random"), tooltip_text=_("Give the cat a random look"))
        randomize.add_css_class("flat")
        randomize.connect("clicked", self.on_random)
        head.append(randomize)
        self.append(head)

        # --- Breed ---
        self.append(label("breed", "num"))
        self.breed = Gtk.DropDown()
        self.breed.connect("notify::selected", self.on_breed)
        self.append(self.breed)
        self.maine_coon = Gtk.CheckButton(label=_("maine coon"), tooltip_text=_("A bigger cat with ear tufts and a thick tail"))
        self.maine_coon.add_css_class("detail")
        self.maine_coon.connect("toggled", self.on_maine_coon)
        self.append(self.maine_coon)

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

        # --- Save the current look as a breed of its own ---
        row = Gtk.Box(spacing=6, margin_top=6)
        self.breed_name = Gtk.Entry(placeholder_text=_("name your cat"), hexpand=True)
        self.breed_name.connect("activate", self.on_save_breed)
        self.breed_name.connect("changed", lambda _e: self.breed_name.remove_css_class("error"))
        row.append(self.breed_name)
        save = Gtk.Button(label=_("save"), tooltip_text=_("Save these colors as a breed"))
        save.add_css_class("flat")
        save.connect("clicked", self.on_save_breed)
        row.append(save)
        self.delete_breed = Gtk.Button(label=_("delete"), tooltip_text=_("Delete this saved breed"))
        self.delete_breed.add_css_class("flat")
        self.delete_breed.connect("clicked", self.on_delete_breed)
        row.append(self.delete_breed)
        self.append(row)

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
        names = cat.breed_names()
        # Built-in breeds are translated; saved ones keep the name they were given
        shown = [_(b) for b in cat.BREEDS] + list(cat.CUSTOM_BREEDS) + [_("custom")]
        model = self.breed.get_model()
        if model is None or [model.get_string(i) for i in range(model.get_n_items())] != shown:
            self.breed.set_model(Gtk.StringList.new(shown))
        breed = cat.SETTINGS["breed"]
        self.breed.set_selected(names.index(breed) if breed in names else len(names))
        self.maine_coon.set_active(cat.SETTINGS["shape"] == "fluffy")
        self.delete_breed.set_visible(breed in cat.CUSTOM_BREEDS)
        self.breed_name.set_text(breed if breed in cat.CUSTOM_BREEDS else "")
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
        names = cat.breed_names()
        i = dropdown.get_selected()
        if i >= len(names):  # "custom": back to the look made here earlier
            if cat.restore_custom_look():
                self.show_current_settings()
                self.title_cat.say(_("{breed}!").format(breed=_("custom")))
                self.save_and_redraw()
            return
        cat.SETTINGS["breed"] = names[i]
        cat.COLORS.update(cat.breed_colors(names[i]))
        cat.set_shape(cat.breed_shape(names[i]))
        self.show_current_settings()
        self.title_cat.say(_("{breed}!").format(breed=_(names[i]) if names[i] in cat.BREEDS else names[i]))
        self.save_and_redraw()

    def became_custom(self):
        """The look no longer matches the chosen breed: show "custom" (the name is kept for saving it again)."""
        cat.SETTINGS["breed"] = "custom"
        cat.remember_custom_look()
        self.updating = True
        self.breed.set_selected(len(cat.breed_names()))
        self.delete_breed.set_visible(False)
        self.updating = False

    def on_color(self, btn, _, key):
        if self.updating:
            return
        cat.COLORS[key] = to_hex(btn.get_rgba())
        if (cat.breed_colors(cat.SETTINGS["breed"]) or {}).get(key) != cat.COLORS[key]:
            self.became_custom()
        self.save_and_redraw()

    def on_maine_coon(self, check):
        if self.updating:
            return
        cat.set_shape("fluffy" if check.get_active() else "normal")
        if cat.SETTINGS["breed"] == "custom" or cat.breed_shape(cat.SETTINGS["breed"]) != cat.SETTINGS["shape"]:
            self.became_custom()
        self.save_and_redraw()

    def on_save_breed(self, _widget):
        name = self.breed_name.get_text().strip()
        if not cat.save_custom_breed(name):
            self.breed_name.add_css_class("error")  # empty, or the name of a built-in breed
            return
        self.show_current_settings()
        self.title_cat.say(_("{breed}!").format(breed=name))
        self.title_cat.queue_draw()

    def on_delete_breed(self, _widget):
        cat.delete_custom_breed(cat.SETTINGS["breed"])
        self.show_current_settings()

    def on_random(self, _button):
        cat.random_look()
        self.show_current_settings()
        self.title_cat.say(_("new look!"))
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
