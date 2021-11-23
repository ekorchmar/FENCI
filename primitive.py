# todo:
# After tech demo
# todo: sparks to leave shapes of lines
# todo: dialogue graphic
# todo:
#  use freetype instead of fonts

import pygame
import os
import random
import math
import json
import sys

# Start pygame:
if not pygame.get_init():
    pygame.mixer.pre_init(44100, -16, 2, 1024)
    pygame.init()
    pygame.mixer.set_num_channels(8)

if not pygame.font.get_init():
    pygame.font.init()

# Alisases
v = pygame.math.Vector2
c = pygame.color.Color
r = pygame.rect.Rect
s = pygame.surface.Surface


# Load JSON dicts:
def load_json(file_path, directory='resource'):
    with open(os.path.join(directory, file_path)) as resource_json:
        return json.loads(resource_json.read())


# Resource collections
raw_materials = load_json('raw_materials.json')
colors = load_json('colors.json')
parts_dict = load_json('parts.json')
character_stats = load_json('monsters.json')
artifacts = load_json('artifact.json')
string = load_json('en.json', directory='language')

# Global options
OPTIONS = load_json('options.json', 'options')

FONT = os.path.join('resource', 'DejaVuSansMono.ttf')

# Screen options:
# WINDOW_SIZE = 1024, 768
WINDOW_SIZE = 1440, 900
FPS_TARGET = 60
FPS_TICK = 1 / FPS_TARGET
BASE_SIZE = 24
DISPLAY_COLOR = colors["background"]

# All sounds and constants:
MUSIC_VOLUME = 0.5
WEAPON_SOUNDS = 'shield', 'metal', 'bone', 'wood', 'mineral'  # Also serves as priority for collision sounds
CREATURE_SOUNDS = 'hurt', 'jump', 'roll', 'collision', 'landing', 'death', 'swing', 'beep1', 'beep2', 'drop', 'ram'
GAME_SOUNDS = 'player_death', 'respawn', 'level_clear', 'level_failed'
MENU_SOUNDS = 'button', 'level_clear', 'level_failed', 'loot'
SOUND_PROFILES = None, '8bit'
SOUND = dict()

# Calculated standard Rects
SCENE_BOUNDS = r(
    BASE_SIZE,
    BASE_SIZE+WINDOW_SIZE[1]//6,
    WINDOW_SIZE[0] - BASE_SIZE*2,
    WINDOW_SIZE[1]*5//6 - BASE_SIZE*2
)

EXTENDED_SCENE_BOUNDS = r(
    BASE_SIZE,
    BASE_SIZE,
    WINDOW_SIZE[0] - BASE_SIZE * 2,
    WINDOW_SIZE[1] - BASE_SIZE * 2,
)

LOOT_SPACE = r(
    SCENE_BOUNDS.left + BASE_SIZE,
    SCENE_BOUNDS.top + BASE_SIZE,
    SCENE_BOUNDS.width - 2*BASE_SIZE,
    SCENE_BOUNDS.height - 2*BASE_SIZE
)

INVENTORY_SPACE = r(
    BASE_SIZE + WINDOW_SIZE[0] // 3,
    BASE_SIZE,
    WINDOW_SIZE[0] * 2 // 3 - 2 * BASE_SIZE,
    WINDOW_SIZE[1] // 6 - BASE_SIZE
)

LEVEL_BAR_SPACE = r(
    BASE_SIZE,
    BASE_SIZE,
    WINDOW_SIZE[0] // 3 - BASE_SIZE,
    WINDOW_SIZE[1] // 6 - BASE_SIZE
)

MAX_LOOT_CARD_SPACE = r(
    0,  # Rect corners are dynamic
    0,
    INVENTORY_SPACE.width // 3,
    WINDOW_SIZE[1] - 4*BASE_SIZE
)

DEFAULT_BUTTON_RECT = r(
    0,
    0,
    WINDOW_SIZE[0] // 6,
    WINDOW_SIZE[1] // 10
)

