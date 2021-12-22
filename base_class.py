# todo:
# after tech demo:
# todo:
#  ?? Compared surface for stat cards
# todo: separate upside and downside lists for enemy weapons
# todo: respect "origin" for materials, prevent mixing evil and good material

from primitive import *
from perlin_noise.perlin_noise import PerlinNoise


# Define base classes:
class MouseV:
    # MouseV is supposed to have a singular instance
    instance = None

    def __new__(cls):
        if cls.instance is None:
            return super().__new__(cls)
        return cls.instance

    def __init__(self):
        if self.__class__.instance is not None:
            return
        self.mouse_state = self.last_mouse_state = False, False, False
        self.__class__.instance = self
        self.v = v()
        self.custom_pointer = v()

    def update_buttons(self):
        self.last_mouse_state = self.mouse_state
        self.mouse_state = pygame.mouse.get_pressed(num_buttons=3)
        self.v = v(pygame.mouse.get_pos())

    def input_changed(self):
        return self.mouse_state != self.last_mouse_state

    def remember(self, point: v):
        self.custom_pointer = point

    @classmethod
    def instantiate(cls):
        cls.instance = cls()

    def get_v(self, start_v=None):
        return self.v if start_v is None else self.v - start_v


class Material:
    _metal_bonus = 2
    registry = dict()
    collections = {
        'plateless_bone': {'cattle horn', 'game antler', 'demon horn', 'unicorn horn', 'moonbeast antler', 'wishbone'},
        'short_bone': {'mollusc shell', 'dragon scale'},
        'elven': {'mythril', 'mallorn', 'spidersilk', 'elven cloth', 'riverglass'},
        'mythical': {'moonglow silver', "unicorn horn", "moonbeast antler", "dragon scale",
                     "dragonhide", "unicorn kashmir", "Giant's beanstalk", "niflheim ice"},
        'demonic': {'fae iron', 'golden', 'warped stem', 'demon horn', 'soulcrystal', 'Stygian papyrus'},
        'ferrous': {'pig iron', 'iron', 'sanchezium', 'dwarfish steel', 'damascus steel'},
        'bendable_bone': {"fish bone", 'cattle horn', 'game antler', 'demon horn', 'unicorn horn',
                          'moonbeast antler', 'wishbone', 'carbon plate', 'cursed bones'},
        'celestial': {'moonglow silver', "moonbeast antler"},
        "silver": {'silver', 'quicksilver', 'moonglow silver'}
    }
    sounds = {
        "metal": "metal",
        "precious": "metal",
        "wood": "wood",
        "reed": "wood",
        "leather": "wood",
        "bone": "bone",
        "feather": "bone",
        "mineral": "mineral",
        "cloth": "mineral"
    }

    def __init__(self, name, hsl_min, hsl_max, tier, physics, weight, attacks_color=None, occurence=2):
        self.name = name
        self.hsl_min = hsl_min
        self.hsl_max = hsl_max
        self.tier = tier
        self.physics = physics
        self.weight = weight
        self.attacks_color = attacks_color
        self.occurence = occurence if physics != 'metal' else self._metal_bonus*occurence

    def generate(self):
        """Return color from material range"""
        color = [random.randint(self.hsl_min[atom], self.hsl_max[atom]) for atom in range(len(self.hsl_min))]
        if len(color) < 4:
            color.append(100)
        out_color = c(0, 0, 0, 0)
        color[0] = color[0] % 360
        out_color.hsla = color
        return out_color

    def corrode(self, ask='adj'):
        """
        :return: return a corosion type according to material physics
        """
        word = 'adj', 'verb', 'noun'

        if self.physics in ('metal', 'precious'):
            answer = 'corroded', 'corrodes', 'rust'
        elif self.physics in ('wood', 'reed', 'bone'):
            answer = 'rotten', 'rots', 'rot'
        elif self.physics in ('cloth', 'leather'):
            answer = 'tattered', 'tatters', 'tatter'
        elif self.physics == 'mineral':
            answer = 'clouded', 'fades', 'shards'
        else:
            answer = 'degraded', 'degrades', 'discard'

        return answer[word.index(ask)]

    @classmethod
    def pick(cls, physics_list, tier, filter_func=lambda x: True, weights=True):
        """
        Pick suitable material with defined physics and tier
        Arguments (1 AND 2) OR 3 MUST be specified
        """
        if not tier:
            return

        matching = [
            cls.registry[X]
            for X in cls.registry
            if cls.registry[X].tier == tier and cls.registry[X].physics in physics_list and filter_func(cls.registry[X])
        ]

        if weights:
            weight_list = [material.occurence for material in matching]
            result = random.choices(matching, weight_list)[0]
        else:
            result = random.choice(matching)
        return result.name

    @classmethod
    def init(cls):
        for sample in raw_materials:
            cls.registry[sample] = cls(
                sample,
                raw_materials[sample]['hsva_values']['min'],
                raw_materials[sample]['hsva_values']['max'],
                raw_materials[sample]['tier'],
                raw_materials[sample]['physics'],
                raw_materials[sample]['weight'],
                raw_materials[sample].get('attacks_color', None),
                raw_materials[sample].get('occurence', 2)
            )

            # Convert to Color object
            if cls.registry[sample].attacks_color:
                cls.registry[sample].attacks_color = c(cls.registry[sample].attacks_color)


class Shaker:
    _max_duration = 1.2
    _minimum_intensity = 0.05
    _frequency = 0.003

    def __init__(self, fading=True, max_shake=SHAKE_RANGE):
        self.oscillators: list = []
        self.fading = fading
        self.max_shake = max_shake

    def add_shake(self, intensity):
        seed = pygame.time.get_ticks()
        self.oscillators.append((min(1.0, intensity), PerlinNoise(seed=seed), PerlinNoise(seed=2*seed)))

    def get_current_v(self):
        repacked_oscillators = []
        timestamp = self._frequency * pygame.time.get_ticks()
        cumulative_v = v()
        for intensity, shaker_x, shaker_y in self.oscillators:
            cumulative_v.x += self.max_shake*intensity*shaker_x(timestamp)
            cumulative_v.y += self.max_shake*intensity*shaker_y(timestamp)

            # Reduce intensity:
            if self.fading:
                time_remaining = lerp((0, self._max_duration), intensity) - FPS_TICK
                new_intensity = lerp((0, 1), time_remaining / self._max_duration)
            else:
                new_intensity = intensity

            # Repack if intensity is above treshold:
            if intensity > self._minimum_intensity:
                repacked_oscillators.append((new_intensity, shaker_x, shaker_y))

        # Save repacked oscillators:
        self.oscillators = repacked_oscillators

        # Set max shake limits:
        limit = self.max_shake*0.5 if OPTIONS["screenshake"] == 2 else self.max_shake*0.25
        cumulative_v.x = cumulative_v.x if cumulative_v.x < limit else limit
        cumulative_v.x = cumulative_v.x if cumulative_v.x > -limit else -limit
        cumulative_v.y = cumulative_v.y if cumulative_v.y < limit else limit
        cumulative_v.y = cumulative_v.y if cumulative_v.y > -limit else -limit

        return cumulative_v

    def reset(self):
        self.oscillators = []


