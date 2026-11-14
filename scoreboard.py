"""64x32 UFC fight board for direct-GPIO Raspberry Pi matrices."""
import argparse
import json
import logging
import time
import unicodedata
from dataclasses import dataclass
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw
from portraits import photo, RESAMPLE
from finishes import ResultFeed, method_label

URL = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
# Four native LED rows per glyph. Each octal digit encodes a three-pixel row.
FONT = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 :-./'",
                ("2575 6567 3443 6556 7467 7464 3473 5755 7227 1116 5655 4447 "
                 "5775 5675 2552 6574 2553 6565 3616 7222 5557 5552 5575 5225 "
                 "5522 7127 7557 2627 7127 7317 5571 7616 4677 7122 7677 7571 "
                 "0000 0202 0070 0002 1124 2200").split()))


@dataclass
class Bout:
    card: str
    names: tuple
    state: str
    detail: str
    winner: tuple = (False, False)
    athlete_ids: tuple = ("", "")
    key: tuple = ()
    method: str = ""
    cards: tuple = ()
    timing: str = ""


def bouts(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError("Missing events list")
    result = []
    for event in payload["events"]:
        for fight in event.get("competitions", []):
            pair = fight.get("competitors", [])
            if len(pair) != 2:
                continue
            names = []
            for competitor in pair:
                athlete = competitor.get("athlete", {})
                name = athlete.get("lastName") or athlete.get("shortName") or athlete.get("displayName") or "TBA"
                names.append(name.split(". ", 1)[-1])
            status = fight.get("status", {})
            kind = status.get("type", {})
            state = kind.get("state", "")
            detail = kind.get("description") or "PENDING"
            if state == "in":
                clock = status.get("displayClock")
                detail = "R{}".format(status["period"]) if status.get("period") else "LIVE"
                if clock and clock != "-":
                    detail += " " + clock
            elif state == "pre" and kind.get("name") == "STATUS_SCHEDULED":
                detail = "UPCOMING"
            judge_scores = []
            for competitor in pair:
                lines = competitor.get("linescores") or []
                judges = lines[0].get("linescores", []) if lines else []
                judge_scores.append([str(j.get("displayValue", "")) for j in judges])
            cards = tuple(a + "-" + b for a, b in zip(*judge_scores)
                          if a.isdigit() and b.isdigit() and int(a) and int(b))
            timing = "R{}".format(status["period"]) if status.get("period") else ""
            if timing and status.get("displayClock") not in (None, "", "-"):
                timing += " " + status["displayClock"]
            result.append(Bout(event.get("shortName") or "UFC", tuple(names), state, detail,
                               tuple(c.get("winner") is True for c in pair),
                               tuple(str(c.get("id") or c.get("athlete", {}).get("id") or "") for c in pair),
                               (str(event.get("id", "")), str(fight.get("id", ""))),
                               method_label(status.get("result")), cards, timing))
    return result


def pixels(draw, x, y, label, color, width):
    label = unicodedata.normalize("NFKD", label.upper()).encode("ascii", "ignore").decode()
    for letter in label:
        if x + 3 > width:
            break
        for row, mask in enumerate(FONT.get(letter, "7120")):
            for col in range(3):
                if int(mask) & (4 >> col):
                    draw.point((x + col, y + row), color)
        x += 4


def fight_frame(bout, tick, offline):
    image = Image.new("RGB", (64, 32))
    draw = ImageDraw.Draw(image)
    for corner, x in enumerate((0, 46)):
        color = ("#ff5050", "#4b9aff")[corner]
        portrait = photo(bout.athlete_ids[corner])
        if portrait is not None:
            thumbnail = portrait.resize((18, 16), RESAMPLE.LANCZOS)
            image.paste(thumbnail, (x, 0), thumbnail)
        else:
            pixels(draw, x + 6, 6, bout.names[corner][:1], color, x + 18)
        draw.line((x, 17, x+17, 17), fill=color)
        winner = bout.state == "post" and bout.winner[corner]
        pixels(draw, corner * 32, 19, bout.names[corner], "#63ff84" if winner else "white", (corner+1)*32)
    status = {"post": "FINAL", "in": "LIVE", "pre": "CARD"}.get(bout.state, "UFC")
    pixels(draw, 19, 2, status, "#ffb944", 46)
    timing = bout.timing or (bout.detail if bout.state == "in" else "")
    round_no, _, clock = timing.partition(" ")
    pixels(draw, 19, 8, round_no, "white", 46)
    pixels(draw, 19, 12, clock, "white", 46)
    captions = []
    if bout.state == "pre":
        captions.append(bout.detail)
    if True in bout.winner:
        captions.append("W " + bout.names[bout.winner.index(True)])
    if bout.method:
        captions.extend(bout.method[i:i+16] for i in range(0, len(bout.method), 16))
    captions.extend("J{} {}".format(i+1, score) for i, score in enumerate(bout.cards))
    footer = "FEED OFFLINE" if offline else (captions[tick % len(captions)] if captions else "SCORE PENDING")
    pixels(draw, 0, 26, footer, "#65e3da", 64)
    return image


def celebration(bout):
    label = bout.method.upper()
    image = fight_frame(bout, 0, False)
    for step in range(14):
        frame = image.copy()
        draw = ImageDraw.Draw(frame)
        draw.rectangle((0, 24, 63, 31), fill="black")
        progress = min(step, 8)
        if "KO" in label or "KNOCKOUT" in label:
            for x in (31-progress*3, 32+progress*3):
                draw.line((31, 24, x, 31), fill="#ff6030")
        elif "SUB" in label:
            draw.rectangle((progress*3, 24, 63-progress*3, 31), outline="#ac71ff")
        elif "DEC" in label or label in ("UD", "SD", "MD"):
            for x in range(0, min(3, 1+step//3)*22, 22):
                draw.line((x, 31, x+17, 31), fill="#ffcb55")
        else:
            draw.line((0, 31, min(63, step*6), 31), fill="#62ffa3")
        offset = min(max(0, len(label)-16), max(0, step-4)*2)
        pixels(draw, 0, 25, label[offset:], "white", 64)
        yield frame


def render(bout, offline=False, demo=False, tick=0):
    if bout and bout.state in ("in", "post"):
        return fight_frame(bout, tick, offline)
    image = Image.new("RGB", (64, 32))
    draw = ImageDraw.Draw(image)
    title = "DEMO" if demo else (bout.card if bout else "UFC")
    pixels(draw, 1, 0, title, "#ffae36", 64)
    for i, name in enumerate(bout.names if bout else ("NO FIGHTS", "")):
        y = 8 + i * 8
        win = bout and bout.state == "post" and bout.winner[i]
        draw.rectangle((0, y, 2, y+5), fill=("#ff5050", "#4b9aff")[i])
        pixels(draw, 5, y, name, "#63ff84" if win else "white", 57 if win else 64)
        if win:
            pixels(draw, 59, y, "W", "#63ff84", 64)
    footer = "FEED OFFLINE" if offline else (bout.detail if bout else "NO CARD")
    pixels(draw, 1, 26, footer, "#ffd04a" if offline else "#65e3da", 64)
    return image


def intro(bout, corner, demo=False):
    portrait = photo(bout.athlete_ids[corner])
    if portrait is None:
        return render(bout, demo=demo)
    image = Image.new("RGB", (64, 32))
    image.paste(portrait, (0, 1), portrait)
    draw = ImageDraw.Draw(image)
    color = ("#ff5050", "#4b9aff")[corner]
    draw.line((30, 1, 30, 30), fill=color)
    pixels(draw, 32, 1, "DEMO" if demo else "UFC", color, 64)
    name = bout.names[corner]
    pixels(draw, 32, 11, name[:8], "white", 64)
    pixels(draw, 32, 18, name[8:16], "white", 64)
    pixels(draw, 32, 26, "ON CARD" if not demo else "INTRO", "#65e3da", 64)
    return image


DEMO = [Bout("UFC", ("Muniz", "Allen"), "pre", "UPCOMING", athlete_ids=("3091099", "3902098")),
        Bout("UFC", ("Muniz", "Allen"), "in", "R2 3:18", athlete_ids=("3091099", "3902098")),
        Bout("UFC", ("Muniz", "Allen"), "post", "FINAL", (False, True), ("3091099", "3902098"), ("demo","1"), "Submission", timing="R2 3:18")]


def fetch():
    request = Request(URL, headers={"User-Agent": "ufc-led-scoreboard/1.0"})
    with urlopen(request, timeout=8) as response:
        return bouts(json.load(response))


def lower_portraits(frame):
    # Exchange the two row banks without flipping the image or its lettering.
    result = Image.new("RGB", frame.size)
    result.paste(frame.crop((0, 0, 64, 16)), (0, 16))
    upper = frame.crop((0, 16, 64, 32))
    # Draw every illuminated text pixel using the working red channel.
    red = upper.convert("L").point(lambda value: 235 if value else 0)
    dark = Image.new("L", upper.size)
    result.paste(Image.merge("RGB", (red, dark, dark)), (0, 0))
    return result


def color_test():
    image = Image.new("RGB", (64, 32))
    draw = ImageDraw.Draw(image)
    for row in (0, 16):
        for column, color in enumerate(("#ff0000", "#00ff00", "#0000ff", "#ffffff")):
            x = 16 * column
            draw.rectangle((x, row + 1, x + 14, row + 14), fill=color)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lower-portraits", action="store_true", help="Use the lower panel half for full-color portraits")
    parser.add_argument("--color-test", action="store_true", help="Show RGB and white on both panel halves")
    parser.add_argument("--rgb-order", choices=("RGB","RBG","GRB","GBR","BRG","BGR"), default="RGB", help="Order of channels sent to the display")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--driver", choices=["preview", "matrix"], default="preview")
    parser.add_argument("--mapping", default="regular")
    parser.add_argument("--gpio-slowdown", type=int, default=1)
    parser.add_argument("--brightness", type=int, choices=range(1, 101), default=50, metavar="1-100")
    args = parser.parse_args()
    matrix = None
    if args.driver == "matrix":
        try:
            from rgbmatrix import RGBMatrix, RGBMatrixOptions
        except ModuleNotFoundError as exc:
            if exc.name != "rgbmatrix":
                raise
            from legacy_display import LegacyDisplay
            matrix = LegacyDisplay(args)
        else:
            options = RGBMatrixOptions()
            options.rows, options.cols = 32, 64
            options.hardware_mapping = args.mapping
            options.gpio_slowdown = args.gpio_slowdown
            options.brightness = args.brightness
            matrix = RGBMatrix(options=options)
    card, refresh, index, offline = DEMO if args.demo else [], 0, 0, False
    results = ResultFeed()
    played = set()
    eligible = set()
    def display(frame):
        if args.lower_portraits and not args.color_test:
            frame = lower_portraits(frame)
        if args.rgb_order != "RGB":
            bands = dict(zip("RGB", frame.split()))
            frame = Image.merge("RGB", tuple(bands[key] for key in args.rgb_order))
        if matrix is not None:
            matrix.SetImage(frame)
        else:
            frame.resize((640, 320), RESAMPLE.NEAREST).save("preview.png")

    try:
        if args.color_test:
            display(color_test())
            while matrix is not None and not args.once:
                time.sleep(1)
            return
        while True:
            if not args.demo and time.monotonic() >= refresh:
                try:
                    card = fetch()
                    offline = False
                except (OSError, ValueError) as exc:
                    logging.warning("UFC feed unavailable: %s", exc)
                    offline = True
                refresh = time.monotonic() + 30
            if not args.demo and not offline:
                results.update(card)
                eligible.update(b.key for b in card if b.state in ("pre", "in"))
                for finished in card:
                    if (finished.state == "post" and finished.method and finished.key in eligible
                            and finished.key not in played and not args.once):
                        for frame in celebration(finished):
                            display(frame)
                            time.sleep(.12)
                        played.add(finished.key)
                        display(render(finished))
                        time.sleep(3)
            live = [b for b in card if b.state == "in"]
            pool = card if args.demo or offline else (live or card)
            screens = []
            for bout in pool:
                if bout.state == "pre" and bout.detail == "UPCOMING" and not offline and not args.lower_portraits:
                    screens.extend([(bout, 0), (bout, 1)])
                else:
                    screens.append((bout, None))
            bout, corner = screens[index % len(screens)] if screens else (None, None)
            if args.demo and bout and bout.state == "post" and bout.key not in played:
                for frame in celebration(bout):
                    display(frame)
                    time.sleep(.12)
                played.add(bout.key)
            frame = render(bout, offline, args.demo, index // max(1, len(screens))) if corner is None else intro(bout, corner, args.demo)
            if args.lower_portraits and bout and bout.state == "pre":
                frame = fight_frame(bout, index, offline)
            display(frame)
            if args.once:
                return
            index += 1
            time.sleep(5 if args.demo else 8)
    except KeyboardInterrupt:
        pass
    finally:
        if matrix is not None:
            matrix.Clear()


if __name__ == "__main__":
    main()
