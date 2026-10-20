"""Katteinnstillinger for morgen-todo-vinduet (glir ut fra siden, som plan- og pomodoro-panelet).

Velg rase, juster fargen på hver del av katten (også konturen), og endre hva katten sier.
Katten i tittelen oppdateres med en gang, så den fungerer som forhåndsvisning.
Alt lagres i ~/.config/morgen-todo/cat.json.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

import cat


def label(text, *classes):
    lbl = Gtk.Label(label=text, xalign=0, wrap=True)
    for c in classes:
        lbl.add_css_class(c)
    return lbl


def to_rgba(hexc):
    rgba = Gdk.RGBA()
    rgba.parse(hexc)
    return rgba


def to_hex(rgba):
    return "#{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in (rgba.red, rgba.green, rgba.blue)))


class CatSettings(Gtk.Box):
    def __init__(self, title_cat):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.title_cat = title_cat
        self.updating = False  # hindrer at programmatiske endringer lagres som egne valg

        head = Gtk.Box(margin_bottom=6)
        head.append(label("cat", "big"))
        reset = Gtk.Button(label="reset", hexpand=True, halign=Gtk.Align.END, tooltip_text="Back to orange tabby and default phrases")
        reset.add_css_class("flat")
        reset.connect("clicked", self.on_reset)
        head.append(reset)
        self.append(head)

        # --- Rase ---
        self.append(label("breed", "num"))
        self.breed = Gtk.DropDown.new_from_strings(list(cat.BREEDS) + ["custom"])
        self.breed.connect("notify::selected", self.on_breed)
        self.append(self.breed)

        # --- Farger ---
        colors_title = label("colors", "num")
        colors_title.set_margin_top(10)
        self.append(colors_title)
        grid = Gtk.Grid(row_spacing=4, column_spacing=12)
        self.color_btns = {}
        for row, (key, name) in enumerate(cat.PARTS):
            grid.attach(label(name, "detail"), 0, row, 1, 1)
            btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False, title=f"Cat {name}"),
                                        hexpand=True, halign=Gtk.Align.END)
            btn.connect("notify::rgba", self.on_color, key)
            grid.attach(btn, 1, row, 1, 1)
            self.color_btns[key] = btn
        self.append(grid)

        # --- Replikker ---
        phrases_title = label("what the cat says", "num")
        phrases_title.set_margin_top(10)
        self.append(phrases_title)
        self.append(label("Separate options with | to pick one at random. Leave empty for just a ♥.", "detail", "muted"))
        self.phrase_entries = {}
        for key, when in cat.EVENTS:
            self.append(label(f"when {when}", "detail", "muted"))
            entry = Gtk.Entry()
            entry.connect("changed", self.on_phrase, key)
            self.append(entry)
            self.phrase_entries[key] = entry

        self.load_into_ui()

    def load_into_ui(self):
        self.updating = True
        names = list(cat.BREEDS)
        breed = cat.SETTINGS["breed"]
        self.breed.set_selected(names.index(breed) if breed in names else len(names))
        for key, btn in self.color_btns.items():
            btn.set_rgba(to_rgba(cat.COLORS[key]))
        for key, entry in self.phrase_entries.items():
            entry.set_text(cat.PHRASES[key])
        self.updating = False

    def changed(self):
        cat.save_cat_settings()
        self.title_cat.queue_draw()

    def on_breed(self, dropdown, _):
        if self.updating:
            return
        names = list(cat.BREEDS)
        i = dropdown.get_selected()
        if i >= len(names):  # «custom» velges automatisk når du endrer en farge
            return
        cat.SETTINGS["breed"] = names[i]
        cat.COLORS.update(cat.BREEDS[names[i]])
        cat.set_shape(cat.BREED_SHAPES.get(names[i], "normal"))
        self.load_into_ui()
        self.title_cat.say(names[i] + "!")  # liten bekreftelse fra katten
        self.changed()

    def on_color(self, btn, _, key):
        if self.updating:
            return
        cat.COLORS[key] = to_hex(btn.get_rgba())
        if cat.BREEDS.get(cat.SETTINGS["breed"], {}).get(key) != cat.COLORS[key]:
            cat.SETTINGS["breed"] = "custom"
            self.updating = True
            self.breed.set_selected(len(cat.BREEDS))
            self.updating = False
        self.changed()

    def on_phrase(self, entry, key):
        if self.updating:
            return
        cat.PHRASES[key] = entry.get_text()
        self.changed()

    def on_reset(self, _):
        cat.SETTINGS["breed"] = "orange tabby"
        cat.COLORS.update(cat.BREEDS["orange tabby"])
        cat.set_shape("normal")
        cat.PHRASES.update(cat.DEFAULT_PHRASES)
        self.load_into_ui()
        self.changed()