class Bar:
    # Every Bar that is created stores input data in cache;
    # SceneHandlers create dozens of characters with same stats, who can share one instance for same bars
    instance_cache = dict()

    def __new__(
        cls,
        size,
        width,
        fill_color,
        max_value,
        base_color=colors["bar_base"],
        show_number=False,
        style='[█_]',
        predetermined: int = None
    ):
        created = size, width, tuple(fill_color), max_value, tuple(base_color), show_number, \
                    style, predetermined
        if created not in cls.instance_cache or predetermined is not None:
            return super().__new__(cls)
        return cls.instance_cache[created]

    def __init__(
        self,
        size,
        width,
        fill_color,
        max_value,
        base_color=colors["bar_base"],
        show_number=False,
        style='[█_]',
        predetermined: int = None
    ):
        # Create a key with arguments to store in
        creation_arguments = size, width, tuple(fill_color), max_value, tuple(base_color), \
                             show_number, style, predetermined

        if creation_arguments not in self.__class__.instance_cache:
            self._init(*creation_arguments)
            self.__class__.instance_cache[creation_arguments] = self
        elif predetermined is not None:
            self._init(*creation_arguments)

    def _init(self, size, width, fill_color, max_value, base_color, show_number, style, predetermined):
        self.max_value = max_value
        self.show_number = show_number
        self.base_color = base_color
        self.width = width
        self.style = style
        self.fill_color = fill_color
        self.size = size

        # Return set value:
        self.predetermined = predetermined

        # Draw surfaces:
        self._update_surfaces()

        self.font_size = size
        self.rect = self.surfaces[0].get_rect()

        # Caching:
        # self.cache = []
        # self.last_updated = pygame.time.get_ticks()

    def _update_surfaces(self):
        if self.predetermined is not None:
            # Generate a single surface displaying given value:
            i = round(self.width * self.predetermined / self.max_value)
            bar_string = (
                [self.style[0], self.base_color],
                [self.style[1] * i, self.fill_color],
                [(self.width - i) * self.style[2] + self.style[3], self.base_color]
            )
            self.surfaces = [ascii_draws(self.size, bar_string)]

        else:
            # Generate sequence of ASCII loading bars representing different states
            bar_set = []
            for i in range(self.width+1):
                bar_set.append((
                    [self.style[0], self.base_color],
                    [self.style[1] * i, self.fill_color],
                    [(self.width - i) * self.style[2] + self.style[3], self.base_color]
                ))
            # Generate sequence of surfaces, cache them
            self.surfaces = [ascii_draws(self.size, bar_string) for bar_string in bar_set]

    def display(self, value):
        if self.predetermined:
            return self.surfaces[0], self.rect

        # Only recache every 0.1s:
        # Not needed with persistent surface cache; also interferes with single cache
        # If I ever need it, there should be a class dict with character-specific timers
        # access_time = pygame.time.get_ticks()
        # if self.caching and access_time - self.last_updated < 100 and self.cache:
        #    return self.cache
        # else:
        #    self.last_updated = pygame.time.get_ticks()

        # Find the closest corresponding image to requested
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

        # self.cache = surface, self.rect

        return surface, self.rect


class Equipment:
    registry = {}
    # Overridable:
    class_name = None
    hitting_surface = None
    prefer_slot = None
    upside = []
    downside = []
    aim_drain_modifier = 0

    def __init__(self, *args, equipment_dict=None, roll_stats=True, **kwargs):
        self.roll_stats = roll_stats

        if equipment_dict is None:
            self.builder = dict()
            self.tier = None
        else:
            self.builder = equipment_dict
            self.tier = equipment_dict['tier']

        self.surface = None
        self.in_use = False
        self.loot_cards = dict()

        # Dict for character-specific variables; filled by on_equip method:
        self.character_specific = dict()

        # Each frame, holding character will querry this variable to limit own speed
        self.speed_limit = 1.0

        # Spawn particles for scene to pick up:
        self.particles = []

        # Generate durability (2-5):
        self.durability = self.max_durability = 3 + random.choices(
            [-1, 0, 1, 2],
            [10, 50, 10, 5] if roll_stats else [0, 1, 0, 0]
        )[0]

        # Some equipment has chance to be dropped:
        self.queue_destroy = False

        self.prevent_regen = False

    def reset(self, character, reposition=True):
        self.particles.clear()

    def generate(self, tier=None):
        """
        Skeleton for subclasses. Intended to generate own surface object and update stats according to picked materials
        """
        pass

    def portrait(self, rect: r, offset=BASE_SIZE*2, discolor=True):
        """Skeleton to draw an in-game object showing the item in inventory"""
        pass

    def activate(self, character, continuous_input):
        """Modifies: vector to move character, duration, dict of slots to lock and angle to lock them at"""
        pass

    def update_stats(self):
        pass

    def aim(self, *args, **kwargs):
        return None

    def hitbox(self):
        return []

    def is_dangerous(self):
        return False

    def drop(self, character):
        return []

    def reduce_damage(self, penalty):
        pass

    def damage(self):
        self.durability = self.durability-1

        # Pick a part of the weapon to be "damaged"
        # 60% of the time, it's hitting surface
        if self.hitting_surface and random.random() < 0.6:
            breaking_part = self.hitting_surface
        else:
            breaking_part = random.choice(list(self.builder["constructor"].keys()))

        breaking_material = Material.registry[self.builder["constructor"][breaking_part]["material"]]
        sentence = f"You survive, but {breaking_part} of your {self.builder['class'].lower()} "\
            f"{breaking_material.corrode(ask='verb')}"

        if self.durability == 0:
            sentence += ' completely!'
            if self.prefer_slot in ('main_hand', 'off_hand'):
                # Lose 30% damage
                self.reduce_damage(0.3)
                sentence += ' 30% damage lost.'
        else:
            sentence += '.'

        # Update comparison loot cards:
        self.redraw_loot()

        return sentence

    def redraw_loot(self):
        for card in self.loot_cards:
            self.loot_cards[card] = LootCard(self, compare_to=card)

    def show_stats(self, compare_to=None):
        return dict()

    def description(self):
        # Form list of parts and their material
        part_material_dict = {
            part: self.builder["constructor"][part]["material"]
            for part in self.builder["constructor"]
        }

        # If there is only one material, return simple description, e.g. Iron Dagger:
        if len(set(part_material_dict.values())) == 1:
            painted = False
            for part in self.builder["constructor"]:
                if "painted" in self.builder["constructor"][part].get("tags", ()):
                    painted = True
            for part in part_material_dict:
                m_name = "Painted " + part_material_dict[part] if painted else part_material_dict[part].capitalize()
                return f'{m_name} {self.builder["class"].lower()}'

        # Order parts by being important (hitting surface), then alphabetically
        parts_order = sorted(part_material_dict, key=lambda x: (x != self.hitting_surface, x), reverse=False)

        # Description is formed as follows: hitting part first, all parts except last separated by ", ", " and "
        # last part
        resulting_string = f'{self.builder["class"]} with '

        # 1. Hitting part:
        if "painted" in self.builder["constructor"][parts_order[0]].get("tags", ()):
            resulting_string += 'painted '

        resulting_string += f'{part_material_dict[parts_order[0]]} {parts_order[0]}'
        # 2. All parts except first and last:
        for part in parts_order[1:-1]:
            resulting_string += ', '
            if "painted" in self.builder["constructor"][part].get("tags", ()):
                resulting_string += 'painted '
            resulting_string += f'{part_material_dict[part]} {part}'
        # 3. Last part:
        resulting_string += ' and'
        if "painted" in self.builder["constructor"][parts_order[-1]].get("tags", ()):
            resulting_string += ' painted'
        resulting_string += f' {part_material_dict[parts_order[-1]]} {parts_order[-1]}'

        return resulting_string

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # Preserves string literals for each of classes that are eligible to spawn
        if cls.class_name:
            cls.registry[cls.class_name] = cls

    def on_equip(self, character):
        pass

    def limit_speed(self):
        current_limit = self.speed_limit
        self.speed_limit = 1.0
        return current_limit

    def drop_json(self):
        own_stats = self.__dict__.copy()

        # Pop all generated objects:
        for stat in ['loot_cards', 'character_specific', 'particles', 'trail_frames', 'wing_tips', 'wing_tips_v']:
            own_stats.pop(stat, 0)

        for key in [key for key, value in own_stats.items() if isinstance(value, (s, v, c, Character, Equipment))]:
            own_stats.pop(key)

        # Modify constructor to use lists instead of colors:
        for part in self.builder["constructor"]:
            own_stats["builder"]["constructor"][part]["color"] = self.builder["constructor"][part]["color"][:]

        return json.dumps(own_stats, sort_keys=False)

    def from_json(self, json_string):
        new_stats = json.loads(json_string)
        self.__dict__.update(**new_stats)

        # Re-generate:
        self.generate()
        self.redraw_loot()