# Game constants
# Initial position is (1/6, 1/2) of scene bounding box,
PLAYER_SPAWN = v(
    SCENE_BOUNDS.left + SCENE_BOUNDS.width // 6,
    SCENE_BOUNDS.top + SCENE_BOUNDS.height // 2
)

ARENA_RECT = r(
    0,
    0,
    512*3,
    512*2
)

SHAKE_RANGE = 2*BASE_SIZE
SHAKER_BUFFER = v(SHAKE_RANGE, SHAKE_RANGE)
CAMERA_SPEED = 0.12

# Physics constants:
SWING_THRESHOLD = 300 * FPS_TICK
MAX_SPEED = 4 * SWING_THRESHOLD
POKE_THRESHOLD = 150 * FPS_TICK
REMAINS_SCREENTIME = 4
FFA = v(0, 3.33*FPS_TICK)

# Inventory constants:
TIERS = range(1, 5)
TIER_WEIGHTS = {
    1: (0.80, 0.15, 0.05, 0.00),
    2: (0.40, 0.40, 0.15, 0.05),
    3: (0.20, 0.25, 0.25, 0.20),
    4: (0.15, 0.20, 0.40, 0.25)
}

PLAYER_SLOTS = ("main_hand", "hat", "off_hand")  # ordered for mouse input
LOOT_OCCURRENCE_WEIGHTS = {
    "main_hand": 1,
    "off_hand": 0.75,
    "hat": 0.4
}

# Sets of character and AI states
DISABLED = {'flying', 'hurt', 'skewered'}
AIRBORNE = {'flying', 'jumping'}
IDLE = {'idle', 'blinking', 'idle_rare', 'exhausted'}

PASSIVE_STRATEGY = {"unknown", "passive", "wait", "wander", "flee"}
ATTACKING_STRATEGY = {'charge', 'dogfight'}
BUSY = {'charge', 'dogfight', 'flee', 'reroute', 'skewered', 'jumping'}

# Number keys indices:
NUMBER_CODES = list(enumerate(range(pygame.K_1, pygame.K_9)))
NUMBER_LABELS = {i: str(i+1) for i in range(9)}

# Pygame display and clock
SCREEN = None
CLOCK = pygame.time.Clock()


# Materials
PAINTABLE = {"wood", "cloth", "leather"}
PAINT8 = colors["paint8"]


# Math utils
def solve_square_rotation(a, b, constant):
    """
    Return all real, positive solutions
    :param a: square coefficient
    :param b: linear coefficient
    :param constant: constant
    :return: 
    """
    solutions = []
    for q in (a, -a):
        D = b*b - 4 * a * constant

        # Try another "a"
        if D < 0:
            continue

        for sign in (1, -1):
            solution = (-b+sign*D) / (2 * q)
            if solution > 0:
                solutions.append(solution)

    return solutions


def intersect_lines(line1, line2):
    """
    https://stackoverflow.com/questions/3838329/how-can-i-check-if-two-segments-intersect/3838357#3838357
    Thank you @ Martijn Pieters!
    """
    max_f = 1.8e+300
    if line2 is None:  # Empty hitboxes
        return False

    X1, Y1 = line1[0]
    X2, Y2 = line1[1]
    X3, Y3 = line2[0]
    X4, Y4 = line2[1]

    if max(X1, X2) < min(X3, X4) or max(Y1, Y2) < min(Y3, Y4):
        return False  # There is no mutual abcisses

    if X1-X2 == 0:
        A1 = max_f
    else:
        A1 = (Y1 - Y2) / (X1 - X2)

    if X3 - X4 == 0:
        A2 = max_f
    else:
        A2 = (Y3 - Y4) / (X3 - X4)  # Pay attention to not dividing by zero

    if A1 == A2:
        return False  # Parallel segments

    b1 = Y2 - A1 * X2
    b2 = Y4 - A2 * X4

    Xa = (b2 - b1) / (A1 - A2)
    if (Xa < max(min(X1, X2), min(X3, X4))) or (Xa > min(max(X1, X2), max(X3, X4))):
        return False  # intersection is out of bound
    else:
        return True


