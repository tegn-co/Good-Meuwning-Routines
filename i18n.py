"""Norsk og engelsk. Engelsk er grunnspråket i koden; _("tekst") gir den norske utgaven når språket er norsk.

Språket velges under ⚙ → language (lagres som "language" i config.json). Er ingenting valgt,
brukes systemspråket: nb/nn/no gir norsk, alt annet engelsk. Endring krever omstart.
"""
import os

import db

LANGUAGES = [("en", "English"), ("nb", "Norsk")]


def detect():
    chosen = db.load_config().get("language")
    if chosen in dict(LANGUAGES):
        return chosen
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return "nb" if value[:2] in ("nb", "nn", "no") else "en"
    return "en"


LANG = detect()


def _(text):
    return NB.get(text, text) if LANG == "nb" else text


NB = {
    # --- tittel, dato ---
    "good morning": "god morgen",
    "monday": "mandag", "tuesday": "tirsdag", "wednesday": "onsdag", "thursday": "torsdag",
    "friday": "fredag", "saturday": "lørdag", "sunday": "søndag",
    "january": "januar", "february": "februar", "march": "mars", "april": "april", "may": "mai",
    "june": "juni", "july": "juli", "august": "august", "september": "september",
    "october": "oktober", "november": "november", "december": "desember",
    # --- listen ---
    "Check email": "Sjekk e-post",
    "Reply to anything urgent, flag the rest": "Svar på det som haster, flagg resten",
    "Add new tasks to today's plan": "Legg nye oppgaver inn i dagens plan",
    "Go through Jira tickets": "Gå gjennom Jira-tickets",
    "Tickets assigned to me – status and priority": "Tickets tildelt meg – status og prioritet",
    "New comments and mentions": "Nye kommentarer og omtaler",
    "Anything blocked or waiting on me?": "Noe som står fast eller venter på meg?",
    "Check today's meetings": "Sjekk dagens møter",
    "Add each meeting under item 04": "Legg inn hvert møte under punkt 04",
    "Prepare for your meetings": "Forbered deg til møtene",
    "Make a short plan for the day": "Lag en liten plan for dagen",
    "The 1–3 most important things today": "De 1–3 viktigste tingene i dag",
    "Focus time between meetings": "Fokustid mellom møtene",
    "What can wait until tomorrow?": "Hva kan vente til i morgen?",
    "Start each task with - to check it off under plan ▸": "Start hver oppgave med - for å krysse den av under plan ▸",
    "Read the agenda": "Les agendaen",
    "Review notes from the last meeting": "Se over notater fra forrige møte",
    "Open relevant documents / tickets": "Åpne relevante dokumenter / tickets",
    "Write down questions and input": "Noter spørsmål og innspill",
    "+ add meeting": "+ legg til møte",
    "10:00 sprint review": "10:00 sprint review",
    "add to routine and press enter": "legg til i rutinen og trykk Enter",
    "Drag to reorder": "Dra for å endre rekkefølgen",
    "plan ▸": "plan ▸", "plan ◂": "plan ◂",
    "[ all done – have a great day ]": "[ alt ferdig – ha en fin dag ]",
    "{n} days in a row": "{n} dager på rad",
    "{n} days in a row!": "{n} dager på rad!",
    "unlocked: {name}!": "låst opp: {name}!",
    # --- timer ---
    "Hours worked today": "Timer jobbet i dag",
    "day off (vacation, sick, holiday)": "fridag (ferie, syk, helligdag)",
    "h": "t",
    "not logged yet · expected {h} h": "ikke ført ennå · forventet {h} t",
    "today {diff} vs {h} h": "i dag {diff} mot {h} t",
    "overtime balance\nweek {week} · month {month}": "overtidssaldo\nuke {week} · måned {month}",
    # --- status ---
    "○ loading…": "○ laster…",
    "● saved": "● lagret",
    "○ unsaved changes": "○ ulagrede endringer",
    "● not saved – {err}": "● ikke lagret – {err}",
    "● could not read the database – retrying in 30 s ({err})": "● fikk ikke lest databasen – prøver igjen om 30 s ({err})",
    "● reminders could not be set – {err}": "● påminnelsene kunne ikke settes – {err}",
    "● setup: {problems}": "● oppsett: {problems}",
    # --- tittellinja og paneler ---
    "Pomodoro timer": "Pomodoro-klokke",
    "Customize the cat": "Tilpass katten",
    "Settings": "Innstillinger",
    "Theme: {name}": "Tema: {name}",
    "system": "system", "light": "lys", "dark": "mørk",
    "today's plan": "dagens plan",
    "Write lines starting with - in 05 to add them here": "Skriv linjer som starter med - i 05 for å få dem hit",
    "pomo {clock}": "pomo {clock}",
    # --- oppdatering ---
    "update": "oppdater",
    "restart": "start på nytt",
    "Not now": "Ikke nå",
    "Version {latest} is available (you have {current}).": "Versjon {latest} er ute (du har {current}).",
    "Downloading…": "Laster ned…",
    "Download failed – {err}": "Nedlastingen feilet – {err}",
    "Run this in a terminal to update:\n{cmd}": "Kjør dette i en terminal for å oppdatere:\n{cmd}",
    "Installing – enter your password in the dialog…": "Installerer – skriv passordet ditt i vinduet…",
    "Updated to {version}. Restart to use it.": "Oppdatert til {version}. Start på nytt for å bruke den.",
    "Not updated (cancelled or failed). Try again, or run:\n{cmd}": "Ikke oppdatert (avbrutt eller feilet). Prøv igjen, eller kjør:\n{cmd}",
    # --- innstillinger ---
    "settings": "innstillinger",
    "show tutorial": "vis gjennomgang",
    "todos": "punkter",
    "Delete asks for a second click to confirm.": "Slett ber om et ekstra klikk for å bekrefte.",
    "delete": "slett",
    "sure?": "sikker?",
    "deleted default items": "slettede standardpunkter",
    "restore": "gjenopprett",
    "schedule": "tider",
    "open the list": "åpne listen",
    "remind me to log hours": "minn meg på å føre timer",
    "save & close": "lagre og lukk",
    "cat lunch": "kattens lunsj",
    "apply": "bruk",
    "saving…": "lagrer…",
    "not saved – lunch must end after it starts": "ikke lagret – lunsjen må slutte etter at den starter",
    "not saved – {err}": "ikke lagret – {err}",
    "saved, but reminders could not be set – {err}": "lagret, men påminnelsene kunne ikke settes – {err}",
    "saved · next open: {open} · reminder: {reminder} · close: {close}": "lagret · neste åpning: {open} · påminnelse: {reminder} · lukking: {close}",
    "off": "av",
    "hours for another day": "timer for en annen dag",
    "day off": "fridag",
    "save": "lagre",
    "loading…": "laster…",
    "Today: use the hours field in the list.": "I dag: bruk timefeltet i listen.",
    "could not read – {err}": "fikk ikke lest – {err}",
    "not logged": "ikke ført",
    "logged {h} h": "ført {h} t",
    "{day}: {logged} · expected {h} h": "{day}: {logged} · forventet {h} t",
    "saved {h} h for {day}": "lagret {h} t for {day}",
    "backup": "sikkerhetskopi",
    "export…": "eksporter…",
    "restore…": "gjenopprett…",
    "hours as CSV…": "timer som CSV…",
    "Save backup": "Lagre sikkerhetskopi",
    "Save hours": "Lagre timer",
    "Restore backup": "Gjenopprett sikkerhetskopi",
    "saving backup…": "lagrer sikkerhetskopi…",
    "backup saved: {path}": "sikkerhetskopi lagret: {path}",
    "could not save – {err}": "kunne ikke lagre – {err}",
    "{n} days of hours saved: {path}": "{n} dager med timer lagret: {path}",
    "Restore this backup?": "Gjenopprette denne sikkerhetskopien?",
    "Your current list, hours and settings are replaced by the backup. A copy of the current database is kept next to it.":
        "Listen, timene og innstillingene dine erstattes av sikkerhetskopien. En kopi av den nåværende databasen blir liggende ved siden av.",
    "Cancel": "Avbryt",
    "Restore": "Gjenopprett",
    "restoring…": "gjenoppretter…",
    "could not restore – {err}": "kunne ikke gjenopprette – {err}",
    "updates": "oppdateringer",
    "version {version}": "versjon {version}",
    "running from source": "kjører fra kildekoden",
    "check for new versions": "se etter nye versjoner",
    "language": "språk",
    "Restart to change the language.": "Start på nytt for å bytte språk.",
    "welcome!": "velkommen!",
    # --- katten ---
    "cat": "katt",
    "reset": "tilbakestill",
    "Back to orange tabby and default phrases": "Tilbake til oransje tabby og standardreplikker",
    "breed": "rase",
    "colors": "farger",
    "custom": "egen",
    "orange tabby": "oransje tabby", "grey tabby": "grå tabby", "black": "svart", "tuxedo": "smoking",
    "calico": "calico", "white": "hvit", "siamese": "siameser", "maine coon": "maine coon",
    "fur": "pels", "stripes": "striper", "chest & paws": "bryst og poter", "nose & ears": "nese og ører",
    "eyes": "øyne", "outline": "kontur",
    "Cat {part}": "Katt: {part}",
    "accessories": "tilbehør",
    "Unlocked by finishing the whole list several working days in a row.": "Låses opp ved å gjøre ferdig hele listen flere arbeidsdager på rad.",
    "bow tie": "sløyfe", "coffee cup": "kaffekopp", "beanie": "lue",
    "{name} – {days} days in a row": "{name} – {days} dager på rad",
    "what the cat says": "hva katten sier",
    "Separate options with | to pick one at random. Leave empty for just a ♥.": "Skill alternativer med | for å velge et tilfeldig. La stå tomt for bare et ♥.",
    "when {event}": "når {event}",
    "you check something off": "du krysser av noe",
    "the whole list is done": "hele listen er ferdig",
    "you click the title": "du klikker på tittelen",
    "a focus session starts": "en fokusøkt starter",
    "time for a break": "det er tid for pause",
    "the break is over": "pausen er over",
    "good job!": "bra jobba!", "all done!": "alt ferdig!", "let's go!": "kjør!",
    "break time!": "pausetid!", "focus time!": "fokustid!",
    "{breed}!": "{breed}!",
    "meow?": "mjau?", "*stares at list*": "*stirrer på listen*", "mrrp?": "mrrp?",
    "playtime!": "lekestund!", "mrrrow!": "mrrrjau!", "let's play!": "la oss leke!",
    "got it!": "tok den!", "pounce!": "hopp!", "mrrp!": "mrrp!", "gotcha!": "fanget!",
    "nom": "nam",
    # --- pomodoro ---
    "pomodoro": "pomodoro",
    "focus": "fokus", "break": "pause", "long break": "lang pause",
    " · paused": " · på pause",
    "start": "start", "pause": "pause", "skip": "hopp over",
    "settings ▸": "innstillinger ▸", "settings ▾": "innstillinger ▾",
    "focus min": "fokus min", "break min": "pause min", "long break min": "lang pause min",
    "rounds before long": "økter før lang pause",
    "{dots}   today: {n}": "{dots}   i dag: {n}",
    "🍅 Focus done": "🍅 Fokusøkt ferdig",
    "Time for a {n} min break.": "Tid for {n} min pause.",
    "🍅 Break over": "🍅 Pausen er over",
    "Ready for the next focus session?": "Klar for neste fokusøkt?",
    # --- velkomst ---
    "Welcome": "Velkommen",
    "hi there": "hei",
    "Morning Routine is a small daily companion: a morning checklist, a plan for the day, hours and overtime, a pomodoro timer – and a cat.\n\nThis takes one minute.":
        "Morning Routine er en liten daglig følgesvenn: en morgensjekkliste, en plan for dagen, timer og overtid, en pomodoro-klokke – og en katt.\n\nDette tar ett minutt.",
    "your list": "listen din",
    "Check things off as you go – the cat notices.\n\nDrag the number (01, 02 …) to change the order.\n\nAdd your own items at the bottom of the list. They come back every day. Delete items under ⚙.":
        "Kryss av etter hvert – katten følger med.\n\nDra i nummeret (01, 02 …) for å endre rekkefølgen.\n\nLegg til egne punkter nederst i listen. De kommer tilbake hver dag. Slett punkter under ⚙.",
    "plan": "plan",
    "Write today's tasks in item 05, one per line, starting with a dash:\n\n    - fix the bug\n    - review PR\n\nOpen plan ▸ to check them off. Unfinished tasks move to the next day.":
        "Skriv dagens oppgaver i punkt 05, én per linje, med bindestrek først:\n\n    - fiks feilen\n    - se over PR\n\nÅpne plan ▸ for å krysse dem av. Uferdige oppgaver blir med til neste dag.",
    "hours": "timer",
    "Log your hours in the ⏱ field at the bottom. The overtime balance adds up for you.\n\nWeekends and days off (tick «day off») expect 0 hours. Forgot a day? Fix it under ⚙ → hours for another day.":
        "Før timene dine i ⏱-feltet nederst. Overtidssaldoen regnes ut for deg.\n\nHelg og fridager (kryss av «fridag») forventer 0 timer. Glemt en dag? Rett det under ⚙ → timer for en annen dag.",
    "more": "mer",
    "pomo – a focus timer. The cat sleeps while you work and plays in the breaks.\n\ncat – breed, colors and what the cat says.\n\n⚙ – when the list opens, reminders, auto close and lunch.":
        "pomo – en fokusklokke. Katten sover mens du jobber og leker i pausene.\n\nkatt – rase, farger og hva katten sier.\n\n⚙ – når listen åpnes, påminnelser, automatisk lukking og lunsj.",
    "set up": "oppsett",
    "A few choices – everything can be changed later under ⚙.": "Noen valg – alt kan endres senere under ⚙.",
    "normal work day (hours)": "vanlig arbeidsdag (timer)",
    "overtime you already have (hours)": "overtid du allerede har (timer)",
    "open the list on weekdays at": "åpne listen på hverdager kl.",
    "remind me to log hours at": "minn meg på å føre timer kl.",
    "pin Morning Routine to the dock": "fest Morning Routine i docken",
    "back": "tilbake", "next": "neste",
    "Mon": "Ma", "Tue": "Ti", "Wed": "On", "Thu": "To", "Fri": "Fr", "Sat": "Lø", "Sun": "Sø",
    "dock: {err}": "dock: {err}",
}