class Nothing(Equipment):
    instance = None
    held_position = v()
    default_angle = 0
    hides_hand = False
    hand_rotation = 0

    def __bool__(self):
        return False

    # Singleton class:
    def __new__(cls):
        if cls.instance is None:
            return super().__new__(cls)
        return cls.instance

    def __init__(self):
        if self.__class__.instance is not None:
            return
        super().__init__()
        self.last_angle = 0
        self.activation_offset = v()
        self.lock_timer = 0
        self.disabled = False
        self.dangerous = False

    def aim(self, hilt_placement, aiming_vector, character):
        self.last_angle = -aiming_vector.as_polar()[1]

    def activate(self, character, continuous_input):
        # todo: punch! stuns and displaces enemy, minimal damage
        pass

    def lock(self, duration, angle=None, inertia=None):
        pass

    def reset(self, character, **kwargs):
        pass

    def description(self):
        return

    def limit_speed(self):
        return 1.0


class Character:
    registry = dict()
    weapon_slots = []
    collision_group = 1  # Default for enemies
    hit_immunity = 0.6
    difficulty = 0
    has_blood = True
    remains_persistence = 1  # 0 to remain indefinitely in scene
    theme = None
    free_fall_range = 0.5, 1.2
    knockback_resistance = 0.1
    loot = None

    # Logic:
    pct_cap = 0.15
    _dps_pct_cap = 1
    class_name = None
    debug = False
    drops_shields = True
    sees_enemies = False  # Only important for player characters

    # Class-specific:
    color = None
    blood = None

    # Face collections are size-specific
    all_faces = dict()
    flipped_faces = dict()

    def __init__(
            self,
            position,
            size,
            agility,
            max_speed,
            stamina,
            stamina_restoration,
            hp_restoration,
            health,
            color,
            blood,
            faces,
            attacks_color,
            hp_color,
            sp_color=colors["sp_color"],
            ai=None,
            name=None,
            **kwargs
    ):

        # Basics:
        self.max_stamina = stamina
        self.stamina = stamina  # At inception, max out
        self.stamina_restoration = stamina_restoration

        self.max_hp = health
        self.hp = health
        self.hp_restoration = hp_restoration

        # Inferred from stats
        self.size = int(BASE_SIZE * size)
        self.weight = 2 * self.max_hp * size
        self.flip_time = 1/agility

        # Visual:
        self.visual_state = 'idle'
        self.visual_timer = 0

        # Behavior:
        self.ai = ai

        # Movement:
        self.position = position
        self.agility = agility
        self.max_speed = max_speed * BASE_SIZE * FPS_TICK
        self.speed = v()
        self.facing_right = False

        # Special movement:
        self.ramming = False
        self.phasing = False

        # Acceleration depends on FPS:
        self.acceleration = 0.17 * self.agility * BASE_SIZE * FPS_TICK

        # Ability to roll:
        self.max_roll = 0
        self.rolling = 0
        self.rolled_through = []
        self.roll_cooldown = 0

        # Anchoring:
        self.anchor_point = None
        self.anchor_timer = 0
        self.anchor_weapon = None

        # To be set by character subclass or externally
        self.body_coordinates = None

        # Save class colors:
        if self.__class__.color is None:
            self.__class__.color = color
            self.__class__.blood = blood

        # Initialize a dictionary of all own faces and class constants in own class
        if self.size not in self.__class__.all_faces:

            self.__class__.all_faces[self.size] = dict()
            self.__class__.flipped_faces[self.size] = dict()

            for face in faces:
                frames = []
                flipped_frames = []
                for frame in faces[face][:-1]:
                    surface = ascii_draw(self.size, frame, self.color)
                    frames.append(surface)
                    flipped_frames.append(pygame.transform.flip(surface, True, False))
                # Last entry in list is time the emotion should be played:
                frames.append(faces[face][-1])
                flipped_frames.append(faces[face][-1])
                self.flipped_faces[self.size][face] = frames
                self.all_faces[self.size][face] = flipped_frames

        self.face = self.all_faces[self.size]['idle']
        # Must be updated by .draw method
        self.hitbox = []

        # Equipment slots:
        self.slots = {}

        # Color of attacks:
        self.attacks_color = c(attacks_color)

        # HP, SP bars:
        self.bars: dict = {
            "hp": Bar(BASE_SIZE // 3, 10, hp_color, health, base_color=colors["bar_base"], show_number=True),
            "stamina": Bar(BASE_SIZE // 3, 10, sp_color, stamina, base_color=colors["bar_base"], show_number=False)
        }

        # Physics/damage/collision support:
        self.channeling = {}
        self.channeling_timer = 0
        self.drawn_equipment = {}

        self.state = 'idle'
        self.state_timer = 0

        self.shielded = None

        self.bleeding_timer = 0
        self.bleeding_intensity = 0.0

        self.disabled_timer = 0  # to cleanse if disabled for too long
        self.immune_timer = 0
        self.immune_timer_wall = 0
        self.life_timer = 0

        self.wall_collision_v: v = v()

        # Stat cards:
        self.name = name or f"{self.__class__.__name__} Lv.??"
        self.stat_cards = {None: StatCard(self)}

        # Counter since last frame when character held dangerous weapon: affects stamina restoration
        self.since_dangerous_frame = 0

        # Limit fall duration:
        self.fall_duration = 0
        self._roll_fall()

    def _roll_fall(self):
        self.fall_duration = random.uniform(*self.free_fall_range)

    def anchor(self, duration, position=None, weapon=None):
        self.speed = v()
        if position:
            self.anchor_point = position
        elif weapon:
            self.anchor_weapon = weapon
        else:
            self.anchor_point = v(self.position)
        self.anchor_timer = duration

        # Already doubled by effect timer:
        # self.bars["anchor_timer"] = Bar(
        #     size=BASE_SIZE // 3,
        #     width=10,
        #     fill_color=colors["effect_timer"],
        #     max_value=duration,
        #     base_color=colors["bar_base"],
        #     show_number=False,
        #     cache=False
        # )

    def update(self, target=None, disable_weapon=False):
        # Prevent modification of mutable input:
        new_target = v(target or v())

        # Tick down timers:
        self.life_timer += FPS_TICK
        self.anchor_timer -= FPS_TICK

        # Tick down channel and execute task if needed:
        if self.channeling:
            # Disable aiming
            new_target = v()
            self.channeling_timer -= FPS_TICK

            # Execute and despawn bar if timer is reached:
            if self.channeling_timer <= 0:
                self.channeling["task"](**self.channeling["arguments"])
                self.bars.pop("channeling_timer", 0)
                self.channeling = {}

        # Tick down immune timer
        if self.immune_timer > 0:
            self.immune_timer -= FPS_TICK
        else:
            self.bars.pop("immune_timer", 0)

        # Modify current face state time (idle or in another state):
        self.state_timer -= FPS_TICK
        self.visual_timer += FPS_TICK

        # Process landing of flying characters
        if (
                self.state in DISABLED and
                self.state in AIRBORNE and
                self.state_timer < self.fall_duration and
                not (self.anchor_point or self.anchor_weapon)
        ):
            self.speed.y = 0
            self.set_state('hurt', self.state_timer)

        if self.state_timer <= 0 and self.state != 'idle':
            # If self was disabled and possessed by an AI, resasses situation:
            if self.ai and self.state in DISABLED:
                self.ai.analyze(self.ai.scene)
            # If character leaves airborne state, reset self.speed
            if self.state in AIRBORNE:
                self.speed = v()

            self.set_state('idle', 0)

        if self.state != self.visual_state and (self.visual_timer >= 0.4 or self.visual_state in IDLE):
            self.visual_state = self.state
            self.visual_timer = 0

        self.breath()

        dangerous = False

        # Aim held weapons:
        for weapon in self.weapon_slots:

            hilt_placement = v(self.position) + v(self.body_coordinates[weapon])

            # Account for weapons requiring special stances:
            if self.slots[weapon].held_position != v():
                held_scale_down = self.size / BASE_SIZE
                held_offset = v(
                    self.slots[weapon].held_position.x * held_scale_down,
                    self.slots[weapon].held_position.y * held_scale_down
                )
                held_offset.x *= -1 if self.facing_right else 1
                hilt_placement += held_offset

            # Modify Y coordinate in accordance to time passed (math.sin)
            if weapon == 'main_hand':  # main hand is "steadier"
                steady = 0.1
            elif self.shielded == self.slots[weapon]:  # equipped shield does not oscilate
                steady = 0
            else:
                steady = 0.25
            hilt_placement.y += self.size * math.sin(self.life_timer * 3) * steady

            if weapon == 'main_hand' or self.slots[weapon].held_position != v():
                # offset hilt by small amount in target direction
                offset_vector = v(self.size * 0.5, 0).rotate(-self.slots[weapon].last_angle)
                # Elliptical orbit looks better
                offset_vector.x = offset_vector.x * 2
                hilt_placement = pygame.math.Vector2(hilt_placement) + offset_vector

            if new_target != v():
                aiming_vector = v(new_target) - hilt_placement
            else:  # Rotate to default angle
                if self.ai is None:
                    aiming_vector = v(BASE_SIZE * 4, 0).rotate(-self.slots[weapon].last_angle)
                else:
                    aiming_vector = v(BASE_SIZE*4, 0).rotate(-self.slots[weapon].default_angle)
                    if not self.facing_right:
                        aiming_vector.x *= -1

            self.slots[weapon].aim(
                hilt_placement=hilt_placement,
                aiming_vector=v() if disable_weapon and self.slots[weapon].aim_drain_modifier > 0 else aiming_vector,
                character=self
            )
            dangerous = dangerous or self.slots[weapon].dangerous or self.slots[weapon].disabled

        # If weapons were dangerous this frame, reset counter:
        if dangerous:
            self.since_dangerous_frame = 0
        else:
            self.since_dangerous_frame += FPS_TICK

        self.hitbox = [self.face[0].get_rect(center=self.position)]

        # Modify hitboxes in special cases:
        if self.ramming:
            # Increase main hitbox:
            self.hitbox[0].inflate_ip(0, self.hitbox[0].height*1.2)

        # elif self.phasing:
            # Disable hitboxes
            # self.hitbox = []

    def draw(self, body_only=False, freeze=False, no_bars=False):
        """Return set of surface and rectangles to draw them on, depending on what is equipped"""

        return_list = []
        self.drawn_equipment = {}

        # Draw bars:
        if not no_bars and not body_only and any(self.bars):
            return_list.extend(self._draw_bars())

        return return_list

    def _draw_bars(self):
        return_list = []

        bar_placement = v(self.body_coordinates['bars']) + v(self.position)
        drawn_bars = dict()
        bar_rects: dict = {}
        for bar in self.bars:
            self._fill_bar_dicts(bar, drawn_bars, bar_rects)

        # Order bars, hp first, stamina second, then alphabetically
        all_bars: list = list(self.bars.keys())
        all_bars.sort(key=lambda x: (x != "hp", x != "stamina", x))

        # Find the topleft corner of first bar
        topleft_v = bar_placement - v(
            bar_rects[all_bars[0]].width*0.5,
            sum([bar_rects[bar].height for bar in bar_rects])*0.5
        )

        for bar_key in all_bars:
            # Prepare bar surface and rect
            surface = drawn_bars[bar_key]
            rect = bar_rects[bar_key].move(topleft_v)
            # Shift topleft for the next bar
            topleft_v.y += rect.height
            return_list.append((surface, rect))

        return return_list

    def _fill_bar_dicts(self, bar: str, drawn_bars: dict, bar_rects: dict):
        drawn_bars[bar], bar_rects[bar] = self.bars[bar].display(self.__dict__[bar])

    def set_state(self, state, duration):
        # If character is skewered, ignore:
        if self.anchor_weapon is not None:
            return

        # Special state sounds:
        if state == 'jumping':
            play_sound('jump', 0.3 * self.size / BASE_SIZE)

        # Limit free fall duration:
        if state in AIRBORNE and state in DISABLED:
            self._roll_fall()
            self.fall_duration = duration if duration < self.fall_duration else duration - self.fall_duration

        self.state = state
        self.state_timer = duration
        self.ramming = (state == 'bashing')
        if self.visual_timer > 0.4:
            self.visual_timer = 0
        # Visual state is modified when .draw is called

    def move(self, direction_v, scene, limit=1.0):
        # If character is channeling, input is ignored:
        if self.channeling:
            direction_v = v()

        # If character is anchored, adjust position
        if self.anchor_timer > 0:
            if self.anchor_weapon:
                self.position = v(self.anchor_weapon.tip_v)
            else:
                try:
                    self.position = v(self.anchor_point)
                except ValueError:
                    print(self.anchor_point)
                    raise ValueError
            self.speed = v()
        else:
            self.anchor_point = None
            self.anchor_weapon = None
            self.bars.pop("anchor_timer", None)

        # If character is flying, under CC effect, or executing a manouver,
        # ignore input and keep going in existing direction
        if self.state in AIRBORNE:
            accelerate = FFA
        elif self.state in DISABLED or self.ramming or self.phasing:
            accelerate = v()

        # If direction is close enough, snap to it:
        elif direction_v != v() and direction_v.length_squared() <= self.acceleration:
            self.position += direction_v
            self.speed = v()
            return

        else:
            if self.speed != v():
                if direction_v == v():
                    # If acceleration in the direction is 0, make it have opposite direction
                    for coordinate in {0, 1}:
                        if direction_v[coordinate] == 0:
                            direction_v[coordinate] = -self.speed[coordinate]

            elif direction_v == v():
                # v = 0, a = 0
                return

            accelerate = direction_v
            if accelerate != v():
                accelerate.scale_to_length(self.acceleration)

            # If acceleration in the direction is 0 or opposite, make sure it's more effective at stopping
            for coordinate in {0, 1}:
                if self.speed[coordinate] * accelerate[coordinate] <= 0:
                    # Prevent jitter:
                    if self.speed[coordinate] * (self.speed[coordinate] + 2*accelerate[coordinate]) < 0:
                        self.speed[coordinate] = 0
                        accelerate[coordinate] = 0
                    else:
                        accelerate[coordinate] *= 2

        self.speed += accelerate

        # Limits for voluntary movement:
        if self.state not in AIRBORNE and self.state not in DISABLED and not self.ramming and not self.phasing:

            equipment_limit = 1.0
            for equipment in self.slots:
                equipment_limit *= self.slots[equipment].limit_speed()

            effective_max_speed = min(equipment_limit, limit)*self.max_speed

            # Backwards is half speed, forward is full speed
            if self.speed.x > 0 == self.facing_right:
                limited_speed_x = min(abs(self.speed.x), 0.5*effective_max_speed)
            else:
                limited_speed_x = min(abs(self.speed.x), effective_max_speed)
            limited_speed_x = math.copysign(limited_speed_x, self.speed.x)

            # Up and down is 0.6 of full speed
            limited_speed_y = min(abs(self.speed.y), 0.6*effective_max_speed)
            limited_speed_y = math.copysign(limited_speed_y, self.speed.y)

            self.speed.xy = limited_speed_x, limited_speed_y

            # Enter running state if max horizontal speed is reached:
            if (self.speed.x > 0) == self.facing_right and abs(self.speed.x) == self.max_speed and self.state in IDLE:
                self.set_state('running', 0.2)

            elif accelerate == v() and self.speed.length_squared() < self.acceleration:
                self.speed.xy = (0, 0)

        # Bounce off boundaries towards center if reached edge
        boundaries = (scene.field_rect.left+BASE_SIZE, scene.field_rect.right-BASE_SIZE), \
                     (scene.field_rect.top+BASE_SIZE, scene.field_rect.bottom-BASE_SIZE)
        center_v = scene.field_rect.center

        # Push disabled characters or characters somehow outside
        # Don't affect jumping or phasing characters (spawning)
        if self.immune_timer_wall > 0:
            self.immune_timer_wall -= FPS_TICK

        if not (self.ai and (self.phasing or self.state == 'jumping')):

            if self.state in DISABLED or not scene.field_rect.collidepoint(self.position):
                for coordinate in {0, 1}:
                    if not boundaries[coordinate][0] < self.position[coordinate] < boundaries[coordinate][1]:
                        to_center = center_v - v(self.position)
                        to_center.scale_to_length(POKE_THRESHOLD * 2)
                        to_center.y *= 0.6
                        # Log own speed for the scene to handle damage
                        if self.immune_timer_wall <= 0:
                            self.wall_collision_v = v(self.speed)
                            self.immune_timer_wall = self.hit_immunity
                        self.speed = v()
                        self.push(to_center, 0.4, state='flying')
                        break

            # Voluntary movement is slowed instead
            else:
                # Find distance to edges; if it's less than BASE SIZE, scale it down
                for axis in {0, 1}:
                    for side in boundaries[axis]:
                        edge_distance = self.position[axis] - side
                        if abs(edge_distance) <= 6.25*BASE_SIZE and (self.speed[axis] * edge_distance) < 0:
                            self.speed[axis] *= 0.16 * abs(edge_distance) / BASE_SIZE

        new_place = v(self.position) + self.speed
        self.position = new_place

    def _interrupt_channel(self):
        self.channeling = dict()
        self.channeling_timer = 0
        self.bars.pop("channeling_timer", 0)

    def push(self, vector, time, state='flying', **kwargs):
        # Interrupt any active channels:
        if (
            self.channeling and
            self.anchor_timer <= 0 and
            (state in DISABLED or not self.drops_shields)
        ):
            self._interrupt_channel()

        self.set_state(state, time)
        self.speed = vector
        # Force visual state
        self.visual_timer = 0
        self.visual_state = state
        # Lock weapons at current angles
        if state != 'active':
            for slot in self.weapon_slots:
                weapon = self.slots[slot]
                weapon.inertia_vector = v()
                weapon.activation_offset = v()

                if weapon.lock_timer <= 0:
                    weapon.lock(time, angle=weapon.last_angle)
                    weapon.disabled = True

    def use(self, slot, continuous_input, **kwargs):
        if self.state in DISABLED or self.channeling:
            return

        # Test if we always activate:
        always_active = False
        try:
            # If we are a Dagger ready to roll, break, as activation should always be allowed:
            if self.slots[slot].last_parry is not None:
                always_active = True
        except AttributeError:
            pass

        try:
            # If we are a Katar or Spear with a skewered enemy, activation should always be allowed:
            if self.slots[slot].kebab is not None:
                always_active = True
        except AttributeError:
            pass

        try:
            # If we are a Shield, activation should always be allowed:
            if self.slots[slot].parry_window and self.slots[slot].activation_offset != v():
                always_active = True
        except AttributeError:
            pass

        # Don't activate if any other weapon is in use
        for other_slot in filter(
                lambda x: self.slots[x] and x != slot and self.slots[x].prevent_activation,
                self.weapon_slots
        ):
            if always_active:
                break

            if self.slots[other_slot].in_use or self.slots[other_slot].activation_offset != v():
                return

        self.slots[slot].activate(character=self, continuous_input=continuous_input, **kwargs)

    def kill(self):
        """Drop a surface of self & equipment to be faded and deleted by handling scripts"""
        self.set_state("dead", 60)
        # Also force visual state
        self.visual_timer = 0
        self.visual_state = "dead"

        remains_set = []

        # Get body parts:
        body = self.draw(body_only=True)
        for surf, rect in body:
            nudge = v()
            r_phi = self.max_speed, -random.randint(60, 120)
            nudge.from_polar(r_phi)
            remains_set.append((surf, rect, self.speed + nudge))

        for weapon in self.weapon_slots:
            self.slots[weapon].reset(self, reposition=False)
            remains_set.append(self.slots[weapon].drop(self))

        return remains_set, self.remains_persistence

    def hurt(self, damage, vector, duration=1.5, deflectable=True, weapon=None, offender=None) -> (bool, int):
        """Reduces HP and pushes self in target direction; returns Boolean, True if character survived the attack"""
        if deflectable and self.shielded:
            vector, damage = self.shielded.block(self, damage, vector, weapon, offender)

            # If shield parried, return it outside:
            if damage < 0:
                return True, damage

        if weapon:
            # Scale vector down depending on character weight:
            vector *= 0.02 * weapon.pushback * weapon.weight * (1-self.knockback_resistance)

        if vector != v() and self.anchor_weapon is None:
            self.push(vector, duration, state='hurt')
        elif damage > 0:
            self.set_state('hurt', duration)

        if damage > 0:
            self.immune_timer = self.hit_immunity
            # Spawn a countdown bar
            hurt_bar = Bar(
                size=BASE_SIZE // 3,
                width=10,
                fill_color=colors["effect_timer"],
                max_value=self.hit_immunity,
                base_color=colors["bar_base"],
                show_number=False
            )
            self.bars['immune_timer'] = hurt_bar

            # Make sure character now has at least 10% max stamina
            self.stamina = max(self.stamina, self.max_stamina*0.1)

        self.hp -= damage
        return self.hp > 0, damage

    def flip(self, new_collision=None, dormant=False):
        if new_collision is not None:
            self.collision_group = new_collision
        self.facing_right = not self.facing_right
        self.flipped_faces, self.all_faces = self.all_faces, self.flipped_faces
        self.speed = v()

        for point in self.body_coordinates:
            self.body_coordinates[point][0] *= -1

        for slot in self.weapon_slots:
            weapon = self.slots[slot]
            weapon.reset(self, )
            # Recalculate variables:
            weapon.on_equip(self)
            weapon.lock(0.2)

        if not dormant and self.ai:
            self.ai.analyze(self.ai.scene)

    def channel(self, duration, task, arguments=None):
        """disables character for duration, causing a task to be performed at the end of channeling"""
        # Test if character is disabled or if already channelling:
        if self.channeling or self.state in DISABLED:
            return

        # Test if any weapons are offset:
        if self.drops_shields:
            for slot in self.weapon_slots:
                if self.slots[slot].activation_offset != v():
                    return

        # Prevent weapons from moving:
        for slot in self.weapon_slots:
            self.slots[slot].inertia_vector = v()

        self.set_state("channeling", duration)

        self.channeling_timer = duration
        self.channeling["task"] = task
        self.channeling["arguments"] = arguments or dict()

        # Spawn a countdown bar:
        self.bars["channeling_timer"] = Bar(
            BASE_SIZE // 3,
            10,
            self.attacks_color,
            duration,
            base_color=colors["bar_base"],
            show_number=False
        )

        # Lock equipped weapons:
        for slot in self.weapon_slots:
            weapon = self.slots[slot]
            if not weapon:
                continue
            weapon.lock(duration=duration, angle=weapon.default_angle)

    def penalize(self) -> (bool, str):
        # Backpacked equipment can not be damaged
        viable_equipment = [
            self.slots[slot]
            for slot in self.slots
            if (
                    slot != 'backpack' and
                    self.slots[slot] and
                    self.slots[slot].durability > 0
            )
        ]

        if not viable_equipment:
            return False, "All equipment is broken!"

        # Don't break main hand weapon until it's the last one
        main_hand_weapon = self.slots['main_hand']
        if main_hand_weapon and len(viable_equipment) > 1:
            if main_hand_weapon.durability == 1:
                viable_equipment.remove(main_hand_weapon)

        # Equipment is more likely to be picked if it's less damaged (less likely to completely break)
        break_likelihood = [item.durability for item in viable_equipment]

        equipment = random.choices(viable_equipment, break_likelihood)[0]
        return True, equipment.damage()

    def ignores_collision(self) -> bool:
        return ((self.state in AIRBORNE and self.state not in DISABLED) or self.phasing) and self.anchor_weapon is None

    def is_flying_meat(self) -> bool:
        return self.state in DISABLED

    def reset(self):
        self.anchor_timer = 0
        self.anchor_point = None
        self.anchor_weapon = None
        self.hp = self.max_hp
        self.immune_timer = 1
        self.stamina = self.max_stamina
        self.set_state('idle', 0)
        self.visual_timer = 0
        self.visual_state = 'idle'

        # Reset own weapons
        for slot in self.weapon_slots:
            self.slots[slot].reset(self, reposition=True)
            if self.shielded is self.slots[slot]:
                self.shielded = None

        self.bleeding_intensity = 0
        self.bleeding_timer = 0

    def bleed(self, intensity, duration):
        self.bleeding_intensity = max(self.bleeding_intensity, intensity)
        self.bleeding_intensity = min(self.bleeding_intensity, self._dps_pct_cap)
        self.bleeding_timer += duration
        self.bars["bleeding_timer"] = Bar(
            BASE_SIZE // 3,
            10,
            self.blood,
            self.bleeding_timer,
            base_color=colors["bar_base"],
            show_number=False
        )

    def breath(self):
        if (
                self.stamina < self.max_stamina and
                self.state not in DISABLED and
                not any(self.slots[slot].prevent_regen for slot in self.slots)
        ):
            # If we are 'resting' by not having dangerous weapons for 2s, restore stamina faster:
            if self.since_dangerous_frame > 2:
                exhaust_mod = 2
            else:
                # Restore slower when stamina is low
                exhaust_mod = max(self.stamina / self.max_stamina, 0.5)
                # Restore slower when moving
                if self.speed.xy != [0, 0]:
                    exhaust_mod *= 0.5
                # Player character restores faster behind shield
                if self.ai is None and isinstance(self.shielded, Equipment):
                    exhaust_mod *= 1.5

            # Hurt characters restore stamina very fast:
            if self.immune_timer > 0:
                exhaust_mod *= 5

            # 30 SP/s is hard lower limit
            stamina_increment = max(self.stamina_restoration * exhaust_mod, 30)

            self.stamina = min(self.stamina + stamina_increment * FPS_TICK, self.max_stamina)

        # HP is passively healed
        if 0 < self.hp < self.max_hp:
            self.hp = min(self.hp + self.hp_restoration * self.max_hp * FPS_TICK, self.max_hp)

        # Bleeding ticks down; damage is never lethal:
        if self.bleeding_timer > 0:
            drop = self.max_hp * self.bleeding_intensity * FPS_TICK
            self.bleeding_timer -= FPS_TICK
            self.hp = max(self.hp - drop, 1)
        else:
            self.bleeding_intensity = 0
            self.bars.pop("bleeding_timer", None)

        # Cleanse chain-stuns from players
        if self.state in DISABLED and not self.ai:
            if self.disabled_timer >= 3:
                self.set_state('idle', 0)
            else:
                self.disabled_timer += FPS_TICK
        else:
            self.disabled_timer = 0

    def roll(self, vector, roll_cooldown=0, duration=0.5):
        # Play roll sound:
        play_sound('roll', 0.3*self.size/BASE_SIZE)

        # Set constants:
        self.rolled_through = []
        self.anchor_timer = 0
        self.phasing = True
        self.max_roll = self.rolling = duration
        self.roll_cooldown = roll_cooldown

        # Push self in direction
        self.speed = v()
        self.push(vector, duration, 'active')

        # Lock weapons in same position
        # Animating them would *look* cooler, but would also have made the feel much clunkier
        for slot in self.weapon_slots:
            weapon = self.slots[slot]
            if weapon:
                weapon.disabled = True
                weapon.lock(duration+0.2, angle=weapon.last_angle)

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        # Preserves string literals for each of classes that are eligible to spawn
        if cls.class_name:
            cls.registry[cls.class_name] = cls

    def equip(self, armament, slot):
        # Allow updating constants
        armament.on_equip(self)

        # Equipping Nothing drops slot content
        if not armament:
            self.slots[slot], drop = Nothing(), self.slots[slot]
            return drop

        # Orient weapon, if possible
        try:
            armament.last_angle = armament.default_angle if self.facing_right else 180 - armament.default_angle
        except AttributeError:
            pass

        # If slot is empty, just equip and drop Nothing
        if not self.slots[slot]:
            self.slots[slot] = armament
            return Nothing()

        # If available, move currently equipped item to backpack
        elif 'backpack' in self.slots and slot != 'backpack' and not self.slots['backpack']:
            self.slots[slot], self.slots['backpack'] = armament, self.slots[slot]
            return Nothing()

        # Otherwise, equip over, drop original content
        self.slots[slot], drop = armament, self.slots[slot]
        return drop


class Particle:
    shakeable = False
    clampable = False

    def __init__(self, position, lifetime, surface=None, rect=None):
        self.position = position[:]
        self.lifetime = self.max_lifetime = lifetime
        self.surface = surface
        self.rect = rect
        self.cache = None

    def draw(self, pause=False):
        if not pause and self.cache:
            return self.cache

        self.lifetime -= FPS_TICK
        self.cache = self.surface, self.rect
        return self.cache


class Card:
    """Metaclass for loots and stat cards"""
    xy_offset = BASE_SIZE * 2 // 3

    def __init__(self):
        self.surface = None
        self.compared_surface = None
        self.rect = None

    def draw(self, position, x_key=None, y_key=None, bounding_box=None, draw_compared=False):
        if bounding_box is None:
            # Use screen
            bounding_box = SCREEN.get_rect()

        # Orient loot card so that it is always closer to center:
        # Top/bottom half:
        if not y_key:
            if position[1] <= bounding_box.top + bounding_box.height // 2:
                y_key = 'top'
            else:
                y_key = 'bottom'

        # Left/right half:
        if not x_key:
            if position[0] <= bounding_box.left + bounding_box.width // 2:
                x_key = 'left'
            else:
                x_key = 'right'

        position_dict = {x_key: position[0], y_key: position[1]}
        surf = self.compared_surface if draw_compared else self.surface
        rect = surf.get_rect(**position_dict)
        rect.clamp_ip(bounding_box)
        return surf, rect


class LootCard(Card):
    stats_order = [
        "DAMAGE",
        "LENGTH",
        "WEIGHT",
        "KNOCKBACK",
        "SPEED",
        "DRAIN",
        "DEFLECT TIME",
        "ROLL DELAY",
        "BLEED",
        "ROLL WINDOW",
        "FULL CHARGE",
        "COOLDOWN",
    ]

    def __init__(self, equipment, compare_to: [None, Equipment] = None):
        self.compared_to = compare_to
        # Collect stats:
        stats_dict = equipment.show_stats(compare_to=compare_to)

        # Generate a surface
        uncut_surface = s(MAX_LOOT_CARD_SPACE.size, pygame.SRCALPHA)
        self.rect = MAX_LOOT_CARD_SPACE.copy()
        uncut_surface.fill(color=c(colors["loot_card"]))

        # 1. Weapon portrait
        portrait = r(0, 0, MAX_LOOT_CARD_SPACE.width, MAX_LOOT_CARD_SPACE.width // 2)

        # If weapon fits, draw normally:
        if equipment.surface.get_width() < portrait.width and equipment.surface.get_height() < portrait.height:
            uncut_surface.blit(equipment.surface, equipment.surface.get_rect(center=portrait.center))
        else:
            # Rotate weapon surface so that it is aligned with diagonal
            rotated_surface = pygame.transform.rotate(equipment.surface, 30)
            uncut_surface.blit(rotated_surface, rotated_surface.get_rect(topleft=portrait.topleft))

        next_element_top = portrait.height

        # 2. Weapon class name, durability and tier
        class_string = f'{equipment.builder["class"]} ({string["slot_names"][equipment.prefer_slot].lower()})'
        next_element_top += blit_cascade_text(
            uncut_surface,
            BASE_SIZE * 2 // 3,
            class_string,
            (self.xy_offset, next_element_top),
            c(colors["inventory_title"])
        ) + BASE_SIZE // 3

        tier_eval = stats_dict.get("TIER", {}).get("evaluation", 0)
        if tier_eval > 0:
            tier_color = colors["inventory_better"]
        elif tier_eval < 0:
            tier_color = colors["inventory_worse"]
        else:
            tier_color = colors["inventory_text"]

        tier_string = f'Tier {equipment.tier}'
        next_element_top += blit_cascade_text(
            uncut_surface,
            BASE_SIZE * 2 // 3,
            tier_string,
            (self.xy_offset, next_element_top),
            c(tier_color)
        ) + BASE_SIZE // 3

        durability_eval = stats_dict.get("DURABILTY", {}).get("evaluation", 0)
        if durability_eval > 0:
            durability_color = colors["inventory_better"]
        elif durability_eval < 0 or equipment.durability == 0:
            durability_color = colors["inventory_worse"]
        else:
            durability_color = colors["inventory_text"]

        durability_string = f'{"♥"*equipment.durability}{"♡"*(equipment.max_durability-equipment.durability)}' if \
            equipment.durability > 0 else f"{'✖'*equipment.max_durability}"
        durability_surface = ascii_draw(BASE_SIZE, durability_string, durability_color)
        durability_rect = durability_surface.get_rect(midtop=(uncut_surface.get_width()//2, next_element_top))

        uncut_surface.blit(durability_surface, durability_rect)

        next_element_top = durability_rect.bottom + BASE_SIZE // 3

        # 3. Upsides and downsides
        for text in equipment.upside:
            next_element_top += blit_cascade_text(
                uncut_surface,
                BASE_SIZE // 2,
                text,
                (self.xy_offset, next_element_top),
                c(colors["inventory_better"])
            )

        if equipment.upside:
            next_element_top += BASE_SIZE // 3

        for text in equipment.downside:
            next_element_top += blit_cascade_text(
                uncut_surface,
                BASE_SIZE // 2,
                text,
                (self.xy_offset, next_element_top),
                c(colors["inventory_worse"])
            )

        if equipment.downside:
            next_element_top += BASE_SIZE // 3

        # 4. Greyed-out description
        next_element_top += blit_cascade_text(
            uncut_surface,
            BASE_SIZE // 2,
            equipment.description(),
            (self.xy_offset, next_element_top),
            c(colors["inventory_description"])
        ) + BASE_SIZE // 3

        # 5. List stats
        for stat in filter(lambda x: x in stats_dict, self.stats_order):
            stat_eval = stats_dict[stat].get("evaluation", 0)
            if stat_eval > 0:
                stat_color = colors["inventory_better"]
            elif stat_eval < 0:
                stat_color = colors["inventory_worse"]
            else:
                stat_color = colors["inventory_text"]

            # Draw triangle indicator:
            if stat_eval > 0:
                quick_indicator = '▲'
            elif stat_eval < 0:
                quick_indicator = '▼'
            else:
                quick_indicator = ' '

            draw_order = [
                (quick_indicator, c(stat_color)),
                (stat + ": ", c(colors["inventory_text"])),
                (stats_dict[stat]["text"], c(stat_color))
            ]

            stat_surface = ascii_draws(BASE_SIZE//2, draw_order)
            uncut_surface.blit(stat_surface, (self.xy_offset, next_element_top))
            next_element_top += stat_surface.get_height()

        next_element_top += BASE_SIZE // 3

        # 6. Cut off surface by bottom content line and draw a frame around the card
        self.rect.inflate_ip(self.rect.width, next_element_top)
        self.surface = s((MAX_LOOT_CARD_SPACE.width, next_element_top), pygame.SRCALPHA)
        self.surface.blit(uncut_surface, (0, 0))

        # Draw frame
        frame_surface(self.surface, colors["inventory_text"])

        # 7. If comparison is specified, allow option to display a loot card on the right
        if compare_to:
            other_surface = compare_to.loot_cards[None].surface
            self.compared_surface = glue_horizontal(self.surface, other_surface, offset=BASE_SIZE//2)
        else:
            self.compared_surface = self.surface


class StatCard(Card):

    def __init__(self, character):
        # Generate a surface
        self.character = character
        self.compared_surface = None  # Should never be drawn
        self.rect = MAX_LOOT_CARD_SPACE.copy()
        self.redraw()

    def redraw(self):
        uncut_surface = s(MAX_LOOT_CARD_SPACE.size, pygame.SRCALPHA)
        uncut_surface.fill(color=c(colors["loot_card"]))
        next_element_top = self.xy_offset

        common_options = {
            "surface": uncut_surface
        }

        differing_options = [
            {
                "font_size": BASE_SIZE * 2 // 3,
                "text": f"{self.character.name}",
                "color": c(colors["inventory_title"])
            },
            {
                "font_size": BASE_SIZE // 2,
                "text": f"HP: {self.character.hp:.1f}/{self.character.max_hp:.0f}",
                "color": c(colors["inventory_text"])
            },
            {
                "font_size": BASE_SIZE // 2,
                "text": f"SP: {self.character.stamina:.1f}/{self.character.max_stamina:.0f}",
                "color": c(colors["inventory_text"])
            },
            {
                "font_size": BASE_SIZE // 2,
                "text": f"HP/s: {100*self.character.hp_restoration:.1f}%",
                "color": c(colors["inventory_text"])
            },
            {
                "font_size": BASE_SIZE // 2,
                "text": f"SP/s: ~{self.character.stamina_restoration:.0f}",
                "color": c(colors["inventory_text"])
            },
            {
                "font_size": BASE_SIZE // 2,
                "text": f"SIZE: {self.character.size/BASE_SIZE:.2f}",
                "color": c(colors["inventory_text"])
            },
            {
                "font_size": BASE_SIZE // 2,
                "text": f"WEIGHT: {0.75*self.character.weight:.0f} lbs",
                "color": c(colors["inventory_text"])
            },
            {
                "font_size": BASE_SIZE // 2,
                "text": f"AGILITY: {self.character.agility:.1f}",
                "color": c(colors["inventory_text"])
            },
            {
                "font_size": BASE_SIZE // 2,
                "text": f"SPEED: {self.character.max_speed:.1f}",
                "color": c(colors["inventory_text"])
            }
        ]

        for option_item in differing_options:
            next_element_top += blit_cascade_text(
                **common_options,
                **option_item,
                xy_topleft=(self.xy_offset, next_element_top)
            )

        # AI stats
        if self.character.ai:
            next_element_top += self.xy_offset
            ai_options = [
                {
                    "font_size": BASE_SIZE * 2 // 3,
                    "text": f"Mind:",
                    "color": c(colors["inventory_title"])
                },
                {
                    "font_size": BASE_SIZE // 2,
                    "text": f"MORALE: {self.character.ai.morale:.1f}",
                    "color": c(colors["inventory_text"])
                },
                {
                    "font_size": BASE_SIZE // 2,
                    "text": f"AGGRESSION: {self.character.ai.aggression:.1f}",
                    "color": c(colors["inventory_text"])
                },
                {
                    "font_size": BASE_SIZE // 2,
                    "text": f"SKILL: {self.character.ai.skill:.1f}",
                    "color": c(colors["inventory_text"])
                },
                {
                    "font_size": BASE_SIZE // 2,
                    "text": f"FLEXIBILITY: {self.character.ai.flexibility:.1f}",
                    "color": c(colors["inventory_text"])
                },
                {
                    "font_size": BASE_SIZE // 2,
                    "text": f"COURAGE: {self.character.ai.courage:.1f}",
                    "color": c(colors["inventory_text"])
                }
            ]

            for ai in ai_options:
                next_element_top += blit_cascade_text(
                    **common_options,
                    **ai,
                    xy_topleft=(self.xy_offset, next_element_top)
                )

        # Add bottom offset:
        next_element_top += self.xy_offset

        # Cut off surface by bottom content line and draw a frame around the card
        self.rect.update(0, 0, self.rect.width, next_element_top)
        self.surface = s((MAX_LOOT_CARD_SPACE.width, next_element_top), pygame.SRCALPHA)
        self.surface.blit(uncut_surface, (0, 0))

        # Draw frame
        frame_surface(self.surface, colors["inventory_text"])


class Inventory:
    slots_order = 'main_hand', 'off_hand', 'hat', 'backpack'

    def __init__(
            self,
            character: Character,
            rectangle: r = INVENTORY_SPACE,
            bg_color=colors["base"],
            foreground=DISPLAY_COLOR
    ):
        self.rect = rectangle
        self.character = character
        self.slot_rects = {}

        # Create basic surface:
        self.base = s(size=rectangle.size)
        self.base.fill(foreground)

        # Create spaces for inventory slots
        slot_x = 0
        for slot in self.slots_order:
            # Prepare rectangle for the weapon:
            slot_rect = r(slot_x, 0, self.rect.width // 4, self.rect.height)
            self.slot_rects[slot] = slot_rect

            # Write name of the slot
            slot_name_surf = ascii_draw(BASE_SIZE // 2, string["slot_names"][slot], colors["inventory_text"])
            slot_name_rect = slot_name_surf.get_rect(right=slot_x + slot_rect.width, top=0)
            self.base.blit(slot_name_surf, slot_name_rect)

            # Offset next rectangle
            slot_x += slot_rect.width

            # Draw a line along the right border
            pygame.draw.line(
                self.base,
                bg_color,
                v(slot_x, 0),
                v(slot_x, self.rect.height),
                BASE_SIZE // 6
            )

        # Form content on surface
        self.surface = None
        self.bars = {}
        self.update()

    def update(self):
        surface = self.base.copy()
        for slot in self.slots_order:

            content = self.character.slots[slot]
            if not content:
                continue

            #  1. Get a portrait of each weapon from each of character slots
            portrait = content.portrait(rect=self.slot_rects[slot])
            surface.blit(portrait, self.slot_rects[slot])

            # 2. Form a durability bar (backpacked equipment can not be damaged, so no bar displayed)
            if not slot == 'backpack':
                color = colors["inventory_durability"] if content.durability > 1 else colors["inventory_broken"]

                durability = Bar(
                    size=BASE_SIZE,
                    width=content.max_durability,
                    max_value=content.max_durability,
                    fill_color=color,
                    base_color=color,
                    show_number=False,
                    style=' ♥♡ ' if content.durability > 0 else ' ✖✖ ',
                    predetermined=content.durability
                )
                bar_surf, bar_rect = durability.display(content.durability)
                bar_left = (self.slot_rects[slot].width - bar_rect.width) // 2
                bar_rect.move_ip(bar_left + self.slot_rects[slot].left, BASE_SIZE // 2 + 3)
                surface.blit(bar_surf, bar_rect)

            # 3. Write down weapon class and tier
            class_string = f'{content.builder["class"]}'
            class_surf = ascii_draw(BASE_SIZE // 2, class_string, colors["inventory_text"])
            class_rect = class_surf.get_rect(left=self.slot_rects[slot].left + BASE_SIZE // 2)

            tier_string = f'{string["tier"]} {content.tier}'
            tier_surf = ascii_draw(BASE_SIZE // 2, tier_string, colors["inventory_text"])
            tier_rect = tier_surf.get_rect(bottomright=self.slot_rects[slot].bottomright)

            surface.blit(tier_surf, tier_rect)
            surface.blit(class_surf, class_rect)

        self.surface = surface

    def draw(self):
        return self.surface, self.rect