def rect_distance(rect1: r, rect2: r):
    x1, y1 = rect1.topleft
    x1b, y1b = rect1.bottomright
    x2, y2 = rect2.topleft
    x2b, y2b = rect2.bottomright
    left = x2b < x1
    right = x1b < x2
    top = y2b < y1
    bottom = y1b < y2
    if bottom and left:
        return math.hypot(x2b-x1, y2-y1b)
    elif left and top:
        return math.hypot(x2b-x1, y2b-y1)
    elif top and right:
        return math.hypot(x2-x1b, y2b-y1)
    elif right and bottom:
        return math.hypot(x2-x1b, y2-y1b)
    elif left:
        return x1 - x2b
    elif right:
        return x2 - x1b
    elif top:
        return y1 - y2b
    elif bottom:
        return y2 - y1b
    else:  # rectangles intersect
        return 0.


def ccw_triangle(point_a: v, point_b: v, point_c: v):
    """
    Return True if points are listed in counter-clockwise order and False if they are on the same line or clockwise
    """
    calc = (point_b.x - point_a.x) * (point_c.y - point_a.y) - (point_c.x - point_a.x) * (point_b.y - point_a.y)
    return calc > 0


def rect_point_distance2(rect: r, point: v):
    dx = max(rect.left - point.x, point.x - rect.right)
    dy = max(rect.top - point.y, point.y - rect.bottom)
    return dx*dx + dy*dy


def lerp(values_range, progression):
    if progression <= 0:
        return values_range[0]

    if progression >= 1:
        return values_range[1]

    # It is not forbidden to have range of (a, a):
    try:
        return values_range[0] + (values_range[1]-values_range[0]) * progression
    except ZeroDivisionError:
        return values_range[0]


def random_point(v1: v, v2: v):
    r_float = random.random()
    difference_v = v2 - v1

    difference_v *= r_float

    return v1 + difference_v


def get_key(val, my_dict):
    for key, value in my_dict.items():
        if val == value:
            return key

    raise ValueError("No key holds this value")


def rect_collide_destination(rect: r, destination) -> bool:
    return (isinstance(destination, r) and destination.colliderect(rect)) or \
           (isinstance(destination, v) and rect.collidepoint(*destination))


# Game utils:
def roll_tier(tier):
    if tier == 0:
        return
    # Find probability weights list from weights dict:
    return random.choices(TIERS, TIER_WEIGHTS[tier])[0]


def kb_move(pressed_keys):
    # Input: WASD
    moving = any(pressed_keys)
    direction = v(0, 0)

    if moving:
        if pressed_keys[0]:
            direction += v(0, -1)

        if pressed_keys[1]:
            direction += v(-1, 0)

        if pressed_keys[2]:
            direction += v(0, 1)

        if pressed_keys[3]:
            direction += v(1, 0)

    return direction


def paint():
    return random.choice(list(PAINT8.values()))


def scale_body(body_dict, new_size):
    for body_part in body_dict:
        body_dict[body_part] = [round(coordinate*new_size) for coordinate in body_dict[body_part]]


def triangle_roll(value, offset):
    absolute_offset = value * offset
    result = random.triangular(value - absolute_offset, value + absolute_offset)
    return result


def exit_game():
    pygame.quit()
    sys.exit()


def draw_icon():
    icon_surface = s((64, 64), pygame.SRCALPHA)
    icon_surface.fill(colors['background'])

    dagger1 = ascii_draw(18, '-]=≡>', colors["inventory_text"])
    icon_surface.blit(*rot_center(dagger1, 45, v(32, 32)))

    dagger2 = ascii_draw(18, '⊂{≡=-', colors["inventory_text"])
    icon_surface.blit(*rot_center(dagger2, 135, v(32, 32)))

    frame_surface(icon_surface, colors["inventory_text"])
    pygame.display.set_icon(icon_surface)


def unfocused():
    return not (pygame.mouse.get_focused() or pygame.mouse.get_focused())


def save_state(state: dict):
    with open(os.path.join('progression', 'saved.json'), 'w') as saved_game_json:
        json.dump(state, saved_game_json)


