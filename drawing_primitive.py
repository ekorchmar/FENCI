# todo: ascii_draw_rows function to draw multiple rows for speech bubbles, hats and axes
# After tech demo
# todo: sparks to leave shapes of lines
# todo: dialogue graphic
# todo: language json
# todo:
#  use freetype instead

import pygame
import os
import random
import math
import json


# Alisases
v = pygame.math.Vector2
c = pygame.color.Color
r = pygame.rect.Rect
s = pygame.surface.Surface


# Load JSON dicts:
def load_resource(file_path):
    with open(os.path.join('resource', file_path)) as resource_json:
        return json.loads(resource_json.read())


raw_materials = load_resource('raw_materials.json')
colors = load_resource('colors.json')
parts_dict = load_resource('parts.json')
character_stats = load_resource('monsters.json')
artifacts = load_resource('artifact.json')

FONT = os.path.join('resource', 'DejaVuSansMono.ttf')

# Screen options:
WINDOW_SIZE = 1024, 768
FPS_TARGET = 60
FPS_TICK = 1 / FPS_TARGET
BASE_SIZE = 24
DISPLAY_COLOR = colors["background"]

# Calculated standard Rects
SCENE_BOUNDS = r(
    BASE_SIZE,
    BASE_SIZE+WINDOW_SIZE[1]//6,
    WINDOW_SIZE[0] - BASE_SIZE*2,
    WINDOW_SIZE[1]*5//6 - BASE_SIZE*2
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

# Initial player position
# Initial position is (1/6, 1/2) of bounding box,
PLAYER_SPAWN = v(
    SCENE_BOUNDS.left + SCENE_BOUNDS.width // 6,
    SCENE_BOUNDS.top + SCENE_BOUNDS.height // 2
)

# Physics constants:
SWING_THRESHOLD = 300 * FPS_TICK
MAX_SPEED = 4 * SWING_THRESHOLD
POKE_THRESHOLD = 150 * FPS_TICK
REMAINS_SCREENTIME = 4
FFA = pygame.math.Vector2(0, 3.33*FPS_TICK)

# Inventory constants:
TIERS = range(1, 5)
TIER_WEIGHTS = {
    1: (0.60, 0.35, 0.20, 0.05),
    2: (0.20, 0.70, 0.15, 0.05),
    3: (0.05, 0.10, 0.60, 0.25),
    4: (0.05, 0.15, 0.30, 0.50)
}
SLOT_NAMES = {
    "main_hand": 'Sword hand',
    "off_hand": 'Off hand',
    "hat": 'Hat',
    "backpack": 'Backpack'
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
BUSY = {'charge', 'dogfight', 'flee', 'reroute'}

# Pygame display and clock
pygame.display.set_caption("FENCI")
# display_flags = pygame.SCALED | pygame.FULLSCREEN
display_flags = pygame.SCALED
SCREEN = pygame.display.set_mode(WINDOW_SIZE, flags=display_flags, vsync=0)

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
        D = b ** 2 - 4 * a * constant

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
    return dx**2 + dy**2


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


# Drawing tools
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
    surfaces: list = []
    for tpl in draw_order:
        # May be less efficient than calculating offset, but it's done once per item
        string_input, color_input = tpl
        surface = ascii_draw(font_size, string_input, color_input)
        surfaces.append(surface)
    return glue_horizontal(*surfaces)


def ascii_draw_rows(font_size, rows: list[list]):
    """Take input in form of multiple rows of ascii_draws. Assume rows are already of same length"""
    # Form list of surfaces from each row
    surfaces = [ascii_draws(font_size, [row]) for row in rows]
    row_x, row_y = surfaces[0].get_size()
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


def blit_cascade_text(surface, font_size, text, xy_topleft, color):
    words = [word.split(' ') for word in text.splitlines()]  # 2D array where each row is a list of words.
    font = pygame.font.Font(FONT, font_size)
    space, word_height = font.size(' ')  # The width of a space.
    max_width, max_height = surface.get_size()
    x, y = xy_topleft
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


def frame_text(lines: list[str], style='╔═╗╚╝║'):
    """
    Possible styles:
    ╔═╗╚╝║
    /–\\/|
    ┏━┓┗┛┃
    """

    max_width = max(len(line) for line in lines)

    top = style[0] + style[1]*max_width + style[2] + '\n'
    bottom = '\n' + style[3] + style[1]*max_width + style[4]

    return top + '\n'.join(style[5] + line.ljust(max_width) + style[5] for line in lines) + bottom


# Graphical effects and details
class Bar:
    def __init__(
            self,
            size,
            width,
            fill_color,
            max_value,
            base_color=colors["bar_base"],
            show_number=False,
            cache=True
    ):
        self.max_value = max_value
        self.show_number = show_number
        self.base_color = base_color
        self.width = width
        # Generate sequence of ASCII loading bars representing different states
        bar_set = []
        for i in range(width+1):
            bar_set.append([['[', base_color], ['█' * i, fill_color], [(width - i) * '_' + ']', base_color]])
        # Generate sequence of surfaces, cache them
        self.surfaces = [ascii_draws(size, string) for string in bar_set]
        self.font_size = size
        self.rect = self.surfaces[0].get_rect()

        self.caching = cache
        self.cache = []
        self.display_timer = 0

    def display(self, value):
        # Only recache every 0.1s:
        if self.caching and self.display_timer <= 0.1 and self.cache:
            self.display_timer += FPS_TICK
            return self.cache
        else:
            self.display_timer = 0

        # Find closest corresponding image to requested
        if value <= 0:
            index = 0
        elif value >= self.max_value:
            index = -1
        else:
            index = int(value * self.width / self.max_value)
        # If show_number, blit rounded value onto bar
        if self.show_number:
            draw_number = ascii_draw(self.font_size, str(round(value)), self.base_color)
            surface = self.surfaces[index].copy()
            num_rect = draw_number.get_rect(center=surface.get_rect().center)
            surface.blit(draw_number, num_rect)
        else:  # Don't copy
            surface = self.surfaces[index]

        self.cache = surface, self.rect

        return self.cache


# Cheats/debugs
def morph_equipment(char):
    for slot in char.weapon_slots:
        char.slots[slot].builder = {}
        char.slots[slot].generate(char.size, tier=random.randint(1, 4))
        char.slots[slot].update_stats()


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