def wipe_save():
    save_state(dict())


# Drawing tools
def update_screen():
    global SCREEN

    # Set window icon and name:
    pygame.display.set_caption("FENCI")
    draw_icon()

    display_flags = pygame.SCALED | pygame.FULLSCREEN if OPTIONS['fullscreen'] else pygame.SCALED
    SCREEN = pygame.display.set_mode(WINDOW_SIZE, flags=display_flags, vsync=0)


def ascii_draw(font_size: int, ascii_string: str, draw_color):
    """Create a surface from text. Input is font size, string, and color"""
    use_font = pygame.font.Font(FONT, font_size)
    text_surface = use_font.render(ascii_string, True, draw_color)
    return text_surface


def ascii_draw_cascaded(font_size: int, ascii_string: str, draw_color, max_width: int = WINDOW_SIZE[0]):
    use_font = pygame.font.Font(FONT, font_size)
    words = ascii_string.split(' ')
    space, word_height = use_font.size(' ')
    x, y = 0, 0
    # Maximum possible size surface, will be blit on a resulting size surface
    total_surface = s((max_width, WINDOW_SIZE[1]), pygame.SRCALPHA)
    for word in words:
        word_surface = ascii_draw(font_size, word, draw_color)
        word_width, word_height = word_surface.get_size()
        if x + word_width >= max_width:
            x = 0  # Reset the x.
            y += word_height  # Start on new row.
        total_surface.blit(word_surface, (x, y))
        x += word_width + space
    # Determine size of resulting text:
    if y > 0:  # If multiple rows
        size = max_width, y+word_height
    else:
        size = x-space, word_height
    sized_surface = s(size, pygame.SRCALPHA)
    sized_surface.blit(total_surface, total_surface.get_rect(topleft=(0, 0)))
    return sized_surface


def ascii_draws(font_size: int, draw_order):
    """
    Create multicolor surface from list of string&color tuples
    Example (iron hilt):
        ascii_draws(14, [('•~[', iron.generate[0)])
    """
    return glue_horizontal(*[ascii_draw(font_size, text, color) for text, color in draw_order])


def ascii_draw_rows(font_size, rows: list):
    """Take input in form of multiple rows of ascii_draws. Use length of the longest row"""
    # Form list of surfaces from each row
    surfaces = [ascii_draws(font_size, [row]) for row in rows]
    row_x = max(surf.get_width() for surf in surfaces)
    row_y = surfaces[0].get_height()
    initial_y = 0
    resulting_surface = s((row_x, row_y * len(rows)), pygame.SRCALPHA)
    for surface in surfaces:
        resulting_surface.blit(surface, (0, initial_y))
        initial_y += row_y
    return resulting_surface


def rot_center(image: s, angle: float, center: v):
    # bypass for 0
    if angle == 0:
        new_rect = image.get_rect(center=center)
        return image, new_rect

    rotated_image = pygame.transform.rotate(image, angle)
    new_rect = rotated_image.get_rect(center=image.get_rect(center=center).center)

    return rotated_image, new_rect


def tint(surf, tint_color):
    """ adds tint_color onto surf.
    """
    surf = surf.copy()
    surf.fill((0, 0, 0, 255), None, pygame.BLEND_RGBA_MULT)
    surf.fill(tint_color[0:3] + (0,), None, pygame.BLEND_RGBA_ADD)
    return surf


def blit_cascade_text(surface, font_size, text, xy_topleft, color, right_offset=None):
    words = [word.split(' ') for word in text.splitlines()]  # 2D array where each row is a list of words.
    font = pygame.font.Font(FONT, font_size)
    space, word_height = font.size(' ')  # The width of a space.
    max_width, max_height = surface.get_size()
    x, y = xy_topleft

    if right_offset is None:
        right_offset = x
    max_width -= right_offset

    for line in words:
        for word in line:
            word_surface = font.render(word, True, color)
            word_width, word_height = word_surface.get_size()
            if x + word_width >= max_width:
                x = xy_topleft[0]  # Reset the x.
                y += word_height  # Start on new row.
            surface.blit(word_surface, (x, y))
            x += word_width + space
        x = xy_topleft[0]  # Reset the x.
        y += word_height  # Start on new row.

    # Return total text height
    return y - xy_topleft[1]


def glue_horizontal(*surfaces: s, offset=0, center_vertically=True):
    # Find dimensions of resulting surface
    width = sum(surface.get_width() for surface in surfaces) + offset * (len(surfaces) - 1)
    height = max(surface.get_height() for surface in surfaces)
    resulting_surface = s((width, height), pygame.SRCALPHA)

    left_x = 0
    for surface in surfaces:
        # Find vertical offset:
        top_y = (height - surface.get_height()) // 2 if center_vertically else 0
        resulting_surface.blit(surface, (left_x, top_y))
        left_x += offset + surface.get_width()

    return resulting_surface


def frame_text(lines: list, style='╔═╗╚╝║'):
    """
    Styles cheat-sheet:
    ╔═╗╚╝║
    /–\\/|
    ┏━┓┗┛┃
    """

    max_width = max(len(line) for line in lines)

    top = style[0] + style[1]*max_width + style[2] + '\n'
    bottom = '\n' + style[3] + style[1]*max_width + style[4]

    return top + '\n'.join(style[5] + line.ljust(max_width) + style[5] for line in lines) + bottom


def frame_surface(surface, color):
    frame_rect = r(
        BASE_SIZE // 12,
        BASE_SIZE // 12,
        surface.get_width() - BASE_SIZE // 6,
        surface.get_height() - BASE_SIZE // 6
    )
    pygame.draw.rect(surface, color, frame_rect, BASE_SIZE // 6)


# Sound management
def play_theme(filepath):
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()

    pygame.mixer.music.load(filepath)
    pygame.mixer.music.set_volume(MUSIC_VOLUME)
    pygame.mixer.music.play(loops=-1, fade_ms=1000)


def end_theme():
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.fadeout(100)
        pygame.mixer.music.unload()


def load_sound_profile(profile_number, file_extension='wav'):
    all_sounds = (*WEAPON_SOUNDS, *CREATURE_SOUNDS, *GAME_SOUNDS, *MENU_SOUNDS)
    pygame.mixer.stop()

    # Stop and drop existing sounds, if any
    if pygame.mixer.get_busy():
        pygame.mixer.stop()
    SOUND.clear()

    # Load new sounds:
    if profile_number == 0:
        return

    profile = SOUND_PROFILES[profile_number]
    for sound in all_sounds:
        SOUND[sound] = pygame.mixer.Sound(file=os.path.join('sound', profile, f"{sound}.{file_extension}"))


def play_sound(sound, volume, **kwargs):
    if OPTIONS["sound"] == 0 or unfocused():
        return

    # Normalize volume:
    volume = min(1, volume)
    volume = max(0, volume)

    # Free up a sound channel if needed:
    free_channel = pygame.mixer.find_channel(True)

    if free_channel is None:
        return
    if free_channel.get_busy():
        free_channel.stop()

    # Copy and play the sound using freed channel:
    sound_instance = pygame.mixer.Sound(SOUND[sound])
    free_channel.play(sound_instance, **kwargs)
    free_channel.set_volume(volume)


# Cheats/debugs
def morph_equipment(char):
    for slot, weapon in char.slots.items():
        if not weapon:
            continue

        weapon.builder = {}
        weapon.generate(weapon.font_size, tier=random.randint(1, 4))
        weapon.update_stats()
        weapon.redraw_loot()


def aneurysm(character, scene):
    character.hp = -1
    scene.undertake(character)


def random_frenzy(scene, strategy='dogfight'):
    frenzied = random.choice(list(filter(lambda x: x.ai, scene.characters)))
    frenzied.ai.target = scene.player
    frenzied.ai.set_strategy(strategy, 10)


def kill_random(scene):
    cohort = scene.characters[:]
    if scene.player in cohort:
        cohort.remove(scene.player)
    scene.undertake(random.choice(cohort))


# Start the screen:
update_screen()
